import json
from pathlib import Path
import re

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_products_config,
)
from smartstock.forecasting import (
    generate_cycle_forecast_records,
    summarize_forecasts,
)
from smartstock.generator import generate_daily_records

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "phase_7_forecasting.ipynb"


def _load_notebook() -> dict[str, object]:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _cell_source(cell: dict[str, object]) -> str:
    source = cell.get("source")
    if not isinstance(source, list) or not all(
        isinstance(line, str) for line in source
    ):
        raise AssertionError("Notebook cell source must be a list of strings.")
    return "".join(source)


def test_phase_7_notebook_has_required_ordered_sections() -> None:
    notebook = _load_notebook()
    assert notebook["nbformat"] == 4
    cells = notebook["cells"]
    assert isinstance(cells, list)
    assert len(cells) == 16
    cell_ids = [cell.get("id") for cell in cells]
    assert cell_ids == [
        "phase-7-title",
        "project-privacy",
        "colab-setup",
        "environment-setup",
        "generate-forecasts",
        "forecast-pipeline",
        "evaluation-contract",
        "forecast-dataframe",
        "method-explanation",
        "overall-metrics",
        "actual-predicted",
        "actual-predicted-chart",
        "product-results",
        "product-error-chart",
        "win-tie-loss-summary",
        "limitations",
    ]
    markdown = "\n".join(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
    )
    required_headings = [
        "# SmartStock ML Phase 7A — Baseline Forecast Evaluation",
        "## 1. Project and Privacy",
        "## 2. Reproducible Colab Setup",
        "## 3. Generate Deterministic Forecasts",
        "## 4. Validate the Evaluation Contract",
        "## 5. Baseline and Candidate",
        "## 6. Actual Versus Predicted Demand",
        "## 7. Per-Product Error Comparison",
        "## 8. Limitations",
    ]
    positions = [markdown.index(heading) for heading in required_headings]
    assert positions == sorted(positions)


def test_phase_7_notebook_has_no_saved_execution_state() -> None:
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


def test_phase_7_notebook_calls_reusable_forecasting_functions() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")
    required_tokens = {
        "load_products_config",
        "load_delivery_config",
        "load_generation_config",
        "generate_daily_records",
        "generate_cycle_forecast_records",
        "summarize_forecasts",
    }
    assert all(token in notebook_text for token in required_tokens)
    assert "write_records_csv" not in notebook_text
    assert "write_inventory_csv" not in notebook_text
    assert "write_recommendations_csv" not in notebook_text


def test_phase_7_notebook_has_no_private_paths_or_secret_assignments() -> None:
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


def test_phase_7_notebook_uses_only_approved_urls() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")
    urls = re.findall(r"https?://[^\s)\]\"]+", notebook_text)
    approved_url_prefixes = (
        "https://github.com/sebass369/smartstock-ml",
        "https://colab.research.google.com/",
    )
    assert urls
    assert all(url.startswith(approved_url_prefixes) for url in urls)


def test_phase_7_notebook_targets_public_main() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")

    assert "blob/main/notebooks/phase_7_forecasting.ipynb" in notebook_text
    assert 'SOURCE_REF = \\"main\\"' in notebook_text
    assert "feature/phase-7-demand-forecasting" not in notebook_text


def test_phase_7_in_memory_pipeline_matches_approved_scope() -> None:
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
    records = generate_cycle_forecast_records(
        demand_records,
        products_config,
        delivery_config,
    )
    summary = summarize_forecasts(records, products_config)

    assert len(records) == 27
    assert {record["product_id"] for record in records} == APPROVED_PRODUCT_IDS
    assert summary["overall"]["forecast_count"] == 27
    assert sum(summary["candidate_product_result_counts"].values()) == 9
    assert all(
        value is None or value >= 0
        for value in (
            summary["overall"]["baseline_wape_percent"],
            summary["overall"]["candidate_wape_percent"],
        )
    )
