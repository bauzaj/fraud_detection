# Feature Research

**Domain:** ML Fraud Scoring on Tabular Transaction Data (Random Forest / XGBoost)
**Researched:** 2026-03-06
**Confidence:** HIGH (tabular fraud detection with tree-based models is mature and well-documented)

---

## Context: What Is Being Added

This is a SUBSEQUENT MILESTONE. The pipeline already has:
- Rule-based detection (`high_amount`, `high_velocity`, `unusual_amount`)
- PostgreSQL `transactions` table with columns: `transaction_id`, `timestamp`, `user_id`, `merchant_id`, `amount`, `card_last_4`, `merchant_category`, `is_fraud` (String ground truth)
- In-memory `FraudDetector` with per-user transaction history (last 100 transactions)

The ML model must be trained offline on that table and run inference inside `processor.py` per Kafka message, storing a `ml_score` (0–1 float) per transaction.

---

## Feature Landscape

### Table Stakes (Users Expect These)

These are the minimum features needed for a tree-based fraud model to perform meaningfully on this dataset. Missing any of these means the model will fail to detect one or more of the three fraud patterns.

| Feature | Why Expected | Complexity | Schema Dependency | Notes |
|---------|--------------|------------|-------------------|-------|
| `amount` (raw) | Direct signal for `high_amount` fraud ($1,100–$2,500). Most important single feature in tabular fraud. | LOW | `transactions.amount` (exists) | No transformation needed; trees handle scale natively |
| `amount_vs_user_avg_ratio` | Core signal for `unusual_amount` fraud (3.1–4.5x user avg). Without this ratio, the model cannot distinguish a user who normally spends $200 from one spiking to $800. | MEDIUM | Requires per-user history aggregation from `transactions` table | Must be computed at inference time using same in-memory history as existing `FraudDetector` |
| `tx_count_last_5min` | Core signal for `velocity` fraud (10-tx burst in 50ms intervals). This is the primary count-based velocity feature. | MEDIUM | Requires in-memory timestamp history per user (already exists in `FraudDetector`) | Reuse existing `user_transactions` dict |
| `hour_of_day` (0–23) | Time-of-day is universally table-stakes in fraud models. Fraud patterns cluster at night/early morning in real systems. In this synthetic dataset, all hours are equally likely, but the feature must still be present for any production-credible model. | LOW | `transactions.timestamp` (exists) | Extract with `datetime.hour` |
| `merchant_category` (encoded) | Category (`retail`, `dining`, `travel`, `online`, `gas`) captures context. `online` and `travel` are higher-risk in real fraud; model should learn category-to-fraud correlation from training data. | LOW | `transactions.merchant_category` (exists) | One-hot encode or ordinal encode; 5 categories only |
| `is_fraud` label (training only) | Ground truth for supervised training. The generator sets this correctly per fraud pattern. | LOW | `transactions.is_fraud` (exists, String type) | Cast `"True"` / `"False"` strings to int (0/1) at training time — schema bug documented in PROJECT.md |

### Differentiators (Competitive Advantage for Portfolio)

