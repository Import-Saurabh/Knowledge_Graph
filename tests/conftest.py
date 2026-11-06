"""Pytest configuration and global fixtures for test isolation."""
import os
import tempfile
from pathlib import Path
import pytest

from server.config import settings

# Disable background scheduler during all test executions to prevent live network calls
settings.scheduler_enabled = False
# Use in-memory or disable kuzu for general tests unless explicitly tested
settings.use_kuzu = False

# Isolate all tests into a temporary database so production data/driftforge.db is never polluted
_test_db_file = tempfile.NamedTemporaryFile(suffix="_test_global.db", delete=False)
_test_db_path = Path(_test_db_file.name)
_test_db_file.close()

settings.db_path = _test_db_path

from server.database import init_db, close_db_connection
init_db(_test_db_path)


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_db():
    yield
    close_db_connection()
    try:
        if _test_db_path.exists():
            os.remove(_test_db_path)
    except Exception:
        pass
