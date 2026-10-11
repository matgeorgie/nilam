# Stair and residential planning correction

The saved 30 x 50 ft, two-floor, south-facing project has been regenerated as a new revision. Its old revision remains in Undo/history.

## What was wrong

The previous validator explicitly allowed hall/stair overlap. Stair connections were inferred from intersection rather than a level approach, the renderer ignored the selected direction, and the generic partitioner stretched one parking bay to 50 ft. A connected room graph was insufficient evidence of a usable plan.

## Implemented correction

A new MODERN_DUPLEX strategy reserves a dedicated 10 x 12 ft return-stair well before allocating rooms. Separate 10 x 4 ft level landing spaces on both floors connect to a 4 ft circulation route. The half-turn landing is 4 ft deep; two flights use 18 equal risers over a 10 ft storey and eight treads per flight. Floor meshes do not cover the stairwell. Drawings, 3D meshes and exports use the same direction and stair parameters.

Parking is a road-facing 10 x 18 ft bay, separated from interior circulation. Living and dining share an open boundary; kitchen adjoins dining. Bedrooms are reached from circulation and attached bathrooms through their bedrooms. The plan rotates for all four road sides. Excess plot depth is not automatically converted into an oversized parking bay. The upper front terrace is an explicit planned outdoor space.

Hard checks reject room/stair overlap, inadequate stair geometry, missing level landings and walls blocking the stair entry. The previous hall/stair overlap exemption was removed. No bathroom was requested in the current saved brief: the resulting warning now survives saving and revalidation.

## Scope and limits

This is a constrained two-floor rectangular concept planner. It targets usable frontage 28-48 ft and depth 44-65 ft (after road orientation and setbacks), one living/dining/kitchen, one to four bedrooms, up to three requested common bathrooms, attached bathrooms, up to two balconies, optional utility, and zero or one car bay. It supports at most one ground-floor bedroom and three upstairs; some combinations still need more space and return an infeasibility error. Unsupported briefs may reach the legacy generator, but unsafe legacy stairs now fail validation rather than being saved.

This does not certify the complete design. Structural support, handrail/guard details, headroom through ceilings and roofs, local setbacks, accessibility, services, fire escape and full furniture/door-swing clearance remain for further implementation and architect review. The thin-tread 3D representation is conceptual; it is not a structural stair detail. Single-floor generation retains its prior planner.

The reasoning uses separate level landings and consistent stair dimensions as described in the official [Approved Document K](https://www.gov.uk/government/publications/protection-from-falling-collision-and-impact-approved-document-k). That source is English guidance, not an assertion of compliance with the user's local building regulations.

## Verification

- 14 planning tests passed: four road orientations, one/two/three upper bedrooms, deliberate missing-landing and overlap failures, original four-bedroom ensuite demo, single-storey no-stair case.
- Four existing model/export tests passed, for 18 passing focused backend tests in total.
- TypeScript checks passed.
- Browser workflow passed for generating the revised duplex, viewing its 2D/3D plan, and checking the upper-floor DOWN label.
- Additional metric-unit and setback example generated without hard-check failures.
- The full older backend suite is not claimed to pass; unrelated legacy failures are documented in RESEARCH-AND-CHANGES.md.

The local website contains these changes. START-HERE.md in the source ZIP explains setup and launch. The bundled model weights are unchanged by this planning correction.
