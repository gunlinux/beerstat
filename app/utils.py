from app.models import BeerDonation
from datetime import datetime
from sqlalchemy import func
import sqlalchemy.orm as sa_orm
from sqlalchemy.orm import Session


def insert_donate(data: dict[str, object], session: sa_orm.scoped_session[Session]):
    # Extract values with proper type conversion
    name = str(data.get("name", ""))
    date_str = str(data.get("date", ""))
    value = float(str(data.get("value", 0.0)))

    donation = BeerDonation(
        name=name,
        date=datetime.fromisoformat(date_str),
        value=value,
    )
    session.add(donation)
    session.commit()


def get_sum(session: Session) -> float | None:
    total_value = session.query(func.sum(BeerDonation.value)).scalar()  # pyright: ignore[reportUnknownArgumentType,reportUnknownArgumentType]
    return float(total_value) if total_value is not None else None
