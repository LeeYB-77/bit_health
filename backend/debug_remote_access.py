import requests
import json
import time

BASE_URL = "http://59.10.164.2:8002"

def login(name, birth_date):
    url = f"{BASE_URL}/api/auth/login"
    try:
        response = requests.post(url, json={"name": name, "birth_date": birth_date})
        if response.status_code == 200:
            return response.json()
        print(f"Login failed: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def get_stats(token):
    url = f"{BASE_URL}/api/admin/dashboard/stats"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        print(f"Stats failed: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Stats error: {e}")
        return None

def access_gym(token):
    url = f"{BASE_URL}/api/gym/access"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        print(f"Gym Access failed: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Gym Access error: {e}")
        return None

def access_golf(token):
    url = f"{BASE_URL}/api/golf/access"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        print(f"Golf Access failed: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Golf Access error: {e}")
        return None

def debug_remote():
    print("--- Debugging Remote Access ---")
    
    # 1. Login
    print("Logging in as admin...")
    token_data = login("admin", "000000")
    if not token_data:
        return
    token = token_data["access_token"]
    print("Logged in.")
    
    # 2. Get Initial Stats
    stats = get_stats(token)
    if stats:
        print(f"Initial Gym Users: {stats.get('current_gym_users')}")
        print(f"Initial Golf Users: {stats.get('current_golf_users')}")
    
    # 3. Access Gym (In/Out)
    print("\nAttempting Gym Access...")
    res = access_gym(token)
    if res:
        print(f"Gym Result: {res}")
        time.sleep(1)
        stats = get_stats(token)
        if stats:
             print(f"Gym Users after access: {stats.get('current_gym_users')}")
    
    # 4. Access Golf (In/Out)
    print("\nAttempting Golf Access...")
    res = access_golf(token)
    if res:
        print(f"Golf Result: {res}")
        time.sleep(1)
        stats = get_stats(token)
        if stats:
             print(f"Golf Users after access: {stats.get('current_golf_users')}")
    else:
        print("Golf access call returned error (see above).")

if __name__ == "__main__":
    debug_remote()
