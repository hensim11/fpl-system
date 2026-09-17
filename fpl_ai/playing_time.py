"""M4B: timestamped playing-time evidence, kept separate from frozen M3."""
import json
import lzma
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json, sha256_file
from fpl_ai.historical_pipeline import load_historical_build
from fpl_ai.historical_transform import parse_utc
from fpl_ai.modelling import capture_from_path, load_season, read_csv

SEASONS = ('2021-22', '2022-23', '2023-24')
KEYS = ('season', 'target_gameweek', 'element')
BASE = ('position', 'status', 'chance', 'previous_minutes', 'minutes_mean_3',
        'minutes_count_3', 'appearance_rate_3', 'observed_season_minutes',
        'observed_season_starts', 'status_changed', 'chance_change')
NULLABLE = tuple(f for f in BASE if f not in ('position', 'minutes_count_3'))
FEATURES = BASE + tuple(f + '_missing' for f in NULLABLE)
CONTRACT = {
    'version': 'playing-time-v2', 'features': list(FEATURES),
    'population': 'accepted snapshot football positions 1..4; season-local element; no final identity',
    'schedule_evidence': 'processed fixtures.csv defines fixture-bearing GWs for labels only; each scheduled fixture requires football-player facts with matching fixture/GW; blanks require schedule absence, never fact absence',
    'asof': 'accepted capture, strictly before authoritative deadline',
    'target': 'total realised minutes across all target-GW fixtures; registered nonplayers zero with evidence; globally fixture-empty GW null',
    'minutes_evidence': 'GW1 settled cumulative after season reset; later GWs settled cumulative minus accepted pre-GW cumulative; exact canonical sum agreement required',
    'history': 'only earlier GWs with independently evidenced minutes settled at or before capture; last three calendar GWs; missing stays null with counts',
    'cumulative': 'copy accepted bootstrap minutes/starts only after GW1; GW1 stale prior-season values excluded',
    'availability_changes': 'current minus immediately preceding GW accepted capture for same season/element; null if either observation missing',
    'fixture_context': 'unavailable historically; final fixtures never enter features',
    'splits': {'train': ['2021-22', '2022-23'], 'development': ['2023-24']},
    'downstream': 'not an xPts input; no in-sample predictions exported; temporal OOS integration deferred',
    'freshness': '2021-22 GW18 remains 12:33 state / 16:00 deadline / 207 minutes',
}
CANDIDATES = {
    'bootstrap.minutes': {'class': 'historically_point_in_time_safe', 'rule': 'direct accepted capture; GW1 stale totals excluded from current-season features'},
    'bootstrap.starts': {'class': 'historically_point_in_time_safe', 'rule': 'direct capture, nullable; absent 2021-22 and early 2022-23; GW1 excluded'},
    'minutes_per_gameweek': {'class': 'safe_only_after_explicit_settlement_evidence', 'rule': CONTRACT['minutes_evidence'] + '; both endpoint hashes retained'},
    'appearances': {'class': 'safe_only_after_explicit_settlement_evidence', 'rule': 'minutes > 0 for evidenced earlier GW, not a fixture appearance count'},
    'status': {'class': 'historically_point_in_time_safe', 'rule': 'direct accepted snapshot; null never means fit'},
    'chance_of_playing_next_round': {'class': 'historically_point_in_time_safe', 'rule': 'direct accepted snapshot; null never means 100 or zero'},
    'availability_changes': {'class': 'historically_point_in_time_safe', 'rule': CONTRACT['availability_changes']},
    'cumulative_capture_deltas': {'class': 'historically_point_in_time_safe', 'rule': 'observable change only; cannot call it GW minutes without separate settlement and reconciliation'},
    'chance_of_playing_this_round': {'class': 'historically_point_in_time_safe', 'rule': 'observable but not selected: ambiguous current/next-event semantics'},
    'news_added': {'class': 'historically_point_in_time_safe', 'rule': 'observable timestamp; not selected, no unverified news interpretation'},
    'form': {'class': 'unavailable_or_insufficiently_evidenced', 'rule': 'observable string but aggregation semantics not independently specified; not selected'},
    'minutes_per_game': {'class': 'unavailable_or_insufficiently_evidenced', 'rule': 'absent in audited archive'},
    'starts_per_90': {'class': 'historically_point_in_time_safe', 'rule': 'partially available, redundant; not selected'},
    'fixture_opponent_home_away_kickoff_count_difficulty': {'class': 'safe_prospectively_not_reconstructable_historically', 'rule': 'pinned archive contains bootstrap captures, not deadline fixture endpoint captures; preserve Decision 014'},
    'final_fixture_rows': {'class': 'post_event_final_source_only', 'rule': 'outcome validation only, never historical features'},
    'vaastav_quarantine_xP_fpl_ep_next': {'class': 'excluded', 'rule': 'quarantined timing / prohibited xP / external ep_next benchmark, never minutes inputs'},
}
AUDIT_FIELDS = ('minutes', 'starts', 'status', 'chance_of_playing_next_round',
                'chance_of_playing_this_round', 'news_added', 'form', 'minutes_per_game', 'starts_per_90')


