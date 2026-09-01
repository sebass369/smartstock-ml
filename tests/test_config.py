from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from smartstock.config import (
    ALLOWED_DEMAND_LEVELS,
    ALLOWED_PRIMARY_RISKS,
    ALLOWED_WEEKDAYS,
    APPROVED_PRODUCT_IDS,
    load_delivery_config,
    load_generation_config,
    load_products_config,
    load_yaml,
    validate_delivery_config,
    validate_generation_config,
    validate_products_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = PROJECT_ROOT / "config" / "products.yaml"
DELIVERY_PATH = PROJECT_ROOT / "config" / "delivery.yaml"
GENERATION_PATH = PROJECT_ROOT / "config" / "generation.yaml"


def test_real_synthetic_configuration_loads_successfully():
    products_config = load_products_config(PRODUCTS_PATH)
    delivery_config = load_delivery_config(DELIVERY_PATH)
    generation_config = load_generation_config(GENERATION_PATH)

    assert "products" in products_config
    assert "delivery" in delivery_config
    assert "generation" in generation_config


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
    assert products["Oat_Beverage"]["demand_level"] == "low"
    assert "demand_level" not in products["Oat_Beverage"]["provisional_fields"]
    assert "high_demand_days" in products["Oat_Beverage"]["provisional_fields"]


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


def test_generation_configuration_contains_approved_values():
    generation = load_generation_config(GENERATION_PATH)["generation"]

    assert generation == {
        "start_date": "2025-01-07",
        "duration_days": 56,
        "default_seed": 42,
        "demand_ranges": {
            "low": {"minimum": 0, "maximum": 2},
            "high": {"minimum": 3, "maximum": 6},
        },
        "high_demand_day_adjustment": 1,
    }


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


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("pack_size_units", True),
        ("open_shelf_life_days", True),
        ("unopened_shelf_life_days", False),
        ("pack_size_units", 4.0),
    ],
)
def test_product_integer_fields_reject_non_integer_values(
    field_name, invalid_value
):
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0][field_name] = invalid_value

    with pytest.raises(ValueError, match=field_name):
        validate_products_config(config)


@pytest.mark.parametrize("invalid_value", [14.0, True, False, "14"])
def test_delivery_cycle_rejects_non_integer_values(invalid_value):
    config = deepcopy(load_delivery_config(DELIVERY_PATH))
    config["delivery"]["cycle_length_days"] = invalid_value

    with pytest.raises(ValueError, match="cycle_length_days"):
        validate_delivery_config(config)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("start_time", "10:00"),
        ("start_time", 1100),
        ("end_time", "13:00"),
        ("end_time", 1200),
    ],
)
def test_delivery_window_rejects_invalid_times(field_name, invalid_value):
    config = deepcopy(load_delivery_config(DELIVERY_PATH))
    config["delivery"]["delivery_window"][field_name] = invalid_value

    with pytest.raises(ValueError, match=field_name):
        validate_delivery_config(config)


@pytest.mark.parametrize("invalid_value", [False, 1, "true", "yes"])
def test_delivery_window_rejects_invalid_approximate_values(invalid_value):
    config = deepcopy(load_delivery_config(DELIVERY_PATH))
    config["delivery"]["delivery_window"]["approximate"] = invalid_value

    with pytest.raises(ValueError, match="approximate"):
        validate_delivery_config(config)


def test_invalid_demand_level_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["demand_level"] = "medium"

    with pytest.raises(ValueError, match="Invalid demand level"):
        validate_products_config(config)


def test_invalid_primary_risk_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["primary_risk"] = "spoilage"

    with pytest.raises(ValueError, match="Invalid primary risk"):
        validate_products_config(config)


def test_duplicate_product_ids_raise_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][1]["product_id"] = config["products"][0]["product_id"]

    with pytest.raises(ValueError, match="Product IDs must be unique"):
        validate_products_config(config)


def test_missing_required_product_field_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    del config["products"][0]["pack_size_units"]

    with pytest.raises(ValueError, match="missing fields.*pack_size_units"):
        validate_products_config(config)


def test_missing_required_delivery_field_raises_value_error():
    config = deepcopy(load_delivery_config(DELIVERY_PATH))
    del config["delivery"]["delivery_weekday"]

    with pytest.raises(ValueError, match="missing fields.*delivery_weekday"):
        validate_delivery_config(config)


@pytest.mark.parametrize("field_name", ["start_time", "end_time", "approximate"])
def test_missing_delivery_window_field_raises_value_error(field_name):
    config = deepcopy(load_delivery_config(DELIVERY_PATH))
    del config["delivery"]["delivery_window"][field_name]

    with pytest.raises(ValueError, match=f"missing {field_name}"):
        validate_delivery_config(config)


@pytest.mark.parametrize(
    "field_name", ["not_a_product_field", "product_id", "provisional_fields"]
)
def test_invalid_provisional_field_name_raises_value_error(field_name):
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["provisional_fields"] = [field_name]

    with pytest.raises(ValueError, match="Unknown provisional field"):
        validate_products_config(config)


def test_duplicate_provisional_field_names_raise_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["provisional_fields"] = [
        "demand_level",
        "demand_level",
    ]

    with pytest.raises(ValueError, match="Duplicate provisional field"):
        validate_products_config(config)


