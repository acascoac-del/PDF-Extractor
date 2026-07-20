"""Punto de entrada para Vercel Serverless Functions.

Vercel espera una variable llamada 'app' que sea una instancia de ASGI/WSGI.
"""
from app.main import app  # noqa: F401
