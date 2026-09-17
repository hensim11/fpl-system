"""Offline full M3 rebuild, preservation and independent row-trace verification."""
import argparse
import json
import lzma
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import mean

from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.historical_pipeline import load_historical_build
from fpl_ai.historical_schema import POST_EVENT_FIXTURE_CONTEXT_FIELDS
from fpl_ai.modelling import read_csv, run_modelling
from fpl_ai.modelling_contract import FEATURES, KEYS


class VerificationError(RuntimeError):
    """A required real-data verification condition failed."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def fingerprint(root):
    return {str(p.relative_to(root)): [sha256_file(p), p.stat().st_mtime_ns]
            for p in sorted(root.rglob('*')) if p.is_file()}


def verify(data_dir):
    historical = data_dir/'historical'
    before = fingerprint(historical/'processed')
    catalogue_before = (historical/'catalogue.json').read_bytes()
    path, _ = run_modelling(data_dir)
    original = fingerprint(path)
    manifest = json.loads((path/'manifest.json').read_text())
    builds = {s:v['version'] for s,v in manifest['identity']['sources'].items()}
    with tempfile.TemporaryDirectory() as tmp:
        rebuilt, reused = run_modelling(data_dir, Path(tmp), builds)
        require(not reused, 'fresh temporary build unexpectedly reused artifacts')
        require({p.name:sha256_file(p) for p in path.iterdir()} == {p.name:sha256_file(p) for p in rebuilt.iterdir()}, 'fresh rebuild differs byte-for-byte')
    require(run_modelling(data_dir, builds=builds)[1], 'published build was not reused')
    require(fingerprint(path) == original, 'reuse changed artifact bytes or mtimes')
    require(fingerprint(historical/'processed') == before, 'historical processed files changed')
    require((historical/'catalogue.json').read_bytes() == catalogue_before, 'historical catalogue bytes changed')
    features = read_csv(path/'features.csv')
    labels = read_csv(path/'labels.csv')
    audits = read_csv(path/'row_audit.csv')
    require(set(features[0]) == set(KEYS) | set(FEATURES), 'feature columns differ from the closed contract')
    forbidden = set(POST_EVENT_FIXTURE_CONTEXT_FIELDS) | {'xP', 'value', 'selected', 'transfers_balance',
                                                        'transfers_in', 'transfers_out', 'modified', 'external_ep_next'}
    require(not forbidden.intersection(features[0]), 'forbidden columns entered features')
    def key(r): return (r['season'],int(r['target_gameweek']),int(r['element']))
    fs, ys, meta = ({key(r):r for r in table} for table in (features,labels,audits))
    require(len(fs) == len(features) == len(ys) == len(meta), 'artifact populations contain duplicate or missing row keys')
    require(set(fs) == set(ys) == set(meta), 'artifact row key populations differ')
    require(all(int(r['deadline_position_id']) in (1,2,3,4) for r in features), 'non-football position entered features')
    traces = []
    checked_targets = 0
    checked_empty_zeros = 0
    # Fixed audit examples, not selected by predictive performance.
    cases = [('2021-22',18,233), ('2022-23',1,546), ('2022-23',2,558),
             ('2022-23',7,283), ('2023-24',26,355), ('2024-25',25,328), ('2025-26',27,100)]
    for season in builds:
        build = load_historical_build(season,builds[season],data_dir)
        facts = read_csv(build.processed_dir/'player_fixture_facts.csv')
        snaps = read_csv(build.processed_dir/'player_deadline_snapshots.csv')
        fact_groups = defaultdict(list)
        for r in facts: fact_groups[(int(r['gameweek']),int(r['element']))].append(r)
        snapshot_map = {(int(r['gameweek']),int(r['element'])):r for r in snaps}
        # Independently verify every label, including empty sums, from pinned raw payloads.
        settled_points = {}
        for gw, evidence in manifest['identity']['sources'][season]['settlements'].items():
            raw_path = build.raw_dir/'fplcache'/evidence['source_path']
            require(sha256_file(raw_path) == evidence['sha256'], 'settlement checksum mismatch')
            payload = json.loads(lzma.decompress(raw_path.read_bytes()))
            event = next(e for e in payload['events'] if e['id'] == int(gw))
            require(event['finished'] is True and event['data_checked'] is True,
                    f'unsettled target evidence: {season}/{gw}')
            settled_points[int(gw)] = {p['id']:p['event_points'] for p in payload['elements']}
        fixture_gws = {g for g, _ in fact_groups}
        for k, label in ys.items():
            if k[0] != season:
                continue
            _, gw, element = k
            target = label['target_points']
            if gw not in fixture_gws:
                require(target == '', f'fixture-empty GW must be unlabelled: {k}')
                continue
            require(target != '', f'missing target in fixture-bearing GW: {k}')
            expected = sum(int(r['total_points']) for r in fact_groups.get((gw,element), []))
            observed = settled_points.get(gw, {}).get(element)
            require(type(observed) is int and observed == expected == int(target),
                    f'target lacks matching integer settlement evidence: {k}')
            checked_targets += 1
            if not fact_groups.get((gw,element)):
                require(observed == 0 and meta[k]['label_status'] == 'empty_player_sum',
                        f'empty-player label lacks explicit settled zero: {k}')
                checked_empty_zeros += 1
        # Add one true double example and one snapshot-observed transfer.
        double = next(((g,e) for (g,e),rr in fact_groups.items()
                       if len(rr)>1 and (g,e) in snapshot_map and snapshot_map[g,e]['deadline_position_id']!='5'),None)
        if double: cases.append((season,*double))
        previous_team = {}
        for r in snaps:
            el = int(r['element'])
            if el in previous_team and previous_team[el] != r['deadline_team_id'] and r['deadline_position_id']!='5':
                cases.append((season,int(r['gameweek']),el))
                break
            previous_team[el] = r['deadline_team_id']
        for s,gw,el in [c for c in cases if c[0]==season]:
            k = (s,gw,el)
            snap = snapshot_map[gw,el]
            raw = json.loads(lzma.decompress((build.raw_dir/'fplcache'/snap['source_path']).read_bytes()))
            player = next(p for p in raw['elements'] if p['id']==el)
            require(fs[k]['price']==str(player['now_cost']), 'traced price differs from raw snapshot')
            require(fs[k]['deadline_team_id']==str(player['team']), 'traced team differs from raw snapshot')
            require(meta[k]['observed_player_code']==str(player['code']), 'traced player code differs from raw snapshot')
            target_facts = fact_groups[gw,el]
            if ys[k]['target_points']:
                require(int(ys[k]['target_points']) == sum(int(r['total_points']) for r in target_facts), 'traced target differs from fixture sum')
            history = []
            for past in range(max(1,gw-3),gw):
                evidence = manifest['identity']['sources'][s]['settlements'].get(str(past))
                if evidence is None or evidence['capture_time_utc'] > snap['capture_time_utc']:
                    continue
                settled = json.loads(lzma.decompress((build.raw_dir/'fplcache'/evidence['source_path']).read_bytes()))
                person = next((p for p in settled['elements'] if p['id']==el),None)
                if person is None: continue
                value = sum(int(r['total_points']) for r in fact_groups[past,el])
                require(value == person['event_points'], 'traced history differs from settled event points')
                history.append({'gameweek':past,'points':value,'settlement':evidence})
            require(int(fs[k]['points_count_3']) == len(history), 'traced rolling count differs from available history')
            require((float(fs[k]['points_mean_3']) if fs[k]['points_mean_3'] else None) == (mean(r['points'] for r in history) if history else None), 'traced rolling mean differs from available history')
            traces.append({'key':list(k),'name':player['web_name'],'source_snapshot':snap['source_path'],
                           'target_fixture_points':[int(r['total_points']) for r in target_facts],
                           'target':ys[k]['target_points'],'prior_three_calendar_gameweeks':history,
                           'features':fs[k],'audit':meta[k]})
    require(meta['2021-22',18,233]['capture_time_utc']=='2021-12-18T12:33:00Z', 'GW18 exception capture changed')
    require(float(meta['2021-22',18,233]['snapshot_age_minutes'])==207, 'GW18 exception freshness gap changed')
    require(meta['2022-23',1,546]['observed_player_code']=='536122', 'Harris GW1 observed code changed')
    require(meta['2022-23',1,558]['observed_player_code']=='530332', 'Bueno GW1 observed code changed')
    require(meta['2022-23',2,558]['observed_player_code']=='490721', 'Bueno GW2 observed code changed')
    require(('2025-26',38,841) not in fs, 'Sillah was backfilled into GW38')
    report = json.loads((path/'evaluation.json').read_text())
    require(checked_targets == report['summary']['labelled_rows'], 'not all targets verified')
    require(checked_empty_zeros == report['summary']['label_status']['empty_player_sum'],
            'not all empty-player zero targets verified')
    require((len(features), checked_targets, checked_empty_zeros) == (137662, 137038, 4553),
            'accepted five-season population or label counts changed')
    return {'identity_sha256':manifest['identity_sha256'], 'artifact_hashes':manifest['artifacts'],
            'historical_builds':{s:{k:v[k] for k in ('version','source_identity_sha256','build_identity_sha256')}
                                 for s,v in manifest['identity']['sources'].items()},
            'checks': {'fresh_rebuild_byte_identical':True,'reuse_preserves_hashes_and_mtimes':True,
                       'historical_processed_files_preserved':len(before),'historical_catalogue_unchanged':True,
                       'all_targets_match_settlement':True, 'settlement_verified_targets':checked_targets,
                       'settlement_verified_empty_player_zeros':checked_empty_zeros,
                       'no_forbidden_or_fixture_columns':True,'snapshot_population_and_anomalies_preserved':True},
            'summary':report['summary'],'evaluation':report['splits'],'manual_source_traces':traces}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    report = verify(args.data_dir)
    atomic_write_json(args.report,report)
    print(f"Verified {report['summary']['rows']} rows; evidence: {args.report}")
