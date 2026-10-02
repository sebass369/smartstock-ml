# Documentation

This directory contains project assumptions, privacy rules, the Phase 3 through Phase 4B data dictionary, and project decisions.

`data_dictionary.md` documents the deterministic synthetic-demand, inventory, and recommendation CSV contracts, reproducibility rules, privacy limits, and leakage boundaries.

`ordering_policy.md` explains the Phase 4B recommendation timing, formulas,
warm-up behavior, conservative expiration rule, and synthetic scenario
comparison in student-friendly language.

`phase_5_validation.md` records the Phase 5 validation scope, regression
anchors, automated checks, manual review boundaries, and excluded behavior.

`forecasting.md` defines the Phase 7A demand target, chronological evaluation,
baseline and candidate formulas, leakage boundary, metrics, in-memory record
contract, and separation from ordering.

`ml_forecasting.md` defines the Phase 7B trained linear model: the daily
problem formulation, the two-feature leakage-safe contract, why
`is_high_demand_day` is excluded, why ordinary least squares is used instead of
Ridge regression, the separate record contract, the reproducibility rules, and
the honest expected result.

The Phase 6 exploratory analysis is available in
[`notebooks/phase_6_exploratory_analysis.ipynb`](../notebooks/phase_6_exploratory_analysis.ipynb).
It demonstrates the existing deterministic pipeline with synthetic in-memory
records and does not introduce forecasting, machine learning, or optimization.

The separate Phase 7A forecasting notebook evaluates deterministic 14-day demand
forecasts without changing the Phase 6 analysis or the Phase 4B policy.

The separate Phase 7B notebook adds the trained linear model and compares it
against both Phase 7A methods on the same 27 product-cycle records.

All documentation must stay privacy-safe. Do not add real operational data, private documents, store identifiers, company names, credentials, or internal records.
