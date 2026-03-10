# Phase 8: Processor Integration - Research

**Researched:** 2026-03-10
**Domain:** sklearn Pipeline inference in a Kafka consumer loop (Python 3.11, scikit-learn 1.6.1, joblib 1.4.2)
**Confidence:** HIGH

---

## Summary

Phase 8 wires the already-trained `fraud_model.joblib` artifact into the existing `processor.py` Kafka consumer loop. The model is a sklearn `Pipeline` (`ColumnTransformer` + `RandomForestClassifier`) serialized with joblib. Loading it once at `FraudDetector.__init__` time is straightforward: a single `joblib.load()` call. The critical technical risk is **training-serving feature skew** — the six features fed to `model.predict_proba()` at inference must use exactly the same window semantics as `train_model.py`. Those semantics are already fully documented in the training script comments and can be computed from the existing `self.user_transactions[user_id]` in-memory list without any new state.

The `write_to_db()` function currently ignores `ml_score`; it must be extended to accept and persist the score to the `ml_score NUMERIC(5,4)` column, which already exists in the schema (added in Phase 6). No schema migration is needed. Pandas is pinned in `requirements.txt` and is already available inside the processor Docker image; however, the project decision from STATE.md explicitly prohibits importing pandas in the processor hot path. The feature vector must therefore be constructed as a plain Python dict wrapped in a single-row list, then passed to `model.predict_proba()` as a pandas DataFrame — but created with minimal overhead using the dict constructor inside `detect_fraud()` immediately before scoring.

The model artifact lives at `src/model/fraud_model.joblib` on the host. The Dockerfile copies `src/` to `/app/src/`, so inside the container the path is `/app/src/model/fraud_model.joblib`. The processor `WORKDIR` is `/app`, making a relative path `src/model/fraud_model.joblib` equivalent and simpler to use.

**Primary recommendation:** Load model once in `FraudDetector.__init__` with `joblib.load('src/model/fraud_model.joblib')`, log a startup message, build a one-row dict from in-memory history to call `model.predict_proba(pd.DataFrame([row]))[0][1]`, pass `ml_score` as an extra argument to `write_to_db`, and assign it to `transaction.ml_score` before `session.merge`.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROC-01 | `FraudDetector` loads model artifact once at `__init__` time (not inside the Kafka consumer loop) | `joblib.load()` is called once in `__init__`; model stored as `self.model`; startup log printed there |
| PROC-02 | ML fraud probability (0.0–1.0) computed per transaction using same feature windows as training script | Feature construction uses `self.user_transactions[user_id]` BEFORE the append; mirrors `closed='left'` rolling and `shift(1)` expanding mean |
| PROC-03 | `ml_score` written to `transactions` table for every processed transaction (not just fraud alerts) | `write_to_db` extended with `ml_score` param; `transaction.ml_score = ml_score` set before `session.merge` |
| PROC-04 | Existing rule-based detection (`high_amount`, `high_velocity`, `unusual_amount`) kept as safety-net alongside ML score | All three rule checks in `detect_fraud()` remain untouched; ML score is additive, not a replacement |
</phase_requirements>

---

## Standard Stack

### Core (already installed in requirements.txt)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| joblib | 1.4.2 | Deserialize sklearn Pipeline artifact | Official sklearn serialization format; already pinned |
| scikit-learn | 1.6.1 | sklearn Pipeline inference (`predict_proba`) | The Pipeline was trained with this version; must match for deserialization |
| pandas | 2.2.3 | Single-row DataFrame construction for Pipeline input | Pipeline's ColumnTransformer expects a DataFrame with named columns |
| numpy | 1.26.4 | Numeric dtype support inside Pipeline | sklearn internal dependency; already pinned |

