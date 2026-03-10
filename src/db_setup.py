from sqlalchemy import create_engine, Column, String, Numeric, TIMESTAMP, ARRAY, Integer, ForeignKey, Index
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection')

engine = create_engine(DATABASE_URL)
Base = declarative_base()

class Transaction(Base):
    __tablename__ = 'transactions'
    
    transaction_id = Column(String, primary_key=True)
    timestamp = Column(TIMESTAMP, index=True)
    user_id = Column(String, index=True)
    merchant_id = Column(String)
    amount = Column(Numeric(10, 2))
    card_last_4 = Column(String)
    merchant_category = Column(String)
    is_fraud = Column(String)  # Ground truth
    processed_at = Column(TIMESTAMP, default=datetime.now)
    ml_score = Column(Numeric(5, 4))  # ML fraud probability 0.0000-1.0000; NULL until Phase 8

class FraudAlert(Base):
    __tablename__ = 'fraud_alerts'
    
    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey('transactions.transaction_id'))
    fraud_score = Column(Numeric(3, 2))
    rules_triggered = Column(ARRAY(String))
    detected_at = Column(TIMESTAMP, index=True)

def init_db():
    Base.metadata.create_all(engine)
    print("Database tables created successfully")

if __name__ == "__main__":
    init_db()