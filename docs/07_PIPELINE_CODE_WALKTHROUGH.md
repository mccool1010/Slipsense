# SlipSense: From Raw Input to Raster Layers — Full Pipeline Walkthrough

**Document Version:** 2.0
**Last Updated:** 2026-02-17
**Project:** SlipSense Landslide Prediction System

---

## Overview

This document traces the **complete journey of data** through the SlipSense pipeline — from the very first CSV inputs and GeoTIFF rasters, through five Python scripts that each process, transform, and refine the data, until we arrive at the **final raster layers** displayed on the frontend map. Every significant line of code is explained, with clear annotations on **where input is taken**, **why each step matters**, and **what each file outputs**.

### Pipeline at a Glance

```
 ┌────────────────────┐   ┌────────────────────┐   ┌──────────────────────┐
 │  CSV Data Sources   │   │  GeoTIFF Rasters    │   │  (9 terrain rasters) │
 │  (landslide points) │   │  (slope, DEM, etc.) │   │                      │
 └────────┬───────────┘   └────────┬───────────┘   └──────────┬───────────┘
          │                        │                           │
          ▼                        │                           │
 ┌────────────────────────┐        │                           │
 │  1. data_preparation.py │◀──────┘                           │
 │  Output: merged CSV     │                                   │
 └────────┬───────────────┘                                    │
          ▼                                                    │
 ┌────────────────────────┐                                    │
 │  2. enhanced_model.py   │                                   │
 │  Output: .pkl model     │                                   │
 └────────┬───────────────┘                                    │
          ▼                                                    │
 ┌─────────────────────────────────┐                           │
 │  3. generate_susceptibility_    │◀──────────────────────────┘
 │     map.py                      │
 │  Output: susceptibility_ml.tif  │
 └────────┬───────────────────────┘
          ▼
 ┌─────────────────────────────────┐
 │  4. unet_refine.py              │
 │  Output: susceptibility_dl.tif  │
 └────────┬───────────────────────┘
          ▼
 ┌─────────────────────────────────┐
 │  5. generate_runout_and_fuse.py │
 │  Outputs: hazard_fused.tif,     │
 │  runout_paths.geojson,          │
 │  transit_mask.tif,              │
 │  deposition_mask.tif            │
 └────────┬───────────────────────┘
          ▼
 ┌─────────────────────────────────┐
 │  6. Backend Tile Server         │
 │  (tiles.py + config.py)         │
 │  Serves rasters → Frontend      │
 └────────────────────────────────┘
```

### The 9 Terrain Rasters (Used Throughout the Pipeline)

These GeoTIFF files cover Kerala at 75m resolution. They are the **core geographic inputs** used by multiple scripts:

| Raster File | Feature Name | What It Represents | Why It Matters for Landslides |
|-------------|--------------|-------------------|-------------------------------|
| `slope75.tif` | slope | Steepness of terrain in degrees | Steeper slopes = higher landslide risk |
| `aspect75.tif` | aspect | Compass direction the slope faces (0–360°) | Certain slope orientations receive more rain/sun |
| `DEM_filled_75.tif` | elevation | Height above sea level (meters) | High elevations with steep slopes are most dangerous |
| `TWI_FINAL.tif` | twi | Topographic Wetness Index | High TWI = more water saturation = weaker soil |
| `SPI75.tif` | spi | Stream Power Index | Measures erosive power of water flow |
| `Flow_Accumulation_clean75.tif` | flow_acc | Accumulated water flow at each pixel | High accumulation = stream locations |
| `Distance_to_River_75.tif` | dist_river | Distance to nearest river (meters) | Close to rivers = more erosion risk |
| `Drainage_Density_Final.tif` | drainage_density | Density of drainage channels | Dense drainage = more water movement |
| `Relative_Relief_75.tif` | relative_relief | Elevation difference in local area | High relief = unstable terrain |

---

## Step 1 — Data Preparation (`data_preparation.py`)

### Significance

> **Why this file exists:** The ML model needs many labeled examples to learn from. We only had 250 labeled points from our primary survey. This script **expands the dataset to ~800 samples** by merging data from 3 different sources — our primary data, Kerala government data, and NASA's global catalog — so the ML model can learn better patterns.

### Where Input is Taken

```python
# LINE 22-23: These set the directories where ALL input files are located
DATA_DIR = Path(r"C:\coding\Slipsense\data")          # CSV files live here
RASTER_DIR = Path(r"C:\coding\Slipsense\backend\rasters")  # GeoTIFF rasters live here

# LINE 26-28: These are the 3 CSV input files
PRIMARY_DATA = DATA_DIR / "landslide - Sheet1 (1).csv"           # ◀ INPUT 1: 250 labeled samples
KERALA_DATA = DATA_DIR / "kerala_landslide_data.csv"             # ◀ INPUT 2: 501 Kerala records
GLOBAL_CATALOG = DATA_DIR / "Global_Landslide_Catalog_Export_rows.csv"  # ◀ INPUT 3: NASA catalog

# LINE 31: This is the OUTPUT file
OUTPUT_FILE = DATA_DIR / "merged_landslide_data.csv"             # ◀ OUTPUT: merged dataset

# LINE 34-44: These 9 rasters are INPUT for extracting terrain feature values at lat/lon points
RASTERS = {
    'slope': RASTER_DIR / "slope75.tif",              # ◀ INPUT: terrain rasters
    'aspect': RASTER_DIR / "aspect75.tif",
    'elevation': RASTER_DIR / "DEM_filled_75.tif",
    'twi': RASTER_DIR / "TWI_FINAL.tif",
    'spi': RASTER_DIR / "SPI75.tif",
    'flow_acc': RASTER_DIR / "Flow_Accumulation_clean75.tif",
    'dist_river': RASTER_DIR / "Distance_to_River_75.tif",
    'drainage_density': RASTER_DIR / "Drainage_Density_Final.tif",
    'relative_relief': RASTER_DIR / "Relative_Relief_75.tif",
}
```

### Line-by-Line Code Walkthrough

#### Function: `load_primary_data()` (Lines 55–83)

This loads the first and most important dataset — 250 hand-verified landslide/non-landslide points that already have terrain features pre-extracted.

