"""Generate deterministic baseline order recommendations and comparisons."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
import sys
from typing import Any

from smartstock.config import (
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_inventory_config,
    load_ordering_config,
    load_products_config,
    validate_delivery_config,
    validate_inventory_config,
    validate_ordering_config,
    validate_products_config,
)
from smartstock.generator import RECORD_COLUMNS, generate_daily_records
from smartstock.inventory import (
    simulate_inventory,
    simulate_inventory_with_delivery_resolver,
    validate_inventory_demand_records,
)

RECOMMENDATION_COLUMNS = (
    "recommendation_date",
    "delivery_date",
    "history_start_date",
    "history_end_date",
    "product_id",
    "baseline_demand_units",
    "safety_stock_units",
    "current_usable_inventory_units",
    "units_expiring_before_next_delivery",
    "usable_inventory_position_units",
    "net_order_units",
    "pack_size_units",
    "recommended_order_packs",
    "recommended_order_units",
)

RECOMMENDATION_INTEGER_COLUMNS = RECOMMENDATION_COLUMNS[5:]

SCENARIO_METRICS = (
    "total_fulfilled_demand_units",
    "total_unmet_demand_units",
    "stockout_event_count",
    "total_waste_units",
    "ending_inventory_units",
    "total_delivered_units",
    "total_delivered_packs",
)


def round_up_to_full_packs(
    required_units: int,
    pack_size_units: int,
) -> int:
    """Return the smallest full-pack count that covers required units."""
    _nonnegative_integer(required_units, "required_units")
    _positive_integer(pack_size_units, "pack_size_units")
    if required_units == 0:
        return 0
    return 1 + (required_units - 1) // pack_size_units


def calculate_baseline_cycle_demand(
    demand_records: list[dict[str, object]],
    product_id: str,
    delivery_date: date,
    cycle_length_days: int,
) -> int | None:
    """Sum one product's demand over the prior completed delivery cycle."""
    if product_id not in APPROVED_PRODUCT_IDS:
        raise ValueError(f"Unknown product ID: {product_id}.")
    if not isinstance(delivery_date, date):
        raise ValueError("delivery_date must be a date.")
    _positive_integer(cycle_length_days, "cycle_length_days")
    if not isinstance(demand_records, list):
        raise ValueError("Demand records must be a list.")

    history_start = delivery_date - timedelta(days=cycle_length_days)
    expected_dates = [
        history_start + timedelta(days=offset)
        for offset in range(cycle_length_days)
    ]
    matching_dates: list[date] = []
    baseline_cycle_demand_units = 0

    for record in demand_records:
        if not isinstance(record, dict):
            raise ValueError("Each demand record must be a mapping.")
        if record.get("product_id") != product_id:
            continue
        record_date = _parse_iso_date(record.get("date"))
        if history_start <= record_date < delivery_date:
            demand_units = record.get("demand_units")
            _nonnegative_integer(demand_units, "demand_units")
            matching_dates.append(record_date)
            baseline_cycle_demand_units += demand_units

    if matching_dates != expected_dates:
        return None
    return baseline_cycle_demand_units


def calculate_order_recommendation(
    delivery_date: date,
    product_id: str,
    baseline_cycle_demand_units: int,
    safety_stock_packs: int,
    current_usable_inventory_units: int,
    units_expiring_before_next_delivery: int,
    pack_size_units: int,
    cycle_length_days: int,
) -> dict[str, object]:
    """Calculate one transparent, full-pack order recommendation."""
    if not isinstance(delivery_date, date):
        raise ValueError("delivery_date must be a date.")
    if product_id not in APPROVED_PRODUCT_IDS:
        raise ValueError(f"Unknown product ID: {product_id}.")
    _nonnegative_integer(
        baseline_cycle_demand_units,
        "baseline_cycle_demand_units",
    )
    _nonnegative_integer(safety_stock_packs, "safety_stock_packs")
    _nonnegative_integer(
        current_usable_inventory_units,
        "current_usable_inventory_units",
    )
    _nonnegative_integer(
        units_expiring_before_next_delivery,
        "units_expiring_before_next_delivery",
    )
    _positive_integer(pack_size_units, "pack_size_units")
    _positive_integer(cycle_length_days, "cycle_length_days")
    if units_expiring_before_next_delivery > current_usable_inventory_units:
        raise ValueError(
            "units_expiring_before_next_delivery cannot exceed current inventory."
        )

    safety_stock_units = safety_stock_packs * pack_size_units
    target_inventory_units = baseline_cycle_demand_units + safety_stock_units
    usable_inventory_position_units = max(
        0,
        current_usable_inventory_units
        - units_expiring_before_next_delivery,
    )
    net_order_units = max(
        0,
        target_inventory_units - usable_inventory_position_units,
    )
    recommended_order_packs = round_up_to_full_packs(
        net_order_units,
        pack_size_units,
    )
    recommended_order_units = recommended_order_packs * pack_size_units
    history_start_date = delivery_date - timedelta(days=cycle_length_days)
    history_end_date = delivery_date - timedelta(days=1)

    return {
        "recommendation_date": delivery_date.isoformat(),
        "delivery_date": delivery_date.isoformat(),
        "history_start_date": history_start_date.isoformat(),
        "history_end_date": history_end_date.isoformat(),
        "product_id": product_id,
        "baseline_demand_units": baseline_cycle_demand_units,
        "safety_stock_units": safety_stock_units,
        "current_usable_inventory_units": current_usable_inventory_units,
        "units_expiring_before_next_delivery": (
            units_expiring_before_next_delivery
        ),
        "usable_inventory_position_units": usable_inventory_position_units,
        "net_order_units": net_order_units,
        "pack_size_units": pack_size_units,
        "recommended_order_packs": recommended_order_packs,
        "recommended_order_units": recommended_order_units,
    }


