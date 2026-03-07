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

Progress: [██░░░░░░░░] 20% (v1.0 complete; v2.0 not started)

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

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [v2.0 planning]: ML inference stays in-process inside processor.py — no new Docker services this milestone
- [v2.0 planning]: Model artifact baked into processor Docker image at build time (not volume-mounted)
- [v2.0 planning]: `is_fraud` String-to-int casting uses `.map({'True': 1, 'False': 0})` — schema type NOT fixed this milestone
- [v2.0 planning]: pandas imported only in train_model.py — must NOT be imported in processor.py hot path
- [v2.0 planning]: Training runs against host port 5433; inference runs in-container against internal port 5432

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 7 risk]: `amount_vs_user_avg_ratio` and `tx_count_last_5min` feature windows in train_model.py must exactly mirror the in-memory FraudDetector computation — inspect `detect_fraud()` before writing training code
- [Phase 8 risk]: `write_to_db()` function signature needs inspection before modifying — verify no other callers break; confirm pkl path inside container is `/app/src/model/fraud_model.joblib`
- [Phase 8 risk]: Training-serving skew is the highest-risk cross-phase issue — feature window constants (5-min velocity, max history) must be identical in both train_model.py and processor.py

## Session Continuity

Last session: 2026-03-06
Stopped at: Roadmap written, ready to plan Phase 6
Resume file: None
