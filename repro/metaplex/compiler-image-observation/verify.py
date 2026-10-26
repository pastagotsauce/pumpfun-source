"""Recheck retained compiler observations; optionally read the pinned archive. No execution."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

HERE = Path(__file__).resolve().parent
MANIFEST_SHA = 'e9f249d5139177d4fd391a3fbf9eb23c5d615347dab45d0f57b3eae0c6e7b784'
ARCHIVE_SHA = '8d5153589dbe19635affe937663cf4555a7e69a62d91ab4a1df064aaa8d5f066'
RUSTC_SHA = '7194df9c12e893cfa88fff5dd821d02d45910b4d375e13677b4723f45769a384'
RUST_REVISION = '764ce69bd00903f5c59f44b6aa72649b173f568c'
HEAD = '4678ffb0fe56c63d46d1851e6fc648fc77695b30'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def verify(archive=None):
    manifest = (HERE/'results-manifest.json').read_bytes()
    require(sha(manifest) == MANIFEST_SHA, 'Result manifest seal differs')
    folder = HERE/'results'
    actual = [{'path':p.relative_to(folder).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
              for p in sorted(folder.rglob('*')) if p.is_file()]
    require(actual == json.loads(manifest), 'Retained result member differs')
    get = lambda name: json.loads((folder/name).read_bytes())
    run, artifact = get('image-attempt/run.json'), get('image-attempt/artifact.json')
    require(run['id'] == 40304340175 and run['head_sha'] == HEAD and run['conclusion'] == 'failure'
            and run['repository']['full_name'] == 'pastagotsauce/pumpfun-source', 'Wrong observed run')
    raw_zip = (folder/'image-attempt/artifact.zip').read_bytes()
    require(artifact['id'] == 12640704841 and artifact['workflow_run']['head_sha'] == HEAD
            and artifact['workflow_run']['id'] == run['id'] and len(raw_zip) == artifact['size_in_bytes'] == 6891
            and artifact['digest'] == 'sha256:' + sha(raw_zip), 'Wrong provider artifact')
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) == 7, 'Unexpected ZIP member count')
        raw = {name:z.read(name) for name in names}
    rows = [{'name':name,'bytes':len(value),'sha256':sha(value)} for name,value in sorted(raw.items())]
    require(rows == get('image-attempt/artifact-members.json'), 'ZIP member receipt differs')
    state = json.loads(raw['observation.json'])
    require(state['status'] == 'failed' and state['build_attempts'] == state['runtime_executions'] == 0
            and state['source_mounted'] is False and 'cleanup_error' not in state, 'Observation scope changed')
    require([(x['label'],x['returncode']) for x in state['commands']] ==
            [('pull-image',0),('inspect-image',0),('start-container',0),('rustc-resolved',1),('stop-container',0)],
            'Observed command sequence differs')
    for command in state['commands']:
        require(len(raw[command['log']]) == command['bytes'] and sha(raw[command['log']]) == command['sha256'],
                'Raw command output differs')
    require(raw['observe.py'] == (HERE/'observe.py').read_bytes(), 'Observed driver changed')
    report, release = get('archive.json'), get('release.json')
    asset = next(x for x in release['assets'] if x['id'] == 101838771)
    require(report['archive_sha256'] == ARCHIVE_SHA and report['bytes'] == asset['size'] == 362756282
            and report['asset_id'] == asset['id'] and report['publisher_digest'] is None
            and asset['digest'] is None and report['executed_files'] == 0, 'Archive observation differs')
    version = (folder/'version.md').read_bytes()
    require(version.splitlines()[0] == (RUST_REVISION+'  https://github.com/solana-labs/rust.git').encode(),
            'Archive Rust revision differs')
    selected = {x['name']:x for x in report['selected_members']}
    require(selected['./rust/bin/rustc']['sha256'] == RUSTC_SHA
            and get('historical-tool-versions.json')['selected_rustc_sha256'] == RUSTC_SHA
            and selected['./version.md']['sha256'] == sha(version), 'Known entrypoint/version binding differs')
    verified_archive = False
    if archive is not None:
        with archive.open('rb') as stream:
            require(archive.stat().st_size == 362756282 and hashlib.file_digest(stream,'sha256').hexdigest() == ARCHIVE_SHA,
                    'Official archive bytes differ')
        found = {}
        count = 0
        with tarfile.open(archive,'r|bz2') as tar:
            for member in tar:
                count += 1
                if member.name in selected:
                    expected = selected[member.name]
                    require(member.isfile() and member.size == expected['bytes'] and member.mode == expected['mode'],
                            'Selected archive member metadata differs')
                    stream = tar.extractfile(member)
                    found[member.name] = hashlib.file_digest(stream,'sha256').hexdigest()
        require(count == report['member_count'] == 2426 and
                found == {name:x['sha256'] for name,x in selected.items()}, 'Archive member bytes differ')
        verified_archive = True
    return {'failed_image_observation_verified':True,'archive_rust_revision':RUST_REVISION,
            'historical_rustc_entrypoint_matches':True,'full_archive_rechecked':verified_archive,
            'historical_loaded_driver_hash_available':False,'actual_prior_cpu_known':False,
            'new_builds':0,'new_program_replays':0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive),indent=2))
