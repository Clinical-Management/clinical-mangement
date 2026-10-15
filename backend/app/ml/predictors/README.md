# Predictors

One file per model. Each subclasses `app.ml.base.BasePredictor`:

```python
import joblib
import numpy as np

from app.ml.base import BasePredictor

FEATURES = ["glucose", "bmi", "age"]


class DiabetesPredictor(BasePredictor):
    name = "diabetes"
    description = "Diabetes risk (scikit-learn)"
    artifact = "diabetes.joblib"

    def load(self):
        return joblib.load(self.artifact_path)

    def predict(self, payload):
        missing = [f for f in FEATURES if f not in payload]
        if missing:
            raise ValueError(f"Missing features: {missing}")
        x = np.array([[float(payload[f]) for f in FEATURES]])
        return {"probability": float(self.model.predict_proba(x)[0, 1])}
```

Then register it in `app/ml/registry.py`. Artifacts are produced by the training
code in the top-level `ml/` folder and saved to `app/ml/artifacts/`.
