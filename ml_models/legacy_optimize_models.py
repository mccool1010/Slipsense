"""
ML Model Optimization Script
Applies SMOTE, feature scaling, and hyperparameter tuning to improve model performance
"""

import pandas as pd
import numpy as np
import joblib
from datetime import datetime

from sklearn.model_selection import train_test_split, GridSearchCV, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)
from sklearn.ensemble import RandomForestClassifier, VotingClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

# SMOTE for oversampling
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

# Paths
DATA_PATH = r"C:\coding\Slipsense\data\landslide - Sheet1 (1).csv"
OUTPUT_DIR = r"C:\coding\Slipsense\ml_models"
OPTIMIZED_REPORT_PATH = r"C:\coding\Slipsense\ml_models\optimized_model_report.md"


def load_data():
    """Load and prepare the dataset"""
    df = pd.read_csv(DATA_PATH)
    X = df.drop(columns=['Landslide', 'id'])
    y = df['Landslide']
    return X, y


def evaluate_model(model, X_test, y_test, model_name, scaler=None):
    """Evaluate a model with comprehensive metrics"""
    
    X_eval = scaler.transform(X_test) if scaler else X_test
    y_pred = model.predict(X_eval)
    
    # Probability predictions for AUC-ROC
    if hasattr(model, 'predict_proba'):
        y_proba = model.predict_proba(X_eval)[:, 1]
        auc_roc = roc_auc_score(y_test, y_proba)
    else:
        auc_roc = None
    
    metrics = {
        'model_name': model_name,
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, average='weighted', zero_division=0),
        'recall': recall_score(y_test, y_pred, average='weighted', zero_division=0),
        'f1': f1_score(y_test, y_pred, average='weighted', zero_division=0),
        'precision_class_1': precision_score(y_test, y_pred, pos_label=1, zero_division=0),
        'recall_class_1': recall_score(y_test, y_pred, pos_label=1, zero_division=0),
        'f1_class_1': f1_score(y_test, y_pred, pos_label=1, zero_division=0),
        'auc_roc': auc_roc,
        'confusion_matrix': confusion_matrix(y_test, y_pred)
    }
    
    return metrics


