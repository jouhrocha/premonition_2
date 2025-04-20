import arrow
import sys
import os
import json
from dotenv import load_dotenv
from data.context import DataContext, InsightContext
from data.insights.price_action import PriceAction
from data.insights.current_price import CurrentPrice
from data.insights.linelevels import LineLevels
from data.insights.momentum import Momentum
from data.insights.news import News
from data.sources.yahoo import YahooSource
from data.sources.tdameritrade import TDAmeritrade
from data.insights.options import Options
from data.insights.vix import VIX
from utils import ask_gpt, save_response
from prompt import MARKET_SYSTEM, OPTIONS_SYSTEM, OPTIONS_USER
from bot.utils import exponential_backoff_retry, ask_gpt, logger
load_dotenv()

def main(prompt_only=False):
    # use the last argument as the symbol if one is provided
    if len(sys.argv) > 1:
        symbols = [sys.argv[-1].upper()]
    else:
        symbols = ['NVDA']

    sources = [
        YahooSource(),
        # TDAmeritrade() - requires TDAmeritrade account
    ]

    insights = [
        # Options(),  - requires TDAmeritrade account
        Momentum(most_recent=True),
        News(),
        LineLevels(3, 45),
        CurrentPrice(),
        PriceAction(day_lookback=60),
        VIX()
    ]

    for symbol in symbols:
        print(f'Getting insights for {symbol}...')
        datum = DataContext(sources, cache=False)
        insights_context = InsightContext(datum, [symbol], insights)

        results = insights_context.get_insights(arrow.now().shift(days=-1))

        insight_prompts = "\n".join([r.to_prompt() for r in results])
        prompt = OPTIONS_USER.replace('$C', insight_prompts)

        with open('prompt.py', 'w', encoding='utf-8') as f:
            f.write(prompt)

        if not prompt_only:
            response = ask_gpt(OPTIONS_SYSTEM, prompt, model='gpt-4')
            save_response(response, symbol)

def analyze_symbol(symbol: str, df_insights: str = "") -> dict:
    """
    Analiza un símbolo usando GPT-4, combinando insights técnicos.
    Parámetros:
      - symbol: par a analizar (ej: 'BTC/USD')
      - df_insights: cadena descriptiva de últimos indicadores (opcional)
    Devuelve dict con:
      {
        'direction': 'bullish'|'bearish'|'neutral',
        'confidence': float  # porcentaje 0-100
      }
    """

    # Construir el prompt, inyectando symbol y los insights técnicos
    insights_text = df_insights if df_insights else ""
    user_prompt = OPTIONS_USER.replace("$C", f"Símbolo: {symbol}\n{insights_text}")

    try:
        # Llamada a GPT con reintentos
        response = exponential_backoff_retry(
            lambda: ask_gpt(MARKET_SYSTEM, user_prompt, model=os.getenv("GPT_MODEL", "gpt-4"))
        )

        # Intentar parsear JSON del contenido
        content = response.strip()
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Si no viene JSON, intentar extraer con heurísticas
            logger.warning("gpt_analyzer: respuesta no es JSON, aplicando heurística mínima")
            direction = "neutral"
            confidence = 50.0
            if "bull" in content.lower():
                direction = "bullish"
            elif "bear" in content.lower():
                direction = "bearish"
            # Buscar porcentaje
            import re
            m = re.search(r"(\d{1,3})\s*%", content)
            if m:
                confidence = float(m.group(1))
            result = {"direction": direction, "confidence": confidence}

        # Normalizar valores
        direction = result.get("direction", "neutral").lower()
        confidence = float(result.get("confidence", 0))
        return {"direction": direction, "confidence": confidence}

    except Exception as e:
        logger.error(f"gpt_analyzer: error al analizar símbolo {symbol}: {e}", exc_info=True)
        # Caída segura
        return {"direction": "neutral", "confidence": 0}
