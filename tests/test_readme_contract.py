"""Phase 8A presentation contract for the root README and repository docs.

These tests pin repository *structure* and claim safety, not prose. They
deliberately avoid asserting complete sentences, paragraphs, byte content, line
numbers, or the current test count so that documentation can be reworded
without breaking the suite.
"""

import json
from pathlib import Path
import re

from smartstock.config import APPROVED_PRODUCT_IDS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
NOTEBOOK_DIRECTORY = PROJECT_ROOT / "notebooks"

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
