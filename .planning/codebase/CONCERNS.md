# Concerns

## Tech Debt

### In-Memory State Lost on Restart
- `FraudDetector.user_transactions` dict lives only in memory (`src/processor.py`)
- Every container restart wipes velocity history and user average history
- `high_velocity` and `unusual_amount` rules go blind on restart until enough new transactions accumulate
- **Impact:** False negatives after any restart; prod reliability is low for these rules

### `is_fraud` Stored as String, Not Boolean
- `src/db_setup.py` line 22: `is_fraud` column is `String` type
- Stored values are likely `"True"`/`"False"` strings
- Makes DB-level boolean queries unreliable; should be `Boolean`

### `fraud_score` Is Not a Real Risk Signal
- `src/processor.py` line 45: score is simply `triggered_rules / total_rules` (0.33 / 0.67 / 1.0)
- No probabilistic model, no weighted rules, no calibration
- Named "score" but carries no actual ML or statistical meaning

### Missing Foreign Key: `fraud_alerts.transaction_id`
- `src/db_setup.py` line 29: no FK constraint linking `fraud_alerts` back to `transactions`
- Orphaned alert rows are possible; DB can't enforce referential integrity

### Stale README
- References old file names: `payment_generator.py`, `fraud_processor.py` (actual names differ)
- Documents velocity threshold incorrectly

---

## Security

### Hardcoded Credentials
- `fraud_user:fraud_pass` hardcoded in `src/db_setup.py`, `src/processor.py`, `src/dashboard.py`, and `docker-compose.yml`
- No `.env` file or secret management — credentials are in version control

### No Dashboard Authentication
- Streamlit dashboard (port 8501) is open with no login, API key, or network restriction
- Anyone with network access can view all transaction and fraud data

### Kafka PLAINTEXT with No Auth
- Kafka on port 9092 uses `PLAINTEXT` protocol — no TLS, no SASL
- Any process with network access can produce or consume messages

### Unhandled JSON Parse in Processor
- No try/except around `json.loads` in `src/processor.py`
- A single malformed Kafka message will crash the consumer process entirely
- **Impact:** DoS via one bad message; requires manual container restart

---

## Performance

### No DB Indexes on Hot Query Columns
- Missing indexes on `transactions.user_id`, `transactions.timestamp`, `fraud_alerts.detected_at`
- Dashboard queries and fraud rule lookups will do full-table scans as data grows

### Linear Velocity Window Scan
- Velocity rule scans up to 100 in-memory entries per incoming message
- Acceptable now; will degrade if window size grows or processor is under high load

### Single DB Session, No Error Recovery
- One SQLAlchemy session reused for all writes
- A transient DB failure has no retry logic — messages are dropped silently

---

## Fragile Areas

### Container Startup Race Condition
- `depends_on` in `docker-compose.yml` only checks container started, not service readiness
- Generator/processor can start before Kafka/Postgres are ready
- Papered over with `restart: on-failure` — not a proper healthcheck solution

### Multi-Instance Processor Would Break Rules
- Running >1 processor container would split in-memory user history across instances
- `high_velocity` and `unusual_amount` rules would silently compute on partial data
- No shared state store (Redis, DB-backed) exists to support horizontal scaling

### Generator and Processor Have Diverging Averages
- `generator.py` maintains its own `user_avg_amounts` dict for seeding unusual_amount patterns
- `processor.py` computes averages from its own in-memory history
- These diverge on restart; generator may produce spikes that processor doesn't flag correctly

---

## Missing Entirely

| Gap | Risk |
|---|---|
| No test suite | Any change could break fraud rules silently |
| No dead-letter queue | Invalid/rejected messages are lost with no record |
| No DB write error handling in processor | Fraud events can be silently dropped |
| No alerting or monitoring | No visibility into consumer lag, error rates, or detection accuracy |
| No schema migrations | Any model change requires manual table drops or `down -v` |
