"""Record M5A hardening regression/preservation evidence from executed test logs.

Before work: --capture /tmp/m5a-before.json
After tests/verifiers: --before ... --normal-log ... --optimized-log ...
                      --focused-log ... --optimized-report ...
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from fpl_ai.historical_io import atomic_write_json, sha256_file


def inventory():
    return {str(p): {'sha256': sha256_file(p), 'mtime_ns': p.stat().st_mtime_ns}
            for p in sorted(Path('data').rglob('*')) if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--before', type=Path)
    parser.add_argument('--normal-log', type=Path)
    parser.add_argument('--optimized-log', type=Path)
    parser.add_argument('--focused-log', type=Path)
    parser.add_argument('--focused-optimized-log', type=Path)
    parser.add_argument('--prior-report', type=Path)
    parser.add_argument('--optimized-report', type=Path)
    parser.add_argument('--optimized-sweep-report', type=Path)
    parser.add_argument('--report', type=Path, default=Path('docs/M5A_REGRESSION.json'))
    args = parser.parse_args()
    if args.capture:
        if args.capture.exists(): raise ValueError('do not overwrite a pre-batch inventory')
        atomic_write_json(args.capture, inventory())
        return
    if any(getattr(args, k) is None for k in ('before','normal_log','optimized_log','focused_log','focused_optimized_log','prior_report','optimized_report','optimized_sweep_report')):
        parser.error('before inventory, four test logs, prior report and optimized report required')
    before = json.loads(args.before.read_text())
    changed = [n for n, expected in before.items() if not Path(n).is_file() or
               {'sha256':sha256_file(Path(n)), 'mtime_ns':Path(n).stat().st_mtime_ns} != expected]
    if changed: raise ValueError(f'pre-existing artifacts changed: {changed}')
    tests = {}
    for mode, path in (('normal',args.normal_log),('optimized',args.optimized_log),('focused',args.focused_log),
                       ('focused_optimized',args.focused_optimized_log)):
        content = path.read_text()
        count = re.search(r'Ran (\d+) tests', content)
        if count is None or not content.rstrip().endswith('OK') or 'FAILED' in content:
            raise ValueError(f'unsuccessful test log: {path}')
        tests[mode] = {'test_count':int(count[1]), 'passed':True, 'log':content, 'sha256':sha256_file(path)}
    if tests['normal']['test_count'] != tests['optimized']['test_count']:
        raise ValueError('test populations differ')
    if tests['focused']['test_count'] != tests['focused_optimized']['test_count']:
        raise ValueError('focused test populations differ')
    normal_report = Path('docs/M5A_VERIFICATION.json')
    if normal_report.read_bytes() != args.optimized_report.read_bytes():
        raise ValueError('normal/optimized verification differs')
    sweep = Path('docs/M5A_EXHAUSTIVE_VERIFICATION.json')
    if sweep.read_bytes() != args.optimized_sweep_report.read_bytes():
        raise ValueError('normal/optimized exhaustive sweep differs')
    prior = json.loads(args.prior_report.read_text())
    current = json.loads(normal_report.read_text())
    for model in ('control', 'v2'):
        for key in ('baseline', 'plans', 'population_counts', 'original_winners_selectable'):
            if current['models'][model][key] != prior['models'][model][key]:
                raise ValueError(f'GW6 evidence changed: {model} {key}')
    checks = {}
    for name, command in (
        ('compileall', [sys.executable,'-m','compileall','-q','fpl_ai','scripts','tests']),
        ('cli_help', [sys.executable,'-m','fpl_ai','optimise','--help']),
        ('git_diff_check', ['git','diff','--check'])):
        subprocess.run(command, check=True, capture_output=True)
        checks[name] = True
    # git diff alone omits new untracked files. Check every nonignored
    # untracked text artifact too, so new M5A modules/evidence are covered.
    untracked = subprocess.run(['git','ls-files','--others','--exclude-standard','-z'],
                               check=True,capture_output=True).stdout.decode().split('\0')
    checked = []
    for name in filter(None,untracked):
        if Path(name).suffix in ('.py','.md','.json','.toml','.txt'):
            whitespace = subprocess.run(['git','diff','--no-index','--check','/dev/null',name],
                                        capture_output=True, text=True)
            # --no-index may return 1 for a clean new-file diff; diagnostics
            # (or an error status) are what indicate a whitespace/check failure.
            if whitespace.returncode not in (0, 1) or whitespace.stdout or whitespace.stderr:
                raise ValueError(f'untracked whitespace check: {name}: {whitespace.stdout}{whitespace.stderr}')
            checked.append(name)
    checks['untracked_whitespace_files'] = checked
    atomic_write_json(args.report, {
        'batch':'M5A semantic tie admission separated from structural feasibility',
        'tests':tests, 'pre_hardening_test_count':236,
        'new_hardening_test_count':tests['normal']['test_count']-236,
        'preservation':{'file_count':len(before),'bytes_and_nanosecond_mtimes_unchanged':True,
                        'changed_files':changed,'before_inventory':before},
        'verification':{'normal_report':str(normal_report),'sha256':sha256_file(normal_report),
                        'normal_optimized_byte_identical':True,
                        'exhaustive_sweep_report':str(sweep),
                        'exhaustive_sweep_sha256':sha256_file(sweep),
                        'exhaustive_sweep_normal_optimized_byte_identical':True,
                        'prior_report_sha256':sha256_file(args.prior_report),
                        'GW6_plans_counts_objectives_selectability_unchanged':True}, 'checks':checks})
    print(f"Verified {len(before)} unchanged files; {tests['normal']['test_count']} tests in both modes")


if __name__ == '__main__': main()
