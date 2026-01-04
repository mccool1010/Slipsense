# Original Flask app backed up as legacy_flask_app.py
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
import joblib
import requests

landslide_model = joblib.load("../ml_models/landslide_model.pkl")
flood_model = joblib.load("../ml_models/flood_model.pkl")


risk_labels = {0: "Low", 1: "Moderate", 2: "High"}
OPENWEATHERMAP_API_KEY = "f4b4c6deaacfaacd2060175e4697b694" 

def get_rainfall_from_openweathermap(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}&units=metric"
        response = requests.get(url)
        data = response.json()

        # Rainfall in last 1h (fallback 0)
        rain = data.get("rain", {}).get("1h", 0)
        return rain
    except:
        return 0 
@app.route('/get-rainfall', methods=['POST'])
def get_rainfall():
    data = request.get_json()
    lat = data.get("lat")
    lon = data.get("lon")

    if lat is None or lon is None:
        return jsonify({"error": "Missing lat/lon"}), 400

    rain = get_rainfall_from_openweathermap(lat, lon)
    return jsonify({"rainfall": rain})

@app.route('/')
def home():
    return jsonify({"message": "ResQ-AI Backend is running!"})
ALERTS = [
    {"lat": 12.9716, "lng": 77.5946, "type": "Landslide", "risk": "Low"},
    {"lat": 15.3173, "lng": 75.7139, "type": "Flood", "risk": "High"},
    {"lat": 17.3850, "lng": 78.4867, "type": "Landslide", "risk": "Moderate"},
]

@app.route('/alerts', methods=['GET'])
def get_alerts():
    return jsonify({"alerts": ALERTS})
@app.route('/predict-landslide', methods=['POST'])
def predict_landslide():
    data = request.get_json()
    slope = data.get('slope')
    rainfall = data.get('rainfall')

    if slope is None or rainfall is None:
        return jsonify({'error': 'Missing slope or rainfall'}), 400

    try:
        prediction = landslide_model.predict([[slope, rainfall]])[0]
        risk = risk_labels[prediction]
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Return a fixed location for now
    return jsonify({
        'risk_level': risk,
        'location': {'lat': 12.9716, 'lng': 77.5946}
    })

@app.route('/predict-flood', methods=['POST'])
def predict_flood():
    data = request.get_json()
    rainfall = data.get('rainfall')
    elevation = data.get('elevation')
    river_distance = data.get('river_distance')

    if None in [rainfall, elevation, river_distance]:
        return jsonify({'error': 'Missing flood features'}), 400

    try:
        prediction = flood_model.predict([[rainfall, elevation, river_distance]])[0]
        risk = risk_labels[prediction]
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'risk_level': risk})


if __name__ == '__main__':
    app.run(debug=True)
