# Model Evaluation Report

**Generated:** 2026-02-06 14:14:53

---

## Dataset Summary

- **Total Samples:** 250
- **Class 0 (No Landslide):** 156 (62.4%)
- **Class 1 (Landslide):** 94 (37.6%)
- **Imbalance Ratio:** 1.66

---

## Model Comparison Summary

| Model | Accuracy | Precision | Recall | F1 Score | AUC-ROC | CV F1 (5-fold) |
|-------|----------|-----------|--------|----------|---------|----------------|
| Logistic Regression | 0.6200 | 0.5930 | 0.6200 | 0.5851 | 0.4788 | 0.6845 ± 0.0675 |
| SVM (RBF) | 0.6000 | 0.5702 | 0.6000 | 0.5695 | 0.4669 | 0.7419 ± 0.1014 |
| XGBoost | 0.5800 | 0.5590 | 0.5800 | 0.5639 | 0.5518 | 0.6396 ± 0.0582 |
| RandomForest | 0.5600 | 0.5417 | 0.5600 | 0.5475 | 0.4975 | 0.6854 ± 0.0284 |
| Decision Tree | 0.5000 | 0.5050 | 0.5000 | 0.5023 | 0.4567 | 0.5838 ± 0.1063 |

---

## Detailed Results Per Model

### Logistic Regression

**Confusion Matrix:**
```
              Predicted 0    Predicted 1
Actual 0           26              5
Actual 1           14              5
```

**Per-Class Metrics:**

| Class | Precision | Recall | F1 Score |
|-------|-----------|--------|----------|
| 0 (No Landslide) | 0.6500 | 0.8387 | 0.7324 |
| 1 (Landslide) | 0.5000 | 0.2632 | 0.3448 |

---

### SVM (RBF)

**Confusion Matrix:**
```
              Predicted 0    Predicted 1
Actual 0           25              6
Actual 1           14              5
```

**Per-Class Metrics:**

| Class | Precision | Recall | F1 Score |
|-------|-----------|--------|----------|
| 0 (No Landslide) | 0.6410 | 0.8065 | 0.7143 |
| 1 (Landslide) | 0.4545 | 0.2632 | 0.3333 |

---

### XGBoost

**Confusion Matrix:**
```
              Predicted 0    Predicted 1
Actual 0           23              8
Actual 1           13              6
```

**Per-Class Metrics:**

| Class | Precision | Recall | F1 Score |
|-------|-----------|--------|----------|
| 0 (No Landslide) | 0.6389 | 0.7419 | 0.6866 |
| 1 (Landslide) | 0.4286 | 0.3158 | 0.3636 |

---

### RandomForest

**Confusion Matrix:**
```
              Predicted 0    Predicted 1
Actual 0           22              9
Actual 1           13              6
```

**Per-Class Metrics:**

| Class | Precision | Recall | F1 Score |
|-------|-----------|--------|----------|
| 0 (No Landslide) | 0.6286 | 0.7097 | 0.6667 |
| 1 (Landslide) | 0.4000 | 0.3158 | 0.3529 |

---

### Decision Tree

**Confusion Matrix:**
```
              Predicted 0    Predicted 1
Actual 0           18             13
Actual 1           12              7
```

**Per-Class Metrics:**

| Class | Precision | Recall | F1 Score |
|-------|-----------|--------|----------|
| 0 (No Landslide) | 0.6000 | 0.5806 | 0.5902 |
| 1 (Landslide) | 0.3500 | 0.3684 | 0.3590 |

---

## Feature Importance Analysis

### RandomForest

| Feature | Importance Score |
|---------|------------------|
| aspect751 | 0.1591 |
| Elevation1 | 0.1448 |
| Distance_to_River | 0.1361 |
| TWI_FINAL751 | 0.1231 |
| SPI751 | 0.1208 |
| Flow_Accumulation_clean751 | 0.0848 |
| slope751 | 0.0807 |
| Relative_Relief_751 | 0.0777 |
| Drainage_Density | 0.0730 |

### XGBoost

| Feature | Importance Score |
|---------|------------------|
| Distance_to_River | 0.1444 |
| TWI_FINAL751 | 0.1365 |
| aspect751 | 0.1329 |
| Elevation1 | 0.1292 |
| Flow_Accumulation_clean751 | 0.0972 |
| SPI751 | 0.0947 |
| slope751 | 0.0901 |
| Drainage_Density | 0.0900 |
| Relative_Relief_751 | 0.0850 |

### Decision Tree

| Feature | Importance Score |
|---------|------------------|
| Elevation1 | 0.2894 |
| aspect751 | 0.2168 |
| Distance_to_River | 0.1794 |
| Flow_Accumulation_clean751 | 0.1266 |
| slope751 | 0.0869 |
| Relative_Relief_751 | 0.0728 |
| SPI751 | 0.0280 |
| TWI_FINAL751 | 0.0000 |
| Drainage_Density | 0.0000 |

### Logistic Regression

| Feature | Importance Score |
|---------|------------------|
| TWI_FINAL751 | 0.1198 |
| Drainage_Density | 0.0795 |
| Flow_Accumulation_clean751 | 0.0065 |
| aspect751 | 0.0038 |
| slope751 | 0.0026 |
| Distance_to_River | 0.0019 |
| Elevation1 | 0.0009 |
| Relative_Relief_751 | 0.0008 |
| SPI751 | 0.0001 |

---

## Optimization Recommendations

### Current Best Model: **Logistic Regression**
- F1 Score: 0.5851
- Accuracy: 0.6200

### Recommendations:

1. **Address Class Imbalance:**
   - Current imbalance ratio is 1.66
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

⚠️ **NEEDS IMPROVEMENT:** Consider applying the optimization recommendations above.

The models show suboptimal performance for landslide prediction. The XGBoost and RandomForest models typically perform well on tabular geospatial data.
