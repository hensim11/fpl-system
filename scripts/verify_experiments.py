"""Offline M4 replay and preservation evidence. Replay is not model selection/tuning."""
import argparse
import json
import tempfile
from pathlib import Path

from fpl_ai.experiment_io import verify_bundle, verify_m3
from fpl_ai.experiments import run_holdout, run_validation
from fpl_ai.historical_io import atomic_write_json, sha256_file


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(root):
    return {str(p.relative_to(root)):[sha256_file(p),p.stat().st_mtime_ns]
            for p in sorted(Path(root).rglob('*')) if p.is_file()}


def verify(m3, frozen, holdout, data_dir):
    m3, frozen, holdout, data_dir = map(Path,(m3,frozen,holdout,data_dir))
    before = {str(p):fingerprint(p) for p in (data_dir/'historical/processed',data_dir/'modelling',frozen,holdout)}
    catalogue = (data_dir/'historical/catalogue.json').read_bytes()
    upstream = verify_m3(m3)
    fm, hm = verify_bundle(frozen,'validation-freeze'),verify_bundle(holdout,'frozen-holdout')
    require(hm['metadata']['frozen_identity']==fm['identity_sha256'],'holdout not linked to freeze')
    with tempfile.TemporaryDirectory() as tmp:
        new_freeze,reused = run_validation(m3,Path(tmp)/'validation')
        require(not reused,'fresh validation unexpectedly reused')
        require(verify_bundle(new_freeze)==fm,'fresh fit/prediction/diagnostic hashes differ')
        new_holdout,reused = run_holdout(m3,new_freeze,Path(tmp)/'holdout')
        require(not reused,'fresh holdout unexpectedly reused')
        require(verify_bundle(new_holdout)==hm,'frozen holdout replay differs')
    require(run_validation(m3,frozen.parent)[1],'validation reuse failed')
    require(run_holdout(m3,frozen,holdout.parent)[1],'holdout reuse failed')
    for path,initial in before.items():
        require(fingerprint(path)==initial,f'bytes or modification times changed: {path}')
    require((data_dir/'historical/catalogue.json').read_bytes()==catalogue,'historical catalogue changed')
    frozen_metadata = json.loads((frozen/'frozen.json').read_text())
    return {
        'upstream_m3_identity':upstream['identity_sha256'],
        'validation_manifest':fm, 'holdout_manifest':hm,
        'frozen':frozen_metadata,
        'validation':json.loads((frozen/'validation.json').read_text()),
        'holdout':json.loads((holdout/'holdout.json').read_text()),
        'validation_comparisons':json.loads((frozen/'comparisons.json').read_text()),
        'holdout_comparisons':json.loads((holdout/'comparisons.json').read_text()),
        'checks':{'fresh_training_artifacts_byte_identical':True,'fresh_holdout_replay_byte_identical':True,
                  'reuse_preserves_bytes_and_mtimes':True,'historical_and_m3_preserved':True,
                  'historical_catalogue_preserved':True,'frozen_selection_precedes_holdout':True,
                  'historical_processed_files':len(before[str(data_dir/'historical/processed')]),
                  'm3_artifact_files':len(before[str(data_dir/'modelling')])},
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--m3-dir',type=Path,required=True)
    parser.add_argument('--frozen-dir',type=Path,required=True)
    parser.add_argument('--holdout-dir',type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=verify(args.m3_dir,args.frozen_dir,args.holdout_dir,args.data_dir)
    atomic_write_json(args.report,report)
    print(f'Experiment replay and preservation verified: {args.report}')


if __name__=='__main__':
    main()
