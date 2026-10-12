"""Calibrate and quality-gate TerraMind + TabPFN late fusion.

This reuses the trained TerraMind cross-attention network and fitted TabPFN
artifact. It learns only two transparent mixture weights on the validation
districts, then reports the geographically held-out development result. The
deployed config falls back to TabPFN when the secondary expert does not improve
both macro-F1 and log loss by the declared margins.
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
    parser.add_argument(
        "--secondary-head", choices=("fusion", "cross", "vision", "tabular"), default="fusion",
        help="Trained multimodal head supplied as TabPFN's secondary expert",
    )
    parser.add_argument("--minimum-test-gain", type=float, default=.005)
    args = parser.parse_args()

    frame = pd.read_csv(args.data)
    available = frame.point_id.map(lambda point_id: (args.chips / f"{point_id}.npz").exists())
    excluded = frame.loc[~available, "point_id"].tolist()
    if excluded:
        print(f"Ignoring {len(excluded)} rows without satellite chips: {excluded[:5]}", flush=True)
        frame = frame.loc[available].reset_index(drop=True)
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
    head_parts = {name: [] for name in ("fusion", "cross", "vision", "tabular")}
    for start in range(0, len(study), args.batch_size):
        part = study.iloc[start:start + args.batch_size]
        chips = torch.stack([load_chip(args.chips / f"{point_id}.npz") for point_id in part.point_id])
        tabular = torch.tensor(scaled[start:start + len(part)], dtype=torch.float32, device=device)
        with torch.inference_mode():
            output = network(chips.to(device), tabular)
            for name in head_parts:
                head_parts[name].append(torch.softmax(output[name], dim=1).cpu().numpy())
        print(f"TerraMind calibration {min(start + len(part), len(study))}/{len(study)}", flush=True)
    heads = {name: np.concatenate(parts).astype(np.float32) for name, parts in head_parts.items()}
    secondary = heads[args.secondary_head]
    labels = study.label.to_numpy(dtype=int)
    validation = study.district.isin(VALIDATION_DISTRICTS).to_numpy()
    test = study.district.isin(TEST_DISTRICTS).to_numpy()
    if int(validation.sum()) != 200 or int(test.sum()) != 300:
        raise RuntimeError(
            f"Expected the trained 200/300 validation/development cohort, got "
            f"{int(validation.sum())}/{int(test.sum())}"
        )

    candidates = []
    for agree in np.linspace(0, .30, 31):
        for disagree in np.linspace(0, .20, 21):
            config = FusionConfig(float(agree), float(disagree), secondary_head=args.secondary_head)
            fused, _ = combine_probabilities(tabpfn[validation], secondary[validation], config)
            result = metrics(labels[validation], fused)
            candidates.append((result["macro_f1"], -result["log_loss"], -agree - disagree, agree, disagree))
    _, _, _, agree, disagree = max(candidates)
    provisional = FusionConfig(float(agree), float(disagree), secondary_head=args.secondary_head)
    validation_fused, _ = combine_probabilities(tabpfn[validation], secondary[validation], provisional)
    test_fused, _ = combine_probabilities(tabpfn[test], secondary[test], provisional)
    validation_result = metrics(labels[validation], validation_fused)
    test_result = metrics(labels[test], test_fused)
    tabpfn_validation = metrics(labels[validation], tabpfn[validation])
    tabpfn_test = metrics(labels[test], tabpfn[test])
    gate = (
        validation_result["macro_f1"] > tabpfn_validation["macro_f1"]
        and test_result["macro_f1"] >= tabpfn_test["macro_f1"] + args.minimum_test_gain
        and test_result["log_loss"] < tabpfn_test["log_loss"]
    )
    deployed_agree, deployed_disagree = (float(agree), float(disagree)) if gate else (0.0, 0.0)
    final = FusionConfig(
        deployed_agree, deployed_disagree, secondary_head=args.secondary_head,
        quality_gate_passed=gate, validation_macro_f1=validation_result["macro_f1"],
        test_macro_f1=test_result["macro_f1"], tabpfn_test_macro_f1=tabpfn_test["macro_f1"],
    )
    final.save(args.out)
    report = {
        "config": json.loads(args.out.read_text()),
        "selected_candidate_weights": {"agree": float(agree), "disagree": float(disagree)},
        "minimum_test_macro_f1_gain": args.minimum_test_gain,
        "validation": validation_result, "test": test_result,
        "tabpfn_validation": tabpfn_validation, "tabpfn_test": tabpfn_test,
        "secondary_head_ablations": {
            name: {"validation": metrics(labels[validation], values[validation]),
                   "test": metrics(labels[test], values[test])}
            for name, values in heads.items()
        },
        "warning": "Retrospective weak-label development evaluation, not observed construction outcomes or a fresh confirmatory test",
    }
    args.out.with_name("evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

