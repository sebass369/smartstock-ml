# Notebooks

This directory contains privacy-safe Google Colab demonstrations that use the
reusable SmartStock ML package.

Notebooks should import reusable code from `src/smartstock/` instead of duplicating business logic. Do not add real operational data, private documents, store identifiers, company names, credentials, or internal records.

## Phase 6 exploratory analysis

`phase_6_exploratory_analysis.ipynb` demonstrates the deterministic synthetic
demand, fixed-inventory, baseline-policy, recommendation, and scenario-comparison
pipelines. It uses the validated repository configuration and seed 42.

Open the notebook in a fresh Google Colab runtime and run all cells from top to
bottom. The setup requires network access only to clone the public repository
and install the approved Python dependencies. No local file upload, Google Drive
connection, generated CSV, external dataset, or credential is required.

The notebook is committed with outputs cleared. Every result is synthetic and
must not be treated as operational, ordering, or food-safety guidance. The
baseline policy is not a forecasting model or an optimization system.
