# Technology Stack

**Analysis Date:** 2026-03-06

## Languages

**Primary:**
- Python 3.11 - All application logic (generator, processor, dashboard, data quality, DB setup)

**Secondary:**
- SQL - PostgreSQL queries in `src/dashboard.py` via pandas `read_sql`

## Runtime

**Environment:**
- Python 3.11 (declared in `Dockerfile`: `FROM python:3.11-slim`)

**Package Manager:**
- pip (via `requirements.txt`)
- Lockfile: Not present (no `pip.lock` or `poetry.lock`)

## Frameworks

**Core:**
- confluent-kafka 2.3.0 - Kafka producer/consumer (`src/generator.py`, `src/processor.py`)
- SQLAlchemy 2.0.23 - ORM for PostgreSQL (`src/db_setup.py`, `src/processor.py`, `src/dashboard.py`)
- Streamlit 1.31.0 - Web dashboard UI (`src/dashboard.py`)

**Data:**
- pandas - SQL query result handling in `src/dashboard.py` (installed as Streamlit dependency)
- Faker 22.0.0 - Synthetic transaction data generation (`src/generator.py`)

**Configuration:**
- python-dotenv 1.0.0 - Environment variable loading (imported in requirements, used via `os.getenv`)

**Database Driver:**
- psycopg2-binary 2.9.9 - PostgreSQL adapter (used by SQLAlchemy engine)

**Testing:**
- Not detected

**Build/Dev:**
- Docker Compose - Multi-service orchestration (`docker-compose.yml`)
- Docker - Container runtime (`Dockerfile`)

## Key Dependencies

**Critical:**
- `confluent-kafka==2.3.0` - Core streaming; all transaction flow depends on this
- `sqlalchemy==2.0.23` - All database interaction; used in processor, dashboard, and db_setup
- `psycopg2-binary==2.9.9` - PostgreSQL wire protocol; required by SQLAlchemy
- `streamlit==1.31.0` - Dashboard rendering; entire UI depends on this

**Infrastructure:**
- `faker==22.0.0` - Transaction synthetic data generation; required by generator
- `python-dotenv==1.0.0` - Env var management across all services

## Configuration

**Environment:**
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka broker address (default: `localhost:9092`; internal Docker: `kafka:29092`)
- `DATABASE_URL` - PostgreSQL connection string (default: `postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection`)
- Config read via `os.getenv()` in `src/generator.py`, `src/processor.py`, `src/db_setup.py`, `src/dashboard.py`

**Build:**
- `Dockerfile` - Single image for generator, processor, and dashboard services
- `docker-compose.yml` - Defines 6 services: zookeeper, kafka, postgres, generator, processor, dashboard

## Platform Requirements

**Development:**
- Docker and Docker Compose
- No local Python install required (all runs in containers)
- Local Kafka/Postgres accessible at `localhost:9092` and `localhost:5433` respectively

**Production:**
- Docker Compose (single-host deployment)
- PostgreSQL 15 with `max_connections=200`
- Kafka via Confluent Platform 7.5.0 images with Zookeeper coordination

---

*Stack analysis: 2026-03-06*
