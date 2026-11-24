"""Entry point for a production server: gunicorn wsgi:app"""
from app import create_app

app = create_app()
