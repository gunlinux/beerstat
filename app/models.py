from sqlalchemy import Column, Integer, String, DateTime, Float
from datetime import datetime
from app.extansions import db


class Donations(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(30))
    date = Column(DateTime, default=datetime.now)
    value = Column(Float)

    def __repr__(self):
        return f"<Donation(id={self.id}, date={self.date}, value={self.value}, name={self.name})>"
