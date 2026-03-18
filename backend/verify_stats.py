import requests
import sys
import os
from datetime import datetime, timedelta
# Attempt to import jwt from jose, might need install
try:
    from jose import jwt
except ImportError:
    print("python-jose not installed. Please install it.")
    sys.exit(1)

SECRET_KEY = "bit_health_secret_key_2026"
ALGORITHM = "HS256"

def create_token(user_id):
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {"sub": str(user_id), "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def test_endpoint():
    # Assuming the server is running on port 8000
    base_url = "http://127.0.0.1:8000/api/admin/dashboard/usage-history"
    
    # Try user_id 1 for admin
    token = create_token(1)
    headers = {"Authorization": f"Bearer {token}"}
    
    periods = ["this_week", "last_week", "month"]
    
    for period in periods:
        print(f"\n--- Testing period: {period} ---")
        try:
            response = requests.get(f"{base_url}?period={period}", headers=headers)
            if response.status_code == 200:
                data = response.json()
                print(f"Success! Received {len(data)} records.")
                if len(data) > 0:
                    print(f"Sample record 0: {data[0]}")
                    print(f"Sample record -1: {data[-1]}")
            elif response.status_code == 401:
                print("Failed: 401 Unauthorized. User ID 1 might not be admin or exist.")
            else:
                print(f"Failed: {response.status_code} - {response.text}")
        except requests.exceptions.ConnectionError:
            print("Error: Could not connect to server. Is it running on port 8000?")
            return
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_endpoint()
