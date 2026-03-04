from faker import Faker
import os
import random
from datetime import datetime
import json
import time
from confluent_kafka import Producer

fake = Faker()

def delivery_report(err, msg):
    """Kafka delivery callback"""
    if err:
        print(f'Delivery failed: {err}')

def generate_transaction(user_id=None, is_fraud=False):
    tx = {
        "transaction_id": f"tx_{fake.uuid4()[:8]}",
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id or f"user_{random.randint(1000, 9999)}",
        "merchant_id": f"merch_{random.randint(100, 999)}",
        "amount": round(random.uniform(10, 500), 2),
        "card_last_4": fake.credit_card_number()[-4:],
        "merchant_category": random.choice(["retail", "dining", "travel", "online", "gas"]),
        "location": {
            "lat": round(27.9506 + random.uniform(-0.5, 0.5), 4),
            "lon": round(-82.4572 + random.uniform(-0.5, 0.5), 4)
        },
        "is_fraud": is_fraud
    }
    return tx

def publish(producer, tx):
    producer.produce(
        'payment-transactions',
        key=tx['transaction_id'],
        value=json.dumps(tx),
        callback=delivery_report
    )
    producer.poll(0)

def generate_stream(rate_per_sec=10, fraud_rate=0.03):
    producer = Producer({
        'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    })

    # Fully isolated user pools — each pool is used by exactly one traffic type
    SMALL_POOL    = [f"user_{i}" for i in range(1000, 1101)]   # unusual_amount fraud + seeding only
    VELOCITY_POOL = [f"user_{i}" for i in range(2000, 3000)]   # velocity fraud bursts only
    GENERAL_POOL  = [f"user_{i}" for i in range(5000, 10000)]  # normal transactions + high_amount fraud only
    # Track running average amount per small-pool user (for unusual_amount spike calculation)
    user_avg_amounts = {u: round(random.uniform(50, 200), 2) for u in SMALL_POOL}

    count = 0

    # Seed: send 5 normal transactions for every small-pool user so the processor
    # has enough history to evaluate the unusual_amount rule from the start
    print("Seeding user history for unusual_amount detection...")
    for user_id in SMALL_POOL:
        for _ in range(3):
            tx = generate_transaction(user_id=user_id, is_fraud=False)
            tx['amount'] = round(random.uniform(30, 150), 2)
            publish(producer, tx)
            user_avg_amounts[user_id] = (user_avg_amounts[user_id] * 0.9) + (tx['amount'] * 0.1)
            count += 1
    producer.flush()
    print(f"Seeded {count} transactions. Starting main stream...")

    while True:
        is_fraud = random.random() < fraud_rate
        fraud_type = None

        if is_fraud:
            fraud_type = random.choices(
                ['high_amount', 'velocity', 'unusual_amount'],
                weights=[0.45, 0.15, 0.40])[0]

        if fraud_type == 'velocity':
            # Burst 10 transactions from same user in quick succession
            user_id = random.choice(VELOCITY_POOL)
            for _ in range(10):
                tx = generate_transaction(user_id=user_id, is_fraud=True)
                tx['amount'] = round(random.uniform(50, 300), 2)
                publish(producer, tx)
                count += 1
                time.sleep(0.05)

        elif fraud_type == 'unusual_amount':
            # Pick a small-pool user and spike their amount well above their average
            user_id = random.choice(SMALL_POOL)
            avg = user_avg_amounts[user_id]
            tx = generate_transaction(user_id=user_id, is_fraud=True)
            tx['amount'] = round(avg * random.uniform(3.1, 4.5), 2)
            publish(producer, tx)
            count += 1

        else:
            # Normal transaction or high_amount fraud — always use GENERAL_POOL
            user_id = random.choice(GENERAL_POOL)
            tx = generate_transaction(user_id=user_id, is_fraud=is_fraud)
            if is_fraud:  # high_amount
                tx['amount'] = round(random.uniform(1100, 2500), 2)
            publish(producer, tx)
            count += 1

        if count % 100 == 0:
            print(f"Published {count} transactions")

        time.sleep(1 / rate_per_sec)

if __name__ == "__main__":
    generate_stream(rate_per_sec=10)