"""Inspect the recorded compiler image without source mounts, compilation or a VM."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import re
import subprocess
import sys
import traceback
import uuid

IMAGE = 'solanafoundation/solana-verifiable-build@sha256:43206149a565ec35da95b1a909f4714f5d5f0d8241c31df24189e517acd18467'
RUSTC = '/root/.cache/solana/v1.37/platform-tools/rust/bin/rustc'
RUSTC_SHA = '7194df9c12e893cfa88fff5dd821d02d45910b4d375e13677b4723f45769a384'
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Fresh output directory required; preserve prior observations')
    output.mkdir(parents=True)
    evidence = output / 'evidence'
    evidence.mkdir()
    (evidence / 'observe.py').write_bytes(Path(__file__).read_bytes())
    state = {'status': 'running', 'scope': __doc__, 'image': IMAGE, 'commands': [],
             'source_mounted': False, 'build_attempts': 0, 'runtime_executions': 0,
             'actual_build_cpu_proven': False, 'historical_llvm_library_identity_proven': False}
    container = None
    container_name = None

    def save():
        (evidence / 'observation.json').write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')

    def run(label, command, required=True, timeout=60):
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raw = (error.stdout or b'') + (error.stderr or b'')
            name = label + '.log'
            (evidence / name).write_bytes(raw)
            state['commands'].append({'label': label, 'command': command, 'returncode': None,
                                      'timeout_seconds': timeout, 'log': name, 'bytes': len(raw),
                                      'sha256': hashlib.sha256(raw).hexdigest()})
            save()
            raise
        raw = result.stdout + result.stderr
        name = label + '.log'
        (evidence / name).write_bytes(raw)
        state['commands'].append({'label': label, 'command': command, 'returncode': result.returncode,
                                  'log': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        save()
        if required and result.returncode:
            raise RuntimeError(f'{label} failed; retained exit status and raw output')
        return result.stdout.decode('utf-8', errors='strict')

    def inside(label, command, required=True):
        return run(label, ['docker', 'exec', container, *command], required)

    try:
        if sys.platform != 'linux' or platform.machine() != 'x86_64':
            raise ValueError('Linux x86_64 inspection required')
        run('pull-image', ['docker', 'pull', '--platform', 'linux/amd64', IMAGE], timeout=900)
        inspection = json.loads(run('inspect-image', ['docker', 'image', 'inspect', IMAGE]))
        if len(inspection) != 1 or IMAGE not in inspection[0]['RepoDigests']:
            raise ValueError('Pinned image digest was not present')
        state['image_id'] = inspection[0]['Id']
        container_name = 'metaplex-tools-' + uuid.uuid4().hex[:12]
        state['container_name'] = container_name
        save()
        container = run('start-container', ['docker', 'run', '--rm', '--detach', '--name', container_name,
            '--platform', 'linux/amd64', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
            '--entrypoint', 'sleep', IMAGE, '600']).strip()
        if not re.fullmatch('[0-9a-f]{64}', container):
            raise ValueError('Unexpected Docker container ID')
        state['container_id'] = container
        resolved = inside('rustc-resolved', ['readlink', '-f', RUSTC]).strip()
        observed = inside('rustc-sha256', ['sha256sum', RUSTC]).split()[0]
        state['recorded_rustc_sha256'] = RUSTC_SHA
        state['observed_rustc_sha256'] = observed
        state['rustc_resolved'] = resolved
        if observed != RUSTC_SHA:
            raise ValueError('Compiler does not match candidate11; stop attribution')
        inside('rustc-version', [RUSTC, '--version', '--verbose'])
        inside('platform-version', ['cat', '/root/.cache/solana/v1.37/platform-tools/version.md'], False)
        inside('platform-version-paths', ['find', '/root/.cache/solana/v1.37/platform-tools', '-maxdepth', '3', '-name', 'version.md'], False)
        dependencies = inside('rustc-ldd', ['ldd', RUSTC], False)
        libraries = sorted(set(re.findall(r'=> (/[^\s]+)', dependencies)))
        state['resolved_dynamic_library_paths'] = libraries
        for index, library in enumerate(libraries):
            inside(f'library-{index:02d}-sha256', ['sha256sum', library])
        inside('rustc-codegen-help', [RUSTC, '-C', 'help'], False)
        inside('rustc-unstable-help', [RUSTC, '-Z', 'help'], False)
        targets = inside('rustc-targets', [RUSTC, '--print', 'target-list']).splitlines()
        selected = [target for target in targets if 'bpf' in target or 'sbf' in target]
        state['available_bpf_sbf_targets'] = selected
        for index, target in enumerate(selected):
            inside(f'target-{index:02d}-spec', [RUSTC, '-Z', 'unstable-options', '--print', 'target-spec-json', '--target', target], False)
            inside(f'target-{index:02d}-cpus', [RUSTC, '--print', 'target-cpus', '--target', target], False)
        inside('cargo-build-sbf-version', ['cargo-build-sbf', '--version'], False)
        inside('cargo-build-sbf-help', ['cargo-build-sbf', '--help'], False)
        state['status'] = 'observed'
        state['limits'] = 'Read-only image observation. Defaults and available target CPUs are not the actual prior compilation arguments. No historical compiler-source or loaded-library claim follows solely from this observation.'
    except Exception as error:
        state.update(status='failed', error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        primary_failure = sys.exc_info()[0] is not None
        cleanup_error = None
        cleanup_target = container if container and re.fullmatch('[0-9a-f]{64}', container) else container_name
        try:
            if cleanup_target:
                run('stop-container', ['docker', 'stop', '--time', '1', cleanup_target])
        except Exception as error:
            cleanup_error = str(error)
            state['cleanup_error'] = cleanup_error
            if not primary_failure:
                state['status'] = 'cleanup-failed'
        finally:
            save()
        if cleanup_error and not primary_failure:
            raise RuntimeError('Compiler observation retained; container cleanup failed: ' + cleanup_error)


if __name__ == '__main__':
    main()
