"""Actual-clock capture, pre-deadline forecast freezes and separate settled scoring."""
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from fpl_ai.client import DEFAULT_BASE_URL, FPLClient
from fpl_ai.errors import FPLValidationError
from fpl_ai.validation import validate_fixture_schedule
from fpl_ai.experiment_io import digest, publish, verify_bundle
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json, sha256_file
from fpl_ai.historical_transform import parse_utc
from fpl_ai.modelling import read_csv
from fpl_ai.playing_time import CONTRACT, FEATURES, KEYS, feature_values, integer, players

SNAPSHOT_CONTRACT = {
    'version': 'prospective-fixtures-v2',
    'source': DEFAULT_BASE_URL,
    'timing': 'separate request-start and response-completion UTC timestamps; both complete before authoritative bootstrap deadline; responses not atomic',
    'fixtures': 'raw official fixture endpoint frozen at capture; target fixture id/event/teams/opponent/home-away/kickoff/difficulty available only as observed; unknown kickoff stays null',
    'schedule_evidence': 'nonempty structurally valid full-season response with known teams/events and at least one event-assigned fixture; only target-specific absence establishes a blank',
    'historical_use': False,
}
FORECAST_CONTRACT = {
    'version': 'prospective-predictions-v1', 'feature_contract': CONTRACT,
    'predictions': ['expected_minutes', 'expected_points'],
    'expected_points': 'null in v1; frozen M4 has no current-season feature adapter',
    'outcomes': 'forbidden in prediction files; later scoring is a distinct artifact',
    'clock': 'runtime UTC; no CLI timestamp override; completion and publication must precede deadline',
    'confirmation': 'locally timestamped evidence; not an externally witnessed or signed timestamp',
}
SETTLEMENT_CONTRACT = {
    'version': 'prospective-settlement-v2',
    'rule': 'bootstrap finished and data_checked; nonempty target fixtures all finished; live stats minutes/points equal summed per-fixture explain values; complete forecast player coverage',
    'empty_gameweek': 'null outcomes only with a validated nonempty full-season schedule having no target-GW fixtures; empty/missing/unusable schedule fails',
}


def now_utc():
    return datetime.now(timezone.utc)


def stamp(clock):
    value = clock()
    if value.tzinfo is None:
        raise ValueError('clock must be timezone aware')
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def before(a, b):
    return parse_utc(a, 'timestamp') < parse_utc(b, 'timestamp')


def require_predeadline(clock, deadline):
    if not before(stamp(clock), deadline):
        raise ValueError('publication reached deadline')


def not_after(a, b):
    return parse_utc(a, 'timestamp') <= parse_utc(b, 'timestamp')


def event_for(payload, gw):
    matches = [e for e in payload['events'] if e['id'] == gw]
    if len(matches) != 1:
        raise ValueError('missing or ambiguous authoritative event')
    return matches[0]


def check_season(season, payload):
    if not re.fullmatch(r'20\d\d-\d\d', season) or int(season[-2:]) != (int(season[:4])+1) % 100:
        raise ValueError('invalid season')
    first = event_for(payload, 1)
    if parse_utc(first['deadline_time'], 'season first deadline').year != int(season[:4]):
        raise ValueError('season does not match authoritative GW1 deadline year')


def timed_get(call, clock):
    start = stamp(clock)
    value = call()
    end = stamp(clock)
    if not not_after(start, end):
        raise ValueError('clock moved backwards during request')
    return value, {'requested_at': start, 'received_at': end}


def safe_output(output_dir, *inputs):
    root = Path(output_dir).resolve()
    for p in inputs:
        if root == Path(p).resolve() or Path(p).resolve() in root.parents:
            raise ValueError('output cannot modify an input artifact directory')


