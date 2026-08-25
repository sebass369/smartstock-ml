from copy import deepcopy
from pathlib import Path

import pytest

from smartstock.config import (
    ALLOWED_DEMAND_LEVELS,
    ALLOWED_PRIMARY_RISKS,
    ALLOWED_WEEKDAYS,
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_products_config,
    validate_products_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = PROJECT_ROOT / "config" / "products.yaml"
DELIVERY_PATH = PROJECT_ROOT / "config" / "delivery.yaml"


def test_real_synthetic_configuration_loads_successfully():
    products_config = load_products_config(PRODUCTS_PATH)
    delivery_config = load_delivery_config(DELIVERY_PATH)

    assert "products" in products_config
    assert "delivery" in delivery_config


def test_exactly_nine_approved_product_aliases_are_present():
    products = load_products_config(PRODUCTS_PATH)["products"]
    product_ids = {product["product_id"] for product in products}

    assert len(products) == 9
    assert product_ids == APPROVED_PRODUCT_IDS


def test_product_ids_are_unique():
    products = load_products_config(PRODUCTS_PATH)["products"]
    product_ids = [product["product_id"] for product in products]

    assert len(product_ids) == len(set(product_ids))


def test_pack_sizes_and_shelf_life_values_are_positive_integers():
    products = load_products_config(PRODUCTS_PATH)["products"]

    for product in products:
        assert isinstance(product["pack_size_units"], int)
        assert product["pack_size_units"] > 0
        assert isinstance(product["open_shelf_life_days"], int)
        assert product["open_shelf_life_days"] > 0
        assert isinstance(product["unopened_shelf_life_days"], int)
        assert product["unopened_shelf_life_days"] > 0


def test_demand_levels_risks_and_weekdays_use_approved_values():
    products = load_products_config(PRODUCTS_PATH)["products"]

    for product in products:
        assert product["demand_level"] in ALLOWED_DEMAND_LEVELS
        assert product["primary_risk"] in ALLOWED_PRIMARY_RISKS
        assert set(product["high_demand_days"]).issubset(ALLOWED_WEEKDAYS)


def test_provisional_fields_are_correctly_represented():
    products = {
        product["product_id"]: product
        for product in load_products_config(PRODUCTS_PATH)["products"]
    }

    for product in products.values():
        assert isinstance(product["provisional_fields"], list)

    assert products["Whipped_Topping"]["provisional_fields"] == [
        "pack_size_units",
        "open_shelf_life_days",
        "unopened_shelf_life_days",
        "high_demand_days",
        "primary_risk",
    ]
    assert "primary_risk" in products["Cold_Foam_A"]["provisional_fields"]
    assert "demand_level" in products["Oat_Beverage"]["provisional_fields"]


def test_delivery_cycle_is_fourteen_days_and_tuesday_based():
    delivery = load_delivery_config(DELIVERY_PATH)["delivery"]

    assert delivery["cycle_length_days"] == 14
    assert delivery["delivery_weekday"] == "Tuesday"
    assert delivery["delivery_window"]["start_time"] == "11:00"
    assert delivery["delivery_window"]["end_time"] == "12:00"
    assert delivery["delivery_window"]["approximate"] is True


def test_full_pack_and_pack_size_rules_are_enabled():
    delivery = load_delivery_config(DELIVERY_PATH)["delivery"]

    assert delivery["full_pack_ordering_required"] is True
    assert delivery["require_pack_size_constraints"] is True


def test_unknown_product_id_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["product_id"] = "Unapproved_Product"

    with pytest.raises(ValueError, match="Unknown product ID"):
        validate_products_config(config)


def test_non_positive_pack_size_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["pack_size_units"] = 0

    with pytest.raises(ValueError, match="pack_size_units"):
        validate_products_config(config)


def test_negative_shelf_life_value_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["open_shelf_life_days"] = -1

    with pytest.raises(ValueError, match="open_shelf_life_days"):
        validate_products_config(config)


def test_invalid_weekday_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["high_demand_days"] = ["Funday"]

    with pytest.raises(ValueError, match="Invalid high-demand weekday"):
        validate_products_config(config)
