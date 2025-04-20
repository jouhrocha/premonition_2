import sqlite3
import logging
import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class HistoricalDataStorage:
    def __init__(self, db_path: str = 'data/historical_data.db'):
        self.db_path = db_path
        self.conn = None
        self.lock = asyncio.Lock()

    async def initialize(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with self.lock:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS candles_1min (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    timestamp INTEGER,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL
                )
            ''')
            self.conn.commit()

    async def get_all_metadata(self) -> List[Dict[str, Any]]:
        async with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT symbol, timestamp FROM candles_1min")
            rows = cursor.fetchall()
            metadata = [{"symbol": row[0], "timestamp": row[1]} for row in rows]
            return metadata

    async def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
