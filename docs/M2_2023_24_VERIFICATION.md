# Milestone 2 — 2023/24 acceptance evidence

Verified 2026-09-16 on `feat/m2-2023-24-season-support`. No commit or publication
was performed. The working tree was clean at the start; the 53-test baseline passed.

## Immutable sources and observed differences

Both seasons use Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88` and
fplcache `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`. These existing immutable
pins were retained after inspecting the real 2023/24 data; no moving ref was used.
The complete, non-truncated fplcache tree exposes the same
`cache/YYYY/M/D/HHMM.json.xz` layout. Filename timestamps are interpreted as UTC,
as in the existing archive contract.

The four Vaastav inputs are `data/2023-24/gws/merged_gw.csv`,
`data/2023-24/players_raw.csv`, `data/2023-24/teams.csv`, and
`data/2023-24/fixtures.csv`. Their observed row counts are respectively
29,725, 865, 20, and 380. All rows executed the selected schema's declared types
and mappings. The fixture and team headers exactly match 2024/25. Differences:

- The merged header omits all seven `mng_*` columns and `modified`.
- Player metadata omits the seven manager columns plus `birth_date`, `can_select`,
  `can_transact`, `has_temporary_code`, `opta_code`, `region`, `removed`, and
  `team_join_date`.
- All fixture positions are GK/DEF/MID/FWD; the older schema rejects AM.
- Starts and all four expected-goals/assists metrics are present. They retain the
  existing nullable contracts; absent optional values are never replaced by zero.
- Ownership, value, and transfer fields remain quarantined; the canonical
  `modified` column is null for all 29,725 rows. Vaastav `xP` remains unmappable.

The schema declares these observed differences over a deep copy of the common
contract. No generic pipeline or canonical table changes were needed.

## Deadline and settlement evidence

The reference capture `cache/2024/5/19/1233.json.xz` supplies all 38 deadlines.
The existing selector accepted the latest qualifying capture for every gameweek:
exact deadline match, `is_next`, strictly before deadline, and after the previous
deadline. Captures precede deadlines by 8 minutes to 6 hours 10 minutes. Coverage
is 38/38, with no interpolation or backfill. All 29,510 deadline rows have complete
team/position identity from their accepted captures; 23 elements have multiple
observed deadline teams. No post-event fixture/result context enters this table.

At `cache/2024/5/20/0121.json.xz`, GW38 is still `finished=false` and
`data_checked=false`. The pipeline rejected it before publication. At
`cache/2024/5/20/0625.json.xz` both flags are true; this is the configured final
settlement. Small real event excerpts are included in the offline test fixtures.

Required reconciliation retains threshold `1.0`: **28,742 eligible, 28,742
compared, 28,742 matching, zero unmatched, zero mismatching**. The same fixture
aggregation and next-accepted-deadline comparison strategy works unchanged.
All 40 hard quality checks pass, including primary keys, cross-table references,
fixture context consistency, capture timing, schema drift, types, and audit counts.

## Identity and row counts

### 2023-24

- Build: `v3-9779cdbc0c07-33dac28d1895-build-7886af1a34dd`
- Source identity: `adfc64c1be2725e4ccc68b3366e615f1b007a8f7583698b0f58e9f2335e2cb9a`
- Build identity: `7886af1a34dd6293e9ea8bfb8c4b94eedd3bcee2c75f7f93d4a98eef390e35e8`
- Frozen inventory SHA-256: `1774f4b05981a9b5ff03af0c2979faf4ae7d276fe69a90bb73a550d2a1d1366b`
- Consumed inventory records: 44; mutable cache records: 45.

| Table | Rows |
| --- | ---: |
| fixtures | 380 |
| gameweeks | 38 |
| player_deadline_snapshots | 29,510 |
| player_fixture_facts | 29,725 |
| players | 865 |
| quarantined_source_metadata | 29,725 |
| teams | 20 |
### 2024-25

- Build: `v3-9779cdbc0c07-33dac28d1895-build-1fbdcc84c93d`
- Source identity: `d94912c4423cd0f7ffb8b1fbaf4ff4493450f772af7d1258f9cfe5bea5a89f69`
- Build identity: `1fbdcc84c93d92367c3f6f2a0b39d039dc04403980bb100491410523c62f9d86`
- Frozen inventory SHA-256: `ccee8444e994e81cf4d1d0dc1bde04c4bbeb9eeace50c570dd1d007a3169840c`
- Consumed inventory records: 44; mutable cache records: 44.

| Table | Rows |
| --- | ---: |
| fixtures | 380 |
| gameweeks | 38 |
| player_deadline_snapshots | 27,479 |
| player_fixture_facts | 27,605 |
| players | 804 |
| quarantined_source_metadata | 27,605 |
| teams | 20 |

The 2023/24 inventory contains four CSVs, the complete discovery tree, 38 accepted
captures (including the deadline reference), and one final settlement capture.
The earlier unsettled capture is excluded. Fresh rebuilding without that unused
cache record produces the same source identity, proving it cannot influence the
successful build. Metadata timestamps and absolute paths are not identity inputs.

## Verification performed

All of the following passed:

```bash
.venv/bin/python -m fpl_ai historical --season 2023-24 --output-dir data
.venv/bin/python -m fpl_ai historical --season 2024-25 --output-dir data
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q fpl_ai tests main.py
.venv/bin/python -m fpl_ai --help
.venv/bin/python -m fpl_ai historical --help
git diff --check
```

The suite contains 60 network-free tests: 53 existing tests plus seven covering
real 2023/24 headers and rows, missing optional values, forbidden fields, invalid
types/AM positions, schema drift, season applicability, the 2024/25 build identity,
actual GW38 settlement flags, and older-shape pipeline reuse without writes.

Additional live-data verification used `run_historical_pipeline` with a fetcher
that raises on every network request. Both existing builds reused successfully;
SHA-256 and nanosecond modification times of every file under `data/historical`
were unchanged. `load_historical_build` verified the catalogue, manifest, raw and
processed checksums for both builds and the 2024/25 v5 compatibility build
`v3-9779cdbc0c07-33dac28d1895-build-105600b4135e`.

Fresh temporary output directories were then built through an injected fetcher
mapping recorded source URLs to the existing raw bytes. Each fresh build matched
both original identity hashes and all seven original CSV hashes below. Immediate
reuse with a rejecting fetcher preserved every fresh file's hash and mtime.
This tests the full transform path independently of the successful-build shortcut.
The same checks can be repeated after the normal command has populated the cache:

```python
import json
import tempfile
from pathlib import Path
from fpl_ai.historical_io import sha256_file
from fpl_ai.historical_pipeline import run_historical_pipeline, load_historical_build

