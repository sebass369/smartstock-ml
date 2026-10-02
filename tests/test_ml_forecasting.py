from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    ENGLISH_WEEKDAYS,
    load_delivery_config,
    load_generation_config,
    load_products_config,
)
from smartstock.forecasting import (
    generate_cycle_forecast_records,
    list_complete_forecast_origins,
    summarize_forecasts,
)
from smartstock.generator import generate_daily_records
from smartstock.ml_forecasting import (
    FEATURE_COLUMNS,
    ML_FORECAST_RECORD_COLUMNS,
    MODEL_PRODUCT_CATEGORIES,
    MODEL_WEEKDAY_CATEGORIES,
    TRAINING_ROW_COLUMNS,
    build_demand_model,
    build_target_feature_rows,
    build_training_rows,
    fit_demand_model,
    generate_ml_cycle_forecast_records,
    predict_daily_demand,
    summarize_ml_forecasts,
    validate_ml_forecast_records,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = PROJECT_ROOT / "config"

FIRST_ORIGIN = date(2025, 1, 21)
SECOND_ORIGIN = date(2025, 2, 4)
THIRD_ORIGIN = date(2025, 2, 18)
CYCLE_LENGTH_DAYS = 14
PRODUCT_COUNT = 9

PROHIBITED_FEATURE_COLUMNS = (
    "is_high_demand_day",
    "delivery_event",
    "date",
    "starting_inventory_units",
    "delivered_units",
    "expired_units",
    "available_inventory_units",
    "fulfilled_demand_units",
    "units_used",
    "unmet_demand_units",
    "waste_units",
    "ending_inventory_units",
    "stockout_event",
    "recommended_order_units",
    "recommended_order_packs",
    "pack_size_units",
    "open_shelf_life_days",
    "unopened_shelf_life_days",
    "demand_level",
    "primary_risk",
)


@pytest.fixture
def configurations():
    return (
        load_products_config(CONFIG_ROOT / "products.yaml"),
        load_delivery_config(CONFIG_ROOT / "delivery.yaml"),
        load_generation_config(CONFIG_ROOT / "generation.yaml"),
    )


@pytest.fixture
def demand_records(configurations):
    return generate_daily_records(*configurations, seed=42)


@pytest.fixture
def product_order(configurations):
    return [product["product_id"] for product in configurations[0]["products"]]


@pytest.fixture
def ml_records(configurations, demand_records):
    products, delivery, _ = configurations
    return generate_ml_cycle_forecast_records(demand_records, products, delivery)


# --- Training-row selection -------------------------------------------------


def test_build_training_rows_accepts_the_complete_dataset_and_filters_by_origin(
    demand_records,
):
    rows = build_training_rows(demand_records, FIRST_ORIGIN)

    assert len(demand_records) == 504
    assert len(rows) == 126


def test_build_training_rows_excludes_the_forecast_origin_date(demand_records):
    before = build_training_rows(demand_records, FIRST_ORIGIN)
    including_origin = build_training_rows(
        demand_records,
        FIRST_ORIGIN + timedelta(days=1),
    )

    assert len(including_origin) - len(before) == PRODUCT_COUNT


def test_every_training_row_is_strictly_before_the_forecast_origin(demand_records):
    allowed_weekdays = {
        (FIRST_ORIGIN - timedelta(days=offset)).strftime("%A")
        for offset in range(1, 15)
    }

    rows = build_training_rows(demand_records, FIRST_ORIGIN)

    assert {row["weekday"] for row in rows} == allowed_weekdays
    expected_total = sum(
        record["demand_units"]
        for record in demand_records
        if record["date"] < FIRST_ORIGIN.isoformat()
    )
    assert sum(row["demand_units"] for row in rows) == expected_total


def test_build_training_rows_returns_expected_row_counts_for_each_origin(
    demand_records,
):
    counts = [
        len(build_training_rows(demand_records, origin))
        for origin in (FIRST_ORIGIN, SECOND_ORIGIN, THIRD_ORIGIN)
    ]

    assert counts == [126, 252, 378]


def test_build_training_rows_uses_only_approved_feature_and_target_columns(
    demand_records,
):
    rows = build_training_rows(demand_records, THIRD_ORIGIN)

    assert TRAINING_ROW_COLUMNS == ("product_id", "weekday", "demand_units")
    assert all(tuple(row) == TRAINING_ROW_COLUMNS for row in rows)
    for prohibited_column in PROHIBITED_FEATURE_COLUMNS:
        assert all(prohibited_column not in row for row in rows)


def test_build_training_rows_rejects_an_unknown_product_alias(demand_records):
    invalid = deepcopy(demand_records)
    invalid[0]["product_id"] = "Donut_Product"

    with pytest.raises(ValueError, match="Unknown product ID"):
        build_training_rows(invalid, FIRST_ORIGIN)


def test_build_training_rows_rejects_negative_demand_units(demand_records):
    invalid = deepcopy(demand_records)
    invalid[0]["demand_units"] = -1

    with pytest.raises(ValueError, match="demand_units cannot be negative"):
        build_training_rows(invalid, FIRST_ORIGIN)


def test_build_training_rows_rejects_boolean_demand_units(demand_records):
    invalid = deepcopy(demand_records)
    invalid[0]["demand_units"] = True

    with pytest.raises(ValueError, match="demand_units must be an integer"):
        build_training_rows(invalid, FIRST_ORIGIN)


def test_build_training_rows_rejects_an_invalid_date_field(demand_records):
    invalid = deepcopy(demand_records)
    invalid[0]["date"] = "not-a-date"

    with pytest.raises(ValueError, match="date must be a valid ISO date"):
        build_training_rows(invalid, FIRST_ORIGIN)


def test_build_training_rows_rejects_a_noncanonical_date_format(demand_records):
    invalid = deepcopy(demand_records)
    invalid[0]["date"] = "20250107"

    with pytest.raises(ValueError, match="date must use the ISO"):
        build_training_rows(invalid, FIRST_ORIGIN)


def test_build_training_rows_rejects_an_empty_dataset():
    with pytest.raises(ValueError, match="nonempty list"):
        build_training_rows([], FIRST_ORIGIN)


# --- Target feature rows ----------------------------------------------------


def test_build_target_feature_rows_covers_fourteen_days_for_nine_products(
    product_order,
):
    rows = build_target_feature_rows(FIRST_ORIGIN, CYCLE_LENGTH_DAYS, product_order)

    assert len(rows) == PRODUCT_COUNT * CYCLE_LENGTH_DAYS
    assert [row["product_id"] for row in rows[:CYCLE_LENGTH_DAYS]] == (
        [product_order[0]] * CYCLE_LENGTH_DAYS
    )
    assert [row["weekday"] for row in rows[:CYCLE_LENGTH_DAYS]] == [
        (FIRST_ORIGIN + timedelta(days=offset)).strftime("%A")
        for offset in range(CYCLE_LENGTH_DAYS)
    ]


def test_build_target_feature_rows_uses_only_calendar_information(product_order):
    rows = build_target_feature_rows(FIRST_ORIGIN, CYCLE_LENGTH_DAYS, product_order)

    assert FEATURE_COLUMNS == ("product_id", "weekday")
    assert all(tuple(row) == FEATURE_COLUMNS for row in rows)
    assert all("demand_units" not in row for row in rows)


def test_build_target_feature_rows_rejects_an_unknown_product_alias():
    with pytest.raises(ValueError, match="Unknown product ID"):
        build_target_feature_rows(FIRST_ORIGIN, CYCLE_LENGTH_DAYS, ["Donut_Product"])


# --- Pipeline configuration -------------------------------------------------


def test_demand_model_encodes_configured_product_and_weekday_categories():
    encoder = build_demand_model().named_steps["features"].transformers[0][1]

    assert MODEL_PRODUCT_CATEGORIES == tuple(sorted(APPROVED_PRODUCT_IDS))
    assert MODEL_WEEKDAY_CATEGORIES == tuple(ENGLISH_WEEKDAYS)
    assert encoder.categories == [
        list(MODEL_PRODUCT_CATEGORIES),
        list(MODEL_WEEKDAY_CATEGORIES),
    ]
    assert encoder.handle_unknown == "error"
    assert encoder.drop == "first"


def test_demand_model_uses_no_numeric_scaling_step():
    assert list(build_demand_model().named_steps) == ["features", "regressor"]


def test_demand_model_uses_a_linear_regression_without_randomness():
    regressor = build_demand_model().named_steps["regressor"]

    assert type(regressor).__name__ == "LinearRegression"
    assert regressor.fit_intercept is True
    assert not hasattr(regressor, "random_state")


def test_fitted_model_produces_one_coefficient_per_encoded_category(demand_records):
    model = fit_demand_model(build_training_rows(demand_records, FIRST_ORIGIN))

    expected_feature_count = (len(MODEL_PRODUCT_CATEGORIES) - 1) + (
        len(MODEL_WEEKDAY_CATEGORIES) - 1
    )
    assert len(model.named_steps["regressor"].coef_) == expected_feature_count


def test_fitted_model_rejects_an_unknown_one_hot_category(demand_records):
    model = fit_demand_model(build_training_rows(demand_records, FIRST_ORIGIN))

    with pytest.raises(ValueError, match="unknown categories"):
        model.predict([["Donut_Product", "Monday"]])


def test_fit_demand_model_rejects_history_missing_a_product(demand_records):
    rows = [
        row
        for row in build_training_rows(demand_records, FIRST_ORIGIN)
        if row["product_id"] != "Skim_Milk"
    ]

    with pytest.raises(ValueError, match="every approved product alias"):
        fit_demand_model(rows)


def test_fit_demand_model_rejects_history_missing_a_weekday(demand_records):
    rows = [
        row
        for row in build_training_rows(demand_records, FIRST_ORIGIN)
        if row["weekday"] != "Sunday"
    ]

    with pytest.raises(ValueError, match="every English weekday"):
        fit_demand_model(rows)


def test_fit_demand_model_rejects_empty_training_rows():
    with pytest.raises(ValueError, match="nonempty list"):
        fit_demand_model([])


# --- Daily prediction behavior ----------------------------------------------


def test_predict_daily_demand_returns_finite_nonnegative_floats(
    demand_records,
    product_order,
):
    model = fit_demand_model(build_training_rows(demand_records, FIRST_ORIGIN))
    feature_rows = build_target_feature_rows(
        FIRST_ORIGIN,
        CYCLE_LENGTH_DAYS,
        product_order,
    )

    predictions = predict_daily_demand(model, feature_rows)

    assert len(predictions) == len(feature_rows)
    assert all(type(value) is float for value in predictions)
    assert all(value >= 0.0 for value in predictions)


def test_predict_daily_demand_clips_negative_estimates_to_zero(demand_records):
    model = fit_demand_model(build_training_rows(demand_records, FIRST_ORIGIN))
    model.named_steps["regressor"].intercept_ -= 1000.0
    feature_rows = [{"product_id": "Skim_Milk", "weekday": "Monday"}]

    assert model.predict([["Skim_Milk", "Monday"]])[0] < 0.0
    assert predict_daily_demand(model, feature_rows) == [0.0]


def test_predict_daily_demand_preserves_input_row_order(demand_records):
    model = fit_demand_model(build_training_rows(demand_records, FIRST_ORIGIN))
    feature_rows = [
        {"product_id": "Skim_Milk", "weekday": "Monday"},
        {"product_id": "Milk_Product_A", "weekday": "Monday"},
    ]

    forward = predict_daily_demand(model, feature_rows)
    reversed_values = predict_daily_demand(model, list(reversed(feature_rows)))

    assert forward == list(reversed(reversed_values))
    assert forward[0] < forward[1]


def test_predict_daily_demand_rejects_unapproved_feature_rows(demand_records):
    model = fit_demand_model(build_training_rows(demand_records, FIRST_ORIGIN))

    with pytest.raises(ValueError, match="Unknown product ID"):
        predict_daily_demand(model, [{"product_id": "Donut", "weekday": "Monday"}])
    with pytest.raises(ValueError, match="Unknown weekday"):
        predict_daily_demand(
            model,
            [{"product_id": "Skim_Milk", "weekday": "Caturday"}],
        )


def test_daily_nonnegative_clipping_does_not_bind_in_the_default_run(
    demand_records,
    product_order,
):
    minimum_raw_prediction = None
    for origin in (FIRST_ORIGIN, SECOND_ORIGIN, THIRD_ORIGIN):
        model = fit_demand_model(build_training_rows(demand_records, origin))
        feature_rows = build_target_feature_rows(
            origin,
            CYCLE_LENGTH_DAYS,
            product_order,
        )
        raw_predictions = model.predict(
            [[row["product_id"], row["weekday"]] for row in feature_rows]
        )
        clipped_predictions = predict_daily_demand(model, feature_rows)
        for raw_value, clipped_value in zip(
            raw_predictions,
            clipped_predictions,
            strict=True,
        ):
            assert float(raw_value) == clipped_value
            if minimum_raw_prediction is None or float(raw_value) < (
                minimum_raw_prediction
            ):
                minimum_raw_prediction = float(raw_value)

    assert minimum_raw_prediction is not None
    assert minimum_raw_prediction > 0.0


# --- Record contract and chronology -----------------------------------------


def test_ml_pipeline_creates_twenty_seven_records_for_three_origins(ml_records):
    assert len(ml_records) == 27
    assert {record["product_id"] for record in ml_records} == APPROVED_PRODUCT_IDS
    assert sorted({record["forecast_origin_date"] for record in ml_records}) == [
        "2025-01-21",
        "2025-02-04",
        "2025-02-18",
    ]


def test_ml_records_follow_origin_and_product_configuration_order(
    ml_records,
    product_order,
):
    for origin_index in range(3):
        start = origin_index * PRODUCT_COUNT
        assert [
            record["product_id"]
            for record in ml_records[start : start + PRODUCT_COUNT]
        ] == product_order


def test_ml_records_use_the_exact_phase_7b_schema(ml_records):
    assert all(
        tuple(record) == ML_FORECAST_RECORD_COLUMNS for record in ml_records
    )
    assert ML_FORECAST_RECORD_COLUMNS == (
        "forecast_origin_date",
        "training_start_date",
        "training_end_date",
        "target_start_date",
        "target_end_date",
        "product_id",
        "training_row_count",
        "actual_demand_units",
        "baseline_prediction_units",
        "candidate_prediction_units",
        "model_prediction_units",
        "baseline_absolute_error_units",
        "candidate_absolute_error_units",
        "model_absolute_error_units",
    )


def test_ml_records_report_expected_training_row_counts(ml_records):
    counts_by_origin = {
        record["forecast_origin_date"]: record["training_row_count"]
        for record in ml_records
    }

    assert counts_by_origin == {
        "2025-01-21": 126,
        "2025-02-04": 252,
        "2025-02-18": 378,
    }


def test_ml_forecast_windows_are_chronological_and_complete(ml_records):
    expected_windows = {
        "2025-01-21": ("2025-01-07", "2025-01-20", "2025-02-03"),
        "2025-02-04": ("2025-01-07", "2025-02-03", "2025-02-17"),
        "2025-02-18": ("2025-01-07", "2025-02-17", "2025-03-03"),
    }

    for record in ml_records:
        training_start, training_end, target_end = expected_windows[
            record["forecast_origin_date"]
        ]
        assert record["training_start_date"] == training_start
        assert record["training_end_date"] == training_end
        assert record["target_start_date"] == record["forecast_origin_date"]
        assert record["target_end_date"] == target_end
        assert record["training_end_date"] < record["target_start_date"]


def test_ml_forecast_covers_the_complete_fourteen_day_horizon(ml_records):
    for record in ml_records:
        start = date.fromisoformat(record["target_start_date"])
        end = date.fromisoformat(record["target_end_date"])
        assert (end - start).days + 1 == CYCLE_LENGTH_DAYS


def test_incomplete_target_cycle_is_skipped_by_the_ml_pipeline(
    configurations,
    demand_records,
):
    products, delivery, _ = configurations

    records = generate_ml_cycle_forecast_records(
        demand_records[: 55 * PRODUCT_COUNT],
        products,
        delivery,
    )

    assert len(records) == 18
    assert {record["forecast_origin_date"] for record in records} == {
        "2025-01-21",
        "2025-02-04",
    }


def test_insufficient_history_produces_no_ml_forecast(configurations, demand_records):
    products, delivery, _ = configurations

    records = generate_ml_cycle_forecast_records(
        demand_records[: 13 * PRODUCT_COUNT],
        products,
        delivery,
    )

    assert records == []


def test_ml_pipeline_reuses_the_shared_complete_origin_logic(demand_records):
    origins = list_complete_forecast_origins(
        demand_records,
        PRODUCT_COUNT,
        CYCLE_LENGTH_DAYS,
    )

    assert origins == [FIRST_ORIGIN, SECOND_ORIGIN, THIRD_ORIGIN]


def test_ml_pipeline_rejects_an_unknown_product_in_the_dataset(
    configurations,
    demand_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(demand_records)
    for record in invalid:
        if record["product_id"] == "Oat_Beverage":
            record["product_id"] = "Donut_Product"

    with pytest.raises(ValueError):
        generate_ml_cycle_forecast_records(invalid, products, delivery)


def test_ml_pipeline_rejects_an_invalid_demand_record_schema(
    configurations,
    demand_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(demand_records)
    invalid[0] = {"product_id": invalid[0]["product_id"], **invalid[0]}

    with pytest.raises(ValueError, match="exact Phase 3 column order"):
        generate_ml_cycle_forecast_records(invalid, products, delivery)


# --- Leakage ----------------------------------------------------------------


def test_future_demand_mutation_does_not_change_earlier_origin_predictions(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    changed = deepcopy(demand_records)
    for record in changed:
        if record["date"] >= FIRST_ORIGIN.isoformat():
            record["demand_units"] += 100

    changed_records = generate_ml_cycle_forecast_records(changed, products, delivery)

    prediction_columns = (
        "baseline_prediction_units",
        "candidate_prediction_units",
        "model_prediction_units",
    )
    for original, mutated in zip(
        ml_records[:PRODUCT_COUNT],
        changed_records[:PRODUCT_COUNT],
        strict=True,
    ):
        assert original["product_id"] == mutated["product_id"]
        for column in prediction_columns:
            assert mutated[column] == original[column]


def test_historical_demand_mutation_changes_the_relevant_model_prediction(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    changed = deepcopy(demand_records)
    changed[0]["demand_units"] += 14

    changed_records = generate_ml_cycle_forecast_records(changed, products, delivery)

    assert changed[0]["product_id"] == "Milk_Product_A"
    assert changed_records[0]["model_prediction_units"] > (
        ml_records[0]["model_prediction_units"]
    )
    assert changed_records[0]["model_prediction_units"] == pytest.approx(
        ml_records[0]["model_prediction_units"] + 14.0,
        rel=1e-9,
    )
    assert changed_records[1]["model_prediction_units"] == pytest.approx(
        ml_records[1]["model_prediction_units"],
        rel=1e-9,
    )


def test_model_inputs_exclude_generator_and_outcome_columns():
    for prohibited_column in PROHIBITED_FEATURE_COLUMNS:
        assert prohibited_column not in FEATURE_COLUMNS
        assert prohibited_column not in TRAINING_ROW_COLUMNS
    assert "is_high_demand_day" not in FEATURE_COLUMNS


def test_model_inputs_contain_only_the_product_alias_and_weekday():
    assert FEATURE_COLUMNS == ("product_id", "weekday")


# --- Fair comparison and metrics --------------------------------------------


def test_ml_and_phase_7a_records_cover_identical_origin_and_product_pairs(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    phase_7a_records = generate_cycle_forecast_records(
        demand_records,
        products,
        delivery,
    )

    assert len(phase_7a_records) == len(ml_records) == 27
    for phase_7a, phase_7b in zip(phase_7a_records, ml_records, strict=True):
        assert phase_7a["forecast_origin_date"] == phase_7b["forecast_origin_date"]
        assert phase_7a["product_id"] == phase_7b["product_id"]
        assert phase_7a["actual_demand_units"] == phase_7b["actual_demand_units"]
        assert phase_7a["baseline_prediction_units"] == (
            phase_7b["baseline_prediction_units"]
        )
        assert phase_7a["candidate_prediction_units"] == (
            phase_7b["candidate_prediction_units"]
        )


def test_trained_model_cycle_totals_match_the_expanding_weekday_mean_candidate(
    ml_records,
):
    for record in ml_records:
        assert record["model_prediction_units"] == pytest.approx(
            record["candidate_prediction_units"],
            rel=1e-9,
        )


def test_ml_summary_reports_three_methods_overall_and_by_product(
    configurations,
    ml_records,
):
    summary = summarize_ml_forecasts(ml_records, configurations[0])

    assert summary["overall"]["forecast_count"] == 27
    assert set(summary["by_product"]) == APPROVED_PRODUCT_IDS
    for method_name in ("baseline", "candidate", "model"):
        assert f"{method_name}_mae_units" in summary["overall"]
        assert f"{method_name}_wape_percent" in summary["overall"]
    for product_summary in summary["by_product"].values():
        assert product_summary["forecast_count"] == 3
        assert product_summary["model_vs_baseline_result"] in {"win", "tie", "loss"}
        assert product_summary["model_vs_candidate_result"] in {"win", "tie", "loss"}


def test_ml_summary_mae_matches_the_manual_formula(configurations, ml_records):
    summary = summarize_ml_forecasts(ml_records, configurations[0])
    expected = sum(
        abs(record["actual_demand_units"] - record["model_prediction_units"])
        for record in ml_records
    ) / len(ml_records)

    assert summary["overall"]["model_mae_units"] == pytest.approx(expected, rel=1e-12)


def test_ml_summary_wape_matches_the_manual_formula(configurations, ml_records):
    summary = summarize_ml_forecasts(ml_records, configurations[0])
    total_error = sum(
        abs(record["actual_demand_units"] - record["model_prediction_units"])
        for record in ml_records
    )
    total_actual = sum(record["actual_demand_units"] for record in ml_records)

    assert total_actual == 1443
    assert summary["overall"]["model_wape_percent"] == pytest.approx(
        100.0 * total_error / total_actual,
        rel=1e-12,
    )


def test_ml_summary_result_counts_total_the_product_scope(configurations, ml_records):
    summary = summarize_ml_forecasts(ml_records, configurations[0])

    assert sum(summary["model_vs_baseline_result_counts"].values()) == PRODUCT_COUNT
    assert sum(summary["model_vs_candidate_result_counts"].values()) == PRODUCT_COUNT
    assert set(summary["model_vs_baseline_result_counts"]) == {
        "wins",
        "ties",
        "losses",
    }


def test_ml_predictions_are_not_rounded_before_evaluation(ml_records):
    assert any(
        record["model_prediction_units"] != float(
            round(record["model_prediction_units"])
        )
        for record in ml_records
    )


def test_ml_summary_rejects_unknown_product_identifiers(configurations, ml_records):
    invalid = deepcopy(ml_records)
    invalid[0]["product_id"] = "Donut_Product"

    with pytest.raises(ValueError, match="Unknown product ID"):
        summarize_ml_forecasts(invalid, configurations[0])


def test_ml_summary_rejects_negative_model_absolute_error(configurations, ml_records):
    invalid = deepcopy(ml_records)
    invalid[0]["model_absolute_error_units"] = -1.0

    with pytest.raises(
        ValueError,
        match="model_absolute_error_units cannot be negative",
    ):
        summarize_ml_forecasts(invalid, configurations[0])


# --- Validator --------------------------------------------------------------


def test_ml_validator_rejects_an_invalid_column_order(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(ml_records)
    invalid[0] = {"product_id": invalid[0]["product_id"], **invalid[0]}

    with pytest.raises(ValueError, match="exact column order"):
        validate_ml_forecast_records(invalid, demand_records, products, delivery)


def test_ml_validator_rejects_a_future_training_end_date(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(ml_records)
    invalid[0]["training_end_date"] = invalid[0]["forecast_origin_date"]

    with pytest.raises(ValueError, match="training_end_date"):
        validate_ml_forecast_records(invalid, demand_records, products, delivery)


def test_ml_validator_rejects_an_incorrect_training_row_count(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(ml_records)
    invalid[0]["training_row_count"] = 127

    with pytest.raises(ValueError, match="training_row_count"):
        validate_ml_forecast_records(invalid, demand_records, products, delivery)


def test_ml_validator_rejects_a_negative_model_prediction(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(ml_records)
    invalid[0]["model_prediction_units"] = -1.0

    with pytest.raises(
        ValueError,
        match="model_prediction_units cannot be negative",
    ):
        validate_ml_forecast_records(invalid, demand_records, products, delivery)


def test_ml_validator_rejects_an_integer_model_prediction(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(ml_records)
    invalid[0]["model_prediction_units"] = 58

    with pytest.raises(ValueError, match="model_prediction_units must be a float"):
        validate_ml_forecast_records(invalid, demand_records, products, delivery)


def test_ml_validator_rejects_an_inconsistent_model_error(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations
    invalid = deepcopy(ml_records)
    invalid[0]["model_absolute_error_units"] += 1.0

    with pytest.raises(ValueError, match="model_absolute_error_units is invalid"):
        validate_ml_forecast_records(invalid, demand_records, products, delivery)


def test_ml_validator_rejects_an_unexpected_record_count(
    configurations,
    demand_records,
    ml_records,
):
    products, delivery, _ = configurations

    with pytest.raises(ValueError, match="Expected 27"):
        validate_ml_forecast_records(
            ml_records[:-1],
            demand_records,
            products,
            delivery,
        )


# --- Reproducibility and regression -----------------------------------------


def test_repeated_ml_training_produces_identical_predictions(
    configurations,
    demand_records,
):
    products, delivery, _ = configurations

    first = generate_ml_cycle_forecast_records(demand_records, products, delivery)
    second = generate_ml_cycle_forecast_records(demand_records, products, delivery)

    assert first == second


def test_repeated_model_fitting_produces_identical_coefficients(demand_records):
    training_rows = build_training_rows(demand_records, SECOND_ORIGIN)

    first = fit_demand_model(training_rows).named_steps["regressor"]
    second = fit_demand_model(training_rows).named_steps["regressor"]

    assert list(first.coef_) == list(second.coef_)
    assert float(first.intercept_) == float(second.intercept_)


def test_ml_pipeline_matches_recorded_reproducibility_anchors(
    configurations,
    ml_records,
):
    first = ml_records[0]

    assert first["forecast_origin_date"] == "2025-01-21"
    assert first["product_id"] == "Milk_Product_A"
    assert first["training_row_count"] == 126
    assert first["actual_demand_units"] == 57
    assert first["baseline_prediction_units"] == 58
    assert first["candidate_prediction_units"] == 58.0
    assert first["model_prediction_units"] == pytest.approx(58.0, rel=1e-9)

    summary = summarize_ml_forecasts(ml_records, configurations[0])
    assert summary["overall"]["baseline_mae_units"] == pytest.approx(
        3.4074074074074074,
        rel=1e-9,
    )
    assert summary["overall"]["candidate_mae_units"] == pytest.approx(
        3.462962962962963,
        rel=1e-9,
    )
    assert summary["overall"]["model_mae_units"] == pytest.approx(
        3.462962962962963,
        rel=1e-9,
    )
    assert summary["overall"]["model_wape_percent"] == pytest.approx(
        6.4795564795564795,
        rel=1e-9,
    )
    assert summary["model_vs_baseline_result_counts"] == {
        "wins": 5,
        "ties": 0,
        "losses": 4,
    }
    assert summary["model_vs_candidate_result_counts"] == {
        "wins": 0,
        "ties": 9,
        "losses": 0,
    }


def test_phase_7a_forecast_records_and_summary_remain_unchanged(
    configurations,
    demand_records,
):
    products, delivery, _ = configurations
    records = generate_cycle_forecast_records(demand_records, products, delivery)
    summary = summarize_forecasts(records, products)

    assert len(records) == 27
    assert records[0]["candidate_prediction_units"] == 58.0
    assert summary["overall"]["baseline_mae_units"] == pytest.approx(
        3.4074074074074074
    )
    assert summary["overall"]["candidate_mae_units"] == pytest.approx(
        3.462962962962963
    )
    assert summary["candidate_product_result_counts"] == {
        "wins": 5,
        "ties": 0,
        "losses": 4,
    }


# --- Privacy ----------------------------------------------------------------


def test_ml_records_contain_only_approved_public_product_aliases(ml_records):
    assert {record["product_id"] for record in ml_records} == APPROVED_PRODUCT_IDS


def test_ml_records_contain_no_identifying_or_operational_fields(ml_records):
    forbidden_fragments = (
        "employee",
        "manager",
        "customer",
        "vendor",
        "store",
        "company",
        "address",
        "location",
        "invoice",
        "token",
        "password",
    )
    for record in ml_records:
        for field_name in record:
            assert not any(
                fragment in field_name.lower() for fragment in forbidden_fragments
            )
