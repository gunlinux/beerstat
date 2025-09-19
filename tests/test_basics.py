import typing
import pytest
import os
from datetime import datetime

from app import create_app
from app import db
from app.models import BeerDonation


@pytest.fixture()
def test_client():
    os.environ["FLASK_ENV"] = "testing"
    app = create_app(testing=True)
    app.config.update(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
    )
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.session.remove()
            db.drop_all()


def test_donate_endpoint_success(test_client) -> None:
    """Test successful donation creation"""
    donation_data = {
        "date": datetime.now().isoformat(),
        "value": 100.5,
        "name": "Test Donor",
    }

    response = test_client.post(
        "/donate", json=donation_data, content_type="application/json"
    )

    assert response.status_code == 200
    assert response.get_json() == {"message": "Success"}


def test_donate_endpoint_invalid_data(test_client):
    """Test donation with invalid data"""
    # Test with missing data
    response = test_client.post("/donate", json={}, content_type="application/json")

    assert response.status_code == 400


def test_donate_endpoint_no_data(test_client):
    """Test donation with no data"""
    response = test_client.post("/donate")

    # Flask returns 415 for unsupported media type when no content-type is specified
    assert response.status_code == 415


def test_balance_endpoint_empty(test_client):
    """Test balance endpoint with no donations"""
    response = test_client.get("/balance")

    assert response.status_code == 200
    assert response.get_json() == {"Total": None}


def test_balance_endpoint_with_donations(test_client):
    """Test balance endpoint with donations"""
    # Add a donation first
    donation_data = {
        "date": datetime.now().isoformat(),
        "value": 50.0,
        "name": "Test Donor",
    }

    response = test_client.post(
        "/donate", json=donation_data, content_type="application/json"
    )

    assert response.status_code == 200

    # Check balance
    response = test_client.get("/balance")

    assert response.status_code == 200
    assert response.get_json() == {"Total": 50.0}


def test_multiple_donations(test_client):
    """Test multiple donations and cumulative balance"""
    donations = [
        {"date": datetime.now().isoformat(), "value": 25.0, "name": "Donor 1"},
        {"date": datetime.now().isoformat(), "value": 75.5, "name": "Donor 2"},
        {"date": datetime.now().isoformat(), "value": 100.0, "name": "Donor 3"},
    ]

    # Add all donations
    for donation in donations:
        response = test_client.post(
            "/donate", json=donation, content_type="application/json"
        )
        assert response.status_code == 200

    # Check total balance
    response = test_client.get("/balance")

    assert response.status_code == 200
    assert response.get_json() == {"Total": 200.5}


def test_donation_model() -> None:
    """Test BeerDonation model creation"""
    donation = BeerDonation(name="Test Donor", value=50.0)

    assert typing.cast("str", donation.name) == "Test Donor"
    assert typing.cast("float", donation.value == 50.0)
    # Date is set when saved to database, not on object creation
    assert donation.date is None  # Before saving to DB
