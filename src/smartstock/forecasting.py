"""Evaluate deterministic Phase 7A 14-day synthetic demand forecasts."""

from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any, Sequence

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    get_english_weekday,
    validate_delivery_config,
    validate_products_config,
)
from smartstock.inventory import validate_inventory_demand_records
from smartstock.ordering import calculate_baseline_cycle_demand

FORECAST_RECORD_COLUMNS = (
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
)

PREDICTION_COLUMNS = {
    "baseline_prediction_units",
    "candidate_prediction_units",
}

TIE_ABSOLUTE_TOLERANCE = 1e-9


def generate_cycle_forecast_records(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
) -> list[dict[str, object]]:
    """Create forecasts for every complete post-warm-up delivery cycle."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_demand_records(
        demand_records,
        products_config,
        delivery_config,
    )

    products = _product_list(products_config["products"])
    delivery = _mapping(delivery_config["delivery"], "delivery")
    cycle_length_days = _positive_integer(
        delivery["cycle_length_days"],
        "cycle_length_days",
    )
    first_date = _parse_iso_date(demand_records[0]["date"], "date")
    origins = _complete_forecast_origins(
        demand_records,
        len(products),
        cycle_length_days,
    )
    records: list[dict[str, object]] = []

    for forecast_origin in origins:
        training_end = forecast_origin - timedelta(days=1)
        target_end = forecast_origin + timedelta(days=cycle_length_days - 1)
        for product in products:
            product_id = _string(product["product_id"], "product_id")
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
                    "actual_demand_units": actual_demand_units,
                    "baseline_prediction_units": baseline_prediction_units,
                    "candidate_prediction_units": candidate_prediction_units,
                    "baseline_absolute_error_units": abs(
                        actual_demand_units - baseline_prediction_units
                    ),
                    "candidate_absolute_error_units": abs(
                        actual_demand_units - candidate_prediction_units
                    ),
                }
            )

    validate_forecast_records(
        records,
        demand_records,
        products_config,
        delivery_config,
    )
    return records


def forecast_cycle_with_expanding_weekday_mean(
    demand_records: list[dict[str, object]],
    product_id: str,
    forecast_origin_date: date,
    cycle_length_days: int,
) -> float | None:
    """Forecast one cycle from pre-origin product means by weekday."""
    if product_id not in APPROVED_PRODUCT_IDS:
        raise ValueError(f"Unknown product ID: {product_id}.")
    if not isinstance(forecast_origin_date, date):
        raise ValueError("forecast_origin_date must be a date.")
    _positive_integer(cycle_length_days, "cycle_length_days")
    if not isinstance(demand_records, list):
        raise ValueError("Demand records must be a list.")

    demand_sum_by_weekday: dict[str, int] = {}
    observation_count_by_weekday: dict[str, int] = {}
    for record in demand_records:
        if not isinstance(record, dict):
            raise ValueError("Each demand record must be a mapping.")
        if record.get("product_id") != product_id:
            continue
        record_date = _parse_iso_date(record.get("date"), "date")
        if record_date >= forecast_origin_date:
            continue
        demand_units = _nonnegative_integer(
            record.get("demand_units"),
            "demand_units",
        )
        weekday = get_english_weekday(record_date)
        demand_sum_by_weekday[weekday] = (
            demand_sum_by_weekday.get(weekday, 0) + demand_units
        )
        observation_count_by_weekday[weekday] = (
            observation_count_by_weekday.get(weekday, 0) + 1
        )

    forecast_units = 0.0
    for day_offset in range(cycle_length_days):
        target_date = forecast_origin_date + timedelta(days=day_offset)
        weekday = get_english_weekday(target_date)
        observation_count = observation_count_by_weekday.get(weekday, 0)
        if observation_count == 0:
            return None
        forecast_units += demand_sum_by_weekday[weekday] / observation_count

    return max(0.0, forecast_units)


def validate_forecast_records(
    records: list[dict[str, object]],
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
) -> None:
    """Validate forecast structure, chronology, formulas, and stable order."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_demand_records(
        demand_records,
        products_config,
        delivery_config,
    )
    if not isinstance(records, list):
        raise ValueError("Forecast records must be a list.")

    products = _product_list(products_config["products"])
    product_ids = [
        _string(product["product_id"], "product_id") for product in products
    ]
    delivery = _mapping(delivery_config["delivery"], "delivery")
    cycle_length_days = _positive_integer(
        delivery["cycle_length_days"],
        "cycle_length_days",
    )
    first_date = _parse_iso_date(demand_records[0]["date"], "date")
    origins = _complete_forecast_origins(
        demand_records,
        len(products),
        cycle_length_days,
    )
    expected_count = len(origins) * len(products)
    if len(records) != expected_count:
        raise ValueError(
            f"Expected {expected_count} forecast records, received {len(records)}."
        )

    for record_index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("Each forecast record must be a mapping.")
        if tuple(record) != FORECAST_RECORD_COLUMNS:
            raise ValueError("Forecast records must use the exact column order.")

        forecast_origin = origins[record_index // len(products)]
        product_id = product_ids[record_index % len(products)]
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
            parsed_value = _parse_iso_date(record[field_name], field_name)
            if parsed_value != expected_date:
                raise ValueError(f"{field_name} does not match forecast timing.")
        if record["product_id"] != product_id:
            raise ValueError("Forecast product order must match products.yaml.")

        actual_demand_units = _nonnegative_integer(
            record["actual_demand_units"],
            "actual_demand_units",
        )
        expected_actual = _sum_product_demand(
            demand_records,
            product_id,
            forecast_origin,
            target_end,
        )
        if actual_demand_units != expected_actual:
            raise ValueError("actual_demand_units does not match the target cycle.")

        baseline_prediction_units = _nonnegative_integer(
            record["baseline_prediction_units"],
            "baseline_prediction_units",
        )
        expected_baseline = calculate_baseline_cycle_demand(
            demand_records,
            product_id,
            forecast_origin,
            cycle_length_days,
        )
        if baseline_prediction_units != expected_baseline:
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

        baseline_error = _nonnegative_integer(
            record["baseline_absolute_error_units"],
            "baseline_absolute_error_units",
        )
        if baseline_error != abs(
            actual_demand_units - baseline_prediction_units
        ):
            raise ValueError("baseline_absolute_error_units is invalid.")

        candidate_error = _nonnegative_number(
            record["candidate_absolute_error_units"],
            "candidate_absolute_error_units",
            require_float=True,
        )
        expected_candidate_error = abs(
            actual_demand_units - candidate_prediction_units
        )
        if not math.isclose(
            candidate_error,
            expected_candidate_error,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("candidate_absolute_error_units is invalid.")


def calculate_mean_absolute_error(
    actual_values: Sequence[int | float],
    predicted_values: Sequence[int | float],
) -> float:
    """Return mean absolute error in demand units."""
    actual, predicted = _validated_metric_values(
        actual_values,
        predicted_values,
    )
    return sum(
        abs(actual_value - predicted_value)
        for actual_value, predicted_value in zip(actual, predicted, strict=True)
    ) / len(actual)


def calculate_weighted_absolute_percentage_error(
    actual_values: Sequence[int | float],
    predicted_values: Sequence[int | float],
) -> float | None:
    """Return WAPE as a percentage, or None when actual demand totals zero."""
    actual, predicted = _validated_metric_values(
        actual_values,
        predicted_values,
    )
    total_actual = sum(actual)
    if total_actual == 0:
        return None
    total_absolute_error = sum(
        abs(actual_value - predicted_value)
        for actual_value, predicted_value in zip(actual, predicted, strict=True)
    )
    return 100.0 * total_absolute_error / total_actual


def classify_metric_result(
    candidate_value: float,
    baseline_value: float,
) -> str:
    """Classify a lower-is-better candidate metric as a win, tie, or loss."""
    candidate = _nonnegative_number(candidate_value, "candidate_value")
    baseline = _nonnegative_number(baseline_value, "baseline_value")
    if math.isclose(
        candidate,
        baseline,
        rel_tol=0.0,
        abs_tol=TIE_ABSOLUTE_TOLERANCE,
    ):
        return "tie"
    return "win" if candidate < baseline else "loss"


def summarize_forecasts(
    records: list[dict[str, object]],
    products_config: dict[str, object],
) -> dict[str, object]:
    """Summarize baseline and candidate errors overall and by product."""
    validate_products_config(products_config)
    if not isinstance(records, list) or not records:
        raise ValueError("Forecast records must be a nonempty list.")
    products = _product_list(products_config["products"])
    product_ids = [
        _string(product["product_id"], "product_id") for product in products
    ]
    for record in records:
        _validate_summary_record(record)

    by_product: dict[str, dict[str, object]] = {}
    result_counts = {"wins": 0, "ties": 0, "losses": 0}
    for product_id in product_ids:
        product_records = [
            record for record in records if record["product_id"] == product_id
        ]
        if not product_records:
            raise ValueError(f"No forecast records found for {product_id}.")
        product_summary = _summarize_record_group(product_records)
        result = classify_metric_result(
            _number(product_summary["candidate_mae_units"], "candidate_mae_units"),
            _number(product_summary["baseline_mae_units"], "baseline_mae_units"),
        )
        product_summary["candidate_result"] = result
        result_count_key = {
            "win": "wins",
            "tie": "ties",
            "loss": "losses",
        }[result]
        result_counts[result_count_key] += 1
        by_product[product_id] = product_summary

    unknown_ids = {
        _string(record["product_id"], "product_id") for record in records
    } - set(product_ids)
    if unknown_ids:
        raise ValueError(f"Unknown forecast product IDs: {sorted(unknown_ids)}.")

    return {
        "overall": _summarize_record_group(records),
        "by_product": by_product,
        "candidate_product_result_counts": result_counts,
    }


def _summarize_record_group(
    records: list[dict[str, object]],
) -> dict[str, object]:
    actual_values = [
        _number(record["actual_demand_units"], "actual_demand_units")
        for record in records
    ]
    baseline_values = [
        _number(
            record["baseline_prediction_units"],
            "baseline_prediction_units",
        )
        for record in records
    ]
    candidate_values = [
        _number(
            record["candidate_prediction_units"],
            "candidate_prediction_units",
        )
        for record in records
    ]
    return {
        "forecast_count": len(records),
        "baseline_mae_units": calculate_mean_absolute_error(
            actual_values,
            baseline_values,
        ),
        "candidate_mae_units": calculate_mean_absolute_error(
            actual_values,
            candidate_values,
        ),
        "baseline_wape_percent": (
            calculate_weighted_absolute_percentage_error(
                actual_values,
                baseline_values,
            )
        ),
        "candidate_wape_percent": (
            calculate_weighted_absolute_percentage_error(
                actual_values,
                candidate_values,
            )
        ),
    }


def _complete_forecast_origins(
    demand_records: list[dict[str, object]],
    product_count: int,
    cycle_length_days: int,
) -> list[date]:
    duration_days = len(demand_records) // product_count
    origins: list[date] = []
    for day_offset in range(cycle_length_days, duration_days, cycle_length_days):
        if day_offset + cycle_length_days > duration_days:
            continue
        first_record = demand_records[day_offset * product_count]
        if first_record.get("delivery_event") is not True:
            raise ValueError("Forecast origins must be delivery events.")
        origins.append(_parse_iso_date(first_record.get("date"), "date"))
    return origins


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


def _validated_metric_values(
    actual_values: Sequence[int | float],
    predicted_values: Sequence[int | float],
) -> tuple[list[float], list[float]]:
    if isinstance(actual_values, (str, bytes)) or isinstance(
        predicted_values,
        (str, bytes),
    ):
        raise ValueError("Metric values must be numeric sequences.")
    actual = [
        _nonnegative_number(value, "actual value") for value in actual_values
    ]
    predicted = [
        _nonnegative_number(value, "predicted value")
        for value in predicted_values
    ]
    if not actual:
        raise ValueError("Metric values must be nonempty.")
    if len(actual) != len(predicted):
        raise ValueError("Actual and predicted values must have equal length.")
    return actual, predicted


def _validate_summary_record(record: object) -> None:
    if not isinstance(record, dict):
        raise ValueError("Each forecast record must be a mapping.")
    if tuple(record) != FORECAST_RECORD_COLUMNS:
        raise ValueError("Forecast records must use the exact column order.")
    product_id = _string(record["product_id"], "product_id")
    if product_id not in APPROVED_PRODUCT_IDS:
        raise ValueError(f"Unknown product ID: {product_id}.")
    _nonnegative_integer(
        record["actual_demand_units"],
        "actual_demand_units",
    )
    for field_name in (
        "baseline_prediction_units",
        "candidate_prediction_units",
        "baseline_absolute_error_units",
        "candidate_absolute_error_units",
    ):
        _nonnegative_number(record[field_name], field_name)


def _mapping(value: object, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a mapping.")
    return value


def _product_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("products must be a list of mappings.")
    return value


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
