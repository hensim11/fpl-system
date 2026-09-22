"""M5B full-suite, deterministic evidence and prior-artifact preservation record."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from fpl_ai.historical_io import atomic_write_json, sha256_file


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--normal-log',type=Path,required=True)
    parser.add_argument('--optimized-log',type=Path,required=True)
    parser.add_argument('--optimized-report',type=Path,required=True)
    parser.add_argument('--optimized-oracle',type=Path,required=True)
    parser.add_argument('--rebuild-evidence',type=Path,required=True)
    parser.add_argument('--report',type=Path,default=Path('docs/M5B_REGRESSION.json'))
    args=parser.parse_args()
    before=json.loads(args.before.read_text())
    changed=[n for n,v in before.items() if not Path(n).is_file() or v!={'sha256':sha256_file(Path(n)),'mtime_ns':Path(n).stat().st_mtime_ns}]
    if changed: raise ValueError('prior artifacts changed: '+str(changed))
    tests={}
    for name,p in [('normal',args.normal_log),('optimized',args.optimized_log)]:
        log=p.read_text(); match=re.search(r'Ran (\d+) tests',log)
        if not match or not log.rstrip().endswith('OK') or 'FAILED' in log: raise ValueError('test suite failed: '+name)
        tests[name]={'count':int(match[1]),'passed':True,'log':log,'sha256':sha256_file(p)}
    if tests['normal']['count']!=tests['optimized']['count']: raise ValueError('test population differs')
    for normal,optimized in [(Path('docs/M5B_VERIFICATION.json'),args.optimized_report),(Path('docs/M5B_ORACLE.json'),args.optimized_oracle)]:
        if normal.read_bytes()!=optimized.read_bytes(): raise ValueError('normal/optimized evidence differs: '+str(normal))
    for command in ([sys.executable,'-m','compileall','-q','fpl_ai','scripts','tests'],
                    [sys.executable,'-m','fpl_ai','project','--help'],[sys.executable,'-m','fpl_ai','plan','--help'],
                    ['git','diff','--check']):
        subprocess.run(command,check=True,capture_output=True)
    paths=subprocess.run(['git','ls-files','--others','--exclude-standard','-z'],check=True,capture_output=True).stdout.decode().split('\0')
    for p in filter(None,paths):
        if Path(p).suffix in ('.py','.md','.json'):
            r=subprocess.run(['git','diff','--no-index','--check','/dev/null',p],capture_output=True,text=True)
            if r.returncode not in (0,1) or r.stdout or r.stderr: raise ValueError('untracked whitespace error: '+p)
    atomic_write_json(args.report,{'tests':tests,'prior_artifacts':{'count':len(before),'bytes_and_nanosecond_mtimes_unchanged':True,'inventory':before},
                                  'normal_optimized_verifier_byte_identical':True,'normal_optimized_oracle_byte_identical':True,
                                  'rebuild':json.loads(args.rebuild_evidence.read_text()),
                                  'compile_help_whitespace_checks_passed':True,
                                  'source_sha256':{n:sha256_file(Path(n)) for n in ('fpl_ai/multi_projection.py','fpl_ai/transfer_path.py','fpl_ai/cli.py','fpl_ai/experiment_io.py')}})
    print(f"Verified {len(before)} preserved files and {tests['normal']['count']} tests in both modes")


if __name__=='__main__': main()
