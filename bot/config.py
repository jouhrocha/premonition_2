# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde un archivo .env (recomendado para desarrollo local)
# En producción (Docker/Cloud), estas variables se inyectan directamente.
load_dotenv()

# --- Claves API Kraken ---
# ¡¡NUNCA codificar las claves directamente aquí!! Leer desde el entorno.
KRAKEN_API_KEY = os.getenv("KRAKEN_API_KEY")
KRAKEN_API_SECRET = os.getenv("KRAKEN_API_SECRET")

# --- Parámetros de Trading ---
TRADING_PAIR = "XBT/USD"  # Par a operar (ejemplo, debe ser formato Kraken)
TIMEFRAME = '1'           # Timeframe en minutos para las velas (ej: '1', '5', '15')
RISK_PER_TRADE = 0.01     # Porcentaje de capital a arriesgar por operación (1%)

# --- Parámetros de Estrategia ---
# Reversión
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
STOCH_K = 14
STOCH_D = 3
STOCH_OVERBOUGHT = 80
STOCH_OVERSOLD = 20
EMA_FAST_PERIOD = 45
SMA_SLOW_PERIOD = 100
SMA_TREND_PERIOD = 200
REVERSAL_VOLUME_MA_PERIOD = 30
REVERSAL_CONFIDENCE_THRESHOLD = 4 # Umbral para señal "Verde" (ej: 4 de 5 criterios)

# Rotura
BREAKOUT_LOOKBACK_PERIOD = 20 # Velas para identificar consolidación/rango
BREAKOUT_VOLUME_MA_PERIOD = 20
BREAKOUT_VOLUME_FACTOR = 1.5 # Volumen de ruptura debe ser > 1.5x el promedio

# --- Gestión de Riesgo ---
USE_TRAILING_STOP = False
TRAILING_STOP_TYPE = 'ATR' # 'PERCENT' o 'ATR'
TRAILING_STOP_VALUE = 1.5  # Valor para % o múltiplo de ATR
ENABLE_PARTIAL_TP = True
PARTIAL_TP_LEVELS = 2      # Número de TPs (ej: 2 para 50%/50%)
TP_RR_RATIO_1 = 1.5       # Ratio R:R para el primer TP
TP_RR_RATIO_2 = 3.0       # Ratio R:R para el segundo TP (si ENABLE_PARTIAL_TP)
MOVE_TO_BE_THRESHOLD = 0.6 # Mover SL a BE cuando se alcanza el 60% del camino al primer TP

# --- Otros ---
LOG_LEVEL = "INFO"        # Nivel de logging: DEBUG, INFO, WARNING, ERROR
MAX_API_RETRIES = 5       # Máximos reintentos para llamadas API fallidas
API_RETRY_DELAY = 2       # Delay inicial en segundos para reintentos

# Validar que las claves API están presentes
if not KRAKEN_API_KEY or not KRAKEN_API_SECRET:
    print("ERROR: Las variables de entorno KRAKEN_API_KEY y KRAKEN_API_SECRET no están configuradas.")
    # En un bot real, aquí se debería lanzar una excepción o salir.
    # exit(1) # Descomentar para forzar salida si no hay claves