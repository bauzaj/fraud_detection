# Fraud Detection Pipeline

## Project Overview
Real-time payment fraud detection pipeline. GitHub: https://github.com/bauzaj/fraud_detection

## Stack
- **Streaming**: Apache Kafka (confluent-kafka)
- **Database**: PostgreSQL 15 (port 5433 externally, 5432 internally)
- **Containerization**: Docker Compose (6 services: zookeeper, kafka, postgres, generator, processor, dashboard)
- **Dashboard**: Streamlit (port 8501)
- **Language**: Python 3.11

## Key Files
- `src/generator.py` - Produces transactions to Kafka with 3 fraud patterns
- `src/processor.py` - Consumes from Kafka, runs fraud detection, writes to Postgres
- `src/dashboard.py` - Streamlit dashboard, auto-refreshes every 10 seconds
- `src/db_setup.py` - SQLAlchemy models and table initialization
- `src/data_quality.py` - Transaction validation

## Fraud Rules (processor.py)
- `high_amount`: amount > 1000
- `high_velocity`: >= 8 transactions in 5 minutes
- `unusual_amount`: amount > 3x user average (requires 2+ history)

## Generator Fraud Patterns (generator.py)
- `high_amount` (45%): single tx, $1,100–$2,500, any user
- `velocity` (15%): 10-tx burst at 50ms intervals, users 2000–9999 (separate from small pool)
- `unusual_amount` (40%): spike 3.1–4.5x user average, small pool users 1000–1100

## User Pools (fully isolated — no cross-contamination)
- `SMALL_POOL` `user_1000`–`user_1100` — seeded with 3 txs each; used **only** for `unusual_amount` fraud
- `VELOCITY_POOL` `user_2000`–`user_2999` — used **only** for velocity fraud bursts
- `GENERAL_POOL` `user_5000`–`user_9999` — used **only** for normal transactions and `high_amount` fraud

## Common Commands
- Start: `docker-compose up -d`
- Stop and wipe DB: `docker-compose down -v`
- Rebuild: `docker-compose build --no-cache <service>`
- Logs: `docker-compose logs <service> --tail=30`
- Query DB: `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "<query>"`