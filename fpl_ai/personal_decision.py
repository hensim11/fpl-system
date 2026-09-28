"""Local personal-state workflow over unchanged, semantically verified M5B–M5D."""
import json
import shutil
import tempfile
from datetime import timedelta
from fractions import Fraction
from pathlib import Path
from time import perf_counter

from fpl_ai import joint_simulation as js, simulation_plans as sp, transfer_path as tp
from fpl_ai.experiment_io import digest, publish, verify_bundle, verify_m3
from fpl_ai.experiments import environment
from fpl_ai.fpl_rules import Rules, integer, require
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json, SQUAD_CONTRACT
from fpl_ai import decision_report

live = js.live
CONTRACT = {
    'version': 'personal-decision-v1', 'input': 'personal-state-v1',
    'config': 'personal-decision-config-v1', 'squad': SQUAD_CONTRACT,
    'free_transfers': 'usable before any target-GW transfer, including that GW accrual; no additional initial accrual',
    'unsupported': 'already-made target-GW transfers, incurred hits, active chips, account inference',
    'pre_deadline_max_age_hours': 24,
    'time': 'local import, report creation start and retained publication check; final guard before rename is not retained; no exact publication timestamp or independent clock witness',
    'ranking': 'unchanged exact M5B objective and tie priorities; simulation does not reorder plans',
    'reuse': 'same request key verifies original bundle without redating; multiple matches fail',
    'replay': 'verify and copy original artifact bytes and attestation; no new decision claim',
}
LIMITATIONS = [
    'Conditional plans from one frozen state; no actions are executed. Small differences are not decisive advice or significance claims.',
    'Static purchase prices and selectability throughout; exact initial sale rights until sold. Later account values do not refresh frozen market facts.',
    'Missing retained history can limit forecasts; no historical fixture predictors.',
    'Forecast-selected XIs and captains stay fixed in simulation; no autosubs, vice-captain substitution or chips.',
    'Limited player/team/match dependence: exchangeable historical donors with a shared as-of block; no current player-specific uncertainty.',
    'No demonstrated realised decision-value improvement or independently validated prospective calibration.',
    'Raw empirical residual bias explains differences between forecast objectives and analytical/simulated means; Monte Carlo error excludes model uncertainty.',
    'Highest-return probabilities concern only the supplied candidate entries under this law, not every legal plan, league wins or FPL rank. Duplicate entries retain split tie credit.',
    'M5C empirical player intervals are separate from simulation plan distributions; their endpoints cannot be added to form a plan interval.',
    'Manual personal state is user-supplied evidence, not independently verified account data. Separate captures are not a synchronized live account snapshot.',
]
ROLES = {'uncertainty': 'multi-uncertainty-forecast', 'calibration': 'multi-uncertainty-calibration',
         'projection': 'multi-horizon-forecast', 'model': 'multi-horizon-model',
         'm4e_model': 'prospective-xpts-model', 'history': 'multi-horizon-score', 'm3': None}


def object_fields(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), f'invalid {label} fields; required: {", ".join(sorted(fields))}')


def timestamp(value, label):
    require(type(value) is str and bool(value), f'{label} must be an explicit timezone-aware timestamp')
    try:
        return live.parse_utc(value, label)
    except (TypeError, ValueError) as error:
        raise ValueError(f'invalid {label}: {error}') from error


def validate_personal(personal, rows, horizon, imported_at):
    object_fields(personal, ('contract', 'squad', 'provenance', 'account_state'), 'personal-state')
    require(personal['contract'] == CONTRACT['input'], 'unsupported personal-state contract')
    provenance = personal['provenance']
    object_fields(provenance, ('kind', 'source', 'observed_at', 'confirmed'), 'provenance')
    require(provenance['kind'] in ('manual', 'synthetic'), 'provenance kind must be manual or synthetic')
    require(provenance['confirmed'] is True, 'unfinished template: explicitly confirm your exact state')
    require(type(provenance['source']) is str and bool(provenance['source'].strip()), 'supply a provenance source description')
    require(timestamp(provenance['observed_at'], 'personal observation') <= timestamp(imported_at, 'import time'),
            'personal observation is in the future; cannot backdate import or confirm future state')
    account = personal['account_state']
    object_fields(account, ('transfers_already_made', 'hits_already_incurred', 'active_chip'), 'account-state')
    for key in ('transfers_already_made', 'hits_already_incurred'):
        integer(account[key], key)
        require(account[key] == 0, 'unsupported already-made transfers/hits: supply a state before any target-GW transfer, or wait for the next GW; do not reset account history to zero')
    require(account['active_chip'] is None, 'active chips unsupported: use a target GW with no active chip')
    require(type(personal['squad']) is dict, 'squad must be a complete current-squad-v1 object')
    _, state = tp.validate_projections(rows, personal['squad'], horizon, Rules())
    return {**personal, 'squad': state}


