"""Read-only evidence audits, separate from immutable transformation identities."""

import json
import lzma
from collections import Counter, defaultdict

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import sha256_file
from fpl_ai.historical_pipeline import _capture_from_path, _extract_deadlines, _valid_snapshot
from fpl_ai.historical_schema import get_vaastav_source_schema, schemas_as_dict
from fpl_ai.historical_snapshot_policy import accept_superseded_snapshot
from fpl_ai.historical_transform import parse_utc, transform_snapshot_elements


def require(condition, message):
    if not condition:
        raise FPLValidationError(f"cross-season audit: {message}")


def csv_value(value):
    return '' if value is None else str(value)


def audit_season(season, tables, raw_dir, inventory, config, quality):
    """Recheck selected raw evidence, then describe availability without features."""
    records = {r['source_path']: r for r in inventory['files']}
    cache = config['sources']['fplcache']
    payloads = {}

    def payload(path):
        require(path in records, f'{season}: source absent from frozen inventory: {path}')
        record = records[path]
        file = raw_dir / record['raw_path']
        require(sha256_file(file) == record['sha256'], f'{season}: source checksum: {path}')
        if path not in payloads:
            payloads[path] = json.loads(lzma.decompress(file.read_bytes()))
        return payloads[path]

    deadlines = _extract_deadlines(payload(cache['reference_snapshot_path']), config['expected_gameweeks'], 'reference')
    snapshots = defaultdict(list)
    for row in tables['player_deadline_snapshots']:
        snapshots[int(row['gameweek'])].append(row)
    deadline_evidence, raw_field_counts, raw_field_types = [], Counter(), defaultdict(Counter)
    raw_nonnull_counts = Counter()
    raw_field_gameweeks = defaultdict(set)
    for row in tables['gameweeks']:
        gw = int(row['gameweek'])
        path = row['snapshot_source_path']
        capture = _capture_from_path(path, cache)
        deadline = deadlines[gw]
        require(parse_utc(row['deadline_time_utc'], 'deadline') == deadline, f'{season} GW{gw}: reference deadline')
        require(parse_utc(row['selected_snapshot_capture_time_utc'], 'capture') == capture, f'{season} GW{gw}: archive timestamp')
        data = payload(path)
        exception = config.get('superseded_deadline_exception')
        if exception and gw == exception['gameweek']:
            accept_superseded_snapshot(exception, season, gw, path, capture, deadline, data, records[path])
        else:
            require(_valid_snapshot(data, gw, deadline, capture), f'{season} GW{gw}: ineligible snapshot')
        expected = transform_snapshot_elements(season, gw, data, capture, deadline, path, records[path]['sha256'])
        require(sorted(snapshots[gw], key=lambda r: int(r['element'])) ==
                sorted(({k: csv_value(v) for k, v in r.items()} for r in expected), key=lambda r: int(r['element'])),
                f'{season} GW{gw}: deadline state differs from raw observation')
        for element in data['elements']:
            raw_field_counts.update(element.keys())
            for key, value in element.items():
                raw_field_types[key][type(value).__name__] += 1
                raw_field_gameweeks[key].add(gw)
                raw_nonnull_counts[key] += value is not None and value != '' and value != [] and value != {}
        event = next(e for e in data['events'] if e['id'] == gw)
        deadline_evidence.append({'gameweek': gw, 'source_path': path, 'sha256': records[path]['sha256'],
                                  'capture_time_utc': row['selected_snapshot_capture_time_utc'],
                                  'deadline_time_utc': row['deadline_time_utc'],
                                  'payload_deadline_utc': event['deadline_time'],
                                  'age_minutes': (deadline - capture).total_seconds() / 60,
                                  'superseded_deadline_exception': bool(exception and gw == exception['gameweek'])})

    fixture_counts = Counter(r['gameweek'] for r in tables['fixtures'])
    team_gw = Counter((r['gameweek'], team) for r in tables['fixtures'] for team in (r['home_team_id'], r['away_team_id']))
    settlement = []
    points = quality['total_points_reconciliation']
    for gw in sorted(map(int, fixture_counts)):
        if 'settlement_selection' in points:
            path = points['settlement_selection']['by_gameweek'][str(gw)]['source_path']
        elif gw == max(deadlines):
            path = cache['points_settlement_snapshot_path']
        else:
            path = next(r['snapshot_source_path'] for r in tables['gameweeks'] if int(r['gameweek']) == gw + 1)
        require('total_points_reconciliation' in records[path]['consumption_roles'], f'{season} GW{gw}: settlement inventory role')
        data = payload(path)
        events = [e for e in data['events'] if e['id'] == gw]
        require(len(events) == 1, f'{season} GW{gw}: ambiguous settlement event')
        event = events[0]
        require(event['finished'] is True and event['data_checked'] is True, f'{season} GW{gw}: unsettled event')
        require(parse_utc(event['deadline_time'], 'settlement deadline') == deadlines[gw], f'{season} GW{gw}: settlement deadline')
        capture = _capture_from_path(path, cache)
        last = max(parse_utc(r['kickoff_time_utc'], 'kickoff') for r in tables['fixtures'] if int(r['gameweek']) == gw)
        require(capture > last and capture > deadlines[gw], f'{season} GW{gw}: premature settlement capture')
        settlement.append({'gameweek': gw, 'source_path': path, 'sha256': records[path]['sha256'],
                           'capture_time_utc': capture.isoformat().replace('+00:00', 'Z'),
                           'hours_after_last_kickoff': (capture-last).total_seconds()/3600,
                           'finished': True, 'data_checked': True})

    final = {r['element']: r for r in tables['players']}
    teams, positions = defaultdict(set), defaultdict(set)
    changes = []
    for row in tables['player_deadline_snapshots']:
        teams[row['element']].add(row['deadline_team_id'])
        positions[row['element']].add(row['deadline_position'])
        if row['player_code'] != final[row['element']]['player_code']:
            changes.append({k: row[k] for k in ('element', 'gameweek', 'player_code', 'deadline_position', 'source_path')})
    schema = get_vaastav_source_schema(config['vaastav_source_schema']['schema_id'], season, 1)
    availability = {}
    for name, columns in schemas_as_dict().items():
        availability[name] = {c['name']: {'information_class': c['information_class'],
                                         'nonempty_rows': sum(r[c['name']] != '' for r in tables[name]),
                                         'row_count': len(tables[name])} for c in columns}
    return {
        'deadlines': deadline_evidence, 'settlement_timing': settlement,
        'all_deadline_rows_equal_raw_observations': True,
        'fixture_counts_by_gameweek': dict(sorted(fixture_counts.items(), key=lambda v: int(v[0]))),
        'team_fixture_totals': dict(sorted(Counter(t for r in tables['fixtures'] for t in (r['home_team_id'], r['away_team_id'])).items())),
        'team_blank_gameweeks': [{'gameweek': int(gw), 'team_id': t['team_id']} for gw in map(str, sorted(deadlines)) for t in tables['teams'] if not team_gw[gw, t['team_id']]],
        'team_double_gameweeks': [{'gameweek': int(gw), 'team_id': team, 'fixtures': count} for (gw, team), count in sorted(team_gw.items()) if count > 1],
        'deadline_team_changes': {k: sorted(v) for k, v in sorted(teams.items()) if len(v) > 1},
        'final_elements_absent_from_last_deadline': sorted(set(final) - {r['element'] for r in snapshots[max(deadlines)]}, key=int),
        'final_elements_never_observed': sorted(set(final) - set(teams), key=int),
        'within_season_position_changes': {k: sorted(v) for k, v in sorted(positions.items()) if len(v) > 1},
        'snapshot_final_code_differences': changes,
        'known_identity_exceptions': quality['known_identity_exceptions'],
        'source_duplicate_rows': quality['source_schema_changes']['merged_gw.csv'].get('exact_duplicate_rows'),
        'final_position_counts': dict(Counter(r['end_of_season_position'] for r in tables['players'])),
        'canonical_field_availability': availability,
        'source_field_policy': {name: {key: contract[key] for key in ('known_column_order', 'required_columns', 'optional_columns', 'ignored_columns', 'quarantined_columns', 'forbidden_columns')}
                                for name, contract in schema['files'].items()},
        'raw_snapshot_field_availability': {key: {'present_rows': count, 'nonempty_rows': raw_nonnull_counts[key], 'observed_json_types': dict(sorted(raw_field_types[key].items())), 'present_gameweeks': sorted(raw_field_gameweeks[key])} for key, count in sorted(raw_field_counts.items())},
    }


