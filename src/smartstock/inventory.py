"""Simulate deterministic inventory from approved synthetic demand records."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import sys
from typing import Any, Callable

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    get_english_weekday,
    load_delivery_config,
    load_generation_config,
    load_inventory_config,
    load_products_config,
    validate_delivery_config,
    validate_inventory_config,
    validate_products_config,
)
from smartstock.generator import RECORD_COLUMNS, generate_daily_records

INVENTORY_RECORD_COLUMNS = (
    *RECORD_COLUMNS,
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
)

INVENTORY_INTEGER_COLUMNS = (
    "starting_inventory_units",
    "delivered_units",
    "expired_units",
    "available_inventory_units",
    "fulfilled_demand_units",
    "units_used",
    "unmet_demand_units",
    "waste_units",
    "ending_inventory_units",
)


@dataclass
class _InventoryCohort:
    """Track the usable remainder and expiration date of one receipt."""

    received_date: date
    remaining_units: int
    expires_on: date


DeliveryUnitsResolver = Callable[[date, str, int, int, bool], int]


def simulate_inventory(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    inventory_config: dict[str, object],
) -> list[dict[str, object]]:
    """Apply fixed deliveries, expiration, and FIFO demand fulfillment."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_config(inventory_config, products_config)
    _validate_demand_records(demand_records, products_config, delivery_config)

    product_by_id = {
        _string(product["product_id"], "product_id"): product
        for product in _product_list(products_config["products"])
    }
    inventory_by_id = _inventory_by_id(inventory_config)

    def fixed_delivery_resolver(
        _delivery_date: date,
        product_id: str,
        _current_usable_inventory_units: int,
        _units_expiring_before_next_delivery: int,
        _is_first_delivery: bool,
    ) -> int:
        pack_size_units = _integer(
            product_by_id[product_id]["pack_size_units"],
            "pack_size_units",
        )
        delivery_pack_count = _integer(
            inventory_by_id[product_id]["delivery_pack_count"],
            "delivery_pack_count",
        )
        return delivery_pack_count * pack_size_units

    records = _simulate_inventory_with_delivery_resolver(
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
        fixed_delivery_resolver,
    )
    validate_inventory_records(
        records,
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
    )
    return records


def simulate_inventory_with_delivery_resolver(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    inventory_config: dict[str, object],
    delivery_units_resolver: DeliveryUnitsResolver,
) -> list[dict[str, object]]:
    """Simulate inventory with deterministic delivery decisions."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_config(inventory_config, products_config)
    _validate_demand_records(demand_records, products_config, delivery_config)
    if not callable(delivery_units_resolver):
        raise ValueError("delivery_units_resolver must be callable.")

    records = _simulate_inventory_with_delivery_resolver(
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
        delivery_units_resolver,
    )
    validate_inventory_scenario_records(
        records,
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
    )
    return records


def validate_inventory_demand_records(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
) -> None:
    """Validate demand records accepted by the shared inventory engine."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    _validate_demand_records(demand_records, products_config, delivery_config)


