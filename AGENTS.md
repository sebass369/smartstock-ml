# SmartStock ML Agent Instructions

## Project Purpose

SmartStock ML is a privacy-safe Python portfolio project that uses synthetic retail inventory data to study demand forecasting, stockouts, waste, and 14-day ordering decisions.

The repository is designed for a Computer Science student learning Python, software engineering, data analysis, testing, and machine learning. Prefer clear and explainable solutions over unnecessary complexity.

## Source of Truth

- Read `PROJECT.md` before implementing project requirements.
- Read files under `config/` before changing product or delivery behavior.
- Treat `PROJECT.md` as the source of truth for scope and acceptance criteria.
- Treat values in `config/` as synthetic modeling assumptions, not real operational or food-safety guidance.
- If a requirement is missing or uncertain, document the assumption instead of inventing a fact.

## Language and Code Standards

- Use Python 3.12.
- Write all code in English.
- Write filenames, variable names, function names, class names, configuration keys, comments, docstrings, tests, notebook Markdown, and technical documentation in English.
- Write final task explanations in simple English.
- Follow PEP 8.
- Use descriptive names, type hints, and concise docstrings.
- Prefer small, focused, testable functions.
- Avoid duplicated logic and unnecessary abstractions.
- Use pandas, NumPy, PyYAML, and pytest unless the approved scope requires something else.
- Do not add a new dependency without explaining why it is necessary.

## Repository Structure

- `src/smartstock/`: reusable Python implementation.
- `tests/`: automated tests.
- `config/`: synthetic product and delivery configuration.
- `docs/`: assumptions, privacy rules, data dictionary, and project decisions.
- `notebooks/`: Google Colab demonstrations and experiments.
- `data/generated/`: reproducible generated data; do not treat it as the source of truth.
- `data/sample/`: small privacy-safe examples suitable for review.

## Google Colab Rules

- Use Google Colab for demonstrations, exploratory analysis, visualizations, and model experiments.
- Keep business logic in `src/smartstock/`, not inside notebook cells.
- Notebooks must import and call reusable project functions.
- Keep cells short, ordered, and executable from top to bottom.
- Use a fixed random seed in demonstrations.
- Keep saved outputs small and privacy-safe.
- Never place passwords, API keys, access tokens, private paths, or credentials in a notebook.

## Data and Modeling Rules

- Use only synthetic and anonymized data.
- Use only approved public product identifiers from `config/products.yaml`.
- Keep demand, fulfilled usage, unmet demand, waste, and stockouts as separate concepts.
- Never allow negative inventory, negative waste, or negative demand.
- Ensure `units_used` does not exceed available inventory.
- Preserve inventory balance from one day to the next.
- Make generated data reproducible with a configurable random seed.
- Deliveries occur on the configured 14-day Tuesday cycle.
- Do not invent store operating hours or an exact Skim_Milk refill interval.
- Do not calculate exact daily dispenser refill counts until operating hours are confirmed.
- Start with a simple baseline before using advanced machine-learning models.
- Avoid target leakage and future-data leakage in all forecasting work.

## Privacy and Public Repository Rules

Never add or expose:

- Employer, brand, or store names.
- Store numbers or exact locations.
- Employee, manager, customer, or vendor names.
- Internal product names that have not been approved for public use.
- Real sales, orders, invoices, delivery PDFs, screenshots, or internal documents.
- Credentials, tokens, secrets, private URLs, or personal information.

Before recommending that the repository become public, search the entire repository for private or identifying information and report the result.

## Required Workflow

Before editing:

1. Inspect the relevant files and current repository status.
2. Restate the requested scope.
3. Present a short implementation plan.
4. Identify assumptions or blockers.
5. Avoid changing files outside the approved scope.

While editing:

1. Make the smallest coherent change that satisfies the task.
2. Preserve unrelated user changes.
3. Update tests and documentation when behavior changes.
4. Do not weaken, skip, or delete a valid test merely to make the suite pass.

After editing:

1. Run the relevant tests.
2. Run validation checks for generated data when applicable.
3. Review the diff for privacy, correctness, and unnecessary changes.
4. Report files changed, commands run, test results, assumptions, and limitations.
5. Explain in simple English what was built and why it matters.

## Standard Commands

Install the project:

```bash
python -m pip install -e .
```

Run the test suite:

```bash
python -m pytest -q
```

Run a focused test file:

```bash
python -m pytest -q tests/test_generator.py
```

## Definition of Done

A task is complete only when:

- The approved behavior is implemented.
- Code and documentation are written in English.
- Relevant tests pass.
- Generated data satisfies documented validation rules.
- No private or identifying information is present.
- Colab notebooks call reusable code instead of duplicating it.
- Assumptions and limitations are documented.
- The final explanation is written in simple English.

## Scope and Change Control

- Do not implement forecasting, optimization, dashboards, deployment, or unrelated features before their phase is approved.
- Do not push, merge, deploy, publish, change repository visibility, or contact external services without explicit user authorization.
- When a requested action is destructive or expands the project scope, stop and ask for confirmation.