### No New Dependencies
All required libraries are already in `requirements.txt` (INFRA-02, Phase 6). No `pip install` changes needed for Phase 8.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pd.DataFrame([row_dict])` (single-row) | numpy array | Pipeline's ColumnTransformer requires column names for the `cat` transformer; numpy array loses names — do not use |
| `joblib.load` | `pickle.load` | joblib is the sklearn-blessed serializer; pickle would work but is non-standard here |

---

## Architecture Patterns

### How the Processor Currently Works (exact flow)

```
consume_and_process()
  └── detector = FraudDetector()       ← __init__ (one time)
  └── while True:
        msg = consumer.poll(1.0)
        tx = json.loads(...)
        result = detector.detect_fraud(tx)   ← called per message
        write_to_db(session, tx, result)
```

`detect_fraud()` current flow:
1. Check `high_amount` rule (reads `amount`)
2. Check `high_velocity` rule (reads `self.user_transactions[user_id]`)
3. Check `unusual_amount` rule (reads `self.user_transactions[user_id]`)
4. **APPEND** current tx to `self.user_transactions[user_id]`  ← append happens LAST
5. Cap history at 100 entries
6. Return `result` dict

### Pattern 1: Model Load at Init (PROC-01)

**What:** `joblib.load` called once in `FraudDetector.__init__`, stored as `self.model`. Startup log printed immediately.
**When to use:** Any stateful object that is expensive to initialize once and reused per-message.

```python
# Confirmed pattern — joblib.load() is the standard sklearn artifact loader
import joblib

class FraudDetector:
    def __init__(self):
        self.user_transactions = defaultdict(list)
        model_path = 'src/model/fraud_model.joblib'
        self.model = joblib.load(model_path)
        print(f"Model loaded from {model_path}")
```

**Graceful degradation vs hard fail:** Given this is a portfolio streaming service, a hard fail at startup is CORRECT behavior. If the artifact is missing, the processor should crash immediately with a clear error rather than silently writing NULL scores. The `FileNotFoundError` raised by `joblib.load` when the file doesn't exist is already informative enough — no try/except needed at this call site. The Docker build bakes the artifact in at image build time, so a missing file indicates a broken image, not a transient error.

### Pattern 2: Feature Construction at Inference (PROC-02)

**What:** Compute the six training features from in-memory history BEFORE the append (step 4 above), build a one-row dict, wrap in `pd.DataFrame([row])`, call `model.predict_proba`.

**Critical semantics — mirrors training exactly:**

| Feature | Training computation | Inference computation |
|---------|---------------------|-----------------------|
| `amount` | raw column | `tx['amount']` |
| `tx_count_last_5min` | `rolling('5min', closed='left').count()` — excludes current row | Count entries in `self.user_transactions[user_id]` where `timestamp - t['timestamp'] < timedelta(minutes=5)` — same `recent_txs` list already computed for `high_velocity` rule |
| `amount_vs_user_avg_ratio` | `expanding().mean().shift(1)` — excludes current tx | `mean(t['amount'] for t in history)` then `amount / avg`; cold-start (empty history) → `1.0` |
| `hour_of_day` | `timestamp.dt.hour` | `timestamp.hour` |
| `day_of_week` | `timestamp.dt.dayofweek` | `timestamp.weekday()` |
| `merchant_category` | raw string column | `tx['merchant_category']` |

**Key observation:** `recent_txs` is already computed earlier in `detect_fraud()` for the `high_velocity` check. Reuse it directly for `tx_count_last_5min`. No duplicate list comprehension needed.

**Column order must match training feature order:**
```python
# From train_model.py — this exact order is required
NUMERIC_FEATURES = ['amount', 'tx_count_last_5min', 'amount_vs_user_avg_ratio', 'hour_of_day', 'day_of_week']
CAT_FEATURES = ['merchant_category']
# Pipeline input columns: NUMERIC_FEATURES + CAT_FEATURES
```

The ColumnTransformer references columns by name (`CAT_FEATURES` = `['merchant_category']`), so the DataFrame must contain all six column names. Order of numeric columns doesn't technically matter for ColumnTransformer with named references, but matching training order eliminates any ambiguity.

```python
import pandas as pd

