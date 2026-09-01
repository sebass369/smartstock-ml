# SmartStock ML Project Specification

## 1. Project overview

SmartStock ML is a privacy-safe Python portfolio project about retail inventory planning.
The project will use only synthetic and anonymized data.
It will study how product demand, stockouts, waste, and 14-day delivery cycles affect ordering decisions.

The project is for learning Python, software engineering, data analysis, testing, and machine learning.
Clear and explainable methods are preferred over unnecessary complexity.

## 2. Problem statement

A retail location receives a product delivery every 14 days.
The delivery normally arrives on Tuesday between approximately 11:00 AM and 12:00 PM.

Demand changes by product and by day of the week.
Some products may run out before the next delivery.
Other products may expire and be discarded.

The future system should help estimate how much of each product should be ordered for the next 14-day delivery cycle.
The system should balance two important risks:

- Stockouts, where demand cannot be fulfilled because inventory is unavailable.
- Waste, where product expires or is discarded before it can be used.

## 3. Version 1 objective

The Version 1 objective is to build a small, explainable foundation for future inventory analysis.
Version 1 will define the project scope, product assumptions, delivery assumptions, data definitions, expected inputs, expected outputs, and success metrics.

Future phases will use this specification to create configuration files, synthetic data, inventory simulation, baseline ordering logic, tests, notebooks, and simple forecasting.

## 4. Version 1 product scope

Version 1 contains exactly nine products.
The public product aliases below are the only approved product names for Version 1.
Do not add a tenth product in Version 1.
Do not include donut waste in Version 1.

| Product alias | Pack size | Open shelf life | Unopened shelf life | Demand pattern or level | Main risk or note |
| --- | ---: | --- | --- | --- | --- |
| Milk_Product_A | 4 units | 7 days | Approximately 90 days | Highest demand on Monday | Main risk is stockout. |
| Milk_Product_B | 6 units | 7 days | Approximately 60 days | Highest demand from Monday through Wednesday | Main risk is stockout. |
| Whole_Milk | 4 units | Dispenser shelf life after opening is 3 days | Approximately 60 days | High demand | The dispenser may be refilled approximately every 3 hours during busy periods. This refill frequency is an operational signal, not a known consumption quantity. |
| Fruit_Refresher_A | 8 units | 7 days | Approximately 60 days | Highest demand on Tuesday and Wednesday | Main risk is stockout. |
| Fruit_Refresher_B | 8 units | 7 days | Approximately 60 days | Highest demand on Tuesday and Wednesday | Main risk is stockout. |
| Cold_Foam_A | 6 units | Approximately 14 days | Approximately 60 days | High demand | Main risk is not yet finalized. |
| Whipped_Topping | Provisional: 6 units | Provisional: approximately 14 days | Provisional: approximately 60 days | High demand | Pack size and shelf-life values require confirmation. |
| Skim_Milk | 4 units | Dispenser shelf life after opening is 3 days | Approximately 60 days | Low demand | Fewer dispenser refills than Whole_Milk. Main risk is waste. |
| Oat_Beverage | 4 units | 7 days | Approximately 90 days | Low demand | Main risk is waste. |

## 5. Delivery-cycle assumptions

- Deliveries occur every 14 days.
- The regular delivery day is Tuesday.
- The regular delivery window is approximately 11:00 AM to 12:00 PM.
- The 14-day cycle starts on delivery day.
- Recommended order quantities must cover the next 14-day delivery cycle.
- Recommended orders must be expressed in full packs.
- Recommended orders must respect each product's pack size.
- Delivery timing is a generalized assumption for synthetic modeling, not private operational guidance.

## 6. Privacy and synthetic-data rules

The public repository must use only synthetic and anonymized data.
No real operational records may be committed.

Never include:

- Company names.
- Store numbers.
- Employee names.
- Manager names.
- Customer names.
- Vendor names.
- Addresses.
- Exact locations.
- Real invoices.
- Real delivery documents.
- Internal screenshots.
- Credentials, tokens, secrets, or private URLs.

Use only public product aliases listed in this specification.
Real operational information may only be represented as generalized assumptions.
Synthetic values must not be presented as real business records.

## 7. Important data definitions

All numeric values in the project must be zero or positive.
Inventory, demand, usage, waste, and order quantities must never be negative.

- **Demand**: The number of units customers or operations would need for a product during a time period, before inventory limits are applied.
- **Units used**: The number of physical units removed from available inventory during a time period.
- **Fulfilled demand**: The part of demand that was successfully served from available inventory.
- **Unmet demand**: The part of demand that could not be served because there was not enough available inventory.
- **Ending inventory**: The number of usable units remaining at the end of a time period after deliveries, usage, and waste are applied.
- **Expired units**: Units that pass their modeled shelf-life limit and are no longer usable.
- **Waste**: Units discarded because they expired or otherwise could not be used under the synthetic rules.
- **Stockout event**: A product-day or product-period where demand is greater than available inventory and unmet demand is greater than zero.
- **Recommended order quantity**: The suggested number of units to order for the next 14-day delivery cycle. This must be rounded to full packs and must respect the product pack size.

Demand, fulfilled demand, units used, unmet demand, expired units, and waste must remain separate concepts.
Units used must not exceed available inventory.
Inventory balance must be preserved from one day to the next.

## 8. Version 1 inputs

Version 1 should eventually use these input categories:

