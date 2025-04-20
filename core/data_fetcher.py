#!/usr/bin/env python3
import sqlite3
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import ccxt
import ccxt.async_support as ccxtasync
from datetime import datetime, timedelta
from utils.symbol_validator import SymbolValidator

logger = logging.getLogger(__name__)

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

class HistoricalDataStorage:
    """
    Clase para almacenar y recuperar datos históricos de mercado
    """
    
    def __init__(self, db_path: str = 'data/historical_data.db'):
        self.pattern_db_path = db_path
        self.conn = None
        self.lock = asyncio.Lock()
        
    async def initialize(self):
        """Inicializa la base de datos"""
        # Asegurarse de que el directorio existe
        os.makedirs(os.path.dirname(self.pattern_db_path), exist_ok=True)
        
        async with self.lock:
            try:
                # Conectar a la base de datos
                self.conn = sqlite3.connect(self.pattern_db_path)
                cursor = self.conn.cursor()
                
                # Crear tablas para cada timeframe común
                timeframes = ['1min', '5min', '15min', '30min', '1hour', '4hour', '1day']
                
                for timeframe in timeframes:
                    cursor.execute(f'''
                    CREATE TABLE IF NOT EXISTS candles_{timeframe} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        volume REAL NOT NULL,
                        UNIQUE(symbol, timestamp)
                    )
                    ''')
                    
                    # Crear índices para búsqueda rápida
                    cursor.execute(f'''
                    CREATE INDEX IF NOT EXISTS idx_symbol_timestamp_{timeframe}
                    ON candles_{timeframe} (symbol, timestamp)
                    ''')
                
                # Crear tabla de metadatos para seguimiento
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS collection_metadata (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    last_collected_timestamp INTEGER,
                    first_collected_timestamp INTEGER,
                    total_candles INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, timeframe)
                )
                ''')
                
                self.conn.commit()
                logger.info(f"Base de datos de datos históricos inicializada en {self.pattern_db_path}")
                
            except Exception as e:
                logger.error(f"Error al inicializar la base de datos de datos históricos: {e}")
                if self.conn:
                    self.conn.close()
                    self.conn = None
                raise
    
    def _get_table_name(self, timeframe: str) -> str:
        """Convierte un timeframe a nombre de tabla"""
        if timeframe == '1m':
            return 'candles_1min'
        elif timeframe == '5m':
            return 'candles_5min'
        elif timeframe == '15m':
            return 'candles_15min'
        elif timeframe == '30m':
            return 'candles_30min'
        elif timeframe == '1h':
            return 'candles_1hour'
        elif timeframe == '4h':
            return 'candles_4hour'
        elif timeframe == '1d':
            return 'candles_1day'
        else:
            # Fallback para timeframes no estándar
            return f'candles_{timeframe.replace("m", "min").replace("h", "hour").replace("d", "day")}'
    
    async def get_candles(self, symbol: str, timeframe: str, since: int, limit: int = 1000) -> List[Candle]:
        """
        Obtiene velas históricas de la base de datos
        
        Args:
            symbol: Símbolo del mercado
            timeframe: Timeframe de las velas
            since: Timestamp desde donde comenzar (en milisegundos)
            limit: Número máximo de velas a obtener
            
        Returns:
            Lista de objetos Candle
        """
        if not self.conn:
            await self.initialize()
            
        async with self.lock:
            try:
                cursor = self.conn.cursor()
                table_name = self._get_table_name(timeframe)
                
                # Consultar velas
                cursor.execute(f'''
                SELECT timestamp, open, high, low, close, volume
                FROM {table_name}
                WHERE symbol = ? AND timestamp >= ?
                ORDER BY timestamp
                LIMIT ?
                ''', (symbol, since, limit))
                
                rows = cursor.fetchall()
                
                # Convertir a objetos Candle
                candles = []
                for row in rows:
                    timestamp, open_price, high, low, close, volume = row
                    candle = Candle(
                        timestamp=timestamp,
                        open=float(open_price),
                        high=float(high),
                        low=float(low),
                        close=float(close),
                        volume=float(volume)
                    )
                    candles.append(candle)
                
                return candles
                
            except Exception as e:
                logger.error(f"Error al obtener velas de la base de datos: {e}")
                return []
    
    async def save_candles(self, symbol: str, timeframe: str, candles: List[Candle]) -> bool:
        """
        Guarda velas históricas en la base de datos
        
        Args:
            symbol: Símbolo del mercado
            timeframe: Timeframe de las velas
            candles: Lista de objetos Candle
            
        Returns:
            True si se guardaron correctamente, False en caso contrario
        """
        if not self.conn:
            await self.initialize()
            
        if not candles:
            return True  # Nada que guardar
            
        async with self.lock:
            try:
                cursor = self.conn.cursor()
                table_name = self._get_table_name(timeframe)
                
                # Insertar velas
                for candle in candles:
                    try:
                        cursor.execute(f'''
                        INSERT OR IGNORE INTO {table_name}
                        (symbol, timestamp, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            symbol,
                            candle.timestamp,
                            candle.open,
                            candle.high,
                            candle.low,
                            candle.close,
                            candle.volume
                        ))
                    except sqlite3.IntegrityError:
                        # La vela ya existe, ignorar
                        pass
                
                # Actualizar metadatos
                first_timestamp = candles[0].timestamp if candles else None
                last_timestamp = candles[-1].timestamp if candles else None
                
                if first_timestamp and last_timestamp:
                    # Obtener total de velas
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE symbol = ?", (symbol,))
                    total_candles = cursor.fetchone()[0] or 0
                    
                    # Actualizar metadatos
                    cursor.execute('''
                    INSERT OR REPLACE INTO collection_metadata 
                    (symbol, timeframe, last_collected_timestamp, first_collected_timestamp, total_candles, last_updated)
                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                    ''', (symbol, timeframe, last_timestamp, first_timestamp, total_candles))
                
                self.conn.commit()
                return True
                
            except Exception as e:
                logger.error(f"Error al guardar velas en la base de datos: {e}")
                return False
    
    async def get_collection_metadata(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Obtiene metadatos de recopilación"""
        if not self.conn:
            await self.initialize()
            
        async with self.lock:
            try:
                cursor = self.conn.cursor()
                
                cursor.execute('''
                SELECT symbol, timeframe, last_collected_timestamp, first_collected_timestamp, total_candles, last_updated
                FROM collection_metadata
                WHERE symbol = ? AND timeframe = ?
                ''', (symbol, timeframe))
                
                row = cursor.fetchone()
                
                if row:
                    return {
                        'symbol': row[0],
                        'timeframe': row[1],
                        'last_collected_timestamp': row[2],
                        'first_collected_timestamp': row[3],
                        'total_candles': row[4],
                        'last_updated': row[5]
                    }
                
                return None
                
            except Exception as e:
                logger.error(f"Error al obtener metadatos de recopilación: {e}")
                return None
    
    async def close(self):
        """Cierra la conexión a la base de datos"""
        if self.conn:
            self.conn.close()
            self.conn = None

class DataFetcher:
    """Clase para obtener datos de mercado de exchanges"""
    async def initialize(self):
        """Inicializa el data fetcher y sus conexiones"""
        try:
            logger.info(f"Inicializando data fetcher para {self.exchange_id}")
            # Cualquier inicialización necesaria
            # Por ejemplo, verificar conexión con el exchange
            return True
        except Exception as e:
            logger.error(f"Error al inicializar data fetcher: {e}")
            return False

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa el fetcher de datos
        
        Args:
            config: Configuración del bot
        """
        self.config = config
        self.exchange_id = config['api']['exchange']
        self.api_key = config['api'].get('api_key', '')
        self.api_secret = config['api'].get('api_secret', '')
        
        # Inicializar exchange
        exchange_class = getattr(ccxt, self.exchange_id)
        self.exchange = exchange_class({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
        })
        logger.info(f"Exchange {self.exchange_id} inicializado correctamente")
        
        # Inicializar exchange asíncrono
        async_exchange_class = getattr(ccxtasync, self.exchange_id)
        self.async_exchange = async_exchange_class({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
        })
        logger.info(f"Exchange asíncrono {self.exchange_id} inicializado correctamente")
        
        # Inicializar validador de símbolos
        self.symbol_validator = SymbolValidator(self.exchange_id)
    
    async def fetch_historical_data(self, symbol: str, timeframe: str, days: int) -> List[Candle]:
        """
        Obtiene datos históricos del mercado
        
        Args:
            symbol: Símbolo a consultar (ej: BTC/USD)
            timeframe: Timeframe de las velas (ej: 1h, 1d)
            days: Número de días hacia atrás
            
        Returns:
            Lista de velas
        """
        try:
            # Calcular timestamp de inicio
            since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            
            # Validar y corregir el símbolo
            valid_symbol = await self.symbol_validator.get_valid_symbol(symbol)
            if not valid_symbol:
                logger.error(f"No se encontró un símbolo válido para {symbol}")
                return []
            
            if valid_symbol != symbol:
                logger.info(f"Usando símbolo válido: {valid_symbol} en lugar de {symbol}")
            
            # Obtener datos históricos
            ohlcv = await self.async_exchange.fetch_ohlcv(valid_symbol, timeframe, since)
            
            # Convertir a objetos Candle
            candles = []
            for c in ohlcv:
                candle = Candle(
                    timestamp=c[0],
                    open=c[1],
                    high=c[2],
                    low=c[3],
                    close=c[4],
                    volume=c[5]
                )
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            logger.error(f"Error al obtener datos históricos: {e}")
            return []
    
    async def fetch_historical_candles(self, symbol: str, timeframe: str, since=None, limit=None) -> List[Candle]:
        """
        Obtiene datos históricos, primero de la base de datos local y luego de la API si es necesario
        
        Args:
            symbol: Símbolo a consultar (ej: BTC/USD)
            timeframe: Timeframe de las velas (ej: 1h, 1d)
            since: Timestamp de inicio (opcional)
            limit: Límite de velas a obtener (opcional)
            
        Returns:
            Lista de velas
        """
        # Calcular días si se proporciona since
        days = 7  # valor por defecto
        if since:
            # Convertir since de milisegundos a días
            days_diff = (datetime.now().timestamp() * 1000 - since) / (1000 * 60 * 60 * 24)
            days = max(1, int(days_diff))
        
        logger.info(f"Obteniendo datos históricos para {symbol} en timeframe {timeframe} de los últimos {days} días")
        
        # Intentar obtener datos de la base de datos local primero
        try:
            # Inicializar almacenamiento de datos históricos si no existe
            if not hasattr(self, 'historical_storage'):
                self.historical_storage = HistoricalDataStorage()
                await self.historical_storage.initialize()
            
            # Obtener velas de la base de datos
            local_candles = await self.historical_storage.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                since=since,
                limit=limit or 1000
            )
            
            # Si tenemos suficientes datos locales, usarlos
            if local_candles and (limit is None or len(local_candles) >= limit):
                logger.info(f"Usando {len(local_candles)} velas de la base de datos local para {symbol} ({timeframe})")
                return local_candles
            
            # Si no tenemos datos locales o son insuficientes, usar la API
            logger.info(f"Datos locales insuficientes, obteniendo de la API para {symbol} ({timeframe})")
            
        except Exception as e:
            logger.warning(f"Error al obtener datos de la base de datos local: {e}. Usando API.")
        
        # Obtener datos de la API
        api_candles = await self.fetch_historical_data(symbol, timeframe, days)
        
        # Guardar los datos obtenidos en la base de datos local para uso futuro
        try:
            if hasattr(self, 'historical_storage') and api_candles:
                await self.historical_storage.save_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=api_candles
                )
                logger.info(f"Guardadas {len(api_candles)} velas en la base de datos local para {symbol} ({timeframe})")
        except Exception as e:
            logger.warning(f"Error al guardar datos en la base de datos local: {e}")
        
        return api_candles

    
    async def fetch_recent_candles(self, symbol: str, timeframe: str, limit: int = 100) -> List[Candle]:
        """
        Obtiene las velas más recientes del mercado
        
        Args:
            symbol: Símbolo a consultar (ej: BTC/USD)
            timeframe: Timeframe de las velas (ej: 1h, 1d)
            limit: Número de velas a obtener
            
        Returns:
            Lista de velas
        """
        try:
            # Validar y corregir el símbolo
            valid_symbol = await self.symbol_validator.get_valid_symbol(symbol)
            if not valid_symbol:
                logger.error(f"No se encontró un símbolo válido para {symbol}")
                return []
            
            if valid_symbol != symbol:
                logger.info(f"Usando símbolo válido: {valid_symbol} en lugar de {symbol}")
            
            # Obtener datos históricos recientes
            ohlcv = await self.async_exchange.fetch_ohlcv(valid_symbol, timeframe, limit=limit)
            
            # Convertir a objetos Candle
            candles = []
            for c in ohlcv:
                candle = Candle(
                    timestamp=c[0],
                    open=c[1],
                    high=c[2],
                    low=c[3],
                    close=c[4],
                    volume=c[5]
                )
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            logger.error(f"Error al obtener velas recientes: {e}")
            return []
    
    async def fetch_latest_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        """
        Obtiene la última vela del mercado
        
        Args:
            symbol: Símbolo a consultar (ej: BTC/USD)
            timeframe: Timeframe de la vela (ej: 1h, 1d)
            
        Returns:
            Última vela o None si hay error
        """
        try:
            # Validar y corregir el símbolo
            valid_symbol = await self.symbol_validator.get_valid_symbol(symbol)
            if not valid_symbol:
                logger.error(f"No se encontró un símbolo válido para {symbol}")
                return None
            
            # Obtener el ticker actual para tener el precio más reciente
            ticker = await self.async_exchange.fetch_ticker(valid_symbol)

            # Obtener últimas velas
            ohlcv = await self.async_exchange.fetch_ohlcv(valid_symbol, timeframe, limit=1)
            
            if not ohlcv or len(ohlcv) == 0:
                logger.warning(f"No se obtuvieron velas para {valid_symbol}")
                return None
            
            # Convertir a objeto Candle
            c = ohlcv[0]
            candle = Candle(
                timestamp=c[0],
                open=c[1],
                high=c[2],
                low=c[3],
                close=ticker['last'],  # Usar el precio más reciente del ticker
                volume=c[5]
            )
            
            return candle
            
        except Exception as e:
            logger.error(f"Error al obtener última vela: {e}")
            return None
    
    async def get_available_symbols(self, quote_currency='USD', limit=10):
        """
        Obtiene los símbolos disponibles en el exchange
        
        Args:
            quote_currency: Moneda de cotización (ej: USD, EUR)
            limit: Número máximo de símbolos a devolver
            
        Returns:
            Lista de símbolos disponibles
        """
        return await self.symbol_validator.get_popular_symbols(quote_currency, limit)
    
    async def close(self):
        """Libera recursos"""
        try:
            if hasattr(self, 'async_exchange'):
                await self.async_exchange.close()
            
            if hasattr(self, 'historical_storage'):
                await self.historical_storage.close()
                
            logger.info("Recursos del data fetcher liberados correctamente")
        except Exception as e:
            logger.error(f"Error al cerrar data fetcher: {e}")
