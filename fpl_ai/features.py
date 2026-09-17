"""Pure feature construction. Labels and benchmark never enter feature projection."""
import math
from collections import defaultdict
from statistics import mean

from fpl_ai.modelling_contract import (
    FEATURES, STATE_FIELDS, NULLABLE_FEATURES, split_for,
)
from fpl_ai.historical_transform import parse_utc


def number(value, kind='number'):
    if value is None or value == '':
        return None
    if kind == 'string':
        return value
    result = int(value) if kind == 'integer' else float(value)
    if not math.isfinite(result):
        raise ValueError('non-finite modelling input')
    return result


def build_rows(season, snapshots, facts, settlements, exception=None):
    """settlements maps GW to {capture_time_utc, points: {element: int}}.

    Production adapter verifies these against the accepted M2 reconciliation
    sources. No final identity or fixture context is projected into features.
    """
    totals = defaultdict(int)
    fact_keys = set()
    fixture_gws = set()
    for fact in facts:
        if fact['season'] != season:
            raise ValueError('mixed fact seasons')
        if fact['position_at_fixture'] == 'AM':
            continue
        key = (int(fact['gameweek']), int(fact['element']))
        fk = (int(fact['element']), int(fact['fixture']))
        if fk in fact_keys:
            raise ValueError('duplicate fixture fact')
        fact_keys.add(fk)
        fixture_gws.add(key[0])
        totals[key] += int(fact['total_points'])
    settlement_times = {gw: parse_utc(e['capture_time_utc'], 'settlement') for gw, e in settlements.items()}
    seen = set()
    rows = []
    for snap in sorted(snapshots, key=lambda r: (int(r['gameweek']), int(r['element']))):
        if snap['season'] != season:
            raise ValueError('mixed snapshot seasons')
        position = number(snap['deadline_position_id'], 'integer')
        if position == 5 or snap['deadline_position'] == 'AM':
            continue
        if position not in (1, 2, 3, 4):
            raise ValueError('unknown deadline football position')
        gw, element = int(snap['gameweek']), int(snap['element'])
        if (gw, element) in seen:
            raise ValueError('duplicate snapshot key')
        seen.add((gw, element))
        capture, deadline = snap['capture_time_utc'], snap['deadline_time_utc']
        asof = parse_utc(capture, 'capture')
        end = parse_utc(deadline, 'deadline')
        if asof >= end:
            raise ValueError('capture must precede deadline')
        history = {}
        for past in range(1, gw):
            evidence = settlements.get(past)
            if past not in fixture_gws or evidence is None:
                continue
            if settlement_times[past] > asof:
                continue
            observed = evidence['points'].get(element)
            if observed is None:
                continue
            expected = totals.get((past, element), 0)
            if observed != expected:
                raise ValueError(f'settled points disagree: {season}/{past}/{element}')
            history[past] = observed
        features = {name: number(snap[name], kind) for name, kind in STATE_FIELDS.items()}
        features['previous_points'] = history.get(gw - 1)
        for window in (3, 5):
            values = [history[p] for p in range(max(1, gw-window), gw) if p in history]
            features[f'points_mean_{window}'] = mean(values) if values else None
            features[f'points_count_{window}'] = len(values)
        features['season_points_mean'] = mean(history.values()) if history else None
        features['season_points_count'] = len(history)
        features.update({f'{name}_missing': int(features[name] is None) for name in NULLABLE_FEATURES})
        if set(features) != set(FEATURES):
            raise ValueError('feature allowlist violated')
        label = totals.get((gw, element), 0) if gw in fixture_gws else None
        settlement = settlements.get(gw)
        if label is not None:
            target_key = f'{season}/{gw}/{element}'
            if settlement is None:
                raise ValueError(f'target has no settlement evidence: {target_key}')
            observed = settlement['points'].get(element)
            if type(observed) is not int:
                raise ValueError(f'target lacks integer settlement event_points: {target_key}')
            if observed != label:
                raise ValueError(f'target disagrees with settlement: {target_key}: {label} != {observed}')
        is_exception = bool(exception and gw == exception['gameweek'])
        rows.append({
            'season': season, 'target_gameweek': gw, 'element': element,
            'split': split_for(season), 'features': features,
            'target_points': label,
            'label_available_at': settlement['capture_time_utc'] if label is not None else None,
            'external_ep_next': number(snap['expected_points_next_gameweek']),
            'audit': {
                'capture_time_utc': capture, 'deadline_time_utc': deadline,
                'snapshot_age_minutes': (end-asof).total_seconds()/60,
                'snapshot_source_path': snap['source_path'], 'snapshot_sha256': snap['source_sha256'],
                'observed_player_code': snap['player_code'],
                'superseded_deadline_exception': is_exception,
                'payload_deadline_utc': exception['payload_deadline_utc'] if is_exception else deadline,
                'label_status': 'observed_fixture_sum' if (gw, element) in totals else
                                ('empty_player_sum' if label is not None else 'fixture_empty_gameweek'),
            },
        })
    return rows