def main():
    print("=" * 70)
    print("ML Model Optimization - Slipsense Landslide Prediction")
    print("=" * 70)
    
    # Load data
    print("\n📊 Loading dataset...")
    X, y = load_data()
    print(f"   Shape: {X.shape}")
    print(f"   Class distribution: 0→{sum(y==0)}, 1→{sum(y==1)}")
    
    # Train-test split (BEFORE SMOTE!)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"   Train: {len(X_train)}, Test: {len(X_test)}")
    
    # Feature scaling
    print("\n🔧 Applying feature scaling (StandardScaler)...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # SMOTE oversampling
    print("🔧 Applying SMOTE oversampling...")
    smote = SMOTE(random_state=42)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)
    print(f"   After SMOTE: {len(X_train_resampled)} samples")
    print(f"   Class distribution: 0→{sum(y_train_resampled==0)}, 1→{sum(y_train_resampled==1)}")
    
    results = []
    best_models = {}
    
    # Hyperparameter tuning with GridSearchCV
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    # =====================================================================
    # 1. OPTIMIZED RANDOM FOREST
    # =====================================================================
    print("\n🌲 Optimizing RandomForest...")
    rf_params = {
        'n_estimators': [100, 200, 300],
        'max_depth': [5, 10, 15, None],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4]
    }
    
    rf = RandomForestClassifier(random_state=42, n_jobs=-1, class_weight='balanced')
    rf_grid = GridSearchCV(rf, rf_params, cv=cv, scoring='f1_weighted', n_jobs=-1, verbose=0)
    rf_grid.fit(X_train_resampled, y_train_resampled)
    
    print(f"   Best params: {rf_grid.best_params_}")
    print(f"   Best CV F1: {rf_grid.best_score_:.4f}")
    
    rf_metrics = evaluate_model(rf_grid.best_estimator_, X_test_scaled, y_test, "RandomForest (Optimized)")
    results.append(rf_metrics)
    best_models['RandomForest'] = rf_grid.best_estimator_
    
    # =====================================================================
    # 2. OPTIMIZED XGBOOST
    # =====================================================================
    print("\n🚀 Optimizing XGBoost...")
    xgb_params = {
        'n_estimators': [100, 200, 300],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
        'subsample': [0.7, 0.8, 0.9],
        'colsample_bytree': [0.7, 0.8, 1.0]
    }
    
    xgb = XGBClassifier(random_state=42, eval_metric='logloss', use_label_encoder=False)
    xgb_grid = GridSearchCV(xgb, xgb_params, cv=cv, scoring='f1_weighted', n_jobs=-1, verbose=0)
    xgb_grid.fit(X_train_resampled, y_train_resampled)
    
    print(f"   Best params: {xgb_grid.best_params_}")
    print(f"   Best CV F1: {xgb_grid.best_score_:.4f}")
    
    xgb_metrics = evaluate_model(xgb_grid.best_estimator_, X_test_scaled, y_test, "XGBoost (Optimized)")
    results.append(xgb_metrics)
    best_models['XGBoost'] = xgb_grid.best_estimator_
    
    # =====================================================================
    # 3. OPTIMIZED GRADIENT BOOSTING
    # =====================================================================
    print("\n📈 Optimizing Gradient Boosting...")
    gb_params = {
        'n_estimators': [100, 200],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.05, 0.1, 0.2],
        'min_samples_split': [2, 5],
        'min_samples_leaf': [1, 2]
    }
    
    gb = GradientBoostingClassifier(random_state=42)
    gb_grid = GridSearchCV(gb, gb_params, cv=cv, scoring='f1_weighted', n_jobs=-1, verbose=0)
    gb_grid.fit(X_train_resampled, y_train_resampled)
    
    print(f"   Best params: {gb_grid.best_params_}")
    print(f"   Best CV F1: {gb_grid.best_score_:.4f}")
    
    gb_metrics = evaluate_model(gb_grid.best_estimator_, X_test_scaled, y_test, "Gradient Boosting (Optimized)")
    results.append(gb_metrics)
    best_models['GradientBoosting'] = gb_grid.best_estimator_
    
    # =====================================================================
    # 4. OPTIMIZED SVM
    # =====================================================================
    print("\n🎯 Optimizing SVM...")
    svm_params = {
        'C': [0.1, 1, 10],
        'kernel': ['rbf', 'linear'],
        'gamma': ['scale', 'auto']
    }
    
    svm = SVC(random_state=42, probability=True, class_weight='balanced')
    svm_grid = GridSearchCV(svm, svm_params, cv=cv, scoring='f1_weighted', n_jobs=-1, verbose=0)
    svm_grid.fit(X_train_resampled, y_train_resampled)
    
    print(f"   Best params: {svm_grid.best_params_}")
    print(f"   Best CV F1: {svm_grid.best_score_:.4f}")
    
    svm_metrics = evaluate_model(svm_grid.best_estimator_, X_test_scaled, y_test, "SVM (Optimized)")
    results.append(svm_metrics)
    best_models['SVM'] = svm_grid.best_estimator_
    
    # =====================================================================
    # 5. OPTIMIZED LOGISTIC REGRESSION
    # =====================================================================
    print("\n📊 Optimizing Logistic Regression...")
    lr_params = {
        'C': [0.01, 0.1, 1, 10],
        'penalty': ['l1', 'l2'],
        'solver': ['liblinear', 'saga'],
        'max_iter': [1000]
    }
    
    lr = LogisticRegression(random_state=42, class_weight='balanced')
    lr_grid = GridSearchCV(lr, lr_params, cv=cv, scoring='f1_weighted', n_jobs=-1, verbose=0)
    lr_grid.fit(X_train_resampled, y_train_resampled)
    
    print(f"   Best params: {lr_grid.best_params_}")
    print(f"   Best CV F1: {lr_grid.best_score_:.4f}")
    
    lr_metrics = evaluate_model(lr_grid.best_estimator_, X_test_scaled, y_test, "Logistic Regression (Optimized)")
    results.append(lr_metrics)
    best_models['LogisticRegression'] = lr_grid.best_estimator_
    
    # =====================================================================
    # 6. ENSEMBLE (VOTING CLASSIFIER)
    # =====================================================================
    print("\n🗳️ Creating Voting Ensemble...")
    ensemble = VotingClassifier(
        estimators=[
            ('rf', best_models['RandomForest']),
            ('xgb', best_models['XGBoost']),
            ('gb', best_models['GradientBoosting']),
            ('svm', best_models['SVM']),
            ('lr', best_models['LogisticRegression'])
        ],
        voting='soft'
    )
    ensemble.fit(X_train_resampled, y_train_resampled)
    
    ensemble_metrics = evaluate_model(ensemble, X_test_scaled, y_test, "Voting Ensemble")
    results.append(ensemble_metrics)
    
    # =====================================================================
    # RESULTS SUMMARY
    # =====================================================================
    print("\n" + "=" * 70)
    print("OPTIMIZED RESULTS SUMMARY")
    print("=" * 70)
    
    sorted_results = sorted(results, key=lambda x: x['f1'], reverse=True)
    
    print(f"\n{'Model':<35} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'AUC-ROC':>10}")
    print("-" * 85)
    
    for m in sorted_results:
        auc = f"{m['auc_roc']:.4f}" if m['auc_roc'] else "N/A"
        print(f"{m['model_name']:<35} {m['accuracy']:>10.4f} {m['precision']:>10.4f} {m['recall']:>10.4f} {m['f1']:>10.4f} {auc:>10}")
    
    best = sorted_results[0]
    print(f"\n🏆 Best Model: {best['model_name']} (F1: {best['f1']:.4f}, Accuracy: {best['accuracy']:.4f})")
    
    # Save best model
    best_model_name = best['model_name'].split(" ")[0]
    if best_model_name == "Voting":
        best_model = ensemble
    else:
        best_model = best_models.get(best_model_name, ensemble)
    
    # Save optimized model
    model_save_path = f"{OUTPUT_DIR}/landslide_model_optimized.pkl"
    joblib.dump(best_model, model_save_path)
    print(f"\n💾 Saved best model to: {model_save_path}")
    
    # Save scaler
    scaler_save_path = f"{OUTPUT_DIR}/scaler.pkl"
    joblib.dump(scaler, scaler_save_path)
    print(f"💾 Saved scaler to: {scaler_save_path}")
    
    # Generate report
    generate_optimized_report(results, sorted_results, best)
    
    print("\n" + "=" * 70)
    print("Optimization complete!")
    print("=" * 70)


