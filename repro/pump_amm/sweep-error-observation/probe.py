#!/usr/bin/env python3
"""Observe nine signed offline sweep cases without assuming their outcomes."""
import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--built', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, built, output = args.repo.resolve(), args.built.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError('output already exists')
    binaries = {
        'original': root / 'evidence/original/pump_amm/deployed.so',
        'baseline': built / 'baseline/candidate.so',
        'liquidity_corrected': built / 'corrected/candidate.so',
    }
    expected = {
        'original': '6a7ad34596d83b4c435b32f458a56e718e9f82eb4ad38e4316616d15d24d8ff7',
        'baseline': 'cc2326ba730ccbbe85af8e9860833382e8d3e33b7e065c6ae80cfc838f80f4aa',
        'liquidity_corrected': 'ec8aa1dfe54221eb19f332cac459d16a65cab0aa3064bcabf7c452211702e149',
    }
    if {kind: sha(path) for kind, path in binaries.items()} != expected:
        raise ValueError('unexpected binary input')
    inputs = [
        'scripts/pump_amm_sweep_differential.py',
        'scripts/pump_amm_liquidity_differential.py',
        'scripts/pump_amm_admin_differential.py',
        'scripts/pump_amm_reusable_harness.py',
        'research/imported-lab/analysis/pump_fun/config-snapshot.json',
        'research/imported-lab/analysis/pump_fun/amm-v2-trade-fixture.json',
        'evidence/upstream/pump_amm.json',
        'evidence/dependencies/spl_token/deployed.so',
        'evidence/dependencies/spl_token_2022/deployed.so',
        'evidence/dependencies/associated_token/deployed.so',
    ]
    bindings = {path: sha(root / path) for path in inputs}
    os.chdir(root)
    sys.path.insert(0, str(root / 'scripts'))
    import pump_amm_sweep_differential as harness
    import pump_amm_reusable_harness as reusable
    import solders.solders as native
    transactions = []
    send = reusable._ResettableVM.send_transaction

    def observe(self, transaction):
        transaction.verify()
        transactions.append({'raw_base64': base64.b64encode(bytes(transaction)).decode(),
                             'verified_signature_count': len(transaction.signatures)})
        return send(self, transaction)

    rows = []
    report = {
        'scope': 'Nine synthetic signed local protocol sweep cases against three binary inputs. History-disabled LiteSVM fixture; no RPC, deployment, historical replay or full equivalence claim. Observations only, without a predicted outcome.',
        'binary_sha256': expected, 'input_sha256': bindings,
        'probe_sha256': sha(Path(__file__)),
        'build_record_sha256': {kind: sha(built / kind / 'build-record.json') for kind in ('baseline', 'corrected')},
        'runtime': {'python': sys.version, 'platform': platform.platform(),
                    'solders': importlib.metadata.version('solders'), 'native_sha256': sha(Path(native.__file__))},
        'planned_case_count': 9, 'planned_transaction_count': 27, 'cases': rows,
    }

    def retain(status, failure=None):
        report.update(status=status, failure=failure,
                      completed_case_count=sum(all(side in row and 'error' in row[side] for side in binaries) for row in rows),
                      transaction_count=sum(len(row.get(side, {}).get('transactions', [])) for row in rows for side in binaries))
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output)

    reusable._ResettableVM.send_transaction = observe
    retain('incomplete')
    try:
        for mode in ('ordinary', 'alias_pool_owner', 'alias_wrong_owner'):
            for amount in (0, 1, 1000):
                row = {'instruction': 'sweep_protocol_fee', 'mode': mode, 'amount': amount}
                rows.append(row)
                kw = {}
                if mode != 'ordinary':
                    owner = harness.pool if mode == 'alias_pool_owner' else harness.OUTSIDER.pubkey()
                    kw = {'recipient': harness.pool,
                          'overrides': harness.combine(
                              harness.mutate(harness.CONFIG_KEY, 57, bytes(harness.pool) * 8),
                              harness.mutate(harness.vaultquote, 32, bytes(owner)))}
                for side, binary in binaries.items():
                    transactions.clear()
                    try:
                        result = harness.sweep('sweep_protocol_fee', amount, candidate=binary, **kw)
                    except Exception as exc:
                        row[side] = {'transactions': list(transactions), 'execution_exception': type(exc).__name__ + ': ' + str(exc)}
                        raise
                    result['transactions'] = list(transactions)
                    row[side] = result
                    retain('incomplete')
                    if len(transactions) != 1:
                        raise ValueError('expected one local signed transaction per case and binary')
        if bindings != {path: sha(root / path) for path in inputs} or expected != {kind: sha(path) for kind, path in binaries.items()}:
            raise ValueError('inputs changed during observation')
        retain('completed')
    except Exception as exc:
        retain('failed', type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        reusable._ResettableVM.send_transaction = send
    print(json.dumps({'case_count': report['completed_case_count'], 'transaction_count': report['transaction_count'],
                      'errors': [{k: row[k]['error'] for k in binaries} for row in rows]}))


if __name__ == '__main__':
    main()
