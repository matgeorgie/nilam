# Nilam
<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
React frontend with a Python API. Google Maps provides the basemap, place search, drawing context, and optional Street View. Python owns geospatial processing, the TerraMind + TabPFN assessment pipeline, candidate search, Laya preference interpretation, and local speech transcription.

## Users
People evaluating a known site in Kerala for building a house, and people who know their household needs but still need to find promising candidate areas. The creator also needs a technically substantial academic demonstration of multimodal training, geographic evaluation, and explainability.

## Product Purpose
Support two linked decisions across Kerala's 14 districts: assess a known point or drawn site boundary, or describe desired surroundings and rank candidate zones within a district, drawn search area, or the visible map region. Every path keeps suitability, personal fit, evidence, explanation, and unknowns distinct.

## Capabilities and Constraints
The assessment workspace accepts a Google place result, map click, point, or drawn polygon. It returns mapped TabPFN evidence first, then seasonal TerraMind satellite evidence, calibrated fusion, and conditional SHAP explanation as each stage becomes available. Street View is optional visual context, never assessment evidence.

The land-matcher workspace accepts typed or locally transcribed English requests. Laya converts the request into reviewable, editable filters; always-on mapped water, high-flood, and high-landslide safeguards remain visible. Search may use a district, a custom drawn boundary, or 25 km around the map centre. Candidate rows keep model suitability, preference fit, and combined rank separate, support a local shortlist, and can reopen a candidate for full TerraMind verification.

The product remains public-data-first and experimental. Expert-reviewed suitability labels may become available later. Preserve reproducible experiments and changes in matgeorgie/nilam. Do not equate historical hazard susceptibility, candidate rank, Street View imagery, or model output with permission or advice to build or buy. Soil bearing capacity, title, planning compliance, utility connections, crime, affordability, and on-site drainage still require independent evidence.

## Evidence on Hand
KSDMA historical flood layers in 14 district KMZ files and a landslide KML with low/medium/high classes. Source archives are locally retained with hashes; redistribution license is not established. The statewide study uses 1,400 points, 38 mapped terrain, hazard, and access features, dry- and monsoon-season 12-band Sentinel-2 chips, and five held-out districts. The current interface reports 0.850 TabPFN test macro-F1 and 0.847 calibrated-fusion test macro-F1 on weak labels; TerraMind therefore receives a validation-calibrated 8% influence rather than being presented as the stronger branch. These are research metrics, not safety validation.

## Product Principles
- Evidence and predictions have distinct labels.
- Unknown values never silently become safe values.
- Evaluation must separate geographic areas and avoid target leakage.
- Every assessment exposes provenance and limitations.
- Progressive results label what is ready, what is still running, and what changed the final estimate.
- Suitability, personal preference fit, and combined candidate rank remain separate values.
- Natural-language and voice interpretation always resolves to visible, editable requirements before search.
- A ranked candidate is a screening lead; users return to the assessment workspace to inspect its evidence.

## Brand Commitments
Nilam, matching the user's repository name. The product uses a Kerala field-report visual language: warm paper, deep green structure, square survey controls, compact evidence typography, and rust only for constraints, failures, or cautions.