def offline(url):
    raise AssertionError(f"unexpected network request: {url}")

for season in ("2023-24", "2024-25"):
    existing = run_historical_pipeline(season, "data", fetcher=offline)
    assert existing.reused
    load_historical_build(season, existing.version, "data")
    records = json.loads((existing.raw_dir / "source_manifest.json").read_text())["files"]
    sources = {r["source_url"]: (existing.raw_dir / r["raw_path"]).read_bytes() for r in records}
    with tempfile.TemporaryDirectory() as output:
        fresh = run_historical_pipeline(season, output, fetcher=sources.__getitem__)
        original = json.loads((existing.processed_dir / "manifest.json").read_text())
        rebuilt = json.loads((fresh.processed_dir / "manifest.json").read_text())
        for key in ("source_identity_sha256", "build_identity_sha256"):
            assert original[key] == rebuilt[key]
        for csv in existing.processed_dir.glob("*.csv"):
            assert sha256_file(csv) == sha256_file(fresh.processed_dir / csv.name)
        before = {p: (sha256_file(p), p.stat().st_mtime_ns)
                  for p in Path(output).rglob("*") if p.is_file()}
        assert run_historical_pipeline(season, output, fetcher=offline).reused
        assert before == {p: (sha256_file(p), p.stat().st_mtime_ns)
                          for p in Path(output).rglob("*") if p.is_file()}
