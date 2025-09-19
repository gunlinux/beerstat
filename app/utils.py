from app.extensions import db
from app.models import BeerDonation
from datetime import datetime
from sqlalchemy import func


def insert_donate(data, session):
    donation = BeerDonation(
        date=datetime.fromisoformat(data.get("date")),
        value=data.get("value"),
        name=data.get("name"),
    )
    session.add(donation)
    session.commit()


def get_sum(session):
    total_value = db.session.query(func.sum(BeerDonation.value)).scalar()
    return total_value
