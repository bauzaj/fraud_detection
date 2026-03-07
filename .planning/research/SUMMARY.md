# Project Research Summary

**Project:** Fraud Detection Pipeline — v2.0 ML Fraud Scoring
**Domain:** ML scoring integration into an existing Kafka/PostgreSQL streaming pipeline
**Researched:** 2026-03-06
**Confidence:** HIGH

## Executive Summary

This milestone adds an offline-trained machine learning scoring layer on top of an already-working rule-based fraud detection pipeline. The existing system (Kafka + processor.py + PostgreSQL + Streamlit) is fully functional; the task is to extend it without adding new Docker services, new external dependencies beyond the ML libraries, or runtime complexity. The recommended approach is: train a Random Forest or XGBoost model offline on the `transactions` table, serialize it to `src/model/fraud_model.pkl`, bake the artifact into the processor Docker image at build time, and run synchronous in-process inference inside the Kafka poll loop. The model stores a `ml_score` float (0–1) on every transaction row, which the dashboard then surfaces.

The three fraud patterns in this dataset (high_amount, velocity, unusual_amount) are mechanistic and fully deterministic — the generator's rules will be re-learned by the model with near-perfect precision and recall. This is expected and acceptable for a portfolio project. The engineering value is in the pipeline integration: feature extraction reusing in-memory FraudDetector state, correct label casting, class imbalance handling, and zero training-serving skew. The hardest risks are not algorithmic but operational: a boolean casting bug that silently corrupts all training labels, training-serving skew from inconsistent feature window definitions, and model load latency in the Kafka hot path.

The implementation requires changes to four existing files (processor.py, db_setup.py, dashboard.py, requirements.txt) and two new files (train_model.py, src/model/fraud_model.pkl). No new Docker containers are introduced. The correct build order is: schema migration first, then training script execution, then processor rebuild and restart, then dashboard rebuild. Skipping this order causes failures at every downstream step.

## Key Findings

### Recommended Stack

The ML stack adds five packages to requirements.txt on top of the existing Python 3.11 / Docker Compose / Kafka / PostgreSQL base. All packages are stable, pinned versions — deliberately avoiding recent major-version releases that introduced breaking changes or C-API friction in Docker slim images. The training script runs on the host against the external PostgreSQL port (5433), not inside Docker.

**Core technologies:**
- `scikit-learn==1.6.1`: Provides `RandomForestClassifier`, `Pipeline`, `ColumnTransformer`, `class_weight='balanced'` — latest proven stable; 1.8.0 too recent
- `xgboost==2.1.4`: Stable release with identical scikit-learn Pipeline API; v3.x is a breaking-change major version
- `joblib==1.4.2`: Serialization for numpy-backed model artifacts; preferred over pickle; already a transitive dep of scikit-learn
- `pandas==2.2.3`: Training script only — must NOT be imported in processor.py hot path; v3.0.1 too recent
- `numpy==1.26.4`: Last 1.x LTS — satisfies all three ML libs simultaneously; numpy 2.x has C-API friction in Docker slim images

Explicitly rejected: MLflow, FastAPI/BentoML/Ray Serve, imbalanced-learn/SMOTE, TensorFlow/PyTorch, any new Docker service.

### Expected Features

Six P1 (must-have) features cover all three fraud patterns. Four P2 features improve recall if the baseline falls short. P3 features (merchant_id mean-target encoding, amount_percentile_in_category, location) are over-engineering for synthetic data and should be deferred.

**Must have (table stakes — v2.0):**
- `amount` (raw) — primary signal for high_amount fraud; trees handle scale natively
- `amount_vs_user_avg_ratio` — essential for unusual_amount detection; without it, spikes below $1,000 are invisible
- `tx_count_last_5min` — essential for velocity detection; reuses existing in-memory FraudDetector history
- `merchant_category` (one-hot, 5 categories) — standard context feature; LOW implementation cost
- `hour_of_day` (0–23) — universally table-stakes in fraud models; extracted from timestamp
- `user_tx_count_total` — history length as proxy for account age; already available in-memory
- `is_fraud` label cast (String "True"/"False" → int 1/0) — required at training time; do NOT fix schema type this milestone

**Should have (v2.x — add if recall is below target):**
- `time_since_last_tx_seconds` — inter-transaction gap; strong signal for 50ms velocity burst spacing
- `amount_user_stddev` — more stable than ratio alone when history is short
- `tx_count_last_1hr` — broader velocity window to complement 5-minute count
- `day_of_week` — add if dashboard shows temporal clustering in false negatives

**Defer (v3+):**
- `merchant_id` mean-target encoding — target leakage risk without proper cross-val pipeline
- `amount_percentile_in_category` — requires category-level stat storage; over-engineering for synthetic data
- Location features (lat/lon) — not persisted to DB; requires schema and pipeline changes

**Critical anti-features to drop entirely:** `card_last_4` (zero signal, high cardinality), `transaction_id` (random UUID), `rules_triggered` / `fraud_score` (label leakage from rule engine output).

