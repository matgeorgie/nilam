# Nilam academic research roadmap

## Current study

Nilam is a reproducible statewide public-data screening experiment. It samples 100 locations in each Kerala district, derives 38 terrain, soil, climate, water, hazard, access and amenity features, compares four model variants, and holds out entire districts to measure geographic transfer. The deployed TabPFN model reached 0.845 macro-F1 on the experimental weak target. Permutation SHAP explains the displayed ordinal suitability score in percentage points.

The current target is weak supervision built from public geospatial evidence. It must not be presented as observed construction safety.

## High-value research extensions

### 1. Expert-label active learning

Ask civil, geotechnical and planning experts to label an initial 200–400 diverse sites. Select each new review batch with uncertainty sampling and geographic diversity. Compare the expert model against the weak-label model and report inter-rater agreement. This is the most important step because it changes the target from encoded rules to expert evidence.

### 2. Multimodal geospatial foundation model

Extract seasonal Sentinel-2 optical and Sentinel-1 SAR image chips around every site. Fine-tune a geospatial encoder such as Clay, Prithvi or SatMAE, then fuse its embedding with the 38 tabular features using gated cross-attention. Test whether imagery adds accuracy beyond TabPFN using district-held-out ablations.

### 3. Monsoon-aware temporal risk

Build a temporal branch from IMD/CHIRPS rainfall history, Sentinel-1 flood observations and soil moisture. Predict dry-season and peak-monsoon suitability separately. This turns a static score into a seasonal risk profile.

### 4. Drainage and access graph neural network

Represent streams, roads and settlements as a heterogeneous graph. Train a graph model to estimate drainage connectivity, emergency access and isolation during flooding. Fuse the graph embedding with the site model.

### 5. Calibrated uncertainty and conformal prediction

Calibrate probabilities on held-out districts and produce conformal prediction sets. The interface should show when several classes remain plausible and abstain when the site is outside the training distribution. Measure empirical coverage separately for coastal, midland and highland terrain.

### 6. Parcel and mobile field evidence

Add parcel-boundary ingestion and a mobile capture flow for geotagged photos, slope views, drainage, road width and visible utilities. Fine-tune a vision encoder only after a consented, quality-controlled field dataset exists. Use image evidence as a separate channel with provenance rather than silently merging it into the public-data score.

## Evaluation protocol

Use nested spatial cross-validation, district and watershed holdouts, class-balanced macro-F1, ordinal mean absolute error, Brier score, calibration error and conformal coverage. Publish feature, imagery and graph ablations. Track performance by terrain zone and district. Maintain an external expert-reviewed test set that never participates in weak-label construction or model selection.

## Thesis-grade experiment sequence

1. Baseline: ExtraTrees and weak-label rules.
2. Tabular transformer: feature-token Transformer and TabPFN.
3. Uncertainty: calibration, conformal sets and out-of-distribution detection.
4. Multimodal fusion: satellite encoder plus tabular model.
5. Expert active learning: label-efficiency curve and inter-rater analysis.
6. Field validation: compare predictions with soil tests, planning decisions and observed site conditions.
