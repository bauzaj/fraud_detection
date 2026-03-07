# Fraud Detection Pipeline

## What This Is

A real-time payment fraud detection pipeline that streams synthetic transactions through Apache Kafka, applies fraud detection, persists results to PostgreSQL, and visualizes them on a live Streamlit dashboard. Built as a portfolio/learning project to demonstrate streaming data engineering and ML scoring on tabular financial data.

## Core Value

Every transaction is scored for fraud risk in real time — the score is visible on the dashboard and drives downstream alerts.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Transaction streaming pipeline (generator → Kafka → processor → PostgreSQL) — v1.0
- ✓ Rule-based fraud detection: `high_amount`, `high_velocity`, `unusual_amount` — v1.0
- ✓ Isolated user pools (SMALL_POOL, VELOCITY_POOL, GENERAL_POOL) for clean fraud signal — v1.0
- ✓ Streamlit dashboard with live transaction metrics and auto-refresh — v1.0
- ✓ Docker Compose orchestration of 6 services — v1.0
- ✓ Transaction validation layer (`data_quality.py`) — v1.0

### Active

<!-- Current scope: ML Fraud Scoring (v2.0) -->

- [ ] ML model (Random Forest / XGBoost) trained on existing PostgreSQL transaction data
- [ ] Feature engineering: amount, merchant_category, time features (hour/day), user velocity + avg
- [ ] Real-time model inference inside `processor.py` per Kafka message
- [ ] ML fraud score (0–1) stored per transaction in DB (`ml_score` column on `transactions`)
- [ ] Existing rules kept as safety-net fallback alongside ML score
- [ ] Dashboard updated: ML fraud score per transaction replaces fraud rate column

### Out of Scope

- Real-time model retraining — model is trained offline, served statically; v3+ concern
- Separate ML microservice — inference runs in-process in processor, not a separate container
- Model versioning / MLflow — out of scope for this milestone
- Authentication on dashboard — not a priority for this portfolio project
- Dead-letter queue for invalid transactions — deferred

## Context

- PostgreSQL `transactions` table already has `is_fraud` (String ground truth label set by generator), `merchant_category`, `amount`, `user_id`, `timestamp`, `merchant_id` — all features needed for ML are already stored
- `fraud_alerts.fraud_score` currently stores a trivial rule-count ratio (0.33 / 0.67 / 1.0) — this will be replaced by real ML probabilities
- Generator currently sets `is_fraud` as a ground truth flag derived from its fraud patterns — this is the training label
- Existing in-memory user transaction history in `FraudDetector` can be reused to compute velocity features at inference time
- Python 3.11, scikit-learn / xgboost are the natural fit; no model serving framework needed for in-process inference

## Constraints

- **Tech stack**: Python 3.11, Docker Compose — all new code stays in-container; no external ML platforms
- **Inference location**: Model must run inside `processor.py` — no new Docker services for this milestone
- **Training data**: Must use existing PostgreSQL `transactions` table as the sole data source for training
- **No lockfile**: `requirements.txt` only — be precise with versions added

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Kafka + PostgreSQL streaming pipeline | Standard event-driven architecture for real-time fraud | ✓ Good |
| Isolated user pools for fraud patterns | Prevents signal contamination across fraud types | ✓ Good |
| In-memory FraudDetector state (not persisted) | Simple but fragile — loses history on restart | ⚠️ Revisit |
| `is_fraud` stored as String not Boolean | Schema bug — makes DB-level boolean queries unreliable | ⚠️ Revisit |
| ML inference in-process (no separate service) | Simpler for v2; trade-off is coupling model to processor | — Pending |
| Store `ml_score` on `transactions` table | Score every transaction (not just alerts) for dashboard visibility | — Pending |

---
*Last updated: 2026-03-06 after ML Fraud Scoring milestone (v2.0) started*
