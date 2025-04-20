#!/usr/bin/env python3
# -*- coding: utf-8 -

import sys
import ccxt.async_support as ccxtasync
sys.path.append("..")

# Función para obtener la lista de símbolos disponibles en Kraken y los pares con Bitcoin
class SymbolsList:
    def __init__(self):
        self.exchange = ccxtasync.kraken()
        self.symbols = []
        self.load_symbols()
        self.load_btc_pairs()
        self.print_symbols()
    def load_symbols(self):
        try:
            self.symbols = self.exchange.symbols
        except Exception as e:
            print(f"Error: {e}")
            return []
        return self.symbols
    def load_btc_pairs(self):
        btc_pairs = [symbol for symbol in self.symbols if 'BTC/' in symbol]
        return btc_pairs
    def print_symbols(self):
        print("Símbolos disponibles en Kraken:")
        for symbol in sorted(self.symbols):
            print(f"- {symbol}")
            pass
        print("\nPares con Bitcoin:")
        for symbol in sorted(self.symbols):
            if 'BTC/' in symbol:
                print(f"- {symbol}")
                pass

if __name__ == "__main__":
    symbols_list = SymbolsList()
    symbols_list.print_symbols()
    pass
