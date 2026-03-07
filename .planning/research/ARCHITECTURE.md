# Architecture Research

**Domain:** ML scoring integration into existing streaming fraud detection pipeline
**Researched:** 2026-03-06
**Confidence:** HIGH (based on direct codebase inspection)

## Standard Architecture

### System Overview — Current (v1.0)

```
generator.py
    |
    | JSON → Kafka topic: payment-transactions
    |
processor.py
    |-- validate_transaction()        [data_quality.py]
    |-- FraudDetector.detect_fraud()  [in-memory rules]
    |-- write_to_db()
         |-- Transaction row          [db_setup.Transaction]
         |-- FraudAlert row (if fraud)[db_setup.FraudAlert]
    |
PostgreSQL
    |-- transactions table
    |-- fraud_alerts table
    |
dashboard.py  [reads PostgreSQL directly via SQLAlchemy]
```

### System Overview — Target (v2.0, this milestone)

```
src/train_model.py  (NEW — run offline, outside Docker)
    |-- reads transactions from PostgreSQL
    |-- engineers features
    |-- trains RandomForest/XGBoost
    |-- writes model artifact → src/model/fraud_model.pkl
    |
[model artifact is baked into Docker image at build time]
    |
processor.py  (MODIFIED)
    |-- validate_transaction()          [data_quality.py — unchanged]
    |-- FraudDetector.detect_fraud()    [rules unchanged, kept as fallback]
    |-- MLScorer.predict(tx, detector)  [NEW class, in-process, loads pkl at startup]
    |-- write_to_db()                   [MODIFIED — writes ml_score]
         |-- Transaction row            [MODIFIED — ml_score column added]
         |-- FraudAlert row (if fraud)  [unchanged]
    |
PostgreSQL
    |-- transactions table              [MODIFIED — ml_score NUMERIC(5,4) column added]
    |-- fraud_alerts table              [unchanged]
    |
dashboard.py  (MODIFIED)
    |-- new query reads ml_score from transactions
    |-- replaces fraud_rate column with avg ml_score metric
    |-- adds ml_score per-transaction view
```

### Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `train_model.py` (NEW) | Offline training script: query DB, engineer features, fit model, save pkl | `src/train_model.py` |
| `fraud_model.pkl` (NEW) | Serialized scikit-learn/xgboost pipeline artifact | `src/model/fraud_model.pkl` |
| `MLScorer` class (NEW) | Load pkl at startup, expose `.predict(tx, detector) -> float` | inside `src/processor.py` |
| `FraudDetector` (modified) | Existing rule engine — unchanged logic; in-memory history reused by MLScorer for velocity features | `src/processor.py` |
| `write_to_db()` (modified) | Accept and persist `ml_score` on the Transaction row | `src/processor.py` |
| `Transaction` model (modified) | Add `ml_score = Column(Numeric(5, 4))` | `src/db_setup.py` |
| `dashboard.py` (modified) | Read `ml_score` from transactions; surface it as a metric and per-row column | `src/dashboard.py` |

## Recommended Project Structure

```
src/
├── generator.py          # unchanged
├── processor.py          # MODIFIED — add MLScorer class, pass ml_score to write_to_db
├── dashboard.py          # MODIFIED — add ml_score queries and display
├── db_setup.py           # MODIFIED — add ml_score column to Transaction model
├── data_quality.py       # unchanged
├── train_model.py        # NEW — offline training script
└── model/
    └── fraud_model.pkl   # NEW — artifact written by train_model.py, read by processor
```

### Structure Rationale

- **`src/model/`:** Keeps the artifact co-located with src so Docker's `COPY src/ /app/src/` (or equivalent) includes it automatically. No path gymnastics at load time.
- **`train_model.py` in `src/`:** Consistent with the project convention that all Python source lives in `src/`. Can be run locally pointing at the external PostgreSQL port (5433).
- **`MLScorer` inside `processor.py`:** The constraint is no new Docker services. Co-locating the class in the same file avoids an extra module import chain and keeps the startup sequence explicit.

## Architectural Patterns

### Pattern 1: Load-Once In-Process Inference

**What:** Model is deserialized from disk once at processor startup (inside `consume_and_process()`), held in a module-level or instance variable, and called synchronously per message in the Kafka poll loop.

**When to use:** Single-process consumer where the model artifact is small enough to fit in RAM and inference latency is acceptable inside the poll loop. Correct for this project.

**Trade-offs:** Startup adds ~1–3 seconds for model load. Inference adds <5ms per transaction for a small RandomForest/XGBoost. Model is stale until the container is rebuilt and restarted — acceptable for this milestone since retraining is out of scope.

**Example:**
```python
# Inside consume_and_process(), before the poll loop:
scorer = MLScorer(model_path="src/model/fraud_model.pkl")

# Inside the loop, after detect_fraud():
ml_score = scorer.predict(tx, detector)
write_to_db(session, tx, result, ml_score)
```

