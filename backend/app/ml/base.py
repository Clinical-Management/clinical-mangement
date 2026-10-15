import asyncio
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"


class BasePredictor(ABC):
    """One ML/DL model served by the API.

    Subclasses set `name`, `artifact` (file in app/ml/artifacts) and implement
    `load()` and `predict()`. The model is loaded lazily on first use so the
    server starts fast and only pays memory for models that are actually called.
    """

    name: str
    description: str = ""
    artifact: str
    allowed_roles: frozenset[str] = frozenset({"doctor", "admin"})

    def __init__(self) -> None:
        self._model: Any = None
        self._lock = threading.Lock()

    @property
    def artifact_path(self) -> Path:
        return ARTIFACTS_DIR / self.artifact

    @property
    def model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    if not self.artifact_path.exists():
                        raise FileNotFoundError(self.artifact_path)
                    self._model = self.load()
        return self._model

    @abstractmethod
    def load(self) -> Any: ...

    @abstractmethod
    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate `payload`, run inference with `self.model`, return a JSON-able dict.
        Raise ValueError for bad input."""

    async def apredict(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Inference is CPU-bound; keep it off the event loop
        return await asyncio.to_thread(self.predict, payload)

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "available": self.artifact_path.exists(),
            "loaded": self._model is not None,
        }
