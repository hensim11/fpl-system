"""Immutable M5F retention, manual assertions and predeclared outcome diagnostics."""
import json
import shutil
from pathlib import Path

from fpl_ai import personal_decision as pd, multi_outcomes as mo
from fpl_ai.decision_report import Document
from fpl_ai.experiment_io import digest, publish, verify_bundle
from fpl_ai.fpl_rules import Rules, integer, require
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_optimiser import load_json

live = pd.live
CONTRACT = {
    'version': 'decision-review-v1',
    'actions': 'manager-confirmation-v1',
    'scoring': 'fixed XI sum + one extra captain - explicit hits; no vice captain, autosubs or chips; never official FPL score',
    'comparison': 'original no_transfer, greedy, exact_1..N order; no outcome-dependent selection',
    'cumulative': 'all target GWs and all required player labels or null; blanks remain null',
    'counterfactual': 'arithmetic only; future transfers hypothetical, later prices/availability/circumstances unsupported',
    'provenance': 'manual assertions are not independently verified account history; synthetic excluded',
    'prospective': 'pre-deadline M5E, retention before first deadline, confirmation before target deadline; local clock only',
    'extension': 'fill unknown fields only; conflicting heads fail; no silent correction',
    'action_validation': {'rules': Rules().as_dict(),
                          'pairs': 'each asserted out/in pair preserves frozen position',
                          'hits': 'complete target-GW count/hit must be possible for a later FT state Rules.next_free(0, 0)..cap; first target reconciles exact original FTs'},
    'review_exclusions': 'sorted unique union of retention and all attached confirmation exclusions, including predecessors',
    'settlement': mo.CONTRACT,
}
FIELDS = ('transfers', 'squad', 'starting_xi', 'captain', 'transfer_hit', 'chip')
KINDS = ('decision-retention', 'manager-confirmation', 'decision-outcome-review')


def same(a, b, message):
    require(digest(a) == digest(b), message)


def order(summary):
    return ['no_transfer', 'greedy', *[f'exact_{i}' for i in range(1, summary['returned_exact_paths']+1)]]


def timing(imported, checked, earliest, deadline):
    values = [pd.timestamp(v, n) for v, n in ((earliest, 'earliest'), (imported, 'import'), (checked, 'publication check'), (deadline, 'deadline'))]
    require(values[0] <= values[1] <= values[2], 'invalid record chronology')
    return {'imported_at': imported, 'publication_checked_at': checked,
            'late': values[2] >= values[3]}


def guard(attestation, deadline):
    final = pd.timestamp(live.stamp(live.now_utc), 'final check')
    require(final >= pd.timestamp(attestation['publication_checked_at'], 'publication check'), 'record clock reversed')
    if not attestation['late']:
        require(final < pd.timestamp(deadline, 'deadline'), 'record publication crossed deadline; retry to label late')


def write_products(root, metadata, products, publication_guard=None):
    def writer(folder):
        for name, value in products.items():
            if name.endswith('.json'): atomic_write_json(folder/name, value)
            else: (folder/name).write_text(value)
    return publish(root, metadata, writer, publication_guard=publication_guard)


