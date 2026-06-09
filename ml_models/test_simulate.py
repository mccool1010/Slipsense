"""Test Vonage SMS — direct API call."""
import requests, json

api_key = "df55c592"
api_secret = "2CRRqxnL01RqQwtx"
to_number = "919207499037"

url = "https://rest.nexmo.com/sms/json"
payload = {
    "from": "SlipSense",
    "text": "LANDSLIDE ALERT - SlipSense Test. SMS system verified!",
    "to": to_number,
    "api_key": api_key,
    "api_secret": api_secret
}

r = requests.post(url, json=payload, timeout=10)
result = r.json()
print(json.dumps(result, indent=2))

msgs = result.get("messages", [])
if msgs and msgs[0].get("status") == "0":
    print(f"\nSMS SENT! No trial prefix!")
else:
    error = msgs[0].get("error-text", "Unknown") if msgs else "No response"
    print(f"\nFailed: {error}")
