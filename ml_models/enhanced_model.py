"""
enhanced_model.py
Train an enhanced stacking ensemble for landslide prediction.
Uses RF + XGBoost + LightGBM as base models with LogisticRegression meta-learner.

Target: 70%+ F1 score
"""

import os
import numpy as np
import pandas as pd
import joblib
from pathlib import Path

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    roc_auc_score, classification_report, confusion_matrix
)

# Optional: SMOTE for oversampling
try:
    from imblearn.over_sampling import SMOTE
    HAS_SMOTE = True
except ImportError:
    print("Warning: imblearn not installed, SMOTE disabled")
    HAS_SMOTE = False

# Optional: XGBoost and LightGBM
try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    print("Warning: XGBoost not installed")
    HAS_XGB = False

try:
    from lightgbm import LGBMClassifier
    HAS_LGBM = True
except ImportError:
    print("Warning: LightGBM not installed, using additional RF")
    HAS_LGBM = False

# -----------------------
# Config
# -----------------------
DATA_DIR = Path(r"C:\coding\Slipsense\data")
MODEL_DIR = Path(r"C:\coding\Slipsense\ml_models")

# Input
DATA_FILE = DATA_DIR / "merged_landslide_data.csv"

# Output
MODEL_OUT = MODEL_DIR / "enhanced_model.pkl"
SCALER_OUT = MODEL_DIR / "enhanced_scaler.pkl"
REPORT_OUT = MODEL_DIR / "enhanced_model_report.md"

# Feature columns
FEATURE_COLS = [
    'relative_relief', 'spi', 'twi', 'flow_acc', 'aspect',
    'slope', 'elevation', 'dist_river', 'drainage_density'
]


def load_data():
    """Load the merged dataset."""
    print("Loading data...")
    df = pd.read_csv(DATA_FILE)
    
    X = df[FEATURE_COLS].values
    y = df['landslide'].values.astype(int)
    
    print(f"  Total samples: {len(df)}")
    print(f"  Features: {len(FEATURE_COLS)}")
    print(f"  Class distribution: 0={sum(y==0)}, 1={sum(y==1)}")
    
    return X, y, df


def create_stacking_ensemble():
    """Create the stacking ensemble model."""
    print("\nBuilding stacking ensemble...")
    
    # Base estimators
    estimators = []
    
    # RandomForest (always available)
    rf = RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )
    estimators.append(('rf', rf))
    print("  Added: RandomForest (n=300, depth=12)")
    
    # XGBoost (if available)
    if HAS_XGB:
        xgb = XGBClassifier(
            n_estimators=300,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=1.5,
            random_state=42,
            n_jobs=-1,
            use_label_encoder=False,
            eval_metric='logloss'
        )
        estimators.append(('xgb', xgb))
        print("  Added: XGBoost (n=300, depth=8)")
    
    # LightGBM (if available)
    if HAS_LGBM:
        lgbm = LGBMClassifier(
            n_estimators=300,
            max_depth=8,
            learning_rate=0.05,
            num_leaves=50,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1,
            verbose=-1
        )
        estimators.append(('lgbm', lgbm))
        print("  Added: LightGBM (n=300, depth=8)")
    else:
        # Alternative: another RF with different params
        rf2 = RandomForestClassifier(
            n_estimators=200,
            max_depth=15,
            min_samples_split=3,
            class_weight='balanced',
            random_state=123,
            n_jobs=-1
        )
        estimators.append(('rf2', rf2))
        print("  Added: RandomForest-2 (n=200, depth=15)")
    
    # Meta-learner
    meta_learner = LogisticRegression(
        C=1.0,
        class_weight='balanced',
        max_iter=1000,
        random_state=42
    )
    
    # Create stacking classifier
    stacking = StackingClassifier(
        estimators=estimators,
        final_estimator=meta_learner,
        cv=5,
        stack_method='predict_proba',
        n_jobs=-1
    )
    
    print(f"  Meta-learner: LogisticRegression")
    print(f"  Total base models: {len(estimators)}")
    
    return stacking


