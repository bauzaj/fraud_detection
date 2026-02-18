from datetime import datetime

def validate_transaction(tx: dict) -> tuple[bool, list]:
    """Returns (is_valid, list of errors)"""
    errors = []

    # Required fields
    required = ['transaction_id', 'timestamp', 'user_id', 'merchant_id', 'amount', 'card_last_4', 'merchant_category']
    for field in required:
        if field not in tx or tx[field] is None:
            errors.append(f"missing_field:{field}")

    if errors:
        return False, errors

    # Amount checks
    if tx['amount'] <= 0:
        errors.append("invalid_amount:negative_or_zero")
    if tx['amount'] > 50000:
        errors.append("invalid_amount:exceeds_max")

    # Timestamp not in future
    try:
        ts = datetime.fromisoformat(tx['timestamp'])
        if ts > datetime.now():
            errors.append("invalid_timestamp:future")
    except ValueError:
        errors.append("invalid_timestamp:unparseable")

    # Card last 4 digits
    if not str(tx['card_last_4']).isdigit() or len(str(tx['card_last_4'])) != 4:
        errors.append("invalid_card_last_4")

    return len(errors) == 0, errors