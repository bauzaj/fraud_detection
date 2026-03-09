# Phase 7: Training Pipeline — Research

**Phase:** 7
**Slug:** training-pipeline
**Confidence:** HIGH
**Researched:** 2026-03-09

---

## Validation Architecture

| Task | Verify Command | Type |
|------|---------------|------|
| Script runs without error | `python src/train_model.py` exits 0, prints PR-AUC and recall | manual/smoke |
| Class distribution check | Script prints class distribution; assertion `nunique() == 2` passes | automated (in-script) |
| Artifact exists | `ls src/model/fraud_model.joblib` after script completes | manual/smoke |
| Recall >= 0.80 | Script prints fraud-class recall metric | manual/smoke |

---

## Critical Findings from Codebase Inspection

### Feature Window Parity (Training-Serving Skew Risk)

Inspected `src/processor.py` `detect_fraud()` method. The in-memory feature computation uses:

**tx_count_last_5min:**
- `self.user_transactions[user_id]` is a list of dicts with `timestamp` and `amount`
- History is appended AFTER fraud check — current tx is NOT included in window
- 5-minute window: only prior transactions within 300 seconds of current tx timestamp
- Training pandas equivalent: `rolling('5min', closed='left')` on sorted timestamp index, EXCLUDES current row

**amount_vs_user_avg_ratio:**
- Mean of ALL prior history (up to 100 entries cap), EXCLUDES current transaction
- Cold-start: only computed when len(history) >= 2 (processor returns 1.0 implicitly for cold-start)
- Training pandas equivalent: `expanding().mean().shift(1)`, fill NaN → 1.0

**Critical:** Both features must EXCLUDE the current transaction. Use shift or closed='left' window.

### Schema Inspection (`src/db_setup.py`)

```python
class Transaction(Base):
    transaction_id = Column(String, primary_key=True)
    timestamp = Column(TIMESTAMP)
    user_id = Column(String)
    merchant_id = Column(String)
    amount = Column(Numeric(10, 2))
    card_last_4 = Column(String)
    merchant_category = Column(String)
    is_fraud = Column(String)      # stores "True"/"False" strings — NOT bool
    processed_at = Column(TIMESTAMP)
    ml_score = Column(Numeric(5, 4))  # added in Phase 6, nullable
```

**is_fraud label casting trap:** `bool("False") == True` — NEVER cast to bool directly.
Use: `df['is_fraud'].map({'True': 1, 'False': 0})` with assertion `nunique() == 2`.

### Feature Columns

**Use as features (TRAIN-01):**
- `amount` — direct numeric
- `tx_count_last_5min` — engineered (rolling window)
- `amount_vs_user_avg_ratio` — engineered (expanding mean, shifted)
- `hour_of_day` — extracted from `timestamp`
- `day_of_week` — extracted from `timestamp`
- `merchant_category` — categorical, needs encoding

**Exclude (leakage/irrelevant):**
- `transaction_id`, `merchant_id`, `card_last_4`, `processed_at` — identifiers/audit
- `ml_score` — target leakage
- `rules_triggered`, `fraud_score` — in `fraud_alerts` table, not transactions table

### PostgreSQL Connection

- External port: 5433 (host access during training)
- Internal port: 5432 (used by processor container at inference time)
- Connection string: `postgresql://fraud_user:fraud_pass@localhost:5433/fraud_detection`
- SQLAlchemy: `create_engine(connection_string)` + `pd.read_sql(query, engine)`

### Class Imbalance

- Fraud rate ~3% (synthetic data generator produces ~3% fraud across rule patterns)
- Use `RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42)`
- Evaluate with: PR-AUC (`average_precision_score`) + fraud-class recall (`classification_report`)
- Do NOT report raw accuracy (misleading at 3% fraud rate)
- If recall < 0.80: try XGBoost with `scale_pos_weight = n_negative / n_positive`

---

## Recommended Implementation

### Script Structure: `src/train_model.py`

