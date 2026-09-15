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
    load_ordering_config,
    load_products_config,
)
from smartstock.generator import generate_daily_records
from smartstock.inventory import simulate_inventory
from smartstock.ordering import (
    RECOMMENDATION_COLUMNS,
    SCENARIO_METRICS,
    calculate_baseline_cycle_demand,
    calculate_order_recommendation,
    compare_scenarios,
    main,
    round_up_to_full_packs,
    simulate_policy_inventory,
    summarize_scenario,
    validate_recommendation_records,
    write_recommendations_csv,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = PROJECT_ROOT / "config" / "products.yaml"
DELIVERY_PATH = PROJECT_ROOT / "config" / "delivery.yaml"
GENERATION_PATH = PROJECT_ROOT / "config" / "generation.yaml"
INVENTORY_PATH = PROJECT_ROOT / "config" / "inventory.yaml"
ORDERING_PATH = PROJECT_ROOT / "config" / "ordering.yaml"
PHASE_4B_CSV_SHA256 = (
    "6837650452c0266acb8b558212a0d14b9aa2e8ed35a22511c80c1fe18ebd3267"
)


@pytest.fixture
def configurations():
    products = load_products_config(PRODUCTS_PATH)
    delivery = load_delivery_config(DELIVERY_PATH)
    return (
        products,
        delivery,
        load_generation_config(GENERATION_PATH),
        load_inventory_config(INVENTORY_PATH, products),
        load_ordering_config(ORDERING_PATH, products, delivery),
    )


@pytest.fixture
def default_demand_records(configurations):
    return generate_daily_records(*configurations[:3])


@pytest.fixture
def default_policy_result(configurations, default_demand_records):
    products, delivery, _, inventory, ordering = configurations
    return simulate_policy_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )


@pytest.mark.parametrize(
    ("required_units", "pack_size_units", "expected_packs"),
    [(0, 4, 0), (1, 4, 1), (3, 4, 1), (4, 4, 1), (5, 4, 2), (12, 6, 2)],
)
def test_full_pack_rounding(required_units, pack_size_units, expected_packs):
    assert round_up_to_full_packs(required_units, pack_size_units) == expected_packs


@pytest.mark.parametrize(
    ("required_units", "pack_size_units"),
    [(True, 4), (-1, 4), (1, True), (1, 0), (1, 4.0)],
)
def test_full_pack_rounding_rejects_invalid_values(
    required_units,
    pack_size_units,
):
    with pytest.raises(ValueError):
        round_up_to_full_packs(required_units, pack_size_units)


def test_order_formula_subtracts_inventory_and_excludes_expiring_units():
    recommendation = calculate_order_recommendation(
        date(2025, 1, 21),
        "Milk_Product_A",
        baseline_cycle_demand_units=47,
        safety_stock_packs=0,
        current_usable_inventory_units=15,
        units_expiring_before_next_delivery=3,
        pack_size_units=4,
        cycle_length_days=14,
    )

    assert recommendation["safety_stock_units"] == 0
    assert recommendation["usable_inventory_position_units"] == 12
    assert recommendation["net_order_units"] == 35
    assert recommendation["recommended_order_packs"] == 9
    assert recommendation["recommended_order_units"] == 36


def test_order_formula_never_returns_negative_recommendation():
    recommendation = calculate_order_recommendation(
        date(2025, 1, 21),
        "Milk_Product_A",
        baseline_cycle_demand_units=4,
        safety_stock_packs=0,
        current_usable_inventory_units=10,
        units_expiring_before_next_delivery=0,
        pack_size_units=4,
        cycle_length_days=14,
    )

    assert recommendation["net_order_units"] == 0
    assert recommendation["recommended_order_packs"] == 0
    assert recommendation["recommended_order_units"] == 0


