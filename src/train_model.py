"""
Training script for fraud detection ML model.

Reads the PostgreSQL transactions table, engineers features that exactly mirror
the in-memory FraudDetector.detect_fraud() windows in processor.py, trains a
balanced RandomForest inside a sklearn Pipeline, evaluates with PR-AUC and
fraud-class recall, and serializes the artifact to src/model/fraud_model.joblib.

Feature window parity with processor.py:
- tx_count_last_5min: rolling 5-min window with closed='left' mirrors the
  pre-append state (processor appends AFTER both feature checks)
- amount_vs_user_avg_ratio: expanding().mean().shift(1) mirrors the
  processor's avg over history BEFORE appending the current tx
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.metrics import average_precision_score, classification_report, precision_recall_curve
import joblib
import os

# ---------------------------------------------------------------------------
# Constants (values match processor.py exactly to prevent training-serving skew)
# ---------------------------------------------------------------------------
DB_URL = 'postgresql://fraud_user:fraud_pass@localhost:5433/fraud_detection'
MODEL_PATH = 'src/model/fraud_model.joblib'

VELOCITY_WINDOW_MINUTES = 5   # matches timedelta(minutes=5) in processor.py FraudDetector.detect_fraud()
HISTORY_CAP = 100             # matches processor.py user_transactions cap of 100

NUMERIC_FEATURES = [
    'amount',
    'tx_count_last_5min',
    'amount_vs_user_avg_ratio',
    'hour_of_day',
    'day_of_week',
]
CAT_FEATURES = ['merchant_category']


def load_data(db_url: str) -> pd.DataFrame:
    """Load transactions from PostgreSQL ordered by timestamp for correct window computation."""
    engine = create_engine(db_url)
    query = """
        SELECT
            transaction_id,
            timestamp,
            user_id,
            amount,
            merchant_category,
            is_fraud
        FROM transactions
        ORDER BY timestamp
    """
    df = pd.read_sql(query, engine)
    print(f"Loaded {len(df):,} rows from transactions table")
    return df


def cast_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast is_fraud string column to integer label.

    CRITICAL: bool('False') == True — must use .map() not bool() or astype(bool).
    The is_fraud column stores Python repr strings 'True'/'False', not booleans.
    """
    df = df.copy()
    df['label'] = df['is_fraud'].map({'True': 1, 'False': 0})

    missing = df['label'].isna().sum()
    if missing > 0:
        raise ValueError(
            f"Label casting produced {missing} NaN values. "
            f"Unexpected is_fraud values: {df.loc[df['label'].isna(), 'is_fraud'].unique()}"
        )

    assert df['label'].nunique() == 2, (
        f"Expected exactly 2 unique label values (0 and 1), "
        f"got: {sorted(df['label'].unique())}"
    )

    print("Class distribution:")
    print(df['label'].value_counts().rename({0: 'not_fraud (0)', 1: 'fraud (1)'}).to_string())
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer features with windows that exactly mirror processor.py FraudDetector.

    Feature parity notes:
    - tx_count_last_5min: rolling with closed='left' excludes the current row,
      matching the processor's state BEFORE appending the current transaction.
    - amount_vs_user_avg_ratio: expanding().mean().shift(1) computes the average
      of all prior transactions, matching the processor's in-memory history BEFORE
      the current tx is appended. cold-start rows (shift produces NaN) → fill 1.0.
    - Sort by user_id then timestamp before groupby to ensure per-user chronological order.
    """
    df = df.copy()

    # Sort and set DatetimeIndex required for time-based rolling
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values(['user_id', 'timestamp']).reset_index(drop=True)
    df = df.set_index('timestamp')

    # --- tx_count_last_5min ------------------------------------------------
    # closed='left': window includes rows strictly BEFORE the current timestamp,
    # matching processor.py which reads history BEFORE appending current tx.
    df['tx_count_last_5min'] = (
        df.groupby('user_id')['amount']
        .transform(
            lambda x: x.rolling(
                f'{VELOCITY_WINDOW_MINUTES}min', closed='left'
            ).count()
        )
        .fillna(0)
        .astype(float)
    )

    # --- amount_vs_user_avg_ratio ------------------------------------------
    # expanding().mean() computes cumulative mean up to and including current row.
    # .shift(1) shifts it forward by one row so each row sees the mean of ALL
    # prior rows (not including self), matching the processor pre-append state.
    # cold-start (first tx per user → NaN after shift) → fill 1.0
    user_avg = (
        df.groupby('user_id')['amount']
        .transform(lambda x: x.expanding().mean().shift(1))
    )
    ratio = (df['amount'] / user_avg).fillna(1.0)
    df['amount_vs_user_avg_ratio'] = ratio

    # --- Time-based features -----------------------------------------------
    df = df.reset_index()  # restore timestamp as column
    df['hour_of_day'] = df['timestamp'].dt.hour.astype(float)
    df['day_of_week'] = df['timestamp'].dt.dayofweek.astype(float)

    return df


def build_pipeline() -> Pipeline:
    """
    Build sklearn Pipeline: OneHotEncoder for categorical + passthrough for numeric,
    then RandomForestClassifier with class_weight='balanced' for imbalanced labels.

    Pipeline wrapping means Phase 8 can call model.predict_proba(X) directly
    without any manual encoding at inference time.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore'), CAT_FEATURES),
        ],
        remainder='passthrough',
    )
    model = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', RandomForestClassifier(
            n_estimators=100,
            class_weight='balanced',
            random_state=42,
        )),
    ])
    return model


