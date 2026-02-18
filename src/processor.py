from confluent_kafka import Consumer
import json
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_setup import Transaction, FraudAlert
from data_quality import validate_transaction

DATABASE_URL = "postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection"
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

class FraudDetector:
    def __init__(self):
        self.user_transactions = defaultdict(list)
        
    def detect_fraud(self, tx):
        rules_triggered = []
        user_id = tx['user_id']
        amount = tx['amount']
        timestamp = datetime.fromisoformat(tx['timestamp'])
        
        if amount > 1000:
            rules_triggered.append("high_amount")
        
        recent_txs = [t for t in self.user_transactions[user_id] 
                      if timestamp - t['timestamp'] < timedelta(minutes=5)]
        if len(recent_txs) >= 3:
            rules_triggered.append("high_velocity")
        
        if len(self.user_transactions[user_id]) > 5:
            avg_amount = sum(t['amount'] for t in self.user_transactions[user_id]) / len(self.user_transactions[user_id])
            if amount > avg_amount * 3:
                rules_triggered.append("unusual_amount")
        
        self.user_transactions[user_id].append({'amount': amount, 'timestamp': timestamp})
        if len(self.user_transactions[user_id]) > 100:
            self.user_transactions[user_id] = self.user_transactions[user_id][-100:]
        
        return {
            "transaction_id": tx['transaction_id'],
            "is_fraud": len(rules_triggered) > 0,
            "fraud_score": len(rules_triggered) / 3.0,
            "rules_triggered": rules_triggered,
            "detected_at": datetime.now().isoformat(),
            "raw": tx
        }

def write_to_db(session, tx, result):
    # Write transaction
    transaction = Transaction(
        transaction_id=tx['transaction_id'],
        timestamp=datetime.fromisoformat(tx['timestamp']),
        user_id=tx['user_id'],
        merchant_id=tx['merchant_id'],
        amount=tx['amount'],
        card_last_4=tx['card_last_4'],
        merchant_category=tx['merchant_category'],
        is_fraud=str(tx.get('is_fraud', False))
    )
    session.merge(transaction)

    # Write fraud alert if flagged
    if result['is_fraud']:
        alert = FraudAlert(
            transaction_id=result['transaction_id'],
            fraud_score=result['fraud_score'],
            rules_triggered=result['rules_triggered'],
            detected_at=datetime.fromisoformat(result['detected_at'])
        )
        session.add(alert)

    session.commit()

def consume_and_process():
    consumer = Consumer({
        'bootstrap.servers': 'localhost:9092',
        'group.id': 'fraud-detector',
        'auto.offset.reset': 'earliest'
    })
    
    consumer.subscribe(['payment-transactions'])
    detector = FraudDetector()
    session = Session()
    
    processed = 0
    fraud_detected = 0
    invalid_count = 0
    
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue
            
            tx = json.loads(msg.value().decode('utf-8'))

            is_valid, errors = validate_transaction(tx)
            if not is_valid:
                invalid_count += 1
                print(f"INVALID TX {tx.get('transaction_id', 'unknown')}: {errors}")
                continue

            result = detector.detect_fraud(tx)
            write_to_db(session, tx, result)
            
            processed += 1
            if result['is_fraud']:
                fraud_detected += 1
                print(f"FRAUD DETECTED: {result['transaction_id']} | Rules: {result['rules_triggered']}")
            
            if processed % 100 == 0:
                print(f"Processed: {processed} | Fraud detected: {fraud_detected} | Invalid: {invalid_count} | DB writes: {processed}")
                
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        session.close()

if __name__ == "__main__":
    consume_and_process()