def _simulate_inventory_with_delivery_resolver(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    inventory_config: dict[str, object],
    delivery_units_resolver: DeliveryUnitsResolver,
) -> list[dict[str, object]]:
    """Run the shared FIFO engine for fixed or policy deliveries."""

    products = _product_list(products_config["products"])
    product_by_id = {
        _string(product["product_id"], "product_id"): product
        for product in products
    }
    inventory_by_id = _inventory_by_id(inventory_config)
    cohorts_by_id: dict[str, list[_InventoryCohort]] = {
        product_id: [] for product_id in product_by_id
    }
    product_count = len(products)
    delivery = _mapping(delivery_config["delivery"], "delivery")
    cycle_length_days = _integer(
        delivery["cycle_length_days"],
        "cycle_length_days",
    )
    records: list[dict[str, object]] = []

    for record_index, demand_record in enumerate(demand_records):
        product_id = _string(demand_record["product_id"], "product_id")
        current_date = date.fromisoformat(_string(demand_record["date"], "date"))
        product = product_by_id[product_id]
        inventory_entry = inventory_by_id[product_id]
        cohorts = cohorts_by_id[product_id]
        shelf_life_days = _integer(
            product["unopened_shelf_life_days"],
            "unopened_shelf_life_days",
        )

        if record_index < product_count:
            starting_units = _integer(
                inventory_entry["starting_inventory_units"],
                "starting_inventory_units",
            )
            if starting_units > 0:
                cohorts.append(
                    _create_cohort(current_date, starting_units, shelf_life_days)
                )

        starting_inventory_units = _cohort_total(cohorts)
        expired_units = _remove_expired_cohorts(cohorts, current_date)
        delivered_units = 0
        if demand_record["delivery_event"] is True:
            pack_size_units = _integer(
                product["pack_size_units"],
                "pack_size_units",
            )
            next_delivery_date = current_date + timedelta(days=cycle_length_days)
            units_expiring_before_next_delivery = sum(
                cohort.remaining_units
                for cohort in cohorts
                if current_date < cohort.expires_on < next_delivery_date
            )
            delivered_units = delivery_units_resolver(
                current_date,
                product_id,
                _cohort_total(cohorts),
                units_expiring_before_next_delivery,
                record_index < product_count,
            )
            if isinstance(delivered_units, bool) or not isinstance(
                delivered_units, int
            ):
                raise ValueError("Resolved delivered units must be an integer.")
            if delivered_units < 0:
                raise ValueError("Resolved delivered units cannot be negative.")
            if delivered_units % pack_size_units != 0:
                raise ValueError("Resolved delivered units must use full packs.")
            if delivered_units > 0:
                cohorts.append(
                    _create_cohort(
                        current_date,
                        delivered_units,
                        shelf_life_days,
                    )
                )

        available_inventory_units = _cohort_total(cohorts)
        demand_units = _integer(demand_record["demand_units"], "demand_units")
        units_used = _consume_fifo(cohorts, demand_units)
        fulfilled_demand_units = units_used
        unmet_demand_units = demand_units - fulfilled_demand_units
        ending_inventory_units = _cohort_total(cohorts)
        waste_units = expired_units
        stockout_event = (
            demand_units > available_inventory_units
            and unmet_demand_units > 0
        )

        records.append(
            {
                **demand_record,
                "starting_inventory_units": starting_inventory_units,
                "delivered_units": delivered_units,
                "expired_units": expired_units,
                "available_inventory_units": available_inventory_units,
                "fulfilled_demand_units": fulfilled_demand_units,
                "units_used": units_used,
                "unmet_demand_units": unmet_demand_units,
                "waste_units": waste_units,
                "ending_inventory_units": ending_inventory_units,
                "stockout_event": stockout_event,
            }
        )

    return records


def validate_inventory_records(
    records: list[dict[str, object]],
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    inventory_config: dict[str, object],
) -> None:
    """Validate Phase 4A record order, types, quantities, and balances."""
    _validate_inventory_records(
        records,
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
        require_fixed_deliveries=True,
    )


def validate_inventory_scenario_records(
    records: list[dict[str, object]],
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    inventory_config: dict[str, object],
) -> None:
    """Validate inventory balances for a deterministic delivery scenario."""
    _validate_inventory_records(
        records,
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
        require_fixed_deliveries=False,
    )