```python
def load_primary_data():
    # LINE 58: Read the CSV file into a pandas DataFrame
    # WHY: This CSV has columns like 'Relative_Relief_751', 'slope751', etc.
    # with values already extracted from the rasters for each point
    df = pd.read_csv(PRIMARY_DATA)

    # LINE 61-72: Rename columns to clean, standardized names
    # WHY: The original CSV has messy names like 'Relative_Relief_751' and 'SPI751'
    # (the '751' is from the raster filename). We rename to simple names like
    # 'relative_relief' and 'spi' so all datasets use the same column names.
    column_mapping = {
        'Relative_Relief_751': 'relative_relief',  # Elevation difference → landslide indicator
        'SPI751': 'spi',                            # Stream Power Index
        'TWI_FINAL751': 'twi',                      # Topographic Wetness
        'Flow_Accumulation_clean751': 'flow_acc',   # Water accumulation
        'aspect751': 'aspect',                      # Slope direction
        'slope751': 'slope',                        # Steepness
        'Elevation1': 'elevation',                  # Height
        'Distance_to_River': 'dist_river',          # River proximity
        'Drainage_Density': 'drainage_density',     # Drainage network density
        'Landslide': 'landslide'                    # LABEL: 0=safe, 1=landslide
    }
    df = df.rename(columns=column_mapping)

    # LINE 76-78: Keep only the 9 feature columns + the label
    # WHY: The CSV might have extra columns we don't need. We only need the
    # 9 terrain features and the landslide label for training.
    feature_cols = ['relative_relief', 'spi', 'twi', 'flow_acc', 'aspect',
                    'slope', 'elevation', 'dist_river', 'drainage_density', 'landslide']
    df = df[feature_cols]

    # LINE 79: Tag the source so we can track where each sample came from
    df['source'] = 'primary'

    return df  # Returns: DataFrame with 250 rows, 11 columns
```

#### Function: `load_kerala_data()` (Lines 86–117)

```python
def load_kerala_data():
    # LINE 89: Read the Kerala government landslide dataset
    df = pd.read_csv(KERALA_DATA)

    # LINE 92-93: Convert text risk levels to binary numbers
    # WHY: Our model needs 0/1 labels, not text. "High" and "Moderate" risk
    # both mean a landslide happened (1), while "Low" means safe (0).
    risk_mapping = {'High': 1, 'Moderate': 1, 'Low': 0}
    df['landslide'] = df['risk_level'].map(risk_mapping)

    # LINE 97-108: Generate approximate feature values
    # WHY: This dataset only has 'slope' — it's missing the other 8 features.
    # Since we can't look up raster values for these (no exact coordinates),
    # we generate statistically reasonable approximations:
    df['relative_relief'] = df['slope'] * 1.5   # Correlated with slope
    df['spi'] = np.random.uniform(-5, 5, len(df))  # Random within typical range
    df['twi'] = np.random.uniform(1, 18, len(df))
    df['flow_acc'] = np.random.uniform(1, 10, len(df))
    df['aspect'] = np.random.uniform(0, 360, len(df))

    # LINE 102-107: Elevation and river distance depend on landslide label
    # WHY: Landslide areas tend to have higher elevation and be closer to rivers.
    # We use different ranges for positive (landslide=1) vs negative (landslide=0)
    # to make the synthetic features more realistic.
    df['elevation'] = np.where(df['landslide'] == 1,
                               np.random.uniform(500, 1400, len(df)),   # Higher for landslides
                               np.random.uniform(50, 800, len(df)))     # Lower for safe areas
    df['dist_river'] = np.where(df['landslide'] == 1,
                                np.random.uniform(200, 1000, len(df)),  # Closer for landslides
                                np.random.uniform(1500, 2600, len(df))) # Farther for safe areas

    return df  # Returns: DataFrame with 501 rows, 11 columns
```

#### Function: `extract_features_from_rasters()` (Lines 120–144)

This is the function that **reads actual raster values** at a specific geographic coordinate.

```python
def extract_features_from_rasters(lat, lon):
    features = {}

    # LINE 124: Loop through each of the 9 rasters
    for name, raster_path in RASTERS.items():
        try:
            # LINE 130: Open the raster file using rasterio
            with rasterio.open(raster_path) as src:

                # LINE 132: Convert latitude/longitude → pixel row/column
                # WHY: Rasters are grids of pixels. To find the value at a
                # real-world location, we need to convert the lat/lon into
                # which pixel (row, column) corresponds to that location.
                # The raster's 'transform' matrix handles this conversion.
                row, col = rowcol(src.transform, lon, lat)

                # LINE 135-138: Read the single pixel value at that location
                # WHY: We create a tiny 1×1 window at the exact pixel, then read it.
                if 0 <= row < src.height and 0 <= col < src.width:
                    window = rasterio.windows.Window(col, row, 1, 1)
                    value = src.read(1, window=window)[0, 0]  # Read band 1, get single value
                    features[name] = float(value)
                else:
                    features[name] = np.nan  # Point is outside the raster's coverage
        except Exception:
            features[name] = np.nan

    return features  # Returns: dict with 9 keys like {'slope': 28.5, 'elevation': 850, ...}
```

#### Function: `load_global_catalog()` (Lines 147–200)

```python
def load_global_catalog():
    # LINE 150: Read NASA's global catalog (11,000+ events worldwide)
    df = pd.read_csv(GLOBAL_CATALOG, low_memory=False)

    # LINE 153-158: Filter to only Kerala/Karnataka region
    # WHY: We only need events in our study area. The catalog covers the entire
    # world, so we filter by latitude (8°N to 16°N) and longitude (74°E to 78.5°E).
    india_df = df[
        (df['latitude'] >= 8.0)  & (df['latitude'] <= 16.0) &
        (df['longitude'] >= 74.0) & (df['longitude'] <= 78.5)
    ]
    # Result: ~49 events in our study area

    # LINE 167-176: For each event, extract terrain features from rasters
    # WHY: These events have lat/lon coordinates. We read the actual raster pixel
    # values at each coordinate to get real terrain feature values for that location.
    samples = []
    for _, row in india_df.iterrows():
        features = extract_features_from_rasters(row['latitude'], row['longitude'])

        # Only keep if at least 3 of the 9 features are valid (not NaN)
        valid_features = sum(1 for v in features.values() if not np.isnan(v))
        if valid_features >= 3:
            features['landslide'] = 1  # All catalog events are confirmed landslides
            samples.append(features)

    return pd.DataFrame(samples)  # Returns: ~49 rows with real raster-extracted features
```

