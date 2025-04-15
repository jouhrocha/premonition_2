# -*- coding: utf-8 -*-
from bot import config
from bot.utils import logger

# Constantes para el Semáforo
SIGNAL_GREEN = "VERDE"
SIGNAL_RED = "ROJO"
SIGNAL_NONE = "NINGUNA"

def check_reversal_signal(df_with_indicators):
    """
    Evalúa la última vela del DataFrame para una señal de Reversión.
    Basado en Conceptos Trading.pdf y Guía Completa.pdf.
    Retorna: (Estado_Semáforo, Detalles_Señal), ej: (SIGNAL_GREEN, "Reversión Alcista - Vela Envolvente + RSI < 30 + Vol Alto")
    """
    if df_with_indicators is None or len(df_with_indicators) < max(config.EMA_FAST_PERIOD, config.SMA_SLOW_PERIOD, config.SMA_TREND_PERIOD, 5):
        return SIGNAL_NONE, "Datos insuficientes"

    # Usar las últimas 2 velas para comparación
    try:
        prev = df_with_indicators.iloc[-2]
        last = df_with_indicators.iloc[-1]
    except IndexError:
        return SIGNAL_NONE, "Insuficientes velas recientes"

    # --- Evaluar Condiciones para Reversión Alcista ---
    # (La lógica para Reversión Bajista sería simétrica)
    score = 0
    details = []

    # 1. Contexto de Caída y Sobreextensión: Precio bajo MAs? (Simplificado)
    is_extended_down = (last['close'] < prev['EMA_fast']) and (last['close'] < prev['SMA_slow'])
    if is_extended_down:
        score += 1
        details.append("Precio bajo MAs")
        # Podría mejorarse midiendo distancia % a las MAs

    # 2. Nivel de Soporte Clave: (Difícil de automatizar sin análisis previo)
    # Placeholder: Se podría añadir lógica si se precalculan soportes. Por ahora, omitido para puntuación.

    # 3. Vela de Giro Alcista: Envolvente o Martillo con mecha inferior
    is_bullish_candle = last['close'] > last['open']
    is_prev_bearish = prev['close'] < prev['open']
    is_engulfing = is_bullish_candle and is_prev_bearish and \
                   last['close'] > prev['open'] and last['open'] < prev['close'] # [source: 414, 830]

    # Mecha inferior significativa (ej. > 30% del rango total)
    total_range = last['high'] - last['low']
    lower_wick = min(last['open'], last['close']) - last['low']
    has_lower_wick = total_range > 0 and (lower_wick / total_range) > 0.3 # [source: 411, 812]

    is_reversal_candle = is_bullish_candle and (is_engulfing or has_lower_wick)
    if is_reversal_candle:
        score += 1
        details.append(f"{'Envolvente' if is_engulfing else ''}{'+' if is_engulfing and has_lower_wick else ''}{'Mecha Inferior' if has_lower_wick else ''}")

    # 4. Volumen Alto en Vela de Giro: Comparado con la media
    is_volume_high = last['volume'] > last['Volume_MA'] * 1.1 # > 110% de la media [source: 427, 813]
    if is_volume_high:
        score += 1
        details.append("Volumen Alto")

    # 5. Indicadores en Sobreventa / Divergencia
    is_rsi_oversold = last['RSI'] < config.RSI_OVERSOLD # [source: 446]
    is_stoch_oversold = last['STOCHk'] < config.STOCH_OVERSOLD and last['STOCHd'] < config.STOCH_OVERSOLD # [source: 459]

    # Divergencia Alcista RSI Simple: Precio hizo nuevo mínimo, RSI no
    made_lower_low = last['low'] < prev['low']
    rsi_higher_low = last['RSI'] > prev['RSI']
    has_rsi_divergence = made_lower_low and rsi_higher_low # [source: 442, 814]

    if is_rsi_oversold or is_stoch_oversold or has_rsi_divergence:
        score += 1
        details.append(f"{'RSI<30 ' if is_rsi_oversold else ''}{'Stoch<20 ' if is_stoch_oversold else ''}{'DivRSI ' if has_rsi_divergence else ''}")

    # --- Decisión del Semáforo ---
    if score >= config.REVERSAL_CONFIDENCE_THRESHOLD:
        signal_type = SIGNAL_GREEN
        signal_details = f"Reversión Alcista ({score}/5): {', '.join(details)}"
        logger.info(signal_details)
        # Aquí también necesitaríamos calcular SL y TP propuestos
        stop_loss_price = last['low'] * (1 - 0.001) # Un poco por debajo del mínimo [source: 520]
        entry_price = last['close'] # Asumiendo entrada al cierre
        # TP basado en R:R
        risk_per_unit = entry_price - stop_loss_price
        if risk_per_unit <= 0: return SIGNAL_NONE, "Distancia de stop inválida"
        take_profit_price_1 = entry_price + config.TP_RR_RATIO_1 * risk_per_unit
        take_profit_price_2 = entry_price + config.TP_RR_RATIO_2 * risk_per_unit if config.ENABLE_PARTIAL_TP else None
        
        return signal_type, {
            "strategy": "Reversal",
            "direction": "LONG",
            "details": signal_details,
            "entry_price": entry_price,
            "stop_loss": stop_loss_price,
            "take_profit_1": take_profit_price_1,
            "take_profit_2": take_profit_price_2
        }
    elif score > 0: # Si hay alguna condición pero no suficiente
         # Podríamos loggear como señal débil o ROJA, pero no operarla
         logger.debug(f"Señal Reversión Débil ({score}/5) ignorada: {', '.join(details)}")
         return SIGNAL_RED, f"Reversión Alcista Débil ({score}/5)"
    else:
        return SIGNAL_NONE, "Sin señal de reversión"