class Reader:
    """One operation verifies each dependency once; no persistent trust cache."""
    def __init__(self, roots):
        self.roots = list(map(Path, roots))
        self.cache = {}
        self.decisions = {}
        self.active = set()

    def locate(self, ref, role):
        path = pd.resolve_one(ref['identity'], self.roots, role)
        same(pd.reference(path, verify_bundle(path)), ref, f'altered {role} reference')
        return path

    def decision(self, ref):
        path = self.locate(ref, 'decision')
        if path not in self.decisions:
            self.decisions[path] = pd.verify(path, self.roots)
        return self.decisions[path][1]

    def read(self, folder):
        folder = Path(folder).resolve()
        if folder in self.cache: return self.cache[folder]
        require(folder not in self.active, 'cyclic evidence')
        self.active.add(folder)
        manifest = verify_bundle(folder)
        m = manifest['metadata']
        require(m['kind'] in KINDS, 'not M5F evidence')
        same(m['contract'], CONTRACT, 'M5F contract mismatch')
        product = load_json(folder/'record.json')
        if m['kind'] == KINDS[0]:
            summary = self.decision(m['decision'])
            expected = retention_product(summary, self, m['attestation'])
            same(m, {'kind': KINDS[0], 'contract': CONTRACT, 'decision': m['decision'],
                     'attestation': m['attestation'], 'request_key': digest(m['decision'])}, 'retention metadata mismatch')
        elif m['kind'] == KINDS[1]:
            rm, retained = self.read(self.locate(m['retention'], 'retention'))
            require(rm['metadata']['kind'] == KINDS[0], 'expected retention')
            retained = with_identity(retained, rm['metadata']['decision'])
            previous = self.read(self.locate(m['previous'], 'previous')) if m['previous'] else None
            if previous:
                require(previous[0]['metadata']['kind'] == KINDS[1], 'previous is not a confirmation')
                same(previous[0]['metadata']['retention'], m['retention'], 'previous retention mismatch')
            expected = confirmation_product(product['assertion'], retained, m['attestation'], previous[1] if previous else None)
            expected_meta = confirmation_metadata(m['retention'], m['previous'], product['assertion'], m['attestation'])
            same(m, expected_meta, 'confirmation metadata mismatch')
        else:
            retained = self.read(self.locate(m['retention'], 'retention'))[1]
            expected, actions, settlements = assemble(self, m['retention'], retained,
                [self.locate(r, 'confirmation') for r in m['confirmations']],
                [self.locate(r, 'settlement') for r in m['settlements']])
            same(m, review_metadata(m['retention'], actions, settlements), 'review metadata mismatch')
        same(product, expected, 'record semantic reconstruction mismatch')
        same(load_json(folder/'contract.json'), CONTRACT, 'saved contract mismatch')
        for name, value in render(m['kind'], product).items():
            require((folder/name).read_text() == value, 'review rendering mismatch')
        self.active.remove(folder)
        self.cache[folder] = manifest, product
        return manifest, product


def retention_product(summary, reader, attestation):
    u = reader.locate(summary['dependencies']['uncertainty'], 'uncertainty')
    um = verify_bundle(u, 'multi-uncertainty-forecast')  # already semantically verified by M5E
    weeks = summary['plans']['no_transfer']['weeks']
    deadlines = {str(w['gameweek']): mo.target_context(u, um, w['gameweek'])['metadata']['deadline'] for w in weeks}
    expected_time = timing(attestation['imported_at'], attestation['publication_checked_at'],
                           summary['timing']['publication_checked_at'], deadlines[str(weeks[0]['gameweek'])])
    same(attestation, expected_time, 'retention timing mismatch')
    reasons = []
    if summary['config']['mode'] != 'pre-deadline': reasons.append('snapshot/what-if decision')
    if attestation['late']: reasons.append('retention recorded after first deadline')
    if summary['personal']['provenance']['kind'] == 'synthetic': reasons.append('synthetic decision')
    return {'summary': summary, 'candidate_order': order(summary), 'deadlines': deadlines,
            'attestation': expected_time, 'prospective_exclusions': reasons,
            'evaluation': CONTRACT}


def cached(root, key, reader, kind):
    matches = [p.parent for p in Path(root).glob('*/manifest.json')
               if load_json(p)['metadata'].get('kind') == kind and load_json(p)['metadata'].get('request_key') == key]
    require(len(matches) <= 1, 'ambiguous immutable reuse')
    if matches:
        _, product = reader.read(matches[0])
        return matches[0], True, product


def retain(decision, roots, output=Path('data/decision_reviews/retentions')):
    imported = live.stamp(live.now_utc)
    reader = Reader([*roots, output])
    dm, summary = pd.verify(decision, roots)
    ref = pd.reference(decision, dm)
    reader.decisions[Path(decision).resolve()] = (dm, summary)
    live.safe_output(output, decision)
    reuse = cached(output, digest(ref), reader, KINDS[0])
    if reuse: return reuse
    checked = live.stamp(live.now_utc)
    t = timing(imported, checked, summary['timing']['publication_checked_at'], summary['timing']['first_target_deadline'])
    product = retention_product(summary, reader, t)
    m = {'kind': KINDS[0], 'contract': CONTRACT, 'decision': ref, 'attestation': t, 'request_key': digest(ref)}
    out, reused = write_products(output, m, {'record.json': product, 'contract.json': CONTRACT, **render(KINDS[0], product)},
                                 lambda: guard(t, summary['timing']['first_target_deadline']))
    return out, reused, product