def settings(raw, state, simulation_config):
    object_fields(raw, ('horizon', 'max_transfers', 'top_n', 'scenario_count', 'seed'), 'planning')
    integer(raw['horizon'], 'horizon', 1, 5)
    integer(raw['max_transfers'], 'max transfers per GW', 0, 15)
    integer(raw['top_n'], 'top N maximum', 1, 20)
    js.configuration(raw['scenario_count'], raw['seed'])
    require({k: raw[k] for k in ('scenario_count', 'seed')} == simulation_config,
            'scenario settings differ from selected simulation; deliberately freeze/select a compatible simulation first')
    effective = min(raw['horizon'], 39-state['as_of_gameweek'])
    require(effective <= state['horizon'], 'planning horizon exceeds the bound projection/simulation; freeze compatible evidence first')
    return {**raw, 'effective_horizon': effective}


def read_config(path):
    path = Path(path).resolve()
    config = load_json(path)
    object_fields(config, ('contract', 'personal_state', 'simulation_dir', 'evidence_roots', 'dependencies',
                           'plan_dir', 'output_dir', 'mode', 'planning'), 'workflow config')
    require(config['contract'] == CONTRACT['config'], 'unsupported workflow config contract')
    require(config['mode'] in ('snapshot', 'pre-deadline'), 'mode must be snapshot or pre-deadline')
    require(type(config['evidence_roots']) is list and bool(config['evidence_roots']), 'supply evidence_roots')
    require(type(config['dependencies']) is dict and set(config['dependencies']) <= set(ROLES), 'unknown dependency role')
    def location(value):
        require(type(value) is str and bool(value), 'locations must be nonempty strings')
        return (path.parent/value).resolve()
    locations = {k: location(config[k]) for k in ('personal_state', 'simulation_dir', 'output_dir')}
    locations['roots'] = [location(p) for p in config['evidence_roots']]
    locations['overrides'] = {k: location(v) for k, v in config['dependencies'].items()}
    locations['plan'] = location(config['plan_dir']) if config['plan_dir'] is not None else None
    return config, locations


def resolve_one(identity, roots, role, overrides=None):
    require(type(identity) is str and len(identity) == 64 and all(c in '0123456789abcdef' for c in identity), 'invalid dependency identity')
    if role in (overrides or {}):
        candidates = {Path(overrides[role]).resolve()}
    else:
        candidates = {p.parent.resolve() for root in roots for p in Path(root).rglob(identity+'/manifest.json')}
        candidates |= {Path(root).resolve() for root in roots if Path(root).name == identity and (Path(root)/'manifest.json').is_file()}
    require(bool(candidates), f'missing {role} prerequisite {identity}: restore the retained artifact under evidence_roots or set dependencies.{role}; see README deliberate setup/refresh commands; no automatic fitting')
    require(len(candidates) == 1, f'ambiguous {role} {identity}: set dependencies.{role} to one exact artifact directory')
    folder = candidates.pop()
    require(folder.name == identity, f'{role} override conflicts with bound identity {identity}')
    return folder


def reference(folder, manifest):
    return {**js.uc.reference(folder, manifest), 'manifest_file_sha256': sha256_file(Path(folder)/'manifest.json')}