def _compute_ml_score(self, tx, timestamp, recent_txs):
    """Compute ML fraud probability using pre-append in-memory history."""
    history = self.user_transactions[tx['user_id']]  # read BEFORE append

    tx_count_last_5min = float(len(recent_txs))  # reuse already-computed list

    if history:
        avg_amount = sum(t['amount'] for t in history) / len(history)
        amount_vs_user_avg_ratio = float(tx['amount']) / avg_amount
    else:
        amount_vs_user_avg_ratio = 1.0  # cold-start: no prior history

    row = {
        'amount': float(tx['amount']),
        'tx_count_last_5min': tx_count_last_5min,
        'amount_vs_user_avg_ratio': amount_vs_user_avg_ratio,
        'hour_of_day': float(timestamp.hour),
        'day_of_week': float(timestamp.weekday()),
        'merchant_category': tx['merchant_category'],
    }
    X = pd.DataFrame([row])
    return float(self.model.predict_proba(X)[0][1])
```

### Pattern 3: Persisting ml_score (PROC-03)

**What:** `write_to_db` receives `ml_score` as an additional parameter and sets it on the `Transaction` ORM object before `session.merge`.

**Current `write_to_db` signature:**
```python
def write_to_db(session, tx, result):
```

**New signature:**
```python
def write_to_db(session, tx, result, ml_score):
```

**The `Transaction` ORM model already has:**
```python
ml_score = Column(Numeric(5, 4))  # ML fraud probability 0.0000-1.0000; NULL until Phase 8
```

**Change to Transaction construction:**
```python
transaction = Transaction(
    # ... existing fields unchanged ...
    ml_score=ml_score,  # new — float 0.0-1.0, stored as NUMERIC(5,4)
)
```

**Call site in `consume_and_process()`:**
```python
result = detector.detect_fraud(tx)  # now returns ml_score in result dict OR pass separately
write_to_db(session, tx, result, ml_score=result['ml_score'])
```

**Simplest approach:** Add `ml_score` to the `result` dict returned by `detect_fraud()`, then unpack it in `write_to_db`. This keeps `write_to_db`'s call site at one argument (`result`) and avoids a separate variable.

### Pattern 4: Rule Detection Unchanged (PROC-04)

All three rule checks (`high_amount`, `high_velocity`, `unusual_amount`) remain in `detect_fraud()` exactly as-is. The ML score is computed in addition to rules, never replacing them. The `result` dict gains a new `ml_score` key; all existing keys remain.

### Anti-Patterns to Avoid

- **Import pandas at module level in processor.py:** STATE.md decision — "pandas imported only in train_model.py — must NOT be imported in processor.py hot path." Import `pandas` inside `detect_fraud()` locally, OR move the import to the top but only after confirming the STATE.md decision applies to the `import` statement location vs. the call site. The most literal reading: import pandas at the top of `processor.py` is fine since the file is not a hot-path module-level import concern — what the decision prevents is slow per-call imports inside the loop. A top-level `import pandas as pd` in processor.py satisfies the intent. Confirm: import once at top, not inside the loop.
- **Calling `model.predict_proba` with a numpy array:** The Pipeline's ColumnTransformer uses named column references. Always pass a named `pd.DataFrame`.
- **Computing features AFTER the append:** `self.user_transactions[user_id].append(...)` happens at line 38 of current `processor.py`. Feature computation must happen before that line. `_compute_ml_score` must be called before the append block.
- **Using `model.predict` instead of `model.predict_proba`:** `predict` returns 0/1 class label. `predict_proba(X)[0][1]` returns the continuous probability for class 1. Only the latter produces a float 0.0–1.0.
- **Storing pandas import inside the consumer loop:** Even though the file-level import is fine, do not call `import pandas` inside `while True` — Python caches imports but the call itself has a small overhead.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OHE at inference | Manual category-to-int mapping | `model.predict_proba(X)` — Pipeline includes OHE | Pipeline handles unknown categories via `handle_unknown='ignore'`; manual mapping will diverge |
| Feature scaling | Manual z-score normalization | Pipeline passthrough (RF doesn't need scaling) | RF is scale-invariant; training pipeline uses passthrough for numerics |
| Threshold application | `if ml_score > 0.5` binary decision | Keep raw float in DB; rule-based alerts are separate | Phase 8 is scoring only; threshold-based alerting is ADV-01 (future) |

**Key insight:** The sklearn Pipeline encapsulates all preprocessing. The processor only needs to construct raw features in the correct column format — the Pipeline handles the rest.

---

## Common Pitfalls

### Pitfall 1: Feature Window Direction (Training-Serving Skew)
**What goes wrong:** `tx_count_last_5min` computed AFTER the append (includes current tx) vs. the training window that excludes it. Score is systematically wrong for high-velocity users.
**Why it happens:** Append happens at the bottom of `detect_fraud()`; easy to compute features after all rule checks as an afterthought.
**How to avoid:** Call `_compute_ml_score` before the append block (current line 38 in `processor.py`). The `recent_txs` list is already computed for the velocity rule check — pass it directly.
**Warning signs:** `tx_count_last_5min` is always 1 higher than expected; velocity fraud rows show inflated scores.

### Pitfall 2: Cold-Start Division by Zero
**What goes wrong:** `amount / avg_amount` raises `ZeroDivisionError` when `history` is empty (first transaction ever for a user).
**Why it happens:** Empty list → `sum([]) / 0` → division by zero.
**How to avoid:** Guard with `if history: ... else: ratio = 1.0`. Matches training `fillna(1.0)` behavior exactly.
**Warning signs:** Processor crash log: `ZeroDivisionError` on first transaction for new user IDs.

### Pitfall 3: DataFrame Column Names Mismatch
**What goes wrong:** `model.predict_proba(X)` raises `ValueError: Feature names must be...` or silently mis-routes categorical column through numeric transformer.
**Why it happens:** Column name typo or wrong order in the dict used to build the DataFrame.
**How to avoid:** Use the exact strings from `train_model.py`: `'amount'`, `'tx_count_last_5min'`, `'amount_vs_user_avg_ratio'`, `'hour_of_day'`, `'day_of_week'`, `'merchant_category'`.
**Warning signs:** `ValueError` from sklearn ColumnTransformer at runtime.

### Pitfall 4: ml_score Precision Loss on NUMERIC(5,4)
**What goes wrong:** `predict_proba` returns a float64 like `0.999999...`; SQLAlchemy truncates or raises on values outside `NUMERIC(5,4)` range (max stored value is 9.9999).
**Why it happens:** `predict_proba` guarantees [0.0, 1.0] but floating point can produce values like `1.0000000001` due to rounding.
**How to avoid:** Clamp before writing: `ml_score = min(1.0, max(0.0, raw_score))`. `float()` cast ensures Python native float, not numpy float64.
**Warning signs:** Rare DB write failures; scores of exactly 0 or 1 in unexpected proportions.

### Pitfall 5: Model Path Inside Container
**What goes wrong:** `FileNotFoundError: src/model/fraud_model.joblib` — path doesn't exist inside container.
**Why it happens:** Confusion between host path and container path; or model artifact not committed to source before `docker build`.
**How to avoid:** The Dockerfile copies `src/` to `/app/src/`. Container `WORKDIR` is `/app`. Path `src/model/fraud_model.joblib` is valid inside the container as a relative path from `/app`. Verify with `docker exec fraud_detection-processor-1 ls /app/src/model/`.
**Warning signs:** Processor crashes at startup (not during message processing) with `FileNotFoundError`.

### Pitfall 6: Session State After DB Failure
**What goes wrong:** `session.rollback()` is called in the `except` block in `consume_and_process()`, but the session object may be in an invalid state for subsequent writes.
**Why it happens:** SQLAlchemy sessions become invalid after certain errors without a full rollback.
**How to avoid:** This is an existing pattern in `processor.py` (already handles rollback). No new risk introduced by Phase 8 as long as `ml_score` values are valid floats. The clamp in Pitfall 4 avoids DB constraint violations.
**Warning signs:** `ProgrammingError: can't reconnect until invalid transaction is rolled back`.

