# SmartStock ML

SmartStock ML is a privacy-safe Python portfolio project for studying retail inventory planning with synthetic data. The project will eventually explore demand, stockouts, waste, and 14-day ordering decisions in a clear and explainable way.

## Privacy statement

This repository must use only synthetic and anonymized data. Do not add employer names, brand names, store numbers, exact locations, employee names, customer names, vendor names, private URLs, credentials, real invoices, delivery documents, screenshots, or operational records.

## Current project status

The project contains the Phase 1 Python foundation, Phase 2 validated configuration, a Phase 3 deterministic synthetic-demand generator, and a Phase 4A deterministic inventory simulator. Phase 4A adds fixed starting inventory, fixed full-pack deliveries, FIFO fulfillment, unopened expiration, waste, and stockout outcomes. The Phase 4B baseline ordering policy is postponed.

## Planned repository structure

- `src/smartstock/`: reusable Python package code.
- `tests/`: automated tests.
- `config/`: validated synthetic product and delivery configuration.
- `docs/`: assumptions, privacy rules, the data dictionary, and future project decisions.
- `notebooks/`: future Google Colab demonstrations that import reusable code.
- `data/generated/`: generated CSV files are ignored by Git while `.gitkeep` remains tracked.
- `data/sample/`: future small privacy-safe synthetic examples.

## Requirements

- Python 3.12 or newer.
- `pytest` for development testing.

## Installation

Install the project in editable mode with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Running tests

Run the test suite with:

```bash
python -m pytest -q
```

## Generating synthetic demand

Run the generator from the repository root after installation:

```bash
python -m smartstock.generator
```

The default command writes `data/generated/synthetic_daily_records.csv`. It produces 504 rows from 56 synthetic dates and nine approved product aliases. The CSV columns are `date`, `weekday`, `product_id`, `is_high_demand_day`, `demand_units`, and `delivery_event`.

Demand uses a local seeded random generator. Low demand is an inclusive integer from 0 through 2, and high demand is an inclusive integer from 3 through 6. One unit is added on a product's configured high-demand weekdays. The default seed is 42 and can be replaced with `--seed`.

Phase 3 supports only `low` and `high` demand levels. `medium` is unsupported, and a product with `demand_level: unknown` cannot be processed by the Phase 3 generator. The broader Phase 2 configuration validator may retain `unknown` for incomplete or future configuration.

A delivery event marks the first date and each 14-day Tuesday cycle. It does not represent inventory or a delivery quantity.

## Simulating synthetic inventory

Run the separate Phase 4A CLI from the repository root:

```bash
python -m smartstock.inventory
```

The default command writes `data/generated/synthetic_inventory_records.csv`. It generates Phase 3 demand in memory, applies the fixed synthetic values in `config/inventory.yaml`, and produces 504 deterministic records. Use `--seed` to override the demand seed or `--output` to choose another path.

Inventory uses FIFO cohorts. Carried cohorts expire before demand, scheduled deliveries are then added and are usable that date, and demand consumes the oldest usable units first. Only unopened shelf life is used. Fixed delivery pack counts are scenario inputs, not recommendations.

The default 56-day run has zero expiration and waste because every approved unopened shelf life is at least 60 days and starting inventory is fresh. Focused tests use shorter synthetic shelf lives to verify expiration boundaries.

Python 3.12 is the project baseline. Phase 3 is also verified with Python 3.13 when that interpreter is available.

## Current limitations

- Generated demand is synthetic and is not operational or food-safety guidance.
- `demand_units` is a future prediction target and must not be used to predict demand for the same row.
- No baseline ordering policy or ordering recommendations are implemented yet.
- No forecasting, optimization, dashboard, deployment, or notebook analysis is implemented yet.
- Phase 4A outcome columns describe results after demand and inventory transitions. They must not be used as same-row features in future prediction tasks.
