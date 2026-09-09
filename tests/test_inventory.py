import csv
from copy import deepcopy
from datetime import date, timedelta
import hashlib
from pathlib import Path
import shutil

import pytest

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    get_english_weekday,
    load_delivery_config,
    load_generation_config,
    load_inventory_config,
    load_products_config,
)
from smartstock.generator import generate_daily_records
from smartstock.inventory import (
    INVENTORY_RECORD_COLUMNS,
    main,
    simulate_inventory,
    validate_inventory_records,
    write_inventory_csv,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = PROJECT_ROOT / "config" / "products.yaml"
DELIVERY_PATH = PROJECT_ROOT / "config" / "delivery.yaml"
GENERATION_PATH = PROJECT_ROOT / "config" / "generation.yaml"
INVENTORY_PATH = PROJECT_ROOT / "config" / "inventory.yaml"
PHASE_4_CSV_SHA256 = (
    "2cf57c1916024d754ea0ebafafacc74b272cda1b58ec9f5ea78bc70aa4b4d3d0"
)


@pytest.fixture
def configurations():
    products = load_products_config(PRODUCTS_PATH)
    return (
        products,
        load_delivery_config(DELIVERY_PATH),
        load_generation_config(GENERATION_PATH),
        load_inventory_config(INVENTORY_PATH, products),
    )


@pytest.fixture
def default_demand_records(configurations):
    return generate_daily_records(*configurations[:3])


@pytest.fixture
def default_inventory_records(configurations, default_demand_records):
    products, delivery, _, inventory = configurations
    return simulate_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
    )


def test_default_simulation_creates_504_records_for_nine_products(
    default_inventory_records,
):
    assert len(default_inventory_records) == 504
    aliases = {record["product_id"] for record in default_inventory_records}
    assert aliases == APPROVED_PRODUCT_IDS

    for day_offset in range(56):
        day_records = default_inventory_records[day_offset * 9 : (day_offset + 1) * 9]
        assert {record["product_id"] for record in day_records} == (
            APPROVED_PRODUCT_IDS
        )


def test_default_records_use_exact_phase_4_column_order(default_inventory_records):
    assert all(
        tuple(record) == INVENTORY_RECORD_COLUMNS
        for record in default_inventory_records
    )


def test_first_date_uses_approved_starting_inventory_and_deliveries(
    configurations,
    default_inventory_records,
):
    products, _, _, inventory = configurations
    product_by_id = {
        product["product_id"]: product for product in products["products"]
    }
    inventory_by_id = {
        product["product_id"]: product
        for product in inventory["inventory"]["products"]
    }

    for record in default_inventory_records[:9]:
        product_id = record["product_id"]
        inventory_entry = inventory_by_id[product_id]
        assert record["starting_inventory_units"] == (
            inventory_entry["starting_inventory_units"]
        )
        assert record["delivered_units"] == (
            inventory_entry["delivery_pack_count"]
            * product_by_id[product_id]["pack_size_units"]
        )


def test_deliveries_occur_only_on_approved_offsets(default_inventory_records):
    delivery_offsets = []
    for day_offset in range(56):
        day_records = default_inventory_records[day_offset * 9 : (day_offset + 1) * 9]
        if day_records[0]["delivery_event"]:
            delivery_offsets.append(day_offset)
            assert all(record["delivered_units"] >= 0 for record in day_records)
        else:
            assert all(record["delivered_units"] == 0 for record in day_records)

    assert delivery_offsets == [0, 14, 28, 42]


def test_delivery_units_are_constant_full_pack_multiples(
    configurations,
    default_inventory_records,
):
    products, _, _, inventory = configurations
    product_by_id = {
        product["product_id"]: product for product in products["products"]
    }
    inventory_by_id = {
        product["product_id"]: product
        for product in inventory["inventory"]["products"]
    }
    deliveries_by_id: dict[str, set[int]] = {}

    for record in default_inventory_records:
        if not record["delivery_event"]:
            continue
        product_id = record["product_id"]
        pack_size = product_by_id[product_id]["pack_size_units"]
        expected_units = inventory_by_id[product_id]["delivery_pack_count"] * pack_size
        assert record["delivered_units"] == expected_units
        assert record["delivered_units"] % pack_size == 0
        deliveries_by_id.setdefault(product_id, set()).add(record["delivered_units"])

    assert all(len(values) == 1 for values in deliveries_by_id.values())