#### Function: `main()` — Merge, Balance, Save (Lines 254–307)

```python
def main():
    # LINE 260-262: Load all three data sources
    primary_df = load_primary_data()    # 250 samples
    kerala_df = load_kerala_data()      # 501 samples
    global_df = load_global_catalog()   # ~49 samples

    # LINE 270: Merge all into one DataFrame
    # WHY: combine all data sources into a single training dataset
    merged = pd.concat([primary_df, kerala_df, global_df], ignore_index=True)
    # Result: ~800 rows total

    # LINE 278-280: If too many positive samples, add synthetic negative samples
    # WHY: If we have way more landslide points (class 1) than safe points (class 0),
    # the model will be biased. We generate fake "safe" points with realistic
    # terrain values (low slope, low elevation, far from rivers).
    if pos_count > neg_count * 1.2:
        extra_neg = generate_negative_samples(n_samples=pos_count - neg_count)
        merged = pd.concat([merged, extra_neg], ignore_index=True)

    # LINE 283: Balance classes to 45% positive / 55% negative
    # WHY: A balanced dataset prevents the model from just predicting the majority class.
    balanced = balance_dataset(merged, target_ratio=0.45)

    # LINE 290-292: Fill any remaining NaN values with column medians
    # WHY: The model cannot accept NaN values. Median is used because it's robust
    # to outliers (unlike mean which can be skewed by extreme values).
    for col in feature_cols:
        balanced[col] = balanced[col].fillna(balanced[col].median())

    # LINE 295: Save the final merged dataset as CSV
    balanced.to_csv(OUTPUT_FILE, index=False)
    # ◀ OUTPUT: data/merged_landslide_data.csv (~800 rows × 11 columns)
```

### Output

| Output | Path | Format | Description |
|--------|------|--------|-------------|
| **merged_landslide_data.csv** | `data/merged_landslide_data.csv` | CSV with columns: `relative_relief`, `spi`, `twi`, `flow_acc`, `aspect`, `slope`, `elevation`, `dist_river`, `drainage_density`, `landslide`, `source` | ~800 labeled samples ready for model training |

---

## Step 2 — Model Training (`enhanced_model.py`)

### Significance

> **Why this file exists:** This is the **core ML training script**. It takes the labeled CSV dataset and trains a powerful Stacking Ensemble model — three different ML algorithms combined by a meta-learner to get the best prediction accuracy. The trained model is saved as a `.pkl` file that is loaded by later scripts to make predictions.

### Where Input is Taken

```python
# LINE 54: The ONLY input to this file — the merged CSV from Step 1
DATA_FILE = DATA_DIR / "merged_landslide_data.csv"    # ◀ INPUT: from data_preparation.py

# LINE 57-59: The THREE outputs this file produces
MODEL_OUT = MODEL_DIR / "enhanced_model.pkl"           # ◀ OUTPUT 1: trained model
SCALER_OUT = MODEL_DIR / "enhanced_scaler.pkl"         # ◀ OUTPUT 2: feature scaler
REPORT_OUT = MODEL_DIR / "enhanced_model_report.md"    # ◀ OUTPUT 3: performance report

# LINE 62-65: The 9 features the model expects — same order as data_preparation.py
FEATURE_COLS = [
    'relative_relief', 'spi', 'twi', 'flow_acc', 'aspect',
    'slope', 'elevation', 'dist_river', 'drainage_density'
]
```

### Line-by-Line Code Walkthrough

#### Function: `load_data()` (Lines 68–80)

```python
def load_data():
    # LINE 71: Read the merged CSV (output of Step 1)
    df = pd.read_csv(DATA_FILE)

    # LINE 73: Extract the 9 feature columns as a NumPy array
    # WHY: sklearn models expect a 2D NumPy array where each row is a sample
    # and each column is a feature. Shape: (800, 9)
    X = df[FEATURE_COLS].values

    # LINE 74: Extract the labels (0 or 1) as a 1D array
    # WHY: These are what the model learns to predict. Shape: (800,)
    y = df['landslide'].values.astype(int)

    return X, y, df
```

#### Function: `create_stacking_ensemble()` (Lines 83–167)

```python
def create_stacking_ensemble():
    # LINE 91-100: Base Model 1 — RandomForest
    # WHY: RF trains many independent decision trees on random subsets of data,
    # then averages their predictions. It's robust and handles non-linear patterns.
    rf = RandomForestClassifier(
        n_estimators=300,       # Build 300 different decision trees
        max_depth=12,           # Each tree can be at most 12 levels deep
        min_samples_split=4,    # Need at least 4 samples to split a node
        min_samples_leaf=2,     # Each leaf must have at least 2 samples
        class_weight='balanced', # Give more weight to minority class (landslides)
        random_state=42,        # For reproducibility
        n_jobs=-1               # Use all CPU cores for parallel processing
    )
    estimators.append(('rf', rf))

    # LINE 105-117: Base Model 2 — XGBoost
    # WHY: XGBoost builds trees sequentially, where each new tree corrects the
    # mistakes of all previous trees. It captures different patterns than RF.
    xgb = XGBClassifier(
        n_estimators=300,         # 300 boosting rounds
        max_depth=8,              # Shallower trees to prevent overfitting
        learning_rate=0.05,       # Small step size → more precise learning
        subsample=0.8,            # Use 80% of data per round (prevents overfitting)
        colsample_bytree=0.8,    # Use 80% of features per tree
        scale_pos_weight=1.5,    # Give 1.5x weight to positive (landslide) class
        use_label_encoder=False,
        eval_metric='logloss'     # Optimize for log-loss (classification metric)
    )
    estimators.append(('xgb', xgb))

    # LINE 122-131: Base Model 3 — LightGBM
    # WHY: LightGBM grows trees leaf-wise (most accurate split first) instead of
    # level-wise like XGBoost. This often finds patterns others miss.
    lgbm = LGBMClassifier(
        n_estimators=300,
        max_depth=8,
        learning_rate=0.05,
        num_leaves=50,             # Max number of leaves per tree
        class_weight='balanced',
        verbose=-1                 # Suppress verbose output
    )
    estimators.append(('lgbm', lgbm))

    # LINE 148-153: Meta-Learner — Logistic Regression
    # WHY: Instead of simple averaging, Logistic Regression LEARNS the optimal
    # way to combine the 3 base models' predictions. It figures out which model
    # to trust more for which patterns.
    meta_learner = LogisticRegression(
        C=1.0,                    # Regularization strength
        class_weight='balanced',  # Balanced for class imbalance
        max_iter=1000
    )

    # LINE 156-161: Combine into Stacking Classifier
    # WHY: StackingClassifier handles the entire 2-level architecture:
    #   Level 1: Each base model makes predictions using 5-fold cross-validation
    #   Level 2: Meta-learner combines those predictions into final prediction
    stacking = StackingClassifier(
        estimators=estimators,              # The 3 base models
        final_estimator=meta_learner,       # The meta-learner
        cv=5,                               # 5-fold cross-validation for Level 1
        stack_method='predict_proba',       # Pass probabilities (not just 0/1) to meta-learner
        n_jobs=-1                           # Use all CPU cores
    )

    return stacking
```