def resolve(simulation_dir, roots, overrides=None):
    simulation_dir = Path(simulation_dir)
    require((simulation_dir/'manifest.json').is_file(), 'missing simulation prerequisite: deliberately run simulate freeze with retained uncertainty/calibration and frozen models; ordinary decision runs never train or capture')
    simulation = verify_bundle(simulation_dir, 'joint-simulation')
    binding = simulation['metadata']['binding']
    state = binding['state']
    ids = {k: binding[k]['identity'] for k in ('uncertainty', 'calibration', 'projection')}
    ids.update(model=state['model_identity'], m4e_model=state['m4e_model_identity'],
               history=js.uc.CONTRACT['history_identity'], m3=js.uc.CONTRACT['m3_identity'])
    paths = {k: resolve_one(v, roots, k, overrides) for k, v in ids.items()}
    paths['simulation'] = simulation_dir
    manifests = {k: (verify_m3(paths[k]) if k == 'm3' else verify_bundle(paths[k], ROLES[k])) for k in ids}
    for k in ('uncertainty', 'calibration', 'projection'):
        require(js.uc.reference(paths[k], manifests[k]) == binding[k], f'bound {k} reference mismatch')
    require(manifests['projection']['metadata'] == state, 'projection/simulation state mismatch')
    manifests['simulation'] = simulation
    return paths, {k: reference(paths[k], v) for k, v in manifests.items()}


def common(paths):
    return tuple(paths[k] for k in ('uncertainty', 'calibration', 'model', 'm4e_model'))


def sources(paths):
    return {'history_dir': paths['history'], 'm3_dir': paths['m3']}


def bound_context(paths):
    """Read only archives already authenticated by the upstream semantic readers."""
    archive = load_json(paths['projection']/'source.json')
    forecast = json.loads(archive['files']['manifest.json'])
    evidence = json.loads(archive['files']['evidence.json'])
    snapshot = evidence['snapshot']
    bootstrap = json.loads(snapshot['files']['bootstrap.json'])
    return {'forecast_metadata': forecast['metadata'],
            'snapshot_metadata': json.loads(snapshot['files']['manifest.json'])['metadata'],
            'clubs': {str(t['id']): t['name'] for t in bootstrap['teams']},
            'retained_history_count': len(evidence['history']),
            'snapshot_identity': snapshot['identity']}


def time_check(personal, config, state, simulation, imported_at, created_at, final_at):
    observed = timestamp(personal['provenance']['observed_at'], 'observation')
    imported, created, final = (timestamp(v, n) for v, n in
                               ((imported_at, 'import'), (created_at, 'creation'), (final_at, 'publication check')))
    capture = timestamp(state['capture'], 'capture')
    require(observed <= imported <= created <= final, 'invalid observation/import/creation chronology')
    require(timestamp(simulation['computed_at'], 'simulation computation') <= imported, 'simulation was computed after personal import')
    if config['mode'] == 'pre-deadline':
        require(final < timestamp(state['deadline'], 'first target deadline'), 'pre-deadline decision publication reached deadline; use snapshot mode for offline inspection')
        require(capture <= observed, 'pre-deadline personal observation predates snapshot; reconfirm current state')
        age = timedelta(hours=CONTRACT['pre_deadline_max_age_hours'])
        require(final-capture <= age and final-observed <= age,
                'pre-deadline sources exceed 24-hour freshness gate; deliberately refresh frozen-model evidence and reconfirm personal state, or use snapshot mode')


def implementation():
    return {'workflow': sha256_file(Path(__file__)), 'renderer': sha256_file(Path(decision_report.__file__))}


def request_key(personal, effective, refs):
    return digest({'personal': personal, 'config': effective, 'dependencies': refs,
                   'contract': CONTRACT, 'implementation': implementation(), 'environment': environment()})


def check_plan(folder, personal, effective, projection_ref):
    manifest = verify_bundle(folder, 'multi-gw-transfer-path')
    m = manifest['metadata']
    original = load_json(Path(folder)/'squad.json')
    require(type(original) is dict and type(original.get('players')) is list, 'invalid path squad')
    canonical = {**original, 'players': sorted(original['players'], key=lambda p: p['element'])}
    require(canonical == personal['squad'], 'path belongs to a different squad/economics')
    require(m['projection_identity'] == projection_ref['identity'] and
            all(m[k] == effective['planning'][p] for k, p in
                (('horizon', 'effective_horizon'), ('max_transfers', 'max_transfers'), ('top_n', 'top_n'))),
            'path projection/planning settings mismatch')
    return manifest


