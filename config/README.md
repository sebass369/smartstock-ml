# Configuration

This directory contains synthetic configuration for SmartStock ML Phases 2 through 4A.
The YAML files use only public product aliases and generalized delivery-cycle assumptions.

## Files

- `products.yaml` defines the nine approved public product aliases, pack sizes, shelf-life assumptions, demand labels, risk labels, high-demand weekdays, and provisional fields.
- `delivery.yaml` defines the synthetic 14-day Tuesday delivery cycle, the approximate 11:00 AM to 12:00 PM delivery window, and full-pack ordering constraints.
- `generation.yaml` defines the Phase 3 start date, duration, default seed, inclusive low and high demand ranges, and high-demand-weekday adjustment.
- `inventory.yaml` defines fixed synthetic starting inventory and delivery pack counts for the nine approved aliases. Pack sizes remain defined only in `products.yaml`.

## Synthetic modeling assumptions

All values in these files are synthetic modeling assumptions for a portfolio project.
They are not real operational records, private delivery instructions, or food-safety guidance.
Do not use these values to make real product-handling, ordering, or safety decisions.

## Provisional fields

A value listed in `provisional_fields` is not fully confirmed in `PROJECT.md`.
It is included only so future synthetic modeling can remain structured while clearly showing which assumptions need review.

Phase 3 uses only `demand_level` and `high_demand_days` from the product configuration. It does not use pack sizes or shelf-life values to calculate demand. The values are synthetic assumptions and are not operational or food-safety guidance.

The Phase 3 generator supports only `low` and `high` demand levels. `medium` is unsupported, and `unknown` cannot be processed by the generator. The broader Phase 2 configuration validator may retain `unknown` for incomplete or future configuration.

Phase 4A directly uses `pack_size_units` and `unopened_shelf_life_days`, so those fields cannot remain provisional. It does not use open shelf life or primary risk. The already validated Phase 3 demand records may reflect provisional high-demand weekdays; that approved limitation remains explicit in `products.yaml`.

Starting inventory may be any nonnegative integer and does not need to be a pack multiple. Delivery pack counts are fixed nonnegative integers used on every scheduled delivery date. They are synthetic scenario inputs, not ordering recommendations.

## Privacy rules

Never add company names, store identifiers, addresses, exact locations, employee names, manager names, customer names, vendor names, private URLs, credentials, invoice information, real delivery records, screenshots, or internal product names to this directory.
