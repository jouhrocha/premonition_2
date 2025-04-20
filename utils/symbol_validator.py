#!/usr/bin/env python3
import asyncio
import logging
import ccxt.async_support as ccxtasync
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class SymbolValidator:
    """Clase para validar y corregir símbolos de trading"""
    
    def __init__(self, exchange_id):
        self.exchange_id = exchange_id
        self.exchange = None
        self.symbols_cache = None
    
    async def initialize(self):
        """Inicializa el exchange y carga los símbolos disponibles"""
        try:
            self.exchange = getattr(ccxtasync, self.exchange_id)()
            await self.exchange.load_markets()
            self.symbols_cache = self.exchange.symbols
            logger.info(f"Validador de símbolos inicializado para {self.exchange_id}")
            return True
        except Exception as e:
            logger.error(f"Error al inicializar validador de símbolos: {e}")
            return False
    
    async def get_valid_symbol(self, symbol, asset_type=None, quote_currency=None):
        """
        Obtiene un símbolo válido basado en las preferencias
        
        Args:
            symbol: Símbolo preferido (ej: 'BTC/USD')
            asset_type: Tipo de activo ('crypto', 'forex', etc.)
            quote_currency: Moneda de cotización preferida ('USD', 'EUR', etc.)
            
        Returns:
            str: Símbolo válido o None si no se encuentra
        """
        if not self.symbols_cache:
            await self.initialize()
        
        # Si el símbolo ya es válido, devolverlo
        if symbol in self.symbols_cache:
            logger.info(f"Símbolo {symbol} es válido")
            return symbol
        
        # Extraer base y quote del símbolo original
        parts = symbol.split('/')
        base = parts[0] if len(parts) > 0 else None
        quote = parts[1] if len(parts) > 1 else quote_currency or 'USD'
        
        # Si no se especifica quote_currency, usar el del símbolo original
        quote_currency = quote_currency or quote
        
        # Buscar alternativas
        alternatives = []
        
        # Caso especial para Bitcoin (BTC/XBT)
        if base in ['BTC', 'XBT']:
            for alt_base in ['BTC', 'XBT', 'WBTC', 'TBTC']:
                alt_symbol = f"{alt_base}/{quote_currency}"
                if alt_symbol in self.symbols_cache:
                    alternatives.append((alt_symbol, 1))  # Prioridad 1 para coincidencias exactas
        
        # Buscar cualquier símbolo que contenga la base
        if base:
            for s in self.symbols_cache:
                s_parts = s.split('/')
                s_base = s_parts[0]
                s_quote = s_parts[1] if len(s_parts) > 1 else None
                
                # Coincidencia exacta de base y quote
                if s_base == base and s_quote == quote_currency:
                    alternatives.append((s, 1))
                # Coincidencia de base con cualquier quote
                elif s_base == base:
                    alternatives.append((s, 2))
                # Base contiene el término buscado
                elif base in s_base:
                    alternatives.append((s, 3))
        
        # Si se especifica quote_currency, filtrar por esa moneda
        if quote_currency:
            quote_alternatives = [a for a in alternatives if a[0].endswith(f"/{quote_currency}")]
            if quote_alternatives:
                alternatives = quote_alternatives
        
        # Ordenar por prioridad
        alternatives.sort(key=lambda x: x[1])
        
        if alternatives:
            best_match = alternatives[0][0]
            logger.info(f"Símbolo {symbol} no encontrado. Usando alternativa: {best_match}")
            return best_match
        
        logger.error(f"No se encontró ningún símbolo válido para {symbol}")
        return None
    
    async def get_popular_symbols(self, quote_currency='USD', limit=10):
        """Obtiene los símbolos más populares para un quote_currency dado"""
        if not self.symbols_cache:
            await self.initialize()
        
        # Filtrar por quote_currency
        filtered_symbols = [s for s in self.symbols_cache if s.endswith(f"/{quote_currency}")]
        
        # Lista de criptomonedas populares
        popular_bases = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'SHIB', 'LINK', 'LTC', 'DOT', 'AVAX', 'MATIC']
        
        # Ordenar por popularidad
        popular_symbols = []
        for base in popular_bases:
            for symbol in filtered_symbols:
                if symbol.startswith(f"{base}/"):
                    popular_symbols.append(symbol)
                    break
        
        # Añadir otros símbolos hasta alcanzar el límite
        remaining = limit - len(popular_symbols)
        if remaining > 0:
            other_symbols = [s for s in filtered_symbols if s not in popular_symbols]
            popular_symbols.extend(other_symbols[:remaining])
        
        return popular_symbols[:limit]
    
    async def close(self):
        """Cierra la conexión con el exchange"""
        if self.exchange:
            await self.exchange.close()

# Lista de símbolos comunes para validación rápida sin necesidad de consultar el exchange
COMMON_SYMBOLS = [
    'BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'BNB/USD',
    'BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'BNB/USD',
    'BTC/EUR', 'ETH/EUR', 'SOL/EUR', 'XRP/EUR', 'BNB/EUR'
]

# Variable global para el validador
_validator = None

async def get_validator(exchange_id='kraken'):
    """Obtiene una instancia del validador de símbolos"""
    global _validator
    if _validator is None:
        _validator = SymbolValidator(exchange_id)
        await _validator.initialize()
    return _validator

async def validate_symbol(symbol: str) -> bool:
    """
    Valida si un símbolo tiene el formato correcto y está disponible
    
    Args:
        symbol: Símbolo a validar (ej: 'BTC/USD')
        
    Returns:
        True si el símbolo es válido, False en caso contrario
    """
    try:
        # Validación rápida para símbolos comunes
        if symbol in COMMON_SYMBOLS:
            return True
        
        # Validación básica de formato
        if not symbol or not isinstance(symbol, str):
            logger.warning(f"Símbolo inválido: {symbol} (tipo incorrecto)")
            return False
        
        # Validar formato
        parts = symbol.split('/')
        if len(parts) != 2:
            logger.warning(f"Símbolo inválido: {symbol} (formato incorrecto)")
            return False
        
        # Validación completa con el exchange (solo si es necesario)
        try:
            validator = await get_validator()
            valid_symbol = await validator.get_valid_symbol(symbol)
            return valid_symbol is not None
        except Exception as e:
            logger.error(f"Error al validar con el exchange: {e}")
            # Si falla la validación con el exchange, asumimos que es válido si pasa las validaciones básicas
            return True
        
    except Exception as e:
        logger.error(f"Error al validar símbolo {symbol}: {e}")
        return False

async def get_valid_symbols(quote_currency='USD', limit=10):
    """
    Obtiene una lista de símbolos válidos
    
    Args:
        quote_currency: Moneda de cotización (ej: 'USD')
        limit: Número máximo de símbolos a devolver
        
    Returns:
        Lista de símbolos válidos
    """
    try:
        validator = await get_validator()
        return await validator.get_popular_symbols(quote_currency, limit)
    except Exception as e:
        logger.error(f"Error al obtener símbolos válidos: {e}")
        # Devolver símbolos comunes como fallback
        return [s for s in COMMON_SYMBOLS if s.endswith(f"/{quote_currency}")][:limit]

# Función para pruebas
async def test_validator():
    symbols = ['BTC/USD', 'ETH/USD', 'invalid', 'BTC-USD', 'BTC/USD/ETH']
    for symbol in symbols:
        result = await validate_symbol(symbol)
        print(f"Símbolo: {symbol} - Válido: {result}")

if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Ejecutar prueba
    asyncio.run(test_validator())
