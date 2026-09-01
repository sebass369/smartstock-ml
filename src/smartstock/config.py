"""Load and validate synthetic SmartStock configuration files."""

from datetime import date
from pathlib import Path
from typing import Any

import yaml

APPROVED_PRODUCT_IDS = {
    "Milk_Product_A",
    "Milk_Product_B",
    "Whole_Milk",
    "Fruit_Refresher_A",
    "Fruit_Refresher_B",
    "Cold_Foam_A",
    "Whipped_Topping",
    "Skim_Milk",
    "Oat_Beverage",
}

ALLOWED_DEMAND_LEVELS = {"high", "low", "unknown"}
ALLOWED_PRIMARY_RISKS = {"stockout", "waste", "unknown"}
ALLOWED_WEEKDAYS = {
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}
ELIGIBLE_PROVISIONAL_FIELDS = {
    "pack_size_units",
    "open_shelf_life_days",
    "unopened_shelf_life_days",
    "demand_level",
    "high_demand_days",
    "primary_risk",
}

PRODUCT_REQUIRED_FIELDS = {
    "product_id",
    "pack_size_units",
    "open_shelf_life_days",
    "unopened_shelf_life_days",
    "demand_level",
    "high_demand_days",
    "primary_risk",
    "provisional_fields",
}

DELIVERY_REQUIRED_FIELDS = {
    "cycle_length_days",
    "delivery_weekday",
    "delivery_window",
    "full_pack_ordering_required",
    "require_pack_size_constraints",
}

GENERATION_REQUIRED_FIELDS = {
    "start_date",
    "duration_days",
    "default_seed",
    "demand_ranges",
    "high_demand_day_adjustment",
}

DEMAND_RANGE_LEVELS = {"low", "high"}
DEMAND_RANGE_REQUIRED_FIELDS = {"minimum", "maximum"}


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file safely and return a dictionary."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as yaml_file:
        try:
            data = yaml.safe_load(yaml_file)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"Malformed YAML configuration: {config_path}"
            ) from exc

    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {config_path}")
    return data


def load_products_config(path: str | Path) -> dict[str, Any]:
    """Load and validate the synthetic product configuration."""
    config = load_yaml(path)
    validate_products_config(config)
    return config


def load_delivery_config(path: str | Path) -> dict[str, Any]:
    """Load and validate the synthetic delivery configuration."""
    config = load_yaml(path)
    validate_delivery_config(config)
    return config


def load_generation_config(path: str | Path) -> dict[str, Any]:
    """Load and validate the synthetic demand generation configuration."""
    config = load_yaml(path)
    validate_generation_config(config)
    return config


def validate_products_config(config: dict[str, Any]) -> None:
    """Validate product aliases, shelf-life values, risks, and flags."""
    products = config.get("products")
    if not isinstance(products, list):
        raise ValueError("Product configuration must contain a products list.")

    if len(products) != len(APPROVED_PRODUCT_IDS):
        raise ValueError("Product configuration must contain exactly nine products.")

    product_ids: list[str] = []
    for product in products:
        _validate_product(product)
        product_ids.append(product["product_id"])

    if len(product_ids) != len(set(product_ids)):
        raise ValueError("Product IDs must be unique.")

    configured_ids = set(product_ids)
    if configured_ids != APPROVED_PRODUCT_IDS:
        extra_ids = configured_ids - APPROVED_PRODUCT_IDS
        missing_ids = APPROVED_PRODUCT_IDS - configured_ids
        raise ValueError(
            "Product IDs must match the approved public aliases. "
            f"Extra: {sorted(extra_ids)}. Missing: {sorted(missing_ids)}."
        )

    for product_id in product_ids:
        if "donut" in product_id.lower():
            raise ValueError("Donut products are excluded from this version.")


def validate_delivery_config(config: dict[str, Any]) -> None:
    """Validate the synthetic 14-day Tuesday delivery rules."""
    delivery = config.get("delivery")
    if not isinstance(delivery, dict):
        raise ValueError("Delivery configuration must contain a delivery mapping.")

    missing_fields = DELIVERY_REQUIRED_FIELDS - set(delivery)
    if missing_fields:
        raise ValueError(
            f"Delivery configuration is missing fields: {sorted(missing_fields)}."
        )

    cycle_length_days = delivery["cycle_length_days"]
    if (
        isinstance(cycle_length_days, bool)
        or not isinstance(cycle_length_days, int)
        or cycle_length_days != 14
    ):
        raise ValueError("cycle_length_days must be the integer 14.")
    if delivery["delivery_weekday"] != "Tuesday":
        raise ValueError("Delivery weekday must be Tuesday.")
    if delivery["full_pack_ordering_required"] is not True:
        raise ValueError("Full-pack ordering must be required.")
    if delivery["require_pack_size_constraints"] is not True:
        raise ValueError("Pack-size constraints must be required.")

    delivery_window = delivery["delivery_window"]
    if not isinstance(delivery_window, dict):
        raise ValueError("Delivery window must be a mapping.")
    for field_name in ("start_time", "end_time", "approximate"):
        if field_name not in delivery_window:
            raise ValueError(f"Delivery window is missing {field_name}.")

    start_time = delivery_window["start_time"]
    if not isinstance(start_time, str) or start_time != "11:00":
        raise ValueError("Delivery window start_time must be the string '11:00'.")

    end_time = delivery_window["end_time"]
    if not isinstance(end_time, str) or end_time != "12:00":
        raise ValueError("Delivery window end_time must be the string '12:00'.")

    if delivery_window["approximate"] is not True:
        raise ValueError("Delivery window approximate must be the Boolean true.")


