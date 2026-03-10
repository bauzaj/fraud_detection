---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: ML Fraud Scoring
status: planning
stopped_at: Checkpoint at 08-01 Task 2 (human-verify docker rebuild)
last_updated: "2026-03-10T18:50:30.932Z"
last_activity: 2026-03-06 — Roadmap created for v2.0 ML Fraud Scoring (Phases 6-9)
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 3
  completed_plans: 3
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-06)

**Core value:** Every transaction is scored for fraud risk in real time — the score is visible on the dashboard and drives downstream alerts.
**Current focus:** Phase 6 — Schema and Dependencies (v2.0 ML Fraud Scoring)

## Current Position

Phase: 6 of 9 (Schema and Dependencies)
Plan: Not started
Status: Ready to plan
Last activity: 2026-03-06 — Roadmap created for v2.0 ML Fraud Scoring (Phases 6-9)

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 0 (v2.0)
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 6-9 (v2.0) | TBD | - | - |

**Recent Trend:**
- No v2.0 plans completed yet

*Updated after each plan completion*
| Phase 06-schema-and-dependencies P01 | 6 | 3 tasks | 3 files |
| Phase 07-training-pipeline P01 | 23 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v2.0 planning]: ML inference stays in-process inside processor.py — no new Docker services this milestone
- [v2.0 planning]: Model artifact baked into processor Docker image at build time (not volume-mounted)
- [v2.0 planning]: `is_fraud` String-to-int casting uses `.map({'True': 1, 'False': 0})` — schema type NOT fixed this milestone
- [v2.0 planning]: pandas imported only in train_model.py — must NOT be imported in processor.py hot path
- [v2.0 planning]: Training runs against host port 5433; inference runs in-container against internal port 5432
- [Phase 06-schema-and-dependencies]: ml_score column is nullable so processor rows written before Phase 8 ML inference do not fail with NOT NULL violations
- [Phase 06-schema-and-dependencies]: numpy==1.26.4 pinned to last 1.x LTS; numpy 2.x has C-API friction on python:3.11-slim
- [Phase 07-training-pipeline]: Recall achieved via threshold optimization (0.13) not hyperparameter tuning — RF default 0.5 threshold gives 0.71 recall; PR-AUC=0.82 confirms model discriminates well
- [Phase 07-training-pipeline]: precision_recall_curve used to find decision threshold=0.13 achieving recall=0.8001 — Phase 8 uses predict_proba scores so threshold does not affect inference
- [Phase 08-processor-integration]: joblib/pandas/numpy imported at module level (not inside while loop hot path) in processor.py
- [Phase 08-processor-integration]: ML scoring block placed before user_transactions.append to preserve pre-append state matching training-time shift(1)/closed=left semantics
- [Phase 08-processor-integration]: cold-start amount_vs_user_avg_ratio defaults to 1.0 matching training fillna(1.0)

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 7 risk]: `amount_vs_user_avg_ratio` and `tx_count_last_5min` feature windows in train_model.py must exactly mirror the in-memory FraudDetector computation — inspect `detect_fraud()` before writing training code
- [Phase 8 risk]: `write_to_db()` function signature needs inspection before modifying — verify no other callers break; confirm pkl path inside container is `/app/src/model/fraud_model.joblib`
- [Phase 8 risk]: Training-serving skew is the highest-risk cross-phase issue — feature window constants (5-min velocity, max history) must be identical in both train_model.py and processor.py

## Session Continuity

Last session: 2026-03-10T18:50:23.150Z
Stopped at: Checkpoint at 08-01 Task 2 (human-verify docker rebuild)
Resume file: None