def id_list(value, label, population, size=None):
    require(type(value) is list, f'{label} must be a list')
    for e in value:
        integer(e, label, 1)
        require(str(e) in population, f'unknown {label} player')
    require(len(set(value)) == len(value) and (size is None or len(value) == size), f'duplicate/wrong size {label}')


def validate_assertion(a, retained, imported):
    pd.object_fields(a, ('contract', 'decision_identity', 'season', 'target_gameweek', 'provenance', 'choice', 'actions'), 'confirmation')
    require(a['contract'] == CONTRACT['actions'], 'unsupported confirmation contract')
    s = retained['summary']; pop = s['population']; rules = Rules().validate()
    same(a['decision_identity'], retained['decision_identity'], 'confirmation decision mismatch')
    require(a['season'] == s['personal']['squad']['season'], 'confirmation season mismatch')
    integer(a['target_gameweek'], 'target Gameweek', 1, 38)
    require(str(a['target_gameweek']) in retained['deadlines'], 'target outside frozen horizon')
    p = a['provenance']
    pd.object_fields(p, ('kind', 'source', 'declared_at', 'confirmed'), 'provenance')
    require(p['kind'] in ('manual', 'synthetic') and type(p['source']) is str and bool(p['source'].strip()) and p['confirmed'] is True,
            'explicit manual/synthetic confirmation and source required')
    require(pd.timestamp(s['timing']['publication_checked_at'], 'decision publication') <= pd.timestamp(p['declared_at'], 'declared action') <= pd.timestamp(imported, 'import'),
            'declared action must follow decision publication and precede import')
    choice = a['choice']
    if choice is not None:
        pd.object_fields(choice, ('selected', 'rejected'), 'choice')
        require(choice['selected'] is None or choice['selected'] in retained['candidate_order'], 'unknown selected candidate')
        require(type(choice['rejected']) is list and all(type(n) is str and n in retained['candidate_order'] for n in choice['rejected']), 'unknown rejected candidate')
        require(len(set(choice['rejected'])) == len(choice['rejected']) and choice['selected'] not in choice['rejected'], 'ambiguous choice')
        require(choice['selected'] is not None or choice['rejected'], 'empty choice; use null')
    actions = a['actions']; pd.object_fields(actions, FIELDS, 'actions')
    require(choice is not None or any(v is not None for v in actions.values()), 'empty confirmation')
    for key, size in (('squad', 15), ('starting_xi', 11)):
        if actions[key] is not None:
            id_list(actions[key], key, pop, size)
            counts = [sum(pop[str(e)]['position'] == p for e in actions[key]) for p in range(1, 5)]
            if key == 'squad':
                require(counts == list(Rules().position_counts), 'illegal squad positions')
                require(all(sum(pop[str(e)]['team'] == team for e in actions[key]) <= 3 for team in {pop[str(e)]['team'] for e in actions[key]}), 'illegal squad club count')
            else: require(all(lo <= n <= hi for n, lo, hi in zip(counts, Rules().xi_min, Rules().xi_max)), 'illegal XI formation')
    if actions['squad'] is not None and actions['starting_xi'] is not None:
        require(set(actions['starting_xi']) <= set(actions['squad']), 'XI outside confirmed squad')
    if actions['captain'] is not None:
        id_list([actions['captain']], 'captain', pop, 1)
        if actions['starting_xi'] is not None: require(actions['captain'] in actions['starting_xi'], 'captain outside XI')
    if actions['transfer_hit'] is not None:
        integer(actions['transfer_hit'], 'hit points')
        require(actions['transfer_hit'] % rules.hit_cost == 0, 'hit points must be a multiple of the rules hit cost')
    require(actions['chip'] in (None, 'none'), 'unsupported chip; v1 requires no chip for scoring')
    if actions['transfers'] is not None:
        require(type(actions['transfers']) is list, 'transfers must be an ordered list')
        for pair in actions['transfers']:
            pd.object_fields(pair, ('out', 'in'), 'transfer')
            id_list([pair['out'], pair['in']], 'transfer', pop, 2)
            require(pop[str(pair['out'])]['position'] == pop[str(pair['in'])]['position'],
                    'asserted transfer pair has incompatible frozen positions')
        if actions['transfer_hit'] is not None:
            minimum = 0 if a['target_gameweek'] == s['personal']['squad']['target_gameweek'] else rules.next_free(0, 0)
            possible = {rules.hit(len(actions['transfers']), free) for free in range(minimum, rules.free_transfer_cap+1)}
            require(actions['transfer_hit'] in possible, 'transfers contradict hit points under every valid FT state')
        # Only the first GW has a verified starting squad/economics. Later transfer
        # sequences are retained assertions without invented intervening account history.
        if a['target_gameweek'] == s['personal']['squad']['target_gameweek']:
            held = {p['element'] for p in s['personal']['squad']['players']}
            for pair in actions['transfers']:
                require(pair['out'] in held and pair['in'] not in held, 'inconsistent executed transfer sequence')
                held.remove(pair['out']); held.add(pair['in'])
            if actions['squad'] is not None: require(held == set(actions['squad']), 'transfers contradict confirmed squad')
            if actions['transfer_hit'] is not None:
                require(actions['transfer_hit'] == rules.hit(len(actions['transfers']), s['personal']['squad']['free_transfers']), 'transfers contradict confirmed hits')
    return a


