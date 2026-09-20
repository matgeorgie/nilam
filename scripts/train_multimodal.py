"""Train TerraMind + tabular gated cross-attention fusion with district holdouts."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import time
import warnings

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, Dataset

from kerala_land_lab.multimodal import MultimodalFusionModel, build_terramind, load_chip, set_backbone_trainable, S2_BANDS
from kerala_land_lab.weak_labels import VERSION
FEATURES = [
    "annual_rainfall", "aspect", "clay_content", "distance_to_water", "elevation", "flood_occurrence", "land_cover_class", "mean_humidity", "mean_temperature", "mean_wind_speed", "ndvi", "organic_carbon", "sand_content", "slope", "soil_ph", "terrain_ruggedness_index", "water_content", "flood_level_10yr_m", "flood_level_25yr_m", "flood_level_50yr_m", "flood_level_100yr_m", "flood_level_200yr_m", "flood_level_500yr_m", "gsi_landslide_code", "dist_nearest_road", "dist_nearest_highway", "dist_nearest_hospital", "dist_nearest_school", "dist_nearest_quarry", "dist_nearest_bus_stop", "dist_nearest_railway_station", "dist_nearest_pharmacy", "dist_nearest_shop", "dist_nearest_bank", "dist_nearest_park", "dist_nearest_power_line", "dist_nearest_waste_facility", "dist_nearest_industrial",
]
GSI_CODES = {"Not mapped": 0, "Low": 1, "Moderate": 2, "High": 3}
VALIDATION_DISTRICTS = ["Ernakulam", "Wayanad"]
TEST_DISTRICTS = ["Alappuzha", "Idukki", "Kasaragod"]


class SiteDataset(Dataset):
    def __init__(self, frame, indices, tabular, chips_dir, augment=False):
        self.frame=frame.iloc[indices].reset_index(drop=True);self.tabular=tabular[indices];self.chips_dir=chips_dir;self.augment=augment
    def __len__(self):return len(self.frame)
    def __getitem__(self,index):
        row=self.frame.iloc[index]
        return {"chips":load_chip(self.chips_dir/f"{row.point_id}.npz",self.augment),"tabular":torch.tensor(self.tabular[index],dtype=torch.float32),"label":torch.tensor(int(row.label)),"point_id":row.point_id}


def probabilities(model, loader, device):
    model.eval();outputs={name:[] for name in ("fusion","vision","tabular")};labels=[];gates=[]
    with torch.no_grad():
        for batch in loader:
            result=model(batch["chips"].to(device),batch["tabular"].to(device));labels.append(batch["label"].numpy());gates.append(result["gate"].cpu().numpy())
            for name in outputs:outputs[name].append(torch.softmax(result[name],dim=1).cpu().numpy())
    return np.concatenate(labels),{name:np.concatenate(parts) for name,parts in outputs.items()},np.concatenate(gates)


def metrics(y, probability):
    predicted=probability.argmax(1)
    return {"macro_f1":float(f1_score(y,predicted,average="macro")),"accuracy":float(accuracy_score(y,predicted)),"log_loss":float(log_loss(y,probability,labels=[0,1,2,3])),"confusion_matrix":confusion_matrix(y,predicted,labels=[0,1,2,3]).tolist(),"n":len(y)}


def optimizer_for(model, head_lr, backbone_lr, weight_decay):
    backbone_ids={id(parameter) for parameter in model.backbone.parameters() if parameter.requires_grad}
    head=[parameter for parameter in model.parameters() if parameter.requires_grad and id(parameter) not in backbone_ids]
    groups=[{"params":head,"lr":head_lr}]
    backbone=[parameter for parameter in model.backbone.parameters() if parameter.requires_grad]
    if backbone:groups.append({"params":backbone,"lr":backbone_lr})
    return torch.optim.AdamW(groups,weight_decay=weight_decay)


def main():
    warnings.filterwarnings("ignore", message=r"`torch\.jit\.script` is deprecated.*", category=FutureWarning)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("data/processed/kerala_statewide_features.csv"))
    parser.add_argument("--chips",type=Path,default=Path("data/processed/sentinel2_chips"))
    parser.add_argument("--out",type=Path,default=Path("models/multimodal"))
    parser.add_argument("--checkpoint",type=Path,help="Local TerraMind checkpoint matching --variant; omit for automatic download")
    parser.add_argument("--variant",choices=("tiny","base"),default="base",help="TerraMind backbone; base is recommended on the 16 GB M4")
    parser.add_argument("--epochs",type=int,default=30);parser.add_argument("--unfreeze-epoch",type=int,default=7);parser.add_argument("--unfreeze-blocks",type=int,default=2)
    parser.add_argument("--batch-size",type=int,default=1);parser.add_argument("--accumulate",type=int,default=16);parser.add_argument("--workers",type=int,default=0)
    parser.add_argument("--head-lr",type=float,default=3e-4);parser.add_argument("--backbone-lr",type=float,default=1e-5);parser.add_argument("--weight-decay",type=float,default=.02)
    parser.add_argument("--device",default="auto");parser.add_argument("--seed",type=int,default=42)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed)
    device=torch.device("mps" if args.device=="auto" and torch.backends.mps.is_available() else "cuda" if args.device=="auto" and torch.cuda.is_available() else "cpu" if args.device=="auto" else args.device)
    print(f"[setup] device={device} variant={args.variant}",flush=True)
    frame=pd.read_csv(args.data);frame["gsi_landslide_code"]=frame.gsi_landslide_susceptibility.map(GSI_CODES)
    if set(frame.weak_label_version.unique())!={VERSION}:raise RuntimeError("Weak-label version mismatch")
    available=frame.point_id.map(lambda point_id:(args.chips/f"{point_id}.npz").exists())
    missing=frame.loc[~available,"point_id"].tolist()
    if missing:raise RuntimeError(f"Missing {len(missing)} chips; rerun download_satellite_chips.py. First: {missing[:5]}")
    print(f"[data] verified {len(frame)} samples and satellite chips",flush=True)
    train_mask=~frame.district.isin(VALIDATION_DISTRICTS+TEST_DISTRICTS);validation_mask=frame.district.isin(VALIDATION_DISTRICTS);test_mask=frame.district.isin(TEST_DISTRICTS)
    splits={"train":np.flatnonzero(train_mask),"validation":np.flatnonzero(validation_mask),"test":np.flatnonzero(test_mask)}
    baseline=joblib.load("models/statewide/baseline.joblib")
    raw=frame[FEATURES].to_numpy(dtype=np.float32);imputed=baseline["imputer"].transform(raw).astype(np.float32)
    scaler=StandardScaler().fit(imputed[splits["train"]]);tabular=scaler.transform(imputed).astype(np.float32)
    datasets={name:SiteDataset(frame,index,tabular,args.chips,augment=name=="train") for name,index in splits.items()}
    loaders={name:DataLoader(dataset,batch_size=args.batch_size,shuffle=name=="train",num_workers=args.workers,pin_memory=device.type=="cuda") for name,dataset in datasets.items()}
    print(f"[split] train={len(datasets['train'])} validation={len(datasets['validation'])} test={len(datasets['test'])}",flush=True)
    print(f"[model] loading TerraMind {args.variant} checkpoint",flush=True)
    backbone,vision_dim=build_terramind(args.checkpoint,args.variant);set_backbone_trainable(backbone,0)
    model=MultimodalFusionModel(backbone,len(FEATURES),vision_dim).to(device)
    total_parameters=sum(parameter.numel() for parameter in model.parameters())
    trainable_parameters=sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    print(f"[model] ready: {total_parameters:,} parameters; {trainable_parameters:,} initially trainable",flush=True)
    counts=np.bincount(frame.loc[train_mask,"label"].to_numpy(),minlength=4);class_weights=torch.tensor(len(splits["train"])/(4*counts),dtype=torch.float32,device=device)
    criterion=nn.CrossEntropyLoss(weight=class_weights);optimizer=optimizer_for(model,args.head_lr,args.backbone_lr,args.weight_decay)
    best_score=-1;best_state=None;patience=0;history=[];trainable_blocks=[]
    for epoch in range(1,args.epochs+1):
        if epoch==args.unfreeze_epoch:
            trainable_blocks=set_backbone_trainable(model.backbone,args.unfreeze_blocks);optimizer=optimizer_for(model,args.head_lr,args.backbone_lr,args.weight_decay)
            print(f"[epoch {epoch}] unfroze {len(trainable_blocks)} parameters from final {args.unfreeze_blocks} backbone blocks",flush=True)
        epoch_started=time.monotonic()
        print(f"[epoch {epoch}/{args.epochs}] training {len(loaders['train'])} batches",flush=True)
        model.train();optimizer.zero_grad(set_to_none=True);losses=[]
        for step,batch in enumerate(loaders["train"],1):
            result=model(batch["chips"].to(device),batch["tabular"].to(device));target=batch["label"].to(device)
            loss=criterion(result["fusion"],target)+.2*criterion(result["vision"],target)+.2*criterion(result["tabular"],target)
            (loss/args.accumulate).backward();losses.append(float(loss.detach().cpu()))
            if step%args.accumulate==0 or step==len(loaders["train"]):
                nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.0);optimizer.step();optimizer.zero_grad(set_to_none=True)
            if step==1 or step%25==0 or step==len(loaders["train"]):
                elapsed=time.monotonic()-epoch_started
                print(f"[epoch {epoch}/{args.epochs}] batch {step}/{len(loaders['train'])} mean_loss={np.mean(losses):.4f} elapsed={elapsed:.0f}s",flush=True)
        y_val,val_probs,val_gates=probabilities(model,loaders["validation"],device);val={name:metrics(y_val,prob) for name,prob in val_probs.items()};score=val["fusion"]["macro_f1"]
        history.append({"epoch":epoch,"train_loss":float(np.mean(losses)),"validation":val,"mean_gate":val_gates.mean(axis=0).tolist(),"backbone_unfrozen":epoch>=args.unfreeze_epoch})
        print(json.dumps(history[-1]),flush=True)
        if score>best_score+1e-4:best_score=score;best_state=copy.deepcopy(model.state_dict());patience=0
        else:patience+=1
        if patience>=7:break
    model.load_state_dict(best_state)
    results={}
    for split in ("validation","test"):
        y,probs,gates=probabilities(model,loaders[split],device);results[split]={name:metrics(y,prob) for name,prob in probs.items()};results[split]["mean_gate"]={"vision":float(gates[:,0].mean()),"tabular":float(gates[:,1].mean()),"cross_attention":float(gates[:,2].mean())}
    checkpoint={"state_dict":model.state_dict(),"features":FEATURES,"tabular_mean":scaler.mean_.tolist(),"tabular_scale":scaler.scale_.tolist(),"vision_dim":vision_dim,"bands":S2_BANDS,"seasons":["dry_Jan_Mar","monsoon_Jun_Sep"],"weak_label_version":VERSION,"training_districts":sorted(frame.loc[train_mask,"district"].unique()),"model":f"TerraMind-1.0-{args.variant} + temporal transformer + gated cross-attention","variant":args.variant,"trainable_backbone_parameters":trainable_blocks}
    torch.save(checkpoint,args.out/"terramind_tabular_fusion.pt")
    report={"dataset_sha256":hashlib.sha256(args.data.read_bytes()).hexdigest(),"chip_count":len(frame),"chip_shape":[2,12,224,224],"split":"Same whole-district holdout as statewide tabular study","validation_districts":VALIDATION_DISTRICTS,"test_districts":TEST_DISTRICTS,"results":results,"best_validation_macro_f1":best_score,"epochs_run":len(history),"device":str(device),"target_warning":"Experimental weak labels, not observed construction outcomes"}
    (args.out/"evaluation.json").write_text(json.dumps(report,indent=2)+"\n");(args.out/"training_history.json").write_text(json.dumps(history,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
