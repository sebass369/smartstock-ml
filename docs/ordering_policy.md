# Phase 4B Baseline Ordering Policy

## Purpose

Phase 4B adds a small, deterministic baseline for 14-day order recommendations.
It is designed to be easy to inspect and explain. It uses synthetic demand,
integer arithmetic, FIFO inventory cohorts, and full-pack rounding. It is not a
forecasting model or an optimization system.

## Decision checkpoint

Version 1 uses a synthetic zero-day lead time. On an eligible Tuesday delivery
date, the simulator performs these steps for each product:

1. Carry forward the prior FIFO cohorts.
2. Remove cohorts expiring on the current date.
3. Measure current usable inventory.
4. Calculate a recommendation from the previous 14 completed dates.
5. Add the recommended units as a fresh cohort.
6. Apply current-day demand using FIFO consumption.

The recommendation date equals the delivery date. Demand on that date and all
future dates is unavailable when the recommendation is calculated.

## Warm-up cycle

The first cycle, January 7 through January 20, 2025, is a shared warm-up period.
Both fixed and policy scenarios use the Phase 4A fixed delivery on January 7.
That receipt is a synthetic warm-up input, not a recommendation.

No recommendation is produced until 14 completed dates exist. Starting January
21, policy deliveries replace fixed deliveries and never supplement them. The
default recommendation dates are January 21, February 4, and February 18, for 27
records across nine products.

## Demand baseline

For product `P` and delivery date `D`:

```text
baseline_cycle_demand_units =
    sum of demand_units for P from D - 14 days through D - 1 day
```

The policy uses demand rather than fulfilled demand or units used. This preserves
needs that could not be fulfilled during a stockout.

## Expiration credit

After same-day expiration, the policy finds current cohort units satisfying:

```text
delivery_date < expires_on < delivery_date + 14 days
```

Those units receive zero inventory credit. Units expiring exactly on the next
delivery date remain credited because they are usable throughout the covered
cycle.

This rule is deliberately conservative. It does not predict that FIFO demand may
consume an older cohort before expiration. It may therefore recommend additional
inventory and may increase waste.

## Recommendation formulas

```text
safety_stock_units = safety_stock_packs * pack_size_units

target_inventory_units =
    baseline_cycle_demand_units + safety_stock_units

usable_inventory_position_units =
    max(
        0,
        current_usable_inventory_units
        - units_expiring_before_next_delivery
    )

net_order_units =
    max(0, target_inventory_units - usable_inventory_position_units)

recommended_order_packs =
    0
    if net_order_units == 0
    else 1 + (net_order_units - 1) // pack_size_units

recommended_order_units =
    recommended_order_packs * pack_size_units
```

The default configuration uses zero safety-stock packs for all nine products.
There are no confirmed incoming units in this baseline.

## Scenario comparison

The unchanged Phase 4A fixed scenario is the baseline. The Phase 4B policy is the
candidate. Evaluation begins on January 21 and uses identical demand, initial
inventory, warm-up delivery, FIFO behavior, and expiration rules.

Both overall and product-level summaries report:

- Total fulfilled demand units.
- Total unmet demand units.
- Stockout-event count.
- Total waste units.
- Ending inventory units.
- Total delivered units.
- Total delivered packs.

Each difference is `policy value - fixed value`. No combined score is calculated.
The comparison describes one synthetic scenario. It does not demonstrate an
optimal policy or real-world improvement.

## Privacy and phase boundary

The policy uses only approved public aliases and synthetic values. It contains no
employer, store, employee, customer, vendor, or private operational data. Phase
4B does not add machine learning, forecasting, optimization, dashboards,
deployment, or external-service behavior. Phase 5 remains separate.
