import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.dependencies import get_db
from app.core.security import create_access_token
from app.core.config import settings
from app.main import app
from app.utils.seed import seed_db_data

settings.ENVIRONMENT = "production"

TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    seed_db_data(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_auth_headers():
    token = create_access_token(1)  # Admin user seeded with id 1
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def creator_auth_headers():
    token = create_access_token(2)  # Creator user seeded with id 2
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def freelancer_auth_headers():
    token = create_access_token(4)  # Freelancer user seeded with id 4
    return {"Authorization": f"Bearer {token}"}