def fixture_validation(fixtures, payload, gw, predeadline):
    try:
        validate_fixture_schedule(payload, fixtures)
    except FPLValidationError as exc:
        raise ValueError(str(exc)) from exc
    teams = {t['id'] for t in payload['teams']}
    ids = set()
    target = []
    for f in fixtures:
        if type(f.get('id')) is not int or f['id'] in ids:
            raise ValueError('duplicate or invalid fixture id')
        ids.add(f['id'])
        if f.get('team_h') not in teams or f.get('team_a') not in teams or f['team_h'] == f['team_a']:
            raise ValueError('invalid fixture teams')
        if f.get('kickoff_time') is not None:
            parse_utc(f['kickoff_time'], 'kickoff')
        if f.get('event') == gw:
            target.append(f)
            if predeadline and (f.get('started') is True or f.get('finished') is True or
                                f.get('team_h_score') is not None or f.get('team_a_score') is not None):
                raise ValueError('target fixture already contains outcomes')
            if not predeadline and f.get('finished') is not True:
                raise ValueError('target fixture not settled')
    return target


def capture_snapshot(season, gw, output_dir=Path('data/prospective_snapshots'), *, client=None, clock=now_utc):
    client = client or FPLClient()
    if client.base_url != DEFAULT_BASE_URL:
        raise ValueError('prospective evidence requires official FPL endpoints')
    bootstrap, bt = timed_get(client.get_bootstrap, clock)
    check_season(season, bootstrap)
    event = event_for(bootstrap, gw)
    deadline = event['deadline_time']
    if event.get('is_next') is not True or sum(e.get('is_next') is True for e in bootstrap['events']) != 1:
        raise ValueError('capture must target the unambiguous upcoming GW')
    fixtures, ft = timed_get(client.get_fixtures, clock)
    fixture_validation(fixtures, bootstrap, gw, True)
    players(bootstrap)
    if not before(ft['received_at'], deadline) or not not_after(bt['received_at'], ft['requested_at']):
        raise ValueError('snapshot must complete before target deadline')
    metadata = {'kind': 'prospective-snapshot', 'contract': SNAPSHOT_CONTRACT, 'season': season,
                'target_gameweek': gw, 'deadline': deadline,
                'bootstrap_timing': bt, 'fixtures_timing': ft}
    def writer(folder):
        atomic_write_json(folder/'bootstrap.json', bootstrap)
        atomic_write_json(folder/'fixtures.json', fixtures)
        if not before(stamp(clock), deadline):
            raise ValueError('snapshot publication reached deadline')
    return publish(output_dir, metadata, writer, publication_guard=lambda: require_predeadline(clock, deadline))


def load_snapshot(folder):
    folder = Path(folder)
    manifest = verify_bundle(folder, 'prospective-snapshot')
    m = manifest['metadata']
    if m['contract'] != SNAPSHOT_CONTRACT:
        raise ValueError('prospective snapshot contract mismatch')
    bootstrap = json.loads((folder/'bootstrap.json').read_text())
    fixtures = json.loads((folder/'fixtures.json').read_text())
    check_season(m['season'], bootstrap)
    event = event_for(bootstrap, m['target_gameweek'])
    if event['deadline_time'] != m['deadline'] or event.get('is_next') is not True:
        raise ValueError('prospective authoritative deadline mismatch')
    bt, ft = m['bootstrap_timing'], m['fixtures_timing']
    if not (not_after(bt['requested_at'], bt['received_at']) and not_after(bt['received_at'], ft['requested_at'])
            and not_after(ft['requested_at'], ft['received_at']) and before(ft['received_at'], m['deadline'])):
        raise ValueError('prospective capture timing mismatch')
    fixture_validation(fixtures, bootstrap, m['target_gameweek'], True)
    return bootstrap, fixtures, manifest


