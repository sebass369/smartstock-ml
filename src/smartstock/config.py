"""Load and validate synthetic SmartStock configuration files."""

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


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file safely and return a dictionary."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as yaml_file:
        data = yaml.safe_load(yaml_file)

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

    if delivery["cycle_length_days"] != 14:
        raise ValueError("Delivery cycle length must be 14 days.")
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
            raise ValueError(f"Invalid high-demand weekday for {product_id}: {weekday}.")

    if not isinstance(product["provisional_fields"], list):
        raise ValueError(f"Provisional fields must be a list for {product_id}.")


def _validate_positive_integer(product: dict[str, Any], field_name: str) -> None:
    value = product[field_name]
    if not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{field_name} must be a positive integer for {product['product_id']}."
        )
