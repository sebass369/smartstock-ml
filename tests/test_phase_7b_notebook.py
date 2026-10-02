import json
from pathlib import Path
import re

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_products_config,
)
from smartstock.generator import generate_daily_records
from smartstock.ml_forecasting import (
    generate_ml_cycle_forecast_records,
    summarize_ml_forecasts,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "phase_7b_machine_learning.ipynb"


def _load_notebook() -> dict[str, object]:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _cell_source(cell: dict[str, object]) -> str:
    source = cell.get("source")
    if not isinstance(source, list) or not all(
        isinstance(line, str) for line in source
    ):
        raise AssertionError("Notebook cell source must be a list of strings.")
    return "".join(source)


def test_phase_7b_notebook_has_required_ordered_sections() -> None:
    notebook = _load_notebook()
    assert notebook["nbformat"] == 4
    cells = notebook["cells"]
    assert isinstance(cells, list)
    assert len(cells) == 16
    assert [cell.get("id") for cell in cells] == [
        "phase-7b-title",
        "project-privacy",
        "colab-setup",
        "environment-setup",
        "build-forecasts",
        "forecast-pipeline",
        "evaluation-contract",
        "forecast-dataframe",
        "model-explanation",
        "model-coefficients",
        "method-comparison",
        "overall-metrics",
        "actual-predicted-chart",
        "product-results",
        "product-error-chart",
        "limitations",
    ]
    markdown = "\n".join(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
    )
    required_headings = [
        "# SmartStock ML Phase 7B — Simple Machine Learning Model",
        "## 1. Project and Privacy",
        "## 2. Reproducible Colab Setup",
        "## 3. Generate Baseline, Candidate, and Model Forecasts",
        "## 4. Validate the Evaluation Contract",
        "## 5. The Trained Model and Its Coefficients",
        "## 6. Three-Method Comparison",
        "## 7. Per-Product Error Comparison",
        "## 8. Limitations",
    ]
    positions = [markdown.index(heading) for heading in required_headings]
    assert positions == sorted(positions)


def test_phase_7b_notebook_has_unique_stable_cell_ids() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    cell_ids = [cell.get("id") for cell in cells]

    assert all(isinstance(cell_id, str) and cell_id for cell_id in cell_ids)
    assert len(cell_ids) == len(set(cell_ids))
    assert all(re.fullmatch(r"[a-z0-9-]+", cell_id) for cell_id in cell_ids)


def test_phase_7b_notebook_has_no_saved_execution_state() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    code_cells = [
        cell
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    ]
    assert code_cells
    for cell in code_cells:
        assert cell.get("execution_count") is None
        assert cell.get("outputs") == []


def test_phase_7b_notebook_calls_reusable_machine_learning_functions() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")
    required_tokens = {
        "load_products_config",
        "load_delivery_config",
        "load_generation_config",
        "generate_daily_records",
        "generate_ml_cycle_forecast_records",
        "summarize_ml_forecasts",
        "build_training_rows",
        "fit_demand_model",
    }
    assert all(token in notebook_text for token in required_tokens)
    assert "write_records_csv" not in notebook_text
    assert "write_inventory_csv" not in notebook_text
    assert "write_recommendations_csv" not in notebook_text
    assert "joblib" not in notebook_text
    assert "pickle" not in notebook_text


def test_phase_7b_notebook_code_cells_do_not_build_the_model_inline() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    code_source = "\n".join(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    )

    for implementation_token in (
        "sklearn",
        "OneHotEncoder",
        "ColumnTransformer",
        "LinearRegression",
        "Ridge",
        "Pipeline(",
        ".fit(",
    ):
        assert implementation_token not in code_source


def test_phase_7b_notebook_installs_the_approved_optional_groups() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")

    assert "[analysis,ml]" in notebook_text


def test_phase_7b_notebook_pins_an_immutable_source_revision() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    setup_source = next(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict) and cell.get("id") == "environment-setup"
    )

    revision_match = re.search(
        r'SOURCE_REVISION = "([0-9a-f]{40})"',
        setup_source,
    )
    assert revision_match is not None
    assert "checkout" in setup_source
    assert "--branch" not in setup_source
    assert 'SOURCE_REF = "main"' not in setup_source
    assert "feature/phase-7b-machine-learning" not in setup_source


def test_phase_7b_notebook_links_the_public_notebook_path() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")

    assert "blob/main/notebooks/phase_7b_machine_learning.ipynb" in notebook_text


def test_phase_7b_notebook_has_no_private_paths_or_secret_assignments() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    notebook_source = "\n".join(
        _cell_source(cell) for cell in cells if isinstance(cell, dict)
    )

    assert re.search(r"(?<![A-Za-z0-9_])[A-Za-z]:\\", notebook_source) is None
    assert re.search(
        r"(?i)(api[_-]?key|access[_-]?token|password)\s*=",
        notebook_source,
    ) is None


def test_phase_7b_notebook_uses_only_approved_urls() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")
    urls = re.findall(r"https?://[^\s)\]\"]+", notebook_text)
    approved_url_prefixes = (
        "https://github.com/sebass369/smartstock-ml",
        "https://colab.research.google.com/",
    )

    assert urls
    assert all(url.startswith(approved_url_prefixes) for url in urls)


def test_phase_7b_notebook_states_the_expected_result_honestly() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    markdown = "\n".join(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
    )

    assert "expected to match the expanding weekday-mean candidate" in markdown
    assert "may lose to the previous-cycle baseline" in markdown
    assert "not a defect" in markdown
    assert "is_high_demand_day" in markdown


def test_phase_7b_notebook_does_not_claim_real_world_accuracy() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    markdown = "\n".join(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
    )

    assert "not sales records" in markdown
    assert "no real-world forecast" in markdown.lower() or (
        "no real-world forecast accuracy is claimed" in markdown
    )


def test_phase_7b_in_memory_pipeline_matches_approved_scope() -> None:
    config_root = PROJECT_ROOT / "config"
    products_config = load_products_config(config_root / "products.yaml")
    delivery_config = load_delivery_config(config_root / "delivery.yaml")
    generation_config = load_generation_config(config_root / "generation.yaml")
    demand_records = generate_daily_records(
        products_config,
        delivery_config,
        generation_config,
        seed=42,
    )
    records = generate_ml_cycle_forecast_records(
        demand_records,
        products_config,
        delivery_config,
    )
    summary = summarize_ml_forecasts(records, products_config)

    assert len(records) == 27
    assert {record["product_id"] for record in records} == APPROVED_PRODUCT_IDS
    assert summary["overall"]["forecast_count"] == 27
    assert sum(summary["model_vs_baseline_result_counts"].values()) == 9
    assert sum(summary["model_vs_candidate_result_counts"].values()) == 9
    assert all(
        value is None or value >= 0
        for value in (
            summary["overall"]["baseline_wape_percent"],
            summary["overall"]["candidate_wape_percent"],
            summary["overall"]["model_wape_percent"],
        )
    )