def freeze_predictions(snapshot_dir, model_dir, output_dir=Path('data/prospective_predictions'), *,
                       previous_dir=None, history_pairs=(), clock=now_utc):
    from fpl_ai.minutes import load_frozen, predict
    safe_output(output_dir, snapshot_dir, model_dir)
    bootstrap, fixtures, snapshot = load_snapshot(snapshot_dir)
    meta = snapshot['metadata']
    season, gw, deadline = meta['season'], meta['target_gameweek'], meta['deadline']
    started = stamp(clock)
    if not (not_after(meta['fixtures_timing']['received_at'], started) and before(started, deadline)):
        raise ValueError('forecast must be generated after source capture and before deadline')
    model, frozen, model_manifest = load_frozen(model_dir)
    if not before(frozen['latest_training_settlement'], meta['bootstrap_timing']['requested_at']):
        raise ValueError('future-fitted minutes model')
    # Model selection also needs to be prior information, not only training labels.
    if int(season[:4]) <= 2023:
        raise ValueError('model development season cannot be a prospective forecast season')
    previous = {}
    previous_id = None
    if previous_dir:
        safe_output(output_dir, previous_dir)
        old, _, old_manifest = load_snapshot(previous_dir)
        om = old_manifest['metadata']
        if om['season'] != season or om['target_gameweek'] != gw-1 or not before(om['fixtures_timing']['received_at'], meta['bootstrap_timing']['requested_at']):
            raise ValueError('availability history requires previous GW capture before current capture')
        previous = players(old)
        previous_id = old_manifest['identity_sha256']
    histories, history_sources = {}, []
    seen_gws = set()
    for prior_prediction, settlement_dir in history_pairs:
        safe_output(output_dir, prior_prediction, settlement_dir)
        old_prediction = verify_prediction(prior_prediction)
        outcomes, settled = load_settlement(settlement_dir, old_prediction)
        expected_players = {int(r['element']) for r in read_csv(Path(prior_prediction)/'predictions.csv')}
        if not expected_players <= {r['element'] for r in outcomes}:
            raise ValueError('history settlement lacks predicted population')
        outcomes = [r for r in outcomes if r['element'] in expected_players]
        om = old_prediction['metadata']
        past = om['target_gameweek']
        if om['season'] != season or past >= gw or past in seen_gws or not not_after(settled['metadata']['received_at'], meta['bootstrap_timing']['requested_at']):
            raise ValueError('future, duplicate or cross-season playing-time history')
        seen_gws.add(past)
        for r in outcomes:
            if r['target_minutes'] is not None:
                histories.setdefault(r['element'], {})[past] = r['target_minutes']
        history_sources.append({'prediction': old_prediction['identity_sha256'], 'settlement': settled['identity_sha256']})
    rows = [{ 'season': season, 'target_gameweek': gw, 'element': e,
              'features': feature_values(gw, p, previous.get(e), histories.get(e, {}))}
            for e,p in sorted(players(bootstrap).items()) if p['element_type'] in (1,2,3,4)]
    all_predictions = predict(rows, model, frozen)
    preds = [{**{k:p[k] for k in KEYS}, 'expected_minutes': p[frozen['selected']], 'expected_points': None} for p in all_predictions]
    completed = stamp(clock)
    if not (not_after(started, completed) and before(completed, deadline)):
        raise ValueError('prediction completion reached deadline')
    metadata = {'kind': 'prospective-predictions', 'contract': FORECAST_CONTRACT,
                'season': season, 'target_gameweek': gw, 'deadline': deadline,
                'prediction_started_at': started, 'prediction_timestamp': completed,
                'snapshot_identity': snapshot['identity_sha256'], 'snapshot_manifest_sha256': sha256_file(Path(snapshot_dir)/'manifest.json'),
                'snapshot_artifacts': snapshot['artifacts'], 'snapshot_timing': {k:meta[k] for k in ('bootstrap_timing','fixtures_timing')},
                'feature_contract_identity': digest(CONTRACT), 'model_identity': model_manifest['identity_sha256'],
                'model_artifacts': model_manifest['artifacts'], 'model_manifest_sha256': sha256_file(Path(model_dir)/'manifest.json'),
                'fixture_context_snapshot_identity': snapshot['identity_sha256'], 'fixture_features_used': False,
                'previous_snapshot_identity': previous_id, 'history_sources': sorted(history_sources, key=lambda r:r['prediction'])}
    def writer(folder):
        atomic_write_csv(folder/'features.csv', ({**{k:r[k] for k in KEYS}, **r['features']} for r in rows), list(KEYS+FEATURES))
        atomic_write_csv(folder/'predictions.csv', preds, list(KEYS)+['expected_minutes', 'expected_points'])
        if not before(stamp(clock), deadline):
            raise ValueError('prediction publication reached deadline')
    return publish(output_dir, metadata, writer, publication_guard=lambda: require_predeadline(clock, deadline))