def test_non_string_provisional_field_entry_raises_value_error():
    config = deepcopy(load_products_config(PRODUCTS_PATH))
    config["products"][0]["provisional_fields"] = [1]

    with pytest.raises(ValueError, match="must be strings"):
        validate_products_config(config)


@pytest.mark.parametrize(
    "field_name",
    [
        "start_date",
        "duration_days",
        "default_seed",
        "demand_ranges",
        "high_demand_day_adjustment",
    ],
)
def test_missing_generation_field_raises_value_error(field_name):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    del config["generation"][field_name]

    with pytest.raises(ValueError, match=f"missing fields.*{field_name}"):
        validate_generation_config(config)


def test_unknown_generation_field_raises_value_error():
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["unknown_setting"] = 1

    with pytest.raises(ValueError, match="unknown fields.*unknown_setting"):
        validate_generation_config(config)


def test_unknown_generation_top_level_field_raises_value_error():
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["other_generation"] = {}

    with pytest.raises(ValueError, match="unknown fields.*other_generation"):
        validate_generation_config(config)


@pytest.mark.parametrize("invalid_value", ["not-a-date", "2025-02-30", 20250107])
def test_invalid_generation_start_date_raises_value_error(invalid_value):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["start_date"] = invalid_value

    with pytest.raises(ValueError, match="start_date"):
        validate_generation_config(config)


def test_generation_start_date_must_be_tuesday():
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["start_date"] = "2025-01-08"

    with pytest.raises(ValueError, match="Tuesday"):
        validate_generation_config(config)


@pytest.mark.parametrize("invalid_value", [True, False, 56.0, 0, -1])
def test_generation_duration_must_be_a_positive_integer(invalid_value):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["duration_days"] = invalid_value

    with pytest.raises(ValueError, match="duration_days"):
        validate_generation_config(config)


@pytest.mark.parametrize("invalid_value", [True, False, 42.0, "42"])
def test_generation_seed_must_be_an_integer(invalid_value):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["default_seed"] = invalid_value

    with pytest.raises(ValueError, match="default_seed"):
        validate_generation_config(config)


@pytest.mark.parametrize("demand_level", ["low", "high"])
def test_generation_requires_each_demand_range(demand_level):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    del config["generation"]["demand_ranges"][demand_level]

    with pytest.raises(ValueError, match=f"missing fields.*{demand_level}"):
        validate_generation_config(config)


def test_generation_rejects_medium_demand_range():
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["demand_ranges"]["medium"] = {
        "minimum": 1,
        "maximum": 3,
    }

    with pytest.raises(ValueError, match="medium demand level is unsupported"):
        validate_generation_config(config)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("minimum", True),
        ("maximum", False),
        ("minimum", 0.5),
        ("maximum", 2.5),
        ("minimum", -1),
        ("maximum", -1),
    ],
)
def test_generation_demand_ranges_reject_invalid_values(
    field_name, invalid_value
):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["demand_ranges"]["low"][field_name] = invalid_value

    with pytest.raises(ValueError, match=field_name):
        validate_generation_config(config)


def test_generation_demand_range_rejects_reversed_bounds():
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["demand_ranges"]["low"] = {
        "minimum": 3,
        "maximum": 2,
    }

    with pytest.raises(ValueError, match="minimum cannot exceed maximum"):
        validate_generation_config(config)


@pytest.mark.parametrize("invalid_value", [True, False, -1, 1.5])
def test_generation_adjustment_rejects_invalid_values(invalid_value):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["high_demand_day_adjustment"] = invalid_value

    with pytest.raises(ValueError, match="high_demand_day_adjustment"):
        validate_generation_config(config)


@pytest.mark.parametrize("invalid_value", [[], "low", None])
def test_generation_demand_ranges_must_be_a_mapping(invalid_value):
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["demand_ranges"] = invalid_value

    with pytest.raises(ValueError, match="demand_ranges must be a mapping"):
        validate_generation_config(config)


def test_generation_range_rejects_unknown_fields():
    config = deepcopy(load_generation_config(GENERATION_PATH))
    config["generation"]["demand_ranges"]["low"]["average"] = 1

    with pytest.raises(ValueError, match="unknown fields.*average"):
        validate_generation_config(config)


@pytest.mark.parametrize("yaml_text", ["", "- products"])
def test_yaml_top_level_must_be_a_mapping(tmp_path, yaml_text):
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a mapping"):
        load_yaml(config_path)


def test_malformed_yaml_raises_project_value_error(tmp_path):
    config_path = tmp_path / "malformed.yaml"
    config_path.write_text("products: [\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed YAML configuration") as exc_info:
        load_yaml(config_path)

    assert str(config_path) in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, yaml.YAMLError)


@pytest.mark.parametrize("yaml_text", ["", "- generation"])
def test_generation_yaml_top_level_must_be_a_mapping(tmp_path, yaml_text):
    config_path = tmp_path / "generation.yaml"
    config_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a mapping"):
        load_generation_config(config_path)


def test_malformed_generation_yaml_uses_project_error_handling(tmp_path):
    config_path = tmp_path / "generation.yaml"
    config_path.write_text("generation: [\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed YAML configuration"):
        load_generation_config(config_path)
