"""Shared test fixtures."""
import os

# Set test env vars before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/1")
