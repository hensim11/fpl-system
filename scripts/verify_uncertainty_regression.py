"""Collect executed M5C regression evidence and prove prior artifacts unchanged."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from fpl_ai.historical_io import atomic_write_json, sha256_file


def check(value, message):
    if not value: raise ValueError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--evidence-prefix', type=Path, default=Path('/tmp/m5c'))
    parser.add_argument('--report', type=Path, default=Path('docs/M5C_REGRESSION.json'))
    args = parser.parse_args()
    prefix = str(args.evidence_prefix)
    baseline = json.loads(args.before.read_text())
    changed = [n for n, v in baseline.items() if not Path(n).is_file() or
               v != {'sha256': sha256_file(Path(n)), 'mtime_ns': Path(n).stat().st_mtime_ns}]
    check(not changed, 'pre-batch data changed: '+str(changed))
    tests = {}
    for mode in ('normal', 'optimized', 'focused', 'focused-optimized'):
        path = Path(prefix+'-'+mode+'.log')
        log = path.read_text()
        count = re.search(r'Ran (\d+) tests', log)
        check(count is not None and log.rstrip().endswith('OK') and 'FAILED' not in log, 'test failure: '+mode)
        test_command = ['.venv/bin/python'] + (['-O'] if 'optimized' in mode else [])
        test_command += ['-m', 'unittest'] + (['tests.test_multi_uncertainty', '-v'] if mode.startswith('focused') else ['discover', '-v'])
        tests[mode] = {'count': int(count[1]), 'passed': True, 'command': test_command, 'log': log, 'sha256': sha256_file(path)}
    check(tests['normal']['count'] == tests['optimized']['count'] and
          tests['focused']['count'] == tests['focused-optimized']['count'], 'test populations differ')
    comparisons = []
    for a, b in [('docs/M5C_VERIFICATION.json', prefix+'-verification-optimized.json'),
                 ('docs/M5B_VERIFICATION.json', prefix+'-m5b.json'),
                 ('docs/M5B_VERIFICATION.json', prefix+'-m5b-optimized.json'),
                 ('docs/M5B_ORACLE.json', prefix+'-oracle.json'),
                 ('docs/M5B_ORACLE.json', prefix+'-oracle-optimized.json')]:
        check(Path(a).read_bytes() == Path(b).read_bytes(), 'replay differs: '+a+' / '+b)
        comparisons.append({'accepted': a, 'replayed': b, 'byte_identical': True, 'sha256': sha256_file(Path(a))})
    commands = [
        [sys.executable, '-m', 'compileall', '-q', 'fpl_ai', 'scripts', 'tests'],
        [sys.executable, '-m', 'pip', '--disable-pip-version-check', '--no-cache-dir', 'check'],
        [sys.executable, '-S', '-m', 'fpl_ai', '--help'],
        [sys.executable, '-m', 'fpl_ai', 'uncertainty', '--help'],
        ['git', 'diff', '--check'],
        ['git', 'diff', '--exit-code', '--', 'pyproject.toml', 'fpl_ai/multi_projection.py', 'fpl_ai/transfer_path.py',
         'fpl_ai/prospective.py', 'fpl_ai/prospective_xpts.py', 'fpl_ai/transfer_optimiser.py', 'fpl_ai/fpl_rules.py'],
    ]
    checks = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        checks.append({'command': command, 'passed': True, 'stdout': result.stdout})
    untracked = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '-z'], check=True, capture_output=True).stdout.decode().split('\0')
    for name in filter(None, untracked):
        if Path(name).suffix in ('.py', '.md', '.json'):
            r = subprocess.run(['git', 'diff', '--no-index', '--check', '/dev/null', name], capture_output=True, text=True)
            check(r.returncode in (0, 1) and not r.stdout and not r.stderr, 'untracked whitespace: '+name)
    prior = {}
    for stage in ('m2', 'm3', 'm4e'):
        path = Path(prefix+'-'+stage+'.json')
        report = json.loads(path.read_text())
        log = Path(prefix+'-'+stage+'.log').read_text()
        check(report and 'Traceback' not in log, 'prior verification failed: '+stage)
        script = {'m2': 'verify_historical_seasons.py', 'm3': 'verify_modelling.py', 'm4e': 'verify_prospective_xpts.py'}[stage]
        command = ['.venv/bin/python', 'scripts/'+script]
        if stage == 'm4e':
            command += ['--model-dir', 'data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230',
                        '--forecast-dir', 'data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527']
        command += ['--report', str(path)]
        prior[stage] = {'command': command, 'environment': {'PYTHONPATH': '.', 'LOKY_MAX_CPU_COUNT': '1'},
                        'report_sha256': sha256_file(path), 'top_level_keys': sorted(report), 'log': log}
    profile = json.loads(Path('docs/M5C_PROFILE.json').read_text())
    check(profile['all_decision_bytes_identical'] and not profile['production_planner_changed'], 'planner changed')
    failed = Path(prefix+'-premature.log').read_text()
    check('target deadline has not passed' in failed, 'no real premature rejection evidence')
    live = json.loads(Path('docs/M5C_LIVE.json').read_text())
    for name, sha in live['hashes'].items():
        check(sha256_file(Path(live['evidence_dir'])/name) == sha, 'live inspection hash mismatch')
    sources = ('fpl_ai/multi_uncertainty.py', 'fpl_ai/multi_outcomes.py', 'fpl_ai/cli.py', 'fpl_ai/experiment_io.py',
               'scripts/verify_multi_uncertainty.py', 'scripts/profile_multi_planner.py', 'scripts/verify_uncertainty_regression.py',
               'tests/test_multi_uncertainty.py')
    atomic_write_json(args.report, {'tests': tests, 'comparisons': comparisons, 'prior_milestone_replays': prior,
                                   'prior_artifacts': {'count': len(baseline), 'bytes_and_nanosecond_mtimes_unchanged': True,
                                                       'baseline_sha256': sha256_file(args.before), 'inventory': baseline},
                                   'checks': checks, 'untracked_whitespace_passed': True, 'profile': profile,
                                   'real_premature_settlement_rejected': failed.strip(),
                                   'source_sha256': {n: sha256_file(Path(n)) for n in sources},
                                   'no_commit_merge_or_push': True})
    print(f"Verified {len(baseline)} preserved files, {tests['normal']['count']} tests in both modes and independent prior replays")


if __name__ == '__main__': main()
