# Nilam
<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
React frontend with a Python API. Google Maps provides the basemap, place search, drawing context, and optional Street View. Python owns geospatial processing, the TerraMind + TabPFN assessment pipeline, candidate search, Laya preference interpretation, and local speech transcription.

## Users
People evaluating a known site in Kerala for building a house, and people who know their household needs but still need to find promising candidate areas. The creator also needs a technically substantial academic demonstration of multimodal training, geographic evaluation, and explainability.

## Product Purpose
Support two clearly separated decisions across Kerala's 14 districts: assess a known point or drawn site boundary, or choose a centre and radius and rank fresh candidate cells that match desired surroundings.

## Capabilities and Constraints
The assessment workspace accepts a Google place result, map click, device location, point, or drawn polygon. It shows local terrain and amenity facts while TabPFN and seasonal TerraMind run, then reveals only the calibrated fused percentage and conditional SHAP explanation. Street View is optional visual context, never assessment evidence.

The land-matcher workspace starts with a point and a 1–15 km radius. It accepts typed or locally transcribed English requests, while an inline Laya activity state shows when System 1 interpretation is active. Each run sends roughly 1,600 fresh cells to an Earth Engine first-stage screen for recent Dynamic World open/built probability and 45 m SRTM flatness. Cells with water or other non-buildable cover, uneven terrain, built-up evidence, or a mapped building within 30 m are removed before official hazards, amenity distances, and TabPFN plus explicit preference fit are evaluated. Up to 20 top-ranked cell footprints appear on the map; selecting one opens its site details, a nearby outdoor Street View panorama aimed toward the cell, or a full multimodal assessment.

The product remains public-data-first and experimental. Expert-reviewed suitability labels may become available later. Preserve reproducible experiments and changes in matgeorgie/nilam. Do not equate historical hazard susceptibility, candidate rank, Street View imagery, or model output with permission or advice to build or buy. Soil bearing capacity, title, planning compliance, utility connections, crime, affordability, and on-site drainage still require independent evidence.

## Evidence on Hand
KSDMA historical flood layers in 14 district KMZ files and a landslide KML with low/medium/high classes. Source archives are locally retained with hashes; redistribution license is not established. The statewide study uses 1,400 points, 38 mapped terrain, hazard, and access features, dry- and monsoon-season 12-band Sentinel-2 chips, and five held-out districts. The current interface reports 0.850 TabPFN test macro-F1 and 0.847 calibrated-fusion test macro-F1 on weak labels; TerraMind therefore receives a validation-calibrated 8% influence rather than being presented as the stronger branch. These are research metrics, not safety validation.

## Product Principles
- Evidence and predictions have distinct labels.
- Unknown values never silently become safe values.
- Evaluation must separate geographic areas and avoid target leakage.
- Progressive assessment explains what is running without exposing an interim percentage that could be mistaken for the final fused result.
- Suitability, personal preference fit, and combined candidate rank remain separate values.
- Natural-language and local voice input feed the matching search directly.
- A ranked candidate is a screening lead; users return to the assessment workspace to inspect its evidence.

## Brand Commitments
Nilam, matching the user's repository name. The product uses a modern Kerala land-intelligence visual language: soft field neutrals, deep green structure, restrained rounded controls, compact evidence typography, and rust only for constraints or failures.
