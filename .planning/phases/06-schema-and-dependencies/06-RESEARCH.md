# Phase 6: Schema and Dependencies - Research

**Researched:** 2026-03-09
**Domain:** PostgreSQL schema migration, Python ML dependency management, Docker image layering
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | `ml_score NUMERIC(5,4)` column added to `transactions` table in `db_setup.py` | SQLAlchemy ORM column addition documented; schema recreation via `down -v` confirmed as project pattern |
| INFRA-02 | `scikit-learn==1.6.1`, `xgboost==2.1.4`, `joblib==1.4.2`, `pandas==2.2.3`, `numpy==1.26.4` added to `requirements.txt` | Exact versions locked in STACK.md; numpy 1.x constraint for Docker slim compatibility confirmed |
| INFRA-03 | `src/model/` directory created for model artifact storage inside the processor container | Dockerfile `COPY src/ ./src/` copies the directory; a `.gitkeep` placeholder is needed for git to track the empty directory |
</phase_requirements>

---

## Summary

Phase 6 is the foundation layer for the v2.0 ML Fraud Scoring milestone. Its three requirements are deliberately narrow: add one column to the ORM model, pin five ML libraries in `requirements.txt`, and create the `src/model/` directory that downstream phases will write the trained artifact into.

All three changes are mechanical, but each has a concrete gotcha. The schema change requires a full `docker-compose down -v` to take effect because SQLAlchemy's `create_all` never alters existing tables — it only creates missing ones. The dependency additions require a `docker-compose build processor` (and dashboard/generator builds should follow because all three services share the same Dockerfile and image layers). The `src/model/` directory must be committed with a `.gitkeep` placeholder so that git tracks it and it appears inside the container after `COPY src/ ./src/`.

**Primary recommendation:** Make all three changes atomically in one wave — edit `db_setup.py`, edit `requirements.txt`, create `src/model/.gitkeep` — then execute `docker-compose down -v && docker-compose build && docker-compose up -d` to validate success criteria in a single pass.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | 1.6.1 | ML model training and inference pipeline | Latest proven stable; provides `RandomForestClassifier`, `Pipeline`, `ColumnTransformer`, `class_weight='balanced'` |
| xgboost | 2.1.4 | Gradient boosted tree alternative to RandomForest | Stable 2.x; drops into scikit-learn Pipeline via identical API; v3.x has breaking changes |
| joblib | 1.4.2 | Model serialization / deserialization | More efficient than pickle for numpy arrays; already a transitive dep of scikit-learn — explicit pin for reproducibility |
| pandas | 2.2.3 | DataFrame operations in training script only | 2.2.3 proven; v3.x too recent; training-only import (must NOT enter processor.py hot path) |
| numpy | 1.26.4 | Numerical array substrate for all three ML libs | Last 1.x LTS; satisfies scikit-learn, xgboost, and joblib simultaneously; numpy 2.x has C-API friction on python:3.11-slim |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psycopg2-binary | 2.9.9 (already pinned) | PostgreSQL driver used by train_model.py | Already present; no change needed |
| sqlalchemy | 2.0.23 (already pinned) | ORM used for schema and processor DB writes | Already present; ml_score column addition uses existing ORM |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| scikit-learn 1.6.1 | scikit-learn 1.8.x | Too recent for a portfolio project — 1.6.1 is the verified stable release as of research date |
| numpy 1.26.4 | numpy 2.x | numpy 2.x has C-API changes that cause compatibility issues in Docker slim images with some compiled extensions |
| joblib (explicit) | rely on transitive dep | Transitive deps can shift on rebuild; explicit pin guarantees reproducibility |
| `docker-compose down -v` migration | Alembic migration | Alembic is correct for production but adds complexity; `down -v` is the project-sanctioned pattern per CLAUDE.md |

**Installation (additions to requirements.txt):**
```
scikit-learn==1.6.1
xgboost==2.1.4
joblib==1.4.2
pandas==2.2.3
numpy==1.26.4
```

---

## Architecture Patterns

### Current File State (pre-Phase 6)

```
src/
├── generator.py         # unchanged — no ML
├── processor.py         # unchanged — no ML yet
├── dashboard.py         # unchanged — no ml_score yet
├── db_setup.py          # Transaction model has NO ml_score column
├── data_quality.py      # unchanged
requirements.txt         # 6 packages — no ML libs
# src/model/             # DOES NOT EXIST
```

### Target File State (post-Phase 6)

```
src/
├── generator.py         # unchanged
├── processor.py         # unchanged (Phase 8 modifies this)
├── dashboard.py         # unchanged (Phase 9 modifies this)
├── db_setup.py          # Transaction model has ml_score = Column(Numeric(5, 4))
├── data_quality.py      # unchanged
├── model/
│   └── .gitkeep         # placeholder — fraud_model.joblib written here in Phase 7
requirements.txt         # 11 packages — ML libs added
```

