# Pinned 2025/26 regression excerpts

The four CSVs retain the exact header and first data row from Vaastav revision
`9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`, under `data/2025-26/`
(`merged_gw.csv` is under `gws/`). They exercise real schemas rather than fabricated
column contracts; full files remain in the ignored immutable raw store.

`events.json` contains only event 38 from four captures at fplcache revision
`33dac28d18953bee5bc4bd56ddd8a5e32e169d68`. Each entry records the original compressed
file SHA-256 and path. These are payload excerpts, not replacement raw captures.
They prove the pre-deadline 08:39 eligibility, post-deadline 13:49 rejection despite
`is_next`, and May 25 04:38 unsettled versus 10:23 settled flags.

Full investigation provenance, duplicate-row evidence and overlapping renamed
player histories are in `docs/M2_2025_26_SOURCE_AUDIT.json`. The generic integration
fixture is synthetic and intentionally retains the common test's 2024 timestamps;
it tests transformation contracts, not real season coverage.
