# Testing

## Status
**No test framework configured. No test files exist in this codebase.**

## Current State
- No `pytest`, `unittest`, or any other test framework is installed or configured
- No test files found (`test_*.py`, `*_test.py`, `tests/` directory)
- No CI pipeline running tests
- No test coverage tooling

## Units That Would Need Testing

### `src/generator.py`
- Transaction generation logic (amounts, user pool selection)
- Fraud pattern triggering: `high_amount`, `velocity`, `unusual_amount`
- User pool isolation (SMALL_POOL, VELOCITY_POOL, GENERAL_POOL)
- Kafka producer message format

### `src/processor.py`
- Fraud detection rules:
  - `high_amount`: amount > 1000
  - `high_velocity`: >= 8 transactions in 5 minutes
  - `unusual_amount`: amount > 3x user average (requires 2+ history)
- Kafka consumer message parsing
- PostgreSQL write correctness

### `src/data_quality.py`
- Transaction validation logic
- Edge cases: missing fields, invalid types, boundary values

### `src/db_setup.py`
- SQLAlchemy model definitions
- Table initialization idempotency

## Recommended Test Structure (When Added)
```
tests/
  unit/
    test_generator.py       # Fraud pattern logic, user pool selection
    test_processor.py       # Fraud detection rules
    test_data_quality.py    # Validation logic
  integration/
    test_kafka_flow.py      # Producer → Consumer round-trip
    test_db_writes.py       # Processor → PostgreSQL
```

## Recommended Mocking Patterns
- Mock Kafka producer/consumer with `unittest.mock.MagicMock`
- Mock PostgreSQL with `pytest-postgresql` or in-memory SQLite for unit tests
- Use `freezegun` for time-dependent velocity rule tests
- Docker Compose services for integration tests (already containerized)

## Recommended Framework
- `pytest` + `pytest-cov` for unit/integration tests
- `pytest-mock` for mocking
- Add `pytest` to `requirements.txt` when implementing
