"""Independent target-GW settlement and append-only M5C scoring evidence."""
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import numpy as np

from fpl_ai import multi_uncertainty as uncertainty
from fpl_ai import prospective as live
from fpl_ai.client import DEFAULT_BASE_URL, FPLClient
from fpl_ai.evaluation import spearman
from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.fpl_rules import integer, require
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_optimiser import load_json

CONTRACT = {
    'version': 'm5c-target-settlement-v1', 'settlement': live.SETTLEMENT_CONTRACT,
    'deadline': 'target deadline must match the original retained bootstrap event; revisions fail closed for explicit investigation',
    'identity': 'original projection manifest/bytes, as-of state, target GW, horizon and exact independently captured evidence',
    'missing': 'absent player evidence fails entire target; authoritative season-wide blank retains null outcomes',
}
SCORE_CONTRACT = {
    'version': 'm5c-prospective-scores-v1', 'calibration': uncertainty.CONTRACT,
    'duplicate_policy': 'deduplicate identical projection/target/settlement; reject competing settlement or uncertainty versions for one projection/target',
    'aggregate': 'row-weighted errors/coverage; rank correlations averaged within projection/target/horizon; distinct target GW counts separate',
    'cumulative': 'same projection, complete labelled offsets 0..length-1; no outcomes from another as-of state',
    'diagnostics_minimum': {'rows': 100, 'target_gameweeks': 5},
    'interpretation': 'descriptive prospective evidence; dependent players and overlapping forecasts are not independent samples; thresholds do not establish calibration quality',
}


def target_context(uncertainty_dir, manifest, gw):
    """Adapt only identity/event metadata to the existing shared settlement validator."""
    p = manifest['metadata']['state']
    integer(gw, 'target Gameweek', p['as_of_gameweek'], p['as_of_gameweek']+p['horizon']-1)
    archive = load_json(Path(uncertainty_dir)/'projection.json')
    source = uncertainty.mp.load_json_from_text(archive['files']['source.json'])
    evidence = uncertainty.mp.load_json_from_text(source['files']['evidence.json'])
    bootstrap = uncertainty.mp.load_json_from_text(evidence['snapshot']['files']['bootstrap.json'])
    deadline = live.event_for(bootstrap, gw)['deadline_time']
    require(live.before(p['computed_at'], deadline), 'projection after target deadline')
    return {'identity_sha256': manifest['metadata']['projection']['identity'],
            'metadata': {'season': p['season'], 'target_gameweek': gw, 'deadline': deadline}}


def settlement_metadata(context, uncertainty_manifest, timing):
    p = context['metadata']
    state = uncertainty_manifest['metadata']['state']
    return {'kind': 'multi-target-settlement', 'contract': CONTRACT,
            'projection': uncertainty_manifest['metadata']['projection'], 'state': state,
            'horizon': p['target_gameweek']-state['as_of_gameweek'], **p,
            'prediction_identity': context['identity_sha256'],
            'received_at': timing['live']['received_at'], 'request_timing': timing}


def outcomes_from_raw(raw, metadata, context, uncertainty_manifest, rows):
    expected = settlement_metadata(context, uncertainty_manifest, metadata['request_timing'])
    require(metadata == expected, 'target settlement identity/state mismatch')
    # Shared M4E/M4B authority: finished/data_checked, all fixtures finished,
    # full explicit live totals reconciled with per-fixture explanations.
    adapted = {**metadata, 'contract': live.SETTLEMENT_CONTRACT}
    outcomes = live.settlement_outcomes(*raw, adapted, context)
    require(live.before(uncertainty_manifest['metadata']['computed_at'], metadata['request_timing']['bootstrap']['requested_at']),
            'outcome captured before uncertainty publication')
    players = {r['element'] for r in rows if r['target_gameweek'] == metadata['target_gameweek']}
    require(players and players <= set(outcomes), 'settlement lacks explicit projected player outcome')
    return [outcomes[e] for e in sorted(players)]


