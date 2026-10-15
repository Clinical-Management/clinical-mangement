from typing import Annotated

from bson import ObjectId
from pydantic import BeforeValidator

# Mongo ObjectIds are exposed to the API as plain strings
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


def parse_object_id(value: str) -> ObjectId | None:
    return ObjectId(value) if ObjectId.is_valid(value) else None
