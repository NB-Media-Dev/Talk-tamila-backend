from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.core.security import hash_password

db = SessionLocal()

existing = db.query(User).filter (User.username == "admin").first()
if existing:
    print("Test user already exists")
else:
    test_user = User(
        username="admin",
        first_name="Admin",
        last_name="User",
        email="admin@talktamila.com",
        mobile_no="99999 99999",
        password=hash_password("admin123"),
        role=UserRole.admin,
    )
    db.add(test_user)
    db.commit()
    print("Test user created: username=admin, password=admin123")

db.close()