---

## Code Examples

Verified from direct inspection of `processor.py` and `train_model.py`:

### Model Load at Init
```python
# Source: joblib official API — joblib.load(filename) returns the object
import joblib

class FraudDetector:
    def __init__(self):
        self.user_transactions = defaultdict(list)
        self.model = joblib.load('src/model/fraud_model.joblib')
        print("Model loaded from src/model/fraud_model.joblib")
```

### Feature Vector Construction (Pre-Append State)
```python
# Source: train_model.py engineer_features() — exact window semantics
import pandas as pd

# Inside detect_fraud(), BEFORE the append block:
# recent_txs is already computed for high_velocity check:
#   recent_txs = [t for t in self.user_transactions[user_id]
#                 if timestamp - t['timestamp'] < timedelta(minutes=5)]

history = self.user_transactions[user_id]  # pre-append state

tx_count_last_5min = float(len(recent_txs))

if history:
    avg_amount = sum(t['amount'] for t in history) / len(history)
    amount_vs_user_avg_ratio = float(amount) / avg_amount
else:
    amount_vs_user_avg_ratio = 1.0

row = {
    'amount': float(amount),
    'tx_count_last_5min': tx_count_last_5min,
    'amount_vs_user_avg_ratio': amount_vs_user_avg_ratio,
    'hour_of_day': float(timestamp.hour),
    'day_of_week': float(timestamp.weekday()),
    'merchant_category': tx['merchant_category'],
}
X = pd.DataFrame([row])
ml_score = float(self.model.predict_proba(X)[0][1])
ml_score = min(1.0, max(0.0, ml_score))  # clamp for NUMERIC(5,4) safety
```