def _validate_inventory_records(
    records: list[dict[str, object]],
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    inventory_config: dict[str, object],
    require_fixed_deliveries: bool,
) -> None:
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_config(inventory_config, products_config)
    _validate_demand_records(demand_records, products_config, delivery_config)

    if len(records) != len(demand_records):
        raise ValueError(
            f"Expected {len(demand_records)} inventory records, "
            f"received {len(records)}."
        )

    products = _product_list(products_config["products"])
    product_by_id = {
        _string(product["product_id"], "product_id"): product
        for product in products
    }
    inventory_by_id = _inventory_by_id(inventory_config)
    prior_ending_by_id: dict[str, int] = {}
    product_count = len(products)

    for record_index, (record, demand_record) in enumerate(
        zip(records, demand_records, strict=True)
    ):
        if not isinstance(record, dict):
            raise ValueError("Each inventory record must be a mapping.")
        if tuple(record) != INVENTORY_RECORD_COLUMNS:
            raise ValueError("Inventory records must use the exact column order.")
        for column in RECORD_COLUMNS:
            if record[column] != demand_record[column]:
                raise ValueError(f"Inventory record must preserve {column}.")

        product_id = _string(record["product_id"], "product_id")
        product = product_by_id[product_id]
        inventory_entry = inventory_by_id[product_id]
        for column in INVENTORY_INTEGER_COLUMNS:
            _nonnegative_record_integer(record, column)
        if type(record["stockout_event"]) is not bool:
            raise ValueError("stockout_event must be a Boolean.")

        starting_inventory_units = _integer(
            record["starting_inventory_units"],
            "starting_inventory_units",
        )
        expected_starting = (
            _integer(
                inventory_entry["starting_inventory_units"],
                "starting_inventory_units",
            )
            if record_index < product_count
            else prior_ending_by_id[product_id]
        )
        if starting_inventory_units != expected_starting:
            raise ValueError(
                "starting_inventory_units must equal the configured first-day "
                "value or the prior ending inventory."
            )

        pack_size_units = _integer(product["pack_size_units"], "pack_size_units")
        delivery_pack_count = _integer(
            inventory_entry["delivery_pack_count"],
            "delivery_pack_count",
        )
        delivered_units = _integer(record["delivered_units"], "delivered_units")
        if require_fixed_deliveries:
            expected_delivery = (
                delivery_pack_count * pack_size_units
                if record["delivery_event"] is True
                else 0
            )
            if delivered_units != expected_delivery:
                raise ValueError(
                    "delivered_units must match the configured delivery quantity."
                )
        elif record["delivery_event"] is not True and delivered_units != 0:
            raise ValueError("Deliveries may occur only on delivery events.")
        if delivered_units % pack_size_units != 0:
            raise ValueError("delivered_units must be a full-pack multiple.")

        expired_units = _integer(record["expired_units"], "expired_units")
        if expired_units > starting_inventory_units:
            raise ValueError("expired_units cannot exceed starting_inventory_units.")
        available_inventory_units = _integer(
            record["available_inventory_units"],
            "available_inventory_units",
        )
        expected_available = (
            starting_inventory_units - expired_units + delivered_units
        )
        if available_inventory_units != expected_available:
            raise ValueError("available_inventory_units does not satisfy its formula.")

        demand_units = _integer(record["demand_units"], "demand_units")
        fulfilled_demand_units = _integer(
            record["fulfilled_demand_units"],
            "fulfilled_demand_units",
        )
        if fulfilled_demand_units != min(demand_units, available_inventory_units):
            raise ValueError("fulfilled_demand_units does not satisfy its formula.")
        units_used = _integer(record["units_used"], "units_used")
        if units_used != fulfilled_demand_units:
            raise ValueError("units_used must equal fulfilled_demand_units.")
        unmet_demand_units = _integer(
            record["unmet_demand_units"],
            "unmet_demand_units",
        )
        if demand_units != fulfilled_demand_units + unmet_demand_units:
            raise ValueError("Demand balance is not preserved.")
        waste_units = _integer(record["waste_units"], "waste_units")
        if waste_units != expired_units:
            raise ValueError("waste_units must equal expired_units.")

        ending_inventory_units = _integer(
            record["ending_inventory_units"],
            "ending_inventory_units",
        )
        expected_ending = (
            starting_inventory_units
            + delivered_units
            - expired_units
            - units_used
        )
        if ending_inventory_units != expected_ending:
            raise ValueError("Ending inventory balance is not preserved.")
        expected_stockout = (
            demand_units > available_inventory_units
            and unmet_demand_units > 0
        )
        if record["stockout_event"] is not expected_stockout:
            raise ValueError("stockout_event does not satisfy its condition.")
        prior_ending_by_id[product_id] = ending_inventory_units

    duration_days = len(records) // product_count
    minimum_shelf_life = min(
        _integer(product["unopened_shelf_life_days"], "unopened_shelf_life_days")
        for product in products
    )
    if duration_days <= minimum_shelf_life and any(
        record["expired_units"] != 0 or record["waste_units"] != 0
        for record in records
    ):
        raise ValueError(
            "Fresh inventory cannot expire within the configured duration."
        )


