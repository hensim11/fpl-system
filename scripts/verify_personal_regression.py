"""Run M5E acceptance checks without overwriting pre-existing evidence."""
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
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--report',type=Path,default=Path('docs/M5E_REGRESSION.json'))
    args=parser.parse_args()
    logs=Path('local/m5e-checks'); logs.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONPATH':'.','LOKY_MAX_CPU_COUNT':'4'}
    commands=[]
    for mode, flags in (('normal',[]),('optimized',['-O'])):
        for focused in (True,False):
            commands.append((('focused-' if focused else 'full-')+mode,
                [sys.executable,*flags,'-m','unittest',*(['tests.test_personal_decision'] if focused else ['discover'])],None,None))
        for name,script,options,accepted in (
            ('m5b','verify_multi_gameweek.py',['--projections-dir','data/multi_projection/forecasts/03a9f348378b8ad61a8eea3c58424fdb7bf689f5c1da46707c03e54c35f1427b','--plan-dir',str(PLAN)],'docs/M5B_VERIFICATION.json'),
            ('m5b-oracle','verify_multi_oracle.py',[],'docs/M5B_ORACLE.json'),
            ('m5c','verify_multi_uncertainty.py',['--calibration-dir',str(CALIBRATION),'--uncertainty-dir',str(UNCERTAINTY)],'docs/M5C_VERIFICATION.json'),
            ('m5d','verify_joint_simulation.py',['--simulation-dir','data/simulations/0a4dceb30cd0fba3c4ef50c8f09b4c89e74eeb3a4b3704dc70baa69ac5029a62',
              '--evaluation-dir','data/simulation_evaluations/36a266e775e124a6d36bfb813e0aedf364c200a394a82d9b25e0b48a75902c3f'],'docs/M5D_VERIFICATION.json')):
            output=logs/(name+'-'+mode+'.json')
            commands.append((name+'-'+mode,[sys.executable,*flags,'scripts/'+script,*options,'--report',str(output)],output,Path(accepted)))
    for name,script,options in (
        ('m2','verify_historical_seasons.py',[]),('m3','verify_modelling.py',[]),
        ('m4e','verify_prospective_xpts.py',['--model-dir',str(M4E),'--forecast-dir','data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527'])):
        output=logs/(name+'.json')
        commands.append((name,[sys.executable,'scripts/'+script,*options,'--report',str(output)],output,None))
    results=[]
    for name,command,output,accepted in commands:
        print('Running '+name,flush=True); started=perf_counter()
        r=subprocess.run(command,env=env,capture_output=True,text=True)
        log=logs/(name+'.log'); log.write_text(r.stdout+r.stderr)
        check(r.returncode==0,'failed '+name+'; see '+str(log))
        if accepted: check(output.read_bytes()==accepted.read_bytes(),'prior accepted report differs: '+name)
        match=re.search(r'Ran (\d+) tests',log.read_text())
        results.append({'name':name,'command':command,'seconds':perf_counter()-started,'tests':int(match[1]) if match else None,
                        'log_sha256':sha256_file(log),'report_sha256':sha256_file(output) if output else None,
                        'accepted_bytes_identical':True if accepted else None,'passed':True})
        print('Passed '+name,flush=True)
    checks=[]
    for command in ([sys.executable,'-m','compileall','-q','fpl_ai','scripts','tests'],
        [sys.executable,'-m','pip','--disable-pip-version-check','--no-cache-dir','check'],
        [sys.executable,'-S','-m','fpl_ai','--help'],[sys.executable,'-m','fpl_ai','decision','--help'],
        ['git','diff','--check'],['git','diff','--exit-code','--','pyproject.toml','fpl_ai/multi_projection.py',
        'fpl_ai/multi_uncertainty.py','fpl_ai/multi_outcomes.py','fpl_ai/transfer_path.py','fpl_ai/transfer_optimiser.py',
        'fpl_ai/fpl_rules.py','fpl_ai/joint_simulation.py','fpl_ai/simulation_plans.py']):
        r=subprocess.run(command,env=env,capture_output=True,text=True)
        check(r.returncode==0,'check failed '+str(command)+r.stdout+r.stderr)
        checks.append({'command':command,'passed':True})
    before=json.loads(args.before.read_text())
    changed=[n for n,v in before.items() if not Path(n).is_file() or sha256_file(Path(n))!=v['sha256'] or Path(n).stat().st_mtime_ns!=v['mtime_ns']]
    check(not changed,'prior evidence changed: '+str(changed))
    whitespace=[]
    for p in [*Path('fpl_ai').glob('*.py'),*Path('scripts').glob('*personal*.py'),Path('tests/test_personal_decision.py'),*Path('docs').glob('M5E*')]:
        whitespace += [f'{p}:{i}' for i,line in enumerate(p.read_text().splitlines(),1) if line.rstrip()!=line]
    check(not whitespace,'trailing whitespace '+str(whitespace))
    baseline_counts={}
    for mode,log in [('normal',Path('/tmp/m5e-baseline.log')),('optimized',Path('/tmp/m5e-baseline-optimized.log'))]:
        text=log.read_text(); match=re.search(r'Ran (\d+) tests',text)
        check(match is not None and text.rstrip().endswith('OK'),'baseline run not successful')
        baseline_counts[mode]={'tests':int(match[1]),'log_sha256':sha256_file(log)}
    atomic_write_json(args.report,{'baseline':baseline_counts,
        'executed':results,'checks':checks,'new_text_whitespace_passed':True,
        'preservation':{'files':len(before),'data_files':sum(n.startswith('data/') for n in before),
        'inventory_sha256':sha256_file(args.before),'all_bytes_and_nanosecond_mtimes_unchanged':True},'no_commit_merge_or_push':True})
    print(args.report,flush=True)


if __name__=='__main__': main()