### Pattern 1: SQLAlchemy ORM Column Addition

**What:** Add `ml_score = Column(Numeric(5, 4))` to the `Transaction` ORM class in `db_setup.py`. This is nullable by default in SQLAlchemy — no `nullable=False` needed because Phase 8 processor writes it on every transaction.

**When to use:** Whenever the DB schema must change to support a new data attribute written by the processor.

**Example:**
```python
# src/db_setup.py — add this line inside the Transaction class
ml_score = Column(Numeric(5, 4))  # ML fraud probability 0.0000–1.0000
```

**NUMERIC(5,4) constraint:** Stores values from -9.9999 to 9.9999. The ML probability output is always 0.0000–1.0000, so this precision (4 decimal places) is correct and sufficient.

### Pattern 2: Schema Recreation via docker-compose down -v

**What:** SQLAlchemy's `Base.metadata.create_all(engine)` (used in `init_db()`) only creates tables that do not yet exist. It never issues `ALTER TABLE`. Adding a column to the ORM model requires either an `ALTER TABLE` run manually or dropping and recreating all data.

**When to use:** Always after a schema-breaking change in this project. Documented in CLAUDE.md as the standard approach.

**Command sequence:**
```bash
docker-compose down -v       # wipes postgres_data volume — all transaction data lost
docker-compose up -d         # recreates tables with new schema via init_db()
```

**Data loss:** This wipes all existing transactions. Acceptable because data is synthetic (generator.py regenerates it on startup).

### Pattern 3: Docker Image Rebuild After requirements.txt Change

**What:** The Dockerfile installs packages during `RUN pip install -r requirements.txt`. Changing `requirements.txt` requires a rebuild to take effect inside the container.

**When to use:** Any time Python dependencies change.

**Command:**
```bash
docker-compose build processor   # rebuilds only the processor image
# OR
docker-compose build             # rebuilds all three custom services (generator, processor, dashboard)
```

**Layer cache note:** Because `COPY requirements.txt .` is before `COPY src/ ./src/` in the Dockerfile, pip install is cached as long as `requirements.txt` is unchanged. Changing `requirements.txt` busts the pip layer — expect a longer build on first run with new ML packages (scikit-learn, xgboost, numpy are large).

### Pattern 4: Git-Tracked Empty Directory via .gitkeep

**What:** Git does not track empty directories. Creating `src/model/` on disk does not cause it to appear in the Docker image unless it is committed to git (or added via a `RUN mkdir` in the Dockerfile). Using a `.gitkeep` placeholder file is the conventional solution.

**When to use:** Any time a directory must exist in the repo and inside the container before its contents are generated.

**Implementation:**
```bash
mkdir src/model
touch src/model/.gitkeep
git add src/model/.gitkeep
```

The Dockerfile `COPY src/ ./src/` will then copy `src/model/.gitkeep` → `/app/src/model/.gitkeep`, which means `/app/src/model/` exists inside the container. Phase 7's `train_model.py` writes `src/model/fraud_model.joblib` alongside `.gitkeep`.

### Anti-Patterns to Avoid

- **ALTER TABLE in application code:** Do not add `ALTER TABLE transactions ADD COLUMN ml_score` inside `db_setup.py` or any init script. The project pattern is `down -v` + recreate. Mixing approaches creates confusion about the authoritative schema.
- **Importing pandas in processor.py:** Even though pandas is now in `requirements.txt` (installed in the processor image), STACK.md explicitly forbids importing pandas in the processor hot path. The pandas requirement is there for `train_model.py`, which runs on the host — but it will also be available in the container image. Do not let this proximity trigger a misuse.
- **Pinning without a comment:** The ML packages should be grouped with a comment in `requirements.txt` so future maintainers understand why they were added. See Code Examples.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Model serialization | Custom pickle wrapper | `joblib.dump()` / `joblib.load()` | joblib handles numpy arrays more efficiently; is the scikit-learn standard |
| Schema migrations | Manual SQL scripts baked into init_db() | `docker-compose down -v` + ORM recreate | Per project convention; Alembic is out of scope |
| Directory creation in container | `RUN mkdir /app/src/model` in Dockerfile | `.gitkeep` in `src/model/` | Dockerfile is unchanged — the `COPY src/` already handles it if the directory is committed |

**Key insight:** Phase 6 is infrastructure prep, not implementation. Resist the temptation to also scaffold `MLScorer` or `train_model.py` here — those belong to Phases 7 and 8. Scope discipline is the main risk in this phase.

---

## Common Pitfalls

