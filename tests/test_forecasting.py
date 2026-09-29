from copy import deepcopy
from datetime import date
import math
from pathlib import Path

import pytest

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_products_config,
)
from smartstock.forecasting import (
    FORECAST_RECORD_COLUMNS,
    calculate_mean_absolute_error,
    calculate_weighted_absolute_percentage_error,
    classify_metric_result,
    forecast_cycle_with_expanding_weekday_mean,
    generate_cycle_forecast_records,
    summarize_forecasts,
    validate_forecast_records,
)
from smartstock.generator import generate_daily_records

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
def demand_records(configurations):
    return generate_daily_records(*configurations, seed=42)


@pytest.fixture
def forecast_records(configurations, demand_records):
    products, delivery, _ = configurations
    return generate_cycle_forecast_records(
        demand_records,
        products,
        delivery,
    )


def test_default_pipeline_creates_twenty_seven_forecasts_for_nine_products(
    forecast_records,
):
    assert len(forecast_records) == 27
    assert {record["product_id"] for record in forecast_records} == (
        APPROVED_PRODUCT_IDS
    )
    assert sorted(
        {record["forecast_origin_date"] for record in forecast_records}
    ) == ["2025-01-21", "2025-02-04", "2025-02-18"]


def test_forecasts_follow_origin_and_product_configuration_order(
    configurations,
    forecast_records,
):
    expected_product_order = [
        product["product_id"] for product in configurations[0]["products"]
    ]

    for origin_index in range(3):
        start = origin_index * 9
        assert [
            record["product_id"]
            for record in forecast_records[start : start + 9]
        ] == expected_product_order


def test_forecast_records_use_exact_privacy_safe_schema(forecast_records):
    assert all(
        tuple(record) == FORECAST_RECORD_COLUMNS for record in forecast_records
    )
    assert set(FORECAST_RECORD_COLUMNS) == {
        "forecast_origin_date",
        "training_start_date",
        "training_end_date",
        "target_start_date",
        "target_end_date",
        "product_id",
        "actual_demand_units",
        "baseline_prediction_units",
        "candidate_prediction_units",
        "baseline_absolute_error_units",
        "candidate_absolute_error_units",
    }


def test_forecast_windows_are_chronological_and_complete(forecast_records):
    expected_windows = {
        "2025-01-21": ("2025-01-07", "2025-01-20", "2025-02-03"),
        "2025-02-04": ("2025-01-07", "2025-02-03", "2025-02-17"),
        "2025-02-18": ("2025-01-07", "2025-02-17", "2025-03-03"),
    }

    for record in forecast_records:
        training_start, training_end, target_end = expected_windows[
            record["forecast_origin_date"]
        ]
        assert record["training_start_date"] == training_start
        assert record["training_end_date"] == training_end
        assert record["target_start_date"] == record["forecast_origin_date"]
        assert record["target_end_date"] == target_end
        assert record["training_end_date"] < record["target_start_date"]


def test_previous_cycle_baseline_uses_only_completed_pre_origin_dates(
    demand_records,
    forecast_records,
):
    first = forecast_records[0]
    expected = sum(
        record["demand_units"]
        for record in demand_records
        if record["product_id"] == "Milk_Product_A"
        and "2025-01-07" <= record["date"] <= "2025-01-20"
    )

    assert first["product_id"] == "Milk_Product_A"
    assert first["baseline_prediction_units"] == expected


def test_first_weekday_mean_equals_first_previous_cycle_total(forecast_records):
    for record in forecast_records[:9]:
        assert record["candidate_prediction_units"] == pytest.approx(
            record["baseline_prediction_units"]
        )


def test_weekday_mean_uses_all_matching_pre_origin_observations(
    demand_records,
):
    product_id = "Milk_Product_A"
    forecast_origin = date(2025, 2, 4)
    historical = [
        record
        for record in demand_records
        if record["product_id"] == product_id
        and record["date"] < forecast_origin.isoformat()
    ]
    expected = sum(
        sum(
            record["demand_units"]
            for record in historical
            if record["weekday"] == weekday
        )
        / sum(1 for record in historical if record["weekday"] == weekday)
        for weekday in (
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
            "Monday",
        )
        for _ in range(2)
    )

    actual = forecast_cycle_with_expanding_weekday_mean(
        demand_records,
        product_id,
        forecast_origin,
        14,
    )

    assert actual == pytest.approx(expected)


