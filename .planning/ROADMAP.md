# Roadmap: Fraud Detection Pipeline

## Milestones

- ✅ **v1.0 Streaming Fraud Pipeline** - Phases 1-5 (shipped pre-GSD)
- 🚧 **v2.0 ML Fraud Scoring** - Phases 6-9 (in progress)

## Overview

v1.0 delivered the full streaming pipeline: generator → Kafka → processor → PostgreSQL → Streamlit dashboard with rule-based fraud detection. v2.0 layers a trained ML model (Random Forest / XGBoost) on top: schema updated to carry an `ml_score` column, a training script that reads from the existing `transactions` table, in-process inference wired into the processor Kafka loop, and the dashboard updated to display real ML probabilities per transaction.

The four v2.0 phases execute in strict dependency order — schema before training, training artifact before processor rebuild, processor running before dashboard can display scores.

## Phases

<details>
<summary>✅ v1.0 Streaming Fraud Pipeline (Phases 1-5) - SHIPPED pre-GSD</summary>

Phases 1-5 were completed before GSD tooling was in place. The shipped system includes:
- Transaction streaming: generator → Kafka → processor → PostgreSQL
- 3 fraud detection rules: `high_amount`, `high_velocity`, `unusual_amount`
- Isolated user pools (SMALL_POOL, VELOCITY_POOL, GENERAL_POOL)
- Streamlit dashboard with auto-refresh (port 8501)
- Docker Compose orchestration of 6 services
- Transaction validation layer (`data_quality.py`)

</details>

### 🚧 v2.0 ML Fraud Scoring (In Progress)

**Milestone Goal:** Replace the trivial rule-count `fraud_score` with a trained ML model that scores each transaction 0.0–1.0 in real time inside the processor, stores that score per transaction, and surfaces it on the dashboard.

## Phase Details

### Phase 6: Schema and Dependencies
**Goal**: The database schema and ML library dependencies are in place so that every downstream phase can build on a stable foundation.
**Depends on**: Phases 1-5 (v1.0 pipeline shipped)
**Requirements**: INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "\d transactions"` shows an `ml_score` column of type `numeric(5,4)`
  2. `docker-compose build processor` completes without package resolution errors for scikit-learn, xgboost, joblib, pandas, or numpy
  3. A file at `src/model/` directory path exists inside the processor container (visible via `docker exec ... ls /app/src/model`)
  4. `docker-compose up -d` brings all 6 services healthy after the schema migration run with `down -v`
**Plans**: 1 plan

Plans:
- [ ] 06-01-PLAN.md — Add ml_score column, pin ML dependencies, create model directory, validate full stack

### Phase 7: Training Pipeline
**Goal**: A training script runs against the PostgreSQL `transactions` table, engineers the required features, and produces a serialized model artifact at `src/model/fraud_model.joblib` ready to be baked into the processor image.
**Depends on**: Phase 6
**Requirements**: TRAIN-01, TRAIN-02, TRAIN-03, TRAIN-04
**Success Criteria** (what must be TRUE):
  1. Running `python src/train_model.py` (against port 5433) completes without error and prints PR-AUC and fraud-class recall (not raw accuracy)
  2. The script prints a class distribution confirming both fraud and non-fraud labels are present (assertion `nunique() == 2` passes)
  3. `src/model/fraud_model.joblib` exists on the filesystem after the script completes
  4. Printed evaluation shows fraud-class recall >= 0.80 on the held-out validation split
**Plans**: 1 plan

Plans:
- [ ] 07-01-PLAN.md -- Write train_model.py: feature engineering, balanced RandomForest Pipeline, PR-AUC/recall evaluation, joblib serialization

### Phase 8: Processor Integration
**Goal**: The processor loads the trained model once at startup and writes a real `ml_score` float (0.0–1.0) to the `transactions` table for every Kafka message processed, while keeping all existing rule-based detection active.
**Depends on**: Phase 7 (requires `fraud_model.joblib`), Phase 6 (requires `ml_score` column)
**Requirements**: PROC-01, PROC-02, PROC-03, PROC-04
**Success Criteria** (what must be TRUE):
  1. After `docker-compose build processor && docker-compose up -d processor`, the processor logs show "Model loaded" (or equivalent) once at startup — not once per Kafka message
  2. `SELECT ml_score FROM transactions WHERE ml_score IS NOT NULL LIMIT 10` returns rows with float values between 0 and 1 (not NULL for every row)
  3. `SELECT COUNT(*) FROM transactions WHERE ml_score IS NULL` approaches 0 after the processor runs for 60+ seconds
  4. Transactions flagged by existing rules (`high_amount`, `high_velocity`, `unusual_amount`) still appear in `fraud_alerts` table — rule-based detection continues to fire alongside ML scoring
**Plans**: TBD

### Phase 9: Dashboard Integration
**Goal**: The Streamlit dashboard displays each transaction's ML fraud score as a percentage (0–100%), replacing the previous rule-count-based fraud rate column, so the ML output is visible to a viewer without database access.
**Depends on**: Phase 8 (requires `ml_score` populated in DB)
**Requirements**: DASH-01
**Success Criteria** (what must be TRUE):
  1. The transaction table on the dashboard at `localhost:8501` shows an `ml_score` column with values in the range 0%–100% (not 0.0–1.0 raw floats and not the old 0.33/0.67/1.0 rule-count values)
  2. High-risk transactions (those also flagged by rules) show noticeably higher ML score percentages than typical non-fraud transactions in the same view
  3. The dashboard auto-refreshes every 10 seconds and the ML score column updates as new transactions are processed
**Plans**: TBD

## Progress

**Execution Order:** 6 → 7 → 8 → 9 (strict — no phase can safely swap order)

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-5. Streaming Pipeline | v1.0 | - | Complete | pre-GSD |
| 6. Schema and Dependencies | 1/1 | Complete   | 2026-03-09 | - |
| 7. Training Pipeline | v2.0 | 0/1 | Planned | - |
| 8. Processor Integration | v2.0 | 0/TBD | Not started | - |
| 9. Dashboard Integration | v2.0 | 0/TBD | Not started | - |