def write_inventory_csv(
    records: list[dict[str, object]],
    output_path: Path,
) -> None:
    """Write validated-shape Phase 4A records as deterministic UTF-8 CSV."""
    _validate_csv_record_shapes(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=INVENTORY_RECORD_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    column: _csv_value(record[column])
                    for column in INVENTORY_RECORD_COLUMNS
                }
            )


def main(argv: list[str] | None = None) -> int:
    """Run the deterministic Phase 4A inventory command-line interface."""
    parser = _build_argument_parser()
    arguments = parser.parse_args(argv)
    try:
        products_config = load_products_config(arguments.products_config)
        delivery_config = load_delivery_config(arguments.delivery_config)
        generation_config = load_generation_config(arguments.generation_config)
        inventory_config = load_inventory_config(
            arguments.inventory_config,
            products_config,
        )
        generation = _mapping(generation_config["generation"], "generation")
        seed_used = (
            generation["default_seed"]
            if arguments.seed is None
            else arguments.seed
        )
        demand_records = generate_daily_records(
            products_config,
            delivery_config,
            generation_config,
            seed=seed_used,
        )
        records = simulate_inventory(
            demand_records,
            products_config,
            delivery_config,
            inventory_config,
        )
        validate_inventory_records(
            records,
            demand_records,
            products_config,
            delivery_config,
            inventory_config,
        )
        write_inventory_csv(records, arguments.output)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Generated {len(records)} inventory records at {arguments.output} "
        f"with seed {seed_used}."
    )
    return 0


def _create_cohort(
    received_date: date,
    units: int,
    shelf_life_days: int,
) -> _InventoryCohort:
    return _InventoryCohort(
        received_date=received_date,
        remaining_units=units,
        expires_on=received_date + timedelta(days=shelf_life_days),
    )


def _remove_expired_cohorts(
    cohorts: list[_InventoryCohort],
    current_date: date,
) -> int:
    expired_units = 0
    usable_cohorts: list[_InventoryCohort] = []
    for cohort in cohorts:
        if current_date >= cohort.expires_on:
            expired_units += cohort.remaining_units
        else:
            usable_cohorts.append(cohort)
    cohorts[:] = usable_cohorts
    return expired_units


def _consume_fifo(cohorts: list[_InventoryCohort], demand_units: int) -> int:
    remaining_demand = demand_units
    for cohort in cohorts:
        consumed = min(remaining_demand, cohort.remaining_units)
        cohort.remaining_units -= consumed
        remaining_demand -= consumed
        if remaining_demand == 0:
            break
    cohorts[:] = [cohort for cohort in cohorts if cohort.remaining_units > 0]
    return demand_units - remaining_demand


def _cohort_total(cohorts: list[_InventoryCohort]) -> int:
    return sum(cohort.remaining_units for cohort in cohorts)