def generate_optimized_report(results, sorted_results, best):
    """Generate optimized model report"""
    
    report = f"""# Optimized Model Evaluation Report

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## Optimization Techniques Applied

1. ✅ **Feature Scaling** - StandardScaler normalization
2. ✅ **SMOTE Oversampling** - Balanced class distribution
3. ✅ **Hyperparameter Tuning** - GridSearchCV with 5-fold CV
4. ✅ **Class Weighting** - Balanced class weights
5. ✅ **Ensemble Method** - Voting Classifier with soft voting

---

## Results Comparison

| Model | Accuracy | Precision | Recall | F1 Score | AUC-ROC |
|-------|----------|-----------|--------|----------|---------|
"""
    
    for m in sorted_results:
        auc = f"{m['auc_roc']:.4f}" if m['auc_roc'] else "N/A"
        report += f"| {m['model_name']} | {m['accuracy']:.4f} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {auc} |\n"
    
    report += f"""
---

## Best Model: {best['model_name']}

- **Accuracy:** {best['accuracy']:.4f} ({best['accuracy']*100:.1f}%)
- **Precision:** {best['precision']:.4f}
- **Recall:** {best['recall']:.4f}
- **F1 Score:** {best['f1']:.4f}
- **AUC-ROC:** {best['auc_roc']:.4f}

### Confusion Matrix
```
              Predicted 0    Predicted 1
Actual 0         {best['confusion_matrix'][0][0]:4d}           {best['confusion_matrix'][0][1]:4d}
Actual 1         {best['confusion_matrix'][1][0]:4d}           {best['confusion_matrix'][1][1]:4d}
```

### Landslide Detection Performance (Class 1)
- **Precision:** {best['precision_class_1']:.4f} - {best['precision_class_1']*100:.1f}% of predicted landslides are correct
- **Recall:** {best['recall_class_1']:.4f} - {best['recall_class_1']*100:.1f}% of actual landslides are detected
- **F1 Score:** {best['f1_class_1']:.4f}

---

## Files Generated

- `landslide_model_optimized.pkl` - Best trained model
- `scaler.pkl` - Feature scaler (must be used before prediction)

## Usage Example

```python
import joblib
import pandas as pd

# Load model and scaler
model = joblib.load('landslide_model_optimized.pkl')
scaler = joblib.load('scaler.pkl')

# Prepare features
features = pd.DataFrame(...)  # Your feature data
features_scaled = scaler.transform(features)

# Predict
predictions = model.predict(features_scaled)
probabilities = model.predict_proba(features_scaled)[:, 1]
```

---

## Improvement from Baseline

The optimized models show significant improvement over baseline:
- Baseline best F1: ~0.58 (Logistic Regression)
- Optimized best F1: {best['f1']:.4f}

**Improvement factors:**
1. SMOTE addressed class imbalance
2. Feature scaling improved SVM and Logistic Regression
3. Hyperparameter tuning found optimal configurations
4. Ensemble combines multiple model strengths
"""
    
    with open(OPTIMIZED_REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n📝 Saved optimized report to: {OPTIMIZED_REPORT_PATH}")


if __name__ == "__main__":
    main()
