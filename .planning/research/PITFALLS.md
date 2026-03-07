# Pitfalls Research: ML Fraud Scoring

**Project:** Fraud Detection Pipeline — v2.0 ML Fraud Scoring
**Date:** 2026-03-06

## Critical Pitfalls

### 1. Label Leakage via Generator-Derived Labels (CRITICAL)

**Risk:** The `is_fraud` column is set by `generator.py` at produce time based on user pool membership and amount thresholds. Training on it means the model learns to reproduce the generator's own rules — not real fraud detection. The model will key on user pool membership (`user_1000`–`1100` = unusual_amount pool) and amount thresholds ($1,100+). This is circular and not generalizable.

**What NOT to use as features:** `rules_triggered`, `fraud_score` from `fraud_alerts`, or any column derived from the processor's rule output.

**Prevention:** Only use raw transaction features as inputs. Evaluate the model honestly — near-perfect metrics are expected because the labels ARE the rules. Document this limitation.

**Phase:** Training pipeline phase — enforce in feature extraction code.

---

### 2. `is_fraud` String Column Corrupts Training Labels (CRITICAL)

**Risk:** The DB stores `"True"` / `"False"` as strings. In Python, `bool("False") == True`. Any training code that does `.astype(bool)` on this column gets an all-positive training set — every transaction looks like fraud.

**Fix:**
```python
df['is_fraud'] = df['is_fraud'].map({'True': 1, 'False': 0})
assert df['is_fraud'].nunique() == 2, "Label encoding failed — both classes must be present"
```

**Prevention:** Add the assertion and verify class distribution before training.

**Phase:** Training pipeline phase — first thing to validate.

---

### 3. Class Imbalance Produces a Useless Model (HIGH)

**Risk:** At ~3% fraud rate, a model that always predicts "not fraud" achieves 97% accuracy. Standard accuracy metrics are meaningless.

**Fix:**
- `class_weight='balanced'` in scikit-learn RandomForest
- `scale_pos_weight ≈ 32` in XGBoost (ratio of negatives to positives)
- Evaluate with `classification_report` focusing on fraud-class recall and F1
- Report PR-AUC, not ROC-AUC or accuracy

**Prevention:** Never report accuracy as the primary metric. Threshold tuning below 0.5 will likely be needed.

**Phase:** Training pipeline phase.

---

### 4. Model Loading Latency Blocks Kafka Consumer Loop (HIGH)

**Risk:** Loading model from disk inside `detect_fraud()` or inside the `while True` loop causes Kafka consumer lag to grow unboundedly. The consumer will fall behind the producer.

**Fix:** Load model once in `FraudDetector.__init__()`, before `consumer.subscribe()` is called. If file is missing, fail fast with a clear error message.

```python
class FraudDetector:
    def __init__(self):
        self.user_transactions = defaultdict(list)
        self.model = joblib.load('src/model/fraud_model.pkl')  # Load once
```

**Prevention:** Never load from disk in the hot path.

**Phase:** Processor integration phase.

---

### 5. Training-Serving Skew on Velocity/Average Features (HIGH)

**Risk:** Training pulls full DB history per user; inference uses the in-memory window (max 100 entries, 5-minute window for velocity). The same feature has different values in each context — model learns one distribution, sees another at inference time.

**Fix:** Feature computation logic must be identical in both `train_model.py` and `processor.py`. Use the same window sizes, same capping logic, same handling of users with < 2 transactions.

**Prevention:** Extract feature computation into a shared function or module used by both training and inference.

**Phase:** Both training and integration phases — verify feature parity.

---

### 6. Synthetic Data Overfit Looks Great, Means Little (MEDIUM)

**Risk:** Generator patterns are perfectly clean (always exactly $1,100–$2,500 for high_amount, exactly 3.1–4.5x average for unusual_amount). Model achieves near-perfect test metrics but has learned the generator's `random.uniform` ranges, not real fraud signal. This will not generalize to real transactions.

**Prevention:** State this limitation honestly in evaluation output. Focus on the pipeline architecture value, not the model's predictive validity. Note: for a portfolio project, this is expected and acceptable.

**Phase:** Training evaluation — add honest commentary.

---

### 7. Cold-Start False Negatives After Processor Restart (MEDIUM)

**Risk:** `FraudDetector.user_transactions` resets on every container restart. Velocity count and user average are 0/undefined for all users immediately after restart. The ML model will compute incorrect features and likely under-score genuine fraud for several minutes.

**Fix (partial):** Pre-warm `user_transactions` from recent DB rows at startup — query the last N transactions per user before entering the consume loop.

**Phase:** Processor integration phase — add pre-warm step as a stretch goal.

---

## Anti-Patterns to Avoid

| Anti-pattern | Why | Alternative |
|---|---|---|
| Using `fraud_score` or `rules_triggered` as ML features | Label leakage — circular | Raw transaction columns only |
| `df['is_fraud'].astype(bool)` | "False" → True in Python | `.map({'True': 1, 'False': 0})` |
| Reporting accuracy as primary metric | Meaningless at 3% fraud rate | PR-AUC, fraud-class recall, F1 |
| Loading model in hot path | Blocks Kafka consumer | Load once in `__init__` |
| Different feature windows in train vs serve | Training-serving skew | Shared feature extraction logic |

---

*Research date: 2026-03-06*
