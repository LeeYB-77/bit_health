import json

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app import crud, schemas, models

# 비트별장 기본 설정. 7·8월은 최대 2박3일, 그 외 달은 제한 없음(null).
# 성수기 판정은 "이용 기간이 peak_months와 겹치는지"로 한다.
DEFAULT_VILLA_SETTINGS = {
    "peak_months": [7, 8],
    "peak_max_nights": 2,
    "default_max_nights": None,
    "default_checkin_time": "15:00",
    "default_checkout_time": "11:00",
    "villas": {
        "청평별장": {"address": "", "notice": ""},
        "동비재": {"address": "", "notice": ""},
    },
}


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
            {"name": "ScreenGolf", "type": "golf", "capacity": 1},
            {"name": "청평별장", "type": "villa", "capacity": 20},
            {"name": "동비재", "type": "villa", "capacity": 20},
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

        # 비트별장 기본 설정 (성수기 규칙은 해마다 바뀔 수 있어 설정으로 둔다)
        villa_setting = db.query(models.SystemSetting).filter(
            models.SystemSetting.key == "villa_settings"
        ).first()
        if not villa_setting:
            print("Creating villa_settings")
            db.add(models.SystemSetting(
                key="villa_settings",
                value=json.dumps(DEFAULT_VILLA_SETTINGS, ensure_ascii=False)
            ))
            db.commit()
        else:
            print("villa_settings already exists")
    finally:
        db.close()

if __name__ == "__main__":
    print("Creating initial data")
    init_db()
    print("Initial data created")