#### Function: `main()` — Train and Save (Lines 236–313)

```python
def main():
    # LINE 242: Load the merged dataset
    X, y, df = load_data()

    # LINE 245-247: Split data into training (80%) and testing (20%)
    # WHY: We train on 80% and test on the unseen 20% to check if the model
    # generalizes well. 'stratify=y' ensures both splits have the same class ratio.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # LINE 253-254: Normalize all features to zero mean and unit variance
    # WHY: Without scaling, features with large values (like elevation in 100s–1000s)
    # would dominate features with small values (like drainage_density in 0–5).
    # StandardScaler makes all features equally important by converting them to
    # z-scores: value' = (value - mean) / standard_deviation
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)  # fit: learns mean/std from training data
                                                     # transform: applies the normalization

    # LINE 258-261: Apply SMOTE oversampling on training data only
    # WHY: If we have fewer landslide samples than non-landslide samples, the model
    # might just learn to always predict "no landslide". SMOTE creates synthetic
    # minority samples by interpolating between existing positive examples.
    smote = SMOTE(random_state=42)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)

    # LINE 266-270: Build and train the stacking ensemble
    model = create_stacking_ensemble()
    model.fit(X_train_resampled, y_train_resampled)
    # This internally does:
    #   1. 5-fold CV: Train each base model on 4 folds, predict the 5th fold
    #   2. Collect all out-of-fold predictions from 3 models
    #   3. Train meta-learner on those predictions to learn optimal combination

    # LINE 291-295: Save the trained model and scaler as .pkl files
    # WHY: .pkl (pickle) files serialize Python objects to disk so we can load
    # them later in generate_susceptibility_map.py without retraining.
    joblib.dump(model, MODEL_OUT)    # ◀ OUTPUT: enhanced_model.pkl (~4 MB)
    joblib.dump(scaler, SCALER_OUT)  # ◀ OUTPUT: enhanced_scaler.pkl (~1 KB)
```

### Output

| Output | Path | Description | Used By |
|--------|------|-------------|---------|
| **enhanced_model.pkl** | `ml_models/enhanced_model.pkl` | Serialized stacking ensemble model (~4 MB) | Step 3 |
| **enhanced_scaler.pkl** | `ml_models/enhanced_scaler.pkl` | StandardScaler with learned mean/std for 9 features | Step 3 |
| **enhanced_model_report.md** | `ml_models/enhanced_model_report.md` | Markdown report with F1=0.832, Accuracy=85.6%, etc. | Documentation |

---

## Step 3 — Susceptibility Map Generation (`generate_susceptibility_map.py`)

### Significance

> **Why this file exists:** Steps 1 and 2 trained a model on individual labeled points. Now we need to apply that model to **every single pixel** in the entire Kerala region to produce a full geographic probability map. This is the critical step that converts "a model that can predict" into "a map you can see."

### Where Input is Taken

```python
# LINE 20-23: All inputs and output paths defined here
raster_dir = r"C:\coding\Slipsense\backend\rasters"               # ◀ WHERE: rasters folder
model_path = r"C:\coding\Slipsense\ml_models\enhanced_model.pkl"  # ◀ INPUT: trained model (from Step 2)
scaler_path = r"C:\coding\Slipsense\ml_models\enhanced_scaler.pkl" # ◀ INPUT: scaler (from Step 2)
output_tif = r"C:\coding\Slipsense\backend\rasters\susceptibility_ml.tif"  # ◀ OUTPUT

# LINE 28-38: The 9 rasters — MUST be in the SAME ORDER as FEATURE_COLS in enhanced_model.py
# WHY: The model was trained expecting features in this exact order.
# If we swap 'slope' and 'elevation', the model would use slope values
# as if they were elevation values, giving garbage predictions.
rasters = {
    "Relative_Relief_75": "Relative_Relief_75.tif",     # Feature 0: relative_relief
    "SPI75": "SPI75.tif",                               # Feature 1: spi
    "TWI_FINAL": "TWI_FINAL.tif",                       # Feature 2: twi
    "Flow_Accumulation_clean75": "Flow_Accumulation_clean75.tif",  # Feature 3: flow_acc
    "aspect75": "aspect75.tif",                          # Feature 4: aspect
    "slope75": "slope75.tif",                            # Feature 5: slope
    "Elevation": "DEM_filled_75.tif",                    # Feature 6: elevation
    "Distance_to_River_75": "Distance_to_River_75.tif",  # Feature 7: dist_river
    "Drainage_Density_Final": "Drainage_Density_Final.tif" # Feature 8: drainage_density
}
```

### Line-by-Line Code Walkthrough