def test_nonzero_safety_stock_increases_target_and_full_pack_recommendation():
    recommendation = calculate_order_recommendation(
        date(2025, 1, 21),
        "Milk_Product_A",
        baseline_cycle_demand_units=9,
        safety_stock_packs=2,
        current_usable_inventory_units=5,
        units_expiring_before_next_delivery=1,
        pack_size_units=4,
        cycle_length_days=14,
    )

    assert recommendation["safety_stock_units"] == 8
    assert (
        recommendation["baseline_demand_units"]
        + recommendation["safety_stock_units"]
    ) == 17
    assert recommendation["usable_inventory_position_units"] == 4
    assert recommendation["net_order_units"] == 13
    assert recommendation["recommended_order_packs"] == 4
    assert recommendation["recommended_order_units"] == 16


def test_default_policy_creates_exactly_twenty_seven_recommendations(
    default_policy_result,
):
    _, recommendations = default_policy_result
    assert len(recommendations) == 27
    assert {record["product_id"] for record in recommendations} == (
        APPROVED_PRODUCT_IDS
    )
    assert sorted({record["delivery_date"] for record in recommendations}) == [
        "2025-01-21",
        "2025-02-04",
        "2025-02-18",
    ]
    assert all(
        record["delivery_date"] != "2025-01-07"
        for record in recommendations
    )


def test_default_recommendations_are_minimal_full_pack_multiples(
    default_policy_result,
):
    for record in default_policy_result[1]:
        pack_size = record["pack_size_units"]
        recommended_units = record["recommended_order_units"]
        net_units = record["net_order_units"]
        assert recommended_units % pack_size == 0
        assert recommended_units >= net_units
        assert recommended_units - net_units < pack_size


def test_recommendations_follow_product_configuration_order(
    configurations,
    default_policy_result,
):
    expected_order = [
        product["product_id"] for product in configurations[0]["products"]
    ]
    recommendations = default_policy_result[1]

    for date_offset in range(3):
        start = date_offset * 9
        assert [
            record["product_id"]
            for record in recommendations[start : start + 9]
        ] == expected_order


def test_reordered_ordering_entries_do_not_change_output(
    configurations,
    default_demand_records,
    default_policy_result,
):
    products, delivery, _, inventory, ordering = deepcopy(configurations)
    ordering["ordering"]["products"].reverse()

    reordered_result = simulate_policy_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )

    assert reordered_result == default_policy_result


def test_first_history_window_uses_exactly_completed_dates(
    default_demand_records,
    default_policy_result,
):
    first = default_policy_result[1][0]
    expected_demand = sum(
        record["demand_units"]
        for record in default_demand_records
        if record["product_id"] == "Milk_Product_A"
        and "2025-01-07" <= record["date"] <= "2025-01-20"
    )

    assert first["history_start_date"] == "2025-01-07"
    assert first["history_end_date"] == "2025-01-20"
    assert first["baseline_demand_units"] == expected_demand


def test_insufficient_history_produces_no_baseline(configurations):
    demand_records = _demand_records(configurations[0], 13)

    assert calculate_baseline_cycle_demand(
        demand_records,
        "Milk_Product_A",
        date(2025, 1, 21),
        14,
    ) is None


def test_current_and_future_demand_do_not_change_existing_recommendation(
    configurations,
    default_demand_records,
    default_policy_result,
):
    products, delivery, _, inventory, ordering = configurations
    changed = deepcopy(default_demand_records)
    for record in changed:
        if record["date"] >= "2025-01-21":
            record["demand_units"] += 100

    changed_recommendations = simulate_policy_inventory(
        changed,
        products,
        delivery,
        inventory,
        ordering,
    )[1]

    assert changed_recommendations[:9] == default_policy_result[1][:9]


def test_historical_demand_changes_relevant_recommendation(
    configurations,
    default_demand_records,
    default_policy_result,
):
    products, delivery, _, inventory, ordering = configurations
    changed = deepcopy(default_demand_records)
    changed[0]["demand_units"] += 20

    changed_recommendations = simulate_policy_inventory(
        changed,
        products,
        delivery,
        inventory,
        ordering,
    )[1]

    original_recommendation = default_policy_result[1][0]
    changed_recommendation = changed_recommendations[0]
    assert changed_recommendation["baseline_demand_units"] == (
        original_recommendation["baseline_demand_units"] + 20
    )


