# Phase 7A — Baseline Forecast Evaluation

## Purpose

Phase 7A evaluates two transparent demand forecasts on the deterministic
synthetic dataset. It forecasts demand only. It does not change inventory
simulation, ordering recommendations, or the Phase 4B policy.

Phase 7A compares the previous completed cycle baseline with the expanding
weekday-mean candidate. Neither method is a trained machine-learning model.
Phase 7A itself does not implement Ridge regression, scikit-learn, or other
machine-learning behavior. Phase 7B implements the trained model separately and
is documented in `ml_forecasting.md`.

All records and results are synthetic. They do not establish real-world
accuracy, operational benefit, or ordering performance.

## Target and prediction timing

Each forecast predicts total `demand_units` for one approved product over the
next complete 14-day delivery cycle. A forecast is created on an eligible
Tuesday delivery date before demand for that date is known.

For forecast origin `O`:

```text
training data ends = O - 1 day
target period = O through O + 13 days
actual demand = sum of demand_units in the target period
```

The default 56-day dataset contains four complete cycles. The first cycle is a
warm-up, leaving these three expanding evaluation origins:

| Forecast origin | Available history | Target period |
| --- | --- | --- |
| 2025-01-21 | 2025-01-07 through 2025-01-20 | 2025-01-21 through 2025-02-03 |
| 2025-02-04 | 2025-01-07 through 2025-02-03 | 2025-02-04 through 2025-02-17 |
| 2025-02-18 | 2025-01-07 through 2025-02-17 | 2025-02-18 through 2025-03-03 |

There are 27 default forecast records: three origins multiplied by nine
products. An incomplete future cycle is skipped rather than partially scored.

## Baseline

The naive baseline reuses the existing Phase 4B completed-cycle calculation:

```text
baseline_prediction_units =
    sum of product demand from O - 14 days through O - 1 day
```

This baseline is aligned with the delivery cycle and never reads current-day or
future demand.

## Candidate method

The candidate is an expanding weekday-mean forecast. For each date in the
target cycle, it averages the product's demand from all earlier dates with the
same weekday. It then sums the 14 daily estimates:

```text
weekday_mean(product, weekday, O) =
    mean of demand_units where product matches, weekday matches, and date < O

candidate_prediction_units =
    sum of weekday_mean values for dates O through O + 13 days
```

The method is deterministic, uses no fitted black-box model, and adds no
dependency. The first candidate total equals the first baseline total because
the 14-day warm-up contains exactly two observations for every weekday. Later
candidate forecasts can differ because they use expanding history.

## Leakage boundary

Allowed inputs are:

- Approved public product aliases.
- Forecast and target calendar dates.
- Weekdays derived from calendar dates.
- Historical `demand_units` from dates strictly before the forecast origin.

The forecast excludes same-day and future demand, fulfilled demand, units used,
unmet demand, inventory outcomes, stockout results, expiration, waste, order
recommendations, and future actual values.

`is_high_demand_day` is known from configuration but is intentionally excluded.
It directly reflects part of the synthetic generation rule and remains
provisional for some products. Pack size, shelf life, risk labels, and delivery
quantities are also excluded because they do not define this demand-only task.

## Metrics

Mean absolute error is the primary unit-scale metric:

```text
MAE = mean(abs(actual demand - predicted demand))
```

Weighted absolute percentage error is an aggregate percentage:

```text
WAPE = 100.0 * sum(abs(actual demand - predicted demand)) / sum(actual demand)
```

Phase 7A reports WAPE as a percentage using the exact formula above. WAPE may
exceed 100.0. If total actual demand is zero, WAPE is `None`.

Candidate and baseline MAE values are classified as a tie only when:

```python
math.isclose(candidate, baseline, rel_tol=0.0, abs_tol=1e-9)
```

Otherwise, lower candidate MAE is a win and higher candidate MAE is a loss.
The project defines no passing accuracy threshold and no combined accuracy
score.

## Forecast-record contract

In-memory records use these columns in stable origin and product order:

| Column | Type | Meaning |
| --- | --- | --- |
| `forecast_origin_date` | ISO date string | Delivery-date prediction checkpoint. |
| `training_start_date` | ISO date string | Earliest available historical date. |
| `training_end_date` | ISO date string | Day immediately before the origin. |
| `target_start_date` | ISO date string | First target date; equal to the origin. |
| `target_end_date` | ISO date string | Final date in the 14-day target cycle. |
| `product_id` | string | One approved public product alias. |
| `actual_demand_units` | nonnegative integer | Actual target-cycle demand total. |
| `baseline_prediction_units` | nonnegative integer | Previous-cycle total. |
| `candidate_prediction_units` | nonnegative float | Expanding weekday-mean total. |
| `baseline_absolute_error_units` | nonnegative integer | Baseline absolute error. |
| `candidate_absolute_error_units` | nonnegative float | Candidate absolute error. |

Predictions are not rounded before evaluation. Forecast records remain in
memory; Phase 7A does not add a generated CSV or CLI.

## Ordering boundary and limitations

Phase 7A does not feed forecasts into Phase 4B, replace its baseline demand,
change full-pack rounding, or run a forecast-driven inventory comparison. Such
an experiment requires separate approval.

The dataset contains only 56 synthetic days and three evaluation cycles. The
results describe the configured generator and seed 42, not customer behavior or
real operations. Wins, ties, and losses must be reported without claiming that
the candidate is generally superior.
