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
- `unusual_amount`: amount > 2.5x user average (requires 2+ history)

## Common Commands
- Start: `docker-compose up -d`
- Stop and wipe DB: `docker-compose down -v`
- Rebuild: `docker-compose build --no-cache <service>`
- Logs: `docker-compose logs <service> --tail=30`
- Query DB: `docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "<query>"`

## Current Issues Being Worked On
- Balancing fraud rule distribution (high_velocity currently over-represented)