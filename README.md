# FPL AI Platform

Milestone 1 foundation for an AI-powered Fantasy Premier League analytics platform. The repository currently downloads public FPL data and turns it into local, analysis-friendly snapshots. It does **not** contain prediction or recommendation models.

## Quick start

Python 3.11 or newer is required. The ingestion pipeline and tests have no third-party runtime dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m fpl_ai --output-dir data
python -m unittest discover -v
```

The compatibility entry point is equivalent:

```bash
python main.py --output-dir data
```

An optional editable installation exposes the `fpl-ingest` command:

```bash
python -m pip install -e .
fpl-ingest --output-dir data
```

The command prints row counts and the absolute locations of the new raw and processed snapshot directories. Each run uses a UTC identifier such as `20260829T123000Z`.

TLS certificate verification is always enabled. If a python.org macOS installation has not loaded its optional certificate bundle, the client uses the operating system CA bundle when available.

## Repository structure

```text
.
├── data/
│   ├── raw/                 # Untouched API JSON, grouped by snapshot (ignored)
│   └── processed/           # CSV tables and manifest, grouped by snapshot (ignored)
├── fpl_ai/
│   ├── client.py            # Minimal HTTP client and endpoint definitions
│   ├── validation.py        # Required-field, ID, and relationship checks
│   ├── transform.py         # JSON-to-tabular transformations
│   ├── pipeline.py          # Snapshot orchestration and persistence
│   └── cli.py               # Command-line interface
├── notebooks/
│   └── exploration.ipynb    # Existing placeholder retained for future exploration
├── tests/                   # Deterministic unit/integration-style pipeline tests
├── DECISIONS.md             # Lightweight architecture decision record
├── PROJECT_STATE.md         # Current status and next handoff
├── PROJECT_VISION.md        # Long-term integrated product vision
├── ROADMAP.md               # Incremental delivery plan
├── main.py                  # Compatibility CLI entry point
└── pyproject.toml           # Python package and environment metadata
```

Generated data is intentionally ignored by Git. The `.gitkeep` files retain the raw/processed directory convention.

## Data sources

The pipeline makes two unauthenticated GET requests to the public endpoints used by the official FPL website:

| Endpoint | Use |
| --- | --- |
| `https://fantasy.premierleague.com/api/bootstrap-static/` | Player catalogue and current aggregate player statistics, teams, and player positions. |
| `https://fantasy.premierleague.com/api/fixtures/` | Full fixture schedule, gameweek assignment, kickoff time, teams, scores, status, and fixture difficulty. |

These endpoints are public but are not presented as a versioned, supported developer API. Their schema or availability can change. The client sends only two requests per run and does not require FPL credentials.

## Output datasets

For a snapshot `<id>`, the pipeline writes:

### Raw

- `data/raw/<id>/bootstrap-static.json`: the full bootstrap response, unchanged apart from JSON formatting.
- `data/raw/<id>/fixtures.json`: the full fixture response, unchanged apart from JSON formatting.

Raw snapshots preserve upstream fields for reproducibility and allow future transformations without re-downloading.

### Processed

- `data/processed/<id>/players.csv`: player identity, team and position labels, availability, price field, selection percentage, current FPL points, minutes, core match statistics, disciplinary statistics, ICT measures, and expected metrics.
- `data/processed/<id>/teams.csv`: team identity, strength fields, and any current table fields supplied by FPL.
- `data/processed/<id>/fixtures.csv`: gameweek, kickoff/status, readable home/away teams, scores, difficulties, and played minutes.
- `data/processed/<id>/manifest.json`: retrieval time, source URLs, generated files, and row counts.

Foreign keys are retained as IDs while readable team/position labels are added. CSV values preserve the API representation: for example, decimal-like metrics remain decimal strings and `now_cost` remains FPL's integer price field rather than embedding a currency conversion rule.

## Validation

Before anything is saved, the pipeline checks that:

- bootstrap players, teams, and positions are present and non-empty;
- required fields exist in every player, team, position, and fixture row;
- entity IDs are unique integers;
- every player references a known team and position;
- every fixture references two different known teams.

An empty fixtures array is accepted because it can be a legitimate state during a season transition. Download, JSON, and validation failures produce a concise error and a non-zero exit status.

## Assumptions and limitations

- This is a current-state snapshot, not a historical store or incremental updater.
- Data semantics and completeness are controlled by FPL; there is no schema-version guarantee.
- The two responses are retrieved sequentially and are not an atomic upstream snapshot. They could theoretically straddle an FPL update.
- CSV is used for inspectability and zero extra dependencies. Type inference is left to downstream readers.
- Snapshot IDs have one-second resolution. Re-running into the same output directory within the same second is rejected rather than overwriting data.
- No retry/backoff, cache, authentication, database, scheduler, orchestration framework, or external API layer is included yet.
- No FPL squad, transfer, scoring, chip, or budget rules are encoded. When those rules are needed, season-specific values will live in configuration rather than modelling code.

For wider context, [PROJECT_VISION.md](PROJECT_VISION.md) describes the long-term destination and integrated product vision; [ROADMAP.md](ROADMAP.md) describes the incremental development path; [PROJECT_STATE.md](PROJECT_STATE.md) describes what currently works and what comes next; and [DECISIONS.md](DECISIONS.md) records important architecture, product, and model decisions and their rationale.
