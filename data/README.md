# Data

This directory is reserved for generated and sample synthetic data only.

- `generated/`: reproducible generated datasets. CSV files in this directory are ignored by Git and can be recreated from configuration and a seed.
- `sample/`: future small privacy-safe examples for review.

Run `python -m smartstock.generator` from the repository root to create the default Phase 3 CSV. Do not commit generated CSV files. Keep `generated/.gitkeep` so the empty directory remains in the repository.

Run `python -m smartstock.inventory` to create the separate default Phase 4A CSV at `data/generated/synthetic_inventory_records.csv`. It contains the six Phase 3 fields followed by fixed-input inventory, fulfillment, expiration, waste, and stockout outcomes. Fixed deliveries are scenario inputs, not recommendations.

Run `python -m smartstock.ordering` to create the separate Phase 4B CSV at
`data/generated/synthetic_order_recommendations.csv`. It contains 27 default
recommendations for three delivery dates and nine approved products. The command
keeps the fixed-versus-policy comparison in memory and prints only its overall
synthetic metrics.

Phase 3 files contain synthetic demand scenarios only. They do not contain inventory, fulfillment, waste, expiration, stockout, or ordering outcomes.

The default Phase 4A output has zero expiration and waste because its 56-day duration is shorter than every approved unopened shelf life. Focused tests verify expiration with shorter synthetic shelf lives. Phase 4A contains no forecasting, machine learning, optimization, baseline ordering policy, or ordering recommendations. Phase 4B adds only the approved transparent baseline policy; it does not add forecasting, machine learning, or optimization.

Do not add real operational data, private documents, store identifiers, company names, credentials, or internal records.
