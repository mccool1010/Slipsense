# Enhanced Model Performance Report

## Dataset
- **Total samples**: 800
- **Training samples**: 640
- **Test samples**: 160
- **Features**: 9

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
| **Accuracy** | 85.6% |
| **F1 Score** | 0.832 |
| **Precision** | 90.5% |
| **Recall** | 77.0% |
| **ROC-AUC** | 0.958 |

## Classification Report
```
              precision    recall  f1-score   support

No Landslide       0.82      0.93      0.87        86
   Landslide       0.90      0.77      0.83        74

    accuracy                           0.86       160
   macro avg       0.86      0.85      0.85       160
weighted avg       0.86      0.86      0.85       160

```

## Confusion Matrix
```
[[80  6]
 [17 57]]
```

## Target Achievement
- **Target F1**: 0.70+
- **Achieved F1**: 0.832
- **Status**: [OK] TARGET MET
