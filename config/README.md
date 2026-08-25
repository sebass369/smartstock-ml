# Configuration

This directory contains synthetic configuration for SmartStock ML Phase 2.
The YAML files use only public product aliases and generalized delivery-cycle assumptions.

## Files

- `products.yaml` defines the nine approved public product aliases, pack sizes, shelf-life assumptions, demand labels, risk labels, high-demand weekdays, and provisional fields.
- `delivery.yaml` defines the synthetic 14-day Tuesday delivery cycle, the approximate 11:00 AM to 12:00 PM delivery window, and full-pack ordering constraints.

## Synthetic modeling assumptions

All values in these files are synthetic modeling assumptions for a portfolio project.
They are not real operational records, private delivery instructions, or food-safety guidance.
Do not use these values to make real product-handling, ordering, or safety decisions.

## Provisional fields

A value listed in `provisional_fields` is not fully confirmed in `PROJECT.md`.
It is included only so future synthetic modeling can remain structured while clearly showing which assumptions need review.

## Privacy rules

Never add company names, store identifiers, addresses, exact locations, employee names, manager names, customer names, vendor names, private URLs, credentials, invoice information, real delivery records, screenshots, or internal product names to this directory.
