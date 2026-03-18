from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app import crud, schemas, models

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if admin exists
        admin_name = "admin"
        admin_birth = "000000"
        
        user = crud.get_user_by_name_and_birth(db, name=admin_name, birth_date=admin_birth)
        if not user:
            print(f"Creating superuser: {admin_name}")
            user_in = schemas.UserCreate(
                name=admin_name,
                birth_date=admin_birth,
                role="admin",
                department="Management"
            )
            crud.create_user(db, user=user_in)
            print("Superuser created")
        else:
            print("Superuser already exists")

        # Initialize Facilities
        facilities = [
            {"name": "Gym", "type": "gym", "capacity": 15},
            {"name": "ScreenGolf", "type": "golf", "capacity": 1}
        ]
        
        for f in facilities:
            facility = db.query(models.Facility).filter(models.Facility.name == f["name"]).first()
            if not facility:
                print(f"Creating facility: {f['name']}")
                new_facility = models.Facility(name=f["name"], type=f["type"], capacity=f["capacity"])
                db.add(new_facility)
                db.commit()
            else:
                print(f"Facility {f['name']} already exists")
    finally:
        db.close()

if __name__ == "__main__":
    print("Creating initial data")
    init_db()
    print("Initial data created")
