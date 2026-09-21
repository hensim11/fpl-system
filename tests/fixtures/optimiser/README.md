# Synthetic GW6 squad — not the user's team

`demo_gw6_squad.json` is a deterministic verification fixture against the retained
2026/27 GW6 M4E forecast. Players were selected by ascending element ID within
position, skipping clubs already at three players. Selling prices are deliberately
synthetic: the bound purchase price minus one tenth. Bank is 10 (£1.0m), with one
free transfer. These are not observations of any account or its purchase history.

Copy the JSON and replace **every** held element and selling price, bank, free
transfers, season and target Gameweek with your actual state before real use.
All money fields use integer £0.1m units, not decimal millions or pounds.