### Pattern 2: Feature Reuse from In-Memory FraudDetector State

**What:** `MLScorer.predict()` accepts the `FraudDetector` instance as a parameter to read `user_transactions[user_id]` for velocity and average-amount features — the same data the rule engine already computed.

**When to use:** When the ML features overlap with rule features and the history is already maintained in memory. Avoids a second DB round-trip per transaction.

**Trade-offs:** Couples `MLScorer` to `FraudDetector`'s internal data structure. Acceptable because both live in the same file and this project is not a library.

**Example:**
```python
class MLScorer:
    def predict(self, tx: dict, detector: FraudDetector) -> float:
        history = detector.user_transactions[tx['user_id']]
        velocity = len([t for t in history
                        if tx_timestamp - t['timestamp'] < timedelta(minutes=5)])
        avg_amount = (sum(t['amount'] for t in history) / len(history)
                      if history else tx['amount'])
        features = self._build_feature_vector(tx, velocity, avg_amount)
        return float(self.model.predict_proba([features])[0][1])
```

### Pattern 3: Schema Migration via `create_all` with `checkfirst`

**What:** SQLAlchemy's `Base.metadata.create_all(engine)` (the existing `init_db()`) does not alter existing tables — it only creates missing ones. Adding `ml_score` to the `Transaction` ORM model requires an explicit `ALTER TABLE` or a `docker-compose down -v` + restart to recreate tables from scratch.

**When to use:** For this project, `docker-compose down -v` is the sanctioned approach (documented in CLAUDE.md). No Alembic migration needed.

**Trade-offs:** Data is wiped on schema change. Acceptable since training data is synthetic and regenerated. If data must be preserved, the correct path is `ALTER TABLE transactions ADD COLUMN ml_score NUMERIC(5,4)` run once directly against the DB.

## Data Flow

### v2.0 Per-Transaction Flow

```
Kafka message (JSON)
    ↓
validate_transaction(tx)          — data_quality.py, unchanged
    ↓ (valid)
FraudDetector.detect_fraud(tx)    — returns result dict with rules_triggered
    ↓
MLScorer.predict(tx, detector)    — reads detector.user_transactions for features
    ↓                               returns float 0.0–1.0
write_to_db(session, tx, result, ml_score)
    ↓
transactions row                  — now includes ml_score
fraud_alerts row                  — if is_fraud (rule-based gate, unchanged)
    ↓
dashboard.py SQL queries          — SELECT ml_score FROM transactions
    ↓
Streamlit UI                      — shows ml_score per transaction
```

### Training Data Flow (offline, one-time before container rebuild)

```
PostgreSQL (port 5433, external)
    ↓  SELECT * FROM transactions WHERE is_fraud IS NOT NULL
train_model.py
    ↓  feature engineering
    ↓  train RandomForest / XGBoost
    ↓  model.fit(X_train, y_train)
src/model/fraud_model.pkl         — written to disk
    ↓
docker-compose build processor    — COPY bakes pkl into container image
    ↓
processor container startup       — MLScorer loads pkl from /app/src/model/fraud_model.pkl
```

### Key Data Flows

1. **ml_score write path:** `MLScorer.predict()` → `write_to_db()` argument → `Transaction.ml_score` column → `session.merge()` → PostgreSQL `transactions.ml_score`
2. **ml_score read path:** `dashboard.py` SQL `SELECT transaction_id, ml_score FROM transactions ORDER BY timestamp DESC LIMIT 50` → pandas DataFrame → `st.dataframe()`
3. **Feature reuse path:** `FraudDetector.user_transactions[user_id]` (already populated by `detect_fraud()`) → `MLScorer.predict()` reads it for velocity count and average amount without an extra DB query

## Integration Points

### New vs Modified Files — Explicit List

| File | Status | Change Summary |
|------|--------|----------------|
| `src/train_model.py` | NEW | Offline training script; reads PostgreSQL, writes pkl |
| `src/model/fraud_model.pkl` | NEW ARTIFACT | Written by `train_model.py`; read by `MLScorer` at startup |
| `src/processor.py` | MODIFIED | Add `MLScorer` class; add `ml_score` param to `write_to_db()`; call `scorer.predict()` in loop |
| `src/db_setup.py` | MODIFIED | Add `ml_score = Column(Numeric(5, 4))` to `Transaction` model |
| `src/dashboard.py` | MODIFIED | Add SQL query for `ml_score`; update displayed columns |
| `requirements.txt` | MODIFIED | Add `scikit-learn==1.4.x` and/or `xgboost==2.x`, `joblib` |
| `src/generator.py` | UNCHANGED | No changes needed |
| `src/data_quality.py` | UNCHANGED | No changes needed |
| `docker-compose.yml` | UNCHANGED | No new services; processor build already uses `build: .` |

### Build Order for Phases

The correct dependency order is:

