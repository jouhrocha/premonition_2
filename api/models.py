from pydantic import BaseModel
from typing import Optional

class Trade(BaseModel):
    pair: str
    direction: str
    size: float
    entry_price: float
    exit_price: float
    pnl: float
    reason: str
    time: str

class Position(BaseModel):
    pair: str
    direction: str
    size: float
    entry_price: float
    sl: float
    tp1: float
    tp2: Optional[float] = None
    current_price: float
    pnl: float
    pnl_pct: float

class OrderParams(BaseModel):
    pair: str
    type: str
    ordertype: str
    volume: float
    price: Optional[float] = None

class OrderResult(BaseModel):
    status: str
    txid: Optional[str] = None
    error: Optional[str] = None