def integer(value, name):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f'invalid nonnegative integer {name}')
    return value


def players(payload):
    result = {}
    for p in payload['elements']:
        if type(p['id']) is not int or p['id'] in result:
            raise ValueError('duplicate or invalid raw player')
        result[p['id']] = p
    return result


def feature_values(gw, player, previous, history):
    """Only observed state and already time-filtered minutes enter this projection."""
    position = player['element_type']
    if type(position) is not int or position not in (1, 2, 3, 4):
        raise ValueError('non-football position')
    chance = integer(player.get('chance_of_playing_next_round'), 'chance')
    if chance is not None and chance > 100:
        raise ValueError('chance outside percent range')
    status = player.get('status')
    if status is not None and (not isinstance(status, str) or not status):
        raise ValueError('invalid status')
    recent = [history[g] for g in range(max(1, gw-3), gw) if g in history]
    old_status = previous.get('status') if previous else None
    old_chance = previous.get('chance_of_playing_next_round') if previous else None
    f = dict(position=position, status=status, chance=chance,
             previous_minutes=history.get(gw-1), minutes_mean_3=mean(recent) if recent else None,
             minutes_count_3=len(recent), appearance_rate_3=mean(v > 0 for v in recent) if recent else None,
             observed_season_minutes=integer(player.get('minutes'), 'minutes') if gw > 1 else None,
             observed_season_starts=integer(player.get('starts'), 'starts') if gw > 1 else None,
             status_changed=int(status != old_status) if status is not None and old_status is not None else None,
             chance_change=chance-old_chance if chance is not None and old_chance is not None else None)
    f.update({name+'_missing': int(f[name] is None) for name in NULLABLE})
    return f


def evidenced_minutes(gw, before, after, expected):
    """Never infer a zero from an absent raw observation, including no-fact targets."""
    end = integer(after.get('minutes'), 'settled minutes') if after else None
    start = integer(before.get('minutes'), 'pre-GW minutes') if before else None
    if end is None or (gw != 1 and start is None):
        raise ValueError('minutes target lacks explicit cumulative evidence')
    observed = end if gw == 1 else end-start
    if observed != expected:
        raise ValueError(f'minutes target disagrees with independent evidence: GW{gw}: {observed} != {expected}')
    return observed


def raw_payload(build, record):
    path = build.raw_dir/'fplcache'/record['source_path']
    if sha256_file(path) != record['sha256']:
        raise ValueError('playing-time raw checksum mismatch')
    return json.loads(lzma.decompress(path.read_bytes()))


def reconcile_schedule(season, gameweeks, schedule, facts):
    """Final schedule is label-only evidence; never projected into predictors."""
    if not schedule:
        raise ValueError('missing/empty historical fixture schedule evidence')
    expected = {}
    for row in schedule:
        fixture, gw = int(row['fixture']), int(row['gameweek'])
        if row['season'] != season or fixture <= 0 or fixture in expected or gw not in gameweeks:
            raise ValueError('invalid historical fixture schedule evidence')
        expected[fixture] = gw
    observed = set()
    for row in facts:
        fixture, gw = int(row['fixture']), int(row['gameweek'])
        if row['season'] != season or expected.get(fixture) != gw:
            raise ValueError('player facts disagree with independent fixture schedule')
        if row['position_at_fixture'] != 'AM':
            observed.add(fixture)
    missing = set(expected)-observed
    if missing:
        raise ValueError(f'scheduled fixtures lack player facts: {sorted(missing)}')
    return set(expected.values())