def simulate_policy_inventory(
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    inventory_config: dict[str, object],
    ordering_config: dict[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Simulate warm-up inventory followed by baseline-policy deliveries."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_inventory_config(inventory_config, products_config)
    validate_ordering_config(
        ordering_config,
        products_config,
        delivery_config,
    )
    products = _product_list(products_config["products"])
    product_by_id = {
        _string(product["product_id"], "product_id"): product
        for product in products
    }
    ordering = _mapping(ordering_config["ordering"], "ordering")
    ordering_by_id = {
        _string(entry["product_id"], "product_id"): entry
        for entry in _product_list(ordering["products"])
    }
    inventory = _mapping(inventory_config["inventory"], "inventory")
    inventory_by_id = {
        _string(entry["product_id"], "product_id"): entry
        for entry in _product_list(inventory["products"])
    }
    delivery = _mapping(delivery_config["delivery"], "delivery")
    cycle_length_days = _integer(
        delivery["cycle_length_days"],
        "cycle_length_days",
    )
    recommendations: list[dict[str, object]] = []

    def policy_delivery_resolver(
        current_date: date,
        product_id: str,
        current_usable_inventory_units: int,
        units_expiring_before_next_delivery: int,
        is_first_delivery: bool,
    ) -> int:
        product = product_by_id[product_id]
        pack_size_units = _integer(
            product["pack_size_units"],
            "pack_size_units",
        )
        if is_first_delivery:
            warm_up_pack_count = _integer(
                inventory_by_id[product_id]["delivery_pack_count"],
                "delivery_pack_count",
            )
            return warm_up_pack_count * pack_size_units

        baseline_cycle_demand_units = calculate_baseline_cycle_demand(
            demand_records,
            product_id,
            current_date,
            cycle_length_days,
        )
        if baseline_cycle_demand_units is None:
            return 0
        safety_stock_packs = _integer(
            ordering_by_id[product_id]["safety_stock_packs"],
            "safety_stock_packs",
        )
        recommendation = calculate_order_recommendation(
            current_date,
            product_id,
            baseline_cycle_demand_units,
            safety_stock_packs,
            current_usable_inventory_units,
            units_expiring_before_next_delivery,
            pack_size_units,
            cycle_length_days,
        )
        recommendations.append(recommendation)
        return _integer(
            recommendation["recommended_order_units"],
            "recommended_order_units",
        )

    policy_records = simulate_inventory_with_delivery_resolver(
        demand_records,
        products_config,
        delivery_config,
        inventory_config,
        policy_delivery_resolver,
    )
    validate_recommendation_records(
        recommendations,
        demand_records,
        products_config,
        delivery_config,
        ordering_config,
    )
    return policy_records, recommendations


def validate_recommendation_records(
    records: list[dict[str, object]],
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    ordering_config: dict[str, object],
) -> None:
    """Validate Phase 4B structure, timing, formulas, and ordering."""
    validate_products_config(products_config)
    validate_delivery_config(delivery_config)
    validate_ordering_config(
        ordering_config,
        products_config,
        delivery_config,
    )
    validate_inventory_demand_records(
        demand_records,
        products_config,
        delivery_config,
    )
    if not isinstance(records, list):
        raise ValueError("Recommendation records must be a list.")
    products = _product_list(products_config["products"])
    product_ids = [
        _string(product["product_id"], "product_id") for product in products
    ]
    product_by_id = {
        _string(product["product_id"], "product_id"): product
        for product in products
    }
    ordering = _mapping(ordering_config["ordering"], "ordering")
    ordering_by_id = {
        _string(entry["product_id"], "product_id"): entry
        for entry in _product_list(ordering["products"])
    }
    delivery = _mapping(delivery_config["delivery"], "delivery")
    cycle_length_days = _integer(
        delivery["cycle_length_days"],
        "cycle_length_days",
    )
    delivery_dates = _eligible_delivery_dates(
        demand_records,
        len(products),
        cycle_length_days,
    )
    expected_count = len(delivery_dates) * len(products)
    if len(records) != expected_count:
        raise ValueError(
            f"Expected {expected_count} recommendation records, "
            f"received {len(records)}."
        )

    for record_index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError("Each recommendation record must be a mapping.")
        if tuple(record) != RECOMMENDATION_COLUMNS:
            raise ValueError("Recommendation records must use the exact column order.")
        delivery_date = delivery_dates[record_index // len(products)]
        product_id = product_ids[record_index % len(products)]
        if record["recommendation_date"] != delivery_date.isoformat():
            raise ValueError("recommendation_date does not match its delivery date.")
        if record["delivery_date"] != delivery_date.isoformat():
            raise ValueError("delivery_date does not follow the configured cycle.")
        if record["history_start_date"] != (
            delivery_date - timedelta(days=cycle_length_days)
        ).isoformat():
            raise ValueError("history_start_date does not match the prior cycle.")
        if record["history_end_date"] != (
            delivery_date - timedelta(days=1)
        ).isoformat():
            raise ValueError("history_end_date must be the prior completed date.")
        if record["product_id"] != product_id:
            raise ValueError("Recommendation product order must match products.yaml.")
        for column in RECOMMENDATION_INTEGER_COLUMNS:
            _nonnegative_integer(record[column], column)

        pack_size_units = _integer(
            product_by_id[product_id]["pack_size_units"],
            "pack_size_units",
        )
        if record["pack_size_units"] != pack_size_units:
            raise ValueError("pack_size_units must match products.yaml.")
        baseline_cycle_demand_units = calculate_baseline_cycle_demand(
            demand_records,
            product_id,
            delivery_date,
            cycle_length_days,
        )
        if baseline_cycle_demand_units is None:
            raise ValueError("A recommendation requires one completed demand cycle.")
        if record["baseline_demand_units"] != baseline_cycle_demand_units:
            raise ValueError("baseline_demand_units does not match completed demand.")
        safety_stock_packs = _integer(
            ordering_by_id[product_id]["safety_stock_packs"],
            "safety_stock_packs",
        )
        expected_safety_stock_units = safety_stock_packs * pack_size_units
        if record["safety_stock_units"] != expected_safety_stock_units:
            raise ValueError("safety_stock_units does not match ordering.yaml.")
        current_inventory = _integer(
            record["current_usable_inventory_units"],
            "current_usable_inventory_units",
        )
        expiring_units = _integer(
            record["units_expiring_before_next_delivery"],
            "units_expiring_before_next_delivery",
        )
        if expiring_units > current_inventory:
            raise ValueError("Expiring units cannot exceed current inventory.")
        expected_position = max(0, current_inventory - expiring_units)
        if record["usable_inventory_position_units"] != expected_position:
            raise ValueError("usable_inventory_position_units is invalid.")
        target_units = baseline_cycle_demand_units + expected_safety_stock_units
        expected_net_order_units = max(0, target_units - expected_position)
        if record["net_order_units"] != expected_net_order_units:
            raise ValueError("net_order_units does not satisfy its formula.")
        expected_packs = round_up_to_full_packs(
            expected_net_order_units,
            pack_size_units,
        )
        if record["recommended_order_packs"] != expected_packs:
            raise ValueError("recommended_order_packs does not satisfy rounding.")
        recommended_units = _integer(
            record["recommended_order_units"],
            "recommended_order_units",
        )
        if recommended_units != expected_packs * pack_size_units:
            raise ValueError("recommended_order_units does not satisfy its formula.")
        if recommended_units % pack_size_units != 0:
            raise ValueError("Recommended units must use full packs.")
        if recommended_units < expected_net_order_units:
            raise ValueError("Recommended units must cover net order units.")
        if recommended_units - expected_net_order_units >= pack_size_units:
            raise ValueError("Full-pack rounding excess must be less than one pack.")


def write_recommendations_csv(
    records: list[dict[str, object]],
    output_path: Path,
    demand_records: list[dict[str, object]],
    products_config: dict[str, object],
    delivery_config: dict[str, object],
    ordering_config: dict[str, object],
) -> None:
    """Validate and write deterministic Phase 4B recommendations."""
    validate_recommendation_records(
        records,
        demand_records,
        products_config,
        delivery_config,
        ordering_config,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=RECOMMENDATION_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(records)


def summarize_scenario(
    records: list[dict[str, object]],
    products_config: dict[str, object],
    evaluation_start_date: date,
) -> dict[str, object]:
    """Summarize one inventory scenario from an inclusive start date."""
    validate_products_config(products_config)
    if not isinstance(evaluation_start_date, date):
        raise ValueError("evaluation_start_date must be a date.")
    products = _product_list(products_config["products"])
    product_ids = [
        _string(product["product_id"], "product_id") for product in products
    ]
    pack_size_by_id = {
        _string(product["product_id"], "product_id"): _integer(
            product["pack_size_units"],
            "pack_size_units",
        )
        for product in products
    }
    by_product: dict[str, dict[str, int]] = {}
    for product_id in product_ids:
        product_records = [
            record
            for record in records
            if record.get("product_id") == product_id
            and _parse_iso_date(record.get("date")) >= evaluation_start_date
        ]
        if not product_records:
            raise ValueError(f"No evaluation records found for {product_id}.")
        pack_size_units = pack_size_by_id[product_id]
        metrics = {
            "total_fulfilled_demand_units": sum(
                _record_integer(record, "fulfilled_demand_units")
                for record in product_records
            ),
            "total_unmet_demand_units": sum(
                _record_integer(record, "unmet_demand_units")
                for record in product_records
            ),
            "stockout_event_count": sum(
                1 for record in product_records if record.get("stockout_event") is True
            ),
            "total_waste_units": sum(
                _record_integer(record, "waste_units")
                for record in product_records
            ),
            "ending_inventory_units": _record_integer(
                product_records[-1],
                "ending_inventory_units",
            ),
            "total_delivered_units": sum(
                _record_integer(record, "delivered_units")
                for record in product_records
            ),
            "total_delivered_packs": sum(
                _record_integer(record, "delivered_units") // pack_size_units
                for record in product_records
            ),
        }
        by_product[product_id] = metrics

    overall = {
        metric: sum(product_metrics[metric] for product_metrics in by_product.values())
        for metric in SCENARIO_METRICS
    }
    return {
        "evaluation_start_date": evaluation_start_date.isoformat(),
        "overall": overall,
        "by_product": by_product,
    }


def compare_scenarios(
    fixed_records: list[dict[str, object]],
    policy_records: list[dict[str, object]],
    products_config: dict[str, object],
    evaluation_start_date: date,
) -> dict[str, object]:
    """Compare policy values with the fixed synthetic baseline."""
    if len(fixed_records) != len(policy_records):
        raise ValueError("Fixed and policy scenarios must contain equal records.")
    for fixed_record, policy_record in zip(
        fixed_records,
        policy_records,
        strict=True,
    ):
        for field_name in RECORD_COLUMNS:
            if fixed_record.get(field_name) != policy_record.get(field_name):
                raise ValueError(
                    "Fixed and policy scenarios must use identical demand records."
                )
    fixed_summary = summarize_scenario(
        fixed_records,
        products_config,
        evaluation_start_date,
    )
    policy_summary = summarize_scenario(
        policy_records,
        products_config,
        evaluation_start_date,
    )
    fixed_overall = _metric_mapping(fixed_summary["overall"], "fixed overall")
    policy_overall = _metric_mapping(policy_summary["overall"], "policy overall")
    difference_overall = {
        metric: policy_overall[metric] - fixed_overall[metric]
        for metric in SCENARIO_METRICS
    }
    fixed_by_product = _summary_by_product(fixed_summary["by_product"])
    policy_by_product = _summary_by_product(policy_summary["by_product"])
    difference_by_product = {
        product_id: {
            metric: (
                policy_by_product[product_id][metric]
                - fixed_by_product[product_id][metric]
            )
            for metric in SCENARIO_METRICS
        }
        for product_id in fixed_by_product
    }
    return {
        "evaluation_start_date": evaluation_start_date.isoformat(),
        "fixed": fixed_summary,
        "policy": policy_summary,
        "difference": {
            "overall": difference_overall,
            "by_product": difference_by_product,
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Run the deterministic Phase 4B ordering command-line interface."""
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
        ordering_config = load_ordering_config(
            arguments.ordering_config,
            products_config,
            delivery_config,
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
        fixed_records = simulate_inventory(
            demand_records,
            products_config,
            delivery_config,
            inventory_config,
        )
        policy_records, recommendations = simulate_policy_inventory(
            demand_records,
            products_config,
            delivery_config,
            inventory_config,
            ordering_config,
        )
        delivery = _mapping(delivery_config["delivery"], "delivery")
        cycle_length_days = _integer(
            delivery["cycle_length_days"],
            "cycle_length_days",
        )
        first_date = _parse_iso_date(demand_records[0]["date"])
        evaluation_start_date = first_date + timedelta(days=cycle_length_days)
        comparison = compare_scenarios(
            fixed_records,
            policy_records,
            products_config,
            evaluation_start_date,
        )
        write_recommendations_csv(
            recommendations,
            arguments.output,
            demand_records,
            products_config,
            delivery_config,
            ordering_config,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Generated {len(recommendations)} recommendation records at "
        f"{arguments.output} with seed {seed_used}."
    )
    overall_fixed = _metric_mapping(
        _mapping(comparison["fixed"], "fixed summary")["overall"],
        "fixed overall",
    )
    overall_policy = _metric_mapping(
        _mapping(comparison["policy"], "policy summary")["overall"],
        "policy overall",
    )
    overall_difference = _metric_mapping(
        _mapping(comparison["difference"], "difference summary")["overall"],
        "difference overall",
    )
    print(
        "Synthetic scenario comparison from "
        f"{comparison['evaluation_start_date']} (policy - fixed):"
    )
    for metric in SCENARIO_METRICS:
        print(
            f"  {metric}: fixed={overall_fixed[metric]}, "
            f"policy={overall_policy[metric]}, "
            f"difference={overall_difference[metric]}"
        )
    print(
        "Results describe one synthetic scenario and do not demonstrate "
        "real-world improvement or an optimal policy."
    )
    return 0


def _eligible_delivery_dates(
    demand_records: list[dict[str, object]],
    product_count: int,
    cycle_length_days: int,
) -> list[date]:
    if not demand_records or len(demand_records) % product_count != 0:
        raise ValueError("Demand records must contain complete product dates.")
    dates: list[date] = []
    for record_index in range(0, len(demand_records), product_count):
        record = demand_records[record_index]
        if not isinstance(record, dict):
            raise ValueError("Each demand record must be a mapping.")
        current_date = _parse_iso_date(record.get("date"))
        if record.get("delivery_event") is True and record_index != 0:
            baseline = calculate_baseline_cycle_demand(
                demand_records,
                _string(record.get("product_id"), "product_id"),
                current_date,
                cycle_length_days,
            )
            if baseline is not None:
                dates.append(current_date)
    return dates


def _record_integer(record: dict[str, object], field_name: str) -> int:
    value = record.get(field_name)
    _nonnegative_integer(value, field_name)
    return value


def _nonnegative_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")


def _positive_integer(value: object, field_name: str) -> None:
    _nonnegative_integer(value, field_name)
    if value == 0:
        raise ValueError(f"{field_name} must be positive.")


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


def _mapping(value: object, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a mapping.")
    return value


def _metric_mapping(value: object, description: str) -> dict[str, int]:
    mapping = _mapping(value, description)
    metrics: dict[str, int] = {}
    for metric in SCENARIO_METRICS:
        metric_value = mapping.get(metric)
        if isinstance(metric_value, bool) or not isinstance(metric_value, int):
            raise ValueError(f"{description} metric {metric} must be an integer.")
        metrics[metric] = metric_value
    return metrics


def _summary_by_product(value: object) -> dict[str, dict[str, int]]:
    mapping = _mapping(value, "by_product")
    return {
        product_id: _metric_mapping(metrics, f"metrics for {product_id}")
        for product_id, metrics in mapping.items()
    }


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


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic baseline order recommendations."
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
        "--ordering-config",
        type=Path,
        default=Path("config/ordering.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/generated/synthetic_order_recommendations.csv"),
    )
    parser.add_argument("--seed", type=int)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