```python
# LINE 43-45: Load the pre-trained model and scaler from .pkl files
model = joblib.load(model_path)    # Load the stacking ensemble from Step 2
scaler = joblib.load(scaler_path)  # Load the StandardScaler from Step 2

# LINE 51-57: Read the FIRST raster to learn the geographic metadata
# WHY: All rasters cover the same area, so we read one to get:
#   - width, height: pixel dimensions of the map
#   - transform: how to convert pixel coordinates ↔ real-world lat/lon
#   - crs: coordinate reference system (what projection is used)
with rasterio.open(sample_raster_path) as src:
    profile = src.profile      # All metadata (dimensions, CRS, data type, etc.)
    width = src.width          # e.g., 7000 pixels wide
    height = src.height        # e.g., 9000 pixels tall
    transform = src.transform  # Affine matrix: pixel → geographic coordinates

# LINE 63-87: Load ALL 9 rasters into a 3D array
# WHY: We need all 9 feature values for every pixel. Each raster is a 2D grid
# of the same size. We stack them into a single 3D block (H × W × 9).
feature_stack = []
for key, filename in rasters.items():
    with rasterio.open(os.path.join(raster_dir, filename)) as src:
        arr = src.read(1).astype("float32")  # Read band 1 into a 2D NumPy array

        # LINE 79-80: Replace missing/nodata pixels with the average value
        # WHY: Some pixels at the edges of the raster have "nodata" markers.
        # The model cannot handle NaN values, so we fill them with the average.
        nodata = src.nodata
        if nodata is not None:
            arr[arr == nodata] = np.nan
        arr = np.nan_to_num(arr, nan=np.nanmean(arr))

        # LINE 83-86: Resize if dimensions don't match
        # WHY: Most rasters are the same size, but some may differ slightly.
        # We resize to match the reference dimensions using bilinear interpolation.
        if arr.shape != (height, width):
            zoom_factors = (height / arr.shape[0], width / arr.shape[1])
            arr = zoom(arr, zoom_factors, order=1)  # order=1 = bilinear interpolation

        feature_stack.append(arr)

# LINE 89: Stack all 9 rasters into one big 3D array
data = np.stack(feature_stack, axis=-1)  # Shape: (height, width, 9)
# This is like a 9-band satellite image, where each "band" is one terrain feature

# LINE 95-99: Flatten → Scale → Predict → Reshape
# WHY: The model expects input as (n_samples, 9_features). But we have a 2D
# grid of pixels. So we flatten the grid into rows, predict, then reshape back.

flat = data.reshape(-1, data.shape[-1])       # Shape: (H*W, 9) — one row per pixel
# flat[0] = [relative_relief, spi, twi, flow_acc, aspect, slope, elevation, dist_river, drainage_density]
# This is the EXACT SAME format as one row in merged_landslide_data.csv

flat_scaled = scaler.transform(flat)           # Apply the SAME normalization from training
# WHY: The model was trained on scaled data. If we don't scale, the predictions
# would be meaningless because the model expects z-score normalized inputs.

pred = model.predict_proba(flat_scaled)[:, 1]  # Get P(landslide) for each pixel
# predict_proba returns [[P(class0), P(class1)], ...] for each sample
# We take [:, 1] which is the probability of class 1 (landslide)
# Values range from 0.0 (definitely safe) to 1.0 (definitely landslide)

pred_map = pred.reshape(height, width)          # Reshape back to 2D map

# LINE 106-115: Save as a GeoTIFF with the same geographic metadata
# WHY: GeoTIFF preserves the exact location, projection, and resolution so this
# output "lines up" perfectly with the input rasters on any map.
new_profile = profile.copy()
new_profile.update({
    "dtype": "float32",     # Store as float (0.0–1.0 probabilities)
    "count": 1,             # Single band
    "compress": "lzw"       # LZW compression to reduce file size
})

with rasterio.open(output_tif, "w", **new_profile) as dst:
    dst.write(pred_map.astype("float32"), 1)   # Write the 2D probability array as band 1
# ◀ OUTPUT: backend/rasters/susceptibility_ml.tif (~55 MB)
```

### Output

| Output | Path | Format | Description | Used By |
|--------|------|--------|-------------|---------|
| **susceptibility_ml.tif** | `backend/rasters/susceptibility_ml.tif` | GeoTIFF, float32, single band | Each pixel = probability of landslide (0.0–1.0) | Step 4 (U-Net) |

---

## Step 4 — U-Net Deep Learning Refinement (`unet_refine.py`)

### Significance

> **Why this file exists:** The ML map from Step 3 treats each pixel independently — it doesn't know about neighboring pixels. But landslides are **spatial phenomena**: a steep slope *leading into* a valley is more dangerous than a steep slope on its own. The U-Net neural network looks at 256×256 pixel neighborhoods and learns spatial patterns, producing a **smoother, more accurate** susceptibility map.

### Where Input is Taken

```python
# LINE 35-38: Input rasters
RASTER_DIR = r"C:\coding\Slipsense\backend\rasters"
SUS_TIF = os.path.join(RASTER_DIR, "susceptibility_ml.tif")  # ◀ INPUT: output from Step 3
SLOPE_TIF = os.path.join(RASTER_DIR, "slope75.tif")           # ◀ INPUT: terrain slope
DEM_TIF = os.path.join(RASTER_DIR, "DEM_filled_75.tif")       # ◀ INPUT: elevation

# LINE 47-48: Outputs
MODEL_OUT = os.path.join(OUT_DIR, "unet_refiner.pth")          # ◀ OUTPUT 1: U-Net weights
OUT_TIF = os.path.join(OUT_DIR, "susceptibility_dl.tif")       # ◀ OUTPUT 2: refined map
```

### Key Code Walkthrough

#### U-Net Architecture (Lines 55–90)

```python
# WHY 3 channels: susceptibility_ml (what the ML model thinks), slope (steepness),
# and DEM (elevation). Together they give the U-Net spatial + terrain context.

class UNetSmall(nn.Module):
    def __init__(self, in_ch=3, out_ch=1, base=32):
        # ENCODER: Compresses the image, learning high-level features
        self.enc1 = ConvBlock(3, 32)       # 256×256×3  → 256×256×32
        self.enc2 = ConvBlock(32, 64)      # 128×128×32 → 128×128×64
        self.enc3 = ConvBlock(64, 128)     # 64×64×64   → 64×64×128
        self.pool = nn.MaxPool2d(2)        # Halves dimensions (256→128→64)

        # DECODER: Expands back up, combining high-level + low-level features
        self.up = nn.Upsample(scale_factor=2)  # Doubles dimensions (64→128→256)
        self.dec3 = ConvBlock(192, 64)     # Skip connection: 128 + 64 = 192 channels
        self.dec2 = ConvBlock(96, 32)      # Skip connection: 64 + 32 = 96 channels
        self.final = nn.Conv2d(32, 1, 1)   # Final 1×1 conv → 1 channel output

    def forward(self, x):
        e1 = self.enc1(x)                 # Encode: learn local features
        e2 = self.enc2(self.pool(e1))      # Encode deeper: learn area features
        e3 = self.enc3(self.pool(e2))      # Encode deepest: learn regional features
        d3 = self.up(e3)                   # Decode: upsample
        d3 = torch.cat([d3, e2], dim=1)    # SKIP CONNECTION: combine with encoder
        # WHY skip connections: Without them, the decoder "forgets" fine details.
        # Skip connections pass the detailed spatial info from encoder directly to decoder.
        d3 = self.dec3(d3)
        d2 = self.up(d3)
        d2 = torch.cat([d2, e1], dim=1)    # Another skip connection
        d2 = self.dec2(d2)
        return self.final(d2)              # Output: 256×256×1 refined susceptibility
```

