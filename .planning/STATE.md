# State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-06)

**Core value:** Every transaction is scored for fraud risk in real time — the score is visible on the dashboard and drives downstream alerts.
**Current focus:** Defining requirements for v2.0 ML Fraud Scoring

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-06 — Milestone v2.0 ML Fraud Scoring started

## Accumulated Context

- Generator logs are being written to `generator_logs.txt` at project root — this file should be gitignored
- Git commit "WIP: Phase 6 ML scoring prep" predates GSD setup — phases 1–5 are considered the v1.0 pipeline, phase 6+ is ML Fraud Scoring
- PostgreSQL accessible externally on port 5433 (internal: 5432) — use port 5433 for local tools like pgAdmin
- All services run in Docker — no local Python install needed for development
- `is_fraud` is stored as String ("True"/"False") in the transactions table — a known schema bug, not being fixed this milestone unless it blocks ML training
