"""
ASGI entry point for Vercel serverless deployment.

Vercel's Python runtime looks for an `app` variable in this module.
It imports this file and wraps the FastAPI ASGI app with its serverless adapter.
"""

from app.main import app
