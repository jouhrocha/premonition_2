# core/bot.py
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from PyQt5.QtCore import QObject, pyqtSignal,QTimer# type: ignore
import ccxt
from utils.database import PatternDatabase
from core.data_fetcher import DataFetcher
from core.pattern_detector import PatternDetector
from core.pattern_analyzer import PatternAnalyzer
from core.trade_executor import TradeExecutor
import functools

logger = logging.getLogger(__name__)

class MultiSymbolTradingBot(QObject):
    log_signal = pyqtSignal(str)
    update_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(bool, object)

    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.bots = {}  # Diccionario para almacenar bots por símbolo
        trading_cfg = config.get("trading", {})
        self.symbol = trading_cfg.get("symbol", "BTC/USD")
        self.timeframe = trading_cfg.get("timeframe", "1h")
        self.historical_days = trading_cfg.get("historical_days", 30)
        self.mode = trading_cfg.get("mode", "paper")
        
        # Configuración de trading
        self.take_profit_pct = trading_cfg.get("take_profit_pct", 2.0)
        self.stop_loss_pct = trading_cfg.get("stop_loss_pct", 1.0)
        self.risk_per_trade = trading_cfg.get("risk_per_trade", 0.02)
        self.max_open_trades = trading_cfg.get("max_open_trades", 3)
        
        # Estado del bot
        self.is_running = False
        self.start_time = None
        self.active_trades = []
        self.trade_history = []
        self.last_check_time = None
        self.last_candle = None
        self.update_timer = QTimer()
        self.update_timer.start(30000)  # Actualizar cada 30 segundos

        # Iniciar logger
        logger.info(f"Bot inicializado para símbolo {self.symbol} en timeframe {self.timeframe}")

    async def initialize(self, is_child_bot=False):
        """Inicializa base de datos, fetcher, etc."""
        # Inicializar bots hijos solo si no es un bot hijo
        if not is_child_bot:
            symbols = self.config.get('multi_trading', {}).get('symbols', [])
            if not symbols:
                logger.warning("No hay símbolos configurados para trading múltiple")
            else:
                # Solo inicializar bots para símbolos diferentes al actual
                for symbol in symbols:
                    if symbol != self.symbol:  # Evitar crear un bot para el símbolo actual
                        # Crear configuración específica para este símbolo
                        symbol_config = self.config.copy()
                        symbol_config['trading']['symbol'] = symbol
                        
                        # Crear bot para este símbolo
                        bot = MultiSymbolTradingBot(symbol_config)
                        success = await bot.initialize(is_child_bot=True)  # Pasar flag para evitar recursión
                        
                        if success:
                            self.bots[symbol] = bot
                            logger.info(f"Bot inicializado para {symbol}")
                        else:
                            logger.error(f"No se pudo inicializar bot para {symbol}")
        
        # Lista para rastrear componentes inicializados
        initialized_components = []
        
        try:
            # DB
            db_path = self.config.get('database', {}).get('path', 'data/patterns.db')
            logger.info("Inicializando base de datos...")
            self.pattern_db = PatternDatabase(db_path)
            await self.pattern_db.initialize()
            initialized_components.append(('pattern_db', self.pattern_db))

            # Data fetcher
            logger.info(f"Inicializando data fetcher para {self.symbol}...")
            self.data_fetcher = DataFetcher(self.config)
            await self.data_fetcher.initialize()
            initialized_components.append(('data_fetcher', self.data_fetcher))

            # Pattern detector
            logger.info("Inicializando detector de patrones...")
            self.pattern_detector = PatternDetector(self.pattern_db)
            await self.pattern_detector.load_patterns()
            initialized_components.append(('pattern_detector', self.pattern_detector))

            # Trade executor
            logger.info("Inicializando ejecutor de trades...")
            self.trade_executor = TradeExecutor(self.config, self.data_fetcher)
            await self.trade_executor.initialize()
            initialized_components.append(('trade_executor', self.trade_executor))

            # Cargar operaciones abiertas
            await self._load_open_operations()
            
            logger.info("Todos los componentes inicializados correctamente")
            return True
        except Exception as e:
            logger.error(f"Error al inicializar componentes del bot: {e}")
            
            # Cerrar componentes inicializados en caso de error
            for name, component in reversed(initialized_components):
                try:
                    if hasattr(component, 'close') and callable(component.close):
                        await component.close()
                        logger.info(f"Componente {name} cerrado correctamente tras error")
                except Exception as close_error:
                    logger.error(f"Error al cerrar componente {name} tras error: {close_error}")
            
        return len(self.bots) > 0 if not is_child_bot else True
    async def _load_open_operations(self):
        """Carga operaciones abiertas desde el exchange o base de datos"""
        logger.info(f"Cargando operaciones abiertas para {self.symbol}...")
        if self.mode.lower() == 'live' and hasattr(self, 'trade_executor') and self.trade_executor:
            try:
                # Obtener tanto posiciones como órdenes
                trading_data = await self.trade_executor.get_positions_and_orders(self.symbol)
                positions = trading_data['positions']
                open_orders = trading_data['orders']

                # Procesar posiciones...
                if positions:
                    logger.info(f"Se encontraron {len(positions)} posiciones abiertas en el exchange para {self.symbol}")
                            
                    # Convertir posiciones del exchange al formato interno
                    for pos in positions:
                        # Obtener datos de la posición
                        symbol = pos.get('symbol', self.symbol)
                        size = float(pos.get('contracts', 0))
                        entry_price = float(pos.get('entryPrice', 0))
                        direction = 'long' if pos.get('side', '').lower() == 'buy' else 'short'
                        
                        # Calcular take profit y stop loss basados en la configuración
                        if direction == 'long':
                            take_profit = entry_price * (1 + self.take_profit_pct / 100)
                            stop_loss = entry_price * (1 - self.stop_loss_pct / 100)
                        else:  # short
                            take_profit = entry_price * (1 - self.take_profit_pct / 100)
                            stop_loss = entry_price * (1 + self.stop_loss_pct / 100)
                        
                        # Crear objeto de posición
                        position = {
                            'id': pos.get('id', f"trade_exchange_{len(self.active_trades) + 1}"),
                            'symbol': symbol,
                            'direction': direction,
                            'entry_price': entry_price,
                            'size': size,
                            'take_profit': take_profit,
                            'stop_loss': stop_loss,
                            'entry_time': datetime.fromtimestamp(pos.get('timestamp', 0)/1000).strftime('%Y-%m-%d %H:%M:%S') if pos.get('timestamp') else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'pattern_id': '',
                            'pattern_name': 'Posición cargada desde exchange',
                            'current_pl': float(pos.get('unrealizedPnl', 0)),
                            'current_price': float(pos.get('markPrice', entry_price)),
                            'status': 'open',
                            'order_id': pos.get('id', '')
                        }
                        
                        # Añadir a posiciones activas si no existe ya
                        if not any(p.get('order_id') == position['order_id'] for p in self.active_trades):
                            self.active_trades.append(position)
                            logger.info(f"Posición cargada desde exchange: {direction} {size} {symbol} a {entry_price}")
                
                # Obtener órdenes abiertas
                open_orders = await self.trade_executor.get_open_orders(self.symbol)
                
                if open_orders:
                    logger.info(f"Se encontraron {len(open_orders)} órdenes abiertas en el exchange para {self.symbol}")
                    
                    # Procesar órdenes abiertas
                    for order in open_orders:
                        # Solo procesar órdenes de mercado o límite
                        if order.get('type') in ['market', 'limit']:
                            # Obtener datos de la orden
                            symbol = order.get('symbol', self.symbol)
                            size = float(order.get('amount', 0))
                            price = float(order.get('price', 0)) if order.get('price') else None
                            side = order.get('side', '')
                            direction = 'long' if side.lower() == 'buy' else 'short'
                            
                            # Si no hay precio (orden de mercado), usar el precio actual
                            if not price:
                                latest_candle = await self.data_fetcher.fetch_latest_candle(symbol, self.timeframe)
                                price = latest_candle.close if latest_candle else 0
                            
                            # Calcular take profit y stop loss
                            if direction == 'long':
                                take_profit = price * (1 + self.take_profit_pct / 100)
                                stop_loss = price * (1 - self.stop_loss_pct / 100)
                            else:  # short
                                take_profit = price * (1 - self.take_profit_pct / 100)
                                stop_loss = price * (1 + self.stop_loss_pct / 100)
                            
                            # Crear objeto de posición
                            position = {
                                'id': order.get('id', f"order_{len(self.active_trades) + 1}"),
                                'symbol': symbol,
                                'direction': direction,
                                'entry_price': price,
                                'size': size,
                                'take_profit': take_profit,
                                'stop_loss': stop_loss,
                                'entry_time': datetime.fromtimestamp(order.get('timestamp', 0)/1000).strftime('%Y-%m-%d %H:%M:%S') if order.get('timestamp') else datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'pattern_id': '',
                                'pattern_name': f'Orden {order.get("type")} desde exchange',
                                'current_pl': 0.0,
                                'current_price': price,
                                'status': 'open',
                                'order_id': order.get('id', '')
                            }
                            
                            # Añadir a posiciones activas si no existe ya
                            if not any(p.get('order_id') == position['order_id'] for p in self.active_trades):
                                self.active_trades.append(position)
                                logger.info(f"Orden cargada desde exchange: {direction} {size} {symbol} a {price}")
            except Exception as ex_error:
                logger.error(f"Error al acceder al exchange: {ex_error}")

           
        if not self.active_trades and hasattr(self, 'pattern_db') and self.pattern_db:
            stored_trades = await self.pattern_db.get_open_trades(self.symbol)
            
            if stored_trades:
                logger.info(f"Se encontraron {len(stored_trades)} operaciones abiertas en la base de datos para {self.symbol}")
                self.active_trades = stored_trades
                
                # Actualizar cada posición con el precio actual
                latest_candle = await self.data_fetcher.fetch_latest_candle(self.symbol, self.timeframe)
                if latest_candle:
                    current_price = latest_candle.close
                    for position in self.active_trades:
                        position['current_price'] = current_price
                        
                        # Recalcular P/L actual
                        entry_price = position.get('entry_price', 0)
                        size = position.get('size', 0)
                        direction = position.get('direction', 'long')
                        
                        if direction == 'long':
                            pl = (current_price - entry_price) * size
                        else:  # short
                            pl = (entry_price - current_price) * size
                        
                        position['current_pl'] = pl
        
        # Mostrar resumen de operaciones cargadas
        if self.active_trades:
            self.log_signal.emit(f"Se cargaron {len(self.active_trades)} operaciones abiertas para {self.symbol}")
            
            # Actualizar interfaz con operaciones cargadas
            self.update_signal.emit({
                'status': 'Operaciones cargadas',
                'open_trades': len(self.active_trades),
                'active_trades': self.active_trades
            })
            
            # Verificar si alguna operación necesita ser cerrada inmediatamente
            await self._check_loaded_operations()
        else:
            logger.info(f"No se encontraron operaciones abiertas para {self.symbol}")

    async def _check_loaded_operations(self):
        """Verifica y gestiona las operaciones cargadas"""
        logger.info("Verificando operaciones cargadas...")
        
        try:
            # Obtener última vela para verificar precios actuales
            latest_candle = await self.data_fetcher.fetch_latest_candle(self.symbol, self.timeframe)
            if not latest_candle:
                logger.warning("No se pudo obtener la última vela para verificar operaciones")
                return
            
            current_price = latest_candle.close
            positions_to_close = []
            
            # Verificar cada posición
            for position in self.active_trades:
                # Actualizar precio actual
                position['current_price'] = current_price
                
                # Obtener datos de la posición
                direction = position.get('direction', 'long')
                take_profit = position.get('take_profit', 0)
                stop_loss = position.get('stop_loss', 0)
                
                # Verificar si se alcanzó take profit o stop loss
                if direction == 'long':
                    if current_price >= take_profit:
                        position['close_reason'] = 'take_profit'
                        positions_to_close.append(position)
                        logger.info(f"Posición cargada alcanzó take profit: {position.get('id')}")
                    elif current_price <= stop_loss:
                        position['close_reason'] = 'stop_loss'
                        positions_to_close.append(position)
                        logger.info(f"Posición cargada alcanzó stop loss: {position.get('id')}")
                else:  # short
                    if current_price <= take_profit:
                        position['close_reason'] = 'take_profit'
                        positions_to_close.append(position)
                        logger.info(f"Posición cargada alcanzó take profit: {position.get('id')}")
                    elif current_price >= stop_loss:
                        position['close_reason'] = 'stop_loss'
                        positions_to_close.append(position)
                        logger.info(f"Posición cargada alcanzó stop loss: {position.get('id')}")
            
            # Cerrar posiciones que alcanzaron take profit o stop loss
            for position in positions_to_close:
                await self._close_position(position)
                self.log_signal.emit(f"Posición cerrada automáticamente: {position.get('direction')} {position.get('symbol')} - Razón: {position.get('close_reason')}")
            
            # Guardar operaciones actualizadas en la base de datos
            if hasattr(self, 'pattern_db') and self.pattern_db:
                for position in self.active_trades:
                    await self.pattern_db.update_trade(position)
                
        except Exception as e:
            logger.error(f"Error al verificar operaciones cargadas: {e}")
    def run(self):
        """Punto de entrada cuando se lanza en un QThread."""
        try:
            # Crear un nuevo loop de eventos para este hilo
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Ejecutar el loop de trading de forma asíncrona
            loop.run_until_complete(self._run_trading_loop())
        except Exception as e:
            logger.error(f"Error en el bot: {e}")
            self.log_signal.emit(f"Error en bot: {e}")
            self.finished_signal.emit(False, str(e))
        finally:
            # Cerrar recursos en un nuevo loop
            try:
                cleanup_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(cleanup_loop)
                cleanup_loop.run_until_complete(self.close())
                cleanup_loop.close()
                logger.info("Recursos del bot liberados correctamente")
            except Exception as e:
                logger.error(f"Error al liberar recursos del bot: {e}")
            
            logger.info("Bot finalizado correctamente.")

    async def _run_trading_loop(self):
        # Inicializar componentes
        success = await self.initialize()
        if not success:
            msg = "No se pudieron inicializar los componentes."
            logger.error(msg)
            self.finished_signal.emit(False, msg)
            return

        # Cargar datos históricos
        logger.info(f"Cargando datos históricos de {self.historical_days} días para {self.symbol}...")
        try:
            candles = await self.data_fetcher.fetch_historical_data(self.symbol, self.timeframe, self.historical_days)
            if not candles:
                raise Exception("No se pudieron cargar datos históricos. Abortando.")
            logger.info(f"Cargadas {len(candles)} velas históricas.")
        except Exception as ex:
            logger.error(f"Error al cargar datos históricos: {ex}")
            self.log_signal.emit(f"Error al cargar datos históricos: {ex}")
            self.finished_signal.emit(False, "No se pudieron cargar datos históricos. Abortando.")
            return

        # Iniciar loop de trading
        self.is_running = True
        self.start_time = datetime.now()
        self.last_check_time = datetime.now()
        
        # Asegurarse de que las operaciones activas estén cargadas
        if not hasattr(self, 'active_trades') or self.active_trades is None:
            self.active_trades = []
            # Intentar cargar operaciones abiertas nuevamente
            await self.reload_open_operations()
        
        if not hasattr(self, 'trade_history'):
            self.trade_history = []
            # Cargar historial de operaciones si es necesario
            if hasattr(self, 'pattern_db') and self.pattern_db:
                try:
                    self.trade_history = await self.pattern_db.get_trade_history(self.symbol, 100)
                    logger.info(f"Se cargaron {len(self.trade_history)} operaciones históricas para {self.symbol}")
                except Exception as hist_error:
                    logger.error(f"Error al cargar historial de operaciones: {hist_error}")
        
        # Ejecutar bots hijos si existen
        if self.bots:
            await self._run_all_bots()

        # Obtener balance inicial
        if hasattr(self, 'trade_executor') and self.trade_executor:
            balance_info = await self.trade_executor.get_balance()
            self.balance = balance_info.get('total', {}).get('USD', 1000.0)
            self.initial_balance = self.balance
        else:
            self.balance = 1000.0
            self.initial_balance = self.balance
        
        logger.info(f"Iniciando loop de trading en modo {self.mode.upper()} con balance inicial: ${self.balance:.2f}")
        
        # Actualizar inmediatamente las posiciones abiertas
        if self.active_trades:
            logger.info(f"Actualizando {len(self.active_trades)} operaciones abiertas al inicio...")
            await self._update_open_positions()
        
        # Bucle principal de trading
        while self.is_running:
            try:
                # Calcular tiempo de ejecución
                runtime = datetime.now() - self.start_time
                runtime_str = str(runtime).split('.')[0]  # Eliminar microsegundos
                
                # Obtener última vela
                latest_candle = await self.data_fetcher.fetch_latest_candle(self.symbol, self.timeframe)
                
                # Verificar si hay una nueva vela
                is_new_candle = False
                if latest_candle and (not self.last_candle or latest_candle.timestamp > self.last_candle.timestamp):
                    self.last_candle = latest_candle
                    is_new_candle = True
                    logger.info(f"Nueva vela detectada: {self.symbol} {self.timeframe} - Precio: {latest_candle.close}")
                
                # Actualizar posiciones abiertas
                if hasattr(self, 'active_trades') and self.active_trades:
                    await self._update_open_positions()
                
                # Buscar nuevas oportunidades de trading si hay una nueva vela
                if is_new_candle:
                    # Obtener últimas N velas para análisis
                    recent_candles = await self.data_fetcher.fetch_recent_candles(self.symbol, self.timeframe, 50)
                    
                    if recent_candles:
                        # Detectar patrones
                        if hasattr(self, 'pattern_detector') and self.pattern_detector:
                            detected_patterns = await self.pattern_detector.detect_patterns(recent_candles)
                            
                            # Registrar patrones detectados
                            if detected_patterns:
                                logger.info(f"Patrones detectados: {len(detected_patterns)}")
                                for pattern in detected_patterns:
                                    logger.info(f"Patrón: {pattern.get('name')}, Dirección: {pattern.get('direction')}, Confianza: {pattern.get('confidence')}")
                                    
                                    # Guardar el patrón en la base de datos para análisis futuro
                                    if hasattr(self, 'pattern_db') and self.pattern_db:
                                        await self.pattern_db.save_pattern(pattern)
                            else:
                                logger.info("No se detectaron patrones en esta vela")
                            
                            # Evaluar patrones y abrir nuevas posiciones si es apropiado
                            if detected_patterns and len(self.active_trades) < getattr(self, 'max_open_trades', 3):
                                await self._evaluate_trading_opportunities(detected_patterns, latest_candle)
                    else:
                        logger.warning(f"No se pudieron obtener velas recientes para {self.symbol}")
                
                # Calcular P/L total
                self.total_pl = self.balance - self.initial_balance
                
                # Actualizar estado en la interfaz
                self.update_signal.emit({
                    'status': 'Ejecutando',
                    'runtime': runtime_str,
                    'open_trades': len(self.active_trades),
                    'balance': self.balance,
                    'total_pl': self.total_pl,
                    'active_trades': self.active_trades,
                    'trade_history': self.trade_history
                })
                
                # Esperar antes del siguiente ciclo
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error en ciclo de trading: {e}")
                self.log_signal.emit(f"Error en ciclo de trading: {e}")
                # Continuar a pesar del error
                await asyncio.sleep(5)
        
        # Finalizar trading
        logger.info("Loop de trading finalizado")
        self.finished_signal.emit(True, "Trading loop finalizado")

    async def _run_all_bots(self):
        """Ejecuta todos los bots en paralelo"""
        if not self.bots:
            logger.info("No hay bots hijos para ejecutar")
            return
            
        # Crear tareas para todos los bots
        tasks = []
        for symbol, bot in self.bots.items():
            # Conectar señales
            bot.log_signal.connect(self.log_signal)
            
            # Usar functools.partial para crear una función parcial
            handler = functools.partial(self._process_bot_update, symbol)
            bot.update_signal.connect(handler)
            
            # Crear tarea
            task = asyncio.create_task(bot._run_trading_loop())
            tasks.append(task)
            
        # Esperar a que todas las tareas terminen o se cancelen
        while self.is_running and tasks:
            done, pending = await asyncio.wait(tasks, timeout=1)
            tasks = list(pending)
            
            # Procesar tareas completadas
            for task in done:
                try:
                    await task
                except Exception as e:
                    logger.error(f"Error en tarea de bot: {e}")


    def _process_bot_update(self, symbol, message):
        """Procesa actualizaciones de los bots individuales"""
        # Añadir símbolo al mensaje
        message['symbol'] = symbol
        
        # Reenviar mensaje
        self.update_signal.emit(message)
        
    def stop(self):
        """Detiene todos los bots"""
        self.is_running = False
        
        # Detener cada bot
        for symbol, bot in self.bots.items():
            bot.stop()
            logger.info(f"Señal de detención enviada al bot de {symbol}")
            
        # Emitir señal de actualización
        self.update_signal.emit({
            'status': 'Deteniendo todos los bots',
            'active_bots': len(self.bots)
        })
        
    async def close(self):
        """Cierra todos los recursos"""
        for symbol, bot in self.bots.items():
            await bot.close()
            logger.info(f"Bot de {symbol} cerrado correctamente")

    async def _update_open_positions(self):
        """Actualiza el estado de las posiciones abiertas"""
        try:
            # Obtener última vela para calcular P/L actual
            latest_candle = self.last_candle
            if not latest_candle:
                return
            
            # Actualizar cada posición activa
            positions_to_close = []
            
            for position in self.active_trades:
                # Obtener precio actual
                current_price = latest_candle.close
                
                # Calcular P/L actual
                entry_price = position.get('entry_price', 0)
                size = position.get('size', 0)
                direction = position.get('direction', 'long')
                
                if direction == 'long':
                    pl = (current_price - entry_price) * size
                else:  # short
                    pl = (entry_price - current_price) * size
                
                # Actualizar P/L en la posición
                position['current_pl'] = pl
                position['current_price'] = current_price
                
                self.update_signal.emit({
                    'status': 'Ejecutando',
                    'open_trades': len(self.active_trades),
                    'balance': self.balance,
                    'total_pl': self.total_pl,
                    'active_trades': self.active_trades,
                    'trade_history': self.trade_history
                })

                # Verificar si se alcanzó take profit o stop loss
                take_profit = position.get('take_profit', 0)
                stop_loss = position.get('stop_loss', 0)
                
                if direction == 'long':
                    if current_price >= take_profit:
                        position['close_reason'] = 'take_profit'
                        positions_to_close.append(position)
                    elif current_price <= stop_loss:
                        position['close_reason'] = 'stop_loss'
                        positions_to_close.append(position)
                else:  # short
                    if current_price <= take_profit:
                        position['close_reason'] = 'take_profit'
                        positions_to_close.append(position)
                    elif current_price >= stop_loss:
                        position['close_reason'] = 'stop_loss'
                        positions_to_close.append(position)
            
            # Cerrar posiciones que alcanzaron take profit o stop loss
            for position in positions_to_close:
                await self._close_position(position)
                
        except Exception as e:
            logger.error(f"Error al actualizar posiciones abiertas: {e}")

    async def _evaluate_trading_opportunities(self, patterns, latest_candle):
        """Evalúa patrones detectados para abrir nuevas posiciones"""
        try:
            # Filtrar patrones con alta confianza
            high_confidence_patterns = [p for p in patterns if p.get('confidence', 0) >= 0.7]
            
            if not high_confidence_patterns:
                logger.info("No se encontraron patrones con suficiente confianza para operar")
                return
            
            # Ordenar por confianza (de mayor a menor)
            sorted_patterns = sorted(high_confidence_patterns, key=lambda x: x.get('confidence', 0), reverse=True)
            
            # Evaluar el patrón de mayor confianza
            best_pattern = sorted_patterns[0]
            pattern_direction = best_pattern.get('direction', '')
            pattern_name = best_pattern.get('name', '')
            pattern_confidence = best_pattern.get('confidence', 0)
            
            logger.info(f"Evaluando patrón: {pattern_name}, Dirección: {pattern_direction}, Confianza: {pattern_confidence}")
            
            # Solo proceder si el patrón tiene una dirección clara
            if pattern_direction not in ['bullish', 'bearish']:
                logger.info(f"Patrón {pattern_name} no tiene dirección clara, no se abrirá posición")
                return
            
            # Convertir dirección del patrón a dirección de la posición
            position_direction = 'long' if pattern_direction == 'bullish' else 'short'
            
            # Obtener configuración de trading
            trading_cfg = self.config.get('trading', {})
            take_profit_pct = trading_cfg.get('take_profit_pct', 2.0)
            stop_loss_pct = trading_cfg.get('stop_loss_pct', 1.0)
            risk_per_trade = trading_cfg.get('risk_per_trade', 0.02)
            
            # Calcular tamaño de la posición basado en riesgo
            risk_amount = self.balance * risk_per_trade
            price = latest_candle.close
            
            # Calcular stop loss y take profit
            if position_direction == 'long':
                stop_loss = price * (1 - stop_loss_pct / 100)
                take_profit = price * (1 + take_profit_pct / 100)
            else:  # short
                stop_loss = price * (1 + stop_loss_pct / 100)
                take_profit = price * (1 - take_profit_pct / 100)
            
            # Calcular tamaño de la posición
            risk_per_unit = abs(price - stop_loss)
            position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
            
            # Limitar el tamaño de la posición
            max_position_size = self.balance * 0.2 / price  # Máximo 20% del balance
            position_size = min(position_size, max_position_size)
            
            if position_size <= 0:
                logger.info("Tamaño de posición calculado es cero o negativo, no se abrirá posición")
                return
            
            logger.info(f"Preparando posición: {position_direction} {position_size} {self.symbol} a {price}")
            logger.info(f"Stop Loss: {stop_loss}, Take Profit: {take_profit}")
            
            # Crear nueva posición
            position = {
                'id': f"trade_{len(self.active_trades) + len(self.trade_history) + 1}",
                'symbol': self.symbol,
                'direction': position_direction,
                'entry_price': price,
                'size': position_size,
                'take_profit': take_profit,
                'stop_loss': stop_loss,
                'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'exit_time': '',
                'exit_price': 0,
                'pl': 0,
                'pattern_id': best_pattern.get('id', ''),
                'pattern_name': pattern_name,
                'current_pl': 0.0,
                'current_price': price,
                'status': 'open',
                'order_id': ''
            }
            
            # Ejecutar la orden si tenemos trade_executor
            if hasattr(self, 'trade_executor') and self.trade_executor:
                side = 'buy' if position_direction == 'long' else 'sell'
                logger.info(f"Ejecutando orden: {side} {position_size} {self.symbol} a {price}")
                
                order = await self.trade_executor.execute_trade(
                    symbol=self.symbol,
                    order_type='market',
                    side=side,
                    amount=position_size
                )
                
                # Si la orden se ejecutó correctamente, añadir a posiciones activas
                if order and 'error' not in order:
                    position['order_id'] = order.get('id', '')
                    self.active_trades.append(position)
                    
                    # Guardar en la base de datos
                    if hasattr(self, 'pattern_db') and self.pattern_db:
                        await self.pattern_db.save_trade(position)
                    
                    logger.info(f"Nueva posición abierta: {position_direction} {position_size} {self.symbol} a {price}")
                    self.log_signal.emit(f"Nueva posición abierta: {position_direction} {position_size} {self.symbol} a {price}")
            else:
                # Modo simulado sin trade_executor
                self.active_trades.append(position)
                
                # Guardar en la base de datos
                if hasattr(self, 'pattern_db') and self.pattern_db:
                    await self.pattern_db.save_trade(position)
                
                logger.info(f"Nueva posición simulada: {position_direction} {position_size} {self.symbol} a {price}")
                self.log_signal.emit(f"Nueva posición simulada: {position_direction} {position_size} {self.symbol} a {price}")
            
        except Exception as e:
            logger.error(f"Error al evaluar oportunidades de trading: {e}")

    async def reload_open_operations(self):
        """Recarga manualmente las operaciones abiertas desde la base de datos"""
        logger.info(f"Recargando operaciones abiertas para {self.symbol}...")
        
        try:
            # Guardar las operaciones actuales en la base de datos antes de recargar
            if hasattr(self, 'active_trades') and self.active_trades and hasattr(self, 'pattern_db') and self.pattern_db:
                for position in self.active_trades:
                    await self.pattern_db.update_trade(position)
            
            # Limpiar operaciones actuales
            self.active_trades = []
            
            # Recargar desde la base de datos
            if hasattr(self, 'pattern_db') and self.pattern_db:
                stored_trades = await self.pattern_db.get_open_trades(self.symbol)
                
                if stored_trades:
                    logger.info(f"Se encontraron {len(stored_trades)} operaciones abiertas en la base de datos para {self.symbol}")
                    self.active_trades = stored_trades
                    
                    # Actualizar cada posición con el precio actual
                    latest_candle = await self.data_fetcher.fetch_latest_candle(self.symbol, self.timeframe)
                    if latest_candle:
                        current_price = latest_candle.close
                        for position in self.active_trades:
                            position['current_price'] = current_price
                            
                            # Recalcular P/L actual
                            entry_price = position.get('entry_price', 0)
                            size = position.get('size', 0)
                            direction = position.get('direction', 'long')
                            
                            if direction == 'long':
                                pl = (current_price - entry_price) * size
                            else:  # short
                                pl = (entry_price - current_price) * size
                            
                            position['current_pl'] = pl
                    
                    # Actualizar interfaz con operaciones cargadas
                    self.update_signal.emit({
                        'status': 'Operaciones recargadas',
                        'open_trades': len(self.active_trades),
                        'active_trades': self.active_trades
                    })
                    
                    self.log_signal.emit(f"Se recargaron {len(self.active_trades)} operaciones abiertas para {self.symbol}")
                    return True
                else:
                    logger.info(f"No se encontraron operaciones abiertas en la base de datos para {self.symbol}")
                    
                    # Actualizar interfaz
                    self.update_signal.emit({
                        'status': 'Sin operaciones abiertas',
                        'open_trades': 0,
                        'active_trades': []
                    })
                    
                    return False
        except Exception as e:
            logger.error(f"Error al recargar operaciones abiertas: {e}")
            self.log_signal.emit(f"Error al recargar operaciones abiertas: {e}")
            return False

    async def _close_position(self, position):
        """Cierra una posición abierta"""
        try:
            # Obtener datos de la posición
            position_id = position.get('id', '')
            symbol = position.get('symbol', self.symbol)
            direction = position.get('direction', 'long')
            size = position.get('size', 0)
            entry_price = position.get('entry_price', 0)
            current_price = position.get('current_price', 0)
            
            # Ejecutar orden de cierre si tenemos trade_executor
            if hasattr(self, 'trade_executor') and self.trade_executor:
                side = 'sell' if direction == 'long' else 'buy'
                order = await self.trade_executor.execute_trade(
                    symbol=symbol,
                    order_type='market',
                    side=side,
                    amount=size
                )
            
            # Calcular P/L final
            if direction == 'long':
                pl = (current_price - entry_price) * size
            else:  # short
                pl = (entry_price - current_price) * size
            
            # Actualizar balance
            self.balance += pl
            
            # Actualizar posición
            position['exit_price'] = current_price
            position['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            position['pl'] = pl
            position['status'] = 'closed'
            
            # Eliminar de posiciones activas
            self.active_trades = [p for p in self.active_trades if p.get('id') != position_id]
            
            # Añadir al historial
            self.trade_history.append(position)
            
            # Guardar en la base de datos
            if hasattr(self, 'pattern_db') and self.pattern_db:
                try:
                    # Actualizar la operación en la base de datos
                    await self.pattern_db.update_trade(position)
                    
                    # Actualizar estadísticas del patrón si existe
                    if position.get('pattern_id'):
                        pattern = next((p for p in await self.pattern_db.get_all_patterns() 
                                    if p['id'] == position.get('pattern_id')), None)
                        if pattern:
                            # Actualizar estadísticas del patrón
                            if pl > 0:
                                pattern['success_count'] = pattern.get('success_count', 0) + 1
                            else:
                                pattern['failure_count'] = pattern.get('failure_count', 0) + 1
                                
                            pattern['total_occurrences'] = pattern.get('total_occurrences', 0) + 1
                            total = pattern['success_count'] + pattern['failure_count']
                            pattern['success_rate'] = (pattern['success_count'] / total) if total > 0 else 0
                            
                            # Añadir resultado al historial
                            if not pattern.get('historical_results'):
                                pattern['historical_results'] = []
                            
                            pattern['historical_results'].append({
                                'timestamp': datetime.now().timestamp(),
                                'symbol': symbol,
                                'direction': direction,
                                'pl': pl,
                                'success': pl > 0
                            })
                            
                            # Guardar patrón actualizado
                            await self.pattern_db.save_pattern(pattern)
                except Exception as db_error:
                    logger.error(f"Error al actualizar la base de datos: {db_error}")
            
            logger.info(f"Posición cerrada: {direction} {size} {symbol} - P/L: ${pl:.2f}")
            self.log_signal.emit(f"Posición cerrada: {direction} {size} {symbol} - P/L: ${pl:.2f}")
            
            # Actualizar interfaz
            self.update_signal.emit({
                'status': 'Operación cerrada',
                'open_trades': len(self.active_trades),
                'balance': self.balance,
                'total_pl': self.total_pl,
                'active_trades': self.active_trades,
                'trade_history': self.trade_history
            })
            
        except Exception as e:
            logger.error(f"Error al cerrar posición: {e}")
            self.log_signal.emit(f"Error al cerrar posición: {e}")

    async def close(self):
        """Libera recursos."""
        logger.info("Liberando recursos del bot...")
        try:
            # Cerrar posiciones abiertas
            for position in self.active_trades:
                await self._close_position(position)
            
            # Cerrar componentes
            components_to_close = [
                ('trade_executor', getattr(self, 'trade_executor', None)),
                ('data_fetcher', getattr(self, 'data_fetcher', None)),
                ('pattern_detector', getattr(self, 'pattern_detector', None)),
                ('pattern_db', getattr(self, 'pattern_db', None))
            ]
            
            for name, component in components_to_close:
                if component and hasattr(component, 'close') and callable(component.close):
                    try:
                        await component.close()
                        logger.info(f"{name} cerrado correctamente")
                    except Exception as e:
                        logger.error(f"Error al cerrar {name}: {e}")
            
            # Cerrar sesiones aiohttp pendientes
            try:
                import aiohttp
                import gc
                
                # Intentar cerrar sesiones aiohttp pendientes
                for obj in gc.get_objects():
                    if isinstance(obj, aiohttp.ClientSession) and not obj.closed:
                        await obj.close()
                        logger.info("Sesión aiohttp cerrada correctamente")
            except Exception as e:
                logger.error(f"Error al cerrar sesiones aiohttp: {e}")
            
            # Cerrar exchanges de ccxt pendientes
            try:
                import ccxt.async_support as ccxtasync
                
                # Cerrar todos los exchanges asíncronos
                for obj in gc.get_objects():
                    if isinstance(obj, ccxtasync.Exchange):
                        try:
                            await obj.close()
                            logger.info(f"Exchange ccxt {obj.id} cerrado correctamente")
                        except Exception as ex:
                            logger.error(f"Error al cerrar exchange ccxt {getattr(obj, 'id', 'unknown')}: {ex}")
            except Exception as e:
                logger.error(f"Error al cerrar exchanges ccxt: {e}")
                
            logger.info("Recursos del bot liberados correctamente")
        except Exception as e:
            logger.error(f"Error liberando recursos: {e}")

    def stop(self):
        """Señal para detener loop en vivo."""
        self.is_running = False
        logger.info("Señal de stop enviada al bot. Deteniendo operaciones...")
        
        # Emitir señal de actualización para informar a la UI
        self.update_signal.emit({
            'status': 'Deteniendo',
            'open_trades': len(getattr(self, 'active_trades', [])),
            'balance': getattr(self, 'balance', 0.0),
            'total_pl': getattr(self, 'total_pl', 0.0)
        })
        
        # Crear un nuevo loop para cerrar recursos
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.close())
            loop.close()
        except Exception as e:
            logger.error(f"Error al cerrar recursos en stop(): {e}")
