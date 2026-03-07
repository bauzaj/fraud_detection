# Milestones

## v1.0 — Streaming Fraud Pipeline (Shipped)

**Goal:** Build a real-time streaming pipeline with rule-based fraud detection and live dashboard.

**Shipped:**
- Transaction streaming: generator → Kafka → processor → PostgreSQL
- 3 fraud detection rules: `high_amount`, `high_velocity`, `unusual_amount`
- Isolated user pools for clean fraud signal (SMALL_POOL, VELOCITY_POOL, GENERAL_POOL)
- Streamlit dashboard with auto-refresh
- Docker Compose orchestration (6 services)
- Transaction validation layer

**Phases:** 1–5 (estimated — pre-GSD, not formally tracked)

---

## v2.0 — ML Fraud Scoring (Current)

**Goal:** Replace the trivial rule-count fraud_score with a trained ML model (Random Forest / XGBoost) that scores each transaction in real time inside the processor.

**Target features:**
- ML model trained from existing PostgreSQL transaction data
- Feature engineering: amount, merchant_category, hour/day, velocity, user avg
- Real-time inference in `processor.py`
- `ml_score` (0–1) stored per transaction in DB
- Rules kept as safety-net fallback
- Dashboard: ML score per transaction replaces fraud rate column

**Phases:** 6+ (continuing from pre-GSD phase numbering)