Features that lift model performance beyond baseline and demonstrate ML engineering depth.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| `user_tx_count_total` (lifetime) | Distinguishes new accounts (high fraud risk in real systems) from established users. In this dataset, SMALL_POOL users are seeded with 3 history transactions — total count < 10 may be a weak signal. | LOW | Computed from in-memory history length | Easy win; already have the data |
| `amount_user_stddev` | Standard deviation of user's past amounts. A user with stddev=5 spiking to $800 is more anomalous than one with stddev=200. Directly supports `unusual_amount` detection beyond a simple ratio. | MEDIUM | Requires storing amounts in history (already stored) | More stable than ratio alone when history is short |
| `tx_count_last_1hr` | Broader velocity window beyond 5-minute burst. Catches slower velocity patterns. | LOW | Same timestamp history, different window | Add as complement to 5-min count |
| `merchant_id` frequency encoding | Encodes merchant by fraud rate seen during training. Rare merchants may have higher fraud concentration. | MEDIUM | `transactions.merchant_id` (exists); ~900 merchant IDs (merch_100–merch_999) | Use mean-target encoding; risk of leakage if not done with holdout — requires care |
| `day_of_week` (0–6) | Weekday vs weekend patterns. In real systems, weekend transactions have different baselines. | LOW | `transactions.timestamp` (exists) | Extract with `datetime.weekday()` |
| `amount_percentile_in_category` | Is this amount unusually large for its merchant category? Normalizes amount within category context. | HIGH | Requires computing category-level statistics at training time and storing for inference | May over-engineer for synthetic data; defer unless model performance needs lifting |
| `time_since_last_tx_seconds` | Inter-transaction gap. Very short gaps (< 1s) directly signal velocity bursts. | MEDIUM | Requires tracking last transaction timestamp per user in-memory | Strong signal for velocity pattern — the generator spaces velocity bursts at 50ms |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| `card_last_4` as a feature | Sounds like a useful ID | Only 4 digits → very high cardinality with no fraud signal; in synthetic data it's randomly generated per transaction so it carries zero information | Drop entirely |
| `transaction_id` as a feature | Unique identifier | Pure random UUID; zero predictive value; causes memorization not generalization | Drop entirely |
| `merchant_id` raw (high cardinality label encoding) | Many merchants exist | 900 unique IDs; naive label encoding creates arbitrary ordinal relationships that mislead tree splits | Use mean-target (frequency) encoding or drop |
| `location` fields (lat/lon) | Geolocation sounds fraud-relevant | Not stored in `transactions` table (only in Kafka message, not persisted to DB); would require schema change | Defer to v3+ if location is persisted |
| Real-time SMOTE during inference | Oversample minority class | SMOTE is a training-time technique only; applying it at inference time is not meaningful and would corrupt scores | Apply SMOTE/class weighting only during offline model training |
| Deep learning / neural nets on this schema | Higher capacity model | Tabular data with <10 features and ~thousands of rows performs better with tree-based models; neural nets need large datasets and careful tuning | Use Random Forest or XGBoost |
| Separate ML service / API | Microservice pattern | Out of scope per PROJECT.md; adds operational overhead for no benefit at this scale | Run inference in-process in `processor.py` |

---

## Feature Dependencies

```
[amount_vs_user_avg_ratio]
    └──requires──> [per-user amount history] (in-memory FraudDetector.user_transactions)
                       └──requires──> [user_transactions populated before inference runs]

[tx_count_last_5min]
    └──requires──> [per-user timestamp history] (in-memory FraudDetector.user_transactions)

[time_since_last_tx_seconds]
    └──requires──> [per-user timestamp history] (same dict)

[amount_user_stddev]
    └──requires──> [per-user amount history] (same dict, at least 2 entries)

[merchant_id mean-target encoding]
    └──requires──> [training data with fraud labels] ──must be computed offline──> [encoding map stored as artifact]
                       └──risk──> [target leakage if not computed on training fold only]

[ML model training]
    └──requires──> [is_fraud label cast from String to int]
                       └──schema note──> ["True"/"False" strings in DB — cast at training time]

[ml_score column]
    └──requires──> [ALTER TABLE transactions ADD COLUMN ml_score NUMERIC(5,4)]
                       └──requires──> [db_setup.py update + migration]
```

### Dependency Notes

- **Velocity and avg-ratio features require in-memory history populated BEFORE the current transaction is appended.** The existing `FraudDetector.detect_fraud` appends to history AFTER computing rules — this ordering must be preserved for ML feature extraction.
- **`is_fraud` String-to-int cast** is required at training time. `"True"` → `1`, `"False"` → `0`. Do not attempt to fix the schema type during this milestone (risks breaking existing rule logic).
- **Mean-target encoding for `merchant_id`** must be computed on training data only to prevent leakage. If cross-validation is used, compute encoding inside each fold.
- **`ml_score` DB column** does not exist yet. Requires a schema migration (ALTER TABLE or SQLAlchemy model update + `create_all` with `checkfirst=True`).

