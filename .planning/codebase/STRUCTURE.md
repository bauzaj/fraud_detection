# Structure

## Directory Layout

```
fraud_detection/
├── src/                        # All Python application code
│   ├── generator.py            # Kafka producer — generates synthetic transactions
│   ├── processor.py            # Kafka consumer — fraud detection + DB writes
│   ├── dashboard.py            # Streamlit dashboard (port 8501)
│   ├── db_setup.py             # SQLAlchemy models + table initialization
│   ├── data_quality.py         # Transaction validation logic
│   └── __pycache__/            # Python bytecode cache
├── .planning/                  # GSD planning directory
│   └── codebase/               # Codebase analysis documents (this directory)
├── .claude/                    # Claude Code configuration
│   └── get-shit-done/          # GSD workflow tooling
│       ├── bin/                # CLI tools (gsd-tools.cjs)
│       ├── templates/          # GSD config templates
│       └── workflows/          # Workflow markdown files
├── docker-compose.yml          # Defines 6 services: zookeeper, kafka, postgres,
│                               #   generator, processor, dashboard
├── Dockerfile                  # Single Dockerfile shared by generator/processor/dashboard
├── requirements.txt            # Python dependencies
├── CLAUDE.md                   # Claude Code project context (checked in)
├── README.md                   # Project documentation
├── generator_logs.txt          # Log output artifact (should be gitignored)
└── LICENSE
```

## Key File Locations

| Purpose | Path |
|---|---|
| Transaction production | `src/generator.py` |
| Fraud detection logic | `src/processor.py` |
| Fraud rules | `src/processor.py` (inline functions) |
| Database schema | `src/db_setup.py` |
| Input validation | `src/data_quality.py` |
| Streamlit UI | `src/dashboard.py` |
| Service orchestration | `docker-compose.yml` |
| Python deps | `requirements.txt` |

## Naming Conventions

- **Files**: `snake_case.py` — all source files follow this pattern
- **Services**: Named functionally in `docker-compose.yml` (`generator`, `processor`, `dashboard`, `postgres`, `kafka`, `zookeeper`)
- **User IDs**: String format `user_NNNN` (e.g., `user_1042`, `user_5312`)
- **Fraud rule names**: `snake_case` strings stored in DB (e.g., `high_amount`, `high_velocity`, `unusual_amount`)

## Where to Place New Code

| New code type | Location |
|---|---|
| New fraud detection rule | `src/processor.py` — add rule function + wire into detection loop |
| New transaction field | `src/db_setup.py` (model) + `src/generator.py` (production) + `src/processor.py` (consumption) |
| New dashboard metric | `src/dashboard.py` |
| New validation | `src/data_quality.py` |
| New service | `docker-compose.yml` + new `src/` file |
| Tests (when added) | `tests/` directory at project root |

## Docker Service Ports

| Service | Internal Port | External Port |
|---|---|---|
| postgres | 5432 | 5433 |
| kafka | 9092 | 9092 |
| zookeeper | 2181 | 2181 |
| dashboard | 8501 | 8501 |
