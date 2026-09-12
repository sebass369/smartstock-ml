# Phase 3 and Phase 4A Data Dictionary

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

Phase 3 supports only `low` and `high` demand levels. `medium` is unsupported. A product configured with `demand_level: unknown` cannot be processed by the Phase 3 generator. The broader Phase 2 product validator may retain `unknown` for incomplete or future configuration.

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

The default output is `data/generated/synthetic_daily_records.csv`. Generated CSV files are ignored by Git and should not be committed. The directory itself is not ignored, and `data/generated/.gitkeep` remains tracked.

The schema excludes company and employer names, stores, locations, people, vendors, credentials, private URLs, source paths, real documents, and private identifiers. Donut products and donut waste are excluded.

Python 3.12 is the baseline. Python 3.13 is used for compatibility verification when available.

## Phase 4A purpose and boundary

Phase 4A generates Phase 3 demand in memory and applies fixed synthetic inventory inputs. It simulates FIFO fulfillment, full-pack deliveries, unopened expiration, expiration waste, and stockouts. The fixed delivery pack counts are scenario inputs, not ordering recommendations. The Phase 4B baseline ordering policy is postponed.

Phase 4A does not use open shelf life, primary risk, machine learning, forecasting, optimization, operational records, or food-safety rules. Provisional Phase 3 high-demand weekdays may influence the approved demand input and remain identified in `products.yaml`.

## Inventory event order

For each product and date, the simulator carries the prior cohort remainders forward. On the first date, starting inventory becomes a fresh unopened cohort. It records starting inventory, removes expired cohorts, adds any scheduled delivery as a fresh usable cohort, and then consumes demand from the oldest usable cohorts first. Empty cohorts are removed before their remainders are carried forward.

A cohort received on date `D` with unopened shelf life `N` is usable from `D` through `D + N - 1`. It expires before demand on `D + N`.

The aggregate relationships are:

```text
available_inventory_units =
    starting_inventory_units - expired_units + delivered_units

fulfilled_demand_units = min(demand_units, available_inventory_units)
units_used = fulfilled_demand_units
unmet_demand_units = demand_units - fulfilled_demand_units
waste_units = expired_units
ending_inventory_units = available_inventory_units - units_used
```

`stockout_event` is true exactly when demand exceeds available inventory and unmet demand is positive.

## Phase 4A CSV contract

The separate default output is `data/generated/synthetic_inventory_records.csv`. It contains 504 rows and these columns in exact order:

| Column | Type | Meaning and validation |
| --- | --- | --- |
| `date` | ISO date string | Preserved Phase 3 date; continuous and ascending. |
| `weekday` | string | Preserved English weekday matching `date`. |
| `product_id` | string | One of exactly nine approved public aliases. |
| `is_high_demand_day` | Boolean | Preserved Phase 3 configuration flag. |
| `demand_units` | integer | Preserved nonnegative synthetic demand before inventory limits. |
| `delivery_event` | Boolean | Preserved 14-day Tuesday calendar marker. |
| `starting_inventory_units` | integer | Cohort total before expiration and delivery; equals prior ending inventory after the first date. |
| `delivered_units` | integer | Fixed pack count multiplied by product pack size on delivery dates; zero otherwise. |
| `expired_units` | integer | Remaining units removed from cohorts whose expiration date has arrived. |
| `available_inventory_units` | integer | Usable units after expiration and delivery, before demand. |
| `fulfilled_demand_units` | integer | Minimum of demand and available inventory. |
| `units_used` | integer | Physical units consumed; equal to fulfilled demand in Phase 4A. |
| `unmet_demand_units` | integer | Demand that available inventory could not fulfill. |
| `waste_units` | integer | Equal to expired units because no other waste rule is approved. |
| `ending_inventory_units` | integer | Usable cohort total remaining after demand. |
| `stockout_event` | Boolean | True exactly when demand exceeds availability and unmet demand is positive. |

All numeric fields are decimal nonnegative integers. Booleans are lowercase `true` or `false`. Files use UTF-8 without a byte-order mark, LF line endings, and one final LF.