def audit_cross_season_identity(players_by_season):
    """Describe code links without treating season-local element or AM slot as a person."""
    codes, elements = defaultdict(list), defaultdict(set)
    duplicate_codes = []
    for season, players in sorted(players_by_season.items()):
        seen = Counter()
        require(len({r['element'] for r in players}) == len(players), f'{season}: duplicate element')
        for row in players:
            if row['end_of_season_position'] == 'AM':
                continue
            seen[row['player_code']] += 1
            codes[row['player_code']].append({'season': season, 'element': row['element'], 'name': row['web_name'], 'position': row['end_of_season_position']})
            elements[row['element']].add(row['player_code'])
        duplicate_codes.extend({'season': season, 'player_code': c, 'count': n} for c, n in sorted(seen.items()) if n > 1)
    return {'identity_key': ['season', 'element'], 'assistant_manager_slots_excluded_from_person_links': True,
            'football_player_codes': len(codes), 'codes_in_multiple_seasons': sum(len({r['season'] for r in rows}) > 1 for rows in codes.values()),
            'element_ids_reused_for_different_codes': sum(len(v) > 1 for v in elements.values()),
            'duplicate_final_codes_within_season': duplicate_codes,
            'cross_season_position_changes': {code: rows for code, rows in sorted(codes.items()) if len({r['position'] for r in rows}) > 1}}
