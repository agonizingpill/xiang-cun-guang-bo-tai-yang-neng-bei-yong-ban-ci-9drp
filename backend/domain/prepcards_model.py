from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, String, Table

from core.db import metadata


prepcards = Table('prepcards', metadata,
    Column('code', String(64), primary_key=True),
    Column('airslot', String(160), ForeignKey('airslots.code'), nullable=False),
    Column('meter', String(160), nullable=False),
    Column('token', String(64), nullable=False, unique=True),
    Column('clear_wh', Float, nullable=True),
    Column('cloudy_wh', Float, nullable=True),
    Column('state', String(160), nullable=False),
    Column('receipt', String(160), nullable=True, unique=True),
    Column('claimed_weather', String(16), nullable=True),
    Column('claimed_wh', Float, nullable=True),
    CheckConstraint("state in ('待领用','已领用')"),
)
