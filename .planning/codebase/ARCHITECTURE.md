# Architecture

**Analysis Date:** 2026-03-06

## Pattern Overview

**Overall:** Event-driven streaming pipeline with rule-based detection

**Key Characteristics:**
- Unidirectional data flow: generator → Kafka → processor → PostgreSQL → dashboard
- No shared in-memory state between services; processor maintains per-process in-memory transaction history only
- Rule evaluation is stateful within the processor process (in-memory `defaultdict`) but not persisted
- All services communicate via environment variables for configuration; no service discovery or shared config service

## Layers

**Transaction Generation Layer:**
- Purpose: Produce synthetic payment transactions with embedded fraud patterns
- Location: `src/generator.py`
- Contains: User pool definitions, fraud pattern logic, Kafka producer, seeding routine
- Depends on: Kafka (`payment-transactions` topic), `confluent-kafka` library, `faker`
- Used by: Nothing (producer only; Kafka receives its output)

**Stream Transport Layer:**
- Purpose: Decouple generator from processor; buffer messages
- Location: Docker service `kafka` (external), topic `payment-transactions`
- Contains: Single Kafka topic; single broker; Zookeeper for coordination
- Depends on: Zookeeper
- Used by: Generator (producer), Processor (consumer)

**Detection / Processing Layer:**
- Purpose: Consume transactions, validate, apply fraud rules, persist results
- Location: `src/processor.py`
- Contains: `FraudDetector` class, `write_to_db` function, `consume_and_process` main loop
- Depends on: Kafka consumer, PostgreSQL (`db_setup.Transaction`, `db_setup.FraudAlert`), `data_quality.validate_transaction`
- Used by: Nothing downstream (writes to DB only)

**Data Model / Schema Layer:**
- Purpose: Define ORM models and initialize database tables
- Location: `src/db_setup.py`
- Contains: `Transaction` model, `FraudAlert` model, `init_db()` function
- Depends on: PostgreSQL, SQLAlchemy
- Used by: `processor.py`, `dashboard.py`

**Validation Layer:**
- Purpose: Validate transaction payload before fraud evaluation
- Location: `src/data_quality.py`
- Contains: `validate_transaction(tx: dict) -> tuple[bool, list]`
- Depends on: Nothing external
- Used by: `processor.py` (called per message before `FraudDetector.detect_fraud`)

**Visualization Layer:**
- Purpose: Real-time dashboard displaying transaction metrics and fraud alerts
- Location: `src/dashboard.py`
- Contains: Streamlit page, SQL queries, auto-refresh loop
- Depends on: PostgreSQL (direct SQL via SQLAlchemy), `streamlit`, `pandas`
- Used by: End user (browser on port 8501)

## Data Flow

**Normal Transaction Flow:**

1. `generator.py` calls `generate_transaction()` to build a JSON payload
2. Payload is serialized to JSON and produced to Kafka topic `payment-transactions` via `publish()`
3. `processor.py` polls Kafka with `consumer.poll(1.0)` in a tight loop
4. Message is deserialized from JSON; `validate_transaction()` is called
5. If invalid, message is logged and skipped (no DB write)
6. `FraudDetector.detect_fraud()` evaluates three rules against in-memory history
7. Transaction history is appended in-memory (capped at 100 entries per user)
8. `write_to_db()` persists the `Transaction` row; if fraud, also persists a `FraudAlert` row
9. Dashboard auto-refreshes every 10 seconds, re-querying PostgreSQL for updated counts and alerts

**Fraud Seeding Flow (startup only):**

1. `generate_stream()` seeds 3 normal transactions per `SMALL_POOL` user before entering the main loop
2. Seeded transactions are flushed to Kafka synchronously with `producer.flush()`
3. Processor consumes and stores these in its in-memory history, enabling `unusual_amount` rule evaluation

## Key Abstractions

**FraudDetector:**
- Purpose: Stateful rule engine tracking per-user transaction history within a single process lifetime
- Examples: `src/processor.py` lines 15–49
- Pattern: Class with a `defaultdict(list)` keyed by `user_id`; rules are evaluated then history is appended; history is capped at 100 entries

**Transaction (ORM Model):**
- Purpose: Represents a payment transaction record in PostgreSQL
- Examples: `src/db_setup.py` lines 12–24
- Pattern: SQLAlchemy declarative model; `session.merge()` used for upsert semantics (idempotent by `transaction_id` primary key)

**FraudAlert (ORM Model):**
- Purpose: Represents a fraud detection event linked to a transaction
- Examples: `src/db_setup.py` lines 26–33
- Pattern: SQLAlchemy declarative model with auto-increment `alert_id`; `rules_triggered` stored as PostgreSQL `ARRAY(String)`

**User Pools:**
- Purpose: Isolate traffic types to ensure fraud rule signal is clean and non-contaminated
- Examples: `src/generator.py` lines 48–52
- Pattern: Three named lists (`SMALL_POOL`, `VELOCITY_POOL`, `GENERAL_POOL`); each pool is used by exactly one fraud type or normal traffic

## Entry Points

**generator (Docker entrypoint):**
- Location: `src/generator.py` — `if __name__ == "__main__": generate_stream(rate_per_sec=10)`
- Triggers: Docker Compose starts `generator` service; `restart: on-failure` for resilience
- Responsibilities: Seed user history, then continuously produce transactions to Kafka at 10 tx/sec

**processor (Docker entrypoint):**
- Location: `src/processor.py` — `if __name__ == "__main__": consume_and_process()`
- Triggers: Docker Compose starts `processor` service after `kafka` and `postgres`
- Responsibilities: Initialize DB tables, consume Kafka messages, validate, detect fraud, write to DB

**dashboard (Docker entrypoint):**
- Location: `src/dashboard.py` — invoked via `python -m streamlit run src/dashboard.py --server.port 8501`
- Triggers: Docker Compose starts `dashboard` service; browser accesses port 8501
- Responsibilities: Query PostgreSQL, render metrics and charts, auto-refresh every 10 seconds

## Error Handling

**Strategy:** Fail-fast with logging; `restart: on-failure` at the Docker Compose level provides recovery

**Patterns:**
- Kafka delivery failures are reported via `delivery_report` callback in `src/generator.py` but do not halt generation
- Consumer errors are printed and the loop continues (`src/processor.py` lines 101–103)
- Invalid transactions are counted, logged, and skipped — no dead-letter queue exists
- `KeyboardInterrupt` in the processor triggers graceful consumer and session close (`src/processor.py` lines 124–128)
- No retry logic for DB writes; a failed `session.commit()` will propagate as an unhandled exception

## Cross-Cutting Concerns

**Logging:** `print()` statements only — no structured logging library. Output goes to Docker container stdout, visible via `docker-compose logs`.

**Validation:** Centralized in `src/data_quality.py`; called by processor before any fraud evaluation. Generator does not validate before producing.

**Authentication:** No application-level auth. PostgreSQL credentials are passed via `DATABASE_URL` environment variable (plaintext in `docker-compose.yml`). Kafka has no auth configured.

---

*Architecture analysis: 2026-03-06*
