"""Deterministic, escaped Markdown and standalone HTML from one decision summary."""
from html import escape


def number(value):
    return f'{value:.3f}'


def money(value):
    return f'£{value/10:.1f}m ({value})'


def percent(value):
    return f'{100*value:.2f}%'


def md_text(value):
    return escape(str(value)).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ').replace('`', '&#96;').replace('*', '&#42;').replace('_', '&#95;').replace('[', '&#91;').replace(']', '&#93;')


class Document:
    def __init__(self):
        self.md, self.html = [], []

    def heading(self, title, level=2):
        self.md.append('#'*level+' '+md_text(title)+'\n')
        self.html.append(f'<h{level}>{escape(title)}</h{level}>')

    def paragraph(self, text):
        self.md.append(md_text(text)+'\n')
        self.html.append('<p>'+escape(text)+'</p>')

    def table(self, headers, rows):
        self.md.extend(['| '+' | '.join(map(md_text, headers))+' |', '| '+' | '.join('---' for _ in headers)+' |'])
        self.md.extend('| '+' | '.join(map(md_text, row))+' |' for row in rows)
        self.md.append('')
        self.html.append('<div class="table"><table><thead><tr>'+''.join('<th>'+escape(str(v))+'</th>' for v in headers)+'</tr></thead><tbody>')
        self.html.extend('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)
        self.html.append('</tbody></table></div>')

    def output(self):
        return {'report.md': '\n'.join(self.md)+'\n', 'report.html': '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Personal FPL decision report</title><style>
body{font:16px/1.55 system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1.2rem;color:#182c38;background:#fafcfb}
h1,h2,h3{line-height:1.2;color:#153f36}h2{margin-top:2.5rem;border-top:2px solid #dbe6e0;padding-top:1rem}
.table{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem;margin:.8rem 0}th,td{text-align:left;border-bottom:1px solid #dbe6e0;padding:.55rem;vertical-align:top}th{background:#eaf1ec}p{max-width:100ch}td{overflow-wrap:anywhere}@media print{body{font-size:10pt}h2,h3{break-after:avoid}.table{overflow:visible}}
</style></head><body><main>'''+ '\n'.join(self.html)+'</main></body></html>\n'}


def render(summary):
    s = summary
    d = Document()
    players = s['population']
    def player(e):
        p = players[str(e)]
        return f"{p['name']} [{p['season']}:{e}]"
    def names(ids): return ', '.join(player(e) for e in ids)
    d.heading('Personal FPL decision report', 1)
    d.paragraph(s['label']+' — '+('Offline snapshot/what-if; not a pre-deadline decision record.' if s['config']['mode'] == 'snapshot' else 'Locally recorded before the bound deadline; user assertions are not independently witnessed.'))
    if s['personal']['provenance']['kind'] == 'synthetic':
        d.paragraph('SYNTHETIC DEMONSTRATION — this is not the user’s squad or personalised advice.')
    d.heading('Read these limitations first')
    for text in s['limitations']: d.paragraph(text)
    d.heading('Supplied team and account state')
    state = s['personal']['squad']
    d.paragraph(f"Season {state['season']}; target GW {state['target_gameweek']}; bank {money(state['bank'])}; available FTs {state['free_transfers']}. FTs include target-GW accrual, before any target-GW transfer. No already-made transfers, incurred hits or active chip.")
    d.paragraph('Personal provenance: '+s['personal']['provenance']['source'])
    d.paragraph(f"Planning horizon {s['config']['planning']['effective_horizon']} GWs (requested {s['config']['planning']['horizon']}); maximum {s['config']['planning']['max_transfers']} transfers per GW; returned {s['returned_exact_paths']} exact paths of at most {s['config']['planning']['top_n']} requested.")
    positions = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
    d.table(['Player / ID', 'Club', 'Position', 'Exact selling value', 'Frozen purchase price', 'Can select'],
            [[player(p['element']), s['clubs'][str(players[str(p['element'])]['team'])], positions[players[str(p['element'])]['position']], money(p['selling_price']),
              money(players[str(p['element'])]['purchase_price']), players[str(p['element'])]['can_select']] for p in state['players']])
    d.heading('Separate evidence times and freshness')
    times = s['timing']
    d.table(['Event', 'Time / value'], [[k, times.get(k, "pending")] for k in ('snapshot_capture', 'personal_observed_at', 'imported_at', 'projection_computed_at',
             'simulation_started_at', 'simulation_computed_at', 'created_at', 'publication_checked_at', 'first_target_deadline', 'snapshot_age_hours_at_creation', 'personal_age_hours_at_creation', 'created_after_deadline')])
    snapshot = times['snapshot_requests']
    d.table(['Source request', 'Requested', 'Received'], [[k, snapshot[k]['requested_at'], snapshot[k]['received_at']]
             for k in ('bootstrap_timing', 'fixtures_timing') if k in snapshot])
    forecast = times['forecast_computation']
    d.table(['M4E forecast timing', 'Value'], [[k, v] for k, v in sorted(forecast.items()) if ('_at' in k or 'timing' in k) and not isinstance(v, (dict, list))])
    d.paragraph('created_at records report creation start. publication_checked_at records the local deadline/freshness check after initial rendering and before sealing. A later unretained guard checks again before atomic rename. Neither timestamp proves the exact publication time; the local clock is not an independent or external witness.')
    d.paragraph('The upstream simulation records start/computation attestations and a pre-deadline publication gate, not a separate final publication timestamp. No file mtime is treated as an observation time.')
    d.paragraph(f"Retained history sources: {s['retained_history_count']}. Report creation is not market capture or forecast refresh.")
    d.heading('Highest-ranked plan under the unchanged forecast objective')
    best = s['plans'][s['highest_ranked']]
    first = best['weeks'][0]
    action = ('Sell '+names(first['transfers_out'])+'; buy '+names(first['transfers_in'])) if first['transfer_count'] else 'Roll — no transfers'
    d.paragraph(f"{s['highest_ranked']}: {number(best['total_points'])} expected net points over the horizon. First GW: {action}. Hit {first['transfer_hit']}; bank {money(first['resulting_bank'])}; FT {first['free_transfers_before']} → {first['next_free_transfers']}.")
    d.paragraph('Starting XI: '+names(first['starting_xi'])+'. Captain: '+player(first['captain'])+'. Bench membership: '+names(first['bench_order'])+'. Autosub order and vice-captain substitutions are not simulated.')
    d.heading('Comparable forecast objectives')
    d.table(['Candidate', 'Forecast objective', 'Gain vs no transfer', 'Gain vs greedy', 'Hits', 'Transfers'],
            [[n, number(p['total_points']), number(p['total_points']-s['plans']['no_transfer']['total_points']), number(p['total_points']-s['plans']['greedy']['total_points']), p['total_hit_cost'], p['transfer_count']] for n, p in s['plans'].items()])
    d.heading('Common-scenario uncertainty — separate quantities')
    ev = s['simulation']
    d.paragraph(f"{ev['scenario_count']} scenarios; seed {s['config']['planning']['seed']}. Analytical expectation includes empirical residual bias; Monte Carlo estimates approximate that law. The independent null is diagnostic only and does not select a plan.")
    d.paragraph('Lower 10% mean integrates exactly 10% of empirical probability mass, using a fractional boundary observation. Win/tie/loss use strict binary64 comparison, independent of optimiser tie tolerance. Highest-return credit splits equally among tied supplied entries.')
    d.paragraph('Duplicate path entries: '+str(ev['duplicate_path_entries']))
    for model, result in ev['models'].items():
        d.heading(model, 3)
        d.table(['Candidate', 'Forecast', 'Analytical expectation', 'MC mean', 'MC mean SE', 'Median', 'SD', 'P10', 'P90', 'Lower 10% mean', 'Highest split / inclusive / sole'],
                [[n, number(ev['M5B_forecast_objectives'][n]), number(ev['analytical_simulation_expectation'][n]), number(m['mean']), number(m['mean_mc_standard_error']), number(m['median']), number(m['sd']), number(m['p10']), number(m['p90']), number(m['lower_tail_mean_10pct']),
                  ' / '.join(percent(m[k]) for k in ('probability_highest_split_ties', 'probability_highest_including_ties', 'probability_sole_highest'))] for n, m in result['metrics'].items()])
        d.table(['Candidate', 'Baseline', 'Paired mean gain', 'Gain P10 / P90', 'Win / tie / loss', 'Win probability MC SE'],
                [[n, b, number(m['vs_'+b]['mean']), number(m['vs_'+b]['p10'])+' / '+number(m['vs_'+b]['p90']),
                  ' / '.join(percent(m['vs_'+b]['probability_'+k]) for k in ('win', 'tie', 'loss')), percent(m['vs_'+b]['win_probability_mc_standard_error'])]
                 for n, m in result['metrics'].items() for b in ('no_transfer', 'greedy')])
    d.paragraph('Displayed points are rounded to three decimals. Full precision arithmetic is retained in summary.json; XI, captain and hit decompositions reconcile with the forecast objective up to binary64 rounding.')
    d.heading('Every conditional Gameweek plan')
    for n, p in s['plans'].items():
        d.heading(n, 3)
        for w in p['weeks']:
            move = ('Sell '+names(w['transfers_out'])+'; buy '+names(w['transfers_in'])) if w['transfer_count'] else 'Roll — no transfers'
            d.paragraph(f"GW{w['gameweek']}: {move}. Projected net {number(w['net_points'])}; XI contribution {number(w['gross_xi_points'])}; captain bonus {number(w['captain_bonus'])}; hit {w['transfer_hit']}. Bank {money(w['resulting_bank'])}; FT before {w['free_transfers_before']}, used {w['free_transfers_used']}, unused {w['free_transfers_rolled']}, next GW after accrual/cap {w['next_free_transfers']}.")
            d.paragraph('XI: '+names(w['starting_xi'])+'. Captain: '+player(w['captain'])+'. Bench membership: '+names(w['bench_order'])+'.')
        for baseline, comparison in s['decomposition'][n].items():
            d.paragraph('Numerical explanation versus '+baseline+' (not a model feature attribution or player-specific causal explanation).')
            d.table(['GW', 'XI contribution change', 'Captain bonus change', 'Hit change', 'Net gain'],
                    [[w['gameweek'], *[number(w[k]) for k in ('xi_change', 'captain_bonus_change', 'hit_change', 'net_change')]] for w in comparison['weeks']]+
                    [['Horizon', *[number(comparison['horizon'][k]) for k in ('xi_change', 'captain_bonus_change', 'hit_change', 'net_change')]]])
    d.heading('Empirical player intervals (M5C; not plan confidence scores)')
    involved = {e for p in s['plans'].values() for w in p['weeks'] for e in w['squad']}
    d.paragraph('Shown for players held in supplied plans. Full marginal and cumulative M5C outputs, with availability reasons, are retained separately in summary.json. These endpoints are never summed into team intervals.')
    d.table(['Player', 'GW', 'Point forecast', '50% interval', '80% interval', '90% interval'],
            [[player(r['element']), r['target_gameweek'], number(r['xpts']),
              *[f"{number(r['intervals'][level]['lower'])} to {number(r['intervals'][level]['upper'])}" if r['intervals'][level]['lower'] is not None else 'Unavailable' for level in ('50', '80', '90')]]
             for r in s['empirical_player_intervals']['rows'] if r['element'] in involved and r['horizon'] < s['config']['planning']['effective_horizon']])
    d.heading('Exact pinned evidence')
    d.table(['Role', 'Identity', 'Manifest SHA-256'], [[k, v['identity'], v['manifest_sha256']] for k, v in sorted(s['dependencies'].items())])
    return d.output()


def terminal(summary, folder, reused=False):
    best = summary['plans']['exact_1']
    w = best['weeks'][0]
    name = lambda e: f"{summary['population'][str(e)]['name']} [{e}]"
    moves = 'Roll' if not w['transfer_count'] else 'Sell '+', '.join(map(name, w['transfers_out']))+'; buy '+', '.join(map(name, w['transfers_in']))
    return '\n'.join([f"{'Verified reuse' if reused else 'Published'}: {summary['label']}; {summary['returned_exact_paths']} exact paths.",
        f"Highest-ranked forecast objective {best['total_points']:.3f}; no transfer {summary['plans']['no_transfer']['total_points']:.3f}; greedy {summary['plans']['greedy']['total_points']:.3f}.",
        f"GW{w['gameweek']}: {moves}. Captain {name(w['captain'])}; hit {w['transfer_hit']}; bank {money(w['resulting_bank'])}; FT {w['free_transfers_before']} → {w['next_free_transfers']}.",
        'Conditional frozen-state plans; simulation does not reorder them. See report limitations and source ages.',
        f'HTML: {folder}/report.html', f'Markdown: {folder}/report.md', f'Machine summary: {folder}/summary.json'])
