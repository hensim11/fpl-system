"""Exercise the real personal decision CLI with sockets explicitly forbidden."""
import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter

from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json
from tests.test_prospective import fingerprint


def check(value,message):
    if not value: raise ValueError(message)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--report',type=Path,default=Path('docs/M5E_LIFECYCLE.json'))
    parser.add_argument('--work-dir',type=Path,default=Path('local/m5e-checks'))
    args=parser.parse_args()
    args.work_dir.mkdir(parents=True,exist_ok=True)
    check(load_json(args.bundle/'personal.json')['provenance']['kind']=='synthetic','lifecycle evidence must be explicitly synthetic')
    before=fingerprint(args.bundle)
    actions=[]
    runner="""import sys,runpy
def offline(event,args):
    if event in ('socket.connect','socket.getaddrinfo'): raise RuntimeError('network forbidden in decision workflow')
sys.addaudithook(offline)
sys.argv=['fpl_ai',*sys.argv[1:]]
runpy.run_module('fpl_ai',run_name='__main__')
"""
    def cli(name,options,expected=0):
        print('Running '+name,flush=True)
        start=perf_counter()
        command=[sys.executable,'-c',runner,'decision',*options]
        r=subprocess.run(command,env={**os.environ,'LOKY_MAX_CPU_COUNT':'4'},capture_output=True,text=True)
        log=args.work_dir/(name+'.log'); log.write_text(r.stdout+r.stderr)
        check(r.returncode==expected,'CLI failure '+name+': '+str(log))
        actions.append({'action':name,'cli_arguments':['decision',*map(str,options)],'seconds':perf_counter()-start,
                        'exit_code':r.returncode,'log_sha256':sha256_file(log),'network_audit_hook_enabled':True})
        print('Passed '+name,flush=True)
        return r.stdout+r.stderr
    cli('decision-validate',['validate','--config',str(args.config)])
    cli('decision-verify',['verify','--bundle',str(args.bundle)])
    result=cli('decision-reuse',['run','--config',str(args.config)])
    check('Verified reuse' in result and args.bundle.name in result,'same config did not reuse exact bundle')
    replay_root=args.work_dir/'replay'
    cli('decision-replay',['replay','--bundle',str(args.bundle),'--artifact-dir',str(replay_root)])
    replayed=replay_root/args.bundle.name
    original=verify_bundle(args.bundle)
    check(verify_bundle(replayed)==original,'replay changed identity/attestation')
    check(all((replayed/n).read_bytes()==(args.bundle/n).read_bytes() for n in (*original['artifacts'],'manifest.json')),'replay bytes changed')
    with tempfile.TemporaryDirectory() as tmp:
        def writer(target):
            for n in original['artifacts']: shutil.copyfile(args.bundle/n,target/n)
            summary=load_json(target/'summary.json')
            summary['decomposition']['exact_1']['no_transfer']['horizon']['net_change']+=10
            atomic_write_json(target/'summary.json',summary)
        bad,_=publish(Path(tmp)/'rehashed',original['metadata'],writer)
        result=cli('decision-real-rehashed-summary-rejected',['verify','--bundle',str(bad)],expected=1)
        check('summary semantic reconstruction mismatch' in result,'unexpected corruption rejection')
    with tempfile.TemporaryDirectory() as tmp:
        metadata=copy.deepcopy(original['metadata'])
        metadata['attestation']['publication_checked_at']='2000-01-01T00:00:00Z'
        def writer(target):
            for n in original['artifacts']: shutil.copyfile(args.bundle/n,target/n)
        bad,_=publish(Path(tmp)/'rehashed',metadata,writer)
        result=cli('decision-real-rehashed-attestation-rejected',['verify','--bundle',str(bad)],expected=1)
        check('chronology' in result,'unexpected attestation rejection')
    check(fingerprint(args.bundle)==before,'reuse/verify changed original bytes or nanosecond mtimes')
    atomic_write_json(args.report,{'bundle_identity':args.bundle.name,'synthetic_not_user_advice':True,
        'original_bytes_and_nanosecond_mtimes_unchanged':True,'replay_bytes_identity_and_attestation_preserved':True,
        'real_rehashed_false_summary_rejected':True,'real_rehashed_false_attestation_rejected':True,'all_cli_operations_network_forbidden':True,'actions':actions})
    print(args.report,flush=True)


if __name__=='__main__': main()
