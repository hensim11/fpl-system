"""Execute M5D normal/optimized and prior acceptance checks; preserve evidence."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from fpl_ai.historical_io import atomic_write_json, sha256_file
from scripts.verify_joint_simulation import CALIBRATION, UNCERTAINTY, M4E, PLAN


def check(value, message):
    if not value: raise ValueError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('docs/M5D_REGRESSION.json'))
    args = parser.parse_args()
    env = {**os.environ, 'PYTHONPATH': '.', 'LOKY_MAX_CPU_COUNT': '1'}
    commands = []
    for mode, flags in (('normal', []), ('optimized', ['-O'])):
        for focused in (True, False):
            name = ('focused-' if focused else '')+mode
            command = [sys.executable, *flags, '-m', 'unittest', *(['tests.test_joint_simulation'] if focused else ['discover']), '-v']
            commands.append((name, command, None, None))
        jobs = [
            ('m5b', 'verify_multi_gameweek.py', ['--projections-dir', 'data/multi_projection/forecasts/03a9f348378b8ad61a8eea3c58424fdb7bf689f5c1da46707c03e54c35f1427b', '--plan-dir', str(PLAN)], 'docs/M5B_VERIFICATION.json'),
            ('oracle', 'verify_multi_oracle.py', [], 'docs/M5B_ORACLE.json'),
            ('m5c', 'verify_multi_uncertainty.py', ['--calibration-dir', str(CALIBRATION), '--uncertainty-dir', str(UNCERTAINTY)], 'docs/M5C_VERIFICATION.json'),
        ]
        for name, script, options, accepted in jobs:
            report = '/tmp/m5d-regression-'+name+'-'+mode+'.json'
            commands.append((name+'-'+mode, [sys.executable, *flags, 'scripts/'+script, *options, '--report', report], report, accepted))
    for name, script, options in (
        ('m2', 'verify_historical_seasons.py', []), ('m3', 'verify_modelling.py', []),
        ('m4e', 'verify_prospective_xpts.py', ['--model-dir', str(M4E), '--forecast-dir', 'data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527'])):
        report = '/tmp/m5d-regression-'+name+'.json'
        commands.append((name, [sys.executable, 'scripts/'+script, *options, '--report', report], report, None))
    results = []
    for name, command, report, accepted in commands:
        print('Running '+name, flush=True)
        started = perf_counter()
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        log = result.stdout+result.stderr
        path = Path('/tmp/m5d-regression-'+name+'.log'); path.write_text(log)
        check(result.returncode == 0, 'failed '+name+': '+str(path))
        count = re.search(r'Ran (\d+) tests', log)
        if report: check(Path(report).is_file(), 'missing report '+name)
        if accepted: check(Path(report).read_bytes() == Path(accepted).read_bytes(), 'accepted evidence changed '+name)
        results.append({'name': name, 'command': command, 'seconds': perf_counter()-started,
                        'test_count': int(count[1]) if count else None, 'log': log, 'log_sha256': sha256_file(path),
                        'report_sha256': sha256_file(Path(report)) if report else None,
                        'accepted_report': accepted, 'accepted_byte_identity': True if accepted else None, 'passed': True})
        print('Passed '+name, flush=True)
    checks = []
    for command in ([sys.executable, '-m', 'compileall', '-q', 'fpl_ai', 'scripts', 'tests'],
                    [sys.executable, '-m', 'pip', '--disable-pip-version-check', '--no-cache-dir', 'check'],
                    [sys.executable, '-S', '-m', 'fpl_ai', '--help'],
                    [sys.executable, '-m', 'fpl_ai', 'simulate', '--help'], ['git', 'diff', '--check'],
                    ['git', 'diff', '--exit-code', '--', 'pyproject.toml', 'fpl_ai/multi_projection.py', 'fpl_ai/multi_uncertainty.py',
                     'fpl_ai/multi_outcomes.py', 'fpl_ai/transfer_path.py', 'fpl_ai/transfer_optimiser.py', 'fpl_ai/fpl_rules.py']):
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        check(result.returncode == 0, 'check failed '+str(command)+result.stderr)
        checks.append({'command': command, 'passed': True, 'stdout': result.stdout})
    baseline = json.loads(args.before.read_text())
    changed = [name for name, prior in baseline.items() if not Path(name).is_file() or
               [sha256_file(Path(name)), Path(name).stat().st_mtime_ns] != prior]
    check(not changed, 'pre-batch artifacts changed '+str(changed))
    sources = ['fpl_ai/joint_simulation.py', 'fpl_ai/simulation_plans.py', 'fpl_ai/cli.py', 'fpl_ai/experiment_io.py',
               'tests/test_joint_simulation.py', 'scripts/verify_joint_simulation.py', 'scripts/profile_joint_simulation.py', 'scripts/verify_simulation_regression.py']
    atomic_write_json(args.report, {'executed': results, 'checks': checks, 'prior_artifacts': {
        'count': len(baseline), 'data_count': sum(n.startswith('data/') for n in baseline),
        'bytes_and_nanosecond_mtimes_unchanged': True, 'inventory': baseline},
        'source_sha256': {n: sha256_file(Path(n)) for n in sources}, 'no_commit_merge_or_push': True})
    print(args.report, flush=True)


if __name__ == '__main__': main()