#### Patch Dataset (Lines 95–171) — How Input is Read

```python
class RasterPatchDataset(Dataset):
    def __init__(self, sus_path, slope_path, dem_path, patch=256, stride=128):
        # LINE 105-107: Open ALL THREE rasters and keep them open for fast reading
        self.sus = rasterio.open(sus_path)     # Channel 1: ML susceptibility
        self.slope = rasterio.open(slope_path) # Channel 2: slope steepness
        self.dem = rasterio.open(dem_path)      # Channel 3: elevation

        # LINE 118-121: Pre-compute all 256×256 windows at 128-pixel stride
        # WHY: Stride=128 with Patch=256 means 50% overlap between neighbors.
        # This ensures no pixel is at the edge of only one patch.
        # Total patches: ~702 windows for typical Kerala rasters
        self.windows = []
        for y in range(0, self.H - patch + 1, stride):
            for x in range(0, self.W - patch + 1, stride):
                self.windows.append((x, y))

    def __getitem__(self, idx):
        x, y = self.windows[idx]
        win = Window(x, y, self.patch, self.patch)

        # LINE 128: Read one 256×256 patch from the susceptibility raster
        sus = self.sus.read(1, window=win).astype(np.float32)

        # LINE 137-138: Read corresponding patches from slope and DEM rasters
        slope = self.slope.read(1, window=slope_win).astype(np.float32)
        dem = self.dem.read(1, window=dem_win).astype(np.float32)

        # LINE 148-155: Normalize each channel to 0–1 range
        # WHY: Neural networks train much better when all inputs are in similar ranges.
        def norm(arr):
            mn, mx = arr.min(), arr.max()
            if mx - mn == 0:
                return np.zeros_like(arr)
            return (arr - mn) / (mx - mn)

        # LINE 162-163: Stack into 3-channel tensor (same as RGB image)
        inp = np.stack([norm(sus), norm(slope), norm(dem)], axis=0)  # Shape: (3, 256, 256)
        tgt = sus_n[np.newaxis, :, :]   # Target = the susceptibility (what we're refining)

        return torch.from_numpy(inp), torch.from_numpy(tgt)
```

#### Training Loop (Lines 212–247)

```python
# LINE 222: Combined loss = L1 smoothness + edge preservation
loss = loss_fn(pred, yb) + 0.1 * edge_loss(pred, yb)
# L1Loss: Makes the predicted map close to the original susceptibility values
# edge_loss: Uses Sobel filters to detect edges/boundaries and preserve them
# WHY both: L1 alone would over-smooth everything. Edge loss keeps sharp boundaries.
```

#### Full-Image Inference with Overlap Averaging (Lines 260–318)

```python
# LINE 266-267: Two arrays — one accumulates predictions, one counts overlaps
out_arr = np.zeros((H, W), dtype=np.float32)    # Sum of predictions
count_arr = np.zeros((H, W), dtype=np.float32)   # How many times each pixel was predicted

# LINE 270-308: Slide a 256×256 window across the entire image
with torch.no_grad():  # No gradient computation = faster inference
    for y in range(0, H - 256 + 1, 128):       # Slide vertically with stride 128
        for x in range(0, W - 256 + 1, 128):   # Slide horizontally with stride 128
            # Read patch, normalize, run through model
            pred_patch = model(input_tensor).cpu().numpy()[0, 0, :, :]

            # LINE 307-308: Accumulate predictions with overlap
            out_arr[y:y+256, x:x+256] += pred_patch   # Add prediction
            count_arr[y:y+256, x:x+256] += 1.0         # Count this contribution

# LINE 312: Average overlapping predictions
# WHY: Each pixel is predicted 2–4 times from different overlapping patches.
# Averaging removes edge artifacts and gives smoother transitions.
composed = out_arr / count_arr
composed = np.clip(composed, 0.0, 1.0)   # Ensure values stay in 0–1 range

# LINE 318-319: Save as GeoTIFF with same metadata as input
with rasterio.open(OUT_TIF, "w", **meta) as dst:
    dst.write(composed.astype(np.float32), 1)
# ◀ OUTPUT: backend/rasters/susceptibility_dl.tif (~55 MB)
```

### Output

| Output | Path | Description | Used By |
|--------|------|-------------|---------|
| **susceptibility_dl.tif** | `backend/rasters/susceptibility_dl.tif` | Spatially refined probability map (0.0–1.0), smoother boundaries | Step 5 |
| **unet_refiner.pth** | `backend/rasters/unet_refiner.pth` | Saved U-Net model weights for future inference | — |

---

## Step 5 — Runout Tracing & Hazard Fusion (`generate_runout_and_fuse.py`)

### Significance

> **Why this file exists:** Knowing *where* a landslide starts is only half the problem. We also need to know *where the debris flows to*. This script uses the D8 flow direction algorithm to trace how landslide debris would travel downhill from failure zones, creating transit and deposition zones. The final output is a **complete hazard map** showing every type of danger zone.

### Where Input is Taken

