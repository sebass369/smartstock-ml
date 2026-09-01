# Configuration

This directory contains synthetic configuration for SmartStock ML Phases 2 and 3.
The YAML files use only public product aliases and generalized delivery-cycle assumptions.

## Files

- `products.yaml` defines the nine approved public product aliases, pack sizes, shelf-life assumptions, demand labels, risk labels, high-demand weekdays, and provisional fields.
- `delivery.yaml` defines the synthetic 14-day Tuesday delivery cycle, the approximate 11:00 AM to 12:00 PM delivery window, and full-pack ordering constraints.
- `generation.yaml` defines the Phase 3 start date, duration, default seed, inclusive low and high demand ranges, and high-demand-weekday adjustment.

## Synthetic modeling assumptions

All values in these files are synthetic modeling assumptions for a portfolio project.
They are not real operational records, private delivery instructions, or food-safety guidance.
Do not use these values to make real product-handling, ordering, or safety decisions.

## Provisional fields

A value listed in `provisional_fields` is not fully confirmed in `PROJECT.md`.
It is included only so future synthetic modeling can remain structured while clearly showing which assumptions need review.

Phase 3 uses only `demand_level` and `high_demand_days` from the product configuration. It does not use pack sizes or shelf-life values to calculate demand. The values are synthetic assumptions and are not operational or food-safety guidance.

## Privacy rules

Never add company names, store identifiers, addresses, exact locations, employee names, manager names, customer names, vendor names, private URLs, credentials, invoice information, real delivery records, screenshots, or internal product names to this directory.