## Default expiration limitation

The default simulation lasts 56 days. Every approved unopened shelf life is at least 60 days, and starting inventory is fresh. Therefore, every default `expired_units` and `waste_units` value is zero. Focused tests use shorter synthetic shelf lives to verify the exact expiration boundary without changing the approved default duration.

## Phase 4A target leakage

Inventory state and outcome columns may contain information that would not be known when making a future prediction. Future forecasting work must not use same-row demand, fulfilled demand, usage, unmet demand, expiration, waste, ending inventory, or stockout outcomes as input features for the target being predicted. Any future feature timing requires a separate approved design.

Run Phase 4A with:

```bash
python -m smartstock.inventory
```

## Phase 4B purpose and timing

Phase 4B creates full-pack baseline order recommendations. The first 14-day cycle
is a shared warm-up using the Phase 4A fixed delivery on January 7, 2025. The
first recommendation occurs on January 21. Recommendations are also produced on
February 4 and February 18, giving 27 default records.

At each eligible delivery date, carried cohorts expire first. The policy then
measures usable inventory and calculates a recommendation before receipt and
current-day demand. The synthetic Version 1 lead time is zero days, so
`recommendation_date` equals `delivery_date`.

The baseline uses exactly the previous 14 completed `demand_units` values for the
product. It never uses current-day or future demand, fulfilled demand, units used,
or later inventory outcomes.

## Phase 4B recommendation CSV contract

The separate default output is
`data/generated/synthetic_order_recommendations.csv`. Columns always appear in
this order:

| Column | Type | Meaning and validation |
| --- | --- | --- |
| `recommendation_date` | ISO date string | Synthetic decision date; equal to the delivery date. |
| `delivery_date` | ISO date string | Eligible 14-day Tuesday delivery date. |
| `history_start_date` | ISO date string | Delivery date minus 14 days. |
| `history_end_date` | ISO date string | Day immediately before delivery. |
| `product_id` | string | One approved public product alias. |
| `baseline_demand_units` | integer | Sum of the product's demand over the exact completed history window. |
| `safety_stock_units` | integer | Configured safety-stock packs multiplied by product pack size; zero by default. |
| `current_usable_inventory_units` | integer | Cohort total after same-day expiration and before receipt. |
| `units_expiring_before_next_delivery` | integer | Current cohort units expiring strictly before the next delivery date. |
| `usable_inventory_position_units` | integer | Current usable units minus conservatively excluded expiring units, clamped at zero. |
| `net_order_units` | integer | Target units minus usable inventory position, clamped at zero. |
| `pack_size_units` | integer | Positive pack size read from `products.yaml`. |
| `recommended_order_packs` | integer | Smallest nonnegative full-pack count covering net order units. |
| `recommended_order_units` | integer | Recommended packs multiplied by pack size. |

All numeric fields are decimal nonnegative integers. The file uses UTF-8 without
a byte-order mark, LF line endings, and one final LF. Rows use stable delivery
date order and `products.yaml` product order.

## Phase 4B expiration limitation

A current cohort receives zero inventory credit when its expiration date is
strictly between the current and next delivery dates. A cohort expiring on the
next delivery date remains credited. The policy does not predict whether FIFO
demand could consume earlier-expiring inventory. This transparent conservative
rule may add inventory or waste and is not an optimization claim.

## Phase 4B leakage boundary

For delivery date `D`, only demand from `D - 14` through `D - 1` may influence
the recommendation. Demand and inventory outcomes on `D` or later cannot be
read. Cohort receipt and expiration dates, current post-expiration inventory,
pack sizes, delivery-cycle configuration, and approved safety-stock settings are
known at the checkpoint.

The CLI compares the fixed and policy scenarios in memory beginning on day 14.
It does not write a comparison CSV. Results describe one synthetic scenario and
do not establish real-world improvement or an optimal policy.

Run Phase 4B with:

```bash
python -m smartstock.ordering
```