def test_future_demand_does_not_change_existing_predictions(
    configurations,
    demand_records,
    forecast_records,
):
    products, delivery, _ = configurations
    changed = deepcopy(demand_records)
    for record in changed:
        if record["date"] >= "2025-01-21":
            record["demand_units"] += 100

    changed_forecasts = generate_cycle_forecast_records(
        changed,
        products,
        delivery,
    )

    for original, changed_record in zip(
        forecast_records[:9],
        changed_forecasts[:9],
        strict=True,
    ):
        assert changed_record["baseline_prediction_units"] == (
            original["baseline_prediction_units"]
        )
        assert changed_record["candidate_prediction_units"] == (
            original["candidate_prediction_units"]
        )


def test_historical_demand_changes_the_relevant_prediction(
    configurations,
    demand_records,
    forecast_records,
):
    products, delivery, _ = configurations
    changed = deepcopy(demand_records)
    changed[0]["demand_units"] += 14

    changed_forecasts = generate_cycle_forecast_records(
        changed,
        products,
        delivery,
    )

    assert changed_forecasts[0]["baseline_prediction_units"] == (
        forecast_records[0]["baseline_prediction_units"] + 14
    )
    assert changed_forecasts[0]["candidate_prediction_units"] > (
        forecast_records[0]["candidate_prediction_units"]
    )


def test_incomplete_target_cycle_is_skipped(configurations, demand_records):
    products, delivery, _ = configurations
    incomplete_records = demand_records[: 55 * 9]

    forecasts = generate_cycle_forecast_records(
        incomplete_records,
        products,
        delivery,
    )

    assert len(forecasts) == 18
    assert {record["forecast_origin_date"] for record in forecasts} == {
        "2025-01-21",
        "2025-02-04",
    }


def test_insufficient_history_produces_no_forecast(configurations, demand_records):
    products, delivery, _ = configurations

    forecasts = generate_cycle_forecast_records(
        demand_records[: 13 * 9],
        products,
        delivery,
    )

    assert forecasts == []


def test_weekday_mean_returns_none_when_target_weekday_history_is_missing(
    demand_records,
):
    result = forecast_cycle_with_expanding_weekday_mean(
        demand_records[: 6 * 9],
        "Milk_Product_A",
        date(2025, 1, 13),
        14,
    )

    assert result is None


def test_default_forecasting_pipeline_is_deterministic(
    configurations,
    demand_records,
):
    products, delivery, _ = configurations

    first = generate_cycle_forecast_records(
        demand_records,
        products,
        delivery,
    )
    second = generate_cycle_forecast_records(
        demand_records,
        products,
        delivery,
    )

    assert first == second


def test_default_forecasting_pipeline_matches_reproducibility_anchors(
    configurations,
    forecast_records,
):
    assert forecast_records[0] == {
        "forecast_origin_date": "2025-01-21",
        "training_start_date": "2025-01-07",
        "training_end_date": "2025-01-20",
        "target_start_date": "2025-01-21",
        "target_end_date": "2025-02-03",
        "product_id": "Milk_Product_A",
        "actual_demand_units": 57,
        "baseline_prediction_units": 58,
        "candidate_prediction_units": 58.0,
        "baseline_absolute_error_units": 1,
        "candidate_absolute_error_units": 1.0,
    }

    summary = summarize_forecasts(forecast_records, configurations[0])
    assert summary["overall"]["baseline_mae_units"] == pytest.approx(
        3.4074074074074074
    )
    assert summary["overall"]["candidate_mae_units"] == pytest.approx(
        3.462962962962963
    )
    assert summary["overall"]["baseline_wape_percent"] == pytest.approx(
        6.375606375606376
    )
    assert summary["overall"]["candidate_wape_percent"] == pytest.approx(
        6.4795564795564795
    )
    assert summary["candidate_product_result_counts"] == {
        "wins": 5,
        "ties": 0,
        "losses": 4,
    }


def test_predictions_and_errors_are_nonnegative(forecast_records):
    numeric_columns = (
        "actual_demand_units",
        "baseline_prediction_units",
        "candidate_prediction_units",
        "baseline_absolute_error_units",
        "candidate_absolute_error_units",
    )
    assert all(
        record[column] >= 0
        for record in forecast_records
        for column in numeric_columns
    )