def test_reordered_demand_records_fail_before_recommendation(
    configurations,
    default_demand_records,
):
    products, delivery, _, inventory, ordering = configurations
    reordered = deepcopy(default_demand_records)
    reordered[0], reordered[1] = reordered[1], reordered[0]

    with pytest.raises(ValueError, match="product order"):
        simulate_policy_inventory(
            reordered,
            products,
            delivery,
            inventory,
            ordering,
        )


def test_baseline_uses_demand_even_when_it_was_unmet(configurations):
    products, delivery, _, inventory, ordering = _isolated_configurations(
        configurations
    )
    target_id = "Milk_Product_A"
    demand_records = _demand_records(products, 15, {(0, target_id): 8})

    _, recommendations = simulate_policy_inventory(
        demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )

    first = _recommendation(recommendations, "2025-01-21", target_id)
    assert first["baseline_demand_units"] == 8
    assert first["recommended_order_units"] == 8


def test_same_day_expiration_precedes_recommendation(configurations):
    products, delivery, _, inventory, ordering = _isolated_configurations(
        configurations
    )
    target_id = "Milk_Product_A"
    _product(products, target_id)["unopened_shelf_life_days"] = 14
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 5
    demand_records = _demand_records(products, 15)

    policy_records, recommendations = simulate_policy_inventory(
        demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )
    recommendation = _recommendation(recommendations, "2025-01-21", target_id)
    day_fourteen = _inventory_record(policy_records, 14, target_id)

    assert day_fourteen["expired_units"] == 5
    assert recommendation["current_usable_inventory_units"] == 0


def test_cohort_expiring_on_next_delivery_date_remains_credited(configurations):
    products, delivery, _, inventory, ordering = _isolated_configurations(
        configurations
    )
    target_id = "Milk_Product_A"
    _product(products, target_id)["unopened_shelf_life_days"] = 28
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 5

    _, recommendations = simulate_policy_inventory(
        _demand_records(products, 15),
        products,
        delivery,
        inventory,
        ordering,
    )
    recommendation = _recommendation(recommendations, "2025-01-21", target_id)

    assert recommendation["current_usable_inventory_units"] == 5
    assert recommendation["units_expiring_before_next_delivery"] == 0
    assert recommendation["usable_inventory_position_units"] == 5


def test_earlier_expiring_cohort_receives_zero_inventory_credit(configurations):
    products, delivery, _, inventory, ordering = _isolated_configurations(
        configurations
    )
    target_id = "Milk_Product_A"
    _product(products, target_id)["unopened_shelf_life_days"] = 20
    _inventory_entry(inventory, target_id)["starting_inventory_units"] = 5

    _, recommendations = simulate_policy_inventory(
        _demand_records(products, 15),
        products,
        delivery,
        inventory,
        ordering,
    )
    recommendation = _recommendation(recommendations, "2025-01-21", target_id)

    assert recommendation["current_usable_inventory_units"] == 5
    assert recommendation["units_expiring_before_next_delivery"] == 5
    assert recommendation["usable_inventory_position_units"] == 0


def test_warm_up_records_match_fixed_scenario(configurations, default_demand_records):
    products, delivery, _, inventory, ordering = configurations
    fixed_records = simulate_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
    )
    policy_records, _ = simulate_policy_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )

    assert policy_records[: 14 * 9] == fixed_records[: 14 * 9]


def test_policy_state_matches_fixed_state_before_day_fourteen_delivery(
    configurations,
    default_demand_records,
):
    products, delivery, _, inventory, ordering = configurations
    fixed_records = simulate_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
    )
    _, recommendations = simulate_policy_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )

    for recommendation in recommendations[:9]:
        fixed = _inventory_record(
            fixed_records,
            14,
            recommendation["product_id"],
        )
        assert recommendation["current_usable_inventory_units"] == (
            fixed["starting_inventory_units"] - fixed["expired_units"]
        )


