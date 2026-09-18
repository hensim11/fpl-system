"""Annual expanding-window minutes backtests with a fail-closed downstream reader."""
import hashlib
import json
import math
import pickle
from pathlib import Path

from fpl_ai.experiment_io import digest, publish, verify_bundle
from fpl_ai.experiments import environment
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json, sha256_file
from fpl_ai.historical_transform import parse_utc
from fpl_ai.minutes import (PROTOCOL as DEVELOPMENT, NAMES, evaluate, fit_training,
                            load_frozen, load_rows, predict)
from fpl_ai.modelling import read_csv
from fpl_ai.playing_time import (CONTRACT, FEATURES, KEYS, SEASONS, _inspect_season,
                                 construct_rows)

ALL_SEASONS = SEASONS + ('2024-25', '2025-26')
EXCEPTION = {
    'version': 'ferguson-unresolved-minutes-v1', 'season': '2024-25', 'element': 123,
    'gameweek': 27,
    'source_identity': 'd94912c4423cd0f7ffb8b1fbaf4ff4493450f772af7d1258f9cfe5bea5a89f69',
    'before_sha256': '76a4a39d6b9b8364085e80043bf21dbbac642a080c45af99a0f71e1924bf4511',
    'after_sha256': '5bfe4a25cba3a035cc7d9990433bd29adeae07092b3ef05e37320fc7a8d547c1',
    'known_at': '2025-03-08T06:25:00Z',
    'policy': 'GW27 label unavailable; never history or fitting. Mask cumulative minutes for this player from the first evidenced discrepancy through season end; retain independently reconciled later GW deltas. No numeric correction.',
}
PROTOCOL = {
    'version': 'chronological-minutes-oos-v1', 'prediction_class': 'chronological_oos',
    'feature_contract': CONTRACT, 'exception': EXCEPTION,
    'selection': 'Reuse only M4B bounded candidate selection: fit 2021-22/2022-23, validate 2023-24. No reselection, tuning or prospective outcomes.',
    'first_supported_season': '2024-25', 'forecast_seasons': ['2024-25', '2025-26'],
    'refit': 'Once before first accepted capture of each forecast season; expand from 2021-22 through preceding season; all nonnull evidenced labels; no within-season refit.',
    'cutoffs': 'Every fitting label, fitting feature capture, selection label and selection feature capture strictly precedes first forecast capture; all row captures precede their deadlines.',
    'early_rows': '2021-22 through 2023-24 unavailable, never retroactively OOS',
    'candidate': DEVELOPMENT['candidate'], 'preprocessing': DEVELOPMENT['preprocessing'],
    'baselines': DEVELOPMENT['baselines'], 'prediction_transform': DEVELOPMENT['prediction_transform'],
    'evaluation_role': 'historical walk-forward backtest; 2025-26 is a consumed points holdout, not fresh confirmation',
    'diagnostic_groups': ['status_available', 'status_other', 'status_missing', 'chance_known', 'cumulative_minutes_missing'],
    'historical_clock': 'reconstructed information cutoffs, not actual historical computation timestamps or prospective freezes',
}
PRED_COLUMNS = KEYS + ('prediction_class', 'prediction_capture', 'expected_minutes',
    'downstream_training_allowed', 'unavailable_reason', 'fold', 'model_identity',
    'feature_identity', 'protocol_identity', 'training_cutoff', 'selection_cutoff',
    'source_identity', 'freshness_exception', 'evidence_exception')


def earlier(a, b):
    return parse_utc(a, 'evidence time') < parse_utc(b, 'prediction time')


