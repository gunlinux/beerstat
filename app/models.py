import typing
from sqlalchemy import Column, Integer, String, DateTime, Float
from datetime import datetime
from app.extensions import db


class BeerDonation(db.Model):
    __tablename__ = 'donations'
    id = Column(Integer, primary_key=True)
    name = Column(String(30))
    date = Column(DateTime, default=datetime.now)
    value = Column(Float)  # pyright: ignore[reportUnknownVariableType]

    @typing.override
    def __repr__(self) -> str:
        return f"<Donation(id={self.id}, date={self.date}, value={self.value}, name={self.name})>"
