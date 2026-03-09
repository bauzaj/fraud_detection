---
phase: 7
slug: training-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None — no test framework exists in this codebase |
| **Config file** | none — no test files exist |
| **Quick run command** | `python src/train_model.py` |
| **Full suite command** | `python src/train_model.py && ls src/model/fraud_model.joblib` |
| **Estimated runtime** | ~30-60 seconds (depends on row count in DB) |

---

## Sampling Rate

- **After every task commit:** Run the verification command for the specific task (see Per-Task Verification Map)
- **After every plan wave:** Run `python src/train_model.py` and verify all 4 success criteria pass
- **Before `/gsd:verify-work`:** Script exits 0 + artifact exists + recall >= 0.80 printed
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 7-01-01 | 01 | 1 | TRAIN-01, TRAIN-02 | smoke | `python src/train_model.py 2>&1 \| grep "Class distribution"` | N/A — shell | ⬜ pending |
| 7-01-02 | 01 | 1 | TRAIN-03 | smoke | `python src/train_model.py 2>&1 \| grep -E "PR-AUC\|recall"` | N/A — shell | ⬜ pending |
| 7-01-03 | 01 | 1 | TRAIN-04 | smoke | `ls src/model/fraud_model.joblib` | N/A — shell | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No test files need to be created for Phase 7. All verification is done via running `src/train_model.py` and checking its output. No Python test framework is needed.

*Existing test infrastructure: None — codebase has no test framework (documented in `.planning/codebase/TESTING.md`).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Script exits 0 and prints PR-AUC and recall | TRAIN-01, TRAIN-03 | Requires live PostgreSQL with data; not automatable without CI | Run `python src/train_model.py` — expect PR-AUC and classification report in output, no Python traceback |
| Class distribution shows both classes | TRAIN-02 | Requires live data with both fraud and non-fraud rows | Script prints class distribution; assertion `nunique() == 2` must not raise AssertionError |
| Fraud-class recall >= 0.80 | TRAIN-03 | Metric depends on actual data volume and quality | Read recall value for "fraud" class from classification_report output |
| `src/model/fraud_model.joblib` exists after script | TRAIN-04 | Filesystem check after script completes | `ls src/model/fraud_model.joblib` — expect file to exist with non-zero size |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
