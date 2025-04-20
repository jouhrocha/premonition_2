# core/pattern_analyzer.py
import logging
import asyncio
import json
import os
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

from utils.database import PatternDatabase
from core.data_fetcher import DataFetcher, Candle

logger = logging.getLogger(__name__)

class PatternAnalyzer:
    """Analizador de patrones de trading"""
    
    def __init__(self, config: Dict[str, Any], pattern_db: Optional[PatternDatabase] = None):
        """
        Inicializa el analizador de patrones
        
        Args:
            config: Configuración del analizador
            pattern_db: Base de datos de patrones (opcional)
        """
        self.config = config
        self.pattern_db = pattern_db
        
        # Configuración de análisis
        analysis_config = config.get('pattern_analysis', {})
        self.min_success_rate = analysis_config.get('min_success_rate', 60.0)
        self.lookback_candles = analysis_config.get('lookback_candles', 5)
        self.lookforward_candles = analysis_config.get('lookforward_candles', 10)
        self.min_profit_ratio = analysis_config.get('min_profit_ratio', 1.5)
        self.max_error_rate = analysis_config.get('max_error_rate', 5.0)
        
        # Configuración de trading
        trading_config = config.get('trading', {})
        self.symbol = trading_config.get('symbol', 'BTC/USD')
        self.timeframe = trading_config.get('timeframe', '1h')
        
        # Inicializar data fetcher
        self.data_fetcher = None
        self.patterns = []
    
    async def initialize(self):
        """Inicializa el analizador de patrones"""
        try:
            # Inicializar data fetcher si no se proporcionó
            if not self.data_fetcher:
                self.data_fetcher = DataFetcher(self.config)
                await self.data_fetcher.initialize()
            
            # Inicializar base de datos si no se proporcionó
            if not self.pattern_db:
                db_path = self.config.get('database', {}).get('path', 'data/patterns.db')
                self.pattern_db = PatternDatabase(db_path)
                await self.pattern_db.initialize()
            
            # Cargar patrones existentes
            self.patterns = await self.pattern_db.get_all_patterns()
            
            return True
        except Exception as e:
            logger.error(f"Error al inicializar el analizador de patrones: {e}")
            return False
    
    async def run_analysis(self) -> List[Dict[str,Any]]:
        """Analiza patrones en los datos históricos."""
        try:
            # Obtener datos históricos
            if not hasattr(self, 'data_fetcher'):
                from core.data_fetcher import DataFetcher
                self.data_fetcher = DataFetcher(self.config)
                await self.data_fetcher.initialize()
            
            symbol = self.config.get('trading', {}).get('symbol', 'BTC/USD')
            timeframe = self.config.get('trading', {}).get('timeframe', '1h')
            days = 90  # Analizar 90 días de datos
            
            logger.info(f"Obteniendo datos históricos para análisis de patrones: {symbol} {timeframe}")
            candles = await self.data_fetcher.fetch_historical_data(symbol, timeframe, days)
            
            if not candles:
                logger.warning(f"No se pudieron obtener datos históricos para {symbol}")
                return []
            
            logger.info(f"Analizando {len(candles)} velas para detectar patrones")
            
            # Inicializar detector de patrones
            from core.pattern_detector import PatternDetector
            pattern_detector = PatternDetector(self.pattern_db)
            await pattern_detector.load_patterns()
            
            # Detectar patrones en ventanas deslizantes
            all_patterns = []
            window_size = 50  # Tamaño de la ventana de análisis
            
            for i in range(len(candles) - window_size):
                window = candles[i:i+window_size]
                patterns = await pattern_detector.detect_patterns(window)
                
                # Verificar resultados de los patrones
                for pattern in patterns:
                    # Obtener velas posteriores para verificar resultado
                    future_window = 10  # Velas a mirar hacia adelante
                    if i + window_size + future_window <= len(candles):
                        future_candles = candles[i+window_size:i+window_size+future_window]
                        
                        # Determinar resultado del patrón
                        entry_price = window[-1].close
                        direction = pattern.get('direction', '')
                        
                        if direction == 'bullish':
                            # Para patrones alcistas, verificar si el precio subió
                            max_price = max(c.high for c in future_candles)
                            min_price = min(c.low for c in future_candles)
                            
                            # Si el precio subió al menos 1.5%, es exitoso
                            if max_price >= entry_price * 1.015:
                                pattern['result'] = 'success'
                                pattern['profit_loss'] = (max_price - entry_price) / entry_price * 100
                            # Si el precio bajó más de 1%, es fallido
                            elif min_price <= entry_price * 0.99:
                                pattern['result'] = 'failure'
                                pattern['profit_loss'] = (min_price - entry_price) / entry_price * 100
                            else:
                                pattern['result'] = 'neutral'
                                pattern['profit_loss'] = 0.0
                        
                        elif direction == 'bearish':
                            # Para patrones bajistas, verificar si el precio bajó
                            max_price = max(c.high for c in future_candles)
                            min_price = min(c.low for c in future_candles)
                            
                            # Si el precio bajó al menos 1.5%, es exitoso
                            if min_price <= entry_price * 0.985:
                                pattern['result'] = 'success'
                                pattern['profit_loss'] = (entry_price - min_price) / entry_price * 100
                            # Si el precio subió más de 1%, es fallido
                            elif max_price >= entry_price * 1.01:
                                pattern['result'] = 'failure'
                                pattern['profit_loss'] = (entry_price - max_price) / entry_price * 100
                            else:
                                pattern['result'] = 'neutral'
                                pattern['profit_loss'] = 0.0
                    
                    # Añadir a la lista de patrones
                    all_patterns.append(pattern)
            
            # Agrupar patrones por nombre y calcular estadísticas
            pattern_stats = {}
            for pattern in all_patterns:
                name = pattern.get('name', '')
                if name not in pattern_stats:
                    pattern_stats[name] = {
                        'id': name.lower().replace(' ', '_'),
                        'name': name,
                        'type': pattern.get('type', ''),
                        'direction': pattern.get('direction', ''),
                        'success_count': 0,
                        'failure_count': 0,
                        'neutral_count': 0,
                        'total_occurrences': 0,
                        'total_profit': 0.0,
                        'total_loss': 0.0,
                        'success_rate': 0.0,
                        'avg_profit': 0.0,
                        'avg_loss': 0.0,
                        'profit_factor': 0.0
                    }
                
                # Actualizar estadísticas
                result = pattern.get('result', '')
                profit_loss = pattern.get('profit_loss', 0.0)
                
                pattern_stats[name]['total_occurrences'] += 1
                
                if result == 'success':
                    pattern_stats[name]['success_count'] += 1
                    pattern_stats[name]['total_profit'] += profit_loss
                elif result == 'failure':
                    pattern_stats[name]['failure_count'] += 1
                    pattern_stats[name]['total_loss'] += abs(profit_loss)
                else:
                    pattern_stats[name]['neutral_count'] += 1
            
            # Calcular métricas finales
            for name, stats in pattern_stats.items():
                total = stats['total_occurrences']
                if total > 0:
                    stats['success_rate'] = (stats['success_count'] / total) * 100
                
                if stats['success_count'] > 0:
                    stats['avg_profit'] = stats['total_profit'] / stats['success_count']
                
                if stats['failure_count'] > 0:
                    stats['avg_loss'] = stats['total_loss'] / stats['failure_count']
                
                if stats['total_loss'] > 0:
                    stats['profit_factor'] = stats['total_profit'] / stats['total_loss']
                else:
                    stats['profit_factor'] = float('inf')
            
            # Guardar patrones en la base de datos
            for stats in pattern_stats.values():
                await self.pattern_db.save_pattern(stats)
            
            # Filtrar patrones confiables
            reliable_patterns = [
                stats for stats in pattern_stats.values()
                if stats['success_rate'] >= self.min_success_rate and stats['total_occurrences'] >= 10
            ]
            
            logger.info(f"Patrones confiables: {len(reliable_patterns)}")
            return reliable_patterns
            
        except Exception as e:
            logger.error(f"Error en el análisis de patrones: {e}")
            return []

    async def _identify_patterns(self, candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identifica patrones potenciales en los datos históricos
        
        Args:
            candles: Lista de velas en formato dict
            
        Returns:
            Lista de patrones potenciales
        """
        if len(candles) < (self.lookback_candles + self.lookforward_candles):
            logger.warning("Datos insuficientes para identificar patrones")
            return []
        
        potential_patterns = []
        
        # Analizar cada segmento de velas
        for i in range(len(candles) - (self.lookback_candles + self.lookforward_candles)):
            # Obtener segmento de velas para el patrón
            pattern_candles = candles[i:i+self.lookback_candles]
            
            # Obtener velas de resultado (para verificar si el patrón fue exitoso)
            result_candles = candles[i+self.lookback_candles:i+self.lookback_candles+self.lookforward_candles]
            
            # Extraer características del patrón
            features = self._extract_features(pattern_candles)
            
            # Determinar dirección del patrón (alcista o bajista)
            direction = self._determine_pattern_direction(pattern_candles)
            
            # Determinar resultado del patrón
            result, profit_loss = self._determine_pattern_result(direction, pattern_candles, result_candles)
            
            # Generar ID único para el patrón
            pattern_id = self._generate_pattern_id(features)
            
            # Crear patrón
            pattern = {
                "id": pattern_id,
                "name": f"Pattern-{pattern_id[:6]}",
                "type": "price_action",
                "features": features,
                "direction": direction,
                "result": result,
                "profit_loss": profit_loss,
                "timestamp": pattern_candles[-1].get("timestamp", 0),
                "success_count": 1 if result == "success" else 0,
                "failure_count": 1 if result == "failure" else 0,
                "total_occurrences": 1,
                "success_rate": 100.0 if result == "success" else 0.0,
                "last_updated": int(datetime.now().timestamp())
            }
            
            # Agregar a la lista de patrones potenciales
            potential_patterns.append(pattern)
        
        return potential_patterns
    
    def _extract_features(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extrae características relevantes de una serie de velas
        
        Args:
            candles: Lista de velas
            
        Returns:
            Diccionario con características extraídas
        """
        if not candles:
            return {}
        
        # Características básicas
        features = {
            "candle_count": len(candles),
            "price_movement": [],
            "volume_profile": [],
            "candle_sizes": [],
            "wicks_ratio": []
        }
        
        # Calcular movimientos de precio y volumen
        for i, candle in enumerate(candles):
            # Movimiento de precio (% de cambio)
            if i > 0:
                prev_close = candles[i-1].get("close", 0)
                curr_close = candle.get("close", 0)
                if prev_close > 0:
                    price_change = (curr_close - prev_close) / prev_close * 100
                    features["price_movement"].append(round(price_change, 2))
            
            # Tamaño de la vela (% del rango)
            open_price = candle.get("open", 0)
            close = candle.get("close", 0)
            high = candle.get("high", 0)
            low = candle.get("low", 0)
            
            if high > low:
                body_size = abs(close - open_price) / (high - low) * 100
                features["candle_sizes"].append(round(body_size, 2))
                
                # Ratio de mechas (superior e inferior)
                upper_wick = (high - max(open_price, close)) / (high - low) * 100
                lower_wick = (min(open_price, close) - low) / (high - low) * 100
                features["wicks_ratio"].append([round(upper_wick, 2), round(lower_wick, 2)])
            
            # Perfil de volumen (normalizado)
            volume = candle.get("volume", 0)
            features["volume_profile"].append(volume)
        
        # Normalizar volumen si hay datos
        if features["volume_profile"]:
            max_vol = max(features["volume_profile"])
            if max_vol > 0:
                features["volume_profile"] = [round(v / max_vol, 2) for v in features["volume_profile"]]
        
        return features
    
    def _determine_pattern_direction(self, candles: List[Dict[str, Any]]) -> str:
        """
        Determina la dirección esperada del patrón (alcista o bajista)
        
        Args:
            candles: Lista de velas del patrón
            
        Returns:
            Dirección del patrón ("bullish" o "bearish")
        """
        if not candles:
            return "neutral"
        
        # Obtener precios de cierre
        closes = [c.get("close", 0) for c in candles]
        
        # Calcular tendencia
        if len(closes) >= 3:
            # Usar regresión lineal simple
            n = len(closes)
            x = list(range(n))
            sum_x = sum(x)
            sum_y = sum(closes)
            sum_xy = sum(x[i] * closes[i] for i in range(n))
            sum_xx = sum(x[i] ** 2 for i in range(n))
            
            # Calcular pendiente
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x ** 2) if (n * sum_xx - sum_x ** 2) != 0 else 0
            
            if slope > 0:
                return "bullish"
            elif slope < 0:
                return "bearish"
        
        # Si no hay suficientes datos o la pendiente es 0
        return "neutral"
    
    def _determine_pattern_result(self, direction: str, pattern_candles: List[Dict[str, Any]], 
                                 result_candles: List[Dict[str, Any]]) -> tuple:
        """
        Determina si el patrón fue exitoso basado en el movimiento posterior
        
        Args:
            direction: Dirección esperada del patrón
            pattern_candles: Velas del patrón
            result_candles: Velas posteriores al patrón
            
        Returns:
            Tupla (resultado, profit_loss)
        """
        if not pattern_candles or not result_candles or direction == "neutral":
            return "unknown", 0.0
        
        # Precio de referencia (último cierre del patrón)
        reference_price = pattern_candles[-1].get("close", 0)
        if reference_price == 0:
            return "unknown", 0.0
        
        # Precios máximo y mínimo en el período de resultado
        max_price = max(c.get("high", 0) for c in result_candles)
        min_price = min(c.get("low", 0) for c in result_candles)
        
        # Calcular movimientos porcentuales
        max_move_pct = (max_price - reference_price) / reference_price * 100
        min_move_pct = (min_price - reference_price) / reference_price * 100
        
        # Determinar resultado según la dirección
        if direction == "bullish":
            # Para patrones alcistas, esperamos que el precio suba
            if max_move_pct >= 1.0:  # Al menos 1% de subida
                return "success", max_move_pct
            elif min_move_pct <= -2.0:  # Más de 2% de bajada
                return "failure", min_move_pct
        elif direction == "bearish":
            # Para patrones bajistas, esperamos que el precio baje
            if min_move_pct <= -1.0:  # Al menos 1% de bajada
                return "success", -min_move_pct  # Convertir a positivo para P/L
            elif max_move_pct >= 2.0:  # Más de 2% de subida
                return "failure", -max_move_pct  # Convertir a negativo para P/L
        
        # Si no cumple los criterios claros
        return "neutral", 0.0
    
    def _generate_pattern_id(self, features: Dict[str, Any]) -> str:
        """
        Genera un ID único para un patrón basado en sus características
        
        Args:
            features: Características del patrón
            
        Returns:
            ID único del patrón
        """
        # Convertir características a JSON y generar hash
        features_json = json.dumps(features, sort_keys=True)
        pattern_hash = hashlib.md5(features_json.encode()).hexdigest()
        return pattern_hash[:12]  # Usar primeros 12 caracteres del hash
    
    async def _analyze_pattern_performance(self, patterns: List[Dict[str, Any]], 
                                         candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analiza el rendimiento de los patrones identificados
        
        Args:
            patterns: Lista de patrones potenciales
            candles: Lista completa de velas
            
        Returns:
            Lista de patrones con métricas de rendimiento
        """
        # Agrupar patrones por ID
        patterns_by_id = {}
        for pattern in patterns:
            pattern_id = pattern.get("id", "")
            if pattern_id not in patterns_by_id:
                patterns_by_id[pattern_id] = []
            patterns_by_id[pattern_id].append(pattern)
        
        # Analizar cada grupo de patrones
        analyzed_patterns = []
        
        for pattern_id, pattern_group in patterns_by_id.items():
            if len(pattern_group) == 0:
                continue
            
            # Usar el primer patrón como base
            base_pattern = pattern_group[0].copy()
            
            # Calcular métricas agregadas
            total_occurrences = len(pattern_group)
            success_count = sum(1 for p in pattern_group if p.get("result", "") == "success")
            failure_count = sum(1 for p in pattern_group if p.get("result", "") == "failure")
            
            # Calcular tasa de éxito
            success_rate = (success_count / total_occurrences) * 100 if total_occurrences > 0 else 0
            
            # Calcular ratio de beneficio/pérdida
            profit_sum = sum(p.get("profit_loss", 0) for p in pattern_group if p.get("profit_loss", 0) > 0)
            loss_sum = sum(abs(p.get("profit_loss", 0)) for p in pattern_group if p.get("profit_loss", 0) < 0)
            
            profit_loss_ratio = profit_sum / loss_sum if loss_sum > 0 else float('inf')
            
            # Actualizar métricas en el patrón base
            base_pattern.update({
                "total_occurrences": total_occurrences,
                "success_count": success_count,
                "failure_count": failure_count,
                "success_rate": round(success_rate, 2),
                "profit_loss_ratio": round(profit_loss_ratio, 2) if profit_loss_ratio != float('inf') else 999.99,
                "last_updated": int(datetime.now().timestamp()),
                "historical_results": [
                    {
                        "timestamp": p.get("timestamp", 0),
                        "result": p.get("result", ""),
                        "profit_loss": p.get("profit_loss", 0)
                    }
                    for p in pattern_group
                ]
            })
            
            analyzed_patterns.append(base_pattern)
        
        return analyzed_patterns
    
    async def close(self):
        """Cierra conexiones y libera recursos"""
        try:
            if self.data_fetcher and hasattr(self.data_fetcher, 'close'):
                await self.data_fetcher.close()
            
            if self.pattern_db and hasattr(self.pattern_db, 'close'):
                await self.pattern_db.close()
        except Exception as e:
            logger.error(f"Error al cerrar recursos del analizador de patrones: {e}")
