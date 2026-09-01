"""Generate deterministic synthetic daily demand records."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
import random
import sys
from typing import Any

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_products_config,
    validate_delivery_config,
    validate_generation_config,
    validate_products_config,
)

RECORD_COLUMNS = (
    "date",
    "weekday",
    "product_id",
    "is_high_demand_day",
    "demand_units",
    "delivery_event",
)


def generate_daily_records(
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    generation_config: dict[str, object],
    seed: int | None = None,
) -> list[dict[str, object]]:
    """Generate validated records in stable date and product order."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_generation_config(generation_config)

    generation = _mapping(generation_config["generation"], "generation")
    delivery = _mapping(delivery_config["delivery"], "delivery")
    products = _product_list(products_config["products"])
    seed_used = generation["default_seed"] if seed is None else seed
    if isinstance(seed_used, bool) or not isinstance(seed_used, int):
        raise ValueError("seed must be an integer.")

    start_date = date.fromisoformat(_string(generation["start_date"], "start_date"))
    duration_days = _integer(generation["duration_days"], "duration_days")
    cycle_length = _integer(delivery["cycle_length_days"], "cycle_length_days")
    demand_ranges = _mapping(generation["demand_ranges"], "demand_ranges")
    adjustment = _integer(
        generation["high_demand_day_adjustment"],
        "high_demand_day_adjustment",
    )
    random_generator = random.Random(seed_used)
    records: list[dict[str, object]] = []

    for day_offset in range(duration_days):
        current_date = start_date + timedelta(days=day_offset)
        weekday = current_date.strftime("%A")
        delivery_event = day_offset % cycle_length == 0

        for product in products:
            product_id = _string(product["product_id"], "product_id")
            demand_level = _string(product["demand_level"], "demand_level")
            if demand_level not in {"low", "high"}:
                raise ValueError(
                    f"Unsupported demand level for {product_id}: {demand_level}."
                )

            demand_range = _mapping(demand_ranges[demand_level], demand_level)
            minimum = _integer(demand_range["minimum"], "minimum")
            maximum = _integer(demand_range["maximum"], "maximum")
            high_demand_days = product["high_demand_days"]
            if not isinstance(high_demand_days, list):
                raise ValueError(f"High-demand days must be a list for {product_id}.")
            is_high_demand_day = weekday in high_demand_days
            base_demand = random_generator.randint(minimum, maximum)
            demand_units = (
                base_demand + adjustment
                if is_high_demand_day
                else base_demand
            )

            records.append(
                {
                    "date": current_date.isoformat(),
                    "weekday": weekday,
                    "product_id": product_id,
                    "is_high_demand_day": is_high_demand_day,
                    "demand_units": demand_units,
                    "delivery_event": delivery_event,
                }
            )

    validate_generated_records(
        records,
        products_config,
        delivery_config,
        generation_config,
    )
    return records


