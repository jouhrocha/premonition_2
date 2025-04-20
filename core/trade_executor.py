# core/trade_executor.py
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

import ccxt
import ccxt.async_support as ccxtasync

from core.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

class TradingOperation:
    """Representa una operación completa de trading (entrada + salida)"""
    def __init__(self, symbol: str, direction: str, entry_order: Dict[str, Any], 
                 take_profit: float, stop_loss: float, pattern_id: str = '', pattern_name: str = ''):
        self.symbol = symbol
        self.direction = direction  # 'long' o 'short'
        self.entry_order = entry_order
        self.entry_price = float(entry_order.get('price', 0))
        self.amount = float(entry_order.get('amount', 0))
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.pattern_id = pattern_id
        self.pattern_name = pattern_name
        self.status = 'open'
        self.exit_order = None
        self.profit_loss = 0.0
        self.entry_time = datetime.fromtimestamp(entry_order.get('timestamp', 0)/1000)
        self.exit_time = None

class TradeExecutor:
    """Ejecutor de operaciones de trading"""
    def __init__(self, config: Dict[str, Any], data_fetcher: Optional[DataFetcher] = None):
        """
        Inicializa el ejecutor de operaciones
        
        Args:
            config: Configuración del bot
            data_fetcher: Instancia de DataFetcher (opcional)
        """
        self.config = config
        self.data_fetcher = data_fetcher
        
        # Configuración de trading
        trading_config = config.get('trading', {})
        self.mode = trading_config.get('mode', 'paper')  # 'paper' o 'live'
        self.position_size = trading_config.get('position_size', 1.0)
        self.leverage = trading_config.get('leverage', 1)
        
        # Configuración de API
        api_config = config.get('api', {})
        self.exchange_id = api_config.get('exchange', 'kraken')
        self.api_key = api_config.get('api_key', '')
        self.api_secret = api_config.get('api_secret', '')
        self.testnet = api_config.get('testnet', True)
        
        # Estado interno
        self.open_orders = []
        self.open_positions = []
        self.trade_history = []
        self.balance = 0.0
        self.equity = 0.0
        
        # Exchange
        self.exchange = None
        self.async_exchange = None
        
        # Lock para operaciones concurrentes
        self.lock = asyncio.Lock()
        self.active_operations: List[TradingOperation] = []
            
    async def open_trading_operation(self, symbol: str, direction: str, amount: float, 
                                entry_price: Optional[float] = None, 
                                take_profit_pct: float = 1.0, 
                                stop_loss_pct: float = 0.5,
                                pattern_id: str = '',
                                pattern_name: str = '') -> Optional[TradingOperation]:
        """
        Abre una nueva operación de trading
        """
        try:
            # Determinar side basado en direction
            side = 'buy' if direction == 'long' else 'sell'
            
            # Crear orden de entrada
            entry_order = await self.execute_trade(
                symbol=symbol,
                order_type='limit' if entry_price else 'market',
                side=side,
                amount=amount,
                price=entry_price
            )
            
            if 'error' in entry_order:
                logger.error(f"Error al crear orden de entrada: {entry_order['error']}")
                return None
            
            # Calcular take profit y stop loss
            entry_price = float(entry_order.get('price', 0))
            if direction == 'long':
                take_profit = entry_price * (1 + take_profit_pct/100)
                stop_loss = entry_price * (1 - stop_loss_pct/100)
            else:
                take_profit = entry_price * (1 - take_profit_pct/100)
                stop_loss = entry_price * (1 + stop_loss_pct/100)
            
            # Crear operación
            operation = TradingOperation(
                symbol=symbol,
                direction=direction,
                entry_order=entry_order,
                take_profit=take_profit,
                stop_loss=stop_loss,
                pattern_id=pattern_id,
                pattern_name=pattern_name
            )
            
            # Crear órdenes de take profit y stop loss
            if self.mode == 'live':
                # Take profit
                tp_side = 'sell' if direction == 'long' else 'buy'
                tp_order = await self.execute_trade(
                    symbol=symbol,
                    order_type='limit',
                    side=tp_side,
                    amount=amount,
                    price=take_profit,
                    params={'reduceOnly': True}
                )
                
                # Stop loss
                sl_side = 'sell' if direction == 'long' else 'buy'
                sl_order = await self.execute_trade(
                    symbol=symbol,
                    order_type='stop',
                    side=sl_side,
                    amount=amount,
                    price=stop_loss,
                    params={'reduceOnly': True}
                )
                
                # Guardar IDs de órdenes
                operation.tp_order_id = tp_order.get('id')
                operation.sl_order_id = sl_order.get('id')
            
            # Añadir a operaciones activas
            self.active_operations.append(operation)
            
            logger.info(f"Nueva operación abierta: {direction} {amount} {symbol} @ {entry_price}")
            return operation
        except Exception as e:
            logger.error(f"Error al abrir operación: {e}")
            return None
    
    async def close_trading_operation(self, operation: TradingOperation, 
                                    reason: str = 'manual') -> bool:
        """
        Cierra una operación de trading
        """
        try:
            if operation.status != 'open':
                logger.warning(f"Operación ya cerrada: {operation.symbol}")
                return False
            
            # Cancelar órdenes pendientes
            if self.mode == 'live':
                if hasattr(operation, 'tp_order_id'):
                    await self.cancel_order(operation.tp_order_id, operation.symbol)
                if hasattr(operation, 'sl_order_id'):
                    await self.cancel_order(operation.sl_order_id, operation.symbol)
            
            # Crear orden de cierre
            exit_side = 'sell' if operation.direction == 'long' else 'buy'
            exit_order = await self.execute_trade(
                symbol=operation.symbol,
                order_type='market',
                side=exit_side,
                amount=operation.amount
            )
            
            if 'error' in exit_order:
                logger.error(f"Error al cerrar operación: {exit_order['error']}")
                return False
            
            # Actualizar operación
            operation.exit_order = exit_order
            operation.status = 'closed'
            operation.exit_time = datetime.now()
            
            # Calcular P/L
            entry_price = operation.entry_price
            exit_price = float(exit_order.get('price', 0))
            
            if operation.direction == 'long':
                operation.profit_loss = (exit_price - entry_price) * operation.amount
            else:
                operation.profit_loss = (entry_price - exit_price) * operation.amount
            
            # Remover de operaciones activas
            self.active_operations = [op for op in self.active_operations if op != operation]
            
            logger.info(f"Operación cerrada: {operation.symbol} - P/L: {operation.profit_loss:.2f} - Razón: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error al cerrar operación: {e}")
            return False
    async def check_operations(self):
        """
        Verifica el estado de las operaciones activas
        """
        for operation in self.active_operations[:]:  # Copiar lista para evitar modificación durante iteración
            if operation.status != 'open':
                continue
                
            try:
                # Obtener precio actual
                ticker = await self.async_exchange.fetch_ticker(operation.symbol)
                current_price = float(ticker['last'])
                
                # Verificar take profit y stop loss
                if operation.direction == 'long':
                    if current_price >= operation.take_profit:
                        await self.close_trading_operation(operation, 'take_profit')
                    elif current_price <= operation.stop_loss:
                        await self.close_trading_operation(operation, 'stop_loss')
                else:  # short
                    if current_price <= operation.take_profit:
                        await self.close_trading_operation(operation, 'take_profit')
                    elif current_price >= operation.stop_loss:
                        await self.close_trading_operation(operation, 'stop_loss')
                
            except Exception as e:
                logger.error(f"Error al verificar operación {operation.symbol}: {e}")


    async def initialize(self):
        """Inicializa el ejecutor de operaciones"""
        try:
            # Inicializar exchange
            if self.mode == 'live':
                # Configuración para trading real
                exchange_class = getattr(ccxt, self.exchange_id)
                self.exchange = exchange_class({
                    'apiKey': self.api_key,
                    'secret': self.api_secret,
                    'enableRateLimit': True,
                    'options': {
                        'testnet': self.testnet
                    }
                })
                
                # Exchange asíncrono
                async_exchange_class = getattr(ccxtasync, self.exchange_id)
                self.async_exchange = async_exchange_class({
                    'apiKey': self.api_key,
                    'secret': self.api_secret,
                    'enableRateLimit': True,
                    'options': {
                        'testnet': self.testnet
                    }
                })
                
                # Verificar conexión
                await self.async_exchange.load_markets()
                
                # Obtener balance inicial
                balance_info = await self.async_exchange.fetch_balance()
                self.balance = balance_info.get('total', {}).get('USD', 0.0)
                self.equity = self.balance
                
                logger.info(f"Ejecutor inicializado en modo LIVE con balance: ${self.balance:.2f}")
            else:
                # Modo paper trading
                self.balance = 1000.0  # Balance inicial para paper trading
                self.equity = self.balance
                
                # Inicializar data_fetcher si no se proporcionó
                if not self.data_fetcher:
                    self.data_fetcher = DataFetcher(self.config)
                    await self.data_fetcher.initialize()
                
                logger.info(f"Ejecutor inicializado en modo PAPER con balance: ${self.balance:.2f}")
            
            return True
        except Exception as e:
            logger.error(f"Error al inicializar el ejecutor de operaciones: {e}")
            return False
    async def get_kraken_open_orders(self, symbol=None):
        """Obtiene órdenes abiertas directamente de la API de Kraken"""
        try:
            if self.exchange_id.lower() != 'kraken':
                logger.warning("Este método es solo para Kraken")
                return []
                
            if not self.async_exchange or not self.api_key or not self.api_secret:
                logger.warning("Exchange no inicializado o credenciales no configuradas")
                return []
                
            try:
                # Usar método privado directamente
                params = {'trades': True}
                if symbol:
                    # Convertir formato si es necesario (BTC/USD -> XBTUSD)
                    kraken_symbol = symbol
                    if symbol.startswith('BTC/'):
                        kraken_symbol = 'XBT' + symbol[4:]
                    kraken_symbol = kraken_symbol.replace('/', '')
                    params['pair'] = kraken_symbol
                    
                # Llamar a la API de Kraken directamente
                response = await self.async_exchange.privatePostOpenOrders(params)
                
                logger.info(f"Respuesta de Kraken: {response}")
                
                if 'result' in response and 'open' in response['result']:
                    open_orders_data = response['result']['open']
                    orders = []
                    
                    for order_id, order_data in open_orders_data.items():
                        # Convertir al formato estándar de CCXT
                        pair = order_data.get('descr', {}).get('pair', '')
                        order_type = order_data.get('descr', {}).get('type', '')
                        price = order_data.get('descr', {}).get('price', '0')
                        volume = order_data.get('vol', '0')
                        
                        # Convertir a formato estándar
                        std_order = {
                            'id': order_id,
                            'symbol': pair,
                            'type': order_data.get('descr', {}).get('ordertype', ''),
                            'side': order_type,
                            'amount': float(volume),
                            'price': float(price) if price else 0,
                            'status': 'open',
                            'timestamp': int(float(order_data.get('opentm', 0)) * 1000),
                            'datetime': datetime.fromtimestamp(float(order_data.get('opentm', 0))).strftime('%Y-%m-%d %H:%M:%S'),
                            'info': order_data  # Guardar datos originales
                        }
                        
                        orders.append(std_order)
                        logger.info(f"Orden encontrada: {std_order['id']} - {std_order['symbol']} - {std_order['side']} - {std_order['amount']} @ {std_order['price']}")
                    
                    # Actualizar lista interna
                    self.open_orders = orders
                    
                    logger.info(f"Se encontraron {len(orders)} órdenes abiertas en Kraken")
                    return orders
                
                logger.warning("No se encontraron órdenes en la respuesta de Kraken")
                return []
                    
            except Exception as e:
                logger.error(f"Error al obtener órdenes abiertas de Kraken: {e}")
                # Mostrar detalles del error para depuración
                import traceback
                logger.error(traceback.format_exc())
                return []
                    
        except Exception as e:
            logger.error(f"Error en get_kraken_open_orders: {e}")
            return []

    async def get_positions_and_orders(self, symbol=None):
        """Obtiene tanto posiciones como órdenes abiertas y operaciones activas"""
        positions = await self.get_open_positions(symbol)
        orders = await self.get_kraken_open_orders(symbol) if self.exchange_id.lower() == 'kraken' else await self.get_open_orders(symbol)
        
        # Filtrar operaciones por símbolo
        operations = [op for op in self.active_operations if not symbol or op.symbol == symbol]
        
        return {
            'positions': positions,
            'orders': orders,
            'operations': operations
        }

    async def execute_trade(self, symbol: str, order_type: str, side: str, amount: float, 
                          price: Optional[float] = None, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        """
        Ejecuta una operación de trading
        
        Args:
            symbol: Símbolo a operar
            order_type: Tipo de orden ('market', 'limit', etc.)
            side: Lado de la operación ('buy' o 'sell')
            amount: Cantidad a operar
            price: Precio (para órdenes limit)
            params: Parámetros adicionales
            
        Returns:
            Información de la orden ejecutada
        """
        async with self.lock:
            try:
                if self.mode == 'live':
                    # Trading real
                    if not self.async_exchange:
                        raise Exception("Exchange no inicializado")
                    
                    # Ejecutar orden
                    order = await self.async_exchange.create_order(
                        symbol=symbol,
                        type=order_type,
                        side=side,
                        amount=amount,
                        price=price,
                        params=params
                    )
                    
                    # Registrar orden
                    self.open_orders.append(order)
                    
                    logger.info(f"Orden ejecutada: {side} {amount} {symbol} a {price if price else 'mercado'}")
                    return order
                else:
                    # Paper trading
                    # Obtener precio actual si no se proporciona
                    if not price and order_type == 'market':
                        if not self.data_fetcher:
                            raise Exception("Data fetcher no inicializado para paper trading")
                        
                        latest_candle = await self.data_fetcher.fetch_latest_candle(symbol, '1m')
                        if not latest_candle:
                            raise Exception(f"No se pudo obtener el precio actual para {symbol}")
                        
                        price = latest_candle.close
                    
                    # Crear orden simulada
                    order_id = f"paper_{len(self.open_orders) + len(self.trade_history) + 1}"
                    timestamp = int(datetime.now().timestamp() * 1000)
                    
                    order = {
                        'id': order_id,
                        'symbol': symbol,
                        'type': order_type,
                        'side': side,
                        'amount': amount,
                        'price': price,
                        'timestamp': timestamp,
                        'datetime': datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'closed',  # En paper trading, las órdenes se ejecutan inmediatamente
                        'filled': amount,
                        'remaining': 0,
                        'cost': amount * price,
                        'fee': {
                            'cost': amount * price * 0.001,  # Comisión simulada del 0.1%
                            'currency': 'USD'
                        }
                    }
                    
                    # Actualizar balance
                    if side == 'buy':
                        self.balance -= order['cost'] + order['fee']['cost']
                    else:  # sell
                        self.balance += order['cost'] - order['fee']['cost']
                    
                    # Registrar en historial
                    self.trade_history.append(order)
                    
                    logger.info(f"Orden simulada: {side} {amount} {symbol} a {price}")
                    return order
            
            except Exception as e:
                logger.error(f"Error al ejecutar operación: {e}")
                return {'error': str(e)}

    async def get_open_positions(self, symbol=None):
        """Obtiene las posiciones abiertas del exchange"""
        try:
            if self.mode != 'live' or not self.async_exchange:
                logger.warning("Exchange no inicializado o modo no es live")
                return []

            # Verificar si el exchange soporta la obtención de posiciones
            if not hasattr(self.async_exchange, 'fetch_positions'):
                logger.warning(f"El exchange {self.async_exchange.id} no soporta fetch_positions")
                return []

            try:
                # Obtener todas las posiciones - usar async_exchange en lugar de exchange
                positions = await self.async_exchange.fetch_positions()
                
                # Filtrar por símbolo si se especifica
                if symbol and positions:
                    positions = [pos for pos in positions if pos.get('symbol') == symbol]
                
                logger.info(f"Posiciones obtenidas del exchange: {len(positions)}")
                return positions

            except Exception as e:
                logger.error(f"Error al obtener posiciones del exchange: {e}")
                return []

        except Exception as e:
            logger.error(f"Error en get_open_positions: {e}")
            return []

    async def get_open_orders(self, symbol=None):
        """Obtiene las órdenes abiertas del exchange"""
        try:
            if self.mode != 'live' or not self.async_exchange:
                logger.warning("Exchange no inicializado o modo no es live")
                return []
                
            # Verificar si el exchange soporta la obtención de órdenes abiertas
            if not hasattr(self.async_exchange, 'fetch_open_orders'):
                logger.warning(f"El exchange {self.async_exchange.id} no soporta fetch_open_orders")
                return []
                
            try:
                # Obtener órdenes abiertas - usar async_exchange en lugar de exchange
                if symbol:
                    orders = await self.async_exchange.fetch_open_orders(symbol)
                else:
                    orders = await self.async_exchange.fetch_open_orders()
                
                # Actualizar lista interna
                self.open_orders = orders
                
                logger.info(f"Órdenes abiertas obtenidas del exchange: {len(orders)}")
                return orders
                
            except Exception as e:
                logger.error(f"Error al obtener órdenes abiertas del exchange: {e}")
                return []
                
        except Exception as e:
            logger.error(f"Error en get_open_orders: {e}")
            return []

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """
        Cancela una orden abierta
        
        Args:
            order_id: ID de la orden a cancelar
            symbol: Símbolo de la orden
            
        Returns:
            Información de la cancelación
        """
        async with self.lock:
            try:
                if self.mode == 'live':
                    # Trading real
                    if not self.async_exchange:
                        raise Exception("Exchange no inicializado")
                    
                    # Cancelar orden
                    result = await self.async_exchange.cancel_order(order_id, symbol)
                    
                    # Actualizar lista de órdenes abiertas
                    self.open_orders = [o for o in self.open_orders if o['id'] != order_id]
                    
                    logger.info(f"Orden {order_id} cancelada")
                    return result
                else:
                    # Paper trading
                    # Buscar orden en la lista de órdenes abiertas
                    for i, order in enumerate(self.open_orders):
                        if order['id'] == order_id:
                            # Marcar como cancelada
                            order['status'] = 'canceled'
                            
                            # Eliminar de órdenes abiertas
                            canceled_order = self.open_orders.pop(i)
                            
                            # Añadir al historial
                            self.trade_history.append(canceled_order)
                            
                            logger.info(f"Orden simulada {order_id} cancelada")
                            return canceled_order
                    
                    raise Exception(f"Orden {order_id} no encontrada")
            
            except Exception as e:
                logger.error(f"Error al cancelar orden: {e}")
                return {'error': str(e)}
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Obtiene las órdenes abiertas
        
        Args:
            symbol: Símbolo para filtrar (opcional)
            
        Returns:
            Lista de órdenes abiertas
        """
        try:
            if self.mode == 'live':
                # Trading real
                if not self.async_exchange:
                    raise Exception("Exchange no inicializado")
                
                # Obtener órdenes abiertas
                open_orders = await self.async_exchange.fetch_open_orders(symbol)
                
                # Actualizar lista interna
                self.open_orders = open_orders
                
                return open_orders
            else:
                # Paper trading
                if symbol:
                    return [o for o in self.open_orders if o['symbol'] == symbol]
                else:
                    return self.open_orders
        
        except Exception as e:
            logger.error(f"Error al obtener órdenes abiertas: {e}")
            return []
    
    async def get_balance(self) -> Dict[str, Any]:
        """
        Obtiene el balance actual
        
        Returns:
            Información de balance
        """
        try:
            if self.mode == 'live':
                # Trading real
                if not self.async_exchange:
                    raise Exception("Exchange no inicializado")
                
                # Obtener balance
                balance_info = await self.async_exchange.fetch_balance()
                
                # Actualizar balance interno
                self.balance = balance_info.get('total', {}).get('USD', 0.0)
                
                return balance_info
            else:
                # Paper trading
                return {
                    'free': {'USD': self.balance},
                    'used': {'USD': 0.0},
                    'total': {'USD': self.balance}
                }
        
        except Exception as e:
            logger.error(f"Error al obtener balance: {e}")
            return {}
    
    async def get_position(self, symbol: str) -> Dict[str, Any]:
        """
        Obtiene información de una posición abierta
        
        Args:
            symbol: Símbolo de la posición
            
        Returns:
            Información de la posición
        """
        try:
            if self.mode == 'live':
                # Trading real
                if not self.async_exchange:
                    raise Exception("Exchange no inicializado")
                
                # Verificar si el exchange soporta posiciones
                if hasattr(self.async_exchange, 'fetch_position'):
                    position = await self.async_exchange.fetch_position(symbol)
                    return position
                elif hasattr(self.async_exchange, 'fetch_positions'):
                    positions = await self.async_exchange.fetch_positions([symbol])
                    if positions:
                        return positions[0]
                
                return {}
            else:
                # Paper trading
                for position in self.open_positions:
                    if position['symbol'] == symbol:
                        return position
                
                return {}
        
        except Exception as e:
            logger.error(f"Error al obtener posición: {e}")
            return {}
    
    async def close(self):
        """Cierra conexiones y libera recursos"""
        try:
            if self.mode == 'live' and self.async_exchange:
                await self.async_exchange.close()
            
            if self.data_fetcher and hasattr(self.data_fetcher, 'close'):
                await self.data_fetcher.close()
            
            logger.info("Recursos del ejecutor de operaciones liberados correctamente")
        except Exception as e:
            logger.error(f"Error al cerrar ejecutor de operaciones: {e}")