def test_default_records_preserve_all_balances_and_nonnegative_values(
    default_inventory_records,
):
    prior_ending: dict[str, int] = {}
    integer_columns = INVENTORY_RECORD_COLUMNS[4:5] + INVENTORY_RECORD_COLUMNS[6:-1]

    for record in default_inventory_records:
        product_id = record["product_id"]
        assert all(type(record[column]) is int for column in integer_columns)
        assert all(record[column] >= 0 for column in integer_columns)
        assert record["available_inventory_units"] == (
            record["starting_inventory_units"]
            - record["expired_units"]
            + record["delivered_units"]
        )
        assert record["ending_inventory_units"] == (
            record["starting_inventory_units"]
            + record["delivered_units"]
            - record["expired_units"]
            - record["units_used"]
        )
        assert record["demand_units"] == (
            record["fulfilled_demand_units"] + record["unmet_demand_units"]
        )
        assert record["fulfilled_demand_units"] == min(
            record["demand_units"],
            record["available_inventory_units"],
        )
        assert record["units_used"] == record["fulfilled_demand_units"]
        assert record["waste_units"] == record["expired_units"]
        assert record["stockout_event"] is (
            record["demand_units"] > record["available_inventory_units"]
            and record["unmet_demand_units"] > 0
        )
        if product_id in prior_ending:
            assert record["starting_inventory_units"] == prior_ending[product_id]
        prior_ending[product_id] = record["ending_inventory_units"]


def test_default_expiration_and_waste_are_zero(default_inventory_records):
    assert {record["expired_units"] for record in default_inventory_records} == {0}
    assert {record["waste_units"] for record in default_inventory_records} == {0}


def test_same_seed_produces_equal_inventory_records(configurations):
    products, delivery, generation, inventory = configurations
    first = simulate_inventory(
        generate_daily_records(products, delivery, generation, seed=42),
        products,
        delivery,
        inventory,
    )
    second = simulate_inventory(
        generate_daily_records(products, delivery, generation, seed=42),
        products,
        delivery,
        inventory,
    )

    assert first == second


def test_different_seeds_change_inventory_csv(configurations, tmp_path):
    products, delivery, generation, inventory = configurations
    first_records = simulate_inventory(
        generate_daily_records(products, delivery, generation, seed=42),
        products,
        delivery,
        inventory,
    )
    second_records = simulate_inventory(
        generate_daily_records(products, delivery, generation, seed=99),
        products,
        delivery,
        inventory,
    )
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    write_inventory_csv(first_records, first_path)
    write_inventory_csv(second_records, second_path)

    assert [record["demand_units"] for record in first_records] != [
        record["demand_units"] for record in second_records
    ]
    assert first_path.read_bytes() != second_path.read_bytes()


