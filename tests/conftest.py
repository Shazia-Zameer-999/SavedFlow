import pytest

from app import create_app
from config import TestConfig
from extensions import get_db


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return get_db()


@pytest.fixture(autouse=True)
def _clean_db(app):
    """Ensure each test starts with an empty mongomock database."""
    database = get_db()
    for name in database.list_collection_names():
        database[name].delete_many({})
    yield
