# core/backtester.py
import logging
import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from utils.database import PatternDatabase
from core.data_fetcher import DataFetcher
from core.pattern_detector import PatternDetector
from models.candle import Candle

logger = logging.getLogger('backtester')

class Backtester:
    """Backtester para estrategias de trading"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa el backtester
        
        Args:
            config: Configuración del backtester
        """
        self.config = config
        
        # Configuración de trading
        trading_config = config.get('trading', {})
        self.symbol = trading_config.get('symbol', 'BTC/USD')
        self.timeframe = trading_config.get('timeframe', '1h')
        
        # Configuración de backtest
        backtest_config = config.get('backtest', {})
        self.initial_capital = backtest_config.get('initial_capital', 1000.0)
        self.risk_per_trade = backtest_config.get('risk_per_trade', 0.02)  # 2% por defecto
        self.take_profit_pct = backtest_config.get('take_profit_pct', 2.0)
        self.stop_loss_pct = backtest_config.get('stop_loss_pct', 1.0)
        
        # Período de backtest
        self.backtest_days = backtest_config.get('days', 90)  # 90 días por defecto
        
        # Componentes
        self.data_fetcher = None
        self.pattern_detector = None
        self.pattern_db = None
        
        # Resultados
        self.results = {}
        
        logger.info("Backtester inicializado.")
    
    async def initialize(self):
        """Inicializa los componentes del backtester"""
        try:
            # Inicializar base de datos
            db_path = self.config.get('database', {}).get('path', 'data/patterns.db')
            self.pattern_db = PatternDatabase(db_path)
            await self.pattern_db.initialize()
            
            # Inicializar data fetcher
            self.data_fetcher = DataFetcher(self.config)
            await self.data_fetcher.initialize()
            
            # Inicializar detector de patrones
            self.pattern_detector = PatternDetector(self.pattern_db)
            await self.pattern_detector.load_patterns()
            
            return True
        except Exception as e:
            logger.error(f"Error al inicializar componentes del backtester: {e}")
            return False
    
    async def run_backtest(self) -> Dict[str, Any]:
        """
        Ejecuta el backtest
        
        Returns:
            Resultados del backtest
        """
        logger.info(f"Ejecutando backtest para {self.symbol} en {self.timeframe}")
        
        try:
            # Obtener datos históricos
            candles = await self.data_fetcher.fetch_historical_data(
                symbol=self.symbol,
                timeframe=self.timeframe,
                days=self.backtest_days
            )
            
            if not candles:
                logger.error(f"No se pudieron obtener datos históricos para {self.symbol}")
                return {"error": "No se pudieron obtener datos históricos"}
            
            # Ejecutar simulación
            results = await self._simulate_trading(candles)
            
            return results
        
        except Exception as e:
            logger.error(f"Error en el backtest: {e}")
            return {"error": str(e)}
    
    async def _simulate_trading(self, candles: List[Candle]) -> Dict[str, Any]:
        """
        Simula operaciones de trading en datos históricos
        
        Args:
            candles: Lista de velas históricas
            
        Returns:
            Resultados de la simulación
        """
        # Inicializar variables de seguimiento
        balance = self.initial_capital
        trades = []
        open_positions = []
        
        # Estadísticas
        total_trades = 0
        winning_trades = 0
        losing_trades = 0
        total_profit = 0.0
        total_loss = 0.0
        
        # Recorrer velas (dejando suficientes para lookback)
        lookback = 20  # Velas necesarias para análisis técnico
        
        for i in range(lookback, len(candles)):
            current_candle = candles[i]
            lookback_candles = candles[i-lookback:i]
            
            # Actualizar posiciones abiertas
            await self._update_positions(open_positions, current_candle, trades)
            
            # Detectar patrones en las velas de lookback
            detected_patterns = await self.pattern_detector.detect_patterns(lookback_candles + [current_candle])
            
            # Si se detectaron patrones, evaluar entrada
            for pattern in detected_patterns:
                # Solo considerar patrones con buena tasa de éxito
                if pattern.get('success_rate', 0) >= 60:
                    # Calcular tamaño de posición basado en riesgo
                    position_size = self._calculate_position_size(
                        balance, 
                        current_candle.close, 
                        self.risk_per_trade, 
                        self.stop_loss_pct
                    )
                    
                    # Crear nueva posición
                    direction = pattern.get('direction', 'neutral')
                    if direction in ['bullish', 'bearish']:
                        position = {
                            'id': f"trade_{total_trades + 1}",
                            'pattern_id': pattern.get('id', ''),
                            'pattern_name': pattern.get('name', ''),
                            'entry_price': current_candle.close,
                            'entry_time': current_candle.timestamp,
                            'direction': direction,
                            'size': position_size,
                            'stop_loss': self._calculate_stop_loss(current_candle.close, direction, self.stop_loss_pct),
                            'take_profit': self._calculate_take_profit(current_candle.close, direction, self.take_profit_pct),
                            'status': 'open',
                            'exit_price': None,
                            'exit_time': None,
                            'profit_loss': 0.0,
                            'profit_loss_pct': 0.0
                        }
                        
                        # Añadir a posiciones abiertas
                        open_positions.append(position)
                        total_trades += 1
        
        # Cerrar posiciones abiertas al final del backtest
        if open_positions:
            last_candle = candles[-1]
            for position in open_positions:
                position['status'] = 'closed'
                position['exit_price'] = last_candle.close
                position['exit_time'] = last_candle.timestamp
                
                # Calcular P/L
                pl = self._calculate_profit_loss(
                    position['entry_price'],
                    position['exit_price'],
                    position['direction'],
                    position['size']
                )
                
                position['profit_loss'] = pl
                position['profit_loss_pct'] = (pl / (position['entry_price'] * position['size'])) * 100
                
                # Actualizar balance
                balance += pl
                
                # Actualizar estadísticas
                if pl > 0:
                    winning_trades += 1
                    total_profit += pl
                else:
                    losing_trades += 1
                    total_loss += abs(pl)
                
                # Añadir a trades completados
                trades.append(position)
            
            # Limpiar posiciones abiertas
            open_positions = []
        
        # Calcular estadísticas finales
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        total_return = ((balance - self.initial_capital) / self.initial_capital) * 100
        
        # Preparar resultados
        results = {
            'initial_capital': self.initial_capital,
            'final_balance': balance,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2),
            'total_return': round(total_return, 2),
            'trades': trades
        }
        
        return results
    
    async def _update_positions(self, positions: List[Dict[str, Any]], current_candle: Candle, 
                              completed_trades: List[Dict[str, Any]]):
        """
        Actualiza el estado de las posiciones abiertas
        
        Args:
            positions: Lista de posiciones abiertas
            current_candle: Vela actual
            completed_trades: Lista de trades completados
        """
        positions_to_remove = []
        
        for position in positions:
            # Comprobar si se alcanzó stop loss
            if (position['direction'] == 'bullish' and current_candle.low <= position['stop_loss']) or \
               (position['direction'] == 'bearish' and current_candle.high >= position['stop_loss']):
                # Cerrar posición con stop loss
                position['status'] = 'closed'
                position['exit_price'] = position['stop_loss']
                position['exit_time'] = current_candle.timestamp
                
                # Calcular P/L
                pl = self._calculate_profit_loss(
                    position['entry_price'],
                    position['exit_price'],
                    position['direction'],
                    position['size']
                )
                
                position['profit_loss'] = pl
                position['profit_loss_pct'] = (pl / (position['entry_price'] * position['size'])) * 100
                
                # Añadir a trades completados
                completed_trades.append(position)
                positions_to_remove.append(position)
            
            # Comprobar si se alcanzó take profit
            elif (position['direction'] == 'bullish' and current_candle.high >= position['take_profit']) or \
                 (position['direction'] == 'bearish' and current_candle.low <= position['take_profit']):
                # Cerrar posición con take profit
                position['status'] = 'closed'
                position['exit_price'] = position['take_profit']
                position['exit_time'] = current_candle.timestamp
                
                # Calcular P/L
                pl = self._calculate_profit_loss(
                    position['entry_price'],
                    position['exit_price'],
                    position['direction'],
                    position['size']
                )
                
                position['profit_loss'] = pl
                position['profit_loss_pct'] = (pl / (position['entry_price'] * position['size'])) * 100
                
                # Añadir a trades completados
                completed_trades.append(position)
                positions_to_remove.append(position)
        
        # Eliminar posiciones cerradas
        for position in positions_to_remove:
            positions.remove(position)
    
    def _calculate_position_size(self, balance: float, price: float, risk_pct: float, stop_loss_pct: float) -> float:
        """
        Calcula el tamaño de posición basado en riesgo
        
        Args:
            balance: Balance actual
            price: Precio de entrada
            risk_pct: Porcentaje de riesgo (0-1)
            stop_loss_pct: Porcentaje de stop loss (0-100)
            
        Returns:
            Tamaño de posición
        """
        risk_amount = balance * risk_pct
        stop_loss_amount = price * (stop_loss_pct / 100)
        
        if stop_loss_amount <= 0:
            return 0
        
        return risk_amount / stop_loss_amount
    
    def _calculate_stop_loss(self, price: float, direction: str, stop_loss_pct: float) -> float:
        """
        Calcula el nivel de stop loss
        
        Args:
            price: Precio de entrada
            direction: Dirección de la posición ('bullish' o 'bearish')
            stop_loss_pct: Porcentaje de stop loss (0-100)
            
        Returns:
            Nivel de stop loss
        """
        if direction == 'bullish':
            return price * (1 - stop_loss_pct / 100)
        else:  # bearish
            return price * (1 + stop_loss_pct / 100)
    
    def _calculate_take_profit(self, price: float, direction: str, take_profit_pct: float) -> float:
        """
        Calcula el nivel de take profit
        
        Args:
            price: Precio de entrada
            direction: Dirección de la posición ('bullish' o 'bearish')
            take_profit_pct: Porcentaje de take profit (0-100)
            
        Returns:
            Nivel de take profit
        """
        if direction == 'bullish':
            return price * (1 + take_profit_pct / 100)
        else:  # bearish
            return price * (1 - take_profit_pct / 100)
    
    def _calculate_profit_loss(self, entry_price: float, exit_price: float, direction: str, size: float) -> float:
        """
        Calcula el beneficio/pérdida de una operación
        
        Args:
            entry_price: Precio de entrada
            exit_price: Precio de salida
            direction: Dirección de la posición ('bullish' o 'bearish')
            size: Tamaño de la posición
            
        Returns:
            Beneficio/pérdida
        """
        if direction == 'bullish':
            return (exit_price - entry_price) * size
        else:  # bearish
            return (entry_price - exit_price) * size
