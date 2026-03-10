---
phase: 8
slug: processor-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None — no test framework exists in this codebase |
| **Config file** | none — no test files exist |
| **Quick run command** | `docker-compose logs processor --tail=20` |
| **Full suite command** | `docker-compose build processor && docker-compose up -d processor && sleep 10 && docker-compose logs processor --tail=20` |
| **Estimated runtime** | ~3-5 minutes (docker build with model artifact baked in) |

---

## Sampling Rate

- **After every task commit:** Run the verification command for the specific task (see Per-Task Verification Map)
- **After every plan wave:** Run full rebuild sequence and verify all 4 success criteria pass
- **Before `/gsd:verify-work`:** "Model loaded" in logs + ml_score rows in DB + fraud_alerts still firing
- **Max feedback latency:** 5 minutes

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 8-01-01 | 01 | 1 | PROC-01, PROC-02 | smoke | `docker-compose logs processor --tail=20 2>&1 \| grep "Model loaded"` | N/A — shell | ⬜ pending |
| 8-01-02 | 01 | 1 | PROC-03 | smoke | `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "SELECT ml_score FROM transactions WHERE ml_score IS NOT NULL LIMIT 5"` | N/A — shell | ⬜ pending |
| 8-01-03 | 01 | 1 | PROC-04 | smoke | `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "SELECT COUNT(*) FROM fraud_alerts"` | N/A — shell | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No test files need to be created for Phase 8. All verification is done via docker/psql shell commands. No Python test framework is needed.

*Existing test infrastructure: None — codebase has no test framework (documented in `.planning/codebase/TESTING.md`).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Processor logs "Model loaded" once at startup | PROC-01 | Requires live Docker Compose stack; not automatable without CI | `docker-compose logs processor --tail=20` — expect "Model loaded" exactly once, not per-message |
| `ml_score` non-NULL for processed transactions | PROC-03 | Requires live data flowing through Kafka; not automatable | `SELECT ml_score FROM transactions WHERE ml_score IS NOT NULL LIMIT 10` — expect float values 0.0–1.0 |
| `fraud_alerts` still populated by rules | PROC-04 | Requires synthetic fraud events to arrive; timing-dependent | `SELECT COUNT(*) FROM fraud_alerts` — expect > 0 after 60+ seconds |
| All 6 services healthy after rebuild | all PROC | Docker Compose health check | `docker-compose ps` — all 6 services show `Up` status |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5 minutes
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
