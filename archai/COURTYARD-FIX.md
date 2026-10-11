# Single-floor courtyard fix

The exact supplied 50 x 60 ft north-road courtyard prompt now generates 3 bedrooms, 2 shared bathrooms, living, dining, kitchen, utility, front sit-out and one car bay, all on one floor. A real 14 x 18 ft courtyard hole remains open, with a continuous circulation ring and a door into the courtyard. No staircase is generated.

The original failure combined an unsupported single-storey courtyard partition with missed shared-bathroom wording. The fallback Bedrooms: 4 control was already ignored when text was entered; it is now disabled and explained. Single-floor full briefs also use the replacement-brief path correctly.

This is a constrained measured profile: a north-road rectangular plot, usable width at least 48 ft and depth at least 58 ft, exactly this room mix, no attached bathrooms, no custom shape parameters or exact room dimensions. Explicit minimum areas are checked. Larger plots do not force unlimited room stretching. Unsupported briefs still require the general planner or a different profile. This is conceptual geometry, not construction approval.

A stale backend also prevented early browser verification from loading the new code. Startup and shutdown now record the actual server process IDs, verify process identity before stopping, and check listening ports without the previously blocked WMI calls. A complete stop/start cycle was verified with the new API schema and a responding frontend.

Verification: 17 focused backend tests passed (courtyard prompt, description matching, duplex regression cases). TypeScript passed. The actual New Project wizard succeeded with its original fallback defaults, preserved 3 bedrooms and 2 bathrooms, navigated to the workspace and displayed 2D and 3D views. The courtyard is excluded from room polygons and floor slabs. Its access door is distinguished from the external road entrance.

Ready project: 7636105a-a459-49c1-8ec0-84c61355dfce, titled Courtyard home - 50 x 60 ft.