---

## Class Imbalance

This is a critical concern for fraud detection. The generator runs at `fraud_rate=0.03` (3%). The resulting training set will be approximately **97% non-fraud, 3% fraud**.

### Expected Impact

| Model | Without Handling | With Handling |
|-------|-----------------|---------------|
| Random Forest | Predicts everything as non-fraud; high accuracy, near-zero recall on fraud | `class_weight='balanced'` fixes this without data augmentation |
| XGBoost | Same collapse toward majority class | `scale_pos_weight = (n_negative / n_positive) ≈ 32` corrects gradient weighting |

### Recommended Approach (in priority order)

1. **Class weighting (PRIMARY):** `class_weight='balanced'` (Random Forest) or `scale_pos_weight` (XGBoost). Zero data augmentation needed. Works correctly with the existing dataset size. No inference-time complexity added. **HIGH confidence this is the right choice.**
2. **Threshold tuning (SECONDARY):** Default threshold of 0.5 will likely be too conservative. Tune on validation set to find threshold maximizing F1 or recall at acceptable precision. Store threshold as a config constant, not hardcoded.
3. **SMOTE (AVOID for first pass):** Oversamples minority class via interpolation. Adds training complexity, risk of overfitting to synthetic minority samples, and no benefit when class weighting achieves the same effect. Revisit only if class weighting proves insufficient.

### Expected Metrics

| Metric | Realistic Expectation (synthetic data) | Notes |
|--------|----------------------------------------|-------|
| Accuracy | >97% (misleading) | Don't optimize for this |
| Precision (fraud class) | 70–90% | High achievable — fraud patterns are mechanistic |
| Recall (fraud class) | 80–95% | Target this; missing fraud is costly |
| AUC-ROC | 0.92–0.99 | Synthetic data has near-deterministic patterns |
| F1 (fraud class) | 0.80–0.95 | Primary evaluation metric |

**Why such high expected performance:** The fraud patterns in this dataset are mechanistic (rule-based generator), not adversarial. `amount > $1100` maps cleanly to `high_amount`; burst of 10 transactions maps to `velocity`. A Random Forest with the right features will essentially re-learn the generator's rules. This is expected and correct for a portfolio project — the goal is demonstrating the ML engineering pipeline, not outperforming rules.

### Precision-Recall Tradeoff

- **High recall, lower precision** (catch most fraud, some false positives): Better for fraud domain; false negatives (missed fraud) are more costly than false positives (blocked legitimate transactions).
- **Practical choice:** Tune threshold to achieve recall >= 0.85 on validation set, then check resulting precision. Accept precision as low as 0.60 if recall stays high.

---

## Feature-to-Pattern Mapping

Critical for understanding which features the model will use for each fraud type.

| Fraud Pattern | Generator Behavior | Key Detecting Features | Model Behavior |
|---------------|-------------------|----------------------|----------------|
| `high_amount` | Single tx, $1,100–$2,500, GENERAL_POOL users | `amount` (raw), `amount_vs_user_avg_ratio` | Raw `amount` alone likely sufficient; XGBoost will find split near $1,000 |
| `velocity` | 10-tx burst at 50ms intervals, VELOCITY_POOL | `tx_count_last_5min`, `time_since_last_tx_seconds` | `tx_count_last_5min` >= 8 is a near-perfect signal; inter-tx gap is complementary |
| `unusual_amount` | Spike 3.1–4.5x user avg, SMALL_POOL | `amount_vs_user_avg_ratio`, `amount_user_stddev` | Ratio feature is essential; without it, `high_amount` threshold alone misses spikes that are < $1,000 |

---

## MVP Definition

### Launch With (v2.0 — This Milestone)

These features are needed for the model to detect all three fraud patterns:

