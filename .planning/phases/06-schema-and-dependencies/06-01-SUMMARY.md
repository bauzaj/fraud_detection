---
phase: 06-schema-and-dependencies
plan: 01
subsystem: infra
tags: [postgres, sqlalchemy, scikit-learn, xgboost, joblib, pandas, numpy, docker]

# Dependency graph
requires:
  - phase: 01-05-foundation
    provides: Working Docker Compose stack with 6 services, transactions table, processor image
provides:
  - ml_score column (numeric(5,4)) in PostgreSQL transactions table
  - ML library pins (scikit-learn, xgboost, joblib, pandas, numpy) in processor Docker image
  - src/model/ directory inside processor container for model artifact storage
affects: [07-training, 08-inference, 09-dashboard]

# Tech tracking
tech-stack:
  added: [scikit-learn==1.6.1, xgboost==2.1.4, joblib==1.4.2, pandas==2.2.3, numpy==1.26.4]
  patterns:
    - pandas imported only in training scripts, NOT in processor hot path
    - Model artifacts stored at /app/src/model/ inside processor container (baked in at build time)
    - ml_score column nullable until Phase 8 wires ML inference to avoid write failures

key-files:
  created: [src/model/.gitkeep]
  modified: [src/db_setup.py, requirements.txt]

key-decisions:
  - "ml_score column is nullable (no nullable=False) so processor rows written in Phases 6-7 do not fail before ML inference is wired in Phase 8"
  - "numpy==1.26.4 pinned to last 1.x LTS — numpy 2.x has C-API friction on python:3.11-slim"
  - "xgboost==2.1.4 pinned to stable 2.x — v3.x has breaking changes"
  - "pandas pinned as explicit dependency even though it is training-only to prevent version drift"

patterns-established:
  - "pandas/numpy are training-only imports — must NOT appear in processor.py hot path"
  - "Model artifacts baked into processor Docker image at build time, not volume-mounted"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03]

# Metrics
duration: 6min
completed: 2026-03-09
---

# Phase 6 Plan 01: Schema and Dependencies Summary

**ml_score column (numeric(5,4)) added to PostgreSQL, scikit-learn/xgboost/joblib/pandas/numpy pinned in processor image, and src/model/ directory created inside container — full stack rebuilt and all 6 services verified healthy**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-09T16:52:22Z
- **Completed:** 2026-03-09T16:58:38Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Added ml_score = Column(Numeric(5, 4)) to Transaction ORM model — column confirmed in PostgreSQL via \d transactions showing numeric(5,4) type
- Pinned 5 ML libraries in requirements.txt — all packages installed successfully in processor image and confirmed importable in container
- Created src/model/.gitkeep so the model directory is git-tracked and copied into /app/src/model/ inside the container via COPY src/ ./src/
- Full down -v / build / up -d cycle completed: all 6 services healthy after rebuild

## Task Commits

Each task was committed atomically:

1. **Task 1: Add ml_score column to Transaction ORM model** - `e11775f` (feat)
2. **Task 2: Pin ML library dependencies in requirements.txt** - `9af9c7a` (chore)
3. **Task 3: Create src/model/ directory and validate full stack** - `5b1d3d0` (chore)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `src/db_setup.py` - Added ml_score = Column(Numeric(5, 4)) to Transaction class after processed_at
- `requirements.txt` - Appended 5 ML library pins (scikit-learn, xgboost, joblib, pandas, numpy) with comment block
- `src/model/.gitkeep` - Created to git-track the model artifact directory; copied into container at /app/src/model/

## Decisions Made
- ml_score is nullable: no nullable=False constraint, so processor rows written before Phase 8 wires inference do not fail with NOT NULL violations
- numpy==1.26.4 chosen as last 1.x LTS — numpy 2.x has C-API friction on python:3.11-slim
- xgboost==2.1.4 chosen over 2.x latest — v3.x has breaking changes
- pandas pinned explicitly even though it is training-only, to prevent version drift on container rebuild

## Deviations from Plan

None - plan executed exactly as written.

One operational note: the INFRA-03 verification command `docker exec fraud_detection-processor-1 ls /app/src/model` failed in Git Bash on Windows due to automatic Unix-path-to-Windows-path translation. Using `//app/src/model` (double-slash prefix) bypassed the translation and confirmed `.gitkeep` is present. This is a shell environment behavior, not a code deviation.

## Issues Encountered
- Git Bash on Windows translates `/app/src/model` to `C:/Program Files/Git/app/src/model` inside `docker exec` commands. Resolved by using `//app/src/model` prefix which disables MSYS path conversion. All three INFRA requirements confirmed passing.

## User Setup Required

None - no external service configuration required.

## Self-Check: PASSED

All files confirmed present:
- src/db_setup.py - FOUND
- requirements.txt - FOUND
- src/model/.gitkeep - FOUND
- 06-01-SUMMARY.md - FOUND

All commits confirmed:
- e11775f (Task 1: feat - ml_score column)
- 9af9c7a (Task 2: chore - ML library pins)
- 5b1d3d0 (Task 3: chore - model directory)

## Next Phase Readiness
- Phase 7 (Training Script) can proceed: ml_score column exists, ML libraries are installed, and /app/src/model/ is available for writing fraud_model.joblib
- Phase 8 (Inference): write_to_db() in processor.py needs inspection before modification to confirm ml_score field wiring; pkl path inside container is /app/src/model/fraud_model.joblib
- Phase 9 (Dashboard): ml_score column ready to query for score visualization

---
*Phase: 06-schema-and-dependencies*
*Completed: 2026-03-09*
