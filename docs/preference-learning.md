# Local preference learning in Nilam

The **Find suitable land** workflow first measures fresh cells inside the chosen radius, applies its existing land-cover, building, slope, flood, landslide and stated-distance filters, and predicts a public-data score with TabPFN. Only candidates that pass those filters enter preference learning. The shared preference model runs locally and never updates TabPFN or TerraMind weights.

## Human feedback and model

After a search, **Compare two sites** shows two eligible candidates. Each card has a nearby outdoor Google Street View panorama aimed toward the cell, a satellite inset, coordinates and the same site facts. If no outdoor panorama is available within 250 m, the satellite map fills the card. Street View may show the road instead of the land itself. Users can prefer left, prefer right, tie, or skip. A skip is logged but does not update weights.

Each candidate becomes a nine-feature vector of bounded, comparable values: mapped flatness, apparent open ground, hospital access, school access, road access, park access, shop access, NDVI, and distance from industrial and quarry sites. Missing evidence receives a neutral 0.5 feature value; eligibility was already decided by the original hard filters. No votes are synthesized. The weight vector starts at zero, so the first search is identical to the previous ranking.

For a shown pair with vectors (x_L,x_R), the locally stored online preference model predicts

\[
P(L \succ R)=\sigma\left(w^\top(x_L-x_R)\right).
\]

After a vote with target `y=1` for left, `0` for right, or `0.5` for a tie, it applies a regularized gradient step

\[
w\leftarrow\operatorname{clip}\left(w+\eta[(y-P)(x_L-x_R)-0.01w],-3,3\right),
\quad\eta=0.8/\sqrt{1+n/25}.
\]

This is an online pairwise preference model with a stochastic *dueling bandit* choice of comparison pairs. The model uses no cloud training or synthetic target data. Pair selection favours uncertainty and feature contrast among the top twelve currently ranked candidates. Where at least two have an original model score of 50% or more, weaker candidates are excluded from comparisons; pairs within twenty overall-fit points are preferred. Left/right order is randomized. The log records pair-selection propensity and the 0.5 side-placement propensity.

The method follows the pairwise-feedback setting described in the [preference-based online learning survey](https://www.jmlr.org/papers/v22/18-546.html). This implementation is a lightweight local contextual model, not a fine-tune of the satellite encoder.

## Score and ranking

The original model score `S₀` is retained. A candidate's learned preference adjustment is

\[
\Delta=20\left[\sigma\left(w^\top(x-0.5)\right)-0.5\right],
\qquad -10\leq\Delta\leq10.
\]

The displayed community-adjusted score is `S = clip(S₀ + Δ, 0, 100)`. The same adjustment is added to the existing combined search rank before candidates are sorted again. At zero votes, `w=0` and `Δ=0`. The UI shows the original score beside the adjusted one. A vote expresses preference, not proof of safe or available land; assessment and SHAP continue to use the unadjusted public-data model.

## Storage and evaluation

`data/processed/preference_feedback.sqlite3` holds search snapshots, shown pairs, side order, model version, logged propensities, votes, and two weight vectors. The live vector updates after every non-skip vote. A separate evaluation vector trains on only the training split; roughly 20% of geographic pairs, including any repeated votes on them, form a held-out human-comparison set. The evaluation endpoint and command compare this vector with the original fixed ranking using pairwise accuracy, log loss and Brier score:

```bash
.venv-multimodal/bin/python scripts/evaluate_preference_learning.py
```

These numbers remain unavailable until people cast votes. Small or nonrepresentative vote counts cannot establish improvement. Because pair exposure is adaptive and restricted to already screened top candidates, the held-out metrics describe ranking on shown pairs, not all land in Kerala or construction safety. The local browser ID limits repeated votes on a pair from the same browser; it is not strong identity or abuse protection.