```python
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.metrics import average_precision_score, classification_report
import joblib

DB_URL = "postgresql://fraud_user:fraud_pass@localhost:5433/fraud_detection"
MODEL_PATH = "src/model/fraud_model.joblib"

# 1. Load data
engine = create_engine(DB_URL)
df = pd.read_sql("SELECT * FROM transactions ORDER BY timestamp", engine)

# 2. Label encoding
df['label'] = df['is_fraud'].map({'True': 1, 'False': 0})
assert df['label'].nunique() == 2, "Both fraud and non-fraud labels required"
print(f"Class distribution:\n{df['label'].value_counts()}")

# 3. Feature engineering (must mirror processor.py windows)
df = df.sort_values(['user_id', 'timestamp']).reset_index(drop=True)
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp')

# tx_count_last_5min: rolling 5min, exclude current tx
df['tx_count_last_5min'] = (
    df.groupby('user_id')['amount']
    .transform(lambda x: x.rolling('5min', closed='left').count())
    .fillna(0)
)

# amount_vs_user_avg_ratio: expanding mean shifted by 1 (exclude current)
df['user_avg_amount'] = (
    df.groupby('user_id')['amount']
    .transform(lambda x: x.expanding().mean().shift(1))
)
df['amount_vs_user_avg_ratio'] = (df['amount'] / df['user_avg_amount']).fillna(1.0)

df = df.reset_index()
df['hour_of_day'] = df['timestamp'].dt.hour
df['day_of_week'] = df['timestamp'].dt.dayofweek

# 4. Feature matrix
NUMERIC_FEATURES = ['amount', 'tx_count_last_5min', 'amount_vs_user_avg_ratio',
                    'hour_of_day', 'day_of_week']
CAT_FEATURES = ['merchant_category']

X = df[NUMERIC_FEATURES + CAT_FEATURES]
y = df['label']

# 5. Train/validation split
X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

# 6. Pipeline: preprocessing + classifier
preprocessor = ColumnTransformer([
    ('cat', OneHotEncoder(handle_unknown='ignore'), CAT_FEATURES)
], remainder='passthrough')

model = Pipeline([
    ('preprocessor', preprocessor),
    ('classifier', RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42))
])

model.fit(X_train, y_train)

# 7. Evaluate
y_pred = model.predict(X_val)
y_proba = model.predict_proba(X_val)[:, 1]
pr_auc = average_precision_score(y_val, y_proba)
print(f"PR-AUC: {pr_auc:.4f}")
print(classification_report(y_val, y_pred, target_names=['not_fraud', 'fraud']))

# 8. Serialize
joblib.dump(model, MODEL_PATH)
print(f"Model saved to {MODEL_PATH}")
```

### Pipeline Wrapping (Critical for Phase 8)

Wrap `OneHotEncoder` + classifier in a `sklearn.pipeline.Pipeline` before `joblib.dump()`.
In Phase 8, `model.predict_proba(X)` will work on raw feature dicts without manual encoding.
The Pipeline handles both preprocessing and inference in one call.

### Data Volume Warning

Synthetic generator produces ~1 tx/second. With the system running since Phase 6 (~hours), there may be 3,000–10,000 rows. This is sufficient for training but may be low for robust recall. If recall < 0.80, try lowering `min_samples_leaf=5` or increasing `n_estimators=200`.

---

## Wave Assignment Recommendation

**1 plan, Wave 1, autonomous: yes**

All TRAIN-01 through TRAIN-04 requirements are addressed in a single script. No dependencies between tasks within the plan.

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Training-serving feature skew | HIGH | Feature window code reviewed above — document constants in comments |
| `bool("False") == True` label trap | HIGH | Use `.map({'True': 1, 'False': 0})` with assertion |
| Recall < 0.80 from low data volume | MEDIUM | Print row count; fallback to XGBoost with `scale_pos_weight` |
| Leakage from `rules_triggered` | HIGH | Excluded — only in `fraud_alerts` table, not `transactions` |
| `merchant_category` unseen at inference | MEDIUM | `handle_unknown='ignore'` in OneHotEncoder |
| Cold-start ratio NaN → div/0 | MEDIUM | Fill NaN → 1.0 (same as processor behavior) |
