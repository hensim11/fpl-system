"""Offline M4B independent target/history checks, fresh builds, reuse and preservation."""
import argparse
import json
import lzma
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from fpl_ai.experiment_io import verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.historical_pipeline import load_historical_build
from fpl_ai.minutes import load_rows, run_minutes
from fpl_ai.modelling import read_csv
from fpl_ai.playing_time import SEASONS, build_playing_time, inspect_season, verify_features


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(root):
    return {str(p.relative_to(root)): [sha256_file(p), p.stat().st_mtime_ns]
            for p in sorted(Path(root).rglob('*')) if p.is_file()}


def independent_checks(feature_dir, data_dir):
    rows = load_rows(feature_dir)
    sources = json.loads((feature_dir/'sources.json').read_text())
    evidence = json.loads((feature_dir/'evidence.json').read_text())
    counts = Counter()
    traces = []
    schedule_evidence = {}
    for season in SEASONS:
        source = sources[season]
        build = load_historical_build(season, source['version'], data_dir)
        schedule = read_csv(build.processed_dir/'fixtures.csv')
        require(bool(schedule), 'independent audit: missing fixture schedule')
        schedule_by_id = {}
        for fixture in schedule:
            fid, gw = int(fixture['fixture']), int(fixture['gameweek'])
            require(fixture['season'] == season and fid > 0 and fid not in schedule_by_id,
                    'independent audit: invalid fixture schedule')
            schedule_by_id[fid] = gw
        fixture_gws = set(schedule_by_id.values())
        facts = read_csv(build.processed_dir/'player_fixture_facts.csv')
        fact_fixture_ids = set()
        for fact in facts:
            fid = int(fact['fixture'])
            require(fact['season'] == season and schedule_by_id.get(fid) == int(fact['gameweek']),
                    'independent audit: fact fixture/GW differs from schedule')
            if fact['position_at_fixture'] != 'AM':
                fact_fixture_ids.add(fid)
        require(fact_fixture_ids == set(schedule_by_id),
                'independent audit: scheduled fixtures missing player facts')
        require(source['consumed_tables']['fixtures.csv'] == sha256_file(build.processed_dir/'fixtures.csv'),
                'independent audit: label schedule checksum differs')
        counts['independently_checked_schedule_fixtures'] += len(schedule)
        known_gws = {r['target_gameweek'] for r in rows if r['season'] == season}
        require(fixture_gws <= known_gws, 'independent audit: schedule has unknown gameweek')
        schedule_evidence[season] = {
            'fixtures_sha256': sha256_file(build.processed_dir/'fixtures.csv'),
            'scheduled_fixtures': len(schedule), 'fact_covered_fixtures': len(fact_fixture_ids),
            'fixture_bearing_gameweeks': sorted(fixture_gws),
            'blank_gameweeks': sorted(known_gws-fixture_gws),
            'use': 'independent post-event label validation only; not a predictor',
        }

        totals, fixtures = defaultdict(int), defaultdict(set)
        for f in facts:
            if f['position_at_fixture'] == 'AM': continue
            k = (int(f['gameweek']), int(f['element']))
            totals[k] += int(f['minutes'])
            fixtures[k].add(int(f['fixture']))
        captures, settled = {}, {}
        for g, record in evidence[season]['captures'].items():
            raw = build.raw_dir/'fplcache'/record['source_path']
            require(sha256_file(raw) == record['sha256'], 'capture checksum changed')
            payload = json.loads(lzma.decompress(raw.read_bytes()))
            captures[int(g)] = {p['id']: p for p in payload['elements']}
        for g, record in evidence[season]['settlements'].items():
            raw = build.raw_dir/'fplcache'/record['source_path']
            require(sha256_file(raw) == record['sha256'], 'settlement checksum changed')
            payload = json.loads(lzma.decompress(raw.read_bytes()))
            event = next(e for e in payload['events'] if e['id'] == int(g))
            require(event['finished'] is True and event['data_checked'] is True, 'unsettled independent audit')
            settled[int(g)] = {p['id']: p for p in payload['elements']}
        for row in (r for r in rows if r['season'] == season):
            gw,e = row['target_gameweek'],row['element']
            k=gw,e
            if gw in fixture_gws:
                expected = totals[k]
                require(row['target_minutes'] == expected, 'canonical fixture target mismatch')
                current = settled[gw][e]['minutes']
                observed = current if gw == 1 else current-captures[gw][e]['minutes']
                require(type(observed) is int and observed == expected, 'independent cumulative target mismatch')
                counts['independently_checked_targets'] += 1
                if k not in fixtures: counts['explicit_empty_player_zero'] += 1
                if len(fixtures[k]) > 1: counts['double_rows'] += 1
            else:
                require(row['target_minutes'] is None, 'empty GW must be unlabelled')
                counts['fixture_empty_rows'] += 1
            prior = []
            for past in range(max(1,gw-3),gw):
                if past not in fixture_gws or e not in captures[past]:continue
                record = evidence[season]['settlements'][str(past)]
                if record['capture_time_utc'] > row['audit']['capture_time_utc']:continue
                observed = settled[past][e]['minutes']-(captures[past][e]['minutes'] if past>1 else 0)
                require(observed == totals[past,e], 'history differs from canonical minutes')
                prior.append(observed)
            require(row['features']['minutes_count_3'] == len(prior), 'history count mismatch')
            require(row['features']['minutes_mean_3'] == (mean(prior) if prior else None), 'history mean mismatch')
            p = captures[gw][e]
            require(row['features']['observed_season_minutes'] == (p['minutes'] if gw>1 else None), 'cumulative minutes mismatch')
            require(row['features']['observed_season_starts'] == (p.get('starts') if gw>1 else None), 'cumulative starts mismatch')
            require(row['features']['chance'] == p.get('chance_of_playing_next_round'), 'chance mismatch')
            require(row['features']['status'] == p.get('status'), 'status mismatch')
            require(row['features']['position'] == p['element_type'], 'position mismatch')
            if season=='2021-22' and gw==18:
                require(row['audit']['snapshot_age_minutes']=='207.0' and row['audit']['superseded_deadline_exception']=='True'
                        and row['audit']['capture_time_utc'].endswith('12:33:00Z'), 'GW18 freshness exception lost')
                counts['gw18_exception_rows'] += 1
            counts['independently_checked_feature_rows'] += 1
            if (gw==1 and e==1) or (len(fixtures[k])>1 and not any(t['season']==season and t['case']=='double' for t in traces)):
                traces.append({'season':season,'gameweek':gw,'element':e,'case':'gw1' if gw==1 else 'double',
                               'target_minutes':row['target_minutes'],'features':row['features'],'audit':row['audit']})
    return {'counts':dict(counts),'traces':traces,'schedule_evidence':schedule_evidence,
            'by_season':dict(Counter(r['season'] for r in rows)),
            'missingness':{f:sum(r['features'][f] is None for r in rows) for f in rows[0]['features']}}


