# SmartStock ML

SmartStock ML is a privacy-safe Python portfolio project for studying retail inventory planning with synthetic data. The project will eventually explore demand, stockouts, waste, and 14-day ordering decisions in a clear and explainable way.

## Privacy statement

This repository must use only synthetic and anonymized data. Do not add employer names, brand names, store numbers, exact locations, employee names, customer names, vendor names, private URLs, credentials, real invoices, delivery documents, screenshots, or operational records.

## Current project status

The project currently contains the Phase 1 Python repository foundation and Phase 2 validated synthetic product and delivery configuration. It does not yet contain forecasting, machine-learning functionality, synthetic-data generation, inventory simulation, ordering logic, dashboards, deployment, or Google Colab analysis.

## Planned repository structure

- `src/smartstock/`: reusable Python package code.
- `tests/`: automated tests.
- `config/`: validated synthetic product and delivery configuration.
- `docs/`: future assumptions, privacy rules, data dictionary, and project decisions.
- `notebooks/`: future Google Colab demonstrations that import reusable code.
- `data/generated/`: future reproducible generated synthetic data.
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

## Current limitations

- No synthetic datasets are generated yet.
- No inventory simulation or ordering recommendations are implemented yet.
- No forecasting, optimization, dashboard, deployment, or notebook analysis is implemented yet.