def validate_generation_config(config: dict[str, Any]) -> None:
    """Validate dates, randomness, and synthetic demand ranges."""
    _validate_exact_fields(config, {"generation"}, "Generation YAML")
    generation = config.get("generation")
    if not isinstance(generation, dict):
        raise ValueError("Generation configuration must contain a generation mapping.")

    _validate_exact_fields(
        generation,
        GENERATION_REQUIRED_FIELDS,
        "Generation configuration",
    )

    start_date = generation["start_date"]
    if not isinstance(start_date, str):
        raise ValueError("start_date must be an ISO date string.")
    try:
        parsed_start_date = date.fromisoformat(start_date)
    except ValueError as exc:
        raise ValueError("start_date must be a valid ISO date.") from exc
    if parsed_start_date.isoformat() != start_date:
        raise ValueError("start_date must use the ISO YYYY-MM-DD format.")
    if parsed_start_date.strftime("%A") != "Tuesday":
        raise ValueError("start_date must be a Tuesday.")

    _validate_integer(generation, "duration_days", minimum=1)
    _validate_integer(generation, "default_seed")
    _validate_integer(generation, "high_demand_day_adjustment", minimum=0)

    demand_ranges = generation["demand_ranges"]
    if not isinstance(demand_ranges, dict):
        raise ValueError("demand_ranges must be a mapping.")
    if "medium" in demand_ranges:
        raise ValueError("The medium demand level is unsupported.")
    _validate_exact_fields(demand_ranges, DEMAND_RANGE_LEVELS, "demand_ranges")

    for demand_level in ("low", "high"):
        demand_range = demand_ranges[demand_level]
        if not isinstance(demand_range, dict):
            raise ValueError(f"The {demand_level} demand range must be a mapping.")
        _validate_exact_fields(
            demand_range,
            DEMAND_RANGE_REQUIRED_FIELDS,
            f"The {demand_level} demand range",
        )
        _validate_integer(demand_range, "minimum", minimum=0)
        _validate_integer(demand_range, "maximum", minimum=0)
        if demand_range["minimum"] > demand_range["maximum"]:
            raise ValueError(
                f"The {demand_level} demand range minimum cannot exceed maximum."
            )


def _validate_product(product: Any) -> None:
    if not isinstance(product, dict):
        raise ValueError("Each product must be a mapping.")

    missing_fields = PRODUCT_REQUIRED_FIELDS - set(product)
    if missing_fields:
        raise ValueError(
            f"Product {product.get('product_id')} is missing fields: "
            f"{sorted(missing_fields)}."
        )

    product_id = product["product_id"]
    if product_id not in APPROVED_PRODUCT_IDS:
        raise ValueError(f"Unknown product ID: {product_id}.")

    _validate_positive_integer(product, "pack_size_units")
    _validate_positive_integer(product, "open_shelf_life_days")
    _validate_positive_integer(product, "unopened_shelf_life_days")

    if product["demand_level"] not in ALLOWED_DEMAND_LEVELS:
        raise ValueError(f"Invalid demand level for {product_id}.")
    if product["primary_risk"] not in ALLOWED_PRIMARY_RISKS:
        raise ValueError(f"Invalid primary risk for {product_id}.")

    high_demand_days = product["high_demand_days"]
    if not isinstance(high_demand_days, list):
        raise ValueError(f"High-demand days must be a list for {product_id}.")
    for weekday in high_demand_days:
        if weekday not in ALLOWED_WEEKDAYS:
            raise ValueError(
                f"Invalid high-demand weekday for {product_id}: {weekday}."
            )

    provisional_fields = product["provisional_fields"]
    if not isinstance(provisional_fields, list):
        raise ValueError(f"Provisional fields must be a list for {product_id}.")

    seen_provisional_fields: set[str] = set()
    for field_name in provisional_fields:
        if not isinstance(field_name, str):
            raise ValueError(
                f"Provisional field entries must be strings for {product_id}."
            )
        if field_name not in ELIGIBLE_PROVISIONAL_FIELDS:
            raise ValueError(
                f"Unknown provisional field for {product_id}: {field_name}."
            )
        if field_name in seen_provisional_fields:
            raise ValueError(
                f"Duplicate provisional field for {product_id}: {field_name}."
            )
        seen_provisional_fields.add(field_name)


def _validate_positive_integer(product: dict[str, Any], field_name: str) -> None:
    value = product[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{field_name} must be a positive integer for {product['product_id']}."
        )


def _validate_exact_fields(
    mapping: dict[str, Any],
    required_fields: set[str],
    description: str,
) -> None:
    missing_fields = required_fields - set(mapping)
    if missing_fields:
        raise ValueError(
            f"{description} is missing fields: {sorted(missing_fields)}."
        )

    unknown_fields = set(mapping) - required_fields
    if unknown_fields:
        raise ValueError(
            f"{description} has unknown fields: {sorted(unknown_fields)}."
        )


def _validate_integer(
    mapping: dict[str, Any],
    field_name: str,
    minimum: int | None = None,
) -> None:
    value = mapping[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}.")