def test_policy_delivery_replaces_fixed_delivery_after_warm_up(
    configurations,
    default_demand_records,
):
    products, delivery, _, inventory, ordering = configurations
    policy_records, recommendations = simulate_policy_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )

    for recommendation in recommendations:
        day_offset = (
            date.fromisoformat(recommendation["delivery_date"])
            - date(2025, 1, 7)
        ).days
        policy_record = _inventory_record(
            policy_records,
            day_offset,
            recommendation["product_id"],
        )
        assert policy_record["delivered_units"] == (
            recommendation["recommended_order_units"]
        )


def test_policy_records_preserve_inventory_and_demand_balances(
    default_policy_result,
):
    policy_records = default_policy_result[0]
    prior_ending: dict[str, int] = {}
    for record in policy_records:
        assert record["available_inventory_units"] == (
            record["starting_inventory_units"]
            - record["expired_units"]
            + record["delivered_units"]
        )
        assert record["ending_inventory_units"] == (
            record["available_inventory_units"] - record["units_used"]
        )
        assert record["demand_units"] == (
            record["fulfilled_demand_units"] + record["unmet_demand_units"]
        )
        assert record["units_used"] == record["fulfilled_demand_units"]
        product_id = record["product_id"]
        if product_id in prior_ending:
            assert record["starting_inventory_units"] == prior_ending[product_id]
        prior_ending[product_id] = record["ending_inventory_units"]


def test_recommended_inventory_enters_as_fresh_cohort(configurations):
    products, delivery, _, inventory, ordering = _isolated_configurations(
        configurations
    )
    target_id = "Milk_Product_A"
    _product(products, target_id)["unopened_shelf_life_days"] = 14
    demand_records = _demand_records(products, 29, {(0, target_id): 4})

    policy_records, recommendations = simulate_policy_inventory(
        demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )

    assert _recommendation(
        recommendations,
        "2025-01-21",
        target_id,
    )["recommended_order_units"] == 4
    assert _inventory_record(policy_records, 14, target_id)["delivered_units"] == 4
    assert _inventory_record(policy_records, 28, target_id)["expired_units"] == 4


def test_recommendation_csv_uses_exact_portable_bytes_and_golden_hash(
    configurations,
    default_demand_records,
    default_policy_result,
    tmp_path,
):
    products, delivery, _, _, ordering = configurations
    output_path = tmp_path / "recommendations.csv"
    recommendations = default_policy_result[1]

    write_recommendations_csv(
        recommendations,
        output_path,
        default_demand_records,
        products,
        delivery,
        ordering,
    )
    csv_bytes = output_path.read_bytes()
    expected_header = b",".join(
        column.encode("ascii") for column in RECOMMENDATION_COLUMNS
    ) + b"\n"

    assert csv_bytes.startswith(expected_header)
    assert not csv_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in csv_bytes
    assert csv_bytes.endswith(b"\n")
    assert not csv_bytes.endswith(b"\n\n")
    assert csv_bytes.count(b"\n") == 28
    assert hashlib.sha256(csv_bytes).hexdigest() == PHASE_4B_CSV_SHA256
    assert csv_bytes.splitlines()[1] == (
        b"2025-01-21,2025-01-21,2025-01-07,2025-01-20,"
        b"Milk_Product_A,58,0,14,0,14,44,4,11,44"
    )


def test_same_seed_creates_identical_recommendation_records_and_bytes(
    configurations,
    default_demand_records,
    tmp_path,
):
    products, delivery, _, inventory, ordering = configurations
    first = simulate_policy_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )[1]
    second = simulate_policy_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
        ordering,
    )[1]
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    for records, output_path in ((first, first_path), (second, second_path)):
        write_recommendations_csv(
            records,
            output_path,
            default_demand_records,
            products,
            delivery,
            ordering,
        )

    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()


def test_different_seed_changes_recommendation_output(configurations):
    products, delivery, generation, inventory, ordering = configurations
    first_demand = generate_daily_records(products, delivery, generation, seed=42)
    second_demand = generate_daily_records(products, delivery, generation, seed=99)

    first = simulate_policy_inventory(
        first_demand,
        products,
        delivery,
        inventory,
        ordering,
    )[1]
    second = simulate_policy_inventory(
        second_demand,
        products,
        delivery,
        inventory,
        ordering,
    )[1]

    assert first != second


