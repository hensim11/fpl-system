"""Chronological transparent baselines and reusable coverage-aware metrics."""
import math
from collections import defaultdict
from statistics import mean

from fpl_ai.modelling_contract import split_for

BASELINES = ('historical_mean', 'position_mean', 'recent_points', 'player_scoring_rate', 'fpl_ep_next')


def predict_baselines(rows):
    """Expand through settled training labels only; never fit validation/test labels."""
    for r in rows:
        if r['split'] != split_for(r['season']):
            raise ValueError('split contract violated')
    training = sorted((r for r in rows if r['split'] == 'train' and r['target_points'] is not None),
                      key=lambda r: (r['label_available_at'], r['season'], r['target_gameweek'], r['element']))
    index, total, count = 0, 0, 0
    positions = defaultdict(lambda: [0, 0])
    predictions = {}
    for r in sorted(rows, key=lambda r: (r['audit']['capture_time_utc'], r['season'], r['target_gameweek'], r['element'])):
        cutoff = r['audit']['capture_time_utc']
        while index < len(training) and training[index]['label_available_at'] <= cutoff:
            past = training[index]
            # A malformed availability timestamp must not unlock the same GW.
            if past['audit']['capture_time_utc'] >= past['label_available_at']:
                raise ValueError('label availability must follow its observation')
            y = past['target_points']
            total += y
            count += 1
            bucket = positions[past['features']['deadline_position_id']]
            bucket[0] += y
            bucket[1] += 1
            index += 1
        overall = total/count if count else 0.0
        f = r['features']
        psum, pn = positions[f['deadline_position_id']]
        position = psum/pn if pn else overall
        predictions[(r['season'], r['target_gameweek'], r['element'])] = {
            'historical_mean': overall, 'position_mean': position,
            'recent_points': f['points_mean_3'] if f['points_mean_3'] is not None else position,
            'player_scoring_rate': f['season_points_mean'] if f['season_points_count'] >= 3 else position,
            'fpl_ep_next': r['external_ep_next'],
        }
    return predictions


def ranks(values):
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0]*len(values)
    start = 0
    while start < len(ordered):
        end = start+1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        for index in ordered[start:end]:
            result[index] = (start+1+end)/2
        start = end
    return result


def spearman(actual, predicted):
    if len(actual) < 2:
        return None
    a, b = ranks(actual), ranks(predicted)
    am, bm = mean(a), mean(b)
    numerator = sum((x-am)*(y-bm) for x,y in zip(a,b))
    denominator = math.sqrt(sum((x-am)**2 for x in a)*sum((y-bm)**2 for y in b))
    return numerator/denominator if denominator else None


def metrics(rows, predictions, baseline):
    labelled = [r for r in rows if r['target_points'] is not None]
    pairs, groups = [], defaultdict(list)
    for r in labelled:
        p = predictions[(r['season'], r['target_gameweek'], r['element'])].get(baseline)
        if p is None:
            continue
        if not math.isfinite(p):
            raise ValueError('non-finite prediction')
        pair = (r['target_points'], p)
        pairs.append(pair)
        groups[(r['season'], r['target_gameweek'])].append(pair)
    ranking = [spearman([a for a,b in values], [b for a,b in values]) for values in groups.values()]
    defined = [v for v in ranking if v is not None]
    return {
        'population_rows': len(rows), 'labelled_rows': len(labelled), 'predicted_rows': len(pairs),
        'missing_predictions': len(labelled)-len(pairs),
        'prediction_coverage': len(pairs)/len(labelled) if labelled else None,
        'mae': mean(abs(a-b) for a,b in pairs) if pairs else None,
        'rmse': math.sqrt(mean((a-b)**2 for a,b in pairs)) if pairs else None,
        'mean_gameweek_spearman': mean(defined) if defined else None,
        'ranking_defined_gameweeks': len(defined), 'ranking_undefined_gameweeks': len(ranking)-len(defined),
    }


def evaluate(rows, predictions, baselines=BASELINES):
    """Score keyed predictions; split reports are separate, never pooled for selection."""
    expected = {(r['season'], r['target_gameweek'], r['element']) for r in rows}
    if len(expected) != len(rows) or set(predictions) != expected:
        raise ValueError('prediction keys must match unique evaluation population')
    report = {}
    for split in ('train', 'validation', 'test'):
        subset = [r for r in rows if r['split'] == split]
        segments = {'overall': subset}
        for season in sorted({r['season'] for r in subset}):
            segments[f'season:{season}'] = [r for r in subset if r['season'] == season]
        for position in (1,2,3,4):
            segments[f'position:{position}'] = [r for r in subset if r['features']['deadline_position_id'] == position]
        report[split] = {segment: {b: metrics(group, predictions, b) for b in baselines}
                         for segment, group in segments.items()}
    return report
