---
phase: 6
slug: schema-and-dependencies
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None — no test framework exists in this codebase |
| **Config file** | none — no test files exist |
| **Quick run command** | `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "\d transactions"` |
| **Full suite command** | `docker-compose down -v && docker-compose build && docker-compose up -d && docker-compose ps` |
| **Estimated runtime** | ~3-5 minutes (docker build with new ML packages is slow on first run) |

---

## Sampling Rate

- **After every task commit:** Run the docker exec verification command for the specific requirement (see Per-Task Verification Map)
- **After every plan wave:** Run full reset sequence (`down -v && build && up -d`) and verify all three criteria pass
- **Before `/gsd:verify-work`:** All 6 services healthy + all three docker exec checks passing
- **Max feedback latency:** 5 minutes (dominated by docker build time)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 01 | 1 | INFRA-01 | smoke | `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "\d transactions" \| grep ml_score` | N/A — shell | ⬜ pending |
| 6-01-02 | 01 | 1 | INFRA-02 | smoke | `docker-compose build processor 2>&1 \| tail -5` | N/A — shell | ⬜ pending |
| 6-01-03 | 01 | 1 | INFRA-03 | smoke | `docker exec fraud_detection-processor-1 ls /app/src/model` | N/A — shell | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No test files need to be created for Phase 6. All verification is done via docker/psql shell commands. No Python test framework is needed.

*Existing test infrastructure: None — codebase has no test framework (documented in `.planning/codebase/TESTING.md`).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `ml_score` column exists with correct type | INFRA-01 | No test framework; shell command required | `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "\d transactions"` — expect `ml_score \| numeric(5,4)` row |
| ML packages install on python:3.11-slim | INFRA-02 | Docker build process; not automatable without CI | `docker-compose build processor` — inspect build output for errors |
| `src/model/` directory exists in container | INFRA-03 | Container filesystem inspection required | `docker exec fraud_detection-processor-1 ls /app/src/model` — expect `.gitkeep` in output |
| All 6 services healthy after `down -v` cycle | all INFRA | Docker Compose health check; not automatable | `docker-compose ps` — all 6 services show `Up` status |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5 minutes
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
