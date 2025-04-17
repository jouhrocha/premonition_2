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
    # Ejemplo: reducir el riesgo si la volatilidad actual es mayor que el promedio
    if atr_value > 1.5 * avg_atr_value:
        current_risk_percentage = current_risk_percentage / 2
        logger.warning(f"Volatilidad alta detectada. Reduciendo riesgo a {current_risk_percentage:.2%}")
    return current_risk_percentage

def adjust_risk_for_drawdown(current_risk_percentage, current_drawdown, max_drawdown_threshold):
    """Ajusta el riesgo basado en Drawdown."""
    # Lógica: si current_drawdown > max_drawdown_threshold, reducir el riesgo
    if current_drawdown > max_drawdown_threshold:
        current_risk_percentage = current_risk_percentage / 2
        logger.warning(f"Drawdown máximo alcanzado. Reduciendo riesgo a {current_risk_percentage:.2%}")
    return current_risk_percentage

def adjust_risk_for_gpt_sentiment(current_risk_percentage, gpt_sentiment_score):
    """Ajusta el riesgo basado en el sentimiento de GPT."""
    # Lógica: si GPT indica sentimiento negativo, reducir el riesgo
    if gpt_sentiment_score < 0:  # Asumiendo que GPT devuelve un score entre -1 y 1
        current_risk_percentage = max(0, current_risk_percentage + gpt_sentiment_score)  # Ajustar riesgo
        logger.info(f"Sentimiento GPT negativo detectado. Ajustando riesgo a {current_risk_percentage:.2%}")
    elif gpt_sentiment_score > 0.5:
        current_risk_percentage = min(config.MAX_RISK_PER_TRADE, current_risk_percentage + gpt_sentiment_score)
        logger.info(f"Sentimiento GPT positivo detectado. Ajustando riesgo a {current_risk_percentage:.2%}")
    return current_risk_percentage

def get_gpt_sentiment(df_history):
    """Placeholder para obtener el sentimiento de GPT."""
    # Aquí iría la llamada a la API de GPT con el historial de precios
    # y el análisis técnico.
    # Por ahora, devolvemos un valor aleatorio entre -1 y 1 para simular.
    import random
    return random.uniform(-1, 1)

def calculate_adaptive_position_size(entry_price, stop_loss_price, df_history, capital=None):
    """
    Calcula el tamaño de la posición de forma adaptativa, considerando volatilidad, drawdown y sentimiento de GPT.
    """
    # 1. Calcular el tamaño de la posición base.
    size = calculate_position_size(entry_price, stop_loss_price, capital)
    if size == 0:
        return 0

    # 2. Obtener métricas de volatilidad (ATR).
    atr_value = df_history['atr'].iloc[-1]  # Asumiendo que 'atr' está en df_history
    avg_atr_value = df_history['atr'].mean()

    # 3. Obtener el drawdown actual.
    # Esto requiere llevar un registro del capital a lo largo del tiempo.
    # Aquí simulamos un valor.
    current_drawdown = 0.1  # 10% de drawdown

    # 4. Obtener el sentimiento de GPT.
    gpt_sentiment_score = get_gpt_sentiment(df_history)

    # 5. Ajustar el riesgo.
    risk_percentage = config.RISK_PER_TRADE
    risk_percentage = adjust_risk_for_volatility(risk_percentage, atr_value, avg_atr_value)
    risk_percentage = adjust_risk_for_drawdown(risk_percentage, current_drawdown, config.MAX_DRAWDOWN)
    risk_percentage = adjust_risk_for_gpt_sentiment(risk_percentage, gpt_sentiment_score)

    # 6. Recalcular el tamaño de la posición con el riesgo ajustado.
    adaptive_size = calculate_position_size(entry_price, stop_loss_price, capital, risk_percentage)

    logger.info(f"Tamaño de posición adaptativo calculado: {adaptive_size:.8f}")
    return adaptive_size