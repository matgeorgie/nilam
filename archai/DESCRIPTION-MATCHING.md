# Description-to-plan correction

The exact supplied two-floor, 30 x 50 ft south-road brief now creates one guest bedroom and one shared bathroom on the ground floor, plus two bedrooms, one shared bathroom and one balcony on the first floor. Living, dining and kitchen are on the ground floor, with the entry sit-out, car porch and dedicated stairwell.

Fixed three causes: the parser did not recognise guest/shared room qualifiers; floor-specific room lists were not reliably preserved; a complete design description pasted into an existing project was routed through the single-edit parser. Full design briefs now replace the old brief, while ordinary small edits retain their edit path. Unicode multiplication signs in plot dimensions are normalised. Floor-specific room-count checks now reject placements on the wrong storey.

Rejected edits explicitly say Request not applied and explain that the canvas still shows the last saved plan. The rule-based demo remains a limited parser, not a general language model. This fix verifies the supplied description; it does not claim arbitrary natural-language understanding.

Verification: 17 focused backend tests passed, including the exact description, stale-room replacement, wrong-floor rejection, the existing extraction acceptance test and the duplex planning matrix. TypeScript checks passed. Browser verification covers submitting the exact brief to new and existing projects, checking both floor plans, and displaying the rejection banner for an unsupported request.

The user's project 88ac0719-31fc-4cb2-a648-cfddbea45a79 was updated through the chat handler with the exact brief; its previous revision remains in history. Other architectural limits in PLANNING-CORRECTIONS.md still apply.
