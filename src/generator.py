from faker import Faker
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
    
    if is_fraud:
        tx["amount"] = round(random.uniform(800, 2500), 2)
        
    return tx

def generate_stream(rate_per_sec=10, fraud_rate=0.03):
    producer = Producer({'bootstrap.servers': 'localhost:9092'})
    
    # Track user history to enable realistic unusual_amount fraud
    user_avg_amounts = {}
    
    count = 0
    while True:
        is_fraud = random.random() < fraud_rate
        fraud_type = None

        if is_fraud:
            fraud_type = random.choice(['high_amount', 'velocity', 'unusual_amount'])

        if fraud_type == 'velocity':
            # Burst 4 transactions from same user in quick succession
            user_id = f"user_{random.randint(1000, 9999)}"
            for _ in range(4):
                tx = generate_transaction(user_id=user_id, is_fraud=True)
                tx['amount'] = round(random.uniform(50, 300), 2)  # Normal amounts, high velocity
                producer.produce(
                    'payment-transactions',
                    key=tx['transaction_id'],
                    value=json.dumps(tx),
                    callback=delivery_report
                )
                producer.poll(0)
                count += 1
                time.sleep(0.05)  # Very fast — triggers velocity rule

        elif fraud_type == 'unusual_amount':
            # User with established history suddenly spends 3x their average
            user_id = f"user_{random.randint(1000, 1100)}"  # Small pool so history builds up
            avg = user_avg_amounts.get(user_id, 100)
            tx = generate_transaction(user_id=user_id, is_fraud=True)
            tx['amount'] = round(avg * random.uniform(3.5, 5.0), 2)
            producer.produce(
                'payment-transactions',
                key=tx['transaction_id'],
                value=json.dumps(tx),
                callback=delivery_report
            )
            producer.poll(0)
            count += 1

        else:
            # Normal or high_amount fraud
            tx = generate_transaction(is_fraud=is_fraud)
            # Track user average for unusual_amount detection
            uid = tx['user_id']
            if uid not in user_avg_amounts:
                user_avg_amounts[uid] = tx['amount']
            else:
                user_avg_amounts[uid] = (user_avg_amounts[uid] * 0.9) + (tx['amount'] * 0.1)

            producer.produce(
                'payment-transactions',
                key=tx['transaction_id'],
                value=json.dumps(tx),
                callback=delivery_report
            )
            producer.poll(0)
            count += 1

        if count % 100 == 0:
            print(f"Published {count} transactions")

        time.sleep(1/rate_per_sec)