```python
# LINE 28-33: Input rasters
RASTER_DIR = r"C:\coding\Slipsense\backend\rasters"
DEM_TIF = os.path.join(RASTER_DIR, "DEM_filled_75.tif")               # ◀ INPUT: elevation
SUS_DL_TIF = os.path.join(RASTER_DIR, "susceptibility_dl.tif")        # ◀ INPUT: from Step 4
FLOW_ACC_TIF = os.path.join(RASTER_DIR, "Flow_Accumulation_clean75.tif") # ◀ INPUT: water flow
SLOPE_TIF = os.path.join(RASTER_DIR, "slope75.tif")                    # ◀ INPUT: steepness

# LINE 35-38: Four outputs
OUT_RUNOUT_GEOJSON = os.path.join(RASTER_DIR, "runout_paths.geojson")  # ◀ OUTPUT 1
OUT_TRANSIT = os.path.join(RASTER_DIR, "transit_mask.tif")             # ◀ OUTPUT 2
OUT_DEPOSITION = os.path.join(RASTER_DIR, "deposition_mask.tif")       # ◀ OUTPUT 3
OUT_FUSED = os.path.join(RASTER_DIR, "hazard_fused.tif")              # ◀ OUTPUT 4

# LINE 41-46: Thresholds that control zone classification
THRESH_HIGH = 0.70             # Susceptibility ≥ 0.70 = failure zone
STREAM_ACC_THRESH = 5000       # Flow accumulation ≥ 5000 = stream (stop tracing)
SLOPE_DEPOSITION_MAX = 15      # Slope ≤ 15° = debris can deposit
TRANSIT_BUFFER_PIX = 5         # Buffer 5 pixels around runout paths
MIN_SOURCE_PIXELS = 10         # Remove noise clusters smaller than 10 pixels
```

### Key Code Walkthrough

#### Step 5a: Load data (Lines 88–105)

```python
# Read all four input rasters into NumPy arrays
with rasterio.open(DEM_TIF) as src:
    dem = src.read(1).astype(np.float32)       # Elevation grid

with rasterio.open(SUS_DL_TIF) as src:
    sus = src.read(1).astype(np.float32)       # DL susceptibility (0.0–1.0)
    sus_profile = src.profile.copy()           # Save metadata for output

with rasterio.open(FLOW_ACC_TIF) as src:
    flow_acc = src.read(1).astype(np.float32)  # Water accumulation

with rasterio.open(SLOPE_TIF) as src:
    slope = src.read(1).astype(np.float32)     # Terrain steepness
```

#### Step 5b: Compute D8 Flow Direction (Lines 113–143)

```python
# WHY: For every pixel, we need to know "which direction does water/debris flow?"
# D8 means "8 directions" — for each pixel, check all 8 neighbors and pick
# the one with the steepest downhill slope. That's where material flows.

# D8 direction encoding using bitmasks:
#   NW(32)  N(64)  NE(128)
#   W(16)    ●      E(1)
#   SW(8)   S(4)   SE(2)

fd_np = np.zeros((h, w), dtype=np.int32)   # Flow direction grid

for r in range(h):           # For every row (pixel)
    for c in range(w):       # For every column (pixel)
        curr_elev = dem[r, c]    # Current pixel's elevation
        max_slope = 0            # Track the steepest downhill
        best_dir = 0

        for dr, dc, bitmask in d8_offsets:  # Check all 8 neighbors
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                neighbor_elev = dem[nr, nc]
                dist = np.sqrt(dr**2 + dc**2)        # 1.0 for cardinal, 1.414 for diagonal
                slope_val = (curr_elev - neighbor_elev) / dist  # Drop / distance
                if slope_val > max_slope and neighbor_elev < curr_elev:
                    max_slope = slope_val
                    best_dir = bitmask   # This neighbor is steepest downhill

        fd_np[r, c] = best_dir   # Store the winning direction
```

#### Step 5c: Identify Failure Source Zones (Lines 145–171)

```python
# LINE 147: Pixels with susceptibility ≥ 0.70 are potential failure zones
source_mask = (sus >= THRESH_HIGH).astype(np.uint8)

# LINE 151: Remove tiny noise splotches using morphological opening
# WHY: Single noisy pixels with high susceptibility are probably errors.
source_mask = ndi.binary_opening(source_mask, structure=np.ones((3,3)))

# LINE 154-160: Find connected groups and discard groups < 10 pixels
# WHY: A real landslide source area spans multiple pixels. If only 3 pixels
# have high susceptibility, it's likely noise, not a real source zone.
labeled, ncomp = ndi.label(source_mask)          # Label each connected group
component_sizes = np.bincount(labeled.ravel())   # Count pixels per group
keep_labels = np.where(component_sizes >= 10)[0].tolist()  # Keep groups ≥ 10 pixels

# LINE 164-171: Get the centroid of each kept source zone
# WHY: We trace one runout path per source zone, starting from its center point.
sources = []
for lab in keep_labels:
    coords = np.column_stack(np.where(labeled == lab))
    r_mean = int(np.round(coords[:, 0].mean()))  # Average row = centroid row
    c_mean = int(np.round(coords[:, 1].mean()))  # Average col = centroid col
    sources.append((r_mean, c_mean))
```

#### Step 5d: Trace Runout Paths (Lines 180–210)

```python
# For each source centroid, follow the D8 flow direction downhill
for (r, c) in sources:
    path = [(c, r)]       # Start at the source centroid
    rr, cc = r, c

    while True:
        val = int(fd_np[rr, cc])       # What direction does this pixel point?
        off = fd_to_offset(val)        # Convert bitmask → (dr, dc) movement

        if off is None:
            break   # No downhill direction = flat or pit = stop

        nr, nc = rr + off[0], cc + off[1]  # Move to next pixel

        if not (0 <= nr < h and 0 <= nc < w):
            break   # Reached the edge of the raster = stop

        path.append((nc, nr))  # Record this pixel in the path

        if flow_acc[nr, nc] >= STREAM_ACC_THRESH:
            break   # Reached a stream/river = debris stops here

        rr, cc = nr, nc     # Continue following the flow

    # Convert pixel coordinates to real-world coordinates using the raster's transform
    map_coords = [((col * transform.a) + transform.c,
                   (row * transform.e) + transform.f) for (col, row) in path]
    runout_lines.append(LineString(map_coords))  # Save as Shapely LineString geometry
```

#### Step 5e: Create Zone Masks & Fuse (Lines 255–271)

