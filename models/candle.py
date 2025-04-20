# models/candle.py
from dataclasses import dataclass
from typing import Dict, Any
from datetime import datetime

@dataclass
class Candle:
    """Clase para representar una vela de trading"""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convierte la vela a un diccionario
        
        Returns:
            Diccionario con los datos de la vela
        """
        return {
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'datetime': datetime.fromtimestamp(self.timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
        }