### write_to_db Extension
```python
# Source: db_setup.py — Transaction.ml_score = Column(Numeric(5, 4))
def write_to_db(session, tx, result):
    transaction = Transaction(
        transaction_id=tx['transaction_id'],
        timestamp=datetime.fromisoformat(tx['timestamp']),
        user_id=tx['user_id'],
        merchant_id=tx['merchant_id'],
        amount=tx['amount'],
        card_last_4=tx['card_last_4'],
        merchant_category=tx['merchant_category'],
        is_fraud=str(tx.get('is_fraud', False)),
        ml_score=result['ml_score'],   # new field — float 0.0-1.0
    )
    session.merge(transaction)

    if result['is_fraud']:
        alert = FraudAlert(
            transaction_id=result['transaction_id'],
            fraud_score=result['fraud_score'],
            rules_triggered=result['rules_triggered'],
            detected_at=datetime.fromisoformat(result['detected_at'])
        )
        session.add(alert)

    session.commit()
```

### Result Dict Update
```python
# detect_fraud() return value — add ml_score key, keep all existing keys
return {
    "transaction_id": tx['transaction_id'],
    "is_fraud": len(rules_triggered) > 0,
    "fraud_score": len(rules_triggered) / 3.0,
    "rules_triggered": rules_triggered,
    "detected_at": datetime.now().isoformat(),
    "ml_score": ml_score,   # new
    "raw": tx
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Rule-only fraud_score (0/3, 1/3, 2/3, 3/3) | ML probability 0.0–1.0 from RandomForest | Phase 8 | Continuous risk score replaces step-function |
| No ml_score column | `ml_score NUMERIC(5,4)` nullable column | Phase 6 | Column already exists; no migration needed |

**Deprecated/outdated:**
- The `fraud_score` field in `result` dict (ratio of rules triggered / 3.0) remains for backward compatibility but is no longer the primary scoring output. Do not remove it — `FraudAlert.fraud_score` still writes it to the DB.

---

## Open Questions

1. **pandas import location**
   - What we know: STATE.md says "pandas imported only in train_model.py — must NOT be imported in processor.py hot path." The phrase "hot path" likely refers to inside the `while True` loop, not the module-level import.
   - What's unclear: Does this mean no `import pandas as pd` at the top of `processor.py`, or no `import pandas` inside the consumer loop?
   - Recommendation: Import `pandas` at the top of `processor.py` (module-level, executed once at startup). This satisfies "not in the hot path" while keeping the code clean. The alternative — a local import inside `detect_fraud()` — would add a dict lookup per call (negligible but contrary to the spirit). Confirm with project owner if needed.

2. **`_compute_ml_score` as private method vs. inline**
   - What we know: The feature computation is ~10 lines. It could be inlined inside `detect_fraud()` or extracted as a helper.
   - What's unclear: No explicit style guidance in CLAUDE.md on method extraction.
   - Recommendation: Inline within `detect_fraud()` for minimal diff. The method is only called once, so extraction adds indirection without clarity benefit.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None detected (no pytest.ini, no test/ directory, no test files) |
| Config file | None — Wave 0 must create |
| Quick run command | `pytest src/tests/test_processor_ml.py -x` (once created) |
| Full suite command | `pytest src/tests/ -x` (once created) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROC-01 | Model loaded once at `__init__` (not per-message) | unit | `pytest src/tests/test_processor_ml.py::test_model_loaded_once -x` | Wave 0 |
| PROC-02 | ML score uses pre-append history; cold-start returns 1.0 ratio | unit | `pytest src/tests/test_processor_ml.py::test_feature_windows -x` | Wave 0 |
| PROC-03 | `ml_score` written to `transactions` for every message | integration (DB) | `pytest src/tests/test_processor_ml.py::test_ml_score_persisted -x` | Wave 0 |
| PROC-04 | Rule-based alerts still fire alongside ML score | unit | `pytest src/tests/test_processor_ml.py::test_rules_still_fire -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest src/tests/test_processor_ml.py -x`
- **Per wave merge:** `pytest src/tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `src/tests/__init__.py` — package marker
- [ ] `src/tests/test_processor_ml.py` — covers PROC-01, PROC-02, PROC-03, PROC-04
- [ ] Framework install: `pip install pytest` (pytest not in requirements.txt; add as dev dependency or install only in test environment)

