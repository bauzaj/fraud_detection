# External Integrations

**Analysis Date:** 2026-03-06

## APIs & External Services

**Message Streaming:**
- Apache Kafka (Confluent Platform 7.5.0) - Core event bus for payment transaction streaming
  - SDK/Client: `confluent-kafka==2.3.0` (`confluent_kafka.Producer`, `confluent_kafka.Consumer`)
  - Auth: None (PLAINTEXT protocol, no SASL/SSL)
  - Topic: `payment-transactions`
  - Producer: `src/generator.py`
  - Consumer: `src/processor.py` (consumer group: `fraud-detector`, offset: `earliest`)

**Zookeeper:**
- Apache Zookeeper (Confluent 7.5.0) - Kafka coordination/metadata
  - Internal port: 2181
  - Not directly accessed by application code; managed by Kafka service in `docker-compose.yml`

## Data Storage

**Databases:**
- PostgreSQL 15
  - Connection env var: `DATABASE_URL`
  - Default connection: `postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection`
  - Internal Docker connection: `postgresql://fraud_user:fraud_pass@postgres:5432/fraud_detection`
  - External port: 5433 (mapped from internal 5432)
  - Client/ORM: SQLAlchemy 2.0.23 + psycopg2-binary 2.9.9
  - Tables defined in: `src/db_setup.py`
    - `transactions` - All processed payment records
    - `fraud_alerts` - Records where fraud rules triggered
  - Used by: `src/processor.py` (writes), `src/dashboard.py` (reads), `src/db_setup.py` (schema init)
  - Max connections: 200 (set via `command: postgres -c max_connections=200` in `docker-compose.yml`)
  - Volume: `postgres_data` (named Docker volume, persists across restarts)

**File Storage:**
- Local filesystem only (Docker volume for Postgres data)

**Caching:**
- None - `FraudDetector` in `src/processor.py` maintains in-memory per-user transaction history (up to last 100 transactions per user via `self.user_transactions` defaultdict)

## Authentication & Identity

**Auth Provider:**
- None - No external auth provider
- Database uses hardcoded credentials (`fraud_user` / `fraud_pass`) in `docker-compose.yml` environment vars
- No application-level authentication (dashboard is open access)

## Monitoring & Observability

**Error Tracking:**
- None - No external error tracking service (e.g., Sentry)

**Logs:**
- stdout/stderr only via Python `print()` statements
- `src/generator.py`: logs every 100 published transactions, delivery failures
- `src/processor.py`: logs every 100 processed transactions, fraud detections, invalid transactions
- `src/dashboard.py`: no explicit logging
- Accessible via: `docker-compose logs <service> --tail=30`

**Metrics:**
- None - No metrics collection (e.g., Prometheus, Datadog)

## CI/CD & Deployment

**Hosting:**
- Single-host Docker Compose deployment (no cloud hosting configured)

**CI Pipeline:**
- None detected (no `.github/workflows/`, `.gitlab-ci.yml`, or similar)

**Container Registry:**
- Not configured - images built locally via `docker-compose build`

## Environment Configuration

**Required env vars:**
- `KAFKA_BOOTSTRAP_SERVERS` - Used by `src/generator.py` and `src/processor.py`
  - Internal (Docker): `kafka:29092`
  - External (local dev): `localhost:9092`
- `DATABASE_URL` - Used by `src/processor.py`, `src/dashboard.py`, `src/db_setup.py`
  - Internal (Docker): `postgresql://fraud_user:fraud_pass@postgres:5432/fraud_detection`
  - External (local dev): `postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection`

**Secrets location:**
- Credentials hardcoded in `docker-compose.yml` environment blocks and as `os.getenv` defaults in source files
- No `.env` file detected
- No secrets manager in use

## Webhooks & Callbacks

**Incoming:**
- None - No HTTP endpoints exposed by the application

**Outgoing:**
- None - No outbound HTTP calls to external APIs

## Network Topology

**Internal Docker Network:**
- Network name: `fraud-net` (bridge driver)
- All 6 services communicate on this network
- Only ports exposed to host: `9092` (Kafka), `5433` (Postgres), `8501` (Streamlit dashboard)

**Data Flow:**
1. `generator` produces JSON messages to Kafka topic `payment-transactions`
2. `processor` consumes from `payment-transactions`, runs fraud rules, writes to Postgres
3. `dashboard` reads from Postgres via SQLAlchemy, renders metrics in Streamlit, auto-refreshes every 10 seconds

---

*Integration audit: 2026-03-06*