**Class imbalance handling:** The dataset is ~97% non-fraud. Use `class_weight='balanced'` (Random Forest) or `scale_pos_weight≈32` (XGBoost). Evaluate with fraud-class recall and F1, not accuracy. Tune classification threshold below 0.5 — target recall >= 0.85 on validation set.

### Architecture Approach

The architecture follows a load-once in-process inference pattern: the serialized model is loaded once at processor startup, held in an `MLScorer` instance, and called synchronously per Kafka message. Feature vectors are constructed by reading `detector.user_transactions[user_id]` — the same in-memory dict the rule engine already maintains — avoiding any DB round-trips in the hot path. The model artifact is baked into the processor Docker image at build time. No new services are introduced.

**Major components:**
1. `src/train_model.py` (NEW) — offline training script: connects to PostgreSQL on port 5433, engineers features from the `transactions` table, trains RandomForest/XGBoost, writes `src/model/fraud_model.pkl`
2. `MLScorer` class inside `processor.py` (NEW) — loads pkl once at startup; exposes `.predict(tx, detector) -> float`; reads `detector.user_transactions` for velocity and average-amount features
3. `src/model/fraud_model.pkl` (NEW ARTIFACT) — baked into processor Docker image at build time; read by MLScorer at container startup
4. `db_setup.py` (MODIFIED) — adds `ml_score = Column(Numeric(5, 4))` to the Transaction ORM model
5. `processor.py` (MODIFIED) — calls `scorer.predict()` after `detect_fraud()`, passes `ml_score` to `write_to_db()`
6. `dashboard.py` (MODIFIED) — queries `ml_score` from transactions and surfaces it in the UI

### Critical Pitfalls

1. **`is_fraud` String-to-bool corruption** — `bool("False") == True` in Python; `.astype(bool)` produces an all-positive training set. Fix: `.map({'True': 1, 'False': 0})` with a `assert df['is_fraud'].nunique() == 2` assertion before training.

2. **Training-serving skew on velocity/average features** — Training code and inference code must use identical window sizes, capping logic, and handling of users with < 2 transactions. Divergence causes the model to see a different feature distribution at inference time than it learned from. Fix: extract shared feature computation logic or copy window constants explicitly.

3. **Model loading in the Kafka hot path** — Loading the pkl inside the `while True` poll loop adds 50–200ms of disk I/O per message and causes consumer lag to grow unboundedly. Fix: load once before the loop; fail fast with a clear error if the file is missing.

4. **Class imbalance producing a 97%-accurate but useless model** — Without `class_weight='balanced'` or equivalent, the model predicts "not fraud" for every transaction and reports 97% accuracy. Fix: always use class weighting; always report fraud-class recall and F1, never raw accuracy.

5. **Wrong build order** — Running `train_model.py` before the schema migration means the model trains without the `ml_score` column existing; building the processor image before running `train_model.py` means the pkl is missing at build time. Fix: strictly enforce Phase 1 (schema) → Phase 2 (train) → Phase 3 (processor rebuild) → Phase 4 (dashboard rebuild).

## Implications for Roadmap

Based on research, the architectural dependency chain dictates a strict 4-phase build order. No phase can be safely swapped because each depends on artifacts produced by the prior phase.

### Phase 1: Schema Migration and Dependencies

**Rationale:** The `ml_score` column must exist in PostgreSQL before any other phase can write to it or be tested against it. The requirements.txt must be updated before any Docker rebuild. This phase has no dependencies on any other phase.
**Delivers:** Updated requirements.txt with 5 ML packages; `ml_score NUMERIC(5,4)` column added to the `transactions` table via db_setup.py update and `docker-compose down -v && up -d`; `src/model/` directory created
**Addresses:** Schema dependency from FEATURES.md; STACK.md library versions
**Avoids:** Build-order failure pitfall; prevents downstream phases from failing due to missing column or packages

### Phase 2: Training Pipeline

**Rationale:** `train_model.py` must run after Phase 1 (requires the updated schema and ML packages) and after sufficient transactions have accumulated in the database. The pkl artifact it produces is required before the processor container can be rebuilt in Phase 3.
**Delivers:** `src/train_model.py` implementing feature engineering (6 P1 features), label casting with assertion, class weighting, model training, and pkl serialization to `src/model/fraud_model.pkl`
**Uses:** scikit-learn, xgboost, pandas, numpy, joblib from STACK.md
**Avoids:** is_fraud label corruption pitfall (assertion); class imbalance pitfall (class_weight); synthetic overfit awareness (documented in evaluation output); label leakage pitfall (no rules_triggered or fraud_score in features)

### Phase 3: Processor Integration

**Rationale:** Requires the pkl from Phase 2 and the schema column from Phase 1. This is the most risk-laden phase — it touches the production Kafka consumer loop and must not introduce hot-path latency.
**Delivers:** `MLScorer` class added to processor.py; `write_to_db()` updated to accept and persist `ml_score`; model loaded once at startup; features read from `detector.user_transactions` (no DB round-trips); processor Docker image rebuilt with pkl baked in
**Implements:** Load-once in-process inference pattern; Feature reuse from FraudDetector in-memory state
**Avoids:** Model loading in hot path pitfall; DB round-trip in hot path anti-pattern; training-serving skew (feature windows must match Phase 2 exactly)