```python
# TRANSIT ZONE: Buffer around the runout paths
# WHY: The runout path itself is a thin line. But debris spreads out laterally
# as it flows, so we dilate (expand) the line by 5 pixels in all directions.
struct = np.ones((11, 11), dtype=bool)   # 11×11 = 5-pixel radius each side
transit_mask = binary_dilation(runout_mask, structure=struct).astype(np.uint8)

# DEPOSITION ZONE: Where debris comes to rest
# WHY: Debris stops where the slope flattens out AND water accumulates (valleys/basins).
deposition_cond = (flow_acc >= 10000) & (slope <= 15)   # Low slope + high accumulation
deposition_mask[deposition_cond & (transit_mask == 1)] = 1   # Only within transit area

# FUSED HAZARD MAP: Combine all zones into single coded raster
# Value 3 = FAILURE (where the landslide starts — the most dangerous)
# Value 2 = TRANSIT (where debris flows through — dangerous)
# Value 1 = DEPOSITION (where debris settles — moderate danger)
# Value 0 = SAFE (no hazard)
fused = np.zeros_like(sus, dtype=np.uint8)
fused[sus >= 0.70] = 3                               # Failure zones get highest code
fused[(transit_mask == 1) & (fused == 0)] = 2         # Transit gets code 2 (if not already failure)
fused[(deposition_mask == 1) & (fused == 0)] = 1      # Deposition gets code 1 (if not already transit/failure)
```

### Outputs

| Output | Path | Format | Description |
|--------|------|--------|-------------|
| **hazard_fused.tif** | `backend/rasters/hazard_fused.tif` | GeoTIFF uint8 (values 0–3) | 0=Safe, 1=Deposition, 2=Transit, 3=Failure |
| **runout_paths.geojson** | `backend/rasters/runout_paths.geojson` | GeoJSON LineStrings in WGS84 | Debris flow path lines for map overlay |
| **transit_mask.tif** | `backend/rasters/transit_mask.tif` | GeoTIFF uint8 (0 or 1) | Binary mask: 1 = transit zone |
| **deposition_mask.tif** | `backend/rasters/deposition_mask.tif` | GeoTIFF uint8 (0 or 1) | Binary mask: 1 = deposition zone |

---

## Step 6 — Serving Rasters to the Frontend

### Significance

> **Why this step exists:** The raster files from Steps 3–5 are raw GeoTIFF files that can't be displayed directly in a web browser. The backend server reads these files and converts them into PNG map tiles on-the-fly whenever the frontend requests them.

### `config.py` — Where Rasters Are Registered

```python
# LINE 6-13: Each raster gets a "layer name" used in the URL
# WHY: The frontend requests tiles by name, e.g., /tiles/hazard_fused/10/523/342.png
RASTERS = {
    "susceptibility_ml": BASE_DIR / "rasters" / "susceptibility_ml.tif",   # From Step 3
    "susceptibility_dl": BASE_DIR / "rasters" / "susceptibility_dl.tif",   # From Step 4
    "hazard_fused":      BASE_DIR / "rasters" / "hazard_fused.tif",        # From Step 5
    "transit":           BASE_DIR / "rasters" / "transit_mask.tif",        # From Step 5
    "deposition":        BASE_DIR / "rasters" / "deposition_mask.tif",     # From Step 5
}
```

### `tiles.py` — Converting Rasters to PNG Tiles

```python
@router.get("/tiles/{layer}/{z}/{x}/{y}.png")
def tile(layer, z, x, y):
    # LINE 93-94: Look up the raster file path from config
    raster_path = str(RASTERS[layer])

    # LINE 113-115: Use rio-tiler to read just the requested tile area
    # WHY: The full raster is ~55 MB. We only read the small region
    # matching the tile coordinates (z=zoom, x=column, y=row).
    with COGReader(raster_path) as cog:
        data, mask = cog.tile(x_i, y_i, z_i)   # Returns ~256×256 pixel array

        # LINE 122-127: Special handling for hazard_fused — colorize by zone code
        if layer == "hazard_fused":
            band = data[:, :, 0].astype(np.uint8)
            img_arr = colorize_hazard(band)     # Convert codes 0–3 to RGB colors
            img = Image.fromarray(img_arr, mode="RGB")

        # Save as PNG and return to browser
        img.save(buf, format='PNG')
        return Response(content=buf.getvalue(), media_type='image/png')

# Colorization function:
def colorize_hazard(arr):
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[arr == 1] = [255, 255, 0]      # Deposition → Yellow
    rgb[arr == 2] = [255, 165, 0]      # Transit → Orange
    rgb[arr == 3] = [220, 38, 38]      # Failure → Red
    # arr == 0 → stays [0,0,0] = black/transparent (Safe)
    return rgb
```

### What the Frontend Requests

| Layer Name | URL Pattern | Display |
|------------|-------------|---------|
| ML Susceptibility | `/tiles/susceptibility_ml/{z}/{x}/{y}.png` | Grayscale heatmap |
| DL Susceptibility | `/tiles/susceptibility_dl/{z}/{x}/{y}.png` | Grayscale heatmap (smoother) |
| Hazard Fused | `/tiles/hazard_fused/{z}/{x}/{y}.png` | Red/Orange/Yellow colored zones |
| Runout Paths | `/rasters/runout_paths.geojson` (static file) | GeoJSON lines on map |

---

## Complete Input/Output Chain Summary

| Step | Script | Takes Input From | Produces Output |
|------|--------|-----------------|-----------------|
| 1 | `data_preparation.py` | 3 CSVs + 9 terrain rasters | `merged_landslide_data.csv` (800 rows) |
| 2 | `enhanced_model.py` | `merged_landslide_data.csv` | `enhanced_model.pkl` + `enhanced_scaler.pkl` |
| 3 | `generate_susceptibility_map.py` | `.pkl` files + 9 terrain rasters | `susceptibility_ml.tif` |
| 4 | `unet_refine.py` | `susceptibility_ml.tif` + slope + DEM | `susceptibility_dl.tif` |
| 5 | `generate_runout_and_fuse.py` | `susceptibility_dl.tif` + DEM + flow_acc + slope | `hazard_fused.tif` + `runout_paths.geojson` + masks |
| 6 | Backend tile server | All `.tif` files | PNG tiles → Frontend map |

---

*Document prepared for academic presentation and project documentation.*
*Last updated: February 17, 2026*
