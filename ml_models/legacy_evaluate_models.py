"""
ML Model Evaluation Script
Evaluates RandomForest and XGBoost models with comprehensive metrics
Also trains additional models (Decision Tree, SVM, Logistic Regression) for comparison
"""

import pandas as pd
import numpy as np
import joblib
import os
from datetime import datetime

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)
from sklearn.tree import DecisionTreeClassifier
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

# Paths
DATA_PATH = r"C:\coding\Slipsense\data\landslide - Sheet1 (1).csv"
RF_MODEL_PATH = r"C:\coding\Slipsense\ml_models\landslide_model.pkl"
XGB_MODEL_PATH = r"C:\coding\Slipsense\ml_models\landslide_model_xgb.pkl"
REPORT_PATH = r"C:\coding\Slipsense\ml_models\model_evaluation_report.md"


def load_data():
    """Load and prepare the dataset"""
    df = pd.read_csv(DATA_PATH)
    X = df.drop(columns=['Landslide', 'id'])
    y = df['Landslide']
    return X, y, df


def evaluate_model(model, X_train, X_test, y_train, y_test, model_name):
    """Evaluate a single model with comprehensive metrics"""
    
    # Predict
    y_pred = model.predict(X_test)
    
    # Probability predictions for AUC-ROC
    if hasattr(model, 'predict_proba'):
        y_proba = model.predict_proba(X_test)[:, 1]
        auc_roc = roc_auc_score(y_test, y_proba)
    else:
        auc_roc = None
    
    # Calculate metrics
    metrics = {
        'model_name': model_name,
        'accuracy': accuracy_score(y_test, y_pred),
        'precision_weighted': precision_score(y_test, y_pred, average='weighted', zero_division=0),
        'precision_class_0': precision_score(y_test, y_pred, pos_label=0, zero_division=0),
        'precision_class_1': precision_score(y_test, y_pred, pos_label=1, zero_division=0),
        'recall_weighted': recall_score(y_test, y_pred, average='weighted', zero_division=0),
        'recall_class_0': recall_score(y_test, y_pred, pos_label=0, zero_division=0),
        'recall_class_1': recall_score(y_test, y_pred, pos_label=1, zero_division=0),
        'f1_weighted': f1_score(y_test, y_pred, average='weighted', zero_division=0),
        'f1_class_0': f1_score(y_test, y_pred, pos_label=0, zero_division=0),
        'f1_class_1': f1_score(y_test, y_pred, pos_label=1, zero_division=0),
        'auc_roc': auc_roc,
        'confusion_matrix': confusion_matrix(y_test, y_pred),
        'classification_report': classification_report(y_test, y_pred, zero_division=0)
    }
    
    # Cross-validation score
    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring='f1_weighted')
    metrics['cv_f1_mean'] = cv_scores.mean()
    metrics['cv_f1_std'] = cv_scores.std()
    
    return metrics


def train_additional_models(X_train, y_train):
    """Train additional models for comparison"""
    models = {}
    
    # Decision Tree
    dt = DecisionTreeClassifier(random_state=42, max_depth=6)
    dt.fit(X_train, y_train)
    models['Decision Tree'] = dt
    
    # SVM with probability
    svm = SVC(kernel='rbf', probability=True, random_state=42)
    svm.fit(X_train, y_train)
    models['SVM (RBF)'] = svm
    
    # Logistic Regression
    lr = LogisticRegression(random_state=42, max_iter=1000)
    lr.fit(X_train, y_train)
    models['Logistic Regression'] = lr
    
    return models


def get_feature_importance(model, feature_names, model_name):
    """Extract feature importance if available"""
    if hasattr(model, 'feature_importances_'):
        importance = model.feature_importances_
        return dict(zip(feature_names, importance))
    elif hasattr(model, 'coef_'):
        importance = np.abs(model.coef_[0])
        return dict(zip(feature_names, importance))
    return None


