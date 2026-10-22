"""Phase 8A presentation contract for the root README and repository docs.

These tests pin repository *structure* and claim safety, not prose. They
deliberately avoid asserting complete sentences, paragraphs, byte content, line
numbers, or the current test count so that documentation can be reworded
without breaking the suite.
"""

import json
from pathlib import Path
import re
import xml.etree.ElementTree as ElementTree

from smartstock.config import APPROVED_PRODUCT_IDS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
NOTEBOOK_DIRECTORY = PROJECT_ROOT / "notebooks"
CHART_RELATIVE_PATH = "docs/assets/forecast_mae_comparison.svg"
CHART_PATH = PROJECT_ROOT / "docs" / "assets" / "forecast_mae_comparison.svg"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"

# Displayed values only. The exact metrics stay in docs/ and the ML test suite.
ROUNDED_METRIC_VALUES = ("3.41", "6.38", "3.46", "6.48")
FULL_PRECISION_METRIC_VALUES = (
    "3.4074074074074074",
    "6.375606375606376",
    "3.462962962962963",
    "6.4795564795564795",
)
REQUIRED_CHART_LABELS = (
    "14-Day Cycle Forecast MAE",
    "Lower is better",
    "27 synthetic product-cycle records",
    "Previous-cycle baseline",
    "Expanding weekday mean",
    "Linear regression",
)

REQUIRED_README_HEADINGS = (
    "# SmartStock ML",
    "## Overview",
    "## How It Works",
    "## Key Results",
    "## Try It",
    "## Notebooks",
    "## Repository Structure",
    "## Engineering and Reproducibility",
    "## Privacy",
    "## Limitations",
    "## Roadmap",
    "## License",
)

APPROVED_URL_PREFIXES = (
    "https://github.com/sebass369/smartstock-ml",
    "https://colab.research.google.com/",
)

UNSUPPORTED_CLAIMS = (
    "optimal",
    "cost savings",
    "accuracy improvement",
    "reduces waste",
    "waste reduction",
)

REQUIRED_INDEX_LINKS = (
    "docs/README.md",
    "notebooks/README.md",
    "config/README.md",
    "data/README.md",
)

GOLDEN_HASHES = {
    "tests/test_generator.py": (
        "46f6762dc900f4fb3b965b97773d3147b288d17c1ec044c2c487372cc5e55096"
    ),
    "tests/test_inventory.py": (
        "2cf57c1916024d754ea0ebafafacc74b272cda1b58ec9f5ea78bc70aa4b4d3d0"
    ),
    "tests/test_ordering.py": (
        "6837650452c0266acb8b558212a0d14b9aa2e8ed35a22511c80c1fe18ebd3267"
    ),
}

MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
URL_PATTERN = re.compile(r"https?://[^\s)\]\"'>]+")
WINDOWS_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\")
CREDENTIAL_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret|password)\s*="
)
# Approved aliases look like "Milk_Product_A": a capitalised first segment
# followed by at least one underscore-joined segment.
ALIAS_SHAPE_PATTERN = re.compile(r"\b[A-Z][a-z]+_[A-Za-z][A-Za-z_]*\b")


def _readme_text() -> str:
    return README_PATH.read_text(encoding="utf-8")


def _notebook_paths() -> list[Path]:
    return sorted(NOTEBOOK_DIRECTORY.glob("*.ipynb"))


def _window_around(text: str, needle: str, size: int) -> str:
    index = text.index(needle)
    return text[index : index + size]


def test_readme_required_headings_exist_in_order() -> None:
    readme = _readme_text()
    positions = []
    for heading in REQUIRED_README_HEADINGS:
        pattern = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
        match = pattern.search(readme)
        assert match is not None, f"README is missing the heading: {heading}"
        positions.append(match.start())

    assert positions == sorted(positions)


def test_readme_relative_links_resolve_inside_the_repository() -> None:
    readme = _readme_text()
    targets = [
        target
        for target in MARKDOWN_LINK_PATTERN.findall(readme)
        if not target.startswith(("http://", "https://", "#", "mailto:"))
    ]

    assert targets, "README should link to repository paths."
    for target in targets:
        relative_path = target.split("#", 1)[0]
        resolved = (PROJECT_ROOT / relative_path).resolve()
        assert resolved.exists(), f"README link does not resolve: {target}"
        assert resolved.is_relative_to(PROJECT_ROOT), (
            f"README link escapes the repository: {target}"
        )


def test_readme_links_the_docs_and_notebook_indexes() -> None:
    targets = set(MARKDOWN_LINK_PATTERN.findall(_readme_text()))

    for required_link in REQUIRED_INDEX_LINKS:
        assert required_link in targets, f"README must link to {required_link}."


def test_readme_uses_only_approved_url_prefixes() -> None:
    urls = URL_PATTERN.findall(_readme_text())

    assert urls, "README should contain the badge and Colab links."
    for url in urls:
        assert url.startswith(APPROVED_URL_PREFIXES), f"Unapproved URL: {url}"


def test_readme_has_no_absolute_windows_path() -> None:
    assert WINDOWS_PATH_PATTERN.search(_readme_text()) is None


def test_readme_has_no_credential_like_assignment() -> None:
    assert CREDENTIAL_PATTERN.search(_readme_text()) is None


def test_readme_makes_no_unsupported_claims() -> None:
    readme = _readme_text().lower()

    for claim in UNSUPPORTED_CLAIMS:
        assert claim not in readme, f"README must not claim: {claim}"


