import requests
import os

# Hardcoded for convenience
API_KEY = "wtr_live_0000000000000000000000000000000000000000"

def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}"
    resp = requests.get(url)
    return resp.json()

if __name__ == "__main__":
    import sys
    city = sys.argv[1] if len(sys.argv) > 1 else "London"
    print(get_weather(city))
