# Pinned 2022/23 regression excerpts

The four CSVs contain the exact header and first data row downloaded from
Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`, under `data/2022-23/`
(`merged_gw.csv` is under `gws/`). They exercise real source types and column order.
They are independent samples, not a relational miniature season.

The JSON excerpts come from Randdalf/fplcache revision
`33dac28d18953bee5bc4bd56ddd8a5e32e169d68`. Each records its original archive path.
`settlement_events.json` preserves GW38 event objects from the pre-deadline,
unsettled overnight, and settled morning captures. `player_code_changes.json`
preserves identity fields for Luke Harris and Hugo Bueno from accepted GW1 and
GW2 captures. Only their person codes change between these excerpts; observed
names, team and position remain equal. Tests preserve the earlier code and require
an exact season/gameweek/element/code-pair/source-path exception.

Full ignored raw files, frozen provenance and rebuild evidence are described in
[the verification record](../../../docs/M2_2022_23_VERIFICATION.md).
