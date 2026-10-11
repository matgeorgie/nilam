# Data workspace

Third-party datasets are intentionally not committed or downloaded automatically.

- `raw/`: immutable source archives accepted under their original licenses
- `processed/`: normalized `DatasetSample` JSON records
- `annotations/`: project-owned corrections and derived labels
- `splits/`: reproducible train/validation/test manifests

Every import must record `source`, `sample_id`, `license_reference`, units, and geometry provenance. Do not place RPLAN or other license-unclear material here. CubiCasa5K is research/non-commercial only. Review HouseExpo's upstream SUNCG provenance before commercial use. ResPlan and MSD are preferred research candidates when their distributed license and source provenance meet the intended deployment policy.