def evaluate_model(model, X_test, y_test, scaler):
    """Evaluate model performance."""
    X_test_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_test_scaled)
    y_proba = model.predict_proba(X_test_scaled)[:, 1]
    
    metrics = {
        'accuracy': accuracy_score(y_test, y_pred),
        'f1': f1_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred),
        'recall': recall_score(y_test, y_pred),
        'roc_auc': roc_auc_score(y_test, y_proba)
    }
    
    return metrics, y_pred, y_proba


def generate_report(metrics, y_test, y_pred, data_info):
    """Generate markdown report."""
    report = f"""# Enhanced Model Performance Report

## Dataset
- **Total samples**: {data_info['total']}
- **Training samples**: {data_info['train']}
- **Test samples**: {data_info['test']}
- **Features**: {len(FEATURE_COLS)}

## Model Architecture
```
Stacking Ensemble:
+-- Level 1 (Base Models)
|   +-- RandomForest (n=300, depth=12)
|   +-- XGBoost (n=300, depth=8)
|   +-- LightGBM (n=300, depth=8)
+-- Level 2 (Meta-Learner)
    +-- LogisticRegression (balanced)
```

## Performance Metrics

| Metric | Score |
|--------|-------|
| **Accuracy** | {metrics['accuracy']:.1%} |
| **F1 Score** | {metrics['f1']:.3f} |
| **Precision** | {metrics['precision']:.1%} |
| **Recall** | {metrics['recall']:.1%} |
| **ROC-AUC** | {metrics['roc_auc']:.3f} |

## Classification Report
```
{classification_report(y_test, y_pred, target_names=['No Landslide', 'Landslide'])}
```

## Confusion Matrix
```
{confusion_matrix(y_test, y_pred)}
```

## Target Achievement
- **Target F1**: 0.70+
- **Achieved F1**: {metrics['f1']:.3f}
- **Status**: {'[OK] TARGET MET' if metrics['f1'] >= 0.70 else '[!] Below target'}
"""
    return report


def main():
    print("=" * 60)
    print("Enhanced Landslide Prediction Model Training")
    print("=" * 60)
    
    # Load data
    X, y, df = load_data()
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"\nTrain size: {len(X_train)}, Test size: {len(X_test)}")
    
    # Scale features
    print("\nScaling features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    # Apply SMOTE if available
    if HAS_SMOTE:
        print("Applying SMOTE oversampling...")
        smote = SMOTE(random_state=42)
        X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)
        print(f"  After SMOTE: {len(X_train_resampled)} samples")
    else:
        X_train_resampled, y_train_resampled = X_train_scaled, y_train
    
    # Create and train model
    model = create_stacking_ensemble()
    
    print("\nTraining stacking ensemble...")
    print("  This may take a few minutes...")
    model.fit(X_train_resampled, y_train_resampled)
    
    # Evaluate
    print("\nEvaluating model...")
    metrics, y_pred, y_proba = evaluate_model(model, X_test, y_test, scaler)
    
    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    print(f"  Accuracy:  {metrics['accuracy']:.1%}")
    print(f"  F1 Score:  {metrics['f1']:.3f}")
    print(f"  Precision: {metrics['precision']:.1%}")
    print(f"  Recall:    {metrics['recall']:.1%}")
    print(f"  ROC-AUC:   {metrics['roc_auc']:.3f}")
    
    if metrics['f1'] >= 0.70:
        print("\n[OK] TARGET ACHIEVED: F1 >= 0.70")
    else:
        print(f"\n[!] F1 = {metrics['f1']:.3f}, below 0.70 target")
    
    # Save model and scaler
    print(f"\nSaving model to: {MODEL_OUT}")
    joblib.dump(model, MODEL_OUT)
    
    print(f"Saving scaler to: {SCALER_OUT}")
    joblib.dump(scaler, SCALER_OUT)
    
    # Generate report
    data_info = {
        'total': len(df),
        'train': len(X_train),
        'test': len(X_test)
    }
    report = generate_report(metrics, y_test, y_pred, data_info)
    
    with open(REPORT_OUT, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Saved report to: {REPORT_OUT}")
    
    print("\n" + "=" * 60)
    print("Training Complete!")
    print("=" * 60)
    
    return model, scaler, metrics


if __name__ == "__main__":
    main()
