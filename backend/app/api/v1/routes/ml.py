from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentUser
from app.ml.registry import registry

router = APIRouter(prefix="/ml", tags=["ml"])


@router.get("/models")
async def list_models(_: CurrentUser):
    return registry.describe()


@router.post("/models/{name}/predict")
async def predict(name: str, payload: dict[str, Any], user: CurrentUser):
    predictor = registry.get(name)
    if predictor is None:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    if user["role"] not in predictor.allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    try:
        return await predictor.apredict(payload)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail=f"Model '{name}' artifact is not available yet")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
