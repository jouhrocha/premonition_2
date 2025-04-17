# Premonition V3 - main.py
# Este es el núcleo unificado del sistema operativo de trading IA + técnico

import os
from dotenv import load_dotenv
from bot.strategies import decision_engine
from bot.kraken_api import KrakenAPI
from bot.risk_manager import RiskManager
from bot.indicators import add_indicators
from gpt_analyzer import analyze_symbol
import pandas as pd

load_dotenv()

KRAKEN_KEY = os.getenv("KRAKEN_API_KEY")
KRAKEN_SECRET = os.getenv("KRAKEN_API_SECRET")
SYMBOLS = os.getenv("SYMBOLS", "BTC/USD,ETH/USD").split(',')

kraken = KrakenAPI(KRAKEN_KEY, KRAKEN_SECRET)
risk = RiskManager()


def run_premonition():
    print("[Premonition V3] Inicio del sistema IA + técnico")
    
    for symbol in SYMBOLS:
        print(f"\nAnalizando {symbol}...")
        # Obtener datos OHLCV
        # Aquí debes implementar la lógica para obtener los datos OHLCV del símbolo
        # Puedes usar una API como Kraken o Binance para obtener los datos
        # Por ahora, simularemos los datos con un DataFrame vacío
        df = pd.DataFrame()

        # Añadir indicadores técnicos
        df_with_indicators = add_indicators(df)

        # Analizar el símbolo con GPT
        gpt_result = analyze_symbol(df_with_indicators)

        decision = decision_engine(symbol, df_with_indicators, gpt_result)
        if decision['action'] == 'buy':
            qty = risk.calculate_position_size(symbol)
            kraken.place_order(symbol, 'buy', qty)
            print(f"✅ Compra ejecutada de {symbol} con tamaño {qty}")
        elif decision['action'] == 'sell':
            qty = risk.calculate_position_size(symbol)
            kraken.place_order(symbol, 'sell', qty)
            print(f"✅ Venta ejecutada de {symbol} con tamaño {qty}")
        else:
            print(f"❌ No se recomienda operar {symbol} en este momento.")


if __name__ == "__main__":
    run_premonition()