def evidence_policy(rows, by_gw, targets, evidence, fixture_gws, audit, source):
    """Quarantine one exact disagreement; never turn arbitrary failures into nulls."""
    unavailable = frozenset()
    if audit['season'] == EXCEPTION['season']:
        expected = [{'gameweek': 27, 'element': 123,
                     'reason': 'minutes target disagrees with independent evidence: GW27: 34 != 17'}]
        cumulative = audit['cumulative_disagreements']
        if (source['source_identity_sha256'] != EXCEPTION['source_identity'] or
                audit['captures']['27']['sha256'] != EXCEPTION['before_sha256'] or
                audit['settlements']['27']['sha256'] != EXCEPTION['after_sha256'] or
                audit['settlements']['27']['capture_time_utc'] != EXCEPTION['known_at'] or
                audit['minutes_target_disagreements'] != expected or
                len(cumulative) != 12 or
                {r['gameweek'] for r in cumulative} != set(range(27, 39)) or
                any(r['element'] != 123 or r['observed']-r['canonical'] != 17 for r in cumulative)):
            raise ValueError('unrecognized minutes discrepancy; exception cannot weaken validation')
        unavailable = frozenset({(27, 123)})
    elif audit['minutes_target_disagreements'] or audit['cumulative_disagreements']:
        raise ValueError('unresolved minutes evidence outside exact exception')
    if unavailable.intersection(targets):
        raise ValueError('unresolved target must never become numeric')
    result = construct_rows(rows, by_gw, targets, evidence, fixture_gws, unavailable=unavailable)
    for r in result:
        r['evidence_exception'] = ''
        if audit['season'] == EXCEPTION['season'] and r['element'] == 123:
            if r['target_gameweek'] == 27:
                r['label_available_at'] = None
            if not earlier(r['audit']['capture_time_utc'], EXCEPTION['known_at']):
                r['features']['observed_season_minutes'] = None
                r['features']['observed_season_minutes_missing'] = 1
                r['evidence_exception'] = EXCEPTION['version']
    return result


def collect_rows(data_dir, builds=None):
    if builds is None:
        cat = json.loads((Path(data_dir)/'historical/catalogue.json').read_text())
        builds = {s:cat['seasons'][s]['latest_successful_version'] for s in ALL_SEASONS}
    if set(builds) != set(ALL_SEASONS):
        raise ValueError('exact five-season evidence required')
    rows, audits, sources = [], {}, {}
    for season in ALL_SEASONS:
        batch, audits[season], sources[season] = _inspect_season(
            season, builds[season], Path(data_dir), evidence_policy=evidence_policy)
        rows.extend(batch)
    return rows, audits, sources


def selection_evidence(feature_dir, model_dir):
    rows = load_rows(feature_dir)
    _, frozen, manifest = load_frozen(model_dir)
    fm = verify_bundle(feature_dir, 'playing-time-features')
    if frozen['features_identity'] != fm['identity_sha256'] or frozen['features_manifest_sha256'] != sha256_file(Path(feature_dir)/'manifest.json'):
        raise ValueError('selection feature/model mismatch')
    if any(r['target_minutes'] is None for r in rows if r['season'] == '2023-24'):
        raise ValueError('selection labels incomplete')
    cutoff = max(r['label_available_at'] for r in rows if r['target_minutes'] is not None)
    if any(not earlier(r['audit']['capture_time_utc'], cutoff) for r in rows):
        raise ValueError('selection capture after evidence cutoff')
    return {'cutoff': cutoff, 'selected': frozen['selected'], 'model_manifest': manifest,
            'features_manifest': fm, 'population_sha256': digest(rows),
            'role': 'M4B development only; earliest information-complete selection cutoff, not a historical execution timestamp'}


def partition(rows, season, selection):
    forecast = [r for r in rows if r['season'] == season]
    if season not in PROTOCOL['forecast_seasons'] or not forecast:
        raise ValueError('unsupported OOS forecast period')
    first = min(r['audit']['capture_time_utc'] for r in forecast)
    if not earlier(selection['cutoff'], first):
        raise ValueError('selection evidence reaches prediction capture')
    train = [r for r in rows if r['season'] < season and r['target_minutes'] is not None]
    expected = set(ALL_SEASONS[:ALL_SEASONS.index(season)])
    if {r['season'] for r in train} != expected:
        raise ValueError('expanding fitting history incomplete')
    if any(not r['label_available_at'] or not earlier(r['label_available_at'], first) or
           not earlier(r['audit']['capture_time_utc'], first) for r in train):
        raise ValueError('training evidence reaches prediction capture')
    return train, forecast, first


