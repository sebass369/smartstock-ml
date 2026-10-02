"""Evaluate a Phase 7B trained linear demand model on synthetic records."""

from __future__ import annotations

from datetime import date, timedelta
import math

from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    ENGLISH_WEEKDAYS,
    get_english_weekday,
    validate_delivery_config,
    validate_products_config,
)
from smartstock.forecasting import (
    calculate_mean_absolute_error,
    calculate_weighted_absolute_percentage_error,
    classify_metric_result,
    forecast_cycle_with_expanding_weekday_mean,
    list_complete_forecast_origins,
)
from smartstock.inventory import validate_inventory_demand_records
from smartstock.ordering import calculate_baseline_cycle_demand

ML_FORECAST_RECORD_COLUMNS = (
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

TRAINING_ROW_COLUMNS = ("product_id", "weekday", "demand_units")
FEATURE_COLUMNS = ("product_id", "weekday")
TARGET_COLUMN = "demand_units"

MODEL_PRODUCT_CATEGORIES = tuple(sorted(APPROVED_PRODUCT_IDS))
MODEL_WEEKDAY_CATEGORIES = tuple(ENGLISH_WEEKDAYS)
MINIMUM_PREDICTION_UNITS = 0.0


def build_demand_model() -> Pipeline:
    """Return the unfitted Phase 7B one-hot linear demand pipeline."""
    encoder = OneHotEncoder(
        categories=[
            list(MODEL_PRODUCT_CATEGORIES),
            list(MODEL_WEEKDAY_CATEGORIES),
        ],
        drop="first",
        handle_unknown="error",
        sparse_output=False,
        dtype=float,
    )
    features = ColumnTransformer(
        [("categorical", encoder, [0, 1])],
        remainder="drop",
    )
    return Pipeline(
        [
            ("features", features),
            ("regressor", LinearRegression(fit_intercept=True)),
        ]
    )


def build_training_rows(
    demand_records: list[dict[str, object]],
    forecast_origin_date: date,
) -> list[dict[str, object]]:
    """Select strictly pre-origin rows from the complete demand dataset."""
    if not isinstance(demand_records, list) or not demand_records:
        raise ValueError("Demand records must be a nonempty list.")
    if not isinstance(forecast_origin_date, date):
        raise ValueError("forecast_origin_date must be a date.")

    selected_dates: list[date] = []
    training_rows: list[dict[str, object]] = []
    for record in demand_records:
        if not isinstance(record, dict):
            raise ValueError("Each demand record must be a mapping.")
        record_date = _parse_iso_date(record.get("date"), "date")
        product_id = _string(record.get("product_id"), "product_id")
        if product_id not in APPROVED_PRODUCT_IDS:
            raise ValueError(f"Unknown product ID: {product_id}.")
        demand_units = _nonnegative_integer(
            record.get("demand_units"),
            "demand_units",
        )
        if record_date >= forecast_origin_date:
            continue
        selected_dates.append(record_date)
        training_rows.append(
            {
                "product_id": product_id,
                "weekday": get_english_weekday(record_date),
                TARGET_COLUMN: demand_units,
            }
        )

    if selected_dates and max(selected_dates) >= forecast_origin_date:
        raise ValueError("Training rows must be strictly before the forecast origin.")
    return training_rows


def build_target_feature_rows(
    forecast_origin_date: date,
    cycle_length_days: int,
    product_ids: list[str],
) -> list[dict[str, object]]:
    """Build calendar-only feature rows for the complete target cycle."""
    if not isinstance(forecast_origin_date, date):
        raise ValueError("forecast_origin_date must be a date.")
    _positive_integer(cycle_length_days, "cycle_length_days")
    if not isinstance(product_ids, list) or not product_ids:
        raise ValueError("product_ids must be a nonempty list.")

    feature_rows: list[dict[str, object]] = []
    for product_id in product_ids:
        checked_product_id = _string(product_id, "product_id")
        if checked_product_id not in APPROVED_PRODUCT_IDS:
            raise ValueError(f"Unknown product ID: {checked_product_id}.")
        for day_offset in range(cycle_length_days):
            target_date = forecast_origin_date + timedelta(days=day_offset)
            feature_rows.append(
                {
                    "product_id": checked_product_id,
                    "weekday": get_english_weekday(target_date),
                }
            )
    return feature_rows


def fit_demand_model(training_rows: list[dict[str, object]]) -> Pipeline:
    """Validate pre-origin rows and return a fitted demand pipeline."""
    _validate_training_rows(training_rows)
    model = build_demand_model()
    model.fit(
        _feature_table(training_rows),
        [float(row[TARGET_COLUMN]) for row in training_rows],
    )
    return model


def predict_daily_demand(
    model: Pipeline,
    feature_rows: list[dict[str, object]],
) -> list[float]:
    """Predict nonnegative daily demand for feature rows in input order."""
    if not isinstance(model, Pipeline):
        raise ValueError("model must be a fitted scikit-learn pipeline.")
    _validate_feature_rows(feature_rows)
    raw_predictions = model.predict(_feature_table(feature_rows))
    if len(raw_predictions) != len(feature_rows):
        raise ValueError("Predictions must match the feature row count.")

    predictions: list[float] = []
    for raw_prediction in raw_predictions:
        prediction = float(raw_prediction)
        if not math.isfinite(prediction):
            raise ValueError("Daily predictions must be finite.")
        predictions.append(max(MINIMUM_PREDICTION_UNITS, prediction))
    return predictions


def generate_ml_cycle_forecast_records(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
) -> list[dict[str, object]]:
    """Compare the trained model with both Phase 7A methods per cycle."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_demand_records(
        demand_records,
        products_config,
        delivery_config,
    )

    product_ids = _configured_product_ids(products_config)
    cycle_length_days = _cycle_length_days(delivery_config)
    first_date = _parse_iso_date(demand_records[0]["date"], "date")
    origins = list_complete_forecast_origins(
        demand_records,
        len(product_ids),
        cycle_length_days,
    )
    records: list[dict[str, object]] = []

    for forecast_origin in origins:
        training_end = forecast_origin - timedelta(days=1)
        target_end = forecast_origin + timedelta(days=cycle_length_days - 1)
        training_rows = build_training_rows(demand_records, forecast_origin)
        model = fit_demand_model(training_rows)
        feature_rows = build_target_feature_rows(
            forecast_origin,
            cycle_length_days,
            product_ids,
        )
        daily_predictions = predict_daily_demand(model, feature_rows)

        for product_index, product_id in enumerate(product_ids):
            cycle_start = product_index * cycle_length_days
            model_prediction_units = float(
                sum(daily_predictions[cycle_start : cycle_start + cycle_length_days])
            )
            actual_demand_units = _sum_product_demand(
                demand_records,
                product_id,
                forecast_origin,
                target_end,
            )
            baseline_prediction_units = calculate_baseline_cycle_demand(
                demand_records,
                product_id,
                forecast_origin,
                cycle_length_days,
            )
            candidate_prediction_units = (
                forecast_cycle_with_expanding_weekday_mean(
                    demand_records,
                    product_id,
                    forecast_origin,
                    cycle_length_days,
                )
            )
            if baseline_prediction_units is None:
                raise ValueError("A forecast requires one completed demand cycle.")
            if candidate_prediction_units is None:
                raise ValueError(
                    "A forecast requires historical demand for every target weekday."
                )

            records.append(
                {
                    "forecast_origin_date": forecast_origin.isoformat(),
                    "training_start_date": first_date.isoformat(),
                    "training_end_date": training_end.isoformat(),
                    "target_start_date": forecast_origin.isoformat(),
                    "target_end_date": target_end.isoformat(),
                    "product_id": product_id,
                    "training_row_count": len(training_rows),
                    "actual_demand_units": actual_demand_units,
                    "baseline_prediction_units": baseline_prediction_units,
                    "candidate_prediction_units": candidate_prediction_units,
                    "model_prediction_units": model_prediction_units,
                    "baseline_absolute_error_units": abs(
                        actual_demand_units - baseline_prediction_units
                    ),
                    "candidate_absolute_error_units": abs(
                        actual_demand_units - candidate_prediction_units
                    ),
                    "model_absolute_error_units": abs(
                        actual_demand_units - model_prediction_units
                    ),
                }
            )

    validate_ml_forecast_records(
        records,
        demand_records,
        products_config,
        delivery_config,
    )
    return records


def validate_ml_forecast_records(
    records: list[dict[str, object]],
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
) -> None:
    """Validate Phase 7B structure, chronology, formulas, and stable order."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_demand_records(
        demand_records,
        products_config,
        delivery_config,
    )
    if not isinstance(records, list):
        raise ValueError("Machine learning forecast records must be a list.")

    product_ids = _configured_product_ids(products_config)
    cycle_length_days = _cycle_length_days(delivery_config)
    first_date = _parse_iso_date(demand_records[0]["date"], "date")
    origins = list_complete_forecast_origins(
        demand_records,
        len(product_ids),
        cycle_length_days,
    )
    expected_count = len(origins) * len(product_ids)
    if len(records) != expected_count:
        raise ValueError(
            f"Expected {expected_count} machine learning forecast records, "
            f"received {len(records)}."
        )

    for record_index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("Each forecast record must be a mapping.")
        if tuple(record) != ML_FORECAST_RECORD_COLUMNS:
            raise ValueError(
                "Machine learning forecast records must use the exact column order."
            )

        forecast_origin = origins[record_index // len(product_ids)]
        product_id = product_ids[record_index % len(product_ids)]
        training_end = forecast_origin - timedelta(days=1)
        target_end = forecast_origin + timedelta(days=cycle_length_days - 1)
        expected_dates = {
            "forecast_origin_date": forecast_origin,
            "training_start_date": first_date,
            "training_end_date": training_end,
            "target_start_date": forecast_origin,
            "target_end_date": target_end,
        }
        for field_name, expected_date in expected_dates.items():
            if _parse_iso_date(record[field_name], field_name) != expected_date:
                raise ValueError(f"{field_name} does not match forecast timing.")
        if record["product_id"] != product_id:
            raise ValueError("Forecast product order must match products.yaml.")

        expected_training_rows = len(product_ids) * (
            forecast_origin - first_date
        ).days
        training_row_count = _nonnegative_integer(
            record["training_row_count"],
            "training_row_count",
        )
        if training_row_count != expected_training_rows:
            raise ValueError(
                "training_row_count does not match the pre-origin history."
            )

        actual_demand_units = _nonnegative_integer(
            record["actual_demand_units"],
            "actual_demand_units",
        )
        if actual_demand_units != _sum_product_demand(
            demand_records,
            product_id,
            forecast_origin,
            target_end,
        ):
            raise ValueError("actual_demand_units does not match the target cycle.")

        baseline_prediction_units = _nonnegative_integer(
            record["baseline_prediction_units"],
            "baseline_prediction_units",
        )
        if baseline_prediction_units != calculate_baseline_cycle_demand(
            demand_records,
            product_id,
            forecast_origin,
            cycle_length_days,
        ):
            raise ValueError(
                "baseline_prediction_units does not match completed demand."
            )

        candidate_prediction_units = _nonnegative_number(
            record["candidate_prediction_units"],
            "candidate_prediction_units",
            require_float=True,
        )
        expected_candidate = forecast_cycle_with_expanding_weekday_mean(
            demand_records,
            product_id,
            forecast_origin,
            cycle_length_days,
        )
        if expected_candidate is None or not math.isclose(
            candidate_prediction_units,
            expected_candidate,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "candidate_prediction_units does not match the weekday mean."
            )

        model_prediction_units = _nonnegative_number(
            record["model_prediction_units"],
            "model_prediction_units",
            require_float=True,
        )

        baseline_error = _nonnegative_integer(
            record["baseline_absolute_error_units"],
            "baseline_absolute_error_units",
        )
        if baseline_error != abs(actual_demand_units - baseline_prediction_units):
            raise ValueError("baseline_absolute_error_units is invalid.")

        for error_field, prediction_value in (
            ("candidate_absolute_error_units", candidate_prediction_units),
            ("model_absolute_error_units", model_prediction_units),
        ):
            error_value = _nonnegative_number(
                record[error_field],
                error_field,
                require_float=True,
            )
            if not math.isclose(
                error_value,
                abs(actual_demand_units - prediction_value),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(f"{error_field} is invalid.")


def summarize_ml_forecasts(
    records: list[dict[str, object]],
    products_config: dict[str, object],
) -> dict[str, object]:
    """Summarize baseline, candidate, and model errors overall and by product."""
    validate_products_config(products_config)
    if not isinstance(records, list) or not records:
        raise ValueError("Forecast records must be a nonempty list.")
    product_ids = _configured_product_ids(products_config)
    for record in records:
        _validate_summary_record(record)

    unknown_ids = {
        _string(record["product_id"], "product_id") for record in records
    } - set(product_ids)
    if unknown_ids:
        raise ValueError(f"Unknown forecast product IDs: {sorted(unknown_ids)}.")

    by_product: dict[str, dict[str, object]] = {}
    model_vs_baseline_counts = {"wins": 0, "ties": 0, "losses": 0}
    model_vs_candidate_counts = {"wins": 0, "ties": 0, "losses": 0}
    comparisons = (
        (
            "baseline_mae_units",
            "model_vs_baseline_result",
            model_vs_baseline_counts,
        ),
        (
            "candidate_mae_units",
            "model_vs_candidate_result",
            model_vs_candidate_counts,
        ),
    )
    for product_id in product_ids:
        product_records = [
            record for record in records if record["product_id"] == product_id
        ]
        if not product_records:
            raise ValueError(f"No forecast records found for {product_id}.")
        product_summary = _summarize_record_group(product_records)
        model_mae = _number(product_summary["model_mae_units"], "model_mae_units")
        for reference_key, result_key, counts in comparisons:
            result = classify_metric_result(
                model_mae,
                _number(product_summary[reference_key], reference_key),
            )
            product_summary[result_key] = result
            counts[{"win": "wins", "tie": "ties", "loss": "losses"}[result]] += 1
        by_product[product_id] = product_summary

    return {
        "overall": _summarize_record_group(records),
        "by_product": by_product,
        "model_vs_baseline_result_counts": model_vs_baseline_counts,
        "model_vs_candidate_result_counts": model_vs_candidate_counts,
    }


def _summarize_record_group(
    records: list[dict[str, object]],
) -> dict[str, object]:
    actual_values = [
        _number(record["actual_demand_units"], "actual_demand_units")
        for record in records
    ]
    summary: dict[str, object] = {"forecast_count": len(records)}
    for method_name, column in (
        ("baseline", "baseline_prediction_units"),
        ("candidate", "candidate_prediction_units"),
        ("model", "model_prediction_units"),
    ):
        predicted_values = [_number(record[column], column) for record in records]
        summary[f"{method_name}_mae_units"] = calculate_mean_absolute_error(
            actual_values,
            predicted_values,
        )
        summary[f"{method_name}_wape_percent"] = (
            calculate_weighted_absolute_percentage_error(
                actual_values,
                predicted_values,
            )
        )
    return summary


def _validate_summary_record(record: object) -> None:
    if not isinstance(record, dict):
        raise ValueError("Each forecast record must be a mapping.")
    if tuple(record) != ML_FORECAST_RECORD_COLUMNS:
        raise ValueError(
            "Machine learning forecast records must use the exact column order."
        )
    product_id = _string(record["product_id"], "product_id")
    if product_id not in APPROVED_PRODUCT_IDS:
        raise ValueError(f"Unknown product ID: {product_id}.")
    _nonnegative_integer(record["training_row_count"], "training_row_count")
    _nonnegative_integer(record["actual_demand_units"], "actual_demand_units")
    for field_name in (
        "baseline_prediction_units",
        "candidate_prediction_units",
        "model_prediction_units",
        "baseline_absolute_error_units",
        "candidate_absolute_error_units",
        "model_absolute_error_units",
    ):
        _nonnegative_number(record[field_name], field_name)


def _validate_training_rows(training_rows: object) -> None:
    if not isinstance(training_rows, list) or not training_rows:
        raise ValueError("Training rows must be a nonempty list.")
    observed_products: set[str] = set()
    observed_weekdays: set[str] = set()
    for row in training_rows:
        if not isinstance(row, dict):
            raise ValueError("Each training row must be a mapping.")
        if tuple(row) != TRAINING_ROW_COLUMNS:
            raise ValueError("Training rows must use the exact column order.")
        observed_products.add(_checked_product_id(row["product_id"]))
        observed_weekdays.add(_checked_weekday(row["weekday"]))
        _nonnegative_integer(row[TARGET_COLUMN], TARGET_COLUMN)

    if observed_products != APPROVED_PRODUCT_IDS:
        raise ValueError("Training rows require every approved product alias.")
    if observed_weekdays != set(MODEL_WEEKDAY_CATEGORIES):
        raise ValueError("Training rows require every English weekday.")


def _validate_feature_rows(feature_rows: object) -> None:
    if not isinstance(feature_rows, list) or not feature_rows:
        raise ValueError("Feature rows must be a nonempty list.")
    for row in feature_rows:
        if not isinstance(row, dict):
            raise ValueError("Each feature row must be a mapping.")
        if tuple(row) != FEATURE_COLUMNS:
            raise ValueError("Feature rows must use the exact column order.")
        _checked_product_id(row["product_id"])
        _checked_weekday(row["weekday"])


def _feature_table(rows: list[dict[str, object]]) -> list[list[object]]:
    return [[row[column] for column in FEATURE_COLUMNS] for row in rows]


def _checked_product_id(value: object) -> str:
    product_id = _string(value, "product_id")
    if product_id not in APPROVED_PRODUCT_IDS:
        raise ValueError(f"Unknown product ID: {product_id}.")
    return product_id


def _checked_weekday(value: object) -> str:
    weekday = _string(value, "weekday")
    if weekday not in MODEL_WEEKDAY_CATEGORIES:
        raise ValueError(f"Unknown weekday: {weekday}.")
    return weekday


def _configured_product_ids(products_config: dict[str, object]) -> list[str]:
    products = products_config["products"]
    if not isinstance(products, list) or not all(
        isinstance(item, dict) for item in products
    ):
        raise ValueError("products must be a list of mappings.")
    return [_string(product["product_id"], "product_id") for product in products]


def _cycle_length_days(delivery_config: dict[str, object]) -> int:
    delivery = delivery_config["delivery"]
    if not isinstance(delivery, dict):
        raise ValueError("delivery must be a mapping.")
    return _positive_integer(delivery["cycle_length_days"], "cycle_length_days")


def _sum_product_demand(
    demand_records: list[dict[str, object]],
    product_id: str,
    start_date: date,
    end_date: date,
) -> int:
    matching_dates: list[date] = []
    demand_total = 0
    for record in demand_records:
        if record.get("product_id") != product_id:
            continue
        record_date = _parse_iso_date(record.get("date"), "date")
        if start_date <= record_date <= end_date:
            matching_dates.append(record_date)
            demand_total += _nonnegative_integer(
                record.get("demand_units"),
                "demand_units",
            )
    expected_dates = [
        start_date + timedelta(days=day_offset)
        for day_offset in range((end_date - start_date).days + 1)
    ]
    if matching_dates != expected_dates:
        raise ValueError("Demand totals require a complete chronological window.")
    return demand_total


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value


def _parse_iso_date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date string.")
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO date.") from exc
    if parsed_date.isoformat() != value:
        raise ValueError(f"{field_name} must use the ISO YYYY-MM-DD format.")
    return parsed_date


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric.")
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")
    return float(value)


def _nonnegative_number(
    value: object,
    field_name: str,
    require_float: bool = False,
) -> float:
    if require_float and type(value) is not float:
        raise ValueError(f"{field_name} must be a float.")
    numeric_value = _number(value, field_name)
    if numeric_value < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return numeric_value


def _nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    integer_value = _nonnegative_integer(value, field_name)
    if integer_value == 0:
        raise ValueError(f"{field_name} must be positive.")
    return integer_value
