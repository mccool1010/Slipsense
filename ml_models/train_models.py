
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from xgboost import XGBClassifier
import joblib
import os

# Load dataset
df = pd.read_csv('C:/coding/Slipsense/data/landslide - Sheet1 (1).csv')

# Define features & target
X = df.drop(columns=['Landslide', 'id'])
y = df['Landslide']

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Calculate imbalance ratio for scale_pos_weight
neg = sum(y == 0)
pos = sum(y == 1)
imbalance_ratio = neg / pos

print("Imbalance Ratio =", imbalance_ratio)

# Train XGBoost model
xgb = XGBClassifier(
    n_estimators=500,
    learning_rate=0.05,
    max_depth=6,
    subsample=0.8,
    colsample_bytree=0.7,
    objective='binary:logistic',
    scale_pos_weight=imbalance_ratio,  # key for balancing!
    eval_metric='logloss',
    random_state=42
)

xgb.fit(X_train, y_train)

# Predictions
y_pred = xgb.predict(X_test)

# Evaluation
print("Classification Report:\n", classification_report(y_test, y_pred))
print("Confusion Matrix:\n", confusion_matrix(y_test, y_pred))

# Save trained model
model_filename = 'landslide_model_xgb.pkl'
joblib.dump(xgb, model_filename)
print(f"Saved XGBoost model to: {os.path.abspath(model_filename)}")
