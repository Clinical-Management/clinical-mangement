from app.ml.base import BasePredictor


class ModelRegistry:
    def __init__(self) -> None:
        self._predictors: dict[str, BasePredictor] = {}

    def register(self, predictor: BasePredictor) -> None:
        self._predictors[predictor.name] = predictor

    def get(self, name: str) -> BasePredictor | None:
        return self._predictors.get(name)

    def describe(self) -> list[dict]:
        return [p.info() for p in self._predictors.values()]


registry = ModelRegistry()

# Register predictors here as models are added, e.g.:
# from app.ml.predictors.diabetes import DiabetesPredictor
# registry.register(DiabetesPredictor())
