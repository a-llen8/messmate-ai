import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.models import User, UserRole

def create_admin():
    db = SessionLocal()
    try:
        email = input("Admin email: ")
        name  = input("Admin name: ")
        password = input("Admin password: ")

        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print("User already exists.")
            return

        admin = User(
            supabase_uid = "local-admin",
            email        = email,
            name         = name,
            role         = UserRole.admin,
            is_super     = True,
            is_active    = True,
        )
        db.add(admin)
        db.commit()
        print(f"Admin created: {email}")

    finally:
        db.close()

if __name__ == "__main__":
    create_admin()