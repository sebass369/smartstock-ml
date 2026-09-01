import csv
from copy import deepcopy
from pathlib import Path
import random

import pytest

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_products_config,
)
from smartstock.generator import (
    RECORD_COLUMNS,
    generate_daily_records,
    main,
    validate_generated_records,
    write_records_csv,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = PROJECT_ROOT / "config" / "products.yaml"
DELIVERY_PATH = PROJECT_ROOT / "config" / "delivery.yaml"
GENERATION_PATH = PROJECT_ROOT / "config" / "generation.yaml"


@pytest.fixture
def configurations():
    return (
        load_products_config(PRODUCTS_PATH),
        load_delivery_config(DELIVERY_PATH),
        load_generation_config(GENERATION_PATH),
    )


@pytest.fixture
def default_records(configurations):
    return generate_daily_records(*configurations)


def test_default_generation_creates_exactly_504_records(default_records):
    assert len(default_records) == 504


def test_records_use_exactly_nine_approved_aliases(default_records):
    aliases = {record["product_id"] for record in default_records}

    assert aliases == APPROVED_PRODUCT_IDS
    assert all("donut" not in alias.lower() for alias in aliases)


def test_every_date_contains_one_record_per_product(default_records):
    records_by_date: dict[str, list[str]] = {}
    for record in default_records:
        records_by_date.setdefault(record["date"], []).append(record["product_id"])

    assert len(records_by_date) == 56
    for product_ids in records_by_date.values():
        assert len(product_ids) == 9
        assert set(product_ids) == APPROVED_PRODUCT_IDS


def test_rows_follow_stable_date_and_configuration_order(
    configurations, default_records
):
    products = configurations[0]["products"]
    expected_product_order = [product["product_id"] for product in products]

    assert [record["product_id"] for record in default_records[:9]] == (
        expected_product_order
    )
    assert [record["date"] for record in default_records[:9]] == [
        "2025-01-07"
    ] * 9
    assert default_records[-1]["date"] == "2025-03-03"


def test_records_use_exact_six_column_contract(default_records):
    assert all(tuple(record) == RECORD_COLUMNS for record in default_records)


def test_same_seed_produces_equal_records(configurations):
    first_records = generate_daily_records(*configurations, seed=42)
    second_records = generate_daily_records(*configurations, seed=42)

    assert first_records == second_records


def test_same_seed_produces_byte_identical_csv(configurations, tmp_path):
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    write_records_csv(generate_daily_records(*configurations, seed=42), first_path)
    write_records_csv(generate_daily_records(*configurations, seed=42), second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_selected_different_seeds_change_demand(configurations):
    first_records = generate_daily_records(*configurations, seed=42)
    second_records = generate_daily_records(*configurations, seed=99)

    assert [record["demand_units"] for record in first_records] != [
        record["demand_units"] for record in second_records
    ]


def test_generation_does_not_change_global_random_state(configurations):
    state_before = random.getstate()

    generate_daily_records(*configurations, seed=42)

    assert random.getstate() == state_before


def test_demand_values_follow_ranges_and_weekday_adjustment(
    configurations, default_records
):
    products = {
        product["product_id"]: product for product in configurations[0]["products"]
    }
    generation = configurations[2]["generation"]
    ranges = generation["demand_ranges"]
    adjustment = generation["high_demand_day_adjustment"]

    for record in default_records:
        product = products[record["product_id"]]
        demand_range = ranges[product["demand_level"]]
        expected_adjustment = adjustment if record["is_high_demand_day"] else 0
        assert demand_range["minimum"] + expected_adjustment <= record[
            "demand_units"
        ] <= demand_range["maximum"] + expected_adjustment
        assert record["is_high_demand_day"] == (
            record["weekday"] in product["high_demand_days"]
        )


def test_products_without_high_demand_days_never_receive_adjustment(
    configurations, default_records
):
    products_without_high_days = {
        product["product_id"]
        for product in configurations[0]["products"]
        if not product["high_demand_days"]
    }

    matching_records = [
        record
        for record in default_records
        if record["product_id"] in products_without_high_days
    ]
    assert matching_records
    assert all(record["is_high_demand_day"] is False for record in matching_records)


def test_high_demand_adjustment_applies_only_on_configured_days(configurations):
    products, delivery, generation = deepcopy(configurations)
    for demand_range in generation["generation"]["demand_ranges"].values():
        demand_range["minimum"] = 0
        demand_range["maximum"] = 0

    records = generate_daily_records(products, delivery, generation)

    for record in records:
        expected_demand = 1 if record["is_high_demand_day"] else 0
        assert record["demand_units"] == expected_demand


def test_delivery_events_use_only_approved_offsets_and_tuesdays(default_records):
    delivery_dates = []
    for day_offset in range(56):
        day_records = default_records[day_offset * 9 : (day_offset + 1) * 9]
        event_values = {record["delivery_event"] for record in day_records}
        assert len(event_values) == 1
        if event_values == {True}:
            delivery_dates.append(day_offset)
            assert day_records[0]["weekday"] == "Tuesday"

    assert delivery_dates == [0, 14, 28, 42]


def test_zero_demand_ranges_are_accepted(configurations):
    products, delivery, generation = deepcopy(configurations)
    for demand_range in generation["generation"]["demand_ranges"].values():
        demand_range["minimum"] = 0
        demand_range["maximum"] = 0
    generation["generation"]["high_demand_day_adjustment"] = 0

    records = generate_daily_records(products, delivery, generation)

    assert {record["demand_units"] for record in records} == {0}


def test_unsupported_product_demand_level_raises_value_error(configurations):
    products, delivery, generation = deepcopy(configurations)
    products["products"][-1]["demand_level"] = "unknown"

    with pytest.raises(ValueError, match="Unsupported demand level"):
        generate_daily_records(products, delivery, generation)


def test_boolean_demand_value_cannot_pass_record_validation(
    configurations, default_records
):
    invalid_records = deepcopy(default_records)
    invalid_records[0]["demand_units"] = True

    with pytest.raises(ValueError, match="demand_units must be an integer"):
        validate_generated_records(invalid_records, *configurations)


def test_extra_column_cannot_pass_record_validation(configurations, default_records):
    invalid_records = deepcopy(default_records)
    invalid_records[0]["private_field"] = "not allowed"

    with pytest.raises(ValueError, match="exact column order"):
        validate_generated_records(invalid_records, *configurations)


def test_extra_delivery_event_cannot_pass_record_validation(
    configurations, default_records
):
    invalid_records = deepcopy(default_records)
    invalid_records[9]["delivery_event"] = True

    with pytest.raises(ValueError, match="configured cycle"):
        validate_generated_records(invalid_records, *configurations)


def test_csv_uses_exact_header_and_lowercase_booleans(default_records, tmp_path):
    output_path = tmp_path / "records.csv"
    write_records_csv(default_records, output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(RECORD_COLUMNS)
    assert "True" not in lines[1]
    assert "False" not in lines[1]
    assert "true" in lines[1]
    assert "false" in lines[1]


def test_csv_contains_no_private_or_operational_fields(default_records, tmp_path):
    output_path = tmp_path / "records.csv"
    write_records_csv(default_records, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        assert tuple(reader.fieldnames or ()) == RECORD_COLUMNS
        assert all(set(row) == set(RECORD_COLUMNS) for row in reader)


def test_writer_creates_output_parent_directory(default_records, tmp_path):
    output_path = tmp_path / "nested" / "output" / "records.csv"

    write_records_csv(default_records, output_path)

    assert output_path.is_file()


def test_cli_succeeds_and_reports_record_count_seed_and_output(tmp_path, capsys):
    output_path = tmp_path / "records.csv"

    exit_code = main(_cli_arguments(output_path))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Generated 504 records at {output_path} with seed 42." in captured.out
    assert captured.err == ""
    assert output_path.is_file()


def test_cli_seed_override_changes_output(tmp_path, capsys):
    default_path = tmp_path / "default.csv"
    override_path = tmp_path / "override.csv"
    assert main(_cli_arguments(default_path)) == 0
    capsys.readouterr()

    assert main([*_cli_arguments(override_path), "--seed", "99"]) == 0

    captured = capsys.readouterr()
    assert "with seed 99." in captured.out
    assert default_path.read_bytes() != override_path.read_bytes()


def test_cli_returns_nonzero_for_invalid_configuration(tmp_path, capsys):
    invalid_generation_path = tmp_path / "generation.yaml"
    invalid_generation_path.write_text("generation: {}\n", encoding="utf-8")
    output_path = tmp_path / "records.csv"

    exit_code = main(
        [
            "--products-config",
            str(PRODUCTS_PATH),
            "--delivery-config",
            str(DELIVERY_PATH),
            "--generation-config",
            str(invalid_generation_path),
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Error:" in captured.err
    assert not output_path.exists()


def _cli_arguments(output_path: Path) -> list[str]:
    return [
        "--products-config",
        str(PRODUCTS_PATH),
        "--delivery-config",
        str(DELIVERY_PATH),
        "--generation-config",
        str(GENERATION_PATH),
        "--output",
        str(output_path),
    ]
