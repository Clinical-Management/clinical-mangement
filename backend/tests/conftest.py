import os
from datetime import datetime

# Must be set before the app (and its settings) are imported
os.environ["MONGODB_DB"] = "clinical_management_test"

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.config import settings


def _mongo_available() -> bool:
    try:
        MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1000).admin.command("ping")
        return True
    except PyMongoError:
        return False


@pytest.fixture
def client():
    """App client backed by a fresh test database (skipped if Mongo is not running)."""
    if not _mongo_available():
        pytest.skip("MongoDB not available")
    sync = MongoClient(settings.mongodb_uri)
    sync.drop_database(settings.mongodb_db)

    from app.main import app

    with TestClient(app) as c:
        yield c
    sync.drop_database(settings.mongodb_db)


@pytest.fixture
def make_user(client):
    """Create a user directly in the DB and return auth headers for it."""
    from app.core.security import create_access_token
    from app.services.user_service import hash_password

    db = MongoClient(settings.mongodb_uri)[settings.mongodb_db]

    def _make(role: str, email: str | None = None) -> dict:
        email = email or f"{role}-{db.users.count_documents({})}@test.com"
        uid = db.users.insert_one(
            {
                "email": email,
                "full_name": role.title(),
                "password_hash": hash_password("password123"),
                "role": role,
                "is_active": True,
                "created_at": datetime.now(),
            }
        ).inserted_id
        return {"Authorization": f"Bearer {create_access_token(str(uid), role)}"}

    return _make