def inspect_season(season, version, data_dir, build_features=True):
    if season not in SEASONS and (build_features or season != '2024-25'):
        raise ValueError('minutes development excludes all other seasons, including consumed 2025-26')
    # Reuse the existing independently verified point/identity/settlement gates.
    rows, source = load_season(season, version, data_dir)
    build = load_historical_build(season, version, data_dir)
    gameweeks = {int(g['gameweek']): g for g in read_csv(build.processed_dir/'gameweeks.csv')}
    schedule = read_csv(build.processed_dir/'fixtures.csv')
    facts = read_csv(build.processed_dir/'player_fixture_facts.csv')
    fixture_gws = reconcile_schedule(season, gameweeks, schedule, facts)
    source['consumed_tables']['fixtures.csv'] = sha256_file(build.processed_dir/'fixtures.csv')
    raw, provenance = {}, {}
    for gw, g in sorted(gameweeks.items()):
        record = {'source_path': g['snapshot_source_path'], 'sha256': g['snapshot_sha256']} if 'snapshot_sha256' in g else None
        if record is None:
            snap = next(r for r in rows if r['target_gameweek'] == gw)
            record = {'source_path': snap['audit']['snapshot_source_path'], 'sha256': snap['audit']['snapshot_sha256']}
        payload = raw_payload(build, record)
        capture = capture_from_path(record['source_path'])
        if capture != g['selected_snapshot_capture_time_utc'] or parse_utc(capture, 'capture') >= parse_utc(g['deadline_time_utc'], 'deadline'):
            raise ValueError('raw capture boundary mismatch')
        raw[gw] = payload
        provenance[str(gw)] = dict(record, capture_time_utc=capture, deadline_time_utc=g['deadline_time_utc'])
    by_gw = {g: players(p) for g, p in raw.items()}
    settled = {g: raw_payload(build, rec) for g, rec in source['settlements'].items()}
    totals = defaultdict(int)
    for f in facts:
        if f['position_at_fixture'] == 'AM':
            continue
        g, e = int(f['gameweek']), int(f['element'])
        totals[g, e] += integer(int(f['minutes']), 'fixture minutes')
    differences, targets, evidence = [], {}, {}
    cumulative_disagreements = []
    cumulative_comparisons = 0
    for gw, payload in settled.items():
        capture = source['settlements'][gw]['capture_time_utc']
        event = [e for e in payload['events'] if e['id'] == gw]
        if len(event) != 1 or event[0]['finished'] is not True or event[0]['data_checked'] is not True:
            raise ValueError('minutes requires settled target event')
        if parse_utc(capture, 'settlement') <= parse_utc(gameweeks[gw]['deadline_time_utc'], 'deadline'):
            raise ValueError('settlement precedes target')
        if gw+1 in gameweeks and parse_utc(capture, 'settlement') >= parse_utc(gameweeks[gw+1]['deadline_time_utc'], 'deadline'):
            raise ValueError('cumulative evidence overlaps next target GW')
        end = players(payload)
        for e, p in end.items():
            if p['element_type'] == 5:
                continue
            expected = sum(totals[g, e] for g in range(1, gw+1))
            cumulative_comparisons += 1
            if p.get('minutes') != expected:
                cumulative_disagreements.append({'gameweek': gw, 'element': e, 'observed': p.get('minutes'), 'canonical': expected})
        for e, p in by_gw[gw].items():
            if p['element_type'] == 5 or gw not in fixture_gws:
                continue
            try:
                targets[gw, e] = evidenced_minutes(gw, p, end.get(e), totals[gw, e])
            except ValueError as exc:
                differences.append({'gameweek': gw, 'element': e, 'reason': str(exc)})
            evidence[gw, e] = capture
    fields = {f: dict(sorted(Counter(type(p.get(f)).__name__ for payload in raw.values() for p in payload['elements']).items())) for f in AUDIT_FIELDS}
    audit = {'season': season, 'version': version, 'source_identity_sha256': source['source_identity_sha256'],
             'build_identity_sha256': source['build_identity_sha256'], 'captures': provenance,
             'settlements': {str(g): r for g, r in source['settlements'].items()},
             'candidate_fields': CANDIDATES, 'field_types': fields,
             'minutes_target_comparisons': len(targets)+len(differences), 'minutes_target_disagreements': differences,
             'cumulative_comparisons': cumulative_comparisons, 'cumulative_disagreements': cumulative_disagreements,
             'raw_top_level_keys': sorted(set().union(*(p.keys() for p in raw.values()))),
             'gw1_stale_nonzero_minutes': sum(p.get('minutes', 0) > 0 for p in raw[1]['elements']),
             'snapshot_exception': source['snapshot_exception']}
    if not build_features:
        return [], audit, source
    if differences:
        raise ValueError(f'{season} minutes evidence failed: {differences[:3]}')
    return construct_rows(rows, by_gw, targets, evidence, fixture_gws), audit, source


