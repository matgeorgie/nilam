"""Reproduce a district-held-out comparison of Nilam's deployed and baseline models.

Run with the multimodal environment. The tabular and vision stages cache only
held-out predictions, so an interrupted TerraMind pass need not retrain trees.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from importlib.metadata import version
from pathlib import Path

# Keep the CPU TabPFN/XGBoost combination stable on local macOS OpenMP builds.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
)
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from kerala_land_lab.fusion import FusionConfig, combine_probabilities
from kerala_land_lab.weak_labels import LABEL_NAMES, VERSION

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/kerala_statewide_features.csv"
CHIPS = ROOT / "data/processed/sentinel2_chips"
CACHE = ROOT / "data/cache/model_comparison"
MODEL_DIR = ROOT / "models/comparison"
DOCS = ROOT / "docs"
VALIDATION_DISTRICTS = ("Ernakulam", "Wayanad")
TEST_DISTRICTS = ("Alappuzha", "Idukki", "Kasaragod")
ORDER = (
    "TabPFN + TerraMind", "TabPFN", "TerraMind only", "XGBoost",
    "ExtraTrees", "Random Forest", "RBF SVM", "Logistic Regression", "Majority class",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cohort():
    frame = pd.read_csv(DATA)
    if len(frame) != 1400 or not frame.point_id.is_unique:
        raise RuntimeError("The statewide cohort is not the expected 1,400 unique points")
    if set(frame.weak_label_version) != {VERSION}:
        raise RuntimeError("Weak-label version differs from the trained artifacts")
    digest = sha256(DATA)
    for report in (ROOT / "models/statewide/evaluation.json", ROOT / "models/multimodal_v2/evaluation.json"):
        if json.loads(report.read_text())["dataset_sha256"] != digest:
            raise RuntimeError(f"The dataset differs from the saved model's training cohort: {report}")
    train = frame.loc[~frame.district.isin(VALIDATION_DISTRICTS + TEST_DISTRICTS)].copy()
    study = frame.loc[frame.district.isin(VALIDATION_DISTRICTS + TEST_DISTRICTS)].copy().reset_index(drop=True)
    if len(train) != 900 or len(study) != 500:
        raise RuntimeError("Whole-district train/validation/test split changed")
    train["gsi_landslide_code"] = train.gsi_landslide_susceptibility.map({"Not mapped": 0, "Low": 1, "Moderate": 2, "High": 3})
    study["gsi_landslide_code"] = study.gsi_landslide_susceptibility.map({"Not mapped": 0, "Low": 1, "Moderate": 2, "High": 3})
    split = np.where(study.district.isin(VALIDATION_DISTRICTS), "validation", "test")
    return train, study, split, digest


def save_predictions(path: Path, study: pd.DataFrame, split: np.ndarray, digest: str, probabilities: dict[str, np.ndarray]):
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"point_id": study.point_id.to_numpy(dtype=str), "label": study.label.to_numpy(dtype=np.int64),
              "split": split, "dataset_sha256": np.array(digest)}
    for name, values in probabilities.items():
        values = np.asarray(values, dtype=np.float32)
        if values.shape != (len(study), 4) or not np.isfinite(values).all():
            raise RuntimeError(f"Invalid probability matrix for {name}: {values.shape}")
        arrays[name] = values
    np.savez_compressed(path, **arrays)


def read_predictions(path: Path, study: pd.DataFrame, split: np.ndarray, digest: str):
    with np.load(path, allow_pickle=False) as archive:
        if (archive["dataset_sha256"].item() != digest or
                not np.array_equal(archive["point_id"], study.point_id.to_numpy(dtype=str)) or
                not np.array_equal(archive["label"], study.label.to_numpy(dtype=np.int64)) or
                not np.array_equal(archive["split"], split)):
            raise RuntimeError(f"Cached predictions do not match the current cohort and split: {path}")
        return {key: archive[key] for key in archive.files if key not in {"dataset_sha256", "point_id", "label", "split"}}


def train_tabular(train: pd.DataFrame, study: pd.DataFrame, split: np.ndarray, digest: str):
    from tabpfn.model_loading import load_fitted_tabpfn_model

    bundle = joblib.load(ROOT / "models/statewide/baseline.joblib")
    features = bundle["features"]
    if len(features) != 38 or sorted(train.district.unique()) != bundle["training_districts"]:
        raise RuntimeError("Saved tabular baseline does not match the 38-feature training split")
    # The saved imputer was fitted on the nine training districts only.
    x_train = bundle["imputer"].transform(train[features].to_numpy(dtype=np.float32)).astype(np.float32)
    x_study = bundle["imputer"].transform(study[features].to_numpy(dtype=np.float32)).astype(np.float32)
    y_train = train.label.to_numpy(dtype=np.int64)
    probabilities = {}

    tabpfn = load_fitted_tabpfn_model(ROOT / "models/statewide/tabpfn.tabpfn_fit", device="cpu")
    probabilities["TabPFN"] = tabpfn.predict_proba(x_study)
    print("[tabular] TabPFN: 500 held-out predictions", flush=True)
    del tabpfn
    gc.collect()

    probabilities["ExtraTrees"] = bundle["estimator"].predict_proba(x_study)
    del bundle

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    balanced_weights = compute_sample_weight("balanced", y_train)
    xgb = XGBClassifier(
        n_estimators=450, max_depth=4, learning_rate=0.05,
        subsample=0.9, colsample_bytree=0.9, objective="multi:softprob",
        num_class=4, eval_metric="mlogloss", tree_method="hist", random_state=42, n_jobs=4,
    )
    xgb.fit(x_train, y_train, sample_weight=balanced_weights)
    probabilities["XGBoost"] = xgb.predict_proba(x_study)
    xgb.save_model(MODEL_DIR / "xgboost.json")
    print("[tabular] XGBoost trained on nine districts", flush=True)

    forest = RandomForestClassifier(
        n_estimators=500, min_samples_leaf=2, class_weight="balanced_subsample", random_state=42, n_jobs=4,
    ).fit(x_train, y_train)
    probabilities["Random Forest"] = forest.predict_proba(x_study)
    joblib.dump(forest, MODEL_DIR / "random_forest.joblib")

    scaler = StandardScaler().fit(x_train)
    z_train, z_study = scaler.transform(x_train), scaler.transform(x_study)
    svm = CalibratedClassifierCV(
        SVC(kernel="rbf", C=3, gamma="scale", class_weight="balanced", random_state=42),
        method="sigmoid", cv=5, ensemble=False,
    ).fit(z_train, y_train)
    probabilities["RBF SVM"] = svm.predict_proba(z_study)
    logistic = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42).fit(z_train, y_train)
    probabilities["Logistic Regression"] = logistic.predict_proba(z_study)
    joblib.dump({"scaler": scaler, "svm": svm, "logistic": logistic}, MODEL_DIR / "linear_and_svm.joblib")

    majority = DummyClassifier(strategy="most_frequent").fit(x_train, y_train)
    probabilities["Majority class"] = majority.predict_proba(x_study)
    save_predictions(CACHE / "tabular.npz", study, split, digest, probabilities)
    print("[tabular] saved seven comparable model predictions", flush=True)


def infer_vision(study: pd.DataFrame, split: np.ndarray, digest: str, batch_size: int):
    import torch
    from kerala_land_lab.api import load_multimodal_bundle
    from kerala_land_lab.multimodal import load_chip

    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    bundle = load_multimodal_bundle()
    baseline = joblib.load(ROOT / "models/statewide/baseline.joblib")
    if baseline["features"] != bundle["features"]:
        raise RuntimeError("TerraMind and TabPFN feature order differs")
    raw = study[bundle["features"]].to_numpy(dtype=np.float32)
    imputed = baseline["imputer"].transform(raw).astype(np.float32)
    scaled = bundle["preprocessing"]["scaler"].transform(imputed).astype(np.float32)
    network, device = bundle["network"], bundle["device"]
    parts = []
    for start in range(0, len(study), batch_size):
        end = min(start + batch_size, len(study))
        chips = torch.stack([load_chip(CHIPS / f"{point_id}.npz") for point_id in study.point_id.iloc[start:end]])
        tabular = torch.tensor(scaled[start:end], dtype=torch.float32, device=device)
        with torch.inference_mode():
            logits = network(chips.to(device), tabular)["vision"]
            parts.append(torch.softmax(logits, dim=1).cpu().numpy())
        if end % 25 == 0 or end == len(study):
            print(f"[vision] TerraMind {end}/{len(study)}", flush=True)
    save_predictions(CACHE / "vision.npz", study, split, digest, {"TerraMind only": np.concatenate(parts)})
    print("[vision] saved fine-tuned TerraMind predictions", flush=True)


def metrics(y: np.ndarray, probabilities: np.ndarray):
    prediction = probabilities.argmax(axis=1)
    precision, recall, f1, support = precision_recall_fscore_support(
        y, prediction, labels=[0, 1, 2, 3], average=None, zero_division=0,
    )
    normalized = np.clip(probabilities.astype(np.float64), 1e-7, 1)
    normalized /= normalized.sum(axis=1, keepdims=True)
    return {
        "n": int(len(y)), "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "macro_precision": float(precision.mean()), "macro_recall": float(recall.mean()),
        "macro_f1": float(f1_score(y, prediction, labels=[0, 1, 2, 3], average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y, prediction, labels=[0, 1, 2, 3], average="weighted", zero_division=0)),
        "log_loss": float(log_loss(y, normalized, labels=[0, 1, 2, 3])),
        "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1, 2, 3]).tolist(),
        "per_class": {str(index): {"name": LABEL_NAMES[index], "precision": float(precision[index]),
                                      "recall": float(recall[index]), "f1": float(f1[index]),
                                      "support": int(support[index])} for index in range(4)},
    }


def write_report(study: pd.DataFrame, split: np.ndarray, digest: str):
    tabular = read_predictions(CACHE / "tabular.npz", study, split, digest)
    vision = read_predictions(CACHE / "vision.npz", study, split, digest)
    config = FusionConfig.load(ROOT / "models/terramind_tabpfn/fusion.json")
    fused, weights = combine_probabilities(tabular["TabPFN"], vision["TerraMind only"], config)
    predictions = {"TabPFN + TerraMind": fused, **tabular, **vision}
    if set(predictions) != set(ORDER):
        raise RuntimeError(f"Unexpected model list: {sorted(predictions)}")
    results = {name: {part: metrics(study.label.to_numpy()[split == part], values[split == part])
                      for part in ("validation", "test")} for name, values in predictions.items()}
    test_mask = split == "test"
    labels = study.label.to_numpy(dtype=np.int64)[test_mask]
    tabpfn_prediction = tabular["TabPFN"][test_mask].argmax(1)
    fusion_prediction = fused[test_mask].argmax(1)
    paired = {
        "changed_predictions": int((tabpfn_prediction != fusion_prediction).sum()),
        "tabpfn_only_correct": int(((tabpfn_prediction == labels) & (fusion_prediction != labels)).sum()),
        "fusion_only_correct": int(((fusion_prediction == labels) & (tabpfn_prediction != labels)).sum()),
    }
    report = {
        "dataset_sha256": digest, "rows": 1400, "feature_count": 38,
        "training_districts": sorted(set(pd.read_csv(DATA).district) - set(VALIDATION_DISTRICTS + TEST_DISTRICTS)),
        "validation_districts": list(VALIDATION_DISTRICTS), "test_districts": list(TEST_DISTRICTS),
        "split_counts": {part: int(sum(split == part)) for part in ("validation", "test")},
        "class_names": LABEL_NAMES, "model_order": ORDER,
        "fusion_config": json.loads((ROOT / "models/terramind_tabpfn/fusion.json").read_text()),
        "mean_vision_weight_test": float(weights[split == "test"].mean()),
        "fusion_vs_tabpfn": paired,
        "artifact_sha256": {
            "tabpfn_fit": sha256(ROOT / "models/statewide/tabpfn.tabpfn_fit"),
            "terramind_checkpoint": sha256(ROOT / "models/multimodal_v2/terramind_tabular_fusion.pt"),
            "fusion_config": sha256(ROOT / "models/terramind_tabpfn/fusion.json"),
        },
        "versions": {name: version(name) for name in ("xgboost", "scikit-learn", "tabpfn", "torch")},
        "method": "Saved TabPFN and TerraMind artifacts; fixed fusion config; classical baselines fitted on nine training districts only; same 300 district-held-out test points",
        "limitations": "Labels are deterministic public-data screening rules derived largely from the tabular inputs, not expert-reviewed construction outcomes. The test districts have been reported in earlier development, so this is a retrospective comparison rather than a fresh confirmatory holdout.",
        "models": results,
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "model-comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    columns = ["model", "n", "accuracy", "balanced_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1", "log_loss"]
    rows = [{"model": name, **{key: results[name]["test"][key] for key in columns[1:]}} for name in ORDER]
    pd.DataFrame(rows).to_csv(DOCS / "model-comparison.csv", index=False, float_format="%.6f")
    markdown = [
        "# Land-suitability model comparison", "",
        "**Target:** four-class experimental public-data screening label. These are not verified building outcomes or probabilities that a house is safe.", "",
        "**Evaluation:** 1,400 points (100 per Kerala district); train on 900 points from nine districts, use 200 points from Ernakulam and Wayanad for validation, and report the same 300 test points from Alappuzha, Idukki and Kasaragod for every model. All tabular models use the same 38 mapped features. TerraMind additionally reads dry- and monsoon-season Sentinel-2 chips. No test row is used to fit the new baselines. The fusion weights were already selected on validation data.", "",
        "| Model | Accuracy | Balanced accuracy | Macro precision | Macro recall | Macro F1 | Weighted F1 | Log loss |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ORDER:
        value = results[name]["test"]
        markdown.append("| " + name + " | " + " | ".join(f"{value[key]*100:.1f}%" for key in ("accuracy", "balanced_accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1")) + f" | {value['log_loss']:.3f} |")
    markdown.extend([
        "", "Macro precision, recall and F1 average the four classes equally; weighted F1 gives more influence to common classes. Balanced accuracy is the mean class recall. Higher is better except for log loss.",
        "", f"On these 300 points, TabPFN alone has {100*(results['TabPFN']['test']['macro_f1']-results['TabPFN + TerraMind']['test']['macro_f1']):.2f} percentage points higher macro F1 than fusion. Fusion changed {paired['changed_predictions']} predictions: {paired['fusion_only_correct']} became correct and {paired['tabpfn_only_correct']} became incorrect. Satellite fusion therefore does not improve reproduction of these rule-derived labels.",
        "", "The current app uses the **TabPFN + TerraMind** row. It geometrically blends class probabilities with a fixed 8% TerraMind weight and 92% TabPFN weight. The **TerraMind only** row evaluates its fine-tuned vision head, not the earlier learned multimodal gate.",
        "", "## Per-class F1 on the test districts", "",
        "| Model | Screen out | Low | Moderate | Higher |",
        "|---|---:|---:|---:|---:|",
    ])
    for name in ("TabPFN + TerraMind", "TabPFN", "XGBoost", "ExtraTrees"):
        classes = results[name]["test"]["per_class"]
        markdown.append("| " + name + " | " + " | ".join(f"{classes[str(index)]['f1']*100:.1f}%" for index in range(4)) + " |")
    markdown.extend([
        "", "## Interpretation and limits", "",
        "The labels are calculated from public-data rules that use many of the 38 tabular inputs. High scores therefore mainly show that a model reproduces those rules, not that it can identify safe, vacant or legally buildable plots. TerraMind's image branch has an inherent disadvantage on this target because the target was not labelled from satellite images. The test districts have appeared in prior development reports, so this is a retrospective comparison and should not be presented as a fresh confirmatory result. Independent expert labels and a new spatial holdout are needed for claims about real-world suitability.",
        "", "Reproduce with `PYTORCH_ENABLE_MPS_FALLBACK=1 .venv-multimodal/bin/python scripts/evaluate_model_comparison.py --stage all`. The script checks the dataset SHA-256, point IDs and split before combining predictions. Full per-class metrics and confusion matrices are in `docs/model-comparison.json`.", "",
    ])
    (DOCS / "model-comparison.md").write_text("\n".join(markdown))
    print("[report] wrote docs/model-comparison.{md,csv,json}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "tabular", "vision", "report"), default="all")
    parser.add_argument("--batch-size", type=int, default=1, help="TerraMind chip batch size")
    args = parser.parse_args()
    train, study, split, digest = load_cohort()
    if args.stage in ("all", "tabular"):
        train_tabular(train, study, split, digest)
    if args.stage in ("all", "vision"):
        infer_vision(study, split, digest, args.batch_size)
    if args.stage in ("all", "report"):
        write_report(study, split, digest)


if __name__ == "__main__":
    main()