def generate_report(all_metrics, feature_importances, class_distribution):
    """Generate a detailed markdown report"""
    
    report = f"""# Model Evaluation Report

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## Dataset Summary

- **Total Samples:** {class_distribution['total']}
- **Class 0 (No Landslide):** {class_distribution['class_0']} ({class_distribution['class_0_pct']:.1f}%)
- **Class 1 (Landslide):** {class_distribution['class_1']} ({class_distribution['class_1_pct']:.1f}%)
- **Imbalance Ratio:** {class_distribution['imbalance_ratio']:.2f}

---

## Model Comparison Summary

| Model | Accuracy | Precision | Recall | F1 Score | AUC-ROC | CV F1 (5-fold) |
|-------|----------|-----------|--------|----------|---------|----------------|
"""
    
    # Sort by F1 score
    sorted_metrics = sorted(all_metrics, key=lambda x: x['f1_weighted'], reverse=True)
    
    for m in sorted_metrics:
        auc = f"{m['auc_roc']:.4f}" if m['auc_roc'] else "N/A"
        report += f"| {m['model_name']} | {m['accuracy']:.4f} | {m['precision_weighted']:.4f} | {m['recall_weighted']:.4f} | {m['f1_weighted']:.4f} | {auc} | {m['cv_f1_mean']:.4f} ± {m['cv_f1_std']:.4f} |\n"
    
    report += """
---

## Detailed Results Per Model

"""
    
    for m in sorted_metrics:
        cm = m['confusion_matrix']
        report += f"""### {m['model_name']}

**Confusion Matrix:**
```
              Predicted 0    Predicted 1
Actual 0         {cm[0][0]:4d}           {cm[0][1]:4d}
Actual 1         {cm[1][0]:4d}           {cm[1][1]:4d}
```

**Per-Class Metrics:**

| Class | Precision | Recall | F1 Score |
|-------|-----------|--------|----------|
| 0 (No Landslide) | {m['precision_class_0']:.4f} | {m['recall_class_0']:.4f} | {m['f1_class_0']:.4f} |
| 1 (Landslide) | {m['precision_class_1']:.4f} | {m['recall_class_1']:.4f} | {m['f1_class_1']:.4f} |

---

"""
    
    # Feature Importance Section
    report += "## Feature Importance Analysis\n\n"
    
    for model_name, importance in feature_importances.items():
        if importance:
            sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
            report += f"### {model_name}\n\n"
            report += "| Feature | Importance Score |\n|---------|------------------|\n"
            for feat, score in sorted_features:
                report += f"| {feat} | {score:.4f} |\n"
            report += "\n"
    
    # Optimization Recommendations
    best_model = sorted_metrics[0]
    worst_model = sorted_metrics[-1]
    
    report += f"""---

## Optimization Recommendations

### Current Best Model: **{best_model['model_name']}**
- F1 Score: {best_model['f1_weighted']:.4f}
- Accuracy: {best_model['accuracy']:.4f}

### Recommendations:

1. **Address Class Imbalance:**
   - Current imbalance ratio is {class_distribution['imbalance_ratio']:.2f}
   - Consider using SMOTE (Synthetic Minority Over-sampling Technique)
   - Use class weights in model training

2. **Hyperparameter Tuning:**
   - Use GridSearchCV or RandomizedSearchCV for optimal parameters
   - For XGBoost: tune `n_estimators`, `max_depth`, `learning_rate`
   - For RandomForest: tune `n_estimators`, `max_depth`, `min_samples_split`

3. **Feature Engineering:**
   - Consider adding interaction features
   - Apply feature scaling (StandardScaler) for SVM and Logistic Regression
   - Remove low-importance features to reduce overfitting

4. **Model Ensemble:**
   - Combine top-performing models using VotingClassifier
   - Use stacking with meta-learner for improved predictions

5. **Data Augmentation:**
   - Collect more labeled data if possible
   - Use k-fold cross-validation for more robust evaluation

6. **Threshold Optimization:**
   - For landslide prediction, higher recall may be preferred (fewer false negatives)
   - Adjust classification threshold below 0.5 if minimizing missed landslides is priority

---

## Conclusion

{"✅ **GOOD PERFORMANCE:** " + best_model['model_name'] + " achieves strong metrics with F1 > 0.8" if best_model['f1_weighted'] > 0.8 else "⚠️ **NEEDS IMPROVEMENT:** Consider applying the optimization recommendations above."}

The models show {"excellent" if best_model['f1_weighted'] > 0.85 else "good" if best_model['f1_weighted'] > 0.75 else "moderate" if best_model['f1_weighted'] > 0.65 else "suboptimal"} performance for landslide prediction. The XGBoost and RandomForest models typically perform well on tabular geospatial data.
"""
    
    return report