- [ ] `amount` — raw, no transform required
- [ ] `amount_vs_user_avg_ratio` — essential for `unusual_amount` detection
- [ ] `tx_count_last_5min` — essential for `velocity` detection
- [ ] `hour_of_day` — standard time feature, low complexity
- [ ] `merchant_category` — one-hot encoded (5 categories)
- [ ] `user_tx_count_total` — history length as a feature (already available)
- [ ] `is_fraud` label cast (String → int 0/1) — required for training

### Add After Validation (v2.x)

Features to add if baseline model has recall gaps:

- [ ] `time_since_last_tx_seconds` — if velocity recall is below target; helps distinguish burst timing
- [ ] `amount_user_stddev` — if `unusual_amount` recall is below target; more stable than ratio alone
- [ ] `tx_count_last_1hr` — if broader velocity window catches patterns the 5-min window misses
- [ ] `day_of_week` — add if dashboard shows temporal clustering in false negatives

### Future Consideration (v3+)

- [ ] `merchant_id` mean-target encoding — adds leakage risk complexity; defer until proper cross-val pipeline exists
- [ ] `amount_percentile_in_category` — requires category-level stat storage; over-engineering for synthetic data
- [ ] Location features (lat/lon) — not persisted to DB currently; requires schema and pipeline changes

---

## Feature Prioritization Matrix

| Feature | Detection Value | Implementation Cost | Priority |
|---------|----------------|---------------------|----------|
| `amount` | HIGH | LOW | P1 |
| `amount_vs_user_avg_ratio` | HIGH | MEDIUM | P1 |
| `tx_count_last_5min` | HIGH | MEDIUM | P1 |
| `merchant_category` (encoded) | MEDIUM | LOW | P1 |
| `hour_of_day` | LOW | LOW | P1 |
| `user_tx_count_total` | LOW | LOW | P1 |
| `time_since_last_tx_seconds` | MEDIUM | MEDIUM | P2 |
| `amount_user_stddev` | MEDIUM | MEDIUM | P2 |
| `tx_count_last_1hr` | LOW | LOW | P2 |
| `day_of_week` | LOW | LOW | P2 |
| `merchant_id` mean-target encoding | LOW | HIGH | P3 |
| `amount_percentile_in_category` | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v2.0 launch — without these, one or more fraud patterns go undetected
- P2: Should have — add when P1 baseline is validated
- P3: Nice to have — defer, adds complexity without clear gain on synthetic data

---

## Schema Changes Required

| Change | Type | Risk | Notes |
|--------|------|------|-------|
| `ALTER TABLE transactions ADD COLUMN ml_score NUMERIC(5,4)` | DDL migration | LOW | Required to persist ML score per transaction; use `checkfirst=True` in SQLAlchemy |
| `is_fraud` cast to int at training time | Application logic | LOW | Do not change DB column type this milestone — risks breaking rule logic that reads String |
| No new columns needed for feature computation | — | — | All features computed from existing columns + in-memory state |

---

## Sources

- Domain knowledge: Tabular fraud detection is a canonical ML problem; Random Forest and XGBoost on transaction data is extensively documented in academic literature (e.g., IEEE S&P, KDD, ACM CCS proceedings) and production systems (Stripe, PayPal engineering blogs). Feature engineering patterns described here are standard in the field. **Confidence: HIGH**
- Schema analysis: Derived from direct inspection of `src/db_setup.py`, `src/generator.py`, `src/processor.py` in this repository. **Confidence: HIGH**
- Class imbalance guidance: scikit-learn docs (class_weight='balanced'), XGBoost docs (scale_pos_weight) — both parameters are stable, well-documented API features. **Confidence: HIGH**
- Expected model performance: Based on nature of synthetic/mechanistic fraud patterns in this dataset; actual numbers will vary with training set size and data quality. **Confidence: MEDIUM**

---

*Feature research for: ML Fraud Scoring on tabular payment transaction data*
*Researched: 2026-03-06*
