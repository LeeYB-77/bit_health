from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Remote DB Connection
DATABASE_URL = "postgresql://bit_health_user:bit_health_password@59.10.164.2:5434/bit_health_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def migrate_db():
    db = SessionLocal()
    try:
        print("Starting DB Migration...")
        
        # 1. Add columns to reservations table
        check_col = text("SELECT column_name FROM information_schema.columns WHERE table_name='reservations' AND column_name='participant_count';")
        if not db.execute(check_col).fetchone():
            print("Adding participant_count column...")
            db.execute(text("ALTER TABLE reservations ADD COLUMN participant_count INTEGER DEFAULT 1;"))
        else:
            print("participant_count column already exists.")

        check_col2 = text("SELECT column_name FROM information_schema.columns WHERE table_name='reservations' AND column_name='companions';")
        if not db.execute(check_col2).fetchone():
            print("Adding companions column...")
            db.execute(text("ALTER TABLE reservations ADD COLUMN companions TEXT;"))
        else:
            print("companions column already exists.")

        # 2. Update Gym Capacity
        print("Updating Gym Capacity...")
        # We use raw SQL or models? Let's use raw SQL for simplicity in migration script without importing app models if possible, 
        # but updating capacity is data update.
        # "facilities" table, type='gym', set capacity=15
        db.execute(text("UPDATE facilities SET capacity=15 WHERE type='gym';"))
        
        db.commit()
        print("Migration and Updates Complete.")
        
    except Exception as e:
        print(f"Migration Failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_db()