### Pitfall 1: Forgetting docker-compose down -v After Schema Change
**What goes wrong:** Developer edits `db_setup.py`, runs `docker-compose up -d`, and the schema does not change because `create_all` skips existing tables. The `ml_score` column does not appear. Downstream phases fail mysteriously.
**Why it happens:** SQLAlchemy's `create_all` is idempotent in a "skip if exists" way, not an "alter if changed" way.
**How to avoid:** Always run `docker-compose down -v && docker-compose up -d` after any schema change. The success criterion (`\d transactions` showing `ml_score`) confirms the column exists.
**Warning signs:** `\d transactions` shows no `ml_score` column despite the ORM model having it.

### Pitfall 2: ML Packages Fail to Resolve on python:3.11-slim
**What goes wrong:** `docker-compose build processor` fails with a pip dependency conflict or a numpy C-extension compilation error.
**Why it happens:** numpy 2.x or very recent scikit-learn versions may have compiled dependencies that require build tools not present in the slim image.
**How to avoid:** Use the pinned versions in STACK.md (`numpy==1.26.4`, `scikit-learn==1.6.1`). These are verified against python:3.11-slim.
**Warning signs:** Build output shows `error: command 'gcc' failed` or `Could not find a version that satisfies the requirement`.

### Pitfall 3: src/model/ Directory Missing Inside Container
**What goes wrong:** Phase 7's `train_model.py` writes `src/model/fraud_model.joblib` on the host, but when the processor image is rebuilt in Phase 8, the directory exists in the image but the `.joblib` file is not there (train runs after the build, not before — or the `.gitkeep` was never committed).
**Why it happens:** git does not track empty directories; if `.gitkeep` is absent, `COPY src/ ./src/` in the Dockerfile does not create `/app/src/model/`.
**How to avoid:** Commit `src/model/.gitkeep` to git. Confirm with `docker exec fraud_detection-processor-1 ls /app/src/model` showing `.gitkeep`.
**Warning signs:** `ls /app/src/model` returns "No such file or directory".

### Pitfall 4: Scope Creep into Phase 7/8 Work
**What goes wrong:** While adding the `ml_score` column, the developer also scaffolds `MLScorer` in `processor.py` or writes a partial `train_model.py`. This makes Phase 6 verification tests pass partially while leaving the codebase in a broken intermediate state for Phase 8.
**Why it happens:** The changes feel related and the developer wants to make progress.
**How to avoid:** Phase 6 success criteria are explicit and narrow — column exists, build succeeds, directory exists, all 6 services healthy. Stop there.

---

## Code Examples

Verified patterns from codebase inspection and STACK.md:

### INFRA-01: Add ml_score to Transaction ORM model (db_setup.py)
```python
# src/db_setup.py — Transaction class (add one line)
class Transaction(Base):
    __tablename__ = 'transactions'

    transaction_id = Column(String, primary_key=True)
    timestamp = Column(TIMESTAMP)
    user_id = Column(String)
    merchant_id = Column(String)
    amount = Column(Numeric(10, 2))
    card_last_4 = Column(String)
    merchant_category = Column(String)
    is_fraud = Column(String)  # Ground truth — stores "True"/"False" strings
    processed_at = Column(TIMESTAMP, default=datetime.now)
    ml_score = Column(Numeric(5, 4))  # ML fraud probability 0.0000-1.0000; NULL until Phase 8
```

### INFRA-02: requirements.txt additions
```
faker==22.0.0
python-dotenv==1.0.0
confluent-kafka==2.3.0
psycopg2-binary==2.9.9
sqlalchemy==2.0.23
streamlit==1.31.0

# ML scoring (v2.0 milestone)
scikit-learn==1.6.1
xgboost==2.1.4
joblib==1.4.2
pandas==2.2.3
numpy==1.26.4
```

### INFRA-03: Create src/model/ directory with .gitkeep
```bash
mkdir src/model
touch src/model/.gitkeep
# Then git add src/model/.gitkeep
```

### Verification Commands (Success Criteria)
```bash
# INFRA-01: Confirm ml_score column exists in schema
docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "\d transactions"
# Expected: ml_score | numeric(5,4) | ...

# INFRA-02: Confirm processor image built without errors (check build output)
docker-compose build processor
# Expected: no package resolution errors

# INFRA-03: Confirm src/model/ directory exists inside container
docker exec fraud_detection-processor-1 ls /app/src/model
# Expected: .gitkeep

# INFRA-04 (combined): All 6 services healthy
docker-compose ps
# Expected: All 6 services Up
```

