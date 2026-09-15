"""
tests/conftest.py — Shared pytest configuration.

Sets asyncio_mode so @pytest.mark.asyncio tests work without per-file config.
"""
import pytest


# pytest-asyncio >= 0.21 requires explicit asyncio_mode.
# 'auto' marks all async tests automatically.
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