def decomposition(plan, baseline, rows):
    points = {(r['horizon'], r['element']): Fraction(r['xpts']) for r in rows}
    weeks = []
    totals = [Fraction(), Fraction(), Fraction()]
    for h, (w, b) in enumerate(zip(plan['weeks'], baseline['weeks'])):
        xi = sum((points[h, e] for e in w['starting_xi']), Fraction())-sum((points[h, e] for e in b['starting_xi']), Fraction())
        captain = (points[h, w['captain']]-points[h, b['captain']])*(Rules().captain_multiplier-1)
        hits = Fraction(b['transfer_hit']-w['transfer_hit'])
        for i, v in enumerate((xi, captain, hits)): totals[i] += v
        weeks.append({'gameweek': w['gameweek'], 'xi_change': float(xi), 'captain_bonus_change': float(captain),
                      'hit_change': float(hits), 'net_change': float(xi+captain+hits)})
    return {'weeks': weeks, 'horizon': dict(zip(('xi_change', 'captain_bonus_change', 'hit_change', 'net_change'),
                                               map(float, (*totals, sum(totals, Fraction())))))}


def build_summary(personal, effective, refs, attestation, rows, decision, evaluation, context, uncertainty):
    candidates = {'no_transfer': decision['baseline'], 'greedy': decision['greedy'],
                  **{f'exact_{i}': p for i, p in enumerate(decision['plans'], 1)}}
    population = {str(r['element']): {k: v for k, v in r.items() if k not in ('horizon', 'as_of_gameweek', 'target_gameweek', 'xpts')}
                  for r in rows if r['horizon'] == 0}
    state = context['projection_metadata']
    observed = personal['provenance']['observed_at']
    created = attestation['created_at']
    timings = {'snapshot_capture': state['capture'], 'snapshot_requests': context['snapshot_metadata'],
               'personal_observed_at': observed, **attestation,
               'forecast_computation': context['forecast_metadata'], 'projection_computed_at': state['computed_at'],
               'simulation_started_at': context['simulation_metadata']['started_at'],
               'simulation_computed_at': context['simulation_metadata']['computed_at'], 'first_target_deadline': state['deadline'],
               'snapshot_age_hours_at_creation': (timestamp(created, 'created')-timestamp(state['capture'], 'capture')).total_seconds()/3600,
               'personal_age_hours_at_creation': (timestamp(created, 'created')-timestamp(observed, 'observed')).total_seconds()/3600,
               'mixed_observation_times': observed != state['capture'],
               'created_after_deadline': not live.before(created, state['deadline'])}
    warnings = list(LIMITATIONS)
    if max(timings['snapshot_age_hours_at_creation'], timings['personal_age_hours_at_creation']) > 24:
        warnings.insert(0, 'STALE INPUT: at least one market/personal observation is more than 24 hours old. A new report does not refresh it.')
    if timings['mixed_observation_times']:
        warnings.insert(0, 'MIXED-AGE INPUTS: market and personal observations were recorded at different times.')
    return {'contract': CONTRACT['version'], 'label': f"{personal['provenance']['kind']} / {effective['mode']}",
            'personal': personal, 'config': effective, 'dependencies': refs, 'timing': timings,
            'rules': Rules().as_dict(), 'population': population, 'clubs': context['clubs'],
            'retained_history_count': context['retained_history_count'],
            'highest_ranked': 'exact_1', 'returned_exact_paths': len(decision['plans']),
            'plans': candidates, 'decomposition': {n: {b: decomposition(p, candidates[b], rows)
                        for b in ('no_transfer', 'greedy')} for n, p in candidates.items()},
            'simulation': evaluation, 'empirical_player_intervals': uncertainty,
            'limitations': warnings}


def context_for(paths):
    context = bound_context(paths)
    context['projection_metadata'] = load_json(paths['projection']/'manifest.json')['metadata']
    context['simulation_metadata'] = load_json(paths['simulation']/'manifest.json')['metadata']
    return context