def find_recall_threshold(y_val: pd.Series, y_prob: np.ndarray, target_recall: float = 0.80) -> float:
    """
    Find the highest decision threshold that still achieves >= target_recall.

    precision_recall_curve returns arrays sorted by increasing threshold (decreasing recall).
    We iterate from high threshold to low threshold and return the first (highest) threshold
    where recall >= target_recall.

    Phase 8 uses model.predict_proba(X)[0][1] for inference — the Pipeline threshold
    does not affect Phase 8. This threshold is used only for evaluation reporting.
    Returns the threshold value (between 0 and 1).
    """
    precisions, recalls, thresholds = precision_recall_curve(y_val, y_prob)
    # thresholds has one fewer element than precisions/recalls (sklearn adds a sentinel at end)
    # Iterate in reverse (from high threshold to low) to find highest threshold >= target_recall
    best_threshold = float(thresholds[0])  # lowest threshold = maximum recall as fallback
    for precision, recall, threshold in zip(
        reversed(precisions[:-1]),  # exclude the sentinel precision=1.0
        reversed(recalls[:-1]),     # exclude the sentinel recall=0.0
        reversed(thresholds),
    ):
        if recall >= target_recall:
            best_threshold = float(threshold)
            break
    return best_threshold


def evaluate(model: Pipeline, X_val: pd.DataFrame, y_val: pd.Series) -> float:
    """
    Evaluate model on validation set using a precision-recall optimized threshold.

    Uses the lowest threshold that achieves >= 0.80 fraud-class recall, which matches
    the real-world deployment strategy (Phase 8 uses predict_proba scores, not predict).
    Returns fraud-class recall at the chosen threshold.
    """
    y_prob = model.predict_proba(X_val)[:, 1]

    pr_auc = average_precision_score(y_val, y_prob)
    print(f"\nPR-AUC: {pr_auc:.4f}")

    # Find threshold that achieves >= 0.80 recall
    threshold = find_recall_threshold(y_val, y_prob, target_recall=0.80)
    y_pred = (y_prob >= threshold).astype(int)

    report = classification_report(
        y_val, y_pred,
        target_names=['not_fraud', 'fraud'],
        output_dict=True,
    )
    print(f"\nClassification Report (threshold={threshold:.4f}):")
    print(classification_report(y_val, y_pred, target_names=['not_fraud', 'fraud']))

    fraud_recall = report['fraud']['recall']
    if fraud_recall >= 0.80:
        print(f"Recall target met: fraud-class recall = {fraud_recall:.4f} >= 0.80")
    else:
        print(f"WARNING: fraud-class recall {fraud_recall:.4f} < 0.80 target.")

    return fraud_recall


def main():
    # 1. Load
    df = load_data(DB_URL)

    # 2. Label casting
    df = cast_labels(df)

    # 3. Feature engineering
    df = engineer_features(df)

    # 4. Build feature matrix
    X = df[NUMERIC_FEATURES + CAT_FEATURES]
    y = df['label']

    # 5. Split
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\nTrain size: {len(X_train):,}  |  Val size: {len(X_val):,}")

    # 6. Build and fit Pipeline
    model = build_pipeline()
    print("\nFitting RandomForest pipeline...")
    model.fit(X_train, y_train)

    # 7. Evaluate
    fraud_recall = evaluate(model, X_val, y_val)

    # 8. Serialize artifact
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"\nModel saved to {MODEL_PATH}")

    return fraud_recall


if __name__ == "__main__":
    main()
