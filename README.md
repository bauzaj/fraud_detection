# Real-Time Payment Fraud Detection Pipeline

A production-style streaming pipeline that ingests payment transactions, applies real-time fraud detection, and stores results for analysis — built with Kafka, Python, PostgreSQL, and Streamlit.

---

## Architecture

```
Payment Generator → Kafka → Stream Processor → PostgreSQL
                               ↓                    ↓
                         Fraud Detection       Streamlit Dashboard
                         (Rules Engine)
```

---

## Features

- **Real-time ingestion** via Apache Kafka at 10+ transactions/second
- **Multi-rule fraud detection:**
  - High amount threshold (>$1,000)
  - Velocity check (>=8 transactions in 5 minutes)
  - Unusual amount (3x user's historical average)
- **Data quality validation** on every event before processing
- **PostgreSQL storage** for transactions and fraud alerts
- **Live Streamlit dashboard** with fraud rate metrics and time-series chart

---

## Tech Stack

| Layer | Technology |
|---|---|
| Message Broker | Apache Kafka (via Docker) |
| Stream Processor | Python (confluent-kafka) |
| Data Validation | Custom Pydantic-style validators |
| Storage | PostgreSQL 15 (via Docker) |
| ORM | SQLAlchemy |
| Dashboard | Streamlit |
| Data Generation | Faker |

---

## Project Structure

```
fraud_detection/
├── docker-compose.yml        # Kafka + PostgreSQL containers
├── requirements.txt
└── src/
    ├── generator.py          # Synthetic transaction producer
    ├── processor.py          # Kafka consumer + fraud detection
    ├── train_model.py        # ML model training script
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

### 1. Start infrastructure

```bash
docker-compose up -d
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize the database

```bash
python src/db_setup.py
```

### 4. Launch the dashboard

```bash
python -m streamlit run src/dashboard.py
```

---

## Sample Output

```
Processed: 1000 | Fraud detected: 28 | Invalid: 0 | DB writes: 1000
FRAUD DETECTED: tx_9d62142b | Rules: ['high_amount']
FRAUD DETECTED: tx_e5c8d68f | Rules: ['high_velocity']
FRAUD DETECTED: tx_dbbc5089 | Rules: ['unusual_amount']
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
| ml_score | DECIMAL | ML fraud probability (0.0–1.0) |

**fraud_alerts**
| Column | Type | Description |
|---|---|---|
| alert_id | SERIAL PK | Auto-incremented alert ID |
| transaction_id | VARCHAR FK | Reference to transaction |
| fraud_score | DECIMAL | Score from 0.0 to 1.0 |
| rules_triggered | TEXT[] | Array of triggered rule names |
| detected_at | TIMESTAMP | Detection time |

---

## Key Design Decisions

- **Stateful in-memory processing** — user transaction history maintained in the processor for velocity and behavioral checks without a round-trip to the database
- **Idempotent writes** — `session.merge()` prevents duplicate transactions on replay
- **Port isolation** — PostgreSQL runs on 5433 to avoid conflicts with local installations
- **Offset management** — `auto.offset.reset: earliest` ensures no events are missed on processor restart

---

## Background

This project replicates patterns from production fraud detection systems, where real-time streaming pipelines are used to flag suspicious transactions before they are settled. The pipeline processes synthetic payment data modeled after real-world fraud patterns including card testing (velocity), account takeover (unusual amounts), and high-value fraud.
