# Real-Time Payment Fraud Detection Pipeline

A production-style streaming pipeline that ingests payment transactions, applies real-time fraud detection using both a rules engine and a trained ML model, and stores results for analysis — built with Kafka, Python, PostgreSQL, and Streamlit.

---

## Architecture

```
Payment Generator → Kafka → Stream Processor → PostgreSQL
                               ↓                    ↓
                         Fraud Detection       Streamlit Dashboard
                      (Rules + ML Model)      (Auto-refresh, ML scores)
```

---

## Features

- **Real-time ingestion** via Apache Kafka at 10+ transactions/second
- **Multi-rule fraud detection:**
  - High amount threshold (>$1,000)
  - Velocity check (>=8 transactions in 5 minutes)
  - Unusual amount (>2.5x user's historical average)
- **ML fraud scoring** via Random Forest model trained on historical transaction data
  - Features: transaction amount, user velocity, amount deviation, merchant category, hour of day, day of week
  - Outputs continuous probability score (0.0–1.0) per transaction
  - Rules engine kept as safety net alongside ML model
- **Separated user pools** for realistic fraud pattern generation
- **Data quality validation** on every event before processing
- **PostgreSQL storage** for transactions and fraud alerts
- **Live Streamlit dashboard** with auto-refresh, fraud rate metrics, ML score column, and time-series chart

---

## Tech Stack

| Layer | Technology |
|---|---|
| Message Broker | Apache Kafka (via Docker) |
| Stream Processor | Python (confluent-kafka) |
| ML Model | scikit-learn Random Forest |
| Data Validation | Custom validators |
| Storage | PostgreSQL 15 (via Docker) |
| ORM | SQLAlchemy |
| Dashboard | Streamlit |
| Data Generation | Faker |
| Containerization | Docker Compose |

---

## Project Structure

```
fraud_detection/
├── docker-compose.yml        # All 6 services: zookeeper, kafka, postgres, generator, processor, dashboard
├── requirements.txt
├── CLAUDE.md                 # Claude Code project context
├── .planning/                # GSD project planning docs
└── src/
    ├── generator.py          # Synthetic transaction producer (3 fraud patterns, separated user pools)
    ├── processor.py          # Kafka consumer + fraud detection + ML scoring
    ├── train_model.py        # Random Forest training script
    ├── data_quality.py       # Transaction validation
    ├── db_setup.py           # Schema initialization
    ├── dashboard.py          # Streamlit dashboard
    └── model/                # Trained model artifact (fraud_model.joblib)
```

---

## Getting Started

### Prerequisites
- Docker Desktop
- Python 3.11+

### 1. Start all services

```bash
docker-compose up -d
```

### 2. View live dashboard

Open **http://localhost:8501** in your browser. The dashboard auto-refreshes every 10 seconds.

### 3. Check pipeline logs

```bash
docker-compose logs processor --tail=30
docker-compose logs generator --tail=30
```

### 4. Query the database directly

```bash
docker exec fraud_detection-postgres-1 psql -U fraud_user -d fraud_detection -c "SELECT COUNT(*) FROM transactions;"
```

---

## Fraud Pattern Generator

The generator produces three distinct fraud patterns using fully separated user pools to prevent cross-contamination:

| Pattern | User Pool | Trigger |
|---|---|---|
| High Amount | user_5000–9999 | Amount > $1,000 |
| High Velocity | user_2000–2999 | 8+ transactions in 5 min |
| Unusual Amount | user_1000–1100 | Amount > 2.5x user average |

Fraud type weighting mirrors real-world distribution:
- High Amount: 45%
- Unusual Amount: 40%
- High Velocity: 15%

---

## ML Model

The Random Forest classifier is trained on historical transaction data labeled by the rules engine. Features engineered from raw transaction fields:

- `amount` — raw transaction amount
- `tx_count_last_5min` — velocity window count
- `amount_vs_avg_ratio` — deviation from user's running average
- `merchant_category` — one-hot encoded
- `hour_of_day` — extracted from timestamp
- `day_of_week` — extracted from timestamp

To retrain the model:

```bash
docker exec fraud_detection-processor-1 python src/train_model.py
```

---

## Data Model

**transactions**
| Column | Type | Description |
|---|---|---|
| transaction_id | VARCHAR PK | Unique transaction identifier |
| timestamp | TIMESTAMP | Transaction time |
| user_id | VARCHAR | Customer identifier |
| amount | DECIMAL | Transaction amount |
| merchant_category | VARCHAR | Retail, dining, travel, etc. |
| is_fraud | VARCHAR | Generator ground truth label |
| ml_score | DECIMAL | ML fraud probability (0.0–1.0) |

**fraud_alerts**
| Column | Type | Description |
|---|---|---|
| alert_id | SERIAL PK | Auto-incremented alert ID |
| transaction_id | VARCHAR FK | Reference to transaction |
| fraud_score | DECIMAL | Rules-based score (0.0–1.0) |
| rules_triggered | TEXT[] | Array of triggered rule names |
| detected_at | TIMESTAMP | Detection time |

---

## Key Design Decisions

- **Hybrid detection** — ML model scores every transaction while rules engine acts as a safety net, mirroring production fraud systems that layer statistical and deterministic approaches
- **Separated user pools** — fraud pattern generators use non-overlapping user ID ranges to prevent false positives from pool overlap
- **Stateful in-memory processing** — user transaction history maintained in processor for velocity and behavioral checks without database round-trips
- **Idempotent writes** — `session.merge()` prevents duplicate transactions on replay
- **Port isolation** — PostgreSQL runs on 5433 to avoid conflicts with local installations
- **Weighted fraud injection** — `random.choices` with explicit weights produces realistic fraud type distribution

---

## Background

This project replicates patterns from production fraud detection systems, where real-time streaming pipelines flag suspicious transactions before settlement. The pipeline processes synthetic payment data modeled after real-world fraud patterns including card testing (velocity), account takeover (unusual amounts), and high-value fraud. A Random Forest model trained on rule-labeled data demonstrates how ML can augment — rather than replace — deterministic rule systems in production environments.
