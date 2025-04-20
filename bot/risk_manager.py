# Actualización completa de bot/risk_manager.py con las funciones placeholder completas

import math
import os
from bot import config
from bot.utils import logger
from bot import kraken_api
from gpt_analyzer import analyze_symbol

def calculate_position_size(entry_price, stop_loss_price, capital=None, risk_percentage=None):
    """
    Calcula el tamaño de la posición basado en el riesgo por operación.
    Basado en Conceptos Trading.pdf y Guía Completa.pdf.
    """
    # 1) Obtener capital si no se especifica
    if capital is None:
        balance = kraken_api.get_account_balance()
        base_currency = config.TRADING_PAIR.split('/')[1]  # Ej: 'USD'
        capital = balance.get(base_currency, 0)
        if capital <= 0:
            logger.error("No se pudo obtener capital válido de la cuenta.")
            return 0

    # 2) Obtener porcentaje de riesgo si no se especifica
    if risk_percentage is None:
        risk_percentage = config.RISK_PER_TRADE

    # 3) Validar parámetros
    if entry_price is None or stop_loss_price is None or capital <= 0 or risk_percentage <= 0:
        logger.error("Parámetros inválidos para calcular tamaño de posición.")
        return 0

    # 4) Cálculo base
    risk_amount = capital * risk_percentage
    distance_to_stop = abs(entry_price - stop_loss_price)
    if distance_to_stop == 0:
        logger.warning("Distancia al stop es cero. No se puede calcular tamaño.")
        return 0

    raw_size = risk_amount / distance_to_stop
    precision = getattr(config, "ORDER_DECIMALS", 8)
    size = math.floor(raw_size * (10 ** precision)) / (10 ** precision)

    # 5) Verificar tamaño mínimo
    min_order_size = getattr(config, "MIN_ORDER_SIZE", 0.0001)
    if size < min_order_size:
        logger.warning(f"Tamaño calculado {size} < mínimo {min_order_size}. No se operará.")
        return 0

    logger.info(f"Tamaño Posición: Capital={capital:.2f}, Riesgo={risk_percentage:.2%}, "
                f"Entry={entry_price:.2f}, SL={stop_loss_price:.2f} -> Size={size:.8f}")
    return size

def adjust_risk_for_volatility(current_risk_percentage, atr_value, avg_atr_value):
    """
    Ajusta el riesgo basado en ATR:
      - Si ATR actual > avg * factor, reduce riesgo.
    """
    factor = getattr(config, "VOLATILITY_THRESHOLD_FACTOR", 1.5)
    if atr_value > avg_atr_value * factor:
        new_risk = current_risk_percentage / 2
        logger.warning(f"Alta volatilidad (ATR {atr_value:.4f} > {avg_atr_value*factor:.4f}), "
                       f"reduciendo riesgo a {new_risk:.2%}")
        return new_risk
    return current_risk_percentage

def adjust_risk_for_drawdown(current_risk_percentage, current_drawdown, max_drawdown_threshold):
    """
    Ajusta el riesgo basado en Drawdown:
      - Escala linealmente entre 0 y max_threshold.
    """
    if current_drawdown >= max_drawdown_threshold:
        logger.warning("Drawdown >= umbral máximo, riesgo reducido a 0.")
        return 0
    # factor de escala: 1 - (drawdown / threshold)
    factor = 1 - (current_drawdown / max_drawdown_threshold)
    new_risk = current_risk_percentage * factor
    logger.info(f"Drawdown {current_drawdown:.2%} < umbral {max_drawdown_threshold:.2%}, "
                f"riesgo ajustado a {new_risk:.2%}")
    return new_risk

def adjust_risk_for_gpt_sentiment(current_risk_percentage, symbol):
    """
    Ajusta el riesgo basado en sentimiento de GPT:
      + aumenta si bullish, - reduce si bearish.
    """
    result = analyze_symbol(symbol)
    direction = result.get("direction", "neutral").lower()
    confidence = result.get("confidence", 50) / 100
    if direction == "bearish":
        new_risk = max(0, current_risk_percentage * (1 - confidence))
        logger.info(f"Sentimiento GPT bearish ({confidence:.0%}), riesgo {new_risk:.2%}")
        return new_risk
    elif direction == "bullish":
        max_risk = getattr(config, "MAX_RISK_PER_TRADE", 0.02)
        new_risk = min(max_risk, current_risk_percentage * (1 + confidence))
        logger.info(f"Sentimiento GPT bullish ({confidence:.0%}), riesgo {new_risk:.2%}")
        return new_risk
    return current_risk_percentage

def calculate_adaptive_position_size(entry_price, stop_loss_price, df_history, capital=None):
    """
    Calcula tamaño adaptativo considerando volatilidad, drawdown y GPT.
    """
    # Tamaño base
    size = calculate_position_size(entry_price, stop_loss_price, capital)
    if size == 0:
        return 0

    # ATR y drawdown histórico
    atr_value = df_history['atr'].iloc[-1]
    avg_atr_value = df_history['atr'].mean()
    current_drawdown = df_history['drawdown'].iloc[-1]  # Asumir columna 'drawdown'
    max_dd = getattr(config, "MAX_DRAWDOWN", 0.2)

    # Ajustes de riesgo
    risk_per_trade = config.RISK_PER_TRADE
    risk = adjust_risk_for_volatility(risk_per_trade, atr_value, avg_atr_value)
    risk = adjust_risk_for_drawdown(risk, current_drawdown, max_dd)
    risk = adjust_risk_for_gpt_sentiment(risk, config.TRADING_PAIR)

    # Recalcular tamaño con nuevo riesgo
    adaptive_size = calculate_position_size(entry_price, stop_loss_price, capital, risk)
    logger.info(f"Tamaño adaptativo final: {adaptive_size:.8f}")
    return adaptive_size

# Fin de risk_manager.py
