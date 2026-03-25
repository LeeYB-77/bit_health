from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import users, auth, gym, golf, admin

app = FastAPI()

# CORS configuration
origins = [
    "http://localhost:3000",
    "http://localhost:3002", # Host-mapped port
    "http://59.10.164.2:3002",
    "http://59.10.164.2:3000",
    "http://book.bit.kr:3002",
    "http://wc.bit.kr:3002",
    "http://reserve.bit.kr:3002",
    "http://book.bit.kr",
    "http://wc.bit.kr",
    "http://reserve.bit.kr",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables
Base.metadata.create_all(bind=engine)

app.include_router(users.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(gym.router)
app.include_router(golf.router) # Now golf is in __init__? Check first.

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from .database import SessionLocal
from . import models
from datetime import datetime, timedelta
from . import slack_utils

# 스케줄러: 자동 퇴실 및 1시간 전 사전 알림
def scheduled_jobs():
    db = SessionLocal()
    try:
        now = datetime.now()
        # ------------------------------------------------------------------
        # 1. 예약 1시간 전 사전 알림 (Slack)
        # ------------------------------------------------------------------
        golf_facility = db.query(models.Facility).filter(models.Facility.type == "golf").first()
        if golf_facility:
            # 상태가 reserved이고 알림을 받지 않은 미래의 1시간(60분) 이내 예약 조회
            upcoming_reservations = db.query(models.Reservation).join(models.User).filter(
                models.Reservation.facility_id == golf_facility.id,
                models.Reservation.status == "reserved",
                models.Reservation.notified_slack == False,
                models.Reservation.start_time > now,
                models.Reservation.start_time <= now + timedelta(minutes=61)
            ).all()

            for res in upcoming_reservations:
                if res.user and res.user.email:
                    # 예약일시를 'YYYY-MM-DD HH:MM' 형태로 가공
                    start_time_str = res.start_time.strftime("%Y-%m-%d %H:%M")
                    # Slack 알림 발송 시도
                    slack_utils.notify_upcoming_reservation(
                        email=res.user.email,
                        start_time=start_time_str,
                        participant_count=res.participant_count
                    )
                # 알림 여부에 상관없이 (혹은 이메일이 없더라도) 1회성 처리를 위해 True로 변경
                res.notified_slack = True
                print(f"Slack upcoming notification sent for reservation {res.id}")

        # ------------------------------------------------------------------
        # 2. 자동 퇴실 (Auto Checkout)
        # ------------------------------------------------------------------
        active_logs = db.query(models.AccessLog).join(models.Facility).filter(
            models.AccessLog.check_out_time == None
        ).all()
        
        for log in active_logs:
            # Gym: 2 hours limit
            if log.facility.type == "gym":
                if now - log.check_in_time > timedelta(hours=2):
                    log.check_out_time = now
                    print(f"Auto-checked out user {log.user_id} from Gym (Time limit exceeded)")
            
            # Golf: 4 hours limit
            elif log.facility.type == "golf":
                if now - log.check_in_time > timedelta(hours=4):
                    log.check_out_time = now
                    print(f"Auto-checked out user {log.user_id} from Golf (Time limit exceeded)")
        
        db.commit()
    except Exception as e:
        print(f"Auto-checkout job failed: {e}")
        db.rollback()
    finally:
        db.close()

@app.on_event("startup")
def startup_event():
    scheduler = BackgroundScheduler()
    # Run every minute
    scheduler.add_job(scheduled_jobs, CronTrigger(minute='*'))
    scheduler.start()
    print("Scheduler started (Auto-checkout & Slack notifications every minute)")

@app.get("/")
def read_root():
    return {"message": "Welcome to BIT Wellness Center API"}