def verify_prediction(folder):
    manifest = verify_bundle(folder, 'prospective-predictions')
    m = manifest['metadata']
    if m['contract'] != FORECAST_CONTRACT or m['feature_contract_identity'] != digest(CONTRACT):
        raise ValueError('prediction contract mismatch')
    if not (not_after(m['snapshot_timing']['fixtures_timing']['received_at'], m['prediction_started_at']) and
            not_after(m['prediction_started_at'], m['prediction_timestamp']) and before(m['prediction_timestamp'], m['deadline'])):
        raise ValueError('invalid forecast time boundary')
    populations = []
    for file, columns in [('features.csv', set(KEYS+FEATURES)), ('predictions.csv', set(KEYS+('expected_minutes','expected_points')))]:
        keys = set()
        for r in read_csv(Path(folder)/file):
            if set(r) != columns or r['season'] != m['season'] or int(r['target_gameweek']) != m['target_gameweek'] or int(r['element']) in keys:
                raise ValueError('prediction population or closed columns mismatch')
            if file == 'predictions.csv':
                if r['expected_points'] != '' or r['expected_minutes'] == '':
                    raise ValueError('v1 requires minutes forecasts and null points')
                value = float(r['expected_minutes'])
                if not math.isfinite(value) or value < 0:
                    raise ValueError('invalid expected minutes')
            keys.add(int(r['element']))
        populations.append(keys)
    if not populations[0] or populations[0] != populations[1]:
        raise ValueError('prediction populations differ')
    return manifest


def capture_settlement(prediction_dir, output_dir=Path('data/prospective_settlements'), *, client=None, clock=now_utc):
    safe_output(output_dir, prediction_dir)
    prediction = verify_prediction(prediction_dir)
    p = prediction['metadata']
    client = client or FPLClient()
    if client.base_url != DEFAULT_BASE_URL:
        raise ValueError('settlement requires official FPL endpoints')
    bootstrap, bt = timed_get(client.get_bootstrap, clock)
    fixtures, ft = timed_get(client.get_fixtures, clock)
    live, lt = timed_get(lambda: client.get_event_live(p['target_gameweek']), clock)
    metadata = {'kind': 'prospective-settlement', 'contract': SETTLEMENT_CONTRACT, 'season': p['season'],
                'target_gameweek': p['target_gameweek'], 'deadline': p['deadline'],
                'prediction_identity': prediction['identity_sha256'], 'received_at': lt['received_at'],
                'request_timing': {'bootstrap': bt, 'fixtures': ft, 'live': lt}}
    # Validate before publication; don't publish unusable settlement evidence.
    outcomes = settlement_outcomes(bootstrap, fixtures, live, metadata, prediction)
    expected_players = {int(r['element']) for r in read_csv(Path(prediction_dir)/'predictions.csv')}
    if not expected_players <= set(outcomes):
        raise ValueError('settlement lacks explicit predicted player outcome')
    def writer(folder):
        for name,value in [('bootstrap.json',bootstrap),('fixtures.json',fixtures),('live.json',live)]:
            atomic_write_json(folder/name,value)
    return publish(output_dir, metadata, writer)


