# Phase 5 Validation

## Purpose

Phase 5 strengthens confidence in the existing deterministic SmartStock ML
pipeline. It validates data rules, inventory balances, nonnegative quantities,
and full-pack constraints without changing valid Phase 3, Phase 4A, or Phase 4B
behavior.

The work remains a synthetic portfolio exercise. It does not provide
operational guidance or evidence of real-world improvement.

## Approved automated checks

The test suite covers:

- Configuration structure, approved aliases, supported values, and numeric
  types.
- Deterministic demand generation and isolated seeded randomness.
- Continuous dates, stable product order, and the 14-day Tuesday cycle.
- FIFO inventory consumption, expiration boundaries, stockouts, and inventory
  balance.
- Nonnegative demand, inventory, waste, delivery, and recommendation values.
- Full-pack delivery and recommendation constraints.
- Previous-cycle recommendation history without current-day or future-demand
  leakage.
- Nonzero safety stock conversion from packs to units.
- Warm-up deliveries and policy deliveries replacing fixed deliveries.
- Exact default scenario-comparison metrics.
- UTF-8 CSV output without a byte-order mark, LF-only line endings, one final
  newline, stable columns, and stable row order.
- Validation of all demand CSV record shapes before an output path is created.
- Privacy-safe output schemas containing only approved public aliases.
- CLI defaults, seed overrides, successful output, and failure behavior.

## Regression anchors

The existing byte-level contracts remain unchanged:

- Phase 3 SHA-256:
  `46f6762dc900f4fb3b965b97773d3147b288d17c1ec044c2c487372cc5e55096`
- Phase 4A SHA-256:
  `2cf57c1916024d754ea0ebafafacc74b272cda1b58ec9f5ea78bc70aa4b4d3d0`
- Phase 4B SHA-256:
  `6837650452c0266acb8b558212a0d14b9aa2e8ed35a22511c80c1fe18ebd3267`

The default scenario comparison is pinned from the evaluation window beginning
on January 21, 2025:

| Metric | Fixed scenario | Policy scenario |
| --- | ---: | ---: |
| Fulfilled demand units | 1443 | 1407 |
| Unmet demand units | 0 | 36 |
| Stockout-event count | 0 | 12 |
| Waste units | 0 | 0 |
| Ending inventory units | 111 | 7 |
| Delivered units | 1464 | 1324 |
| Delivered packs | 264 | 237 |

These values are synthetic regression anchors. They do not show that either
scenario is optimal or suitable for real operations.

## Continuous integration

GitHub Actions runs the complete test suite on the Python 3.12 project baseline
for pull requests and pushes to `main`. The workflow has read-only repository
permissions, does not persist checkout credentials, does not cache dependencies,
and does not upload generated outputs or contact an external reporting service.
Python 3.13 remains a manual compatibility check.

## Validation boundaries

Directly injected inventory demand records may contain any nonnegative integer
demand. Generation-configured demand ranges apply to records produced and
validated by the Phase 3 generator; they are not an inventory-engine input
policy. Tightening this boundary would change accepted inputs and requires a
separate decision.

Configuration values that are defined as nonnegative integers do not have an
invented upper limit. Python integer arithmetic remains the governing behavior.

Exact dictionary key order remains part of the record and CSV contract. The
Phase 5 generator change only moves record-shape validation before output-path
creation. It does not change accepted valid records or serialized bytes.

Coverage tooling and numerical coverage thresholds are intentionally excluded.
The project prioritizes tests of meaningful public behavior and exact invariants
over an artificial percentage target.

## Privacy and phase boundary

Automated checks enforce the nine approved aliases and exact output schemas.
Human review remains necessary to detect employer or company identity, store or
person identifiers, private URLs, credentials, real documents, screenshots, or
operational data that cannot be represented by a stable word list.

Phase 5 adds no product categories, donut behavior, machine learning,
forecasting, optimization, dashboard, API, notebook, deployment, or real-data
integration.
