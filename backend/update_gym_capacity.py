from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import models

# Use Remote DB via forwarded port or known IP (if accessible)
# Since we run this locally and deploy.py sets up context, 
# we can rely on the fact that 59.10.164.2:5434 is mapped to DB.
DATABASE_URL = "postgresql://bit_health_user:bit_health_password@59.10.164.2:5434/bit_health_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def update_capacity():
    db = SessionLocal()
    try:
        gym = db.query(models.Facility).filter(models.Facility.type == "gym").first()
        if gym:
            print(f"Updating Gym capacity from {gym.capacity} to 15")
            gym.capacity = 15
            db.commit()
            print("Successfully updated Gym capacity.")
        else:
            print("Gym facility not found!")
    except Exception as e:
        print(f"Error updating capacity: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_capacity()
