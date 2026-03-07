# Stack Research: ML Fraud Scoring

**Project:** Fraud Detection Pipeline — v2.0 ML Fraud Scoring
**Date:** 2026-03-06
**Confidence:** HIGH (versions verified from PyPI)

## Additions to `requirements.txt`

```
# ML scoring (v2.0 milestone)
scikit-learn==1.6.1
xgboost==2.1.4
joblib==1.4.2
pandas==2.2.3
numpy==1.26.4
```

## Library Decisions

| Package | Version | Rationale |
|---|---|---|
| scikit-learn | 1.6.1 | Latest proven stable (1.8.0 too recent); provides `RandomForestClassifier`, `Pipeline`, `ColumnTransformer`, `class_weight='balanced'` for imbalance |
| xgboost | 2.1.4 | v3.x is a breaking-change major version — 2.1.4 is stable and drops into scikit-learn Pipeline via identical API |
| joblib | 1.4.2 | Already a transitive dep of scikit-learn; pin explicitly; preferred over pickle for numpy array efficiency |
| pandas | 2.2.3 | v3.0.1 too recent; 2.2.3 proven. **Training script only** — must NOT be imported in processor.py hot path |
| numpy | 1.26.4 | Last 1.x LTS — satisfies all three ML libs simultaneously; numpy 2.x has C-API friction in Docker slim images |

## What NOT to Add

| Rejected | Reason |
|---|---|
| MLflow / experiment tracking | Out of scope per PROJECT.md |
| FastAPI / BentoML / Ray Serve | Inference must stay in-process — no new services |
| imbalanced-learn / SMOTE | Unnecessary; `class_weight='balanced'` sufficient |
| TensorFlow / PyTorch | Wrong tool for small tabular dataset |

## New Files (Non-Dependencies)

| File | Purpose |
|---|---|
| `src/train_model.py` | Offline training script — reads from PostgreSQL, engineers features, trains model, serializes to `src/model/fraud_model.joblib` |
| `src/model/fraud_model.joblib` | Serialized model artifact — baked into Docker image at build time (acceptable for static model) |

## Infrastructure Changes

- **Single `requirements.txt` edit** + Docker rebuild for `processor` service — no new containers
- Model artifact baked into image via `src/model/` directory — rebuild processor image after each retrain
- Training script runs on **host** against PostgreSQL on port 5433 (external) — not in Docker
- `pandas` is a **training-only** dependency — use plain dicts in processor.py hot path

## Integration Points

```
requirements.txt        ← add 5 packages
src/train_model.py      ← NEW: training script
src/model/              ← NEW: directory for model artifact
src/processor.py        ← MODIFY: load model at startup, call predict_proba() per message
src/db_setup.py         ← MODIFY: add ml_score NUMERIC(5,4) column to Transaction model
src/dashboard.py        ← MODIFY: query + display ml_score column
```

## Key Warning

The `transactions.is_fraud` column stores strings `"True"`/`"False"`. Training code must cast explicitly:

```python
df['is_fraud'] = df['is_fraud'].map({'True': 1, 'False': 0})
assert df['is_fraud'].nunique() == 2
```

`bool("False") == True` in Python — `.astype(bool)` will corrupt the entire label column.

---

*Stack research: 2026-03-06*
