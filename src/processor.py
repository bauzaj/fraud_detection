from confluent_kafka import Consumer
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_setup import Transaction, FraudAlert
from data_quality import validate_transaction
import joblib
import pandas as pd
import numpy as np

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection')
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

class FraudDetector:
    MODEL_PATH = 'src/model/fraud_model.joblib'

    def __init__(self):
        self.user_transactions = defaultdict(list)
        self.model = joblib.load(self.MODEL_PATH)
        print(f"Model loaded from {self.MODEL_PATH}")

    def detect_fraud(self, tx):
        rules_triggered = []
        user_id = tx['user_id']
        amount = tx['amount']
        timestamp = datetime.fromisoformat(tx['timestamp'])
        
        if amount > 1000:
            rules_triggered.append("high_amount")
        
        recent_txs = [t for t in self.user_transactions[user_id] 
                      if timestamp - t['timestamp'] < timedelta(minutes=5)]
        if len(recent_txs) >= 8:
            rules_triggered.append("high_velocity")
        
        if len(self.user_transactions[user_id]) > 2:
            avg_amount = sum(t['amount'] for t in self.user_transactions[user_id]) / len(self.user_transactions[user_id])
            if amount > avg_amount * 3:
                rules_triggered.append("unusual_amount")
        
        # --- ML scoring (pre-append state — history does NOT include current tx) ---
        # recent_txs already computed above; reuse for tx_count_last_5min window parity
        history = self.user_transactions[user_id]
        tx_count_last_5min = float(len(recent_txs))
        if history:
            avg_amount_history = sum(t['amount'] for t in history) / len(history)
            amount_vs_user_avg_ratio = float(amount) / avg_amount_history
        else:
            amount_vs_user_avg_ratio = 1.0  # cold-start: no prior history; matches training fillna(1.0)
        row = {
            'amount': float(amount),
            'tx_count_last_5min': tx_count_last_5min,
            'amount_vs_user_avg_ratio': amount_vs_user_avg_ratio,
            'hour_of_day': float(timestamp.hour),
            'day_of_week': float(timestamp.weekday()),
            'merchant_category': tx['merchant_category'],
        }
        X = pd.DataFrame([row])
        raw_score = float(self.model.predict_proba(X)[0][1])
        ml_score = min(1.0, max(0.0, raw_score))  # clamp for NUMERIC(5,4) safety
        # -------------------------------------------------------------------------

        self.user_transactions[user_id].append({'amount': amount, 'timestamp': timestamp})
        if len(self.user_transactions[user_id]) > 100:
            self.user_transactions[user_id] = self.user_transactions[user_id][-100:]

        return {
            "transaction_id": tx['transaction_id'],
            "is_fraud": len(rules_triggered) > 0,
            "fraud_score": len(rules_triggered) / 3.0,
            "rules_triggered": rules_triggered,
            "detected_at": datetime.now().isoformat(),
            "ml_score": ml_score,
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
        is_fraud=str(tx.get('is_fraud', False)),
        ml_score=result['ml_score'],
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
    # Initialize DB tables if they don't exist
    from db_setup import init_db
    init_db()  
    
    consumer = Consumer({
    'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
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
            
            try:
                tx = json.loads(msg.value().decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Failed to decode message: {e}")
                continue

            is_valid, errors = validate_transaction(tx)
            if not is_valid:
                invalid_count += 1
                print(f"INVALID TX {tx.get('transaction_id', 'unknown')}: {errors}")
                continue

            result = detector.detect_fraud(tx)
            try:
                write_to_db(session, tx, result)
            except Exception as e:
                print(f"DB write failed for {tx.get('transaction_id', 'unknown')}: {e}")
                session.rollback()
            
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