def validate_generated_records(
    records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    generation_config: dict[str, object],
) -> None:
    """Validate the complete Phase 3 daily demand record set."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_generation_config(generation_config)

    products = _product_list(products_config["products"])
    delivery = _mapping(delivery_config["delivery"], "delivery")
    generation = _mapping(generation_config["generation"], "generation")
    start_date = date.fromisoformat(_string(generation["start_date"], "start_date"))
    duration_days = _integer(generation["duration_days"], "duration_days")
    cycle_length = _integer(delivery["cycle_length_days"], "cycle_length_days")
    delivery_weekday = _string(delivery["delivery_weekday"], "delivery_weekday")
    adjustment = _integer(
        generation["high_demand_day_adjustment"],
        "high_demand_day_adjustment",
    )
    demand_ranges = _mapping(generation["demand_ranges"], "demand_ranges")
    expected_count = duration_days * len(products)
    if len(records) != expected_count:
        raise ValueError(f"Expected {expected_count} records, received {len(records)}.")

    configured_ids = [
        _string(product["product_id"], "product_id") for product in products
    ]
    if set(configured_ids) != APPROVED_PRODUCT_IDS:
        raise ValueError("Records must use exactly the approved product aliases.")

    for day_offset in range(duration_days):
        expected_date = start_date + timedelta(days=day_offset)
        expected_weekday = expected_date.strftime("%A")
        expected_delivery_event = day_offset % cycle_length == 0

        for product_index, product in enumerate(products):
            record_index = day_offset * len(products) + product_index
            record = records[record_index]
            if list(record) != list(RECORD_COLUMNS):
                raise ValueError("Generated records must use the exact column order.")

            product_id = _string(product["product_id"], "product_id")
            if record["date"] != expected_date.isoformat():
                raise ValueError("Generated dates must be continuous and ascending.")
            if record["weekday"] != expected_weekday:
                raise ValueError("Record weekday does not match its date.")
            if record["product_id"] != product_id:
                raise ValueError(
                    "Generated product order does not match configuration order."
                )
            if product_id not in APPROVED_PRODUCT_IDS or "donut" in product_id.lower():
                raise ValueError(f"Unapproved product identifier: {product_id}.")

            high_demand_days = product["high_demand_days"]
            if not isinstance(high_demand_days, list):
                raise ValueError(f"High-demand days must be a list for {product_id}.")
            expected_high_demand_day = expected_weekday in high_demand_days
            if type(record["is_high_demand_day"]) is not bool:
                raise ValueError("is_high_demand_day must be a Boolean.")
            if record["is_high_demand_day"] is not expected_high_demand_day:
                raise ValueError(
                    "High-demand-day flag does not match product configuration."
                )

            demand_units = record["demand_units"]
            if type(demand_units) is not int:
                raise ValueError("demand_units must be an integer.")
            if demand_units < 0:
                raise ValueError("demand_units cannot be negative.")
            demand_level = _string(product["demand_level"], "demand_level")
            if demand_level not in {"low", "high"}:
                raise ValueError(
                    f"Unsupported demand level for {product_id}: {demand_level}."
                )
            demand_range = _mapping(demand_ranges[demand_level], demand_level)
            minimum = _integer(demand_range["minimum"], "minimum")
            maximum = _integer(demand_range["maximum"], "maximum")
            expected_adjustment = adjustment if expected_high_demand_day else 0
            lower_bound = minimum + expected_adjustment
            upper_bound = maximum + expected_adjustment
            if not lower_bound <= demand_units <= upper_bound:
                raise ValueError(f"demand_units is outside its range for {product_id}.")

            if type(record["delivery_event"]) is not bool:
                raise ValueError("delivery_event must be a Boolean.")
            if record["delivery_event"] is not expected_delivery_event:
                raise ValueError("Delivery event does not match the configured cycle.")
            if expected_delivery_event and expected_weekday != delivery_weekday:
                raise ValueError(
                    "Delivery events must occur on the configured weekday."
                )


def write_records_csv(
    records: list[dict[str, object]],
    output_path: Path,
) -> None:
    """Write records as deterministic UTF-8 CSV with lowercase Booleans."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=RECORD_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            if list(record) != list(RECORD_COLUMNS):
                raise ValueError("CSV records must use the exact column order.")
            writer.writerow(
                {
                    column: _csv_value(record[column])
                    for column in RECORD_COLUMNS
                }
            )


def main(argv: list[str] | None = None) -> int:
    """Run the synthetic demand generator command-line interface."""
    parser = _build_argument_parser()
    arguments = parser.parse_args(argv)

    try:
        products_config = load_products_config(arguments.products_config)
        delivery_config = load_delivery_config(arguments.delivery_config)
        generation_config = load_generation_config(arguments.generation_config)
        generation = _mapping(generation_config["generation"], "generation")
        seed_used = (
            generation["default_seed"]
            if arguments.seed is None
            else arguments.seed
        )
        records = generate_daily_records(
            products_config,
            delivery_config,
            generation_config,
            seed=seed_used,
        )
        write_records_csv(records, arguments.output)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Generated {len(records)} records at {arguments.output} "
        f"with seed {seed_used}."
    )
    return 0


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic daily demand records."
    )
    parser.add_argument(
        "--products-config",
        type=Path,
        default=Path("config/products.yaml"),
    )
    parser.add_argument(
        "--delivery-config",
        type=Path,
        default=Path("config/delivery.yaml"),
    )
    parser.add_argument(
        "--generation-config",
        type=Path,
        default=Path("config/generation.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/generated/synthetic_daily_records.csv"),
    )
    parser.add_argument("--seed", type=int)
    return parser


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


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    return value


def _csv_value(value: object) -> object:
    if type(value) is bool:
        return "true" if value else "false"
    return value


if __name__ == "__main__":
    raise SystemExit(main())
