# Requirements: Fraud Detection Pipeline

**Defined:** 2026-03-06
**Core Value:** Every transaction is scored for fraud risk in real time — the score is visible on the dashboard and drives downstream alerts.

## v2.0 Requirements (ML Fraud Scoring)

### Infrastructure & Schema

- [ ] **INFRA-01**: `ml_score NUMERIC(5,4)` column added to `transactions` table in `db_setup.py`
- [ ] **INFRA-02**: `scikit-learn==1.6.1`, `xgboost==2.1.4`, `joblib==1.4.2`, `pandas==2.2.3`, `numpy==1.26.4` added to `requirements.txt`
- [ ] **INFRA-03**: `src/model/` directory created for model artifact storage

### Training Pipeline

- [ ] **TRAIN-01**: `src/train_model.py` script reads transactions from PostgreSQL and engineers features: `amount`, `tx_count_last_5min`, `amount_vs_user_avg_ratio`, `hour_of_day`, `day_of_week`, `merchant_category`
- [ ] **TRAIN-02**: Training script correctly casts `is_fraud` String column to int labels using `.map({'True': 1, 'False': 0})` with assertion that both classes are present
- [ ] **TRAIN-03**: Model trained with `class_weight='balanced'`; evaluated with PR-AUC and fraud-class recall (not accuracy)
- [ ] **TRAIN-04**: Trained model serialized to `src/model/fraud_model.joblib`

### Processor Integration

- [ ] **PROC-01**: `FraudDetector` loads model artifact once at `__init__` time (not inside the Kafka consumer loop)
- [ ] **PROC-02**: ML fraud probability (0.0–1.0) computed per transaction using same feature windows as training script
- [ ] **PROC-03**: `ml_score` written to `transactions` table for every processed transaction (not just fraud alerts)
- [ ] **PROC-04**: Existing rule-based detection (`high_amount`, `high_velocity`, `unusual_amount`) kept as safety-net alongside ML score

### Dashboard

- [ ] **DASH-01**: Dashboard displays `ml_score` as a fraud probability percentage (0–100%) per transaction, replacing the existing fraud rate column — value derived from `model.predict_proba()` × 100, read from the `ml_score` column on the `transactions` table

## Future Requirements (v3.0+)

### Model Operations

- **MLOPS-01**: Model versioning and experiment tracking (MLflow)
- **MLOPS-02**: Automated retraining trigger when score distribution drifts
- **MLOPS-03**: Cold-start pre-warming — load recent DB history into FraudDetector at startup

### Advanced Features

- **ADV-01**: ML-score-based alert path independent of rule results (alert on high ml_score even when no rule triggers)
- **ADV-02**: Model performance dashboard metrics (live precision/recall)
- **ADV-03**: P2 features: tx_stddev_amount, inter_tx_gap_seconds, 1-hour tx window

## Out of Scope

| Feature | Reason |
|---|---|
| Separate ML microservice | Inference stays in-process — no new Docker services this milestone |
| MLflow / experiment tracking | Over-engineering for a portfolio project at this stage |
| Real-time model retraining | Model trained offline; serve static artifact |
| imbalanced-learn / SMOTE | `class_weight='balanced'` is sufficient for this data |
| Dashboard authentication | Not a priority for this portfolio project |
| Dead-letter queue | Deferred from v1.0 |

## Traceability

| Requirement | Phase | Status |
|---|---|---|
| INFRA-01 | Phase 6 | Pending |
| INFRA-02 | Phase 6 | Pending |
| INFRA-03 | Phase 6 | Pending |
| TRAIN-01 | Phase 7 | Pending |
| TRAIN-02 | Phase 7 | Pending |
| TRAIN-03 | Phase 7 | Pending |
| TRAIN-04 | Phase 7 | Pending |
| PROC-01 | Phase 8 | Pending |
| PROC-02 | Phase 8 | Pending |
| PROC-03 | Phase 8 | Pending |
| PROC-04 | Phase 8 | Pending |
| DASH-01 | Phase 9 | Pending |

**Coverage:**
- v2.0 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-06*
*Last updated: 2026-03-06 after initial v2.0 definition*