def construct_rows(rows, by_gw, targets, evidence, fixture_gws):
    """Project rows only after evidence validation; outcomes never enter same-GW inputs."""
    by_player = defaultdict(dict)
    for (g, e), value in targets.items():
        by_player[e][g] = value
    result = []
    for row in rows:
        gw, e = row['target_gameweek'], row['element']
        capture = row['audit']['capture_time_utc']
        history = {g: v for g, v in by_player[e].items() if g < gw and evidence[g, e] <= capture}
        f = feature_values(gw, by_gw[gw][e], by_gw.get(gw-1, {}).get(e), history)
        y = targets.get((gw, e)) if gw in fixture_gws else None
        if gw in fixture_gws and y is None:
            raise ValueError('target evidence population incomplete')
        result.append({**{k: row[k] for k in KEYS}, 'features': f, 'target_minutes': y,
                       'label_available_at': evidence.get((gw, e)), 'audit': row['audit']})
    return result


def build_playing_time(data_dir=Path('data'), output_dir=Path('data/playing_time'), builds=None):
    data_dir = Path(data_dir)
    if builds is None:
        cat = json.loads((data_dir/'historical/catalogue.json').read_text())
        builds = {s: cat['seasons'][s]['latest_successful_version'] for s in SEASONS}
    if set(builds) != set(SEASONS):
        raise ValueError('exact minutes train/development seasons required')
    rows, audits, sources = [], {}, {}
    for s in SEASONS:
        batch, audits[s], sources[s] = inspect_season(s, builds[s], data_dir)
        rows.extend(batch)
    def writer(folder):
        atomic_write_json(folder/'contract.json', CONTRACT)
        atomic_write_json(folder/'evidence.json', audits)
        atomic_write_json(folder/'sources.json', sources)
        atomic_write_csv(folder/'features.csv', ({**{k:r[k] for k in KEYS}, **r['features']} for r in rows), list(KEYS+FEATURES))
        atomic_write_csv(folder/'labels.csv', ({**{k:r[k] for k in KEYS}, 'target_minutes': r['target_minutes'], 'label_available_at': r['label_available_at']} for r in rows), list(KEYS)+['target_minutes','label_available_at'])
        atomic_write_csv(folder/'row_audit.csv', ({**{k:r[k] for k in KEYS}, **r['audit']} for r in rows), list(KEYS)+list(rows[0]['audit']))
    return publish(output_dir, {'kind': 'playing-time-features', 'contract': CONTRACT}, writer)


def verify_features(folder):
    manifest = verify_bundle(folder, 'playing-time-features')
    if manifest['metadata']['contract'] != CONTRACT or json.loads((Path(folder)/'contract.json').read_text()) != CONTRACT:
        raise ValueError('playing-time contract mismatch')
    return manifest
