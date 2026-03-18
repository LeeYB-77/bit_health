from app.database import SessionLocal
from app import models

db = SessionLocal()
users = db.query(models.User).all()

print(f"Total Users: {len(users)}")
for user in users:
    print(f"ID: {user.id}, Name: '{user.name}', Birth: '{user.birth_date}', Role: {user.role}")
db.close()