def build_oos(feature_dir, model_dir, data_dir=Path('data'), output_dir=Path('data/minutes_oos'), *, builds=None):
    selection = selection_evidence(feature_dir, model_dir)
    rows, audits, sources = collect_rows(data_dir, builds)
    feature_identity = digest({'contract': CONTRACT, 'exception': EXCEPTION,
                               'sources': sources, 'rows': [{**{k:r[k] for k in KEYS}, 'features':r['features'],
                                   'audit':r['audit'], 'evidence_exception':r['evidence_exception']} for r in rows]})
    folds, states, forecasts, evaluations = {}, {}, {}, {}
    training = []
    for season in PROTOCOL['forecast_seasons']:
        train, target, first = partition(rows, season, selection)
        model, state = fit_training(train, first)
        state.update(selected=selection['selected'], selection_cutoff=selection['cutoff'],
                     training_seasons=sorted({r['season'] for r in train}),
                     training_population_sha256=digest(train), first_prediction_capture=first)
        model_bytes = pickle.dumps(model, protocol=5)
        state['model_identity'] = digest({'state': state, 'pickle_sha256': hashlib.sha256(model_bytes).hexdigest(),
                                          'protocol': PROTOCOL, 'environment': environment()})
        folds[season], states[season] = state, model_bytes
        preds = predict(target, model, state)
        forecasts.update({tuple(p[k] for k in KEYS):p[selection['selected']] for p in preds})
        segments = evaluate(target, preds)
        groups = {'status_available':lambda r:r['features']['status']=='a',
                  'status_other':lambda r:r['features']['status'] not in ('a',None),
                  'status_missing':lambda r:r['features']['status'] is None,
                  'chance_known':lambda r:r['features']['chance'] is not None,
                  'cumulative_minutes_missing':lambda r:r['features']['observed_season_minutes'] is None}
        for name, accept in groups.items():
            pairs = [(r,p) for r,p in zip(target,preds) if accept(r)]
            a,b = zip(*pairs) if pairs else ([],[])
            segments[name] = evaluate(a,b)['all']
        evaluations[season] = {'segments': segments,
                              'gameweeks': {str(g): evaluate([r for r in target if r['target_gameweek']==g],
                                                            [p for p in preds if p['target_gameweek']==g])['all'] for g in range(1,39)}}
        training.extend({'fold': season, **{k:r[k] for k in KEYS},
                         'capture': r['audit']['capture_time_utc'], 'label_available_at': r['label_available_at'],
                         'row_sha256': digest(r)} for r in train)
    predictions = []
    for r in rows:
        s = r['season']; state = folds.get(s); supported = state is not None
        capture = r['audit']['capture_time_utc']
        if not earlier(capture, r['audit']['deadline_time_utc']):
            raise ValueError('prediction source reached deadline')
        predictions.append({**{k:r[k] for k in KEYS},
            'prediction_class': 'chronological_oos' if supported else 'unavailable',
            'prediction_capture': capture, 'expected_minutes': forecasts.get(tuple(r[k] for k in KEYS)),
            'downstream_training_allowed': supported,
            'unavailable_reason': '' if supported else 'insufficient_prior_selection_history',
            'fold': s if supported else '', 'model_identity': state['model_identity'] if supported else '',
            'feature_identity': feature_identity, 'protocol_identity': digest(PROTOCOL),
            'training_cutoff': state['latest_training_settlement'] if supported else '',
            'selection_cutoff': selection['cutoff'], 'source_identity': sources[s]['source_identity_sha256'],
            'freshness_exception': r['audit'].get('superseded_deadline_exception', False),
            'evidence_exception': r['evidence_exception']})
    def writer(folder):
        atomic_write_json(folder/'protocol.json', PROTOCOL)
        atomic_write_json(folder/'sources.json', {'historical': sources, 'evidence': audits, 'selection': selection})
        atomic_write_json(folder/'folds.json', folds)
        for season, content in states.items():
            (folder/f'model_{season}.pickle').write_bytes(content)
        atomic_write_csv(folder/'predictions.csv', predictions, list(PRED_COLUMNS))
        atomic_write_csv(folder/'features.csv', ({**{k:r[k] for k in KEYS}, **r['features']} for r in rows), list(KEYS+FEATURES))
        atomic_write_csv(folder/'row_audit.csv', ({**{k:r[k] for k in KEYS}, **r['audit']} for r in rows), list(KEYS)+list(rows[0]['audit']))
        atomic_write_csv(folder/'training.csv', training, list(training[0]))
    out, reused = publish(output_dir, {'kind':'minutes-oos', 'protocol':PROTOCOL,
                          'feature_identity':feature_identity, 'environment':environment()}, writer)
    verify_oos(out)
    def score_writer(folder):
        atomic_write_json(folder/'metrics.json', evaluations)
        atomic_write_csv(folder/'outcomes.csv', ({**{k:r[k] for k in KEYS}, 'target_minutes':r['target_minutes'],
            'label_available_at':r['label_available_at'],
            'unavailable_reason': 'unresolved_cumulative_discrepancy' if (r['season'],r['target_gameweek'],r['element'])==('2024-25',27,123)
            else ('schedule_supported_blank' if r['target_minutes'] is None else '')}
            for r in rows if r['season'] in folds), list(KEYS)+['target_minutes','label_available_at','unavailable_reason'])
    scored, score_reused = publish(Path(output_dir)/'scores', {'kind':'minutes-oos-score', 'protocol':PROTOCOL,
        'prediction_identity':out.name, 'prediction_manifest_sha256':sha256_file(out/'manifest.json'),
        'evaluation_role':PROTOCOL['evaluation_role']}, score_writer)
    return out, reused, scored, score_reused


