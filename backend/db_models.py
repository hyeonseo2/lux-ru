from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime
import uuid

def generate_uuid():
    return str(uuid.uuid4())

class InstrumentDB(Base):
    __tablename__ = "instruments"

    id = Column(String, primary_key=True, default=generate_uuid)
    market = Column(String)
    symbol = Column(String, unique=True, index=True)
    name_ko = Column(String)
    name_en = Column(String)
    instrument_type = Column(String) # stock, etf, bond, cash
    currency = Column(String)
    country = Column(String)
    sector = Column(String, nullable=True)
    issuer = Column(String, nullable=True)

class HoldingDB(Base):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_symbol = Column(String, index=True) # The ETF symbol
    holding_symbol = Column(String, index=True) # The stock/etf it holds
    holding_name = Column(String)
    weight = Column(Float)
    currency = Column(String)
    country = Column(String)
    sector = Column(String)
    as_of_date = Column(DateTime, default=datetime.utcnow)
