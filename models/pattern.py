from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class Pattern:
    id: str
    name: str
    features: Dict[str, Any] = field(default_factory=dict)
    success_count: int = 0
    failure_count: int = 0
    total_occurrences: int = 0
    last_updated: Optional[datetime] = None
    historical_results: List[Dict[str, Any]] = field(default_factory=list)
    direction: str = ""
    confidence: float = 0.0
    price: float = 0.0
    result: str = ""
    profit_loss: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_occurrences == 0:
            return 0.0
        return (self.success_count / self.total_occurrences)*100

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "features": self.features,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_occurrences": self.total_occurrences,
            "success_rate": self.success_rate,
            "last_updated": self.last_updated.timestamp() if self.last_updated else None,
            "historical_results": self.historical_results,
            "direction": self.direction,
            "confidence": self.confidence,
            "price": self.price,
            "result": self.result,
            "profit_loss": self.profit_loss
        }
