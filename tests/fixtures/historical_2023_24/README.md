# Pinned 2023/24 test excerpts

CSV files preserve each real header and the first data row, reserialized with
Python's CSV writer, from Vaastav commit
`9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`. Paths are under `data/2023-24/`
(`merged_gw.csv` is under `gws/`). These are shape/type fixtures, not a relationally
complete season. Full-source SHA-256 values:

- `fixtures.csv`: `d8521bdbb80edb5141bc17df71bf6026275f2e56fd6a6dc6041b3ae23a39ce6a`
- `merged_gw.csv`: `e9c09c8856f1c86b4f920f46ddd5033af83409439dfda53be925df2a3e7c8a9e`
- `players_raw.csv`: `43d8cf5efb3d901f2499558c40b392b7f0ee22afe28030f36266ad29024c63d9`
- `teams.csv`: `7795f091ccea17fda0752cb07b935e1515b09a9d3f924147997cbf28139edd49`

`settlement_events.json` preserves only the GW38 event object from
Randdalf/fplcache commit `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`, at
`cache/2024/5/20/0121.json.xz` and `cache/2024/5/20/0625.json.xz`.
Wrapper capture timestamps are derived from these archive paths as UTC.
The earlier event is unfinished and unchecked; the later event is finished and
checked. Other payload fields are intentionally omitted for this focused test.

Full source usage context: [DATA_NOTICE.md](../../../DATA_NOTICE.md).