def validate(config_path):
    config, loc = read_config(config_path)
    paths, refs = resolve(loc['simulation_dir'], loc['roots'], loc['overrides'])
    (rows, _, sim_config), sim = js.verify(paths['simulation'], *common(paths), **sources(paths))
    effective = {'mode': config['mode'], 'planning': settings(config['planning'], sim['metadata']['binding']['state'], sim_config)}
    imported = live.stamp(live.now_utc)
    personal = validate_personal(load_json(loc['personal_state']), rows, effective['planning']['effective_horizon'], imported)
    time_check(personal, effective, sim['metadata']['binding']['state'], sim['metadata'], imported, imported, imported)
    if loc['plan']:
        check_plan(loc['plan'], personal, effective, refs['projection'])
        sp.load_plans(loc['plan'], rows, sim['metadata']['binding']['projection'])
    return {'personal': personal, 'config': effective, 'dependencies': refs, 'population_count': len(rows)//sim['metadata']['binding']['state']['horizon']}


def verify(folder, roots, overrides=None):
    folder = Path(folder)
    manifest = verify_bundle(folder, 'personal-decision')
    m = manifest['metadata']
    object_fields(m, ('kind', 'contract', 'request_key', 'attestation', 'implementation', 'environment'), 'decision metadata')
    require(m['contract'] == CONTRACT and m['implementation'] == implementation() and m['environment'] == environment(), 'personal decision implementation/environment/contract mismatch')
    refs = load_json(folder/'dependencies.json')
    paths, upstream = resolve(resolve_one(refs['simulation']['identity'], roots, 'simulation', overrides), roots, overrides)
    require({k: refs[k] for k in upstream} == upstream and set(refs) == set(upstream) | {'plan', 'evaluation'}, 'decision upstream dependency mismatch')
    for role, kind in (('plan', 'multi-gw-transfer-path'), ('evaluation', 'simulation-plan-evaluation')):
        paths[role] = resolve_one(refs[role]['identity'], [folder.parent, *roots], role, overrides)
        require(reference(paths[role], verify_bundle(paths[role], kind)) == refs[role], f'{role} dependency changed')
    effective = load_json(folder/'config.json')
    sim = load_json(paths['simulation']/'manifest.json')
    object_fields(effective, ('mode', 'planning'), 'effective configuration')
    require(effective['mode'] in ('snapshot', 'pre-deadline'), 'invalid saved mode')
    raw = {k: v for k, v in effective['planning'].items() if k != 'effective_horizon'}
    require(digest(effective['planning']) == digest(settings(raw, sim['metadata']['binding']['state'], sim['metadata']['config'])), 'effective planning mismatch')
    rows = load_json(paths['simulation']/'projections.json')
    attestation = m['attestation']
    object_fields(attestation, ('imported_at', 'created_at', 'publication_checked_at'), 'attestation')
    time_check(load_json(folder/'personal.json'), effective, sim['metadata']['binding']['state'], sim['metadata'],
               attestation['imported_at'], attestation['created_at'], attestation['publication_checked_at'])
    personal = validate_personal(load_json(folder/'personal.json'), rows, effective['planning']['effective_horizon'], m['attestation']['imported_at'])
    require(digest(load_json(folder/'squad.json')) == digest(personal['squad']), 'canonical personal squad mismatch')
    require(load_json(folder/'contract.json') == CONTRACT and m['request_key'] == request_key(personal, effective, upstream), 'decision request key mismatch')
    check_plan(paths['plan'], personal, effective, refs['projection'])
    # Includes full simulation/calibration/projection replay and exact M5B replay for every new path identity.
    sp.verify(paths['evaluation'], paths['simulation'], paths['plan'], *common(paths), **sources(paths))
    summary = build_summary(personal, effective, refs, attestation, rows, load_json(paths['plan']/'decision.json'),
                            load_json(paths['evaluation']/'evaluation.json'), context_for(paths),
                            load_json(paths['uncertainty']/'uncertainty.json'))
    require(digest(load_json(folder/'summary.json')) == digest(summary), 'decision summary semantic reconstruction mismatch')
    for name, expected in decision_report.render(summary).items():
        require((folder/name).read_text() == expected, f'{name} rendering reconstruction mismatch')
    return manifest, summary


def run(config_path, progress=print):
    start = perf_counter()
    config, loc = read_config(config_path)
    imported = live.stamp(live.now_utc)
    paths, refs = resolve(loc['simulation_dir'], loc['roots'], loc['overrides'])
    progress('Verifying pinned simulation, calibration, projections and frozen models…')
    (rows, _, sim_config), sim = js.verify(paths['simulation'], *common(paths), **sources(paths))
    effective = {'mode': config['mode'], 'planning': settings(config['planning'], sim['metadata']['binding']['state'], sim_config)}
    personal = validate_personal(load_json(loc['personal_state']), rows, effective['planning']['effective_horizon'], imported)
    if loc['plan']:
        check_plan(loc['plan'], personal, effective, refs['projection'])
    key = request_key(personal, effective, refs)
    root = loc['output_dir']
    live.safe_output(root, *paths.values(), loc['personal_state'], config_path)
    matches = [p.parent for p in root.glob('*/manifest.json') if load_json(p)['metadata'].get('request_key') == key]
    require(len(matches) <= 1, 'ambiguous accepted personal decisions; verify/replay an explicit bundle')
    if matches:
        if loc['plan']:
            requested = reference(loc['plan'], verify_bundle(loc['plan'], 'multi-gw-transfer-path'))
            cached = load_json(matches[0]/'dependencies.json')['plan']
            require(digest(requested) == digest(cached),
                    'explicit path identity conflicts with cached decision; verify the original bundle or use a separate output_dir')
            sp.load_plans(loc['plan'], rows, sim['metadata']['binding']['projection'])
        progress('Verifying existing decision without changing its attestation…')
        _, summary = verify(matches[0], [root, *loc['roots']], loc['overrides'])
        return matches[0], True, summary, {'total_seconds': perf_counter()-start}
    time_check(personal, effective, sim['metadata']['binding']['state'], sim['metadata'], imported, imported, imported)
    profile = {'upstream_verification_seconds': perf_counter()-start}
    checkpoint = perf_counter()
    planning = effective['planning']
    progress('Building or checking exact M5B paths for the supplied squad…')
    if loc['plan']:
        plan = loc['plan']
        check_plan(plan, personal, effective, refs['projection'])
    else:
        with tempfile.TemporaryDirectory() as tmp:
            squad_path = Path(tmp)/'squad.json'
            atomic_write_json(squad_path, personal['squad'])
            plan, _ = tp.build_plan(paths['projection'], paths['model'], paths['m4e_model'], squad_path, root/'paths',
                                   horizon=planning['horizon'], max_transfers=planning['max_transfers'], top_n=planning['top_n'])
    check_plan(plan, personal, effective, refs['projection'])
    profile['planning_seconds'] = perf_counter()-checkpoint
    checkpoint = perf_counter()
    progress('Evaluating all paths on common scenarios; new paths undergo exact optimiser/greedy replay…')
    evaluation, _ = sp.evaluate(paths['simulation'], plan, *common(paths), root/'evaluations', **sources(paths))
    profile['evaluation_and_path_replay_seconds'] = perf_counter()-checkpoint
    checkpoint = perf_counter()
    progress('Verifying evaluation and reconstructing report arithmetic before publication…')
    sp.verify(evaluation, paths['simulation'], plan, *common(paths), **sources(paths))
    refs = {**refs, 'plan': reference(plan, verify_bundle(plan, 'multi-gw-transfer-path')),
            'evaluation': reference(evaluation, verify_bundle(evaluation, 'simulation-plan-evaluation'))}
    created = live.stamp(live.now_utc)
    attestation = {'imported_at': imported, 'created_at': created}
    summary = build_summary(personal, effective, refs, attestation, rows, load_json(plan/'decision.json'),
                            load_json(evaluation/'evaluation.json'), context_for(paths), load_json(paths['uncertainty']/'uncertainty.json'))
    reports = decision_report.render(summary)
    metadata = {'kind': 'personal-decision', 'contract': CONTRACT, 'request_key': key,
                'attestation': attestation, 'implementation': implementation(), 'environment': environment()}
    def writer(folder):
        # Render first, then retain the last check that can be embedded before sealing.
        # A second, unretained guard catches boundary crossings during sealing.
        checked = live.stamp(live.now_utc)
        time_check(personal, effective, sim['metadata']['binding']['state'], sim['metadata'], imported, created, checked)
        attestation['publication_checked_at'] = checked
        summary['timing']['publication_checked_at'] = checked
        reports.update(decision_report.render(summary))
        for name, obj in [('contract', CONTRACT), ('squad', personal['squad']), ('personal', personal),
                          ('config', effective), ('dependencies', refs), ('summary', summary)]:
            atomic_write_json(folder/(name+'.json'), obj)
        for name, content in reports.items(): (folder/name).write_text(content)
    def guard():
        final = live.stamp(live.now_utc)
        require(timestamp(final, 'final guard') >= timestamp(attestation['publication_checked_at'], 'retained check'),
                'final guard clock precedes retained publication check')
        time_check(personal, effective, sim['metadata']['binding']['state'], sim['metadata'], imported, created, final)
    out, reused = publish(root, metadata, writer, publication_guard=guard)
    profile['final_verification_and_publication_seconds'] = perf_counter()-checkpoint
    profile['total_seconds'] = perf_counter()-start
    return out, reused, summary, profile


def replay(folder, roots, output_dir, overrides=None):
    manifest, summary = verify(folder, roots, overrides)
    dependencies = [resolve_one(ref['identity'], [Path(folder).parent, *roots], role, overrides)
                    for role, ref in summary['dependencies'].items()]
    live.safe_output(output_dir, folder, *dependencies)
    def writer(out):
        for name in manifest['artifacts']: shutil.copyfile(Path(folder)/name, out/name)
    out, reused = publish(output_dir, manifest['metadata'], writer)
    return out, reused, summary


def catalog(simulation_dir, roots, query=''):
    paths, _ = resolve(simulation_dir, roots)
    (rows, _, _), _ = js.verify(paths['simulation'], *common(paths), **sources(paths))
    context = bound_context(paths)
    # Return every match; never convert an ambiguous name into an ID.
    return [{**r, 'club': context['clubs'][str(r['team'])]} for r in rows if r['horizon'] == 0 and
            (not query or query.casefold() in r['name'].casefold() or query == str(r['element']))]


def init(config_path, simulation_dir, roots):
    config_path = Path(config_path).resolve()
    personal_path = config_path.with_name(config_path.stem+'-state.json')
    catalog_path = config_path.with_name(config_path.stem+'-players.json')
    require(not any(p.exists() for p in (config_path, personal_path, catalog_path)), 'initialization would overwrite a file; choose a new config name')
    paths, _ = resolve(simulation_dir, roots)
    (rows, _, sim_config), sim = js.verify(paths['simulation'], *common(paths), **sources(paths))
    state = sim['metadata']['binding']['state']
    config = {'contract': CONTRACT['config'], 'personal_state': personal_path.name,
              'simulation_dir': str(Path(simulation_dir).resolve()), 'evidence_roots': [str(Path(r).resolve()) for r in roots],
              'dependencies': {}, 'plan_dir': None, 'output_dir': str(Path('data/personal_decisions').resolve()), 'mode': 'snapshot',
              'planning': {'horizon': state['horizon'], 'max_transfers': 2, 'top_n': 3, **sim_config}}
    personal = {'contract': CONTRACT['input'], 'squad': {'contract': SQUAD_CONTRACT, 'season': state['season'],
                'target_gameweek': state['as_of_gameweek'], 'players': [{'element': None, 'selling_price': None} for _ in range(15)],
                'bank': None, 'free_transfers': None},
                'provenance': {'kind': 'manual', 'source': '', 'observed_at': None, 'confirmed': False},
                'account_state': {'transfers_already_made': None, 'hits_already_incurred': None, 'active_chip': 'UNCONFIRMED'}}
    clubs = bound_context(paths)['clubs']
    config_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(personal_path, personal)
    atomic_write_json(catalog_path, [{**r, 'club': clubs[str(r['team'])]} for r in rows if r['horizon'] == 0])
    atomic_write_json(config_path, config)
    return config_path, personal_path, catalog_path