### Phase 4: Dashboard Integration

**Rationale:** Must come last — requires `ml_score` column to be populated in the database (depends on Phase 3 running and processing transactions) and the column to exist (depends on Phase 1).
**Delivers:** Updated dashboard.py querying `ml_score` per transaction; new metric showing average ML score; per-transaction score visible in the transaction table
**Avoids:** Querying a column that doesn't exist; displaying misleading accuracy metrics instead of fraud-class recall

### Phase Ordering Rationale

- Phase 1 before all others: Schema changes require a full `docker-compose down -v` which wipes the database. Must happen before any transactions are written with the expectation of an ml_score column.
- Phase 2 before Phase 3: The pkl artifact must exist on the filesystem before `docker-compose build processor` bakes it into the image. Building without the pkl causes a startup failure when MLScorer tries to load it.
- Phase 3 before Phase 4: The dashboard can only display ml_score values after the processor has been writing them. Building the dashboard before Phase 3 completes results in a column that exists but is always NULL.
- Training-serving skew spans Phases 2 and 3: Feature computation constants (velocity window = 5 minutes, max history = 100) must be identical in both files. This is a cross-phase constraint that should be explicitly verified at Phase 3 completion.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Training Pipeline):** Feature engineering for `amount_vs_user_avg_ratio` and `tx_count_last_5min` must exactly mirror the in-memory computation in FraudDetector — inspect current `detect_fraud()` implementation carefully before writing training code.
- **Phase 3 (Processor Integration):** The existing `write_to_db()` function signature needs inspection before modifying to ensure no other callers break; also verify the exact path where pkl will be accessed inside the Docker container (`/app/src/model/fraud_model.pkl`).

Phases with standard patterns (skip research-phase):
- **Phase 1 (Schema Migration):** Well-documented SQLAlchemy pattern; `docker-compose down -v` is the sanctioned approach per CLAUDE.md; no research needed.
- **Phase 4 (Dashboard):** Streamlit `st.dataframe()` with a simple SQL SELECT; standard pandas + Streamlit pattern; no research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions verified from PyPI; rationale grounded in documented breaking changes and Docker compatibility issues |
| Features | HIGH | Derived from direct codebase inspection of db_setup.py, generator.py, processor.py; domain patterns are mature and well-documented in fraud ML literature |
| Architecture | HIGH | Based on direct codebase inspection; build order derived from actual file dependencies; no new infrastructure patterns needed |
| Pitfalls | HIGH | is_fraud casting bug and class imbalance are concrete, verifiable issues; training-serving skew is a well-documented ML engineering failure mode |

**Overall confidence:** HIGH

### Gaps to Address

- **Expected model performance on actual accumulated data:** The research estimates precision 70–90%, recall 80–95% based on synthetic data characteristics. Actual numbers depend on how many transactions are in the DB when training runs — with fewer than ~500 fraud samples, recall may be lower. Flag for validation after Phase 2.
- **Kafka consumer lag impact of ML inference:** Research estimates <5ms per transaction for a small RandomForest/XGBoost. This should be measured after Phase 3 deployment by comparing producer throughput to consumer throughput. No action needed unless lag is observed.
- **Cold-start false negatives after processor restart:** The in-memory `user_transactions` dict resets on container restart. Pre-warming from recent DB rows at startup is documented as a stretch goal in PITFALLS.md. Defer to v2.x unless cold-start misses are observed in testing.
- **`ml_score` threshold for fraud alerting:** The current FraudAlert write path is gated on rule results, not ML score. Whether to add a separate ML-score-based alert path (e.g., ml_score > 0.8 → alert even if rules didn't fire) is out of scope for v2.0 but worth flagging for v2.x.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/processor.py`, `src/db_setup.py`, `src/generator.py`, `src/dashboard.py`, `requirements.txt`, `docker-compose.yml` — schema, data flow, user pools, fraud patterns
- `.planning/PROJECT.md` — constraint: no new Docker services; ml_score on transactions table
- `.planning/codebase/ARCHITECTURE.md` — existing layer boundaries and data flow
- PyPI package metadata — version verification for scikit-learn 1.6.1, xgboost 2.1.4, pandas 2.2.3, numpy 1.26.4, joblib 1.4.2
- scikit-learn documentation — `class_weight='balanced'` API stability
- XGBoost documentation — `scale_pos_weight` parameter

### Secondary (MEDIUM confidence)
- IEEE S&P, KDD, ACM CCS proceedings — tabular fraud detection feature engineering patterns (Random Forest, XGBoost on transaction data is canonical and well-documented)
- Stripe, PayPal engineering blogs — production fraud feature patterns confirming velocity and amount-ratio features as table stakes
- Expected model performance figures (precision 70–90%, recall 80–95%) — inferred from nature of mechanistic synthetic patterns; actual numbers require empirical validation after Phase 2

---
*Research completed: 2026-03-06*
*Ready for roadmap: yes*
