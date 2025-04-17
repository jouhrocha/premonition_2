import pandas as pd
from bot import config
from bot.utils import logger
from bot import strategies

def calculate_weighted_score(df_with_indicators):
    """
    Calcula una puntuación ponderada basada en diferentes factores.
    """
    try:
        last = df_with_indicators.iloc[-1]
    except IndexError:
        logger.warning("No hay datos suficientes para calcular la puntuación.")
        return 0, {}

    # --- 1. Definir Factores y Ponderaciones ---
    factors = {
        "rsi": {"weight": config.RSI_WEIGHT, "value": last['RSI']},
        "macd": {"weight": config.MACD_WEIGHT, "value": last['MACD']},
        "gpt_sentiment": {"weight": config.GPT_SENTIMENT_WEIGHT, "value": strategies.get_gpt_sentiment(df_with_indicators)}
        # Añade más factores aquí
    }

    # --- 2. Escala de Puntuación para Cada Factor ---
    # (Ejemplo: escala lineal para RSI, MACD y GPT Sentiment)
    def scale_rsi(rsi_value):
        # Escala RSI de 0 a 100 a -1 a 1
        return (rsi_value - 50) / 50

    def scale_macd(macd_value):
        # Escala MACD (asumiendo que los valores positivos son alcistas y negativos bajistas)
        return macd_value / 10  # Ajusta el divisor según la escala típica de MACD

    def scale_gpt_sentiment(sentiment_score):
        # GPT Sentiment ya está en una escala de -1 a 1 (asumiendo)
        return sentiment_score

    # --- 3. Calcular Puntuaciones Ponderadas ---
    weighted_scores = {}
    total_score = 0

    for factor_name, factor_data in factors.items():
        weight = factor_data["weight"]
        value = factor_data["value"]
        score = 0

        if factor_name == "rsi":
            score = scale_rsi(value) * weight
        elif factor_name == "macd":
            score = scale_macd(value) * weight
        elif factor_name == "gpt_sentiment":
            score = scale_gpt_sentiment(value) * weight

        weighted_scores[factor_name] = score
        total_score += score

    logger.info(f"Puntuaciones ponderadas: {weighted_scores}, Puntuación total: {total_score}")
    return total_score, weighted_scores