def with_identity(retained, ref):
    return {**retained, 'decision_identity': ref['identity']}


def confirmation_product(a, retained, attestation, previous=None):
    # The decision reference is inserted by callers/readers from the retention manifest.
    validate_assertion(a, retained, attestation['imported_at'])
    earliest = retained['attestation']['publication_checked_at']
    if previous:
        old = previous['assertion']
        require(a['target_gameweek'] == old['target_gameweek'], 'previous target mismatch')
        same(a['provenance']['kind'], old['provenance']['kind'], 'previous evidence kind mismatch')
        require(pd.timestamp(a['provenance']['declared_at'], 'declared') >= pd.timestamp(old['provenance']['declared_at'], 'previous declared'), 'extension declared time reversed')
        for field in FIELDS:
            if old['actions'][field] is not None: same(a['actions'][field], old['actions'][field], 'cannot revise confirmed '+field)
        if old['choice'] is not None: same(a['choice'], old['choice'], 'cannot revise confirmed intention')
        require(digest(a['actions']) != digest(old['actions']) or digest(a['choice']) != digest(old['choice']), 'extension adds no confirmation')
        earliest = previous['attestation']['publication_checked_at']
    t = timing(attestation['imported_at'], attestation['publication_checked_at'], earliest, retained['deadlines'][str(a['target_gameweek'])])
    same(attestation, t, 'confirmation timing mismatch')
    exclusions = list(retained['prospective_exclusions'])
    if t['late']: exclusions.append('confirmation recorded after target deadline')
    if a['provenance']['kind'] == 'synthetic': exclusions.append('synthetic confirmation')
    if previous: exclusions += previous['prospective_exclusions']
    selected = a['choice']['selected'] if a['choice'] else None
    components = {}
    if selected:
        week = next(w for w in retained['summary']['plans'][selected]['weeks'] if w['gameweek'] == a['target_gameweek'])
        for field in FIELDS:
            actual = a['actions'][field]
            expected = 'none' if field == 'chip' else week[field] if field != 'transfers' else None
            if actual is None: components[field] = 'unknown'
            elif field == 'transfers':
                components[field] = 'match' if sorted(p['in'] for p in actual) == sorted(week['transfers_in']) and sorted(p['out'] for p in actual) == sorted(week['transfers_out']) else 'divergent'
            else:
                components[field] = 'match' if (sorted(actual) == sorted(expected) if field in ('squad', 'starting_xi') else digest(actual) == digest(expected)) else 'divergent'
    status = ('no selected intention' if not selected else 'divergent' if 'divergent' in components.values() else
              'partial' if 'unknown' in components.values() else 'full declared match')
    missing = [k for k in ('squad', 'starting_xi', 'captain', 'transfer_hit', 'chip') if a['actions'][k] is None]
    return {'assertion': a, 'attestation': t, 'prospective_exclusions': sorted(set(exclusions)),
            'component_match': components, 'relationship_to_intention': status,
            'unscorable_fields': missing}


