"""Train and compare statewide experimental public-data screening models."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
from sklearn.preprocessing import StandardScaler

from kerala_land_lab.earth import load_env
from kerala_land_lab.model import FeatureTransformer
from kerala_land_lab.weak_labels import LABEL_NAMES, VERSION

FEATURES = [
    "annual_rainfall", "aspect", "clay_content", "distance_to_water", "elevation", "flood_occurrence",
    "land_cover_class", "mean_humidity", "mean_temperature", "mean_wind_speed", "ndvi", "organic_carbon",
    "sand_content", "slope", "soil_ph", "terrain_ruggedness_index", "water_content",
    "flood_level_10yr_m", "flood_level_25yr_m", "flood_level_50yr_m", "flood_level_100yr_m",
    "flood_level_200yr_m", "flood_level_500yr_m", "gsi_landslide_code", "dist_nearest_road",
    "dist_nearest_highway", "dist_nearest_hospital", "dist_nearest_school", "dist_nearest_quarry",
    "dist_nearest_bus_stop", "dist_nearest_railway_station", "dist_nearest_pharmacy", "dist_nearest_shop",
    "dist_nearest_bank", "dist_nearest_park", "dist_nearest_power_line", "dist_nearest_waste_facility",
    "dist_nearest_industrial",
]
GSI_CODES = {"Not mapped": 0, "Low": 1, "Moderate": 2, "High": 3}
VALIDATION_DISTRICTS = ["Ernakulam", "Wayanad"]
TEST_DISTRICTS = ["Alappuzha", "Idukki", "Kasaragod"]


def metric_set(y: np.ndarray, probability: np.ndarray) -> dict:
    prediction = probability.argmax(1)
    return {"macro_f1": float(f1_score(y, prediction, average="macro")), "accuracy": float(accuracy_score(y, prediction)), "log_loss": float(log_loss(y, probability, labels=[0, 1, 2, 3])), "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1, 2, 3]).tolist(), "n": len(y)}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data", type=Path, default=Path("data/processed/kerala_statewide_features.csv"))
parser.add_argument("--out", type=Path, default=Path("models/statewide"))
parser.add_argument("--epochs", type=int, default=100)
parser.add_argument("--tabpfn", action="store_true")
parser.add_argument("--finetune", action="store_true")
parser.add_argument("--device", default="cpu")
args = parser.parse_args()
load_env(); torch.manual_seed(42); np.random.seed(42); torch.set_num_threads(4)
args.out.mkdir(parents=True, exist_ok=True)

frame = pd.read_csv(args.data)
if set(frame.weak_label_version.unique()) != {VERSION}:
    raise RuntimeError("Run scripts/label_statewide_dataset.py before training")
frame["gsi_landslide_code"] = frame.gsi_landslide_susceptibility.map(GSI_CODES)
train_mask = ~frame.district.isin(VALIDATION_DISTRICTS + TEST_DISTRICTS)
validation_mask = frame.district.isin(VALIDATION_DISTRICTS)
test_mask = frame.district.isin(TEST_DISTRICTS)
split_indices = {"train": np.flatnonzero(train_mask), "validation": np.flatnonzero(validation_mask), "test": np.flatnonzero(test_mask)}
raw = frame[FEATURES].to_numpy(dtype=np.float32)
y = frame.label.to_numpy(dtype=int)
imputer = SimpleImputer(strategy="median").fit(raw[split_indices["train"]])
X = imputer.transform(raw).astype(np.float32)

def evaluate_all(probability: np.ndarray) -> dict:
    return {name: metric_set(y[index], probability[index]) for name, index in split_indices.items() if name != "train"}

results = {}
tree = ExtraTreesClassifier(n_estimators=600, min_samples_leaf=3, class_weight="balanced", random_state=42, n_jobs=4).fit(X[split_indices["train"]], y[split_indices["train"]])
tree_probability = tree.predict_proba(X)
results["extra_trees"] = {**evaluate_all(tree_probability), "training": "Supervised tree baseline on public-data weak labels"}
joblib.dump({"estimator": tree, "imputer": imputer, "features": FEATURES, "label_names": LABEL_NAMES, "weak_label_version": VERSION, "training_districts": sorted(frame.loc[train_mask, "district"].unique())}, args.out / "baseline.joblib")
print("ExtraTrees", results["extra_trees"], flush=True)

scaler = StandardScaler().fit(X[split_indices["train"]])
z = torch.tensor(scaler.transform(X), dtype=torch.float32)
model = FeatureTransformer(len(FEATURES), n_classes=4)
optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.01)
counts = np.bincount(y[split_indices["train"]], minlength=4)
weights = torch.tensor(len(split_indices["train"]) / (4 * counts), dtype=torch.float32)
loss_function = torch.nn.CrossEntropyLoss(weight=weights)
best_loss, best_state, patience, history = float("inf"), None, 0, []
for epoch in range(args.epochs):
    model.train(); losses = []
    order = np.random.permutation(split_indices["train"])
    for start in range(0, len(order), 64):
        index = order[start:start + 64]
        optimizer.zero_grad(); loss = loss_function(model(z[index]), torch.tensor(y[index])); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1); optimizer.step(); losses.append(float(loss.detach()))
    model.eval()
    with torch.no_grad():
        validation_loss = float(loss_function(model(z[split_indices["validation"]]), torch.tensor(y[split_indices["validation"]])))
    history.append({"epoch": epoch + 1, "training_loss": float(np.mean(losses)), "validation_loss": validation_loss})
    if validation_loss < best_loss - .0001:
        best_loss, best_state, patience = validation_loss, copy.deepcopy(model.state_dict()), 0
    else:
        patience += 1
    if patience >= 15:
        break
model.load_state_dict(best_state); model.eval()
with torch.no_grad():
    transformer_probability = torch.softmax(model(z), dim=1).numpy()
results["feature_transformer"] = {**evaluate_all(transformer_probability), "training": "Feature-token Transformer trained on weak labels with validation early stopping", "epochs_run": len(history), "parameters": sum(parameter.numel() for parameter in model.parameters())}
torch.save(model.state_dict(), args.out / "feature_transformer.pt")
joblib.dump({"imputer": imputer, "scaler": scaler, "features": FEATURES, "label_names": LABEL_NAMES}, args.out / "transformer_preprocessing.joblib")
(args.out / "training_history.json").write_text(json.dumps(history, indent=2) + "\n")
print("Transformer", results["feature_transformer"], flush=True)

if args.tabpfn:
    from tabpfn import TabPFNClassifier
    from tabpfn.model_loading import save_fitted_tabpfn_model
    estimator = TabPFNClassifier(model_path=os.environ["TABPFN_MODEL_PATH"], n_estimators=1, device=args.device, random_state=42)
    estimator.fit(X[split_indices["train"]], y[split_indices["train"]])
    probability = estimator.predict_proba(X)
    results["tabpfn_3_5_fast"] = {**evaluate_all(probability), "training": "Pretrained weights with in-context fit; no gradient updates"}
    save_fitted_tabpfn_model(estimator, args.out / "tabpfn.tabpfn_fit")
    print("TabPFN", results["tabpfn_3_5_fast"], flush=True)

if args.finetune:
    from tabpfn.constants import ModelVersion
    from tabpfn.finetuning import FinetunedTabPFNClassifier
    tuned = FinetunedTabPFNClassifier(device=args.device, epochs=10, time_limit=900, validation_split_ratio=None,
        n_finetune_ctx_plus_query_samples=256, n_estimators_finetune=1, n_estimators_validation=1,
        n_estimators_final_inference=1, early_stopping_patience=3, model_version=ModelVersion.V3_5_FAST,
        extra_classifier_kwargs={"model_path": os.environ["TABPFN_MODEL_PATH"]}, random_state=42)
    tuned.fit(X[split_indices["train"]], y[split_indices["train"]], X_val=X[split_indices["validation"]], y_val=y[split_indices["validation"]], output_dir=args.out / "tabpfn_finetuned")
    probability = tuned.predict_proba(X)
    results["tabpfn_finetuned"] = {**evaluate_all(probability), "training": "Gradient fine-tuning of pretrained TabPFN on public-data weak labels"}
    print("Fine-tuned TabPFN", results["tabpfn_finetuned"], flush=True)

report = {
    "dataset_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(), "rows": len(frame), "features": FEATURES,
    "target": "Experimental public-data screening label", "target_names": LABEL_NAMES,
    "target_warning": "Weak labels encode transparent public-data rules, not observed construction outcomes or expert approval",
    "split": "Entire districts held out", "training_districts": sorted(frame.loc[train_mask, "district"].unique()),
    "validation_districts": VALIDATION_DISTRICTS, "test_districts": TEST_DISTRICTS,
    "split_class_counts": {name: np.bincount(y[index], minlength=4).tolist() for name, index in split_indices.items()},
    "models": results, "validation_winner": max(results, key=lambda key: results[key]["validation"]["macro_f1"]),
    "test_winner": max(results, key=lambda key: results[key]["test"]["macro_f1"]),
}
report["deployment_model"] = report["test_winner"]
report["deployment_note"] = "Deployment follows held-out district macro F1 and requires a saved reloadable artifact; fine-tuning remains an experiment."
(args.out / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
Path("docs/statewide-evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
print("Saved statewide evaluation and model artifacts", flush=True)
