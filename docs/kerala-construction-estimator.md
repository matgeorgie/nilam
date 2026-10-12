# Kerala house-construction estimator

The **Cost estimate** action appears after a home design has been saved in ArchAI. It reads the project's current revision through `GET /api/projects/{id}/estimate`; the budget is recomputed after a room/layout revision and is never used as a land-suitability input. For a design started from Nilam, the district comes from its saved `site_context`. A standalone design starts at the Kerala average and the user can select any of the 14 districts. Finish choice is a scenario control, not inferred from a visual style such as “modern.”

## Calculation

The estimator unions each floor's enclosed room polygons, so overlapping rooms do not double-count. It adds **up to 10%** to usable room area as a wall/gross-area allowance, capped so the priced enclosed area plus semi-open space cannot exceed the saved footprint. The actual allowance used is returned in the API. Porches, verandas, balconies and parking are measured separately after subtracting their overlap with enclosed rooms, then priced at 45% of the selected residential rate. These are explicit concept-stage assumptions, not measured wall/roof/column quantities.

| Finish | Low | Midpoint | High |
| --- | ---: | ---: | ---: |
| Essential | ₹1,800/ft² | ₹2,000/ft² | ₹2,200/ft² |
| Standard | ₹2,200/ft² | ₹2,500/ft² | ₹2,800/ft² |
| Premium | ₹3,000/ft² | ₹3,750/ft² | ₹4,500/ft² |

These are indicative 2026 Kerala residential package bands published by [Mezmerix Builders](https://mezmerix.in/blog-house-construction-cost-kerala), cross-checked against [K Jasons](https://kjasons.com/2026/08/29/house-construction-cost-in-kerala-2026/). They describe ordinary structure, roofing, wiring, plumbing and finishes at the chosen level, but no contract scope is implied.

The district adjustment is a weighted index against the 14-district mean of the **Kerala Directorate of Economics & Statistics [Q4 2025–26 material prices and wages](https://ecostat.kerala.gov.in/storage/publications/1918.pdf)**. It uses daily wages for mason, carpenter, plumber, electrician and unskilled labour (35% collectively); a 50 kg high-strength cement bag (20%); 12 mm TMT bar (25%); and 6-inch AAC blocks (20%). The resulting multiplier is capped at ±8% because input prices are a proxy, not a district turnkey-price survey. These weighting and cap choices are model assumptions, not Kerala government recommendations. **Do not use the DES Building Construction Cost Index to compare districts**: each district series uses its own 2011–12 baseline, so a cross-district ratio would be misleading.

The construction amount is `equivalent_area × finish_rate × district_factor`, plus a 3% allowance for non-rectangular plans and planning fit-out allowances of ₹50,000 per bathroom beyond two and ₹1,00,000 per kitchen beyond one. A 12% reserve gives the displayed planning budget. The low/high range repeats the computation at the low/high package rates, including the reserve. Shape, wall, semi-open, fit-out and reserve factors are provisional assumptions; the published sources do not establish precise quantities for an individual design.

## Boundaries

This is a **concept-stage budget** for comparing the user's own design scenarios. It is not a bill of quantities, loan valuation, tender price or contractor quotation. It does not know soil bearing capacity, exact structural spans and steel quantities, roof construction, site access, flood-related floor raising, excavation, retaining walls, permit/professional fees, utility connections, taxes or land cost. A local architect/engineer and contractors should price these against approved drawings, a geotechnical report and a stated materials specification. Regional inputs and package bands should be refreshed before use in later years.

Core implementation: `archai/apps/api/app/cost_estimator.py` and `archai/apps/web/app/workspace/[id]/estimate/page.tsx`. Targeted tests: `archai/apps/api/tests/test_cost_estimator.py` and `test_nilam_integration.py`.
