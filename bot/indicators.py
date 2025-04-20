# bot/indicators.py

import pandas as pd
import ta
from typing import Dict
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade indicadores técnicos al DataFrame de precios.
    Espera columnas: ['open', 'high', 'low', 'close', 'volume'].
    Devuelve copia con columnas añadidas:
      - rsi (14)
      - macd, macd_signal, macd_diff
      - stoch_k, stoch_d (14)
      - ema_50, ema_200
    """
    df = df.copy()

    # Asegurar las columnas necesarias
    required = ['open', 'high', 'low', 'close', 'volume']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"DataFrame debe contener columna '{col}'")

    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

    # MACD
    macd = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()

    # Estocástico
    stoch = ta.momentum.StochasticOscillator(
        high=df['high'], low=df['low'], close=df['close'], window=14, smooth_window=3
    )
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()

    # EMAs
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

    return df

