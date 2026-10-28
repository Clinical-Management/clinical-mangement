# Vercel entrypoint (the Python runtime serves the ASGI `app` found here)
from app.main import app  # noqa: F401
