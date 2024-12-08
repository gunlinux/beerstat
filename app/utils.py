from app.extansions import db
from app.models import Donations
from datetime import datetime
from sqlalchemy import func


def insert_donate(data, session):
    donation = Donations(
        date=datetime.fromisoformat(data.get('date')),
        value=data.get('value'),
        name=data.get('name')
    )
    session.add(donation)
    session.commit()

def get_sum(session):
    total_value = db.session.query(func.sum(Donations.value)).scalar()
    return total_value