def test_same_seed_produces_byte_identical_inventory_csv(
    default_inventory_records,
    tmp_path,
):
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    write_inventory_csv(default_inventory_records, first_path)
    write_inventory_csv(default_inventory_records, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_inventory_csv_uses_exact_portable_bytes_and_golden_anchor(
    default_inventory_records,
    tmp_path,
):
    output_path = tmp_path / "inventory.csv"
    write_inventory_csv(default_inventory_records, output_path)
    csv_bytes = output_path.read_bytes()
    expected_header = b",".join(
        column.encode("ascii") for column in INVENTORY_RECORD_COLUMNS
    ) + b"\n"

    assert csv_bytes.startswith(expected_header)
    assert not csv_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in csv_bytes
    assert csv_bytes.endswith(b"\n")
    assert not csv_bytes.endswith(b"\n\n")
    assert csv_bytes.count(b"\n") == 505
    assert hashlib.sha256(csv_bytes).hexdigest() == PHASE_4_CSV_SHA256
    assert csv_bytes.splitlines()[1] == (
        b"2025-01-07,Tuesday,Milk_Product_A,false,3,true,8,64,0,72,"
        b"3,3,0,0,69,false"
    )

    with output_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        assert tuple(reader.fieldnames or ()) == INVENTORY_RECORD_COLUMNS
        rows = list(reader)
    assert len(rows) == 504
    for row in rows:
        assert row["is_high_demand_day"] in {"true", "false"}
        assert row["delivery_event"] in {"true", "false"}
        assert row["stockout_event"] in {"true", "false"}


def test_csv_writer_validates_all_rows_before_creating_output(
    default_inventory_records,
    tmp_path,
):
    invalid_records = deepcopy(default_inventory_records)
    invalid_records[-1]["unexpected"] = 1
    output_path = tmp_path / "inventory.csv"

    with pytest.raises(ValueError, match="exact column order"):
        write_inventory_csv(invalid_records, output_path)

    assert not output_path.exists()


def test_delivery_is_usable_on_received_date(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _inventory_entry(inventory, target_id)["delivery_pack_count"] = 1
    demand = _demand_records(products, 1, {(0, target_id): 4})

    records = simulate_inventory(demand, products, delivery, inventory)
    target = _record(records, 0, target_id)

    assert target["starting_inventory_units"] == 0
    assert target["delivered_units"] == 4
    assert target["fulfilled_demand_units"] == 4
    assert target["ending_inventory_units"] == 0
    assert target["stockout_event"] is False


def test_zero_delivery_pack_count_delivers_zero(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    records = simulate_inventory(
        _demand_records(products, 1),
        products,
        delivery,
        inventory,
    )

    assert all(record["delivery_event"] is True for record in records)
    assert all(record["delivered_units"] == 0 for record in records)


def test_starting_inventory_can_be_a_non_pack_multiple(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 3
    demand = _demand_records(products, 1, {(0, target_id): 2})

    target = _record(
        simulate_inventory(demand, products, delivery, inventory),
        0,
        target_id,
    )

    assert target["starting_inventory_units"] == 3
    assert target["fulfilled_demand_units"] == 2
    assert target["ending_inventory_units"] == 1


@pytest.mark.parametrize(
    ("demand_units", "fulfilled", "unmet", "stockout"),
    [
        (0, 0, 0, False),
        (3, 0, 3, True),
    ],
)
def test_zero_inventory_behavior(
    configurations,
    demand_units,
    fulfilled,
    unmet,
    stockout,
):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    demand = _demand_records(products, 1, {(0, target_id): demand_units})

    target = _record(
        simulate_inventory(demand, products, delivery, inventory),
        0,
        target_id,
    )

    assert target["fulfilled_demand_units"] == fulfilled
    assert target["units_used"] == fulfilled
    assert target["unmet_demand_units"] == unmet
    assert target["ending_inventory_units"] == 0
    assert target["stockout_event"] is stockout


def test_partial_fulfillment_uses_exact_stockout_condition(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 2
    demand = _demand_records(products, 1, {(0, target_id): 5})

    target = _record(
        simulate_inventory(demand, products, delivery, inventory),
        0,
        target_id,
    )

    assert target["available_inventory_units"] == 2
    assert target["fulfilled_demand_units"] == 2
    assert target["unmet_demand_units"] == 3
    assert target["stockout_event"] is True


def test_starting_inventory_expires_on_exact_unopened_boundary(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _product(products, target_id)["unopened_shelf_life_days"] = 2
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 3
    demand = _demand_records(products, 3, {(2, target_id): 1})

    records = simulate_inventory(demand, products, delivery, inventory)
    day_before = _record(records, 1, target_id)
    expiration_day = _record(records, 2, target_id)

    assert day_before["expired_units"] == 0
    assert day_before["ending_inventory_units"] == 3
    assert expiration_day["starting_inventory_units"] == 3
    assert expiration_day["expired_units"] == 3
    assert expiration_day["waste_units"] == 3
    assert expiration_day["fulfilled_demand_units"] == 0
    assert expiration_day["unmet_demand_units"] == 1


def test_partially_consumed_cohort_expires_with_only_its_remainder(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _product(products, target_id)["unopened_shelf_life_days"] = 2
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 5
    demand = _demand_records(products, 3, {(0, target_id): 2})

    records = simulate_inventory(demand, products, delivery, inventory)

    assert _record(records, 0, target_id)["ending_inventory_units"] == 3
    assert _record(records, 2, target_id)["expired_units"] == 3
    assert _record(records, 2, target_id)["ending_inventory_units"] == 0


def test_fifo_consumes_oldest_cohorts_before_new_delivery(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _product(products, target_id)["unopened_shelf_life_days"] = 15
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 5
    _inventory_entry(inventory, target_id)["delivery_pack_count"] = 1
    demand = _demand_records(products, 16, {(14, target_id): 6})

    records = simulate_inventory(demand, products, delivery, inventory)
    delivery_day = _record(records, 14, target_id)
    expiration_day = _record(records, 15, target_id)

    assert delivery_day["starting_inventory_units"] == 9
    assert delivery_day["delivered_units"] == 4
    assert delivery_day["ending_inventory_units"] == 7
    assert expiration_day["expired_units"] == 3
    assert expiration_day["ending_inventory_units"] == 4


def test_open_shelf_life_does_not_change_simulation(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 3
    demand = _demand_records(products, 3)
    first_products = deepcopy(products)
    second_products = deepcopy(products)
    _product(first_products, target_id)["open_shelf_life_days"] = 1
    _product(second_products, target_id)["open_shelf_life_days"] = 30

    first = simulate_inventory(demand, first_products, delivery, inventory)
    second = simulate_inventory(demand, second_products, delivery, inventory)

    assert first == second


def test_exact_inventory_exhaustion_removes_empty_cohort(configurations):
    products, delivery, _, inventory = _isolated_configurations(configurations)
    target_id = "Milk_Product_A"
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 3
    demand = _demand_records(products, 2, {(0, target_id): 3})

    records = simulate_inventory(demand, products, delivery, inventory)

    assert _record(records, 0, target_id)["ending_inventory_units"] == 0
    assert _record(records, 1, target_id)["starting_inventory_units"] == 0


def test_reordered_demand_records_fail_clearly(configurations):
    products, delivery, _, inventory = configurations
    demand = _demand_records(products, 1)
    demand[0], demand[1] = demand[1], demand[0]

    with pytest.raises(ValueError, match="product order"):
        simulate_inventory(demand, products, delivery, inventory)


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        ("units_used", True, "must be an integer"),
        ("ending_inventory_units", -1, "cannot be negative"),
        ("stockout_event", 1, "must be a Boolean"),
    ],
)
def test_inventory_record_validation_rejects_invalid_types_and_values(
    configurations,
    default_demand_records,
    default_inventory_records,
    field_name,
    invalid_value,
    message,
):
    products, delivery, _, inventory = configurations
    records = deepcopy(default_inventory_records)
    records[0][field_name] = invalid_value

    with pytest.raises(ValueError, match=message):
        validate_inventory_records(
            records,
            default_demand_records,
            products,
            delivery,
            inventory,
        )


@pytest.mark.parametrize(
    ("field_name", "replacement", "message"),
    [
        ("available_inventory_units", 0, "available_inventory_units"),
        ("fulfilled_demand_units", 0, "fulfilled_demand_units"),
        ("unmet_demand_units", 99, "Demand balance"),
        ("waste_units", 1, "waste_units"),
        ("ending_inventory_units", 0, "Ending inventory balance"),
        ("stockout_event", True, "stockout_event"),
    ],
)
def test_inventory_record_validation_rejects_broken_formulas(
    configurations,
    default_demand_records,
    default_inventory_records,
    field_name,
    replacement,
    message,
):
    products, delivery, _, inventory = configurations
    records = deepcopy(default_inventory_records)
    records[0][field_name] = replacement

    with pytest.raises(ValueError, match=message):
        validate_inventory_records(
            records,
            default_demand_records,
            products,
            delivery,
            inventory,
        )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra_column"])
def test_malformed_demand_records_fail_clearly(configurations, mutation):
    products, delivery, _, inventory = configurations
    demand = _demand_records(products, 2)
    if mutation == "missing":
        demand.pop()
    elif mutation == "duplicate":
        demand[-1] = deepcopy(demand[-2])
    else:
        demand[0]["unexpected"] = 1

    with pytest.raises(ValueError):
        simulate_inventory(demand, products, delivery, inventory)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "unknown", "reordered", "missing_column"],
)
def test_malformed_inventory_records_fail_clearly(
    configurations,
    default_demand_records,
    default_inventory_records,
    mutation,
):
    products, delivery, _, inventory = configurations
    records = deepcopy(default_inventory_records)
    if mutation == "missing":
        records.pop()
    elif mutation == "duplicate":
        records[-1] = deepcopy(records[-2])
    elif mutation == "unknown":
        records[0]["product_id"] = "Unknown_Product"
    elif mutation == "reordered":
        records[0], records[1] = records[1], records[0]
    else:
        records[0].pop("ending_inventory_units")

    with pytest.raises(ValueError):
        validate_inventory_records(
            records,
            default_demand_records,
            products,
            delivery,
            inventory,
        )


def test_inventory_csv_contains_only_privacy_safe_fields(
    default_inventory_records,
    tmp_path,
):
    output_path = tmp_path / "inventory.csv"
    write_inventory_csv(default_inventory_records, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        assert tuple(reader.fieldnames or ()) == INVENTORY_RECORD_COLUMNS
        assert all(row["product_id"] in APPROVED_PRODUCT_IDS for row in reader)


def test_cli_defaults_generate_separate_inventory_csv(tmp_path, monkeypatch, capsys):
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    for source_path in (
        PRODUCTS_PATH,
        DELIVERY_PATH,
        GENERATION_PATH,
        INVENTORY_PATH,
    ):
        shutil.copyfile(source_path, config_directory / source_path.name)
    monkeypatch.chdir(tmp_path)

    exit_code = main([])

    output_path = Path("data/generated/synthetic_inventory_records.csv")
    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.is_file()
    assert "Generated 504 inventory records" in captured.out
    assert "with seed 42." in captured.out
    assert hashlib.sha256(output_path.read_bytes()).hexdigest() == (
        PHASE_4_CSV_SHA256
    )


def test_cli_seed_override_changes_output(tmp_path, capsys):
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    assert main(_cli_arguments(first_path)) == 0
    capsys.readouterr()

    assert main([*_cli_arguments(second_path), "--seed", "99"]) == 0

    captured = capsys.readouterr()
    assert "with seed 99." in captured.out
    assert first_path.read_bytes() != second_path.read_bytes()


def test_cli_failure_does_not_leave_partial_output(tmp_path, capsys):
    invalid_inventory_path = tmp_path / "inventory.yaml"
    invalid_inventory_path.write_text("inventory: {}\n", encoding="utf-8")
    output_path = tmp_path / "inventory.csv"

    exit_code = main(
        [
            "--products-config",
            str(PRODUCTS_PATH),
            "--delivery-config",
            str(DELIVERY_PATH),
            "--generation-config",
            str(GENERATION_PATH),
            "--inventory-config",
            str(invalid_inventory_path),
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Error:" in captured.err
    assert not output_path.exists()


def _isolated_configurations(configurations):
    products, delivery, generation, inventory = deepcopy(configurations)
    for entry in inventory["inventory"]["products"]:
        entry["starting_inventory_units"] = 0
        entry["delivery_pack_count"] = 0
    return products, delivery, generation, inventory


def _demand_records(
    products_config,
    duration_days,
    demand_overrides=None,
):
    overrides = demand_overrides or {}
    start_date = date(2025, 1, 7)
    records = []
    for day_offset in range(duration_days):
        current_date = start_date + timedelta(days=day_offset)
        weekday = get_english_weekday(current_date)
        for product in products_config["products"]:
            product_id = product["product_id"]
            records.append(
                {
                    "date": current_date.isoformat(),
                    "weekday": weekday,
                    "product_id": product_id,
                    "is_high_demand_day": weekday in product["high_demand_days"],
                    "demand_units": overrides.get((day_offset, product_id), 0),
                    "delivery_event": day_offset % 14 == 0,
                }
            )
    return records


def _inventory_entry(inventory_config, product_id):
    return next(
        entry
        for entry in inventory_config["inventory"]["products"]
        if entry["product_id"] == product_id
    )


def _product(products_config, product_id):
    return next(
        product
        for product in products_config["products"]
        if product["product_id"] == product_id
    )


def _record(records, day_offset, product_id):
    day_records = records[day_offset * 9 : (day_offset + 1) * 9]
    return next(record for record in day_records if record["product_id"] == product_id)


def _cli_arguments(output_path):
    return [
        "--products-config",
        str(PRODUCTS_PATH),
        "--delivery-config",
        str(DELIVERY_PATH),
        "--generation-config",
        str(GENERATION_PATH),
        "--inventory-config",
        str(INVENTORY_PATH),
        "--output",
        str(output_path),
    ]
