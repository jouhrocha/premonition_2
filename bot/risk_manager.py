# -*- coding: utf-8 -*-
import math
from bot import config
from bot.utils import logger
from bot import kraken_api # Para obtener balance

def calculate_position_size(entry_price, stop_loss_price, capital=None, risk_percentage=None):
    """
    Calcula el tamaño de la posición basado en el riesgo por operación.
    Basado en la fórmula de Conceptos Trading.pdf y Guía Completa.pdf.
    """
    if capital is None:
        balance = kraken_api.get_account_balance()
        # Asumir que operamos con la moneda base del par (ej: USD para XBT/USD)
        # ¡Esta lógica necesita refinarse según la estructura del par y balance!
        base_currency = config.TRADING_PAIR.split('/')[1] # Ej: 'USD'
        capital = balance.get(base_currency, 0)
        if capital <= 0:
            logger.error("No se pudo obtener capital válido de la cuenta.")
            return 0

    if risk_percentage is None:
        risk_percentage = config.RISK_PER_TRADE

    if entry_price is None or stop_loss_price is None or capital <= 0 or risk_percentage <= 0:
        logger.error("Parámetros inválidos para calcular tamaño de posición.")
        return 0

    risk_amount = capital * risk_percentage # [source: 648, 847]
    distance_to_stop = abs(entry_price - stop_loss_price) # [source: 648]

    if distance_to_stop == 0:
        logger.warning("Distancia al stop es cero. No se puede calcular tamaño.")
        return 0

    # Asumiendo valor_por_punto = 1 (para Spot Cripto/Acciones)
    # Para futuros u otros, necesitaríamos config.VALOR_POR_PUNTO
    raw_size = risk_amount / distance_to_stop # [source: 648, 847]

    # Redondear hacia abajo a un número razonable de decimales para cripto
    # Kraken tiene diferentes precisiones por par, obtener de API o configurar.
    # Ejemplo: redondear a 8 decimales
    precision = 8
    size = math.floor(raw_size * (10**precision)) / (10**precision) # [source: 846] - adaptado para decimales

    # Verificar contra tamaño mínimo de orden de Kraken (obtener de API o configurar)
    min_order_size = 0.0001 # Ejemplo para XBT
    if size < min_order_size:
         logger.warning(f"Tamaño calculado {size} es menor que el mínimo {min_order_size}. No se operará.")
         return 0

    logger.info(f"Cálculo Tamaño Posición: Capital={capital:.2f}, Riesgo={risk_percentage:.2%}, "
                f"Entry={entry_price:.2f}, SL={stop_loss_price:.2f} -> Tamaño={size:.8f}")

    return size

# --- Funciones Placeholder para Gestión Adaptativa ---
def adjust_risk_for_volatility(current_risk_percentage, atr_value, avg_atr_value):
    """Ajusta el riesgo basado en ATR (Placeholder)."""
    # Lógica: si atr_value >> avg_atr_value, reducir current_risk_percentage
    return current_risk_percentage

def adjust_risk_for_drawdown(current_risk_percentage, current_drawdown, max_drawdown_threshold):
    """Ajusta el riesgo basado en Drawdown (Placeholder)."""
    # Lógica: si current_drawdown > max_drawdown_threshold, return current_risk_percentage / 2
    return current_risk_percentage