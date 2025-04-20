# core/pattern_detector.py
import logging
from typing import List, Dict, Any
import numpy as np # type: ignore
import talib # type: ignore
from models.candle import Candle
from utils.database import PatternDatabase

logger = logging.getLogger(__name__)

class PatternDetector:
    """Detector de patrones de velas con TA-Lib."""

    def __init__(self, pattern_db: PatternDatabase):
        self.pattern_db = pattern_db
        self.patterns = []
        self.pattern_functions = {
            'CDLDOJI': ('Doji', self._detect_doji),
            'CDLHAMMER': ('Hammer', self._detect_hammer),
            'CDLENGULFING': ('Engulfing', self._detect_engulfing),
            'CDLMORNINGSTAR': ('Morning Star', self._detect_morning_star),
            'CDLEVENINGSTAR': ('Evening Star', self._detect_evening_star),
            'CDLHARAMI': ('Harami', self._detect_harami),
            'CDLPIERCING': ('Piercing', self._detect_piercing),
            'CDLDARKCLOUDCOVER': ('Dark Cloud Cover', self._detect_dark_cloud_cover),
            'CDLSHOOTINGSTAR': ('Shooting Star', self._detect_shooting_star),
            'CDLMARUBOZU': ('Marubozu', self._detect_marubozu)
        }

    async def load_patterns(self):
        self.patterns = await self.pattern_db.get_all_patterns()
        logger.info(f"Patrones cargados: {len(self.patterns)}")

    async def detect_patterns(self, candles: List[Candle]) -> List[Dict[str,Any]]:
        """
        Detecta patrones en una lista de velas usando TA-Lib.
        
        Args:
            candles: Lista de velas
            
        Returns:
            Lista de patrones detectados
        """
        if len(candles) < 10:  # Necesitamos suficientes velas para detectar patrones
            logger.warning(f"No hay suficientes velas para detectar patrones: {len(candles)}")
            return []
        
        try:
            # Convertir velas a arrays numpy para TA-Lib
            opens = np.array([c.open for c in candles], dtype=float)
            highs = np.array([c.high for c in candles], dtype=float)
            lows = np.array([c.low for c in candles], dtype=float)
            closes = np.array([c.close for c in candles], dtype=float)
            
            # Verificar que los arrays tienen datos válidos
            if len(opens) == 0 or len(highs) == 0 or len(lows) == 0 or len(closes) == 0:
                logger.warning("Arrays de datos vacíos para la detección de patrones")
                return []
            
            # Detectar patrones
            results = []
            
            # Ejecutar todas las funciones de detección
            for pattern_name, (pattern_label, detect_func) in self.pattern_functions.items():
                try:
                    patterns = detect_func(opens, highs, lows, closes)
                    if patterns:
                        logger.info(f"Patrón detectado: {pattern_label}")
                        results.extend(patterns)
                except Exception as e:
                    logger.error(f"Error al detectar patrón {pattern_name}: {e}")
            
            # Buscar patrones personalizados en la base de datos
            try:
                custom_patterns = await self._detect_custom_patterns(candles)
                if custom_patterns:
                    results.extend(custom_patterns)
            except Exception as e:
                logger.error(f"Error al detectar patrones personalizados: {e}")
            
            logger.info(f"Total de patrones detectados: {len(results)}")
            return results
        except Exception as e:
            logger.error(f"Error general en detect_patterns: {e}")
            return []

            
    def _detect_doji(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Doji"""
        try:
            doji = talib.CDLDOJI(opens, highs, lows, closes)
            return self._process_pattern_result(doji, "Doji", "neutral")
        except Exception as e:
            logger.error(f"Error al detectar Doji: {e}")
            return []

    def _detect_hammer(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Hammer"""
        try:
            hammer = talib.CDLHAMMER(opens, highs, lows, closes)
            return self._process_pattern_result(hammer, "Hammer", "bullish")
        except Exception as e:
            logger.error(f"Error al detectar Hammer: {e}")
            return []

    def _detect_engulfing(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Engulfing"""
        try:
            engulfing = talib.CDLENGULFING(opens, highs, lows, closes)
            return self._process_pattern_result(engulfing, "Engulfing", "variable")
        except Exception as e:
            logger.error(f"Error al detectar Engulfing: {e}")
            return []

    def _detect_morning_star(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Morning Star"""
        try:
            morning_star = talib.CDLMORNINGSTAR(opens, highs, lows, closes)
            return self._process_pattern_result(morning_star, "Morning Star", "bullish")
        except Exception as e:
            logger.error(f"Error al detectar Morning Star: {e}")
            return []

    def _detect_evening_star(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Evening Star"""
        try:
            evening_star = talib.CDLEVENINGSTAR(opens, highs, lows, closes)
            return self._process_pattern_result(evening_star, "Evening Star", "bearish")
        except Exception as e:
            logger.error(f"Error al detectar Evening Star: {e}")
            return []

    def _detect_harami(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Harami"""
        try:
            harami = talib.CDLHARAMI(opens, highs, lows, closes)
            return self._process_pattern_result(harami, "Harami", "variable")
        except Exception as e:
            logger.error(f"Error al detectar Harami: {e}")
            return []

    def _detect_piercing(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Piercing"""
        try:
            piercing = talib.CDLPIERCING(opens, highs, lows, closes)
            return self._process_pattern_result(piercing, "Piercing", "bullish")
        except Exception as e:
            logger.error(f"Error al detectar Piercing: {e}")
            return []

    def _detect_dark_cloud_cover(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Dark Cloud Cover"""
        try:
            dark_cloud = talib.CDLDARKCLOUDCOVER(opens, highs, lows, closes)
            return self._process_pattern_result(dark_cloud, "Dark Cloud Cover", "bearish")
        except Exception as e:
            logger.error(f"Error al detectar Dark Cloud Cover: {e}")
            return []

    def _detect_shooting_star(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Shooting Star"""
        try:
            shooting_star = talib.CDLSHOOTINGSTAR(opens, highs, lows, closes)
            return self._process_pattern_result(shooting_star, "Shooting Star", "bearish")
        except Exception as e:
            logger.error(f"Error al detectar Shooting Star: {e}")
            return []

    def _detect_marubozu(self, opens, highs, lows, closes) -> List[Dict[str, Any]]:
        """Detecta patrones Marubozu"""
        try:
            marubozu = talib.CDLMARUBOZU(opens, highs, lows, closes)
            return self._process_pattern_result(marubozu, "Marubozu", "variable")
        except Exception as e:
            logger.error(f"Error al detectar Marubozu: {e}")
            return []

        
    def _process_pattern_result(self, pattern_result, pattern_name, default_direction) -> List[Dict[str, Any]]:
        """
        Procesa los resultados de la detección de patrones
        
        Args:
            pattern_result: Resultado de la función de TA-Lib
            pattern_name: Nombre del patrón
            default_direction: Dirección por defecto del patrón
            
        Returns:
            Lista de patrones detectados
        """
        results = []
        
        # Verificar que pattern_result es un array de numpy
        if not isinstance(pattern_result, np.ndarray):
            logger.error(f"Error: pattern_result no es un array de numpy para {pattern_name}")
            return []
        
        # Buscar todos los índices donde se detectó el patrón
        for i in range(len(pattern_result)):
            # Asegurarse de que estamos comparando valores numéricos
            value = pattern_result[i]
            if not isinstance(value, (int, float, np.integer, np.floating)):
                logger.error(f"Error: valor no numérico en pattern_result[{i}] para {pattern_name}: {type(value)}")
                continue
                
            if value != 0:
                # Determinar dirección basada en el valor
                direction = default_direction
                if default_direction == "variable":
                    direction = "bullish" if value > 0 else "bearish"
                
                # Crear diccionario del patrón
                pattern_dict = {
                    'id': f"{pattern_name.lower().replace(' ', '_')}_{i}",
                    'name': pattern_name,
                    'type': "candlestick",
                    'direction': direction,
                    'confidence': 0.8,  # Valor por defecto
                    'timestamp': i
                }
                
                # Buscar información adicional en la base de datos
                for stored_pattern in self.patterns:
                    if stored_pattern.get('name') == pattern_name:
                        pattern_dict['success_rate'] = stored_pattern.get('success_rate', 0.0)
                        pattern_dict['total_occurrences'] = stored_pattern.get('total_occurrences', 0)
                        pattern_dict['confidence'] = min(0.5 + (stored_pattern.get('success_rate', 0.0) / 100.0), 0.95)
                        break
                
                results.append(pattern_dict)
        
        return results


    async def _detect_custom_patterns(self, candles: List[Candle]) -> List[Dict[str, Any]]:
        """
        Detecta patrones personalizados almacenados en la base de datos
        
        Args:
            candles: Lista de velas
            
        Returns:
            Lista de patrones detectados
        """
        # Esta función podría implementar lógica más avanzada para detectar
        # patrones personalizados basados en los almacenados en la base de datos
        # Por ahora, es un placeholder
        return []

    async def get_patterns(self):
        return self.patterns
