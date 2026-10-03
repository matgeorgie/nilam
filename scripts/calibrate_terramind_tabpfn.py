"""Calibrate and quality-gate TerraMind + TabPFN late fusion.

This reuses the trained TerraMind vision head and fitted TabPFN artifact. It
learns only two transparent mixture weights on the validation districts, then
reports the untouched district test result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score, log_loss

from kerala_land_lab.api import load_multimodal_bundle, load_statewide_baseline, load_statewide_tabpfn
from kerala_land_lab.fusion import FusionConfig, combine_probabilities
from kerala_land_lab.multimodal import load_chip


VALIDATION_DISTRICTS = ["Ernakulam", "Wayanad"]
TEST_DISTRICTS = ["Alappuzha", "Idukki", "Kasaragod"]


def metrics(labels, probabilities):
    predicted = probabilities.argmax(1)
    return {
        "macro_f1": float(f1_score(labels, predicted, average="macro")),
        "accuracy": float(accuracy_score(labels, predicted)),
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1, 2, 3])),
        "n": int(len(labels)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed/kerala_statewide_features.csv"))
    parser.add_argument("--chips", type=Path, default=Path("data/processed/sentinel2_chips"))
    parser.add_argument("--out", type=Path, default=Path("models/terramind_tabpfn/fusion.json"))
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()

    frame = pd.read_csv(args.data)
    frame["gsi_landslide_code"] = frame.gsi_landslide_susceptibility.map({"Not mapped": 0, "Low": 1, "Moderate": 2, "High": 3})
    mask = frame.district.isin(VALIDATION_DISTRICTS + TEST_DISTRICTS)
    study = frame.loc[mask].reset_index(drop=True)
    bundle = load_statewide_baseline()
    raw = study[bundle["features"]].to_numpy(dtype=np.float32)
    imputed = bundle["imputer"].transform(raw).astype(np.float32)
    tabpfn = load_statewide_tabpfn().predict_proba(imputed).astype(np.float32)

    multimodal = load_multimodal_bundle()
    scaled = multimodal["preprocessing"]["scaler"].transform(imputed).astype(np.float32)
    network, device = multimodal["network"], multimodal["device"]
    vision_parts = []
    for start in range(0, len(study), args.batch_size):
        part = study.iloc[start:start + args.batch_size]
        chips = torch.stack([load_chip(args.chips / f"{point_id}.npz") for point_id in part.point_id])
        tabular = torch.tensor(scaled[start:start + len(part)], dtype=torch.float32, device=device)
        with torch.inference_mode():
            vision_parts.append(torch.softmax(network(chips.to(device), tabular)["vision"], dim=1).cpu().numpy())
        print(f"TerraMind calibration {min(start + len(part), len(study))}/{len(study)}", flush=True)
    vision = np.concatenate(vision_parts).astype(np.float32)
    labels = study.label.to_numpy(dtype=int)
    validation = study.district.isin(VALIDATION_DISTRICTS).to_numpy()
    test = study.district.isin(TEST_DISTRICTS).to_numpy()

    candidates = []
    for agree in np.linspace(0, .30, 16):
        for disagree in np.linspace(0, min(agree, .12), 7):
            config = FusionConfig(float(agree), float(disagree))
            fused, _ = combine_probabilities(tabpfn[validation], vision[validation], config)
            result = metrics(labels[validation], fused)
            candidates.append((result["macro_f1"], -result["log_loss"], agree, disagree))
    _, _, agree, disagree = max(candidates)
    provisional = FusionConfig(float(agree), float(disagree))
    validation_fused, _ = combine_probabilities(tabpfn[validation], vision[validation], provisional)
    test_fused, _ = combine_probabilities(tabpfn[test], vision[test], provisional)
    validation_result = metrics(labels[validation], validation_fused)
    test_result = metrics(labels[test], test_fused)
    tabpfn_test = metrics(labels[test], tabpfn[test])
    gate = test_result["macro_f1"] >= tabpfn_test["macro_f1"] - .005 and test_result["log_loss"] <= tabpfn_test["log_loss"] + .03
    final = FusionConfig(float(agree), float(disagree), gate, validation_result["macro_f1"], test_result["macro_f1"], tabpfn_test["macro_f1"])
    final.save(args.out)
    report = {"config": json.loads(args.out.read_text()), "validation": validation_result, "test": test_result, "tabpfn_test": tabpfn_test,
              "warning": "Experimental weak-label evaluation, not observed construction outcomes"}
    args.out.with_name("evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