def test_invalid_recommendation_fails_before_output_creation(
    configurations,
    default_demand_records,
    default_policy_result,
    tmp_path,
):
    products, delivery, _, _, ordering = configurations
    invalid = deepcopy(default_policy_result[1])
    invalid[0]["recommended_order_units"] += 1
    output_path = tmp_path / "recommendations.csv"

    with pytest.raises(ValueError, match="recommended_order_units"):
        write_recommendations_csv(
            invalid,
            output_path,
            default_demand_records,
            products,
            delivery,
            ordering,
        )

    assert not output_path.exists()


def test_invalid_recommendation_does_not_overwrite_existing_output(
    configurations,
    default_demand_records,
    default_policy_result,
    tmp_path,
):
    products, delivery, _, _, ordering = configurations
    invalid = deepcopy(default_policy_result[1])
    invalid[0]["net_order_units"] += 1
    output_path = tmp_path / "recommendations.csv"
    output_path.write_bytes(b"preserve existing bytes\n")

    with pytest.raises(ValueError, match="net_order_units"):
        write_recommendations_csv(
            invalid,
            output_path,
            default_demand_records,
            products,
            delivery,
            ordering,
        )

    assert output_path.read_bytes() == b"preserve existing bytes\n"


def test_recommendation_csv_contains_only_privacy_safe_fields(
    configurations,
    default_demand_records,
    default_policy_result,
    tmp_path,
):
    products, delivery, _, _, ordering = configurations
    output_path = tmp_path / "recommendations.csv"
    write_recommendations_csv(
        default_policy_result[1],
        output_path,
        default_demand_records,
        products,
        delivery,
        ordering,
    )

    with output_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        assert tuple(reader.fieldnames or ()) == RECOMMENDATION_COLUMNS
        assert all(row["product_id"] in APPROVED_PRODUCT_IDS for row in reader)


def test_scenario_comparison_has_required_metrics_and_deltas(
    configurations,
    default_demand_records,
    default_policy_result,
):
    products, delivery, _, inventory, _ = configurations
    fixed_records = simulate_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
    )
    policy_records = default_policy_result[0]

    comparison = compare_scenarios(
        fixed_records,
        policy_records,
        products,
        date(2025, 1, 21),
    )

    assert comparison["evaluation_start_date"] == "2025-01-21"
    assert tuple(comparison["fixed"]["overall"]) == SCENARIO_METRICS
    assert tuple(comparison["policy"]["overall"]) == SCENARIO_METRICS
    assert tuple(comparison["difference"]["overall"]) == SCENARIO_METRICS
    assert set(comparison["fixed"]["by_product"]) == APPROVED_PRODUCT_IDS
    for metric in SCENARIO_METRICS:
        assert comparison["difference"]["overall"][metric] == (
            comparison["policy"]["overall"][metric]
            - comparison["fixed"]["overall"][metric]
        )
    for product_id in APPROVED_PRODUCT_IDS:
        for metric in SCENARIO_METRICS:
            assert comparison["difference"]["by_product"][product_id][metric] == (
                comparison["policy"]["by_product"][product_id][metric]
                - comparison["fixed"]["by_product"][product_id][metric]
            )
    assert "score" not in comparison
    assert comparison == compare_scenarios(
        fixed_records,
        policy_records,
        products,
        date(2025, 1, 21),
    )


