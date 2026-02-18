import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

DATABASE_URL = "postgresql://fraud_user:fraud_pass@127.0.0.1:5433/fraud_detection"
engine = create_engine(DATABASE_URL)

st.title("Fraud Detection Dashboard")

# Metrics
col1, col2, col3 = st.columns(3)

total_tx = pd.read_sql("SELECT COUNT(*) as count FROM transactions", engine).iloc[0]['count']
total_fraud = pd.read_sql("SELECT COUNT(*) as count FROM fraud_alerts", engine).iloc[0]['count']
fraud_rate = round((total_fraud / total_tx) * 100, 2) if total_tx > 0 else 0

col1.metric("Total Transactions", f"{total_tx:,}")
col2.metric("Fraud Alerts", f"{total_fraud:,}")
col3.metric("Fraud Rate", f"{fraud_rate}%")

# Recent fraud alerts
st.subheader("Recent Fraud Alerts")
alerts = pd.read_sql("""
    SELECT fa.transaction_id, fa.fraud_score, fa.rules_triggered, fa.detected_at
    FROM fraud_alerts fa
    ORDER BY fa.detected_at DESC
    LIMIT 20
""", engine)
st.dataframe(alerts)

# Fraud over time
st.subheader("Fraud Detections Over Time")
fraud_over_time = pd.read_sql("""
    SELECT DATE_TRUNC('minute', detected_at) as minute, COUNT(*) as count
    FROM fraud_alerts
    GROUP BY minute
    ORDER BY minute
""", engine)
st.line_chart(fraud_over_time.set_index('minute'))
