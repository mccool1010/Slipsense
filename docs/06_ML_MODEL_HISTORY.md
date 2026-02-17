# SlipSense ML Development Journey

**Document Version:** 2.0
**Last Updated:** 2026-02-06
**Project:** SlipSense Landslide Prediction System

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Development Timeline](#development-timeline)
3. [Model Comparison](#model-comparison)
4. [Phase 1: Baseline Models](#phase-1-baseline-models)
5. [Phase 2: Optimized Models](#phase-2-optimized-models)
6. [Phase 3: Enhanced Stacking Ensemble](#phase-3-enhanced-stacking-ensemble)
7. [U-Net Deep Learning Refinement](#u-net-deep-learning-refinement)
8. [How Each Model Works](#how-each-model-works)
9. [How the Stacking Ensemble Works](#how-the-stacking-ensemble-works)
10. [File Inventory](#file-inventory)
11. [Pipeline Architecture](#pipeline-architecture)
12. [Code Changes Summary](#code-changes-summary)

---

## Executive Summary

The SlipSense ML pipeline underwent significant optimization, achieving a **+42% improvement in F1 score** from baseline (0.585) to the final enhanced model (0.832).

| Metric | Baseline | Optimized | Enhanced (Final) | Improvement |
|--------|----------|-----------|------------------|-------------|
| **F1 Score** | 0.585 | 0.639 | **0.832** | +42.2% |
| **Accuracy** | 62.0% | 66.0% | **85.6%** | +38.1% |
| **Precision** | 59.3% | 64.6% | **90.5%** | +52.6% |
| **Recall** | 62.0% | 66.0% | **77.0%** | +24.2% |
| **ROC-AUC** | 0.479 | 0.525 | **0.958** | +100.0% |

### Key Technologies Used
- **RandomForest** - Ensemble of decision trees
- **XGBoost** - Extreme Gradient Boosting
- **LightGBM** - Light Gradient Boosting Machine (fallback to RF if unavailable)
- **Logistic Regression** - Meta-learner for stacking
- **SMOTE** - Synthetic Minority Over-sampling
- **U-Net** - Deep learning spatial refinement

---

## Development Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: Baseline Evaluation (Feb 2026)                               │
│  ├─ Dataset: 250 samples, 9 features                                   │
│  ├─ Models tested: LogReg, SVM, XGBoost, RandomForest, DecisionTree    │
│  ├─ Best F1: 0.585 (Logistic Regression)                               │
│  └─ Conclusion: Models underperforming, need optimization              │
├─────────────────────────────────────────────────────────────────────────┤
│  PHASE 2: Optimization Attempts (Feb 2026)                             │
│  ├─ Applied: SMOTE oversampling, StandardScaler, GridSearchCV          │
│  ├─ Added: Voting Ensemble, Gradient Boosting                          │
│  ├─ Best F1: 0.639 (RandomForest Optimized)                            │
│  └─ Conclusion: Marginal improvement, need more data                   │
├─────────────────────────────────────────────────────────────────────────┤
│  PHASE 3: Enhanced Ensemble (Feb 2026)                                 │
│  ├─ Data Expansion: 250 → 800 samples (3.2x increase)                  │
│  ├─ Architecture: Stacking Ensemble                                    │
│  │   ├─ Base: RandomForest + XGBoost + LightGBM/RF                     │
│  │   └─ Meta: Logistic Regression                                      │
│  ├─ Best F1: 0.832 (TARGET ACHIEVED!)                                  │
│  └─ Conclusion: Success! 42% improvement over baseline                 │
├─────────────────────────────────────────────────────────────────────────┤
│  PHASE 4: Deep Learning Refinement (Feb 2026)                          │
│  ├─ Model: U-Net convolutional neural network                          │
│  ├─ Purpose: Spatial refinement of susceptibility maps                 │
│  └─ Output: Enhanced susceptibility_dl.tif                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Model Comparison

### Full Performance Comparison Table

| Model Version | Phase | Dataset | F1 Score | Accuracy | Precision | Recall | ROC-AUC |
|---------------|-------|---------|----------|----------|-----------|--------|---------|
| Logistic Regression | Baseline | 250 | 0.585 | 62.0% | 59.3% | 62.0% | 0.479 |
| XGBoost | Baseline | 250 | 0.564 | 58.0% | 55.9% | 58.0% | 0.552 |
| RandomForest | Baseline | 250 | 0.548 | 56.0% | 54.2% | 56.0% | 0.498 |
| RandomForest | Optimized | 250 | 0.639 | 66.0% | 64.6% | 66.0% | 0.525 |
| XGBoost | Optimized | 250 | 0.531 | 54.0% | 52.5% | 54.0% | 0.589 |
| **Stacking Ensemble** | **Enhanced** | **800** | **0.832** | **85.6%** | **90.5%** | **77.0%** | **0.958** |

### Visual F1 Score Comparison

```
F1 Score Progression:

Stacking Ensemble (RF+XGB+LGBM) ████████████████████████████████░ 0.832  ★ FINAL
RandomForest (Optimized)        █████████████████████░░░░░░░░░░░░ 0.639
Logistic Regression (Baseline)  ██████████████████░░░░░░░░░░░░░░░ 0.585
XGBoost (Baseline)              █████████████████░░░░░░░░░░░░░░░░ 0.564
RandomForest (Baseline)         ████████████████░░░░░░░░░░░░░░░░░ 0.548
XGBoost (Optimized)             ████████████████░░░░░░░░░░░░░░░░░ 0.531
                                |-------|-------|-------|-------|
                                0.0     0.25    0.50    0.75    1.0
```

---

## Phase 1: Baseline Models

### Dataset Characteristics
- **Total Samples:** 250
- **Class Distribution:** 156 No Landslide (62.4%), 94 Landslide (37.6%)
- **Imbalance Ratio:** 1.66
- **Features:** 9 terrain variables

### Baseline Model Results

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | CV F1 (5-fold) |
|-------|----------|-----------|--------|-----|---------|----------------|
| Logistic Regression | 62.0% | 59.3% | 62.0% | 0.585 | 0.479 | 0.685 ± 0.068 |
| SVM (RBF Kernel) | 60.0% | 57.0% | 60.0% | 0.570 | 0.467 | 0.742 ± 0.101 |
| XGBoost | 58.0% | 55.9% | 58.0% | 0.564 | 0.552 | 0.640 ± 0.058 |
| RandomForest | 56.0% | 54.2% | 56.0% | 0.548 | 0.498 | 0.685 ± 0.028 |
| Decision Tree | 50.0% | 50.5% | 50.0% | 0.502 | 0.457 | 0.584 ± 0.106 |

### Feature Importance (RandomForest Baseline)

| Rank | Feature | Importance | Description |
|------|---------|------------|-------------|
| 1 | Aspect | 0.159 | Compass direction of slope face |
| 2 | Elevation | 0.145 | Height above sea level |
| 3 | Distance to River | 0.136 | Proximity to water bodies |
| 4 | TWI | 0.123 | Topographic Wetness Index |
| 5 | SPI | 0.121 | Stream Power Index |
| 6 | Flow Accumulation | 0.085 | Water flow concentration |
| 7 | Slope | 0.081 | Terrain steepness |
| 8 | Relative Relief | 0.078 | Local elevation difference |
| 9 | Drainage Density | 0.073 | Drainage network density |

---

## Phase 2: Optimized Models

### Optimization Techniques Applied

| Technique | Purpose | Implementation |
|-----------|---------|----------------|
| **StandardScaler** | Normalize features to zero mean, unit variance | sklearn.preprocessing |
| **SMOTE** | Balance classes by generating synthetic minority samples | imblearn.over_sampling |
| **GridSearchCV** | Systematic hyperparameter search | 5-fold cross-validation |
| **Class Weights** | Penalize misclassification of minority class | `class_weight='balanced'` |
| **Voting Ensemble** | Combine multiple models | Soft voting (probability averaging) |

### Optimized Model Results

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|-------|----------|-----------|--------|-----|---------|
| RandomForest (Optimized) | 66.0% | 64.6% | 66.0% | 0.639 | 0.525 |
| SVM (Optimized) | 56.0% | 56.9% | 56.0% | 0.564 | 0.560 |
| Gradient Boosting | 56.0% | 55.1% | 56.0% | 0.555 | 0.589 |
| Voting Ensemble | 56.0% | 54.2% | 56.0% | 0.548 | 0.535 |
| XGBoost (Optimized) | 54.0% | 52.5% | 54.0% | 0.531 | 0.589 |
| Logistic Regression | 52.0% | 54.9% | 52.0% | 0.527 | 0.503 |

### Key Finding
Despite optimization, improvement was limited (+9.2% F1). **Main bottleneck identified: insufficient training data (only 250 samples).**

---

## Phase 3: Enhanced Stacking Ensemble

### Data Expansion Strategy

| Data Source | Samples | Description |
|-------------|---------|-------------|
| Primary Dataset | 250 | Original labeled landslide points |
| Kerala Landslide Data | 501 | Regional landslide events with coords |
| Global Landslide Catalog | 49 | NASA catalog filtered for India |
| **Total** | **800** | **3.2x expansion** |

### Stacking Ensemble Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │           INPUT FEATURES (9 terrain vars)       │
                    │  slope, aspect, elevation, TWI, SPI, flow_acc,  │
                    │  drainage_density, distance_river, rel_relief   │
                    └─────────────────────┬───────────────────────────┘
                                          │
                    ┌─────────────────────▼───────────────────────────┐
                    │              STANDARDSCALER                      │
                    │     (Normalize to zero mean, unit variance)      │
                    └─────────────────────┬───────────────────────────┘
                                          │
                    ┌─────────────────────▼───────────────────────────┐
                    │                   SMOTE                          │
                    │     (Balance classes via synthetic samples)      │
                    └─────────────────────┬───────────────────────────┘
                                          │
         ┌────────────────────────────────┼────────────────────────────────┐
         │                                │                                │
         ▼                                ▼                                ▼
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│    RANDOMFOREST     │      │      XGBOOST        │      │   LightGBM / RF2    │
│  n_estimators=300   │      │  n_estimators=300   │      │  n_estimators=300   │
│  max_depth=12       │      │  max_depth=8        │      │  max_depth=8        │
│  class_weight=bal   │      │  learning_rate=0.1  │      │  (fallback to RF)   │
└─────────┬───────────┘      └─────────┬───────────┘      └─────────┬───────────┘
          │                            │                            │
          │     LEVEL 1 PREDICTIONS    │                            │
          │    (probability outputs)   │                            │
          └────────────────────────────┼────────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │        LOGISTIC REGRESSION          │
                    │           (Meta-Learner)            │
                    │        class_weight='balanced'      │
                    └──────────────────┬──────────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │         FINAL PREDICTION            │
                    │    0 = No Landslide, 1 = Landslide  │
                    └─────────────────────────────────────┘
```

### Final Model Performance

| Metric | Value | Interpretation |
|--------|-------|----------------|
| **Accuracy** | 85.6% | Correctly classifies 86% of all samples |
| **Precision** | 90.5% | 90% of predicted landslides are correct |
| **Recall** | 77.0% | Detects 77% of actual landslides |
| **F1 Score** | 0.832 | Harmonic mean of precision & recall |
| **ROC-AUC** | 0.958 | Excellent class separation capability |

### Confusion Matrix

```
                      PREDICTED
                   No LS    Landslide
              ┌─────────┬─────────────┐
ACTUAL  No LS │   80    │      6      │  → 93% correctly identified
              ├─────────┼─────────────┤
     Landslide│   17    │     57      │  → 77% correctly identified
              └─────────┴─────────────┘
                  ↓            ↓
              82% True     90% True
              Negative    Positive
```

---

## U-Net Deep Learning Refinement

### Purpose
The U-Net takes the ML susceptibility map and refines it using spatial context from neighboring pixels, slope, and elevation data.

### Architecture

```
U-Net Encoder-Decoder Architecture:

INPUT: 256x256 patch (3 channels)
├── Channel 1: susceptibility_ml (from ML model)
├── Channel 2: slope75 (terrain slope)
└── Channel 3: DEM_filled_75 (elevation)

ENCODER (Downsampling):                    DECODER (Upsampling):
[256×256×3]  ─────────────────────────────→ [256×256×64]   → OUTPUT
     ↓ Conv+ReLU+Pool                            ↑ UpConv+Concat
[128×128×64] ─────────────────────────────→ [128×128×128]
     ↓                                           ↑
[64×64×128]  ─────────────────────────────→ [64×64×256]
     ↓                                           ↑
[32×32×256]  ─────────────────────────────→ [32×32×512]
     ↓                     BOTTLENECK            ↑
[16×16×512] ────────────→ [16×16×1024] ─────────→

OUTPUT: 256×256×1 (refined susceptibility probability)
```

### Training Details

| Parameter | Value |
|-----------|-------|
| Patch Size | 256×256 pixels |
| Stride | 128 (50% overlap) |
| Total Patches | 702 |
| Batch Size | 8 |
| Epochs | 5 |
| Learning Rate | 0.001 |
| Loss Function | Binary Cross-Entropy with Logits |
| Optimizer | Adam |

### Training Progress

| Epoch | Loss | Status |
|-------|------|--------|
| 1 | 0.0521 | Initial |
| 2 | 0.0438 | -15.9% |
| 3 | 0.0388 | -11.4% |
| 4 | 0.0333 | -14.2% |
| 5 | 0.0305 | -8.4% ✓ Final |

---

## How Each Model Works

### 1. Logistic Regression

**What it is:** A linear classifier that predicts the probability of a binary outcome.

**How it works:**
```
P(landslide) = 1 / (1 + e^(-(w₁x₁ + w₂x₂ + ... + wₙxₙ + b)))

Where:
- xᵢ = input features (slope, elevation, etc.)
- wᵢ = learned weights
- b = bias term
```

**Strengths:** Fast, interpretable, works well when classes are linearly separable.
**Weaknesses:** Cannot capture complex non-linear relationships.

---

### 2. Decision Tree

**What it is:** A tree structure that makes decisions by asking yes/no questions about features.

**How it works:**
```
                    [slope > 25°?]
                   /              \
                 YES               NO
                 /                   \
        [elevation > 500m?]    [TWI > 10?]
        /        \              /       \
     YES          NO          YES        NO
      |           |            |          |
  LANDSLIDE    SAFE       LANDSLIDE    SAFE
```

**Strengths:** Highly interpretable, handles non-linear relationships.
**Weaknesses:** Prone to overfitting, unstable (small data changes → large tree changes).

---

### 3. Random Forest

**What it is:** An ensemble of many decision trees, each trained on random subsets of data and features.

**How it works:**
```
Training Data
     │
     ├──→ Bootstrap Sample 1 → Decision Tree 1 → Prediction 1 ─┐
     ├──→ Bootstrap Sample 2 → Decision Tree 2 → Prediction 2 ─┤
     ├──→ Bootstrap Sample 3 → Decision Tree 3 → Prediction 3 ─┼──→ MAJORITY VOTE
     │        ...                   ...              ...        │    → Final Pred
     └──→ Bootstrap Sample N → Decision Tree N → Prediction N ─┘

Key: Each tree sees different data + different features
```

**Configuration used:**
- `n_estimators=300` (300 trees)
- `max_depth=12` (max tree depth)
- `class_weight='balanced'` (adjust for class imbalance)

**Strengths:** Robust, handles overfitting well, provides feature importance.
**Weaknesses:** Slower than single tree, less interpretable.

---

### 4. XGBoost (Extreme Gradient Boosting)

**What it is:** An advanced gradient boosting algorithm that builds trees sequentially, each correcting the errors of the previous ones.

**How it works:**
```
Iteration 1: Build Tree₁ to fit the data
             Calculate residual errors

Iteration 2: Build Tree₂ to fit the RESIDUALS of Tree₁
             Combined prediction = Tree₁ + η×Tree₂

Iteration 3: Build Tree₃ to fit residuals of (Tree₁ + Tree₂)
             Combined = Tree₁ + η×Tree₂ + η×Tree₃

... continue until n_estimators reached

Final Prediction = Σ(ηᵢ × Treeᵢ)   where η = learning rate
```

**Configuration used:**
- `n_estimators=300` (300 boosting rounds)
- `max_depth=8` (prevent overfitting)
- `learning_rate=0.1` (step size)
- `use_label_encoder=False`

**Strengths:** Very accurate, handles missing values, regularization built-in.
**Weaknesses:** Can overfit if not tuned properly, slower training.

---

### 5. LightGBM (Light Gradient Boosting Machine)

**What it is:** A faster, more efficient gradient boosting algorithm that grows trees leaf-wise instead of level-wise.

**How it works:**
```
Traditional (XGBoost):          LightGBM:
Level-wise growth               Leaf-wise growth
                                
    [root]                          [root]
   /      \                        /      \
  O        O   ← grow all        O        [best leaf]
 / \      / \                   / \            |
O   O    O   O                 O   O    [next best]
                                              |
                                        [continues]
```

**Configuration used:**
- `n_estimators=300`
- `max_depth=8`
- `learning_rate=0.1`
- `class_weight='balanced'`

**Strengths:** Faster training, lower memory, often more accurate.
**Weaknesses:** May overfit on small datasets.

**Note:** LightGBM was attempted in our ensemble. If not installed, the system falls back to a second RandomForest.

---

### 6. Support Vector Machine (SVM)

**What it is:** Finds the optimal hyperplane that separates classes with maximum margin.

**How it works:**
```
                    │
           ●        │          ○
       ●            │    ○        ○
           ● ●      │       ○
                    │  ○
        ●           │         ○
    ──────────────MARGIN──────────────
                    │
              HYPERPLANE
              (decision boundary)

RBF Kernel transforms non-linear space → linear separation
```

**Configuration used:**
- `kernel='rbf'` (Radial Basis Function)
- `C=1.0` (regularization)
- `class_weight='balanced'`
- `probability=True` (enable probability estimates)

**Strengths:** Effective in high-dimensional spaces, memory efficient.
**Weaknesses:** Slow on large datasets, sensitive to feature scaling.

---

### 7. Gradient Boosting

**What it is:** Similar to XGBoost but the original scikit-learn implementation.

**How it works:** Same gradient boosting principle as XGBoost, but without the advanced optimizations.

**Configuration used:**
- `n_estimators=100`
- `max_depth=5`
- `learning_rate=0.1`

**Strengths:** Good baseline, well-documented.
**Weaknesses:** Slower than XGBoost, no built-in regularization.

---

### 8. SMOTE (Synthetic Minority Over-sampling Technique)

**What it is:** A preprocessing technique that generates synthetic samples for the minority class.

**How it works:**
```
Original Minority Sample: X = [slope=30, elevation=800]
Nearest Neighbor:         Y = [slope=35, elevation=850]

Synthetic Sample = X + rand(0,1) × (Y - X)
                 = [30, 800] + 0.4 × ([35, 850] - [30, 800])
                 = [30, 800] + 0.4 × [5, 50]
                 = [32, 820]  ← NEW synthetic landslide point
```

**Why we use it:** Balanced training data → better learning for minority class (landslides).

---

### 9. U-Net (Deep Learning)

**What it is:** A convolutional neural network designed for image segmentation, adapted here for spatial refinement.

**How it works:**
1. **Encoder:** Compresses the image, learning high-level features
2. **Bottleneck:** Captures the most abstract representation
3. **Decoder:** Expands back to original size, using skip connections
4. **Skip Connections:** Preserve fine details from encoder layers

**Why we use it:** Captures spatial patterns that pixel-wise ML cannot - for example, edge detection of landslide-prone zones.

---

## How the Stacking Ensemble Works

### The Problem with Single Models
Each model has biases:
- RandomForest may miss subtle patterns
- XGBoost may overfit on noise
- LightGBM may be too aggressive on small data

### The Stacking Solution

**Level 1 - Diverse Base Models:**
```
Input Features → [RandomForest] → Probability₁ (e.g., 0.72)
Input Features → [XGBoost]      → Probability₂ (e.g., 0.68)
Input Features → [LightGBM/RF]  → Probability₃ (e.g., 0.75)
```

**Level 2 - Meta-Learner Combines:**
```
[Probability₁, Probability₂, Probability₃] → [Logistic Regression] → Final (0.73)
```

### Why It Works

1. **Diversity:** Each base model captures different patterns
2. **Error Cancellation:** One model's mistake is corrected by others
3. **Learned Weighting:** Meta-learner learns optimal combination weights
4. **Regularization:** Prevents any single model from dominating

### Cross-Validation in Stacking

To avoid data leakage, we use **out-of-fold predictions**:
```
Fold 1: Train on folds 2,3,4,5 → Predict fold 1
Fold 2: Train on folds 1,3,4,5 → Predict fold 2
Fold 3: Train on folds 1,2,4,5 → Predict fold 3
Fold 4: Train on folds 1,2,3,5 → Predict fold 4
Fold 5: Train on folds 1,2,3,4 → Predict fold 5

Meta-features = Concatenation of all out-of-fold predictions
```

---

## File Inventory

### Active Files (Currently Used)

| File | Purpose | Status |
|------|---------|--------|
| `enhanced_model.pkl` | Trained stacking ensemble | ✅ ACTIVE |
| `enhanced_scaler.pkl` | Feature scaler | ✅ ACTIVE |
| `enhanced_model.py` | Training script | ✅ ACTIVE |
| `data_preparation.py` | Data merging script | ✅ ACTIVE |
| `generate_susceptibility_map.py` | ML map generation | ✅ ACTIVE |
| `unet_refine.py` | Deep learning refinement | ✅ ACTIVE |
| `generate_runout_and_fuse.py` | Hazard zone fusion | ✅ ACTIVE |
| `enhanced_model_report.md` | Performance report | ✅ ACTIVE |

### Legacy Files (Historical Reference)

| File | Original Purpose | Status |
|------|------------------|--------|
| `legacy_landslide_model_rf.pkl` | Baseline RandomForest model | 📦 LEGACY |
| `legacy_landslide_model_optimized.pkl` | Optimized RF model | 📦 LEGACY |
| `legacy_landslide_model_xgb.pkl` | Optimized XGBoost model | 📦 LEGACY |
| `legacy_scaler.pkl` | Old feature scaler | 📦 LEGACY |
| `legacy_evaluate_models.py` | Baseline evaluation script | 📦 LEGACY |
| `legacy_optimize_models.py` | Optimization script | 📦 LEGACY |
| `legacy_train_models.py` | Basic training script | 📦 LEGACY |
| `legacy_test.py` | Test script | 📦 LEGACY |
| `legacy_test_susceptibility.py` | Susceptibility test | 📦 LEGACY |
| `legacy_colorize_hazard.py` | Hazard colorization | 📦 LEGACY |
| `legacy_make_hazard_preview.py` | Preview generation | 📦 LEGACY |
| `model_evaluation_report.md` | Baseline evaluation report | 📦 LEGACY |
| `optimized_model_report.md` | Optimization report | 📦 LEGACY |

### Utility Files

| File | Purpose |
|------|---------|
| `inspect_rasters.py` | Raster inspection utility |
| `requirements.txt` | Python dependencies |

---

## Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE ML PIPELINE                             │
└──────────────────────────────────────────────────────────────────────────┘

STEP 1: DATA PREPARATION
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Primary Dataset │ + │ Kerala Data     │ + │ Global Catalog  │
│ (250 samples)   │   │ (501 samples)   │   │ (49 samples)    │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         └───────────────────┬─────────────────────────┘
                             ↓
                   data_preparation.py
                             ↓
              merged_landslide_data.csv (800 samples)

STEP 2: MODEL TRAINING
                             ↓
                   enhanced_model.py
            ┌────────────────┼────────────────┐
            ↓                ↓                ↓
      RandomForest      XGBoost        LightGBM/RF
            └────────────────┼────────────────┘
                             ↓
                   Logistic Regression (Meta)
                             ↓
         enhanced_model.pkl + enhanced_scaler.pkl

STEP 3: ML SUSCEPTIBILITY MAP
                             ↓
              generate_susceptibility_map.py
              (Loads rasters, applies model)
                             ↓
                   susceptibility_ml.tif

STEP 4: DEEP LEARNING REFINEMENT
                             ↓
                      unet_refine.py
            (U-Net spatial refinement)
                             ↓
                   susceptibility_dl.tif

STEP 5: HAZARD ZONE GENERATION
                             ↓
              generate_runout_and_fuse.py
            (D8 flow, runout tracing)
                             ↓
         ┌───────────┬───────────┬───────────┐
         ↓           ↓           ↓           ↓
   hazard_fused  runout_paths  transit    deposition
      .tif        .geojson    _mask.tif   _mask.tif

STEP 6: FRONTEND DISPLAY
                             ↓
         Backend tile server → Frontend map layers
```

---

## Code Changes Summary

### 1. generate_susceptibility_map.py
Changed model from XGBoost to enhanced stacking ensemble:
```diff
- model_path = "landslide_model_xgb.pkl"
+ model_path = "enhanced_model.pkl"
+ scaler_path = "enhanced_scaler.pkl"

+ # Apply scaling before prediction
+ flat_scaled = scaler.transform(flat)
- pred = model.predict_proba(flat)[:, 1]
+ pred = model.predict_proba(flat_scaled)[:, 1]
```

### 2. generate_runout_and_fuse.py
Adjusted threshold for enhanced model's higher output values:
```diff
- THRESH_HIGH = 0.25   # Too low for enhanced model
+ THRESH_HIGH = 0.70   # Appropriate for new predictions
```

### 3. unet_refine.py
Updated paths to use backend rasters directory:
```diff
- RASTER_DIR = r"C:\coding\rasters"
+ RASTER_DIR = r"C:\coding\Slipsense\backend\rasters"
```

---

## Conclusion

The SlipSense ML pipeline evolution from baseline models to the enhanced stacking ensemble represents a **42% improvement in F1 score** (0.585 → 0.832). Key success factors:

1. **Data Expansion:** 3.2x more training samples
2. **Ensemble Learning:** Combining RF + XGBoost + LightGBM
3. **Stacking Architecture:** Meta-learner optimally weighs base models
4. **Deep Learning Refinement:** U-Net adds spatial awareness

The system now achieves production-quality landslide prediction suitable for real-world deployment.

---

*Document prepared for academic presentation and project documentation.*
*Last updated: February 6, 2026*