```

## Canonical CSV SHA-256 checksums

These hashes matched the fresh rebuilds. In particular, every 2024/25 hash matches
the existing pre-batch verified build; its source/build identities also remain unchanged.

### 2023-24

| Artifact | SHA-256 |
| --- | --- |
| fixtures.csv | `107a1d3b92639f7eb5f55f3fb5e747cbdbcc1c25417cbc9c46000bedf51f0def` |
| gameweeks.csv | `e412079827c4efb65e8451df7e8453e6460eeb64a68986c6df96527e97a2ef1e` |
| player_deadline_snapshots.csv | `147e275e5740afec57afcbd9b5bc6abc0606664dbfa8ffc6403912d1fa7a72d0` |
| player_fixture_facts.csv | `0df65458dff40414bb847785a16e34b76c8630060901fc8f04981bb207047b7f` |
| players.csv | `04e01295bab2517443ead2e42f4bbf7ef5519c9fd8b5c12812ac0df14cde3f2f` |
| quarantined_source_metadata.csv | `67451659ca16e65515a106a5b699f66f846a8d53dd925b1cd532466295860c4e` |
| teams.csv | `42730f6ac029bcb7dd093782b849702425bc8e86aa8bc3f720353a2fda1d8a36` |
### 2024-25

| Artifact | SHA-256 |
| --- | --- |
| fixtures.csv | `f16b12e35243062373ab0c70b8aab0eca2d71097e9b0d91193b96a8bac35f070` |
| gameweeks.csv | `5239b2ad9505d81989cb2beee6bc45bbd6a268521405d846b3f98993e1ac791c` |
| player_deadline_snapshots.csv | `bec32e2e82ac3ac2fdf6628a0a6657ed948d2f996807feeb7f25c167bca93b74` |
| player_fixture_facts.csv | `677d15f5f1c3b092e086db1414f57ad9ebeb0134d5795d996be6dc0d7d7e9159` |
| players.csv | `0a0b8b31ae36adba55b89ac6fa822593821e70e1bc46350ca902c10687d0740d` |
| quarantined_source_metadata.csv | `7b7400ec405ecb3a7733af2c44cb81974d3383658fda694a63335dfd8cda11b0` |
| teams.csv | `aa44bb9410908c2af8cabddf7678fbcf1bfd5804472141fcd7dcc404f02e53f4` |

## Limits and next handoff

Periodic archive captures are not exact-deadline observations; their age is reported,
with no added freshness guarantee. Capture times retain the UTC filename assumption.
Three accepted rows have null FPL `ep_next`; availability and set-piece fields also
contain genuine source nulls. No value is filled from final-season metadata.
Final fixtures remain post-event context; fixture-list snapshots are unavailable.
Cross-season person modelling and feature engineering are outside this batch.
Generated full data remains Git-ignored; checked-in tests retain only small excerpts.
There are no unresolved acceptance failures.

Recommended next batch: add and verify 2022/23, specifically auditing its
fixture-empty GW7, snapshot coverage, and settled comparison availability before
choosing its policy. Do not start modelling yet.

## Changed files

- `fpl_ai/historical_sources.json`: 2023/24 pins, source paths, counts, and strict policy.
- `fpl_ai/historical_schema.py`: inspected 2023/24 schema definition.
- `fpl_ai/cli.py`: supported-season help text.
- `tests/test_historical_2023_24.py`: seven deterministic regression/failure tests.
- `tests/fixtures/historical_2023_24/`: four CSV excerpts, settlement event JSON, and provenance README.
- `README.md`, `PROJECT_STATE.md`, `ROADMAP.md`, `DECISIONS.md`: current support and handoff.
- `docs/M2_2023_24_VERIFICATION.md`: this acceptance and reproducibility record.