def verify_oos(folder):
    """Reject development bundles and rederive eligibility; never trust a CSV flag."""
    folder = Path(folder)
    manifest = verify_bundle(folder, 'minutes-oos')
    if manifest['metadata']['protocol'] != PROTOCOL or json.loads((folder/'protocol.json').read_text()) != PROTOCOL:
        raise ValueError('OOS protocol mismatch')
    folds = json.loads((folder/'folds.json').read_text())
    sources = json.loads((folder/'sources.json').read_text())
    selection = sources['selection']
    if set(folds) != set(PROTOCOL['forecast_seasons']) or selection['selected'] not in NAMES:
        raise ValueError('invalid OOS fold/selection set')
    for name, kind in (('model_manifest','minutes-freeze'), ('features_manifest','playing-time-features')):
        m = selection[name]
        if m['metadata']['kind'] != kind or digest({k:v for k,v in m.items() if k!='identity_sha256'}) != m['identity_sha256']:
            raise ValueError('invalid selection source identity')
    if (selection['model_manifest']['metadata']['protocol'] != DEVELOPMENT or
            selection['features_manifest']['metadata']['contract'] != CONTRACT):
        raise ValueError('selection must use frozen M4B development contract')
    # Selection cutoff is derived from independently pinned prior settlement evidence.
    derived_cutoff = max(r['capture_time_utc'] for s in SEASONS
                         for r in sources['evidence'][s]['settlements'].values())
    if selection['cutoff'] != derived_cutoff:
        raise ValueError('selection cutoff differs from source evidence')
    train = read_csv(folder/'training.csv')
    if any(r['fold'] not in folds for r in train):
        raise ValueError('unknown training fold')
    for season, state in folds.items():
        identity_state = {k:v for k,v in state.items() if k!='model_identity'}
        if digest({'state':identity_state, 'pickle_sha256':sha256_file(folder/f'model_{season}.pickle'),
                   'protocol':PROTOCOL, 'environment':manifest['metadata']['environment']}) != state['model_identity']:
            raise ValueError('OOS fitted model identity mismatch')
        pop = [r for r in train if r['fold']==season]
        keys = [(r['season'], int(r['target_gameweek']), int(r['element'])) for r in pop]
        if (not pop or len(set(keys)) != len(keys) or len(pop) != state['training_rows'] or
                digest([list(k) for k in keys]) != state['training_keys_sha256'] or
                max(r['label_available_at'] for r in pop) != state['latest_training_settlement'] or
                sorted({r['season'] for r in pop}) != list(ALL_SEASONS[:ALL_SEASONS.index(season)]) or
                state['selection_cutoff'] != selection['cutoff'] or state['selected'] != selection['selected']):
            raise ValueError('invalid OOS fitting population')
        for r in pop:
            if not earlier(r['capture'], state['first_prediction_capture']) or not earlier(r['label_available_at'], state['first_prediction_capture']):
                raise ValueError('OOS training boundary violated')
        if not earlier(selection['cutoff'], state['first_prediction_capture']):
            raise ValueError('OOS selection boundary violated')
    tables = {name:read_csv(folder/name) for name in ('predictions.csv','features.csv','row_audit.csv')}
    def key(r): return tuple(r[k] for k in KEYS)
    keys = [key(r) for r in tables['predictions.csv']]
    if not keys or len(keys)!=len(set(keys)) or any([key(r) for r in table]!=keys for table in tables.values()):
        raise ValueError('OOS populations mismatch')
    firsts = {}
    for feature in tables['features.csv']:
        if set(feature) != set(KEYS+FEATURES):
            raise ValueError('OOS feature allowlist mismatch')
        if feature['season']=='2024-25' and feature['element']=='123':
            gw = int(feature['target_gameweek'])
            if (gw>=28 and feature['observed_season_minutes']!='') or (gw==28 and feature['previous_minutes']!=''):
                raise ValueError('unresolved minutes evidence entered OOS features')
        for field in CONTRACT['features']:
            if field.endswith('_missing') and feature[field] != str(int(feature[field.removesuffix('_missing')]=='')):
                raise ValueError('OOS feature missingness mismatch')
    for r, audit in zip(tables['predictions.csv'], tables['row_audit.csv']):
        if set(r) != set(PRED_COLUMNS) or r['season'] not in ALL_SEASONS:
            raise ValueError('OOS closed prediction columns/season mismatch')
        s = r['season']; supported = s in folds
        if (r['downstream_training_allowed'] != str(supported) or
                r['prediction_class'] != ('chronological_oos' if supported else 'unavailable') or
                r['feature_identity'] != manifest['metadata']['feature_identity'] or
                r['protocol_identity'] != digest(PROTOCOL) or
                r['source_identity'] != sources['historical'][s]['source_identity_sha256'] or
                r['prediction_capture'] != audit['capture_time_utc'] or
                r['freshness_exception'] != str(audit.get('superseded_deadline_exception', False)) or
                r['evidence_exception'] != (EXCEPTION['version'] if s=='2024-25' and r['element']=='123' and
                    not earlier(r['prediction_capture'],EXCEPTION['known_at']) else '') or
                not earlier(r['prediction_capture'], audit['deadline_time_utc']) or
                r['selection_cutoff'] != selection['cutoff']):
            raise ValueError('OOS eligibility/provenance mismatch')
        if supported:
            f = folds[s]; value = float(r['expected_minutes'])
            firsts[s] = min(firsts.get(s,r['prediction_capture']),r['prediction_capture'])
            if (not math.isfinite(value) or value<0 or r['unavailable_reason'] or r['fold']!=s or
                    r['model_identity']!=f['model_identity'] or r['training_cutoff']!=f['latest_training_settlement'] or
                    not earlier(r['training_cutoff'],r['prediction_capture']) or not earlier(r['selection_cutoff'],r['prediction_capture'])):
                raise ValueError('unsafe chronological prediction')
        elif (r['expected_minutes'] or r['fold'] or r['model_identity'] or r['training_cutoff'] or
              r['unavailable_reason']!='insufficient_prior_selection_history'):
            raise ValueError('development predictions cannot masquerade as OOS')
    if any(firsts.get(s)!=f['first_prediction_capture'] for s,f in folds.items()):
        raise ValueError('OOS refit boundary mismatch')
    return manifest


def load_downstream(folder):
    """Only this versioned family is admitted; no outcome columns are returned."""
    verify_oos(folder)
    return [r for r in read_csv(Path(folder)/'predictions.csv') if r['downstream_training_allowed']=='True']
