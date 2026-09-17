"""Versioned, deliberately closed feature/target/evaluation contract."""

SPLITS = {
    '2021-22': 'train', '2022-23': 'train', '2023-24': 'train',
    '2024-25': 'validation', '2025-26': 'test',
}
STATE_FIELDS = {
    'deadline_team_id': 'integer', 'deadline_position_id': 'integer',
    'price': 'integer', 'selected_by_percent': 'number',
    'transfers_in_event': 'integer', 'transfers_out_event': 'integer',
    'status': 'string', 'chance_of_playing_next_round': 'integer',
}
HISTORY_FIELDS = {
    'previous_points': 'number', 'points_mean_3': 'number',
    'points_mean_5': 'number', 'points_count_3': 'integer',
    'points_count_5': 'integer', 'season_points_mean': 'number',
    'season_points_count': 'integer',
}
FEATURE_TYPES = {**STATE_FIELDS, **HISTORY_FIELDS}
NULLABLE_FEATURES = tuple(STATE_FIELDS) + (
    'previous_points', 'points_mean_3', 'points_mean_5', 'season_points_mean',
)
FEATURE_TYPES.update({f'{name}_missing': 'integer' for name in NULLABLE_FEATURES})
FEATURES = tuple(FEATURE_TYPES)
KEYS = ('season', 'target_gameweek', 'element')
CONTRACT = {
    'feature_version': 'deadline-points-v1', 'target_version': 'player-gw-points-v1',
    'split_version': 'five-season-chronological-v1', 'evaluation_version': 'baselines-v1',
    'splits': SPLITS,
    'grain': list(KEYS), 'identity': 'season-local; never join on person code',
    'target_type': 'nullable integer; unmultiplied player points, no captain/chip effects',
    'horizon': 'one upcoming target Gameweek',
    'target': 'sum of canonical fixture total_points in target GW; all fixtures in doubles',
    'population': 'accepted snapshot position IDs 1..4, including non-playing registered players',
    'empty_sum': 'zero for a snapshot player without facts in a fixture-bearing GW',
    'fixture_empty_gameweek': 'retain features and predictions; null label, excluded from fitting/scoring/history',
    'as_of': 'accepted snapshot capture (not the later deadline)',
    'history': 'strictly earlier GW; points independently observed settled by capture; season-local',
    'windows': 'previous 3/5 calendar GWs; mean of available values; counts explicit; no zero imputation',
    'history_no_facts': 'zero only when settled archive event_points explicitly equals zero; otherwise missing',
    'baseline_fit': 'only train labels settled by prediction capture; frozen for validation and test',
    'fallback': 'recent mean3 or player season mean (minimum 3) -> train position mean -> train overall -> 0',
    'external_benchmark': 'archived FPL ep_next, separate from features; missing remains missing',
    'ranking': 'mean within-season/GW Spearman using average ties; constant groups undefined and counted',
    'features': {name: {'type': typ, 'nullable': name in NULLABLE_FEATURES}
                 for name, typ in FEATURE_TYPES.items()},
}


def split_for(season):
    if season not in SPLITS:
        raise ValueError(f'no chronological split for {season}')
    return SPLITS[season]

FEATURE_DEFINITIONS = {
    **{name: f"Copied only from accepted player_deadline_snapshots.{name}" for name in STATE_FIELDS},
    'previous_points': 'Settled points in G-1, null if unavailable',
    'points_mean_3': 'Mean of available settled points in G-3..G-1',
    'points_mean_5': 'Mean of available settled points in G-5..G-1',
    'points_count_3': 'Number of available values in G-3..G-1',
    'points_count_5': 'Number of available values in G-5..G-1',
    'season_points_mean': 'Mean of available settled points in GWs 1..G-1',
    'season_points_count': 'Number of available values in GWs 1..G-1',
    **{f'{name}_missing': f'1 when {name} is null, otherwise 0' for name in NULLABLE_FEATURES},
}
for _name, _definition in FEATURE_DEFINITIONS.items():
    CONTRACT['features'][_name]['definition'] = _definition
