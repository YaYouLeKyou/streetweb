import os
import requests

def main():
    base_url = os.getenv("BASE_URL", "http://localhost:5000")
    # Test 1: ping to trigger scheduled jobs
    print("Testing /ping endpoint...")
    resp = requests.get(f"{base_url}/ping")
    print("Ping status:", resp.status_code)
    print("Ping response:", resp.text)

if __name__ == "__main__":
    main()