"""Train a polygon-separated pilot, keeping validation and test sets distinct."""
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
from sklearn.metrics import accuracy_score, f1_score, log_loss, confusion_matrix
from sklearn.preprocessing import StandardScaler
from kerala_land_lab.earth import FEATURES, load_env
from kerala_land_lab.model import FeatureTransformer
from kerala_land_lab.research import grouped_stratified_split

p = argparse.ArgumentParser()
p.add_argument("--epochs",type=int,default=100)
p.add_argument("--tabpfn",action="store_true")
p.add_argument("--finetune",action="store_true")
p.add_argument("--device",default="cpu")
args=p.parse_args()
load_env(); torch.manual_seed(42); np.random.seed(42); torch.set_num_threads(4)
out=Path("models");out.mkdir(exist_ok=True)
data_path=Path("data/processed/landslide_dataset.csv")
frame=pd.read_csv(data_path).dropna(subset=FEATURES)
X=frame[FEATURES].to_numpy(dtype=np.float32);y=frame.target.to_numpy(dtype=int)

# Group by original source polygon while balancing each mapped class.
seed=42
train,val,test=grouped_stratified_split(frame,seed=seed)
for a,b in [(train,val),(train,test),(val,test)]:
    assert not set(frame.iloc[a].source_polygon_id)&set(frame.iloc[b].source_polygon_id)
splits={name:frame.iloc[idx].sample_id.tolist() for name,idx in [("train",train),("validation",val),("test",test)]}
(out/"splits.json").write_text(json.dumps(splits,indent=2))
def metrics(prob,idx):
    pred=prob.argmax(1)
    return {"macro_f1":float(f1_score(y[idx],pred,average="macro")),"accuracy":float(accuracy_score(y[idx],pred)),"log_loss":float(log_loss(y[idx],prob,labels=[0,1,2])),"confusion_matrix":confusion_matrix(y[idx],pred,labels=[0,1,2]).tolist(),"n":len(idx)}
results={}
tree=ExtraTreesClassifier(n_estimators=300,min_samples_leaf=3,class_weight="balanced",random_state=42,n_jobs=4).fit(X[train],y[train])
results['extra_trees']={"validation":metrics(tree.predict_proba(X[val]),val),"test":metrics(tree.predict_proba(X[test]),test),"training":"Supervised tree ensemble"}
joblib.dump({"estimator":tree,"features":FEATURES,"train_min":X[train].min(0),"train_max":X[train].max(0),"background":X[train][:32]},out/"baseline.joblib")
print('ExtraTrees',results['extra_trees'],flush=True)
scaler=StandardScaler().fit(X[train]);z=torch.tensor(scaler.transform(X),dtype=torch.float32)
model=FeatureTransformer(len(FEATURES));opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
counts=np.bincount(y[train],minlength=3);weight=torch.tensor(len(train)/(3*counts),dtype=torch.float32)
lossfn=torch.nn.CrossEntropyLoss(weight=weight)
best=float('inf');best_state=None;history=[];patience=0
for epoch in range(args.epochs):
    model.train();train_losses=[]
    order=np.random.permutation(train)
    for start in range(0,len(order),64):
        ids=order[start:start+64];opt.zero_grad();loss=lossfn(model(z[ids]),torch.tensor(y[ids]));loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);opt.step();train_losses.append(float(loss.detach()))
    model.eval()
    with torch.no_grad():valid=float(lossfn(model(z[val]),torch.tensor(y[val])))
    history.append({"epoch":epoch+1,"train_loss":float(np.mean(train_losses)),"validation_loss":valid})
    if valid<best-.0001:best=valid;best_state=copy.deepcopy(model.state_dict());patience=0
    else:patience+=1
    if patience>=15:break
model.load_state_dict(best_state);model.eval()
with torch.no_grad():prob=torch.softmax(model(z),dim=1).numpy()
results['feature_transformer']={"validation":metrics(prob[val],val),"test":metrics(prob[test],test),"training":"Feature-token Transformer trained from scratch with AdamW; early stopping on validation only", "epochs_run":len(history),"parameters":sum(p.numel() for p in model.parameters())}
torch.save(model.state_dict(),out/"feature_transformer.pt");joblib.dump(scaler,out/"transformer_scaler.joblib")
(out/"training_history.json").write_text(json.dumps(history,indent=2))
print('Transformer',results['feature_transformer'],flush=True)
if args.tabpfn:
    from tabpfn import TabPFNClassifier
    from tabpfn.model_loading import save_fitted_tabpfn_model
    estimator=TabPFNClassifier(model_path=os.environ['TABPFN_MODEL_PATH'],n_estimators=1,device=args.device,random_state=42)
    estimator.fit(X[train],y[train])
    results['tabpfn_3_5_fast']={"validation":metrics(estimator.predict_proba(X[val]),val),"test":metrics(estimator.predict_proba(X[test]),test),"training":"Pretrained weights; in-context fit only, no gradient updates"}
    save_fitted_tabpfn_model(estimator,out/"tabpfn.tabpfn_fit")
    print('TabPFN',results['tabpfn_3_5_fast'],flush=True)
if args.finetune:
    from tabpfn.finetuning import FinetunedTabPFNClassifier
    from tabpfn.constants import ModelVersion
    tuned=FinetunedTabPFNClassifier(device=args.device,epochs=10,time_limit=600,validation_split_ratio=None,
        n_finetune_ctx_plus_query_samples=128,n_estimators_finetune=1,n_estimators_validation=1,n_estimators_final_inference=1,
        early_stopping_patience=3,model_version=ModelVersion.V3_5_FAST,
        extra_classifier_kwargs={"model_path":os.environ['TABPFN_MODEL_PATH']},random_state=42)
    tuned.fit(X[train],y[train],X_val=X[val],y_val=y[val],output_dir=out/"tabpfn_finetuned")
    results['tabpfn_finetuned']={"validation":metrics(tuned.predict_proba(X[val]),val),"test":metrics(tuned.predict_proba(X[test]),test),"training":"Gradient fine-tuning of pretrained TabPFN; checkpoints saved separately"}
    print('Fine-tuned TabPFN',results['tabpfn_finetuned'],flush=True)
report={"dataset_sha256":hashlib.sha256(data_path.read_bytes()).hexdigest(),"seed":seed,"features":FEATURES,"split":"Original source polygons held apart; class-specific row counts balanced greedily; pilot only, not independent district/event validation", "rows":len(frame),"class_counts":np.bincount(y,minlength=3).tolist(),"district_counts":frame.district.value_counts().to_dict(),"geographic_limitation":"537 of 540 rows are in Wayanad; these results must not be generalized statewide.","split_class_counts":{name:np.bincount(y[idx],minlength=3).tolist() for name,idx in [("train",train),("validation",val),("test",test)]},"class_names":["Low mapped susceptibility","Medium mapped susceptibility","High mapped susceptibility"],"sampling_warning":"Class-balanced dataset: probabilities do not estimate Kerala event prevalence", "target_warning":"Agreement with historical KSDMA mapped classes, not real construction safety", "models":results,"validation_winner":max(results,key=lambda k:results[k]['validation']['macro_f1'])}
(out/"evaluation.json").write_text(json.dumps(report,indent=2))
Path('docs/evaluation.json').write_text(json.dumps(report,indent=2))
print('Saved evaluation and model artifacts',flush=True)
