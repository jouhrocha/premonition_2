import os
import json
import logging
import sqlite3
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class PatternDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.lock = asyncio.Lock()

    async def initialize(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with self.lock:
            self.conn = sqlite3.connect(self.db_path)
            cursor = self.conn.cursor()
            
            # Crear tabla de patrones
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS patterns (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT,
                    features TEXT NOT NULL,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    total_occurrences INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0,
                    last_updated INTEGER,
                    historical_results TEXT,
                    direction TEXT,
                    confidence REAL,
                    price REAL,
                    result TEXT,
                    profit_loss REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Crear tabla de operaciones (trades)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    direction TEXT,
                    entry_price REAL,
                    size REAL,
                    take_profit REAL,
                    stop_loss REAL,
                    entry_time TEXT,
                    exit_time TEXT,
                    exit_price REAL,
                    pl REAL,
                    status TEXT,
                    pattern_id TEXT,
                    pattern_name TEXT,
                    order_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.conn.commit()
            logger.info(f"Base de datos inicializada en {self.db_path}")

    async def get_all_patterns(self) -> List[Dict[str, Any]]:
        if not self.conn:
            await self.initialize()
        async with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM patterns")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            patterns = []
            for row in rows:
                p = {columns[i]: row[i] for i in range(len(columns))}
                # Convertir JSON
                if p['features']:
                    try:
                        p['features'] = json.loads(p['features'])
                    except:
                        p['features'] = {}
                if p['historical_results']:
                    try:
                        p['historical_results'] = json.loads(p['historical_results'])
                    except:
                        p['historical_results'] = []
                patterns.append(p)
            return patterns

    async def save_pattern(self, pattern: Dict[str, Any]):
        if not self.conn:
            await self.initialize()
        async with self.lock:
            cursor = self.conn.cursor()

            features_str = json.dumps(pattern.get('features', {}))
            hist_str = json.dumps(pattern.get('historical_results', []))
            # Chequear si existe
            cursor.execute("SELECT id FROM patterns WHERE id = ?", (pattern['id'],))
            exists = cursor.fetchone()
            if exists:
                cursor.execute('''
                    UPDATE patterns SET
                      name=?,
                      type=?,
                      features=?,
                      success_count=?,
                      failure_count=?,
                      total_occurrences=?,
                      success_rate=?,
                      last_updated=?,
                      historical_results=?,
                      direction=?,
                      confidence=?,
                      price=?,
                      result=?,
                      profit_loss=?
                    WHERE id=?
                ''', (
                    pattern.get('name',''),
                    pattern.get('type',''),
                    features_str,
                    pattern.get('success_count',0),
                    pattern.get('failure_count',0),
                    pattern.get('total_occurrences',0),
                    pattern.get('success_rate',0.0),
                    pattern.get('last_updated',0),
                    hist_str,
                    pattern.get('direction',''),
                    pattern.get('confidence',0.0),
                    pattern.get('price',0.0),
                    pattern.get('result',''),
                    pattern.get('profit_loss',0.0),
                    pattern['id']
                ))
            else:
                cursor.execute('''
                    INSERT INTO patterns
                    (id, name, type, features, success_count, failure_count,
                     total_occurrences, success_rate, last_updated,
                     historical_results, direction, confidence, price, result, profit_loss)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    pattern['id'],
                    pattern.get('name',''),
                    pattern.get('type',''),
                    features_str,
                    pattern.get('success_count',0),
                    pattern.get('failure_count',0),
                    pattern.get('total_occurrences',0),
                    pattern.get('success_rate',0.0),
                    pattern.get('last_updated',0),
                    hist_str,
                    pattern.get('direction',''),
                    pattern.get('confidence',0.0),
                    pattern.get('price',0.0),
                    pattern.get('result',''),
                    pattern.get('profit_loss',0.0)
                ))
            self.conn.commit()

    async def get_open_trades(self, symbol=None) -> List[Dict[str, Any]]:
        """Obtiene operaciones abiertas desde la base de datos"""
        if not self.conn:
            await self.initialize()
            
        async with self.lock:
            try:
                cursor = self.conn.cursor()
                
                # Verificar si la tabla existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
                if not cursor.fetchone():
                    logger.info("La tabla de operaciones no existe, creándola...")
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trades (
                        id TEXT PRIMARY KEY,
                        symbol TEXT,
                        direction TEXT,
                        entry_price REAL,
                        size REAL,
                        take_profit REAL,
                        stop_loss REAL,
                        entry_time TEXT,
                        exit_time TEXT,
                        exit_price REAL,
                        pl REAL,
                        status TEXT,
                        pattern_id TEXT,
                        pattern_name TEXT,
                        order_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')
                    self.conn.commit()
                    return []
                
                # Ejecutar consulta para obtener operaciones abiertas
                if symbol:
                    query = "SELECT * FROM trades WHERE status = 'open' AND symbol = ?"
                    cursor.execute(query, (symbol,))
                else:
                    query = "SELECT * FROM trades WHERE status = 'open'"
                    cursor.execute(query)
                    
                rows = cursor.fetchall()
                
                if not rows:
                    logger.info(f"No se encontraron operaciones abiertas en la base de datos para {symbol if symbol else 'ningún símbolo'}")
                    return []
                    
                trades = []
                columns = [desc[0] for desc in cursor.description]
                
                for row in rows:
                    # Convertir fila a diccionario
                    trade = {}
                    for i, col in enumerate(columns):
                        trade[col] = row[i]
                    
                    # Asegurar que los valores numéricos sean del tipo correcto
                    for key in ['entry_price', 'size', 'take_profit', 'stop_loss', 'exit_price', 'pl']:
                        if key in trade and trade[key] is not None:
                            trade[key] = float(trade[key])
                        elif key in trade:
                            trade[key] = 0.0
                    
                    # Añadir campos adicionales para el seguimiento en tiempo real
                    trade['current_pl'] = 0.0  # Se calculará después
                    trade['current_price'] = trade['entry_price']  # Se actualizará después
                    
                    trades.append(trade)
                    
                logger.info(f"Se cargaron {len(trades)} operaciones abiertas desde la base de datos para {symbol if symbol else 'todos los símbolos'}")
                return trades
            except Exception as e:
                logger.error(f"Error al obtener operaciones abiertas: {e}")
                return []

    async def save_trade(self, trade: Dict[str, Any]) -> bool:
        """Guarda una operación en la base de datos"""
        if not self.conn:
            await self.initialize()
            
        async with self.lock:
            try:
                cursor = self.conn.cursor()
                
                # Verificar si la tabla existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
                if not cursor.fetchone():
                    # Crear tabla si no existe
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trades (
                        id TEXT PRIMARY KEY,
                        symbol TEXT,
                        direction TEXT,
                        entry_price REAL,
                        size REAL,
                        take_profit REAL,
                        stop_loss REAL,
                        entry_time TEXT,
                        exit_time TEXT,
                        exit_price REAL,
                        pl REAL,
                        status TEXT,
                        pattern_id TEXT,
                        pattern_name TEXT,
                        order_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    ''')
                    self.conn.commit()
                
                # Insertar o actualizar operación
                query = '''
                INSERT OR REPLACE INTO trades (
                    id, symbol, direction, entry_price, size, take_profit, stop_loss,
                    entry_time, exit_time, exit_price, pl, status, pattern_id, pattern_name, order_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                '''
                
                cursor.execute(query, (
                    trade.get('id', ''),
                    trade.get('symbol', ''),
                    trade.get('direction', ''),
                    trade.get('entry_price', 0),
                    trade.get('size', 0),
                    trade.get('take_profit', 0),
                    trade.get('stop_loss', 0),
                    trade.get('entry_time', ''),
                    trade.get('exit_time', ''),
                    trade.get('exit_price', 0),
                    trade.get('pl', 0),
                    trade.get('status', 'open'),
                    trade.get('pattern_id', ''),
                    trade.get('pattern_name', ''),
                    trade.get('order_id', '')
                ))
                
                self.conn.commit()
                logger.info(f"Operación guardada en la base de datos: {trade.get('id')} - {trade.get('symbol')} - {trade.get('status')}")
                return True
            except Exception as e:
                logger.error(f"Error al guardar operación: {e}")
                return False

    async def update_trade(self, trade: Dict[str, Any]) -> bool:
        """Actualiza una operación existente en la base de datos"""
        return await self.save_trade(trade)
        
    async def get_trade_history(self, symbol=None, limit=100) -> List[Dict[str, Any]]:
        """Obtiene el historial de operaciones cerradas"""
        if not self.conn:
            await self.initialize()
            
        async with self.lock:
            try:
                cursor = self.conn.cursor()
                
                # Verificar si la tabla existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
                if not cursor.fetchone():
                    return []
                
                if symbol:
                    query = "SELECT * FROM trades WHERE status = 'closed' AND symbol = ? ORDER BY exit_time DESC LIMIT ?"
                    cursor.execute(query, (symbol, limit))
                else:
                    query = "SELECT * FROM trades WHERE status = 'closed' ORDER BY exit_time DESC LIMIT ?"
                    cursor.execute(query, (limit,))
                    
                rows = cursor.fetchall()
                
                if not rows:
                    return []
                    
                trades = []
                columns = [desc[0] for desc in cursor.description]
                
                for row in rows:
                    # Convertir fila a diccionario
                    trade = {}
                    for i, col in enumerate(columns):
                        trade[col] = row[i]
                    
                    # Asegurar que los valores numéricos sean del tipo correcto
                    for key in ['entry_price', 'size', 'take_profit', 'stop_loss', 'exit_price', 'pl']:
                        if key in trade and trade[key] is not None:
                            trade[key] = float(trade[key])
                        elif key in trade:
                            trade[key] = 0.0
                    
                    trades.append(trade)
                    
                return trades
            except Exception as e:
                logger.error(f"Error al obtener historial de operaciones: {e}")
                return []

    async def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