- Public product aliases.
- Product pack sizes.
- Product shelf-life assumptions.
- Product demand pattern assumptions.
- Product risk labels, such as stockout risk or waste risk.
- Delivery cycle length.
- Delivery day and approximate delivery window.
- Synthetic starting inventory values.
- Synthetic daily demand assumptions.
- A configurable random seed for reproducible synthetic data.

These inputs are future implementation requirements.
They are not implemented in Phase 1.

## 9. Version 1 outputs

The future Version 1 system should eventually produce:

- Synthetic daily inventory records.
- A 14-day demand estimate.
- Recommended order quantities in full packs.
- Estimated stockout risk.
- Estimated waste risk.
- A product-level summary.
- Overall metrics for fulfilled demand, unmet demand, waste, and stockouts.

These outputs are documented here for planning only.
They must not be implemented during this specification task.

## 10. Success metrics

Future phases should evaluate the system with simple and explainable metrics.
Possible Version 1 metrics include:

- Total fulfilled demand.
- Total unmet demand.
- Number of stockout events.
- Stockout rate by product.
- Total waste.
- Waste rate by product.
- Ending inventory by product.
- Recommended order quantity by product.
- Number of full packs recommended by product.

The first baseline should be simple before any advanced machine-learning model is used.

## 11. Non-goals

The following items are outside the Phase 1 scope:

- Python package implementation.
- Product configuration files.
- Delivery configuration files.
- Synthetic data generation.
- Inventory simulation.
- Ordering optimization.
- Forecasting models.
- Dashboards.
- Google Colab notebooks.
- Real operational data import.
- Real invoice processing.
- Donut waste analysis.
- Public release recommendation.

Forecasting, optimization, and dashboards must not be implemented during Phase 1.

## 12. Development phases

Development must follow a controlled sequence:

1. **Phase 1: Project specification and Python repository foundation**
   - Define the project specification.
   - Create the basic Python project foundation in a later approved task.
   - Do not implement forecasting, optimization, dashboards, or synthetic-data generation in this phase.
2. **Phase 2: Product and delivery configuration**
   - Add approved product and delivery assumptions to configuration files.
3. **Phase 3: Deterministic synthetic-data generator**
   - Generate reproducible synthetic daily demand scenarios with a configurable random seed.
   - Produce only dates, weekdays, approved aliases, high-demand-day flags, demand units, and delivery-event flags.
   - Do not simulate inventory, fulfillment, waste, expiration, stockouts, or ordering behavior.
4. **Phase 4: Inventory simulation and baseline ordering policy**
   - Simulate inventory balance, stockouts, waste, and a simple baseline ordering policy.
5. **Phase 5: Tests and validation**
   - Validate data rules, inventory balance, non-negative values, and pack-size constraints.
6. **Phase 6: Exploratory analysis notebook**
   - Use Google Colab for demonstrations and visual analysis while keeping business logic in reusable Python code.
7. **Phase 7: Simple forecasting model**
   - Add a simple forecasting model after the baseline and validation rules are working.
8. **Phase 8: Portfolio documentation and optional dashboard**
   - Improve public documentation and consider an optional dashboard only after the earlier phases are complete.

## 13. Known assumptions and open questions

Known assumptions:

- The delivery cycle is 14 days.
- The regular delivery day is Tuesday.
- The regular delivery window is approximately 11:00 AM to 12:00 PM.
- All data in the public repository will be synthetic or anonymized.
- Product aliases in this file are public placeholders.
- Donut waste is excluded from Version 1.
- Version 1 includes exactly nine products.

Provisional assumptions that require confirmation:

- Whipped_Topping pack size is provisionally 6 units.
- Whipped_Topping open shelf life is provisionally approximately 14 days.
- Whipped_Topping unopened shelf life is provisionally approximately 60 days.
- Cold_Foam_A main risk is not yet finalized.
- Oat_Beverage high-demand weekdays are not yet finalized.

Open questions:

- What synthetic starting inventory should be used for each product?
- How should refill observations be converted into safe synthetic assumptions without treating them as exact consumption quantities?
- What target balance between stockout risk and waste risk should the baseline ordering policy use?
- What validation thresholds should define an acceptable synthetic dataset?

## 14. Definition of done for Phase 1

Phase 1 is done when:

- `PROJECT.md` defines the project scope and acceptance criteria in clear English.
- The repository has a basic Python project foundation after a later approved setup task.
- No private operational information is added.
- The project uses only public product aliases.
- The Version 1 scope contains exactly nine products.
- Donut waste is excluded from Version 1.
- Forecasting, optimization, dashboards, notebooks, datasets, and production code are not implemented during the specification-only task.
- Known assumptions and open questions are documented.
- The repository is ready for the next approved phase.

## 15. Approved Phase 3 synthetic demand assumptions

Phase 3 uses a fixed synthetic start date of January 7, 2025 and generates 56 days for exactly nine approved product aliases. The default random seed is 42. Low-demand products use inclusive integer values from 0 through 2. High-demand products use inclusive integer values from 3 through 6. A product receives exactly one additional demand unit when the generated weekday appears in its configured `high_demand_days` list.

The generator marks a delivery event on the first date and every 14 days afterward. A delivery event describes the configured calendar cycle only; it does not add inventory or describe a delivery quantity.

The Phase 3 CSV contract contains exactly these columns: `date`, `weekday`, `product_id`, `is_high_demand_day`, `demand_units`, and `delivery_event`. The default output contains 504 synthetic records. Generated CSV files are reproducible artifacts and are not committed.

`demand_units` is a future prediction target. It must not be used as an input feature for a model that predicts demand for the same row. Phase 3 does not implement machine learning or forecasting.
