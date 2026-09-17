"""Coverage, FPL sanity checks and descriptive paired comparisons; no tuning."""
from collections import defaultdict

import numpy as np
from threadpoolctl import threadpool_limits

from fpl_ai.evaluation import BASELINES, metrics
from fpl_ai.experiment_io import key
from fpl_ai.experiments import CATEGORICAL, INDICATORS, MODEL_FEATURES, NUMERIC, SEED, matrix


def comparisons(rows, predictions, models):
    result = {}
    for model in models:
        result[model] = {}
        for baseline in BASELINES:
            common = [r for r in rows if r['target_points'] is not None and predictions[key(r)][baseline] is not None]
            mm, bm = (metrics(common,predictions,n) for n in (model,baseline))
            groups = defaultdict(list)
            for r in common:
                y, p = r['target_points'], predictions[key(r)]
                groups[(r['season'],r['target_gameweek'])].append(((y-p[model])**2,(y-p[baseline])**2))
            sums = np.array([[len(v),sum(a for a,b in v),sum(b for a,b in v)] for _,v in sorted(groups.items())])
            rng = np.random.default_rng(SEED)
            sampled = sums[rng.integers(0,len(sums),size=(2000,len(sums)))].sum(axis=1)
            delta = np.sqrt(sampled[:,1]/sampled[:,0])-np.sqrt(sampled[:,2]/sampled[:,0])
            result[model][baseline] = {
                'common_rows':len(common), 'model':mm,'baseline':bm,
                'delta_model_minus_baseline': {m: mm[m]-bm[m] if mm[m] is not None and bm[m] is not None else None
                                              for m in ('mae','rmse','mean_gameweek_spearman')},
                'rmse_delta_gw_bootstrap_95_percentile':np.quantile(delta,[.025,.975]).tolist(),
                'gameweeks_lower_mse':int(np.sum(sums[:,1]<sums[:,2])), 'gameweeks':len(sums),
            }
    return result


def diagnostics(rows, predictions, models):
    report = {'rows':len(rows), 'missing_features':{f:sum(r['features'][f] is None for r in rows) for f in MODEL_FEATURES}, 'models':{}}
    for model in models:
        values = np.array([predictions[key(r)][model] for r in rows])
        def describe(group):
            vs = np.array([predictions[key(r)][model] for r in group])
            ys = [r['target_points'] for r in group if r['target_points'] is not None]
            return {'rows':len(group), 'prediction_mean':float(vs.mean()) if len(vs) else None,
                    'actual_mean':float(np.mean(ys)) if ys else None,
                    'metrics':{n:metrics(group,predictions,n) for n in (model,)+BASELINES}}
        def example(index):
            r = rows[index]
            return {'key':list(key(r)), 'position':r['features']['deadline_position_id'],
                    'target':r['target_points'],'predictions':predictions[key(r)], 'features':r['features']}
        order = np.argsort(values,kind='stable')
        disagreement = sorted(range(len(rows)),key=lambda j:(-abs(values[j]-predictions[key(rows[j])]['player_scoring_rate']),key(rows[j])))
        report['models'][model] = {
            'quantiles':dict(zip(('min','p01','p10','p50','p90','p99','max'),np.quantile(values,[0,.01,.1,.5,.9,.99,1]).tolist())),
            'mean':float(values.mean()),'negative_predictions':int(np.sum(values<0)),
            'lowest':[example(int(j)) for j in order[:10]], 'highest':[example(int(j)) for j in order[-10:][::-1]],
            'largest_scoring_rate_disagreements':[example(j) for j in disagreement[:10]],
            'positions':{str(p):describe([r for r in rows if r['features']['deadline_position_id']==p]) for p in (1,2,3,4)},
            'cold_start':describe([r for r in rows if r['features']['season_points_count']==0]),
            'low_history':describe([r for r in rows if r['features']['season_points_count']<3]),
            'established_history':describe([r for r in rows if r['features']['season_points_count']>=3]),
            'missing_chance':describe([r for r in rows if r['features']['chance_of_playing_next_round'] is None]),
        }
    return report


def interpretation(rows, models):
    """Permutation moves value plus its missingness flag together within each GW.

    Uses a fixed uniform sample of at most 4096 validation rows for bounded cost.
    Correlated features can mask one another; these are associations, not causes.
    """
    rng = np.random.default_rng(SEED)
    labelled = [r for r in rows if r['target_points'] is not None]
    selected = np.sort(rng.choice(len(labelled),min(4096,len(labelled)),replace=False))
    sample = [labelled[int(j)] for j in selected]
    x, y = matrix(sample), np.array([r['target_points'] for r in sample])
    groups = defaultdict(list)
    for j,r in enumerate(sample): groups[(r['season'],r['target_gameweek'])].append(j)
    result = {}
    with threadpool_limits(limits=1):
        for name,model in models.items():
            pre = model.named_steps['preprocess']
            info = {'numeric_feature_order':list(NUMERIC),
                    'imputation_statistics':pre.named_transformers_['numeric']['impute'].statistics_.tolist(),
                    'scaler_mean':pre.named_transformers_['numeric']['scale'].mean_.tolist(),
                    'scaler_scale':pre.named_transformers_['numeric']['scale'].scale_.tolist(),
                    'categories':{f:c.tolist() for f,c in zip(CATEGORICAL,pre.named_transformers_['categorical'].categories_)}}
            if hasattr(model.named_steps['model'],'coef_'):
                names = list(NUMERIC)+list(INDICATORS)+list(pre.named_transformers_['categorical'].get_feature_names_out(CATEGORICAL))
                info['coefficients'] = dict(zip(names,model.named_steps['model'].coef_.tolist()))
                info['intercept'] = float(model.named_steps['model'].intercept_)
                info['coefficient_units'] = 'Numeric: points per training standard deviation after imputation; flags/categories: points per unit.'
            else:
                base = float(np.mean((model.predict(x)-y)**2))
                importance = {}
                rng = np.random.default_rng(SEED)
                for f in NUMERIC+CATEGORICAL:
                    cols = [MODEL_FEATURES.index(f)]
                    if f+'_missing' in MODEL_FEATURES: cols.append(MODEL_FEATURES.index(f+'_missing'))
                    changes = []
                    for _ in range(3):
                        altered = x.copy()
                        for indices in groups.values():
                            perm = rng.permutation(indices)
                            altered[np.ix_(indices,cols)] = x[np.ix_(perm,cols)]
                        changes.append(float(np.mean((model.predict(altered)-y)**2))-base)
                    importance[f] = {'mse_increase_mean':float(np.mean(changes)),'repeats':changes}
                info['permutation'] = importance
                info['permutation_rows'] = len(sample)
                info['permutation_sample_keys'] = [list(key(r)) for r in sample]
            result[name] = info
    return result