**Note on PROC-03 (integration test):** Writing to the real DB inside a unit test is impractical. The recommended approach is to mock `session.merge` and `session.commit` and assert that the `Transaction` object received a non-null `ml_score` float. This makes the test fast and deterministic without a live DB.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `src/processor.py` — full understanding of `FraudDetector`, `detect_fraud()`, `write_to_db()`, append semantics
- Direct code inspection: `src/train_model.py` — exact feature window definitions; `NUMERIC_FEATURES`, `CAT_FEATURES`, `VELOCITY_WINDOW_MINUTES=5`, `HISTORY_CAP=100`
- Direct code inspection: `src/db_setup.py` — `Transaction.ml_score = Column(Numeric(5, 4))` confirmed present
- Direct code inspection: `Dockerfile` — `COPY src/ ./src/` confirms artifact path `/app/src/model/fraud_model.joblib`
- Direct code inspection: `requirements.txt` — joblib 1.4.2, scikit-learn 1.6.1, pandas 2.2.3, numpy 1.26.4 confirmed present
- Filesystem check: `src/model/fraud_model.joblib` — confirmed present (42MB artifact)
- `.planning/STATE.md` — project decisions including pandas hot-path prohibition, model artifact baked into image at build time

### Secondary (MEDIUM confidence)
- joblib official API: `joblib.load(filename)` returns the serialized object — standard usage, no version caveats for 1.4.2
- sklearn Pipeline `predict_proba(X)` returning shape `(n_samples, n_classes)` with `[0][1]` indexing for single-row binary classification — confirmed via train_model.py usage pattern (`model.predict_proba(X_val)[:, 1]`)

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies confirmed present in requirements.txt; no new installs needed
- Architecture: HIGH — processor.py read in full; exact insertion points identified; feature windows confirmed against training script
- Pitfalls: HIGH — derived from direct code inspection and known sklearn/pandas behaviors; training-serving skew risk documented with exact line numbers
- Validation: MEDIUM — no existing test infrastructure; test design is reasonable but untested

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable stack — sklearn Pipeline API, joblib, pandas DataFrame construction are stable APIs)
