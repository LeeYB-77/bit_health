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

# Auto-checkout job
def auto_checkout_job():
    db = SessionLocal()
    try:
        # print(f"Running auto-checkout job at {datetime.now()}")
        active_logs = db.query(models.AccessLog).join(models.Facility).filter(
            models.AccessLog.check_out_time == None
        ).all()
        
        now = datetime.now()
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
    scheduler.add_job(auto_checkout_job, CronTrigger(minute='*'))
    scheduler.start()
    print("Scheduler started (Auto-checkout every minute)")

@app.get("/")
def read_root():
    return {"message": "Welcome to BIT Wellness Center API"}

