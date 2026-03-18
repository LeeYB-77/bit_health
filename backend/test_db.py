import os
import psycopg2
from sqlalchemy import create_engine

# Try default URL from database.py or the one in docker-compose
# Docker compose says: postgresql://bit_health_user:bit_health_password@db:5432/bit_health_db
# Local access should be: postgresql://bit_health_user:bit_health_password@localhost:5434/bit_health_db

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bit_health_user:bit_health_password@localhost:5434/bit_health_db")

try:
    print(f"Testing connection to: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)
    connection = engine.connect()
    print("Connection successful!")
    connection.close()
except Exception as e:
    print(f"Connection failed: {e}")