def main():
    print("=" * 60)
    print("ML Model Evaluation - Slipsense Landslide Prediction")
    print("=" * 60)
    
    # Load data
    print("\n📊 Loading dataset...")
    X, y, df = load_data()
    print(f"   Shape: {X.shape}")
    print(f"   Features: {list(X.columns)}")
    
    # Class distribution
    class_0 = sum(y == 0)
    class_1 = sum(y == 1)
    class_distribution = {
        'total': len(y),
        'class_0': class_0,
        'class_1': class_1,
        'class_0_pct': class_0 / len(y) * 100,
        'class_1_pct': class_1 / len(y) * 100,
        'imbalance_ratio': class_0 / class_1 if class_1 > 0 else float('inf')
    }
    print(f"   Class 0 (No Landslide): {class_0} ({class_distribution['class_0_pct']:.1f}%)")
    print(f"   Class 1 (Landslide): {class_1} ({class_distribution['class_1_pct']:.1f}%)")
    
    # Calculate imbalance ratio for class weighting
    imbalance_ratio = class_0 / class_1 if class_1 > 0 else 1.0
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\n   Train: {len(X_train)}, Test: {len(X_test)}")
    
    all_metrics = []
    feature_importances = {}
    
    # NOTE: Saved models have feature mismatch with current data
    # Training fresh models for fair comparison on current dataset
    print("\n🔧 Training models on current dataset...")
    print("   (Note: Saved models were trained on different data with different features)")
    
    # RandomForest (matching saved model config)
    print("   ✓ Training RandomForest (n_estimators=400)...")
    rf_model = RandomForestClassifier(n_estimators=400, random_state=42, n_jobs=-1)
    rf_model.fit(X_train, y_train)
    metrics = evaluate_model(rf_model, X_train, X_test, y_train, y_test, "RandomForest")
    all_metrics.append(metrics)
    feature_importances["RandomForest"] = get_feature_importance(rf_model, X.columns, "RandomForest")
    
    # XGBoost (matching saved model config)
    print("   ✓ Training XGBoost (n_estimators=500)...")
    xgb_model = XGBClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.7,
        objective='binary:logistic',
        scale_pos_weight=imbalance_ratio,
        eval_metric='logloss',
        random_state=42
    )
    xgb_model.fit(X_train, y_train)
    metrics = evaluate_model(xgb_model, X_train, X_test, y_train, y_test, "XGBoost")
    all_metrics.append(metrics)
    feature_importances["XGBoost"] = get_feature_importance(xgb_model, X.columns, "XGBoost")
    
    # Train additional models for comparison
    print("\n🔧 Training additional comparison models...")
    additional_models = train_additional_models(X_train, y_train)
    
    for name, model in additional_models.items():
        print(f"   ✓ Trained {name}")
        metrics = evaluate_model(model, X_train, X_test, y_train, y_test, name)
        all_metrics.append(metrics)
        importance = get_feature_importance(model, X.columns, name)
        if importance:
            feature_importances[name] = importance
    
    # Print summary table
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    sorted_metrics = sorted(all_metrics, key=lambda x: x['f1_weighted'], reverse=True)
    
    print(f"\n{'Model':<25} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'AUC-ROC':>10}")
    print("-" * 75)
    
    for m in sorted_metrics:
        auc = f"{m['auc_roc']:.4f}" if m['auc_roc'] else "N/A"
        print(f"{m['model_name']:<25} {m['accuracy']:>10.4f} {m['precision_weighted']:>10.4f} {m['recall_weighted']:>10.4f} {m['f1_weighted']:>10.4f} {auc:>10}")
    
    print(f"\n🏆 Best Model: {sorted_metrics[0]['model_name']} (F1: {sorted_metrics[0]['f1_weighted']:.4f})")
    
    # Generate and save report
    print("\n📝 Generating detailed report...")
    report = generate_report(all_metrics, feature_importances, class_distribution)
    
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"   ✓ Report saved to: {REPORT_PATH}")
    print("\n" + "=" * 60)
    print("Evaluation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