def settlement_outcomes(bootstrap, fixtures, live, m, prediction):
    p = prediction['metadata']
    if m['contract'] != SETTLEMENT_CONTRACT or m['prediction_identity'] != prediction['identity_sha256'] or any(m[k] != p[k] for k in ('season','target_gameweek','deadline')):
        raise ValueError('settlement/forecast contract mismatch')
    check_season(m['season'], bootstrap)
    event = event_for(bootstrap, m['target_gameweek'])
    if event['deadline_time'] != p['deadline'] or event.get('finished') is not True or event.get('data_checked') is not True:
        raise ValueError('target event not authoritatively settled')
    timings = m['request_timing']
    last = p['deadline']
    for name in ('bootstrap','fixtures','live'):
        t = timings[name]
        if not before(last, t['requested_at']) and not (name != 'bootstrap' and not_after(last, t['requested_at'])):
            raise ValueError('settlement request timing invalid')
        if not not_after(t['requested_at'], t['received_at']):
            raise ValueError('settlement clock reversed')
        last = t['received_at']
    if last != m['received_at']:
        raise ValueError('settlement completion mismatch')
    target_fixtures = fixture_validation(fixtures, bootstrap, m['target_gameweek'], False)
    fixture_ids = {f['id'] for f in target_fixtures}
    records = {}
    for e in live['elements']:
        element = e['id']
        if type(element) is not int or element in records:
            raise ValueError('duplicate live element')
        minutes = integer(e['stats'].get('minutes'), 'live minutes')
        points = e['stats'].get('total_points')
        if minutes is None or type(points) is not int:
            raise ValueError('missing explicit settled minutes/points')
        explained_minutes, explained_points, seen = 0, 0, set()
        for entry in e['explain']:
            if entry['fixture'] not in fixture_ids or entry['fixture'] in seen:
                raise ValueError('invalid target fixture explanation')
            seen.add(entry['fixture'])
            stats = entry['stats']
            minute_items = [s for s in stats if s['identifier'] == 'minutes']
            # Zero-minute players can have an empty explanation.
            if len(minute_items) > 1:
                raise ValueError('ambiguous explained minutes')
            if minute_items:
                v = integer(minute_items[0].get('value'), 'explained minutes')
                if v is None:
                    raise ValueError('missing explained minutes')
                explained_minutes += v
            if any(type(s.get('points')) is not int for s in stats):
                raise ValueError('invalid explained points')
            explained_points += sum(s['points'] for s in stats)
        if (minutes, points) != (explained_minutes, explained_points):
            raise ValueError('live stats disagree with fixture explanation')
        records[element] = {'season': m['season'], 'target_gameweek': m['target_gameweek'], 'element': element,
                            'target_minutes': minutes if fixture_ids else None, 'target_points': points if fixture_ids else None}
    if not records:
        raise ValueError('empty live population')
    return records


def load_settlement(folder, prediction):
    manifest = verify_bundle(folder, 'prospective-settlement')
    raw = [json.loads((Path(folder)/n).read_text()) for n in ('bootstrap.json','fixtures.json','live.json')]
    records = settlement_outcomes(*raw, manifest['metadata'], prediction)
    return list(records.values()), manifest


def score_predictions(prediction_dir, settlement_dir, output_dir=Path('data/prospective_scores')):
    from fpl_ai.minutes import metrics
    safe_output(output_dir, prediction_dir, settlement_dir)
    prediction = verify_prediction(prediction_dir)
    outcomes, settlement = load_settlement(settlement_dir, prediction)
    lookup = {r['element']: r for r in outcomes}
    preds = read_csv(Path(prediction_dir)/'predictions.csv')
    rows, forecasts = [], []
    for r in preds:
        element = int(r['element'])
        if element not in lookup:
            raise ValueError('settlement lacks explicit predicted player outcome')
        rows.append(lookup[element])
        forecasts.append({n: float(r[n]) if r[n] else None for n in ('expected_minutes','expected_points')})
    scores = {'expected_minutes': metrics(rows, forecasts, 'expected_minutes')}
    points_rows = [dict(r, target_minutes=r['target_points']) for r in rows]
    scores['expected_points'] = metrics(points_rows, forecasts, 'expected_points')
    def writer(folder):
        atomic_write_csv(folder/'outcomes.csv', rows, list(KEYS)+['target_minutes','target_points'])
        atomic_write_json(folder/'scores.json', scores)
    return publish(output_dir, {'kind': 'prospective-score', 'contract': SETTLEMENT_CONTRACT,
                               'prediction_identity': prediction['identity_sha256'], 'settlement_identity': settlement['identity_sha256'],
                               'prediction_manifest_sha256': sha256_file(Path(prediction_dir)/'manifest.json'),
                               'settlement_manifest_sha256': sha256_file(Path(settlement_dir)/'manifest.json')}, writer)