def capture_settlement(uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, gameweek,
                       output_dir=Path('data/multi_uncertainty/settlements'), *, client=None, clock=live.now_utc, **sources):
    live.safe_output(output_dir, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, *sources.values())
    product, forecast = uncertainty.verify_uncertainty(uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
    context = target_context(uncertainty_dir, forecast, gameweek)
    # Reject before even requesting data when the original target deadline is ahead.
    require(live.before(context['metadata']['deadline'], live.stamp(clock)), 'target deadline has not passed')
    client = client or FPLClient()
    require(client.base_url == DEFAULT_BASE_URL, 'settlement requires official FPL endpoints')
    bootstrap, bt = live.timed_get(client.get_bootstrap, clock)
    fixtures, ft = live.timed_get(client.get_fixtures, clock)
    event_live, lt = live.timed_get(lambda: client.get_event_live(gameweek), clock)
    metadata = settlement_metadata(context, forecast, {'bootstrap': bt, 'fixtures': ft, 'live': lt})
    outcomes_from_raw((bootstrap, fixtures, event_live), metadata, context, forecast, product['rows'])
    def writer(folder):
        for name, value in [('bootstrap.json', bootstrap), ('fixtures.json', fixtures), ('live.json', event_live)]:
            atomic_write_json(folder/name, value)
    return publish(output_dir, metadata, writer)


def load_settlement(folder, uncertainty_dir, forecast, product):
    manifest = verify_bundle(folder, 'multi-target-settlement')
    context = target_context(uncertainty_dir, forecast, manifest['metadata']['target_gameweek'])
    raw = [load_json(Path(folder)/n) for n in ('bootstrap.json', 'fixtures.json', 'live.json')]
    outcomes = outcomes_from_raw(raw, manifest['metadata'], context, forecast, product['rows'])
    return outcomes, manifest


def distribution(values):
    return {'count': len(values), 'min': min(values) if values else None, 'max': max(values) if values else None,
            'mean': mean(values) if values else None,
            'quantiles_05_25_50_75_95': np.quantile(values, [.05, .25, .5, .75, .95]).tolist() if values else []}


def diagnostics(rows):
    pairs = [r for r in rows if r['outcome'] is not None and r['xpts'] is not None]
    groups = defaultdict(list)
    for r in pairs:
        groups[(r['projection_identity'], r['target_gameweek'], r.get('horizon', r.get('length')))].append(r)
    ranking = [spearman([r['outcome'] for r in rs], [r['xpts'] for r in rs]) for rs in groups.values()]
    defined = [r for r in ranking if r is not None]
    gw_count = len({(r['season'], r['target_gameweek']) for r in pairs})
    intervals = {}
    for level in uncertainty.LEVELS:
        interval_rows = [r for r in pairs if r['intervals'][str(level)]['lower'] is not None and
                         r['intervals'][str(level)]['upper'] is not None]
        qs = [r['intervals'][str(level)] for r in interval_rows]
        covered = sum(q['lower'] <= r['outcome'] <= q['upper'] for r, q in zip(interval_rows, qs))
        coverage = covered/len(qs) if qs else None
        nominal = level/100
        intervals[str(level)] = {'nominal': nominal, 'scored_rows': len(qs), 'covered_rows': covered,
                                 'missing_unscorable_rows': len(rows)-len(qs), 'coverage': coverage,
                                 'average_width': mean(q['upper']-q['lower'] for q in qs) if qs else None,
                                 'coverage_minus_nominal': coverage-nominal if qs else None,
                                 'undercoverage': max(0, nominal-coverage) if qs else None,
                                 'overcoverage': max(0, coverage-nominal) if qs else None}
    return {'population_rows': len(rows), 'scored_rows': len(pairs), 'missing_outcomes': sum(r['outcome'] is None for r in rows),
            'missing_predictions': sum(r['xpts'] is None for r in rows), 'coverage': len(pairs)/len(rows) if rows else None,
            'target_gameweeks_with_labels': gw_count, 'forecast_target_groups': len(groups),
            'mae': mean(abs(r['outcome']-r['xpts']) for r in pairs) if pairs else None,
            'rmse': math.sqrt(mean((r['outcome']-r['xpts'])**2 for r in pairs)) if pairs else None,
            'mean_within_gameweek_spearman': mean(defined) if defined else None,
            'ranking_defined_groups': len(defined), 'ranking_undefined_groups': len(ranking)-len(defined),
            'predictions': distribution([r['xpts'] for r in rows if r['xpts'] is not None]),
            'outcomes': distribution([r['outcome'] for r in rows if r['outcome'] is not None]),
            'small_sample': len(pairs) < 100 or gw_count < 5,
            'interpretation': SCORE_CONTRACT['interpretation'], 'intervals': intervals}


def report_rows(forecasts, settlements):
    """Pure keyed assembly; repeated pairs cannot increase the evidence count."""
    records, cumulative, pending = [], [], []
    canonical_outcomes = {}
    for identity, (product, forecast) in sorted(forecasts.items()):
        m = forecast['metadata']['state']
        indexed = {}
        for h in range(m['horizon']):
            selected = settlements.get((identity, m['as_of_gameweek']+h))
            if selected is None:
                pending.append({'projection_identity': identity, 'target_gameweek': m['as_of_gameweek']+h, 'horizon': h})
                continue
            outcomes, settlement = selected
            lookup = {r['element']: r for r in outcomes}
            for r in product['rows']:
                if r['horizon'] != h: continue
                value = lookup[r['element']]['target_points']
                k = (r['season'], r['target_gameweek'], r['element'])
                require(k not in canonical_outcomes or canonical_outcomes[k] == value, 'conflicting outcomes across projections')
                canonical_outcomes[k] = value
                record = {**r, 'projection_identity': identity, 'uncertainty_identity': forecast['identity_sha256'],
                          'settlement_identity': settlement['identity_sha256'], 'outcome': value}
                records.append(record)
                indexed[h, r['element']] = record
        for r in product['cumulative']:
            parts = [indexed.get((h, r['element'])) for h in range(r['length'])]
            reason = r['window_unavailable_reason'] or ('unsettled_target' if any(p is None for p in parts) else
                                                      'missing_outcome' if any(p['outcome'] is None for p in parts) else None)
            cumulative.append({**r, 'projection_identity': identity, 'uncertainty_identity': forecast['identity_sha256'],
                               'target_gameweek': r['as_of_gameweek']+r['length']-1,
                               'outcome': None if reason else sum(p['outcome'] for p in parts),
                               'unscorable_reason': reason,
                               'settlement_identities': [p['settlement_identity'] if p else None for p in parts]})
    report = {'contract': SCORE_CONTRACT, 'settled_target_gameweeks': len({(r['season'], r['target_gameweek']) for r in records}),
              'settled_projection_targets': len(settlements), 'projection_count': len(forecasts),
              'scored_player_rows': sum(r['outcome'] is not None for r in records), 'pending_targets': pending,
              'aggregate': diagnostics(records),
              'targets': {f'{identity}:{gw}': diagnostics([r for r in records if r['projection_identity'] == identity and r['target_gameweek'] == gw])
                          for identity, gw in sorted(settlements)},
              'horizons': {str(h): diagnostics([r for r in records if r['horizon'] == h]) for h in range(5)},
              'positions': {str(p): diagnostics([r for r in records if r['position'] == p]) for p in range(1, 5)},
              'horizon_positions': {f'{h}:{p}': diagnostics([r for r in records if r['horizon'] == h and r['position'] == p])
                                    for h in range(5) for p in range(1, 5)},
              'cumulative': {str(length): {**diagnostics([r for r in cumulative if r['length'] == length]),
                                                'unscorable_reasons': dict(Counter(r['unscorable_reason'] for r in cumulative
                                                                                  if r['length'] == length and r['unscorable_reason']))}
                             for length in (3, 5)}}
    return records, cumulative, report


def score(uncertainty_dirs, settlement_pairs, calibration_dir, model_dir, m4e_model_dir,
          output_dir=Path('data/multi_uncertainty/scores'), **sources):
    """Rebuild an immutable report over an explicit evidence set; calibration is read-only.

    settlement_pairs are (uncertainty_dir, settlement_dir). uncertainty_dirs also
    allows a zero-outcome report. Every input and raw target is reverified.
    """
    paths = sorted({Path(p) for p in uncertainty_dirs} | {Path(p) for p, _ in settlement_pairs})
    require(paths, 'scoring needs at least one frozen uncertainty forecast')
    live.safe_output(output_dir, calibration_dir, model_dir, m4e_model_dir, *paths,
                     *(s for _, s in settlement_pairs), *sources.values())
    forecasts, by_path, references = {}, {}, {}
    for folder in paths:
        product, forecast = uncertainty.verify_uncertainty(folder, calibration_dir, model_dir, m4e_model_dir, **sources)
        identity = forecast['metadata']['projection']['identity']
        require(identity not in forecasts or forecasts[identity][1] == forecast, 'competing uncertainty products for same projection')
        forecasts[identity] = product, forecast
        by_path[folder] = identity
        references[forecast['identity_sha256']] = uncertainty.reference(folder, forecast)
    settlements, settled_refs = {}, {}
    for u, s in settlement_pairs:
        identity = by_path[Path(u)]
        product, forecast = forecasts[identity]
        outcomes, settlement = load_settlement(s, u, forecast, product)
        k = identity, settlement['metadata']['target_gameweek']
        require(k not in settlements or settlements[k][1] == settlement, 'competing settlements for projection/target')
        settlements[k] = outcomes, settlement
        settled_refs[settlement['identity_sha256']] = uncertainty.reference(s, settlement)
    rows, cumulative, report = report_rows(forecasts, settlements)
    metadata = {'kind': 'multi-uncertainty-score', 'contract': SCORE_CONTRACT,
                'calibration_identity': next(iter(forecasts.values()))[1]['metadata']['calibration']['identity'],
                'forecasts': sorted(references.values(), key=lambda r: r['identity']),
                'settlements': sorted(settled_refs.values(), key=lambda r: r['identity'])}
    def writer(folder):
        for name, value in [('rows.json', rows), ('cumulative.json', cumulative), ('metrics.json', report)]:
            atomic_write_json(folder/name, value)
    return publish(output_dir, metadata, writer)