def test_readme_product_scope_stays_within_the_nine_approved_aliases() -> None:
    readme = _readme_text()
    alias_shaped_tokens = set(ALIAS_SHAPE_PATTERN.findall(readme))

    assert len(APPROVED_PRODUCT_IDS) == 9
    assert alias_shaped_tokens <= APPROVED_PRODUCT_IDS, (
        "README mentions product aliases outside the approved nine: "
        f"{sorted(alias_shaped_tokens - APPROVED_PRODUCT_IDS)}"
    )
    assert "donut" not in readme.lower() or "excluded" in readme.lower()


def test_readme_describes_phase_7b_as_implemented() -> None:
    readme = _readme_text()

    assert re.search(r"(?i)phase 7b", readme) is not None
    assert re.search(r"(?i)phase 7b[^\n]*trained", readme) is not None
    assert "is future work" not in readme


def test_phase_7a_notebook_no_longer_calls_phase_7b_future_work() -> None:
    notebook_text = (
        NOTEBOOK_DIRECTORY / "phase_7_forecasting.ipynb"
    ).read_text(encoding="utf-8")

    assert "is future work" not in notebook_text
    assert "phase_7b_machine_learning.ipynb" in notebook_text


def test_readme_describes_phase_8b_as_optional_and_not_implemented() -> None:
    readme = _readme_text()

    assert "Phase 8B" in readme
    window = _window_around(readme, "Phase 8B", 240).lower()
    assert "optional" in window
    assert "not implemented" in window


def test_golden_hashes_remain_present_in_their_existing_test_files() -> None:
    for relative_path, golden_hash in GOLDEN_HASHES.items():
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert golden_hash in text, f"{relative_path} lost its golden hash."


def test_tracked_notebooks_have_no_saved_execution_state() -> None:
    notebook_paths = _notebook_paths()

    assert notebook_paths, "The repository should contain portfolio notebooks."
    for notebook_path in notebook_paths:
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        code_cells = [
            cell
            for cell in notebook["cells"]
            if isinstance(cell, dict) and cell.get("cell_type") == "code"
        ]
        assert code_cells, f"{notebook_path.name} has no code cells."
        for cell in code_cells:
            assert cell.get("execution_count") is None, notebook_path.name
            assert cell.get("outputs") == [], notebook_path.name


def test_repository_has_an_mit_license_file() -> None:
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "MIT License" in license_text
    assert "Sebastian Siles" in license_text


def _chart_text_content() -> str:
    root = ElementTree.parse(CHART_PATH).getroot()
    return "\n".join(
        element.text for element in root.iter() if element.text is not None
    )


def test_readme_rounds_the_headline_error_metrics_for_display() -> None:
    readme = _readme_text()

    for rounded_value in ROUNDED_METRIC_VALUES:
        assert rounded_value in readme, f"README should display {rounded_value}."
    for exact_value in FULL_PRECISION_METRIC_VALUES:
        assert exact_value not in readme, (
            f"README should not display the exact value {exact_value}."
        )
    assert "rounded to two decimals" in readme
    assert "docs/ml_forecasting.md" in readme


def test_full_precision_metrics_remain_in_the_technical_documentation() -> None:
    ml_documentation = (PROJECT_ROOT / "docs" / "ml_forecasting.md").read_text(
        encoding="utf-8"
    )

    for exact_value in FULL_PRECISION_METRIC_VALUES:
        assert exact_value in ml_documentation, (
            f"docs/ml_forecasting.md lost the exact value {exact_value}."
        )


def test_readme_embeds_the_local_forecast_chart() -> None:
    readme = _readme_text()

    assert CHART_PATH.is_file(), "The forecast chart asset is missing."
    alt_text_match = re.search(
        rf"!\[([^\]]+)\]\({re.escape(CHART_RELATIVE_PATH)}\)",
        readme,
    )
    assert alt_text_match is not None, (
        "The README must embed the local chart as an image with alt text."
    )
    assert len(alt_text_match.group(1)) >= 80, "Alt text should be descriptive."


def test_forecast_chart_is_valid_svg_with_its_required_labels() -> None:
    root = ElementTree.parse(CHART_PATH).getroot()

    assert root.tag == f"{{{SVG_NAMESPACE}}}svg"
    assert root.get("role") == "img"
    assert root.find(f"{{{SVG_NAMESPACE}}}title") is not None
    assert root.find(f"{{{SVG_NAMESPACE}}}desc") is not None

    chart_text = _chart_text_content()
    for label in REQUIRED_CHART_LABELS:
        assert label in chart_text, f"The chart is missing the label: {label}."
    for displayed_value in ("3.41", "3.46"):
        assert displayed_value in chart_text


def test_forecast_chart_has_no_external_or_executable_content() -> None:
    chart_markup = CHART_PATH.read_text(encoding="utf-8")
    without_namespace = chart_markup.replace(SVG_NAMESPACE, "")

    assert "http://" not in without_namespace
    assert "https://" not in without_namespace
    for forbidden in ("<script", "<image", "<foreignObject", "href", "@import"):
        assert forbidden not in chart_markup, (
            f"The chart must not contain {forbidden}."
        )


def test_forecast_chart_does_not_imply_the_trained_model_won() -> None:
    root = ElementTree.parse(CHART_PATH).getroot()
    bar_widths = [
        float(element.get("width"))
        for element in root.iter(f"{{{SVG_NAMESPACE}}}rect")
        if element.get("height") == "26"
    ]
    chart_text = _chart_text_content()

    assert len(bar_widths) == 3, "The chart should show exactly three bars."
    baseline_width, candidate_width, model_width = bar_widths
    assert baseline_width < model_width, (
        "Lower is better, so the baseline bar must be the shortest."
    )
    assert candidate_width == model_width, "The tied methods must match exactly."
    assert "did not beat the previous-cycle baseline" in chart_text
    assert "Lower is better" in chart_text