def _validate_demand_records(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
) -> None:
    if not isinstance(demand_records, list) or not demand_records:
        raise ValueError("Demand records must be a nonempty list.")
    products = _product_list(products_config["products"])
    product_ids = [
        _string(product["product_id"], "product_id") for product in products
    ]
    if set(product_ids) != APPROVED_PRODUCT_IDS:
        raise ValueError("Demand records require exactly the approved aliases.")
    product_count = len(products)
    if len(demand_records) % product_count != 0:
        raise ValueError("Demand records must contain every product for every date.")

    delivery = _mapping(delivery_config["delivery"], "delivery")
    cycle_length = _integer(delivery["cycle_length_days"], "cycle_length_days")
    delivery_weekday = _string(delivery["delivery_weekday"], "delivery_weekday")
    first_record = demand_records[0]
    if not isinstance(first_record, dict):
        raise ValueError("Each demand record must be a mapping.")
    first_date = _parse_iso_date(first_record.get("date"))

    for record_index, record in enumerate(demand_records):
        if not isinstance(record, dict):
            raise ValueError("Each demand record must be a mapping.")
        if tuple(record) != RECORD_COLUMNS:
            raise ValueError("Demand records must use the exact Phase 3 column order.")
        day_offset = record_index // product_count
        product_index = record_index % product_count
        expected_date = first_date + timedelta(days=day_offset)
        expected_weekday = get_english_weekday(expected_date)
        expected_product = products[product_index]
        expected_product_id = product_ids[product_index]
        expected_delivery_event = day_offset % cycle_length == 0

        if record["date"] != expected_date.isoformat():
            raise ValueError("Demand record dates must be continuous and ascending.")
        if record["weekday"] != expected_weekday:
            raise ValueError("Demand record weekday does not match its date.")
        if record["product_id"] != expected_product_id:
            raise ValueError(
                "Demand record product order must match product configuration."
            )
        if type(record["is_high_demand_day"]) is not bool:
            raise ValueError("is_high_demand_day must be a Boolean.")
        high_demand_days = expected_product["high_demand_days"]
        if not isinstance(high_demand_days, list):
            raise ValueError(
                f"High-demand days must be a list for {expected_product_id}."
            )
        if record["is_high_demand_day"] is not (
            expected_weekday in high_demand_days
        ):
            raise ValueError(
                "High-demand-day flag does not match product configuration."
            )
        _nonnegative_record_integer(record, "demand_units")
        if type(record["delivery_event"]) is not bool:
            raise ValueError("delivery_event must be a Boolean.")
        if record["delivery_event"] is not expected_delivery_event:
            raise ValueError("Delivery event does not match the configured cycle.")
        if expected_delivery_event and expected_weekday != delivery_weekday:
            raise ValueError("Delivery events must occur on the configured weekday.")


def _validate_csv_record_shapes(records: list[dict[str, object]]) -> None:
    if not isinstance(records, list):
        raise ValueError("Inventory CSV records must be a list.")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each inventory CSV record must be a mapping.")
        if tuple(record) != INVENTORY_RECORD_COLUMNS:
            raise ValueError("CSV records must use the exact column order.")
        for value in record.values():
            if not isinstance(value, (str, int, bool)):
                raise ValueError("CSV values must be strings, integers, or Booleans.")


def _inventory_by_id(
    inventory_config: dict[str, object],
) -> dict[str, dict[str, Any]]:
    inventory = _mapping(inventory_config["inventory"], "inventory")
    entries = _product_list(inventory["products"])
    return {
        _string(entry["product_id"], "product_id"): entry
        for entry in entries
    }


def _product_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("products must be a list of mappings.")
    return value


def _mapping(value: object, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a mapping.")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    return value


def _nonnegative_record_integer(
    record: dict[str, object],
    field_name: str,
) -> None:
    value = record[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")


def _parse_iso_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("date must be an ISO date string.")
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be a valid ISO date.") from exc
    if parsed_date.isoformat() != value:
        raise ValueError("date must use the ISO YYYY-MM-DD format.")
    return parsed_date


def _csv_value(value: object) -> object:
    if type(value) is bool:
        return "true" if value else "false"
    return value


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic inventory records."
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
        "--inventory-config",
        type=Path,
        default=Path("config/inventory.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/generated/synthetic_inventory_records.csv"),
    )
    parser.add_argument("--seed", type=int)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
