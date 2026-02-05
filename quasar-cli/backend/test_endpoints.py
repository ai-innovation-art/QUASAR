import requests
import time
import sys

BASE_URL = "http://localhost:8000"

def wait_for_server(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(f"{BASE_URL}/", timeout=1)
            print("✅ Server is up!")
            return True
        except requests.ConnectionError:
            time.sleep(1)
            print("Waiting for server...")
    return False

def test_endpoints():
    if not wait_for_server():
        print("❌ Server failed to start")
        sys.exit(1)

    print("\nTesting /health...")
    try:
        resp = requests.get(f"{BASE_URL}/api/health")
        if resp.status_code == 200:
            print(f"✅ /health passed: {resp.json()}")
        else:
            print(f"❌ /health failed: {resp.text}")
    except Exception as e:
        print(f"❌ /health error: {e}")

    print("\nTesting /api/agent/models/list...")
    try:
        resp = requests.get(f"{BASE_URL}/api/agent/models/list")
        if resp.status_code == 200:
            print(f"✅ /models/list passed. Found {len(resp.json().get('models', []))} models.")
        else:
            print(f"❌ /models/list failed: {resp.text}")
    except Exception as e:
        print(f"❌ /models/list error: {e}")

if __name__ == "__main__":
    test_endpoints()
