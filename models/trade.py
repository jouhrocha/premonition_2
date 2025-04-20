from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum

class TradeStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"

class TradeDirection(Enum):
    LONG = "long"
    SHORT = "short"

@dataclass
class Trade:
    symbol: str
    direction: TradeDirection
    entry_price: float
    amount: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    status: TradeStatus = TradeStatus.PENDING
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    profit_loss: Optional[float] = None

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "amount": self.amount,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "status": self.status.value,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": self.exit_price,
            "profit_loss": self.profit_loss
        }
