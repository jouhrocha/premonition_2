# -*- coding: utf-8 -*-
import pandas as pd
# Instalar si es necesario: pip install pandas_ta
import pandas_ta as ta
from bot import config
from bot.utils import logger

def add_indicators(df):
    """
    Añade los indicadores técnicos necesarios al DataFrame de velas.
    Utiliza la librería pandas_ta para eficiencia.
    """
    if df is None or df.empty:
        logger.warning("DataFrame vacío, no se pueden calcular indicadores.")
        return None

    try:
        # Calcular indicadores usando pandas_ta
        df.ta.rsi(length=config.RSI_PERIOD, append=True) # Añade columna 'RSI_14'
        df.ta.stoch(k=config.STOCH_K, d=config.STOCH_D, append=True) # Añade 'STOCHk_14_3_3', 'STOCHd_14_3_3'
        df.ta.ema(length=config.EMA_FAST_PERIOD, append=True) # Añade 'EMA_45'
        df.ta.sma(length=config.SMA_SLOW_PERIOD, append=True) # Añade 'SMA_100'
        df.ta.sma(length=config.SMA_TREND_PERIOD, append=True) # Añade 'SMA_200'
        df.ta.sma(close='volume', length=config.REVERSAL_VOLUME_MA_PERIOD, prefix='VOL', append=True) # Media de Volumen

        # Renombrar columnas para claridad (pandas_ta puede añadir sufijos)
        df.rename(columns={
            f'RSI_{config.RSI_PERIOD}': 'RSI',
            f'STOCHk_{config.STOCH_K}_{config.STOCH_D}_3': 'STOCHk', # Ajustar si el nombre difiere
            f'STOCHd_{config.STOCH_K}_{config.STOCH_D}_3': 'STOCHd', # Ajustar si el nombre difiere
            f'EMA_{config.EMA_FAST_PERIOD}': 'EMA_fast',
            f'SMA_{config.SMA_SLOW_PERIOD}': 'SMA_slow',
            f'SMA_{config.SMA_TREND_PERIOD}': 'SMA_trend',
            f'VOL_SMA_{config.REVERSAL_VOLUME_MA_PERIOD}': 'Volume_MA' # Ajustar si el nombre difiere
        }, inplace=True)

        logger.debug("Indicadores técnicos añadidos al DataFrame.")
        return df

    except Exception as e:
        logger.error(f"Error al calcular indicadores: {e}", exc_info=True)
        return None

# --- Podrían añadirse funciones manuales si pandas_ta no es suficiente ---
# def calculate_rsi_manual(series, period=14): ...
# def calculate_sma_manual(series, period=20): ...