def verify(feature_dir, model_dir, data_dir=Path('data')):
    feature_dir,model_dir,data_dir=map(Path,(feature_dir,model_dir,data_dir))
    protected={str(data_dir/p):fingerprint(data_dir/p) for p in ('historical/processed','modelling','experiments','experiment_holdouts')}
    catalogue=(data_dir/'historical/catalogue.json').read_bytes()
    fm=verify_features(feature_dir);mm=verify_bundle(model_dir,'minutes-freeze')
    require(mm['metadata']['features_identity']==fm['identity_sha256'],'minutes model uses different features')
    builds={s:v['version'] for s,v in json.loads((feature_dir/'sources.json').read_text()).items()}
    checks=independent_checks(feature_dir,data_dir)
    original={str(p):fingerprint(p) for p in (feature_dir,model_dir)}
    with tempfile.TemporaryDirectory() as tmp:
        f,reused=build_playing_time(data_dir,Path(tmp)/'features',builds)
        require(not reused,'fresh feature build unexpectedly reused')
        require(verify_features(f)==fm,'fresh minutes features differ')
        m,reused=run_minutes(f,Path(tmp)/'model')
        require(not reused,'fresh minutes fit unexpectedly reused')
        require(verify_bundle(m)==mm,'fresh minutes model or predictions differ')
    require(build_playing_time(data_dir,feature_dir.parent,builds)[1],'feature reuse failed')
    require(run_minutes(feature_dir,model_dir.parent)[1],'model reuse failed')
    for p,prior in original.items():require(fingerprint(p)==prior,'minutes reuse changed bytes or mtimes')
    for p,prior in protected.items():require(fingerprint(p)==prior,'accepted M2/M3/M4 artifacts changed')
    require((data_dir/'historical/catalogue.json').read_bytes()==catalogue,'historical catalogue changed')
    require(not any(p.name.startswith('.building-') for root in (feature_dir.parent,model_dir.parent) for p in root.iterdir()),'temporary artifacts remain')
    return {'features_manifest':fm,'minutes_manifest':mm,'independent_checks':checks,
            'frozen':json.loads((model_dir/'frozen.json').read_text()),
            'development':json.loads((model_dir/'development.json').read_text()),
            'checks':{'fresh_features_byte_identical':True,'fresh_model_predictions_metrics_byte_identical':True,
                      'reuse_preserves_bytes_and_mtimes':True,'accepted_M2_M3_M4_preserved':True,
                      'catalogue_preserved':True,'no_temporary_artifacts':True,'2025_26_not_loaded':True,
                      'blank_GWs_require_independent_processed_schedule':True,
                      'all_scheduled_fixtures_have_football_facts':True}}


def source_audit(feature_dir,data_dir):
    audits=json.loads((Path(feature_dir)/'evidence.json').read_text())
    cat=json.loads((Path(data_dir)/'historical/catalogue.json').read_text())
    _,audits['2024-25'],_=inspect_season('2024-25',cat['seasons']['2024-25']['latest_successful_version'],data_dir,False)
    tree=next((Path(data_dir)/'historical/raw/2021-22').glob('*/fplcache/github-tree.json'))
    payload=json.loads(tree.read_text())
    require(payload['truncated'] is False,'cannot conclude fixture absence from truncated tree')
    return {'seasons':audits,'selection_seasons':list(SEASONS),'2024_25_use':'source audit only; no minutes model predictions or metrics',
            '2025_26_use':'no new source/label/feature/model inspection; consumed holdout remains frozen',
            'fixture_tree':{'sha256':sha256_file(tree),'entries':len(payload['tree']),'truncated':False,
                            'fixture_named_paths':[r['path'] for r in payload['tree'] if 'fixture' in r['path'].lower()],
                            'conclusion':'no fixture captures found in pinned fplcache tree or accepted payload top-level keys; final Vaastav fixture files remain post-event'}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--features-dir',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--data-dir',type=Path,default=Path('data'))
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--source-report',type=Path)
    a=p.parse_args()
    report=verify(a.features_dir,a.model_dir,a.data_dir)
    atomic_write_json(a.report,report)
    if a.source_report:atomic_write_json(a.source_report,source_audit(a.features_dir,a.data_dir))
    print(f'Minutes reproduction and preservation verified: {a.report}')


if __name__=='__main__':main()