def confirmation_metadata(ref, previous, a, t):
    return {'kind': KINDS[1], 'contract': CONTRACT, 'retention': ref, 'previous': previous,
            'attestation': t, 'request_key': digest({'retention': ref, 'previous': previous, 'assertion': a})}


def confirm(retention, assertion, roots, output=Path('data/decision_reviews/confirmations'), previous=None):
    imported = live.stamp(live.now_utc)
    reader = Reader([*roots, output])
    rm, retained = reader.read(retention)
    require(rm['metadata']['kind'] == KINDS[0], 'expected retention')
    ref = pd.reference(retention, rm)
    retained = with_identity(retained, rm['metadata']['decision'])
    a = load_json(assertion)
    old, prev = None, None
    if previous:
        pm, old = reader.read(previous)
        require(pm['metadata']['kind'] == KINDS[1], 'previous is not a confirmation')
        same(pm['metadata']['retention'], ref, 'previous retention mismatch')
        prev = pd.reference(previous, pm)
    live.safe_output(output, retention, assertion, *([previous] if previous else []))
    key = confirmation_metadata(ref, prev, a, {})['request_key']
    reuse = cached(output, key, reader, KINDS[1])
    if reuse: return reuse
    deadline = retained['deadlines'].get(str(a.get('target_gameweek')))
    require(deadline is not None, 'target outside frozen horizon')
    t = timing(imported, live.stamp(live.now_utc), old['attestation']['publication_checked_at'] if old else retained['attestation']['publication_checked_at'], deadline)
    product = confirmation_product(a, retained, t, old)
    out, reused = write_products(output, confirmation_metadata(ref, prev, a, t),
        {'record.json': product, 'contract.json': CONTRACT, **render(KINDS[1], product)}, lambda: guard(t, deadline))
    return out, reused, product


def fixed_score(week, lookup):
    ids = week['starting_xi']+[week['captain']]
    if lookup is None: return {'status': 'pending', 'points': None}
    if any(e not in lookup or lookup[e] is None for e in ids): return {'status': 'unscorable outcome', 'points': None}
    xi = sum(lookup[e] for e in week['starting_xi']); cap = lookup[week['captain']]
    return {'status': 'scored', 'xi_points': xi, 'captain_bonus': cap, 'hit_points': week['transfer_hit'], 'points': xi+cap-week['transfer_hit']}


def total(values):
    return sum(values) if all(v is not None for v in values) else None


def difference(a, b):
    return a-b if a is not None and b is not None else None