```
Phase 1: Schema + ORM change
    db_setup.py  →  add ml_score column
    docker-compose down -v && up -d  →  tables recreated with new column
    ↓
Phase 2: Training script
    train_model.py  →  must run AFTER transactions accumulate in DB
    produces  src/model/fraud_model.pkl
    ↓
Phase 3: Processor integration
    MLScorer class in processor.py  →  requires pkl to exist (train first)
    write_to_db() updated to accept ml_score  →  requires schema from Phase 1
    docker-compose build processor && docker-compose up -d processor
    ↓
Phase 4: Dashboard
    dashboard.py  →  requires ml_score column (Phase 1) to be populated (Phase 3)
    docker-compose build dashboard && docker-compose up -d dashboard
```

**Critical dependency:** `train_model.py` must run and produce a pkl BEFORE building the processor container. The pkl must exist at `src/model/fraud_model.pkl` before `docker-compose build`.

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `MLScorer` ↔ `FraudDetector` | Direct Python object reference — `scorer.predict(tx, detector)` | Both in `processor.py`; no interface contract needed |
| `train_model.py` ↔ `processor.py` | File system — `src/model/fraud_model.pkl` | Baked into Docker image at build time; not a runtime dependency |
| `processor.py` ↔ `db_setup.py` | SQLAlchemy ORM import — `from db_setup import Transaction` | `ml_score` field added to ORM model; processor just sets it |
| `dashboard.py` ↔ PostgreSQL | Raw SQL via `pd.read_sql()` | Dashboard does not import ORM models; SQL must reference `transactions.ml_score` |

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| PostgreSQL (training) | `psycopg2` / `SQLAlchemy` — direct connection from host on port 5433 | `train_model.py` runs on the host, not inside Docker; uses external port |
| PostgreSQL (inference) | Existing `DATABASE_URL` env var — no change | `processor.py` already connects; just writes one more column |

## Anti-Patterns

### Anti-Pattern 1: Loading the Model Inside the Poll Loop

**What people do:** Call `joblib.load("fraud_model.pkl")` on every Kafka message instead of at startup.

**Why it's wrong:** File I/O on every message at 10 tx/sec adds ~50–200ms of disk latency per transaction and defeats the purpose of in-process inference.

**Do this instead:** Load once in `consume_and_process()` before the `while True` loop. Pass the `MLScorer` instance into the loop.

### Anti-Pattern 2: Querying PostgreSQL for User History at Inference Time

**What people do:** Issue a `SELECT amount FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 100` inside `MLScorer.predict()` to get velocity and average-amount features.

**Why it's wrong:** Adds a synchronous DB round-trip (5–20ms) inside the Kafka poll loop for every message. The same data already exists in `detector.user_transactions`.

**Do this instead:** Pass the `FraudDetector` instance to `MLScorer.predict()` and read `detector.user_transactions[user_id]` directly.

### Anti-Pattern 3: Adding a New Docker Service for Inference

**What people do:** Create a Flask/FastAPI model-serving container and call it via HTTP from `processor.py`.

**Why it's wrong:** Violates the explicit constraint ("no new Docker services"), adds network latency, and requires service discovery. Unnecessary for a single-consumer pipeline at this scale.

**Do this instead:** In-process inference inside `processor.py` as described.

### Anti-Pattern 4: Storing ml_score Only in fraud_alerts

**What people do:** Write `ml_score` to `fraud_alerts.fraud_score` (already exists) and only for transactions flagged by rules.

**Why it's wrong:** The PROJECT.md requirement is "ML fraud score stored per transaction" — this means every transaction, not just rule-flagged ones. Storing it only in `fraud_alerts` means clean transactions have no score visible on the dashboard.

**Do this instead:** Add `ml_score` as a column on `transactions` (not `fraud_alerts`). Every transaction row gets a score regardless of whether rules fired.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current (portfolio) | In-process pkl, single processor instance, synchronous DB writes — correct |
| Production (10K tx/sec) | Extract MLScorer to dedicated inference service, async DB writes, connection pooling |
| Production (model drift) | Add MLflow tracking, scheduled retraining job, model versioning — out of scope for v3+ |

## Sources

- Direct inspection of `src/processor.py`, `src/db_setup.py`, `src/dashboard.py`, `src/generator.py`
- `.planning/PROJECT.md` — constraint: no new Docker services; ml_score on transactions table
- `.planning/codebase/ARCHITECTURE.md` — existing layer boundaries and data flow
- `docker-compose.yml` — confirms `build: .` for processor; all services on `fraud-net`
- `requirements.txt` — confirms scikit-learn and xgboost not yet installed; joblib needed for pkl serialization
- CLAUDE.md — `docker-compose down -v` as sanctioned DB wipe/recreate approach

---
*Architecture research for: ML scoring integration into streaming fraud detection pipeline*
*Researched: 2026-03-06*
