import json
from datetime import date, timedelta
from pathlib import Path
import re

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_inventory_config,
    load_ordering_config,
    load_products_config,
)
from smartstock.generator import generate_daily_records
from smartstock.inventory import simulate_inventory
from smartstock.ordering import compare_scenarios, simulate_policy_inventory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = (
    PROJECT_ROOT / "notebooks" / "phase_6_exploratory_analysis.ipynb"
)
APPROVED_SOURCE_REVISION = "8d5b9f9a8b5ee9398b04e6fa2713e4def89d13d4"


def _load_notebook() -> dict[str, object]:
    return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))


def _cell_source(cell: dict[str, object]) -> str:
    source = cell.get("source")
    if not isinstance(source, list) or not all(
        isinstance(line, str) for line in source
    ):
        raise AssertionError("Notebook cell source must be a list of strings.")
    return "".join(source)


def test_phase_6_notebook_has_required_ordered_sections() -> None:
    notebook = _load_notebook()
    assert notebook["nbformat"] == 4
    cells = notebook["cells"]
    assert isinstance(cells, list)
    markdown = "\n".join(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
    )
    required_headings = [
        "# SmartStock ML Phase 6: Exploratory Analysis",
        "## 1. Project and Privacy",
        "## 2. Reproducible Colab Setup",
        "## 3. Load Configuration and Generate Records",
        "## 4. Validate and Inspect the Synthetic Dataset",
        "## 5. Explore Synthetic Demand",
        "## 6. Explore Inventory and Stockouts",
        "## 7. Review Ordering Recommendations",
        "## 8. Compare Fixed and Policy Scenarios",
        "## 9. Limitations and Phase 7 Handoff",
    ]
    positions = [markdown.index(heading) for heading in required_headings]
    assert positions == sorted(positions)


def test_phase_6_notebook_has_no_saved_execution_state() -> None:
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

    metadata = notebook.get("metadata")
    assert isinstance(metadata, dict)
    assert not {"authors", "widgets"} & set(metadata)


def test_phase_6_notebook_calls_reusable_pipeline_functions() -> None:
    notebook_text = NOTEBOOK_PATH.read_text(encoding="utf-8")
    required_tokens = {
        APPROVED_SOURCE_REVISION,
        "load_products_config",
        "load_delivery_config",
        "load_generation_config",
        "load_inventory_config",
        "load_ordering_config",
        "generate_daily_records",
        "simulate_inventory",
        "simulate_policy_inventory",
        "compare_scenarios",
    }
    assert all(token in notebook_text for token in required_tokens)
    assert "write_records_csv" not in notebook_text
    assert "write_inventory_csv" not in notebook_text
    assert "write_recommendations_csv" not in notebook_text


def test_phase_6_notebook_has_no_absolute_windows_paths() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    notebook_source = "\n".join(
        _cell_source(cell) for cell in cells if isinstance(cell, dict)
    )
    assert re.search(r"(?<![A-Za-z0-9_])[A-Za-z]:\\", notebook_source) is None


def test_phase_6_notebook_has_no_unapproved_urls_or_secret_assignments() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    notebook_source = "\n".join(
        _cell_source(cell) for cell in cells if isinstance(cell, dict)
    )
    urls = re.findall(r"https?://[^\s)\]\"]+", notebook_source)
    approved_url_prefixes = (
        "https://github.com/sebass369/smartstock-ml",
        "https://colab.research.google.com/",
    )
    assert urls
    assert all(url.startswith(approved_url_prefixes) for url in urls)
    assert re.search(
        r"(?i)(api[_-]?key|access[_-]?token|password)\s*=",
        notebook_source,
    ) is None


def test_phase_6_in_memory_pipeline_matches_approved_anchors() -> None:
    config_root = PROJECT_ROOT / "config"
    products_config = load_products_config(config_root / "products.yaml")
    delivery_config = load_delivery_config(config_root / "delivery.yaml")
    generation_config = load_generation_config(config_root / "generation.yaml")
    inventory_config = load_inventory_config(
        config_root / "inventory.yaml",
        products_config,
    )
    ordering_config = load_ordering_config(
        config_root / "ordering.yaml",
        products_config,
        delivery_config,
    )

    demand_records = generate_daily_records(
        products_config,
        delivery_config,
        generation_config,
        seed=42,
    )
    fixed_records = simulate_inventory(
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
    )
    policy_records, recommendations = simulate_policy_inventory(
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
        ordering_config,
    )
    evaluation_start = date.fromisoformat(demand_records[0]["date"]) + timedelta(
        days=delivery_config["delivery"]["cycle_length_days"]
    )
    comparison = compare_scenarios(
        fixed_records,
        policy_records,
        products_config,
        evaluation_start,
    )

    assert len(demand_records) == len(fixed_records) == len(policy_records) == 504
    assert len(recommendations) == 27
    assert {record["product_id"] for record in demand_records} == (
        APPROVED_PRODUCT_IDS
    )
    assert comparison["fixed"]["overall"] == {
        "total_fulfilled_demand_units": 1443,
        "total_unmet_demand_units": 0,
        "stockout_event_count": 0,
        "total_waste_units": 0,
        "ending_inventory_units": 111,
        "total_delivered_units": 1464,
        "total_delivered_packs": 264,
    }
    assert comparison["policy"]["overall"] == {
        "total_fulfilled_demand_units": 1407,
        "total_unmet_demand_units": 36,
        "stockout_event_count": 12,
        "total_waste_units": 0,
        "ending_inventory_units": 7,
        "total_delivered_units": 1324,
        "total_delivered_packs": 237,
    }
