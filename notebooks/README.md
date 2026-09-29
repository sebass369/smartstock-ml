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

## Phase 7A — Baseline Forecast Evaluation

`phase_7_forecasting.ipynb` evaluates the previous-cycle baseline and expanding
weekday-mean candidate for three complete 14-day forecast cycles. It imports the
reusable forecasting functions, keeps forecast records in memory, and reports
MAE, WAPE, and product-level wins, ties, and losses.

Neither method is a trained machine-learning model. Phase 7B — Simple Machine
Learning Model is future work and is not implemented in this notebook.

The notebook is separate from Phase 6 so descriptive analysis and predictive
evaluation retain clear boundaries. Outputs remain cleared, and all limitations
about synthetic data and the small evaluation sample are stated in the notebook.
