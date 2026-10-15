"""Create the first admin account (public sign-up only creates patients).

Usage (from backend/):  python -m scripts.create_admin admin@clinic.com "Admin Name" <password>
"""

import asyncio
import sys

from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_db
from app.schemas.user import Role
from app.services.user_service import EmailAlreadyRegistered, create_user


async def main(email: str, full_name: str, password: str) -> None:
    await connect_to_mongo()
    try:
        await create_user(get_db(), email=email, full_name=full_name, password=password, role=Role.ADMIN)
        print(f"Admin {email} created")
    except EmailAlreadyRegistered:
        print(f"{email} is already registered")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    asyncio.run(main(*sys.argv[1:]))