### Full Reset + Rebuild Sequence
```bash
docker-compose down -v                        # wipe DB volume
docker-compose build                          # rebuild processor (and generator, dashboard)
docker-compose up -d                          # start all 6 services; init_db() runs in processor
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pickle for model serialization | joblib.dump/load | scikit-learn ~0.21 | joblib is now the scikit-learn standard; pickle still works but joblib is more efficient for numpy |
| Alembic for schema migrations | `down -v` + recreate (for this project) | Project decision | Acceptable for synthetic data; Alembic is correct for production |
| `numpy.float64` return from predict_proba | Cast to Python `float` explicitly | numpy 2.x prep | `float(model.predict_proba(...)[0][1])` avoids type issues when writing to SQLAlchemy Numeric column |

**Deprecated/outdated:**
- `from sqlalchemy.ext.declarative import declarative_base`: The project already uses the correct `from sqlalchemy.orm import declarative_base` (SQLAlchemy 2.x pattern) — no change needed.

---

## Open Questions

1. **Should `ml_score` have a `NOT NULL` constraint or a DEFAULT?**
   - What we know: Phase 8 writes it for every transaction. Phase 6–7 period has no processor writing scores yet.
   - What's unclear: Whether the processor will fail to write rows during the Phase 6–7 window if `ml_score` has no default.
   - Recommendation: Leave it nullable (SQLAlchemy default) for Phase 6. After Phase 8 ships and all transactions get a score, a `NOT NULL` constraint could be added — but it is not required for any v2.0 success criterion.

2. **Will all three services (generator, processor, dashboard) be rebuilt?**
   - What we know: All three share the same Dockerfile and `requirements.txt`. Adding ML packages to `requirements.txt` busts the pip layer for all three.
   - What's unclear: Whether the generator and dashboard need scikit-learn/xgboost at runtime (they do not — it's wasted image size).
   - Recommendation: Accept the shared image for now (project convention is one Dockerfile). Separate Dockerfiles are a v3+ optimization. Run `docker-compose build` to rebuild all three consistently.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None — no test framework exists in this codebase |
| Config file | None — see Wave 0 gaps |
| Quick run command | N/A — no tests exist |
| Full suite command | N/A — no tests exist |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `ml_score NUMERIC(5,4)` column exists in transactions table | smoke (docker exec) | `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "\d transactions"` | N/A — shell command |
| INFRA-02 | ML packages install without error on python:3.11-slim | smoke (docker build) | `docker-compose build processor` | N/A — docker command |
| INFRA-03 | `src/model/` directory exists inside processor container | smoke (docker exec) | `docker exec fraud_detection-processor-1 ls /app/src/model` | N/A — shell command |

**Note:** All three Phase 6 requirements are infrastructure-level and verified with shell/docker commands rather than automated test files. No Python test framework is needed to validate this phase — the success criteria in the phase description are already expressed as runnable commands.

### Sampling Rate
- **Per task commit:** Run the docker exec verification command for the specific requirement being committed (INFRA-01, INFRA-02, or INFRA-03).
- **Per wave merge:** Run full reset sequence (`down -v && build && up -d`) and verify all three criteria.
- **Phase gate:** All 6 services healthy + all three docker exec checks passing before moving to Phase 7.

### Wave 0 Gaps
No test files need to be created for Phase 6. The verification method is docker/psql commands, not a test framework. If the project adds pytest in a future phase, the infrastructure checks above could be wrapped in `subprocess`-based integration tests — but that is out of scope for Phase 6.

*(Existing test infrastructure: None — codebase has no test framework as documented in `.planning/codebase/TESTING.md`)*

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/db_setup.py` — confirmed current Transaction model has no `ml_score` column
- Direct codebase inspection: `requirements.txt` — confirmed 6 packages, no ML libs
- Direct codebase inspection: `Dockerfile` — confirmed `COPY src/ ./src/` pattern and python:3.11-slim base
- Direct codebase inspection: `docker-compose.yml` — confirmed all services, postgres_data volume, port 5433:5432
- `.planning/research/STACK.md` — pinned versions with rationale (scikit-learn 1.6.1, xgboost 2.1.4, joblib 1.4.2, pandas 2.2.3, numpy 1.26.4)
- `.planning/research/ARCHITECTURE.md` — confirmed `docker-compose down -v` migration pattern, `.gitkeep` for model directory

### Secondary (MEDIUM confidence)
- `.planning/codebase/TESTING.md` — confirmed no test framework exists, no test files
- `CLAUDE.md` — confirmed `docker-compose down -v` as sanctioned DB wipe approach
- `.planning/STATE.md` — confirmed pandas must NOT be imported in processor.py hot path

### Tertiary (LOW confidence)
- None — all findings verified from codebase inspection or prior planning research.

---

## Metadata

**Confidence breakdown:**
- Standard stack (package versions): HIGH — exact versions taken from STACK.md which was verified against PyPI on 2026-03-06
- Architecture (ORM change, migration pattern): HIGH — confirmed from direct inspection of db_setup.py and ARCHITECTURE.md
- Pitfalls: HIGH — derived from direct codebase inspection and documented project decisions in STATE.md
- Validation approach: HIGH — confirmed no test framework exists; docker/psql commands are the correct verification method

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable domain — versions are pinned, migration pattern is project-specific)
