import requests
import pandas as pd

# Tessadem API key
API_KEY = "1d42650ec2908ec1f735242b15271cf3adde23b1"  # Replace with your actual API key

# Kasaragod approximate bounding box
min_lon, max_lon = 75.0, 75.5
min_lat, max_lat = 12.3, 12.6

# Define grid resolution (degrees per point)
# Smaller = more points; e.g., 0.001 ~ 100m per point
resolution = 0.001

# Generate grid coordinates
lons = [min_lon + i*resolution for i in range(int((max_lon - min_lon)/resolution)+1)]
lats = [min_lat + i*resolution for i in range(int((max_lat - min_lat)/resolution)+1)]

data = []

for lat in lats:
    for lon in lons:
        url = f"https://tessadem.com/api/elevation?lat={lat}&lon={lon}&key={API_KEY}"
        response = requests.get(url)
        if response.status_code == 200:
            elev = response.json().get("elevation")
            data.append([lon, lat, elev])
        else:
            data.append([lon, lat, None])  # No data

# Convert to DataFrame
df = pd.DataFrame(data, columns=["Longitude", "Latitude", "Elevation"])

# Save CSV
df.to_csv("Kasaragod_Elevation_Tessadem.csv", index=False)
print("CSV saved successfully!")