def test_default_scenario_comparison_matches_approved_overall_metrics(
    configurations,
    default_demand_records,
    default_policy_result,
):
    products, delivery, _, inventory, _ = configurations
    fixed_records = simulate_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
    )
    comparison = compare_scenarios(
        fixed_records,
        default_policy_result[0],
        products,
        date(2025, 1, 21),
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


def test_delivered_pack_summary_uses_each_product_pack_size(
    configurations,
    default_policy_result,
):
    products = configurations[0]
    policy_records = default_policy_result[0]
    summary = summarize_scenario(
        policy_records,
        products,
        date(2025, 1, 21),
    )
    pack_size_by_id = {
        product["product_id"]: product["pack_size_units"]
        for product in products["products"]
    }

    for product_id, metrics in summary["by_product"].items():
        expected_packs = sum(
            record["delivered_units"] // pack_size_by_id[product_id]
            for record in policy_records
            if record["product_id"] == product_id
            and record["date"] >= "2025-01-21"
        )
        assert metrics["total_delivered_packs"] == expected_packs


def test_scenario_comparison_rejects_different_demand(
    configurations,
    default_demand_records,
    default_policy_result,
):
    products, delivery, _, inventory, _ = configurations
    fixed_records = simulate_inventory(
        default_demand_records,
        products,
        delivery,
        inventory,
    )
    changed_policy = deepcopy(default_policy_result[0])
    changed_policy[14 * 9]["demand_units"] += 1

    with pytest.raises(ValueError, match="identical demand"):
        compare_scenarios(
            fixed_records,
            changed_policy,
            products,
            date(2025, 1, 21),
        )


def test_cli_succeeds_with_explicit_output_and_prints_comparison(
    tmp_path,
    capsys,
):
    output_path = tmp_path / "recommendations.csv"

    exit_code = main(_cli_arguments(output_path))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Generated 27 recommendation records at {output_path}" in captured.out
    assert "with seed 42." in captured.out
    assert "Synthetic scenario comparison from 2025-01-21" in captured.out
    assert "do not demonstrate real-world improvement" in captured.out
    assert captured.err == ""
    assert output_path.is_file()


def test_cli_uses_default_paths_seed_and_output(tmp_path, monkeypatch, capsys):
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    for source_path in (
        PRODUCTS_PATH,
        DELIVERY_PATH,
        GENERATION_PATH,
        INVENTORY_PATH,
        ORDERING_PATH,
    ):
        shutil.copyfile(source_path, config_directory / source_path.name)
    monkeypatch.chdir(tmp_path)

    exit_code = main([])

    output_path = Path("data/generated/synthetic_order_recommendations.csv")
    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.is_file()
    assert "Generated 27 recommendation records" in captured.out
    assert "with seed 42." in captured.out
    assert hashlib.sha256(output_path.read_bytes()).hexdigest() == (
        PHASE_4B_CSV_SHA256
    )


def test_cli_failure_returns_nonzero_without_partial_output(tmp_path, capsys):
    invalid_ordering_path = tmp_path / "ordering.yaml"
    invalid_ordering_path.write_text("ordering: {}\n", encoding="utf-8")
    output_path = tmp_path / "recommendations.csv"

    exit_code = main(
        [
            *_cli_arguments(output_path),
            "--ordering-config",
            str(invalid_ordering_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Error:" in captured.err
    assert not output_path.exists()


def test_cli_rejects_invalid_seed(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        main([*_cli_arguments(tmp_path / "recommendations.csv"), "--seed", "bad"])

    assert exc_info.value.code != 0


def test_recommendation_validator_rejects_extra_private_field(
    configurations,
    default_demand_records,
    default_policy_result,
):
    products, delivery, _, _, ordering = configurations
    invalid = deepcopy(default_policy_result[1])
    invalid[0]["private_field"] = "not allowed"

    with pytest.raises(ValueError, match="exact column order"):
        validate_recommendation_records(
            invalid,
            default_demand_records,
            products,
            delivery,
            ordering,
        )


def _isolated_configurations(configurations):
    products, delivery, generation, inventory, ordering = deepcopy(configurations)
    for entry in inventory["inventory"]["products"]:
        entry["starting_inventory_units"] = 0
        entry["delivery_pack_count"] = 0
    return products, delivery, generation, inventory, ordering


def _demand_records(products_config, duration_days, demand_overrides=None):
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


def _recommendation(records, delivery_date, product_id):
    return next(
        record
        for record in records
        if record["delivery_date"] == delivery_date
        and record["product_id"] == product_id
    )


def _inventory_record(records, day_offset, product_id):
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
        "--ordering-config",
        str(ORDERING_PATH),
        "--output",
        str(output_path),
    ]