def check_breakout_signal(df_with_indicators):
    """
    Evalúa la última vela para una señal de Rotura Alcista.
    Basado en Conceptos Trading.pdf y Guía Completa.pdf.
    Retorna: (Estado_Semáforo, Detalles_Señal)
    """
    if df_with_indicators is None or len(df_with_indicators) < config.BREAKOUT_LOOKBACK_PERIOD + 1:
        return SIGNAL_NONE, "Datos insuficientes para breakout"

    try:
        lookback_candles = df_with_indicators.iloc[-(config.BREAKOUT_LOOKBACK_PERIOD + 1):-1]
        last = df_with_indicators.iloc[-1]
    except IndexError:
        return SIGNAL_NONE, "Insuficientes velas recientes para breakout"

    # --- Evaluar Condiciones para Rotura Alcista ---
    score = 0
    details = []

    # 1. Identificar Consolidación y Nivel de Ruptura
    consolidation_high = lookback_candles['high'].max() # Máximo del rango reciente [source: 184]
    # (Podría mejorarse detectando patrones específicos como triángulos)

    # 2. Ruptura Clara del Nivel
    is_breakout_candle = last['close'] > consolidation_high
    if is_breakout_candle:
        score += 1
        details.append(f"Ruptura de {consolidation_high:.2f}")

    # 3. Volumen Seco en Consolidación (Simplificado: volumen promedio reciente bajo?)
    # (Esta parte requiere una definición más robusta de "volumen seco")
    # Placeholder: Asumimos que si rompe, es suficiente por ahora
    volume_contracting = True # Placeholder
    if volume_contracting:
        score += 1
        details.append("Volumen Seco (Placeholder)")

    # 4. Volumen Alto en la Ruptura
    avg_lookback_volume = lookback_candles['volume'].mean()
    is_breakout_volume_high = last['volume'] > avg_lookback_volume * config.BREAKOUT_VOLUME_FACTOR # [source: 562, 819]
    if is_breakout_volume_high:
        score += 1
        details.append(f"Volumen Ruptura Alto (>{config.BREAKOUT_VOLUME_FACTOR:.1f}x)")

    # 5. Alineación con Tendencia Principal (SMA_trend)
    is_uptrend = last['close'] > last['SMA_trend'] # [source: 565]
    if is_uptrend:
        score += 1
        details.append("Tendencia Principal Alcista")

    # 6. Confirmaciones Adicionales (RSI no extremo, sin divergencia bajista)
    # (Simplificado: solo chequear que RSI no esté > 85)
    is_rsi_ok = last['RSI'] < 85
    if is_rsi_ok:
        score += 1
        details.append("RSI no extremo")

    # --- Decisión del Semáforo ---
    # Umbral más alto para breakouts? Podría ser config.BREAKOUT_CONFIDENCE_THRESHOLD
    breakout_threshold = config.REVERSAL_CONFIDENCE_THRESHOLD # Usamos el mismo por ahora
    if is_breakout_candle and score >= breakout_threshold: # Requiere al menos la ruptura + N criterios
        signal_type = SIGNAL_GREEN
        signal_details = f"Rotura Alcista ({score}/6): {', '.join(details)}"
        logger.info(signal_details)

        # Calcular SL y TP
        stop_loss_price = consolidation_high * (1 - 0.001) # Justo debajo del nivel roto [source: 582]
        entry_price = last['close']
        risk_per_unit = entry_price - stop_loss_price
        if risk_per_unit <= 0: return SIGNAL_NONE, "Distancia de stop inválida"

        # TP por R:R o Proyección (usamos R:R por simplicidad)
        take_profit_price_1 = entry_price + config.TP_RR_RATIO_1 * risk_per_unit
        take_profit_price_2 = entry_price + config.TP_RR_RATIO_2 * risk_per_unit if config.ENABLE_PARTIAL_TP else None

        return signal_type, {
            "strategy": "Breakout",
            "direction": "LONG",
            "details": signal_details,
            "entry_price": entry_price,
            "stop_loss": stop_loss_price,
            "take_profit_1": take_profit_price_1,
            "take_profit_2": take_profit_price_2
        }
    elif is_breakout_candle and score > 0:
        logger.debug(f"Señal Rotura Débil ({score}/6) ignorada: {', '.join(details)}")
        return SIGNAL_RED, f"Rotura Alcista Débil ({score}/6)"
    else:
        return SIGNAL_NONE, "Sin señal de rotura"

# --- Aquí irían las funciones simétricas para señales BAJISTAS ---
# def check_reversal_signal_short(...): ...
# def check_breakout_signal_short(...): ...