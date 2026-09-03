# Data

This directory is reserved for generated and sample synthetic data only.

- `generated/`: reproducible generated datasets. CSV files in this directory are ignored by Git and can be recreated from configuration and a seed.
- `sample/`: future small privacy-safe examples for review.

Run `python -m smartstock.generator` from the repository root to create the default Phase 3 CSV. Do not commit generated CSV files. Keep `generated/.gitkeep` so the empty directory remains in the repository.

Phase 3 files contain synthetic demand scenarios only. They do not contain inventory, fulfillment, waste, expiration, stockout, or ordering outcomes.

Do not add real operational data, private documents, store identifiers, company names, credentials, or internal records.
