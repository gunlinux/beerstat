from flask.testing import FlaskClient
from collections.abc import Generator
from typing import Any
import pytest
import os
from datetime import datetime

from app import create_app
from app.extensions import db


@pytest.fixture()
def test_client() -> Generator[FlaskClient, Any, Any]:
    os.environ["FLASK_ENV"] = "testing"
    app = create_app(testing=True)
    app.config.update(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
    )
    with app.test_client() as client:
        with app.app_context():
            print(type(db.session))
            db.create_all()
        yield client
        with app.app_context():
            db.session.remove()
            db.drop_all()


def test_donate_and_balance_flow(test_client: FlaskClient):
    """Test the complete flow of donating and checking balance, similar to the original test.py"""
    # Test donation
    donation_data = {
        "date": datetime.now().isoformat(),
        "value": 100.5,
        "name": "Cher_cash",
    }

    response = test_client.post(
        "/donate", json=donation_data, content_type="application/json"
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "Success"}

    # Test balance
    response = test_client.get("/balance")

    assert response.status_code == 200
    assert response.get_json() == {"Total": 100.5}
