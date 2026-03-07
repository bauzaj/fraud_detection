# Coding Conventions

**Analysis Date:** 2026-03-06

## Naming Patterns

**Files:**
- `snake_case` for all Python modules: `generator.py`, `db_setup.py`, `data_quality.py`
- No suffix pattern — names are descriptive nouns or verb-noun pairs

**Functions:**
- `snake_case` for all functions: `generate_transaction`, `detect_fraud`, `write_to_db`, `validate_transaction`
- Verbs as prefixes for action functions: `generate_`, `publish_`, `consume_`, `validate_`, `write_`
- Callbacks follow their library's naming: `delivery_report` (Kafka convention)

**Classes:**
- `PascalCase`: `FraudDetector`, `Transaction`, `FraudAlert`
- SQLAlchemy ORM models named as singular nouns: `Transaction`, `FraudAlert`

**Variables:**
- `snake_case` for all variables: `user_id`, `fraud_score`, `rules_triggered`, `avg_amount`
- ALL_CAPS for constants and user pools: `SMALL_POOL`, `VELOCITY_POOL`, `GENERAL_POOL`
- Short names acceptable in tight loops: `tx` (transaction), `err`, `msg`, `ts`

**Database columns:**
- `snake_case` matching Python field names: `transaction_id`, `card_last_4`, `detected_at`

## Code Style

**Formatting:**
- No linter or formatter config file detected (no `.flake8`, `.pylintrc`, `pyproject.toml`, `setup.cfg`, or `ruff.toml`)
- Indentation: 4 spaces throughout
- Line length: no enforced limit; lines stay reasonably short in practice
- Trailing whitespace present in `processor.py` lines 18, 31 (minor)

**String formatting:**
- f-strings used throughout for interpolation: `f"tx_{fake.uuid4()[:8]}"`, `f"FRAUD DETECTED: {result['transaction_id']}"`
- No `.format()` or `%` string formatting observed

**Inline comments:**
- Hash comments above logical blocks: `# Required fields`, `# Amount checks`, `# Write fraud alert if flagged`
- Comments explain intent, not mechanics

## Import Organization

**Order observed (not enforced by tooling):**
1. Standard library imports: `os`, `json`, `time`, `random`, `datetime`, `collections`
2. Third-party imports: `confluent_kafka`, `sqlalchemy`, `faker`, `streamlit`, `pandas`
3. Local imports: `from db_setup import Transaction, FraudAlert`, `from data_quality import validate_transaction`

**Pattern:** No blank lines between import groups. All imports at file top except one deferred import in `processor.py`:
```python
# processor.py line 79 — deferred to avoid circular import issues
from db_setup import init_db
```

**Path aliases:** None used. Local modules imported by name from same `src/` directory.

## Docstrings and Comments

**Docstrings:**
- Only two docstrings present across the entire codebase:
  - `generator.py:12` — `"""Kafka delivery callback"""`
  - `data_quality.py:4` — `"""Returns (is_valid, list of errors)"""`
- Most functions have no docstring; intent conveyed via inline comments

**Comment density:** Moderate. Block-level comments explain major sections (`# Seed: send 5 normal transactions...`, `# Burst 10 transactions from same user...`)

**When to add comments:** Explain non-obvious decisions (pool isolation rationale, seeding logic) and section breaks within long functions.

## Error Handling

**Strategy:** Minimal — errors are logged to stdout and processing continues. No custom exception classes.

**Patterns:**
- Kafka consumer errors checked with `msg.error()` and logged, then `continue` to next message
- Validation errors collected in a list and returned as `(False, errors)` — caller decides what to do
- `try/except ValueError` used specifically for timestamp parsing in `data_quality.py`
- `KeyboardInterrupt` caught in `consume_and_process()` to allow graceful shutdown via `finally`
- No `except Exception` broad catches; error handling is narrow and specific

**Validation pattern** (from `data_quality.py`):
```python
def validate_transaction(tx: dict) -> tuple[bool, list]:
    errors = []
    # ... checks append to errors list
    return len(errors) == 0, errors
```

**Database writes:** No explicit exception handling around `session.commit()` — a DB failure would bubble up and crash the processor.

## Type Annotations

**Usage:** Sparse. Only `data_quality.py` uses type hints:
```python
def validate_transaction(tx: dict) -> tuple[bool, list]:
```
All other functions in `generator.py`, `processor.py`, and `db_setup.py` have no type annotations.

## Configuration

**Pattern:** Environment variables accessed via `os.getenv()` with inline fallback defaults:
```python
os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
os.getenv('DATABASE_URL', 'postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection')
```
The `DATABASE_URL` default is duplicated identically in `processor.py`, `db_setup.py`, and `dashboard.py` — three separate definitions.

## Data Structures

**Transaction dict keys:** string-keyed dicts used throughout as the primary data container; no dataclass or Pydantic model:
```python
tx = {
    "transaction_id": ...,
    "timestamp": ...,
    "user_id": ...,
    "merchant_id": ...,
    "amount": ...,
    "card_last_4": ...,
    "merchant_category": ...,
    "location": {"lat": ..., "lon": ...},
    "is_fraud": ...
}
```

**In-memory state:** `defaultdict(list)` in `FraudDetector` for per-user transaction history; list capped at 100 entries.

## Module Design

**Exports:** No `__all__` defined. Public API is implicit.

**Barrel files:** None. Each module is imported directly.

**Entry points:** All modules use `if __name__ == "__main__":` guards for direct execution.

**Module responsibilities:**
- `src/generator.py` — Kafka producer and fraud pattern generation
- `src/processor.py` — Kafka consumer, fraud detection logic, DB write orchestration
- `src/data_quality.py` — Transaction validation (pure function, no side effects)
- `src/db_setup.py` — SQLAlchemy ORM models and table initialization
- `src/dashboard.py` — Streamlit UI; runs as a top-level script (no functions)

---

*Convention analysis: 2026-03-06*
