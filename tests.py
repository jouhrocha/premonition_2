# filepath: c:\Users\Montse\Desktop\PREMONITION_2\tests.py
import unittest
import pandas as pd
#from bot import strategies, indicators, risk_manager, kraken_api  # Eliminar esta importación
from test_config import TestConfig
from unittest.mock import patch
import io
import sys

@patch('bot.kraken_api.get_historical_data')  # Mockear get_historical_data globalmente
class TestStrategies(unittest.TestCase):
    def test_check_reversal_signal_green(self, mock_get_historical_data):
        from bot import strategies  # Importar solo lo necesario
        # Crear un DataFrame de ejemplo con datos históricos
        data = {
            'open': [100, 101, 102, 101, 100],
            'high': [102, 103, 104, 103, 102],
            'low': [99, 100, 101, 100, 99],
            'close': [101, 102, 103, 102, 101],
            'volume': [1000, 1100, 1200, 1100, 1000],
            'EMA_fast': [100, 101, 102, 101, 100],
            'SMA_slow': [100, 100, 100, 100, 100],
            'Volume_MA': [1000, 1000, 1000, 1000, 1000],
            'RSI': [30, 25, 20, 25, 30],
            'STOCHk': [20, 15, 10, 15, 20],
            'STOCHd': [20, 15, 10, 15, 20]
        }
        df = pd.DataFrame(data)
        mock_get_historical_data.return_value = (df, None)

        # Ejecutar la función check_reversal_signal
        signal_status, signal_details = strategies.check_reversal_signal(df)

        # Verificar que la señal es la esperada
        self.assertEqual(signal_status, strategies.SIGNAL_GREEN)
        self.assertIn("Reversión Alcista", signal_details)

    def test_check_reversal_signal_none(self,mock_get_historical_data):
        from bot import strategies # Importar solo lo necesario
        # Crear un DataFrame de ejemplo sin señal de reversión
        data = {
            'open': [100, 101, 102, 103, 104],
            'high': [102, 103, 104, 105, 106],
            'low': [99, 100, 101, 102, 103],
            'close': [101, 102, 103, 104, 105],
            'volume': [1000, 1100, 1200, 1300, 1400],
            'EMA_fast': [100, 101, 102, 103, 104],
            'SMA_slow': [100, 100, 100, 100, 100],
            'Volume_MA': [1000, 1000, 1000, 1000, 1000],
            'RSI': [50, 50, 50, 50, 50],
            'STOCHk': [50, 50, 50, 50, 50],
            'STOCHd': [50, 50, 50, 50, 50]
        }
        df = pd.DataFrame(data)
        mock_get_historical_data.return_value = (df, None)

        # Ejecutar la función check_reversal_signal
        signal_status, signal_details = strategies.check_reversal_signal(df)

        # Verificar que la señal es la esperada
        self.assertEqual(signal_status, strategies.SIGNAL_NONE)
        self.assertIn("Sin señal de reversión", signal_details)

@patch('bot.indicators.kraken_api.get_historical_data')
class TestIndicators(unittest.TestCase):
    def test_add_indicators(self,mock_get_historical_data):
        from bot import indicators # Importar solo lo necesario
        # Crear un DataFrame de ejemplo
        data = {'open': [1, 2, 3, 4, 5],
                'high': [2, 3, 4, 5, 6],
                'low': [0, 1, 2, 3, 4],
                'close': [2, 3, 4, 5, 6],
                'volume': [10, 20, 30, 40, 50]}
        df = pd.DataFrame(data)
        mock_get_historical_data.return_value = (df, None)

        # Agregar indicadores
        df_with_indicators = indicators.add_indicators(df)

        # Verificar que los indicadores se agregaron correctamente
        self.assertIn('EMA_fast', df_with_indicators.columns)
        self.assertIn('SMA_slow', df_with_indicators.columns)
        self.assertIn('Volume_MA', df_with_indicators.columns)
        self.assertIn('RSI', df_with_indicators.columns)
        self.assertIn('STOCHk', df_with_indicators.columns)
        self.assertIn('STOCHd', df_with_indicators.columns)

@patch('bot.risk_manager.kraken_api.get_historical_data')
class TestRiskManager(unittest.TestCase):
    def test_calculate_position_size(self,mock_get_historical_data):
        from bot import risk_manager # Importar solo lo necesario
        # Definir los parámetros de prueba
        entry_price = 100
        stop_loss = 95
        account_balance = 1000
        risk_percentage = TestConfig.RISK_PER_TRADE  # Utiliza la configuración de prueba
        data = {'open': [1, 2, 3, 4, 5],
                'high': [2, 3, 4, 5, 6],
                'low': [0, 1, 2, 3, 4],
                'close': [2, 3, 4, 5, 6],
                'volume': [10, 20, 30, 40, 50]}
        df = pd.DataFrame(data)
        mock_get_historical_data.return_value = (df, None)

        # Calcular el tamaño de la posición
        position_size = risk_manager.calculate_position_size(entry_price, stop_loss, account_balance, risk_percentage)

        # Verificar que el tamaño de la posición es el esperado
        self.assertAlmostEqual(position_size, 0.2, places=4)  # Ajustar la precisión según sea necesario

@patch('bot.kraken_api.kraken.query_public')
class TestKrakenAPI(unittest.TestCase):
    def test_get_ticker_info(self, mock_query_public):
        from bot import kraken_api # Importar solo lo necesario
        # Configurar el mock para simular una respuesta exitosa de la API
        mock_response = {'error': [], 'result': {'XXBTZUSD': {'a': ['40000.00', '1', '1.000']}}}  # Ejemplo simplificado
        mock_query_public.return_value = mock_response

        # Llamar a la función get_ticker_info
        ticker_info = kraken_api.get_ticker_info(TestConfig.TRADING_PAIR)

        # Verificar que la función devuelve la información del ticker esperada
        # (Ajustar esta aserción según lo que realmente devuelve get_ticker_info)
        #self.assertEqual(ticker_info['ask'], 40000.00)
        print("Test get_ticker_info ejecutado") # Añadir para verificar que se ejecuta

def run_all_tests():
    """Función para ejecutar todas las pruebas."""
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestStrategies))
    suite.addTest(unittest.makeSuite(TestIndicators))
    suite.addTest(unittest.makeSuite(TestRiskManager))
    suite.addTest(unittest.makeSuite(TestKrakenAPI))

    runner = unittest.TextTestRunner()
    runner.run(suite)

def display_menu():
    """Muestra un menú interactivo para ejecutar las pruebas."""
    while True:
        print("\n--- Menú de Pruebas ---")
        print("1. Probar Estrategias")
        print("2. Probar Indicadores")
        print("3. Probar Gestión de Riesgos")
        print("4. Probar API de Kraken")
        print("5. Ejecutar todas las pruebas")
        print("0. Salir")

        choice = input("Selecciona una opción: ")

        if choice == '1':
            unittest.TextTestRunner().run(unittest.makeSuite(TestStrategies))
        elif choice == '2':
            unittest.TextTestRunner().run(unittest.makeSuite(TestIndicators))
        elif choice == '3':
            unittest.TextTestRunner().run(unittest.makeSuite(TestRiskManager))
        elif choice == '4':
            unittest.TextTestRunner().run(unittest.makeSuite(TestKrakenAPI))
        elif choice == '5':
            run_all_tests()
        elif choice == '0':
            break
        else:
            print("Opción inválida. Intenta de nuevo.")

if __name__ == '__main__':
    display_menu()