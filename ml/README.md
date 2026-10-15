# ML / DL workspace

Training lives here; serving lives in `backend/app/ml/`.

```
ml/
├── data/        raw & processed datasets (git-ignored)
├── notebooks/   exploration / experiments
└── training/    reproducible training scripts + export helpers
```

Workflow:

1. Train in `training/` (or a notebook).
2. Export the model into `backend/app/ml/artifacts/` (`training/export.py`).
   - Classic ML: `joblib` file.
   - Deep learning: export to **ONNX** and serve with `onnxruntime`. Full
     PyTorch/TensorFlow won't fit in Render's free-tier 512 MB RAM.
3. Add a predictor in `backend/app/ml/predictors/` and register it in
   `backend/app/ml/registry.py`.
4. It's then served at `POST /api/v1/ml/models/<name>/predict`.

Setup: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