def test_validator_rejects_future_training_end(
    configurations,
    demand_records,
    forecast_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(forecast_records)
    invalid[0]["training_end_date"] = invalid[0]["forecast_origin_date"]

    with pytest.raises(ValueError, match="training_end_date"):
        validate_forecast_records(
            invalid,
            demand_records,
            products,
            delivery,
        )


def test_validator_rejects_invalid_column_order(
    configurations,
    demand_records,
    forecast_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(forecast_records)
    record = invalid[0]
    invalid[0] = {
        "training_start_date": record["training_start_date"],
        **record,
    }

    with pytest.raises(ValueError, match="exact column order"):
        validate_forecast_records(
            invalid,
            demand_records,
            products,
            delivery,
        )


def test_mae_matches_known_values_and_accepts_zero_actual_demand():
    assert calculate_mean_absolute_error([10, 0], [8, 3]) == pytest.approx(2.5)


def test_wape_is_returned_as_a_percentage():
    assert calculate_weighted_absolute_percentage_error(
        [10, 10],
        [8, 9.5],
    ) == pytest.approx(12.5)


def test_wape_can_exceed_one_hundred_percent():
    assert calculate_weighted_absolute_percentage_error([1], [3]) == 200.0


def test_wape_returns_none_when_total_actual_demand_is_zero():
    assert calculate_weighted_absolute_percentage_error([0, 0], [1, 2]) is None


@pytest.mark.parametrize(
    ("candidate", "baseline", "expected"),
    [
        (1.0, 2.0, "win"),
        (2.0, 1.0, "loss"),
        (1.0 + 0.9e-9, 1.0, "tie"),
        (1.0 + 1.1e-9, 1.0, "loss"),
    ],
)
def test_metric_result_uses_approved_tie_tolerance(
    candidate,
    baseline,
    expected,
):
    assert classify_metric_result(candidate, baseline) == expected


def test_metric_functions_reject_mismatched_or_nonfinite_values():
    with pytest.raises(ValueError, match="equal length"):
        calculate_mean_absolute_error([1], [1, 2])
    with pytest.raises(ValueError, match="finite"):
        calculate_weighted_absolute_percentage_error([1], [math.inf])


def test_summary_reports_all_products_and_win_tie_loss_counts(
    configurations,
    forecast_records,
):
    summary = summarize_forecasts(forecast_records, configurations[0])

    assert summary["overall"]["forecast_count"] == 27
    assert set(summary["by_product"]) == APPROVED_PRODUCT_IDS
    assert sum(summary["candidate_product_result_counts"].values()) == 9
    assert set(summary["candidate_product_result_counts"]) == {
        "wins",
        "ties",
        "losses",
    }
    for product_summary in summary["by_product"].values():
        assert product_summary["forecast_count"] == 3
        assert product_summary["candidate_result"] in {"win", "tie", "loss"}


def test_summary_rejects_floating_point_actual_demand(
    configurations,
    forecast_records,
):
    invalid = deepcopy(forecast_records)
    invalid[0]["actual_demand_units"] = 1.5

    with pytest.raises(ValueError, match="actual_demand_units must be an integer"):
        summarize_forecasts(invalid, configurations[0])


def test_summary_rejects_boolean_actual_demand(
    configurations,
    forecast_records,
):
    invalid = deepcopy(forecast_records)
    invalid[0]["actual_demand_units"] = True

    with pytest.raises(ValueError, match="actual_demand_units must be an integer"):
        summarize_forecasts(invalid, configurations[0])


def test_summary_rejects_negative_baseline_absolute_error(
    configurations,
    forecast_records,
):
    invalid = deepcopy(forecast_records)
    invalid[0]["baseline_absolute_error_units"] = -1

    with pytest.raises(
        ValueError,
        match="baseline_absolute_error_units cannot be negative",
    ):
        summarize_forecasts(invalid, configurations[0])


def test_summary_rejects_negative_candidate_absolute_error(
    configurations,
    forecast_records,
):
    invalid = deepcopy(forecast_records)
    invalid[0]["candidate_absolute_error_units"] = -1.0

    with pytest.raises(
        ValueError,
        match="candidate_absolute_error_units cannot be negative",
    ):
        summarize_forecasts(invalid, configurations[0])
