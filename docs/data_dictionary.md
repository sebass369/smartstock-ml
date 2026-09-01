# Phase 3 Data Dictionary

## Purpose and boundary

Phase 3 creates deterministic synthetic daily demand scenarios for the nine approved public product aliases. It does not simulate starting inventory, available inventory, ending inventory, fulfilled demand, units used, unmet demand, expiration, waste, stockouts, or ordering recommendations. Those outcomes are deferred to Phase 4 or later.

The data is synthetic. It is not a real operational record and must not be used as food-safety or ordering guidance.

## Approved generation assumptions

- Start date: `2025-01-07`, a Tuesday.
- Duration: 56 days.
- Default seed: 42.
- Low-demand range: inclusive integers 0 through 2.
- High-demand range: inclusive integers 3 through 6.
- High-demand weekday adjustment: add exactly 1 unit.
- Delivery cycle: the first date and every 14 days afterward.
- Default row count: 56 days multiplied by 9 products, or 504 records.

The demand calculation is:

```text
base_demand = random integer from the product level's inclusive range

if the weekday is in the product's high_demand_days:
    demand_units = base_demand + 1
else:
    demand_units = base_demand
```

The generator uses a local `random.Random(seed)` instance. The same validated configuration, seed, start date, duration, and generator code produce identical records.

## CSV contract

Columns always appear in this order:

| Column | Type | Meaning | Validation |
| --- | --- | --- | --- |
| `date` | ISO date string | Synthetic date in `YYYY-MM-DD` format. | Dates are continuous and ascending. |
| `weekday` | string | English weekday derived from `date`. | Must match the date. |
| `product_id` | string | One approved public product alias. | Every date contains all nine aliases exactly once. |
| `is_high_demand_day` | Boolean | Whether the weekday is listed in the product configuration. | Written as lowercase `true` or `false`. |
| `demand_units` | integer | Synthetic demand before any inventory limit. | Nonnegative and within the approved range plus any weekday adjustment. |
| `delivery_event` | Boolean | Whether the date is on the configured 14-day Tuesday cycle. | True on offsets 0, 14, 28, and 42 for the default dataset. |

`delivery_event` is a calendar marker only. It does not describe a delivery quantity and does not change inventory.

## Target leakage

`demand_units` is the outcome a future demand model may try to predict. A forecasting phase must not use the same row's `demand_units`, or demand from a future date, as an input feature. Calendar fields known before the prediction date may be used later only after a separate forecasting design is approved.

## Output and privacy

Run the generator from the repository root:

```bash
python -m smartstock.generator
```

The default output is `data/generated/synthetic_daily_records.csv`. Generated CSV files are ignored by Git and should not be committed.

The schema excludes company and employer names, stores, locations, people, vendors, credentials, private URLs, source paths, real documents, and private identifiers. Donut products and donut waste are excluded.

Python 3.12 is the baseline. Python 3.13 is used for compatibility verification when available.
