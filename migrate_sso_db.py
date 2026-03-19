from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Remote DB Connection
DATABASE_URL = "postgresql://bit_health_user:bit_health_password@59.10.164.2:5434/bit_health_db"

import os

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def migrate_sso_db():
    db = SessionLocal()
    try:
        print("Starting SSO DB Migration...")
        
        # 1. Add sub and email columns to users table
        check_col = text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='sub';")
        if not db.execute(check_col).fetchone():
            print("Adding sub column...")
            db.execute(text("ALTER TABLE users ADD COLUMN sub VARCHAR UNIQUE;"))
            db.execute(text("CREATE UNIQUE INDEX ix_users_sub ON users(sub);"))
        else:
            print("sub column already exists.")

        check_col2 = text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='email';")
        if not db.execute(check_col2).fetchone():
            print("Adding email column...")
            db.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR;"))
        else:
            print("email column already exists.")

        # 2. Make birth_date nullable (PostgreSQL syntax)
        print("Relaxing birth_date NOT NULL constraint...")
        db.execute(text("ALTER TABLE users ALTER COLUMN birth_date DROP NOT NULL;"))

        db.commit()
        print("Migration Complete.")
        
    except Exception as e:
        print(f"Migration Failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_sso_db()