def assemble(reader, retention_ref, retained, action_paths, settlement_paths):
    s = retained['summary']
    actions, action_refs, ancestors = {}, {}, set()
    # Include predecessor chains so extensions cannot erase earlier assertions.
    def add_action(path):
        m, p = reader.read(path)
        require(m['metadata']['kind'] == KINDS[1], 'expected confirmation')
        same(m['metadata']['retention'], retention_ref, 'confirmation belongs to another retention')
        ref = pd.reference(path, m)
        if ref['identity'] in action_refs:
            same(action_refs[ref['identity']], ref, 'conflicting confirmation bytes')
            return
        action_refs[ref['identity']] = ref
        actions[ref['identity']] = p
        if m['metadata']['previous']:
            ancestors.add(m['metadata']['previous']['identity'])
            add_action(reader.locate(m['metadata']['previous'], 'previous'))
    for path in action_paths: add_action(path)
    heads = {}
    for identity, action in actions.items():
        if identity in ancestors: continue
        gw = action['assertion']['target_gameweek']
        require(gw not in heads, 'competing confirmations for target; use an explicit monotone extension')
        heads[gw] = identity, action
    u = reader.locate(s['dependencies']['uncertainty'], 'uncertainty')
    um = verify_bundle(u, 'multi-uncertainty-forecast')
    product = load_json(u/'uncertainty.json')
    settled, refs = {}, {}
    for path in settlement_paths:
        outcomes, m = mo.load_settlement(path, u, um, product)
        gw = m['metadata']['target_gameweek']
        require(str(gw) in retained['deadlines'], 'settlement outside retained horizon')
        require(gw not in settled or settled[gw][0] == m['identity_sha256'], 'conflicting settlements for target')
        require(len({r['element'] for r in outcomes}) == len(outcomes), 'duplicate settled player')
        settled[gw] = m['identity_sha256'], {r['element']: r['target_points'] for r in outcomes}
        ref = pd.reference(path, m)
        if m['identity_sha256'] in refs:
            same(refs[m['identity_sha256']], ref, 'conflicting settlement bytes')
        refs[m['identity_sha256']] = ref
    forecasts = {(r['target_gameweek'], r['element']): r['xpts'] for r in s['empirical_player_intervals']['rows']}
    candidates = []
    for name in retained['candidate_order']:
        weeks = []
        for w in s['plans'][name]['weeks']:
            gw = w['gameweek']; lookup = settled[gw][1] if gw in settled else None
            scored = fixed_score(w, lookup)
            forecast = fixed_score(w, {e: v for (g,e),v in forecasts.items() if g == gw})['points']
            weeks.append({'gameweek': gw, **scored, 'forecast_points': forecast,
                          'settled_minus_forecast': difference(scored['points'], forecast),
                          'transfer_execution': 'hypothetical frozen path; no execution inferred',
                          'counterfactual_supported': False})
        horizon = total([w['points'] for w in weeks]); forecast = total([w['forecast_points'] for w in weeks])
        candidates.append({'candidate': name, 'weeks': weeks, 'horizon_points': horizon, 'forecast_horizon': forecast,
                           'settled_minus_forecast': difference(horizon, forecast)})
    for c in candidates:
        c['horizon_vs_baselines'] = {b['candidate']: difference(c['horizon_points'], b['horizon_points']) for b in candidates[:2]}
        for h, w in enumerate(c['weeks']):
            w['vs_baselines'] = {b['candidate']: difference(w['points'], b['weeks'][h]['points']) for b in candidates[:2]}
    confirmed = []
    for h, gwstr in enumerate(sorted(retained['deadlines'], key=int)):
        gw = int(gwstr); pair = heads.get(gw)
        if not pair:
            confirmed.append({'gameweek': gw, 'status': 'unconfirmed', 'points': None}); continue
        identity, action = pair
        a = action['assertion']['actions']
        scored = {'status': 'partial confirmation', 'points': None} if action['unscorable_fields'] else fixed_score(a, settled[gw][1] if gw in settled else None)
        forecast = None if action['unscorable_fields'] else fixed_score(a, {e: v for (g,e),v in forecasts.items() if g == gw})['points']
        confirmed.append({'gameweek': gw, 'confirmation_identity': identity, **scored,
                          'forecast_points': forecast, 'settled_minus_forecast': difference(scored['points'], forecast),
                          'relationship_to_intention': action['relationship_to_intention'],
                          'unscorable_fields': action['unscorable_fields'], 'prospective_exclusions': action['prospective_exclusions'],
                          'vs_baselines': {b['candidate']: difference(scored['points'], b['weeks'][h]['points']) for b in candidates[:2]}})
    confirmed_total = total([a['points'] for a in confirmed])
    retention_exclusions = sorted(set(retained['prospective_exclusions']))
    confirmation_exclusions = sorted({reason for action in actions.values() for reason in action['prospective_exclusions']})
    return ({'retention_identity': retention_ref['identity'], 'candidate_order': retained['candidate_order'],
             'prospective_exclusions': sorted(set(retention_exclusions) | set(confirmation_exclusions)),
             'retention_exclusions': retention_exclusions, 'confirmation_exclusions': confirmation_exclusions,
             'candidates': candidates, 'confirmed': confirmed,
             'confirmed_horizon_points': confirmed_total,
             'confirmed_horizon_vs_baselines': {b['candidate']: difference(confirmed_total, b['horizon_points']) for b in candidates[:2]},
             'pending_targets': sorted(int(g) for g in retained['deadlines'] if int(g) not in settled),
             'settled_targets': sorted(settled), 'evaluation': CONTRACT,
             'decision_value_claim': False},
            sorted(action_refs.values(), key=lambda r:r['identity']), sorted(refs.values(), key=lambda r:r['identity']))


def review_metadata(ref, actions, settlements):
    return {'kind': KINDS[2], 'contract': CONTRACT, 'retention': ref, 'confirmations': actions, 'settlements': settlements}


def review(retention, roots, actions=(), settlements=(), output=Path('data/decision_reviews/reviews'), previous=None):
    reader = Reader(roots)
    rm, retained = reader.read(retention)
    require(rm['metadata']['kind'] == KINDS[0], 'expected retention')
    ref = pd.reference(retention, rm)
    actions, settlements = list(actions), list(settlements)
    if previous:
        pm, _ = reader.read(previous)
        require(pm['metadata']['kind'] == KINDS[2], 'previous is not a review')
        same(pm['metadata']['retention'], ref, 'previous review retention mismatch')
        actions += [reader.locate(r, 'confirmation') for r in pm['metadata']['confirmations']]
        settlements += [reader.locate(r, 'settlement') for r in pm['metadata']['settlements']]
    live.safe_output(output, retention, *actions, *settlements, *([previous] if previous else []))
    product, ar, sr = assemble(reader, ref, retained, actions, settlements)
    out, reused = write_products(output, review_metadata(ref, ar, sr), {'record.json': product, 'contract.json': CONTRACT, **render(KINDS[2], product)})
    return out, reused, product


def verify(folder, roots):
    return Reader(roots).read(folder)


def replay(folder, roots, output):
    m, p = verify(folder, roots)
    live.safe_output(output, folder)
    def writer(out):
        for name in m['artifacts']: shutil.copyfile(Path(folder)/name, out/name)
    out, reused = publish(output, m['metadata'], writer)
    return out, reused, p


def render(kind, p):
    d = Document(); d.heading('Decision retention and outcome review', 1)
    d.paragraph(kind+' / '+CONTRACT['version'])
    d.paragraph(CONTRACT['scoring']); d.paragraph(CONTRACT['provenance']); d.paragraph(CONTRACT['counterfactual'])
    d.paragraph('Prospective exclusions: '+('; '.join(p['prospective_exclusions']) or 'none under local-clock policy; no causal benefit claim'))
    if kind == KINDS[0]:
        d.paragraph('Frozen candidates in original order: '+', '.join(p['candidate_order']))
        d.paragraph('Original full forecasts, simulation statistics, assumptions and timestamps: record.json → summary; original M5E report remains authoritative.')
        d.paragraph('Target deadlines: '+json.dumps(p['deadlines'], sort_keys=True))
    elif kind == KINDS[1]:
        d.paragraph('Choice is intention only: '+json.dumps(p['assertion']['choice'], sort_keys=True))
        d.paragraph('Target GW: '+str(p['assertion']['target_gameweek'])+'; declared action time: '+p['assertion']['provenance']['declared_at'])
        d.paragraph('Relationship to intention: '+p['relationship_to_intention'])
        d.paragraph('Confirmed fields (null means unknown): '+json.dumps(p['assertion']['actions'], sort_keys=True))
        d.paragraph('Unscorable fields: '+', '.join(p['unscorable_fields']))
    else:
        d.paragraph('Pending targets: '+(', '.join(map(str,p['pending_targets'])) or 'none'))
        for c in p['candidates']:
            d.heading(c['candidate'])
            d.table(['GW','Status','Forecast','Fixed-lineup settled','Error','vs no-transfer','vs greedy'],
                [[w['gameweek'],w['status'],w['forecast_points'],w['points'],w['settled_minus_forecast'],w['vs_baselines']['no_transfer'],w['vs_baselines']['greedy']] for w in c['weeks']])
            d.paragraph('Complete horizon points: '+str(c['horizon_points']))
        d.heading('Explicitly confirmed actions')
        d.table(['GW','Status','Fixed-lineup points','Intention relationship','Exclusions'],
                [[a['gameweek'],a['status'],a['points'],a.get('relationship_to_intention','unconfirmed'),'; '.join(a.get('prospective_exclusions',[]))] for a in p['confirmed']])
        d.paragraph('Complete confirmed horizon points: '+str(p['confirmed_horizon_points']))
        d.paragraph('No realised decision-value or official FPL score claim. Unconfirmed future transfers remain hypothetical.')
    if 'attestation' in p: d.paragraph('Actual recording: '+json.dumps(p['attestation'], sort_keys=True))
    return d.output()
