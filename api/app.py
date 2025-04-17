# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request
# from flask_socketio import SocketIO # Para WebSockets (pip install Flask-SocketIO)
# from flask_cors import CORS # Para permitir peticiones desde React en desarrollo (pip install Flask-Cors)
import sys
# Añadir directorio 'bot' al path para importar estado
sys.path.append('..')
from bot import main as bot_main # Para acceder a 'current_position', etc. (Necesita refactorizar estado)
from bot import kraken_api
from bot.utils import logger

app = Flask(__name__)
# CORS(app) # Habilitar CORS si frontend está en dominio/puerto diferente
# socketio = SocketIO(app, cors_allowed_origins="*") # Configurar SocketIO

# --- Estado Global (¡Debería ser gestionado mejor!) ---
# Acceder al estado del bot (current_position) de forma segura (requiere refactorizar bot/main.py)
# Por ahora, simulamos datos.

@app.route('/api/status', methods=['GET'])
def get_status():
    """Endpoint para obtener el estado general y posición actual."""
    logger.debug("API: Solicitud /api/status recibida")
    try:
        balance = kraken_api.get_account_balance() # Obtener balance real
        # Obtener posición actual del estado del bot (simulado por ahora)
        # position = bot_main.current_position
        position = { # Datos simulados
             'pair': 'XBT/USD', 'direction': 'LONG', 'size': 0.01, 'entry_price': 40000,
             'sl': 39800, 'tp1': 40400, 'current_price': 40150,
             'pnl': (40150-40000)*0.01, 'pnl_pct': (40150/40000 - 1)*100
        } if True else None # Simular que hay una posición abierta

        # Calcular PnL Diario (Necesita acceder al historial de trades)
        daily_pnl = 15.50 # Simulado

        return jsonify({
            "bot_running": True, # Simplificado
            "balance": balance,
            "current_position": position,
            "daily_pnl": daily_pnl,
            # Añadir más datos: trades cerrados hoy, etc.
        })
    except Exception as e:
        logger.error(f"API Error en /api/status: {e}", exc_info=True)
        return jsonify({"error": "Error interno al obtener estado"}), 500

@app.route('/api/trades/closed', methods=['GET'])
def get_closed_trades():
    """Endpoint para obtener los trades cerrados recientemente."""
    logger.debug("API: Solicitud /api/trades/closed recibida")
    # Aquí se consultaría el historial de trades (ej. de las últimas 24h)
    # trades = kraken_api.get_trade_history(...)
    simulated_trades = [ # Datos simulados
        {'pair': 'XBT/USD', 'direction': 'LONG', 'size': 0.01, 'entry_price': 39500, 'exit_price': 39700, 'pnl': 2.0, 'reason': 'Take Profit 1', 'time': '2024-04-10 10:30:00'},
        {'pair': 'XBT/USD', 'direction': 'SHORT', 'size': 0.01, 'entry_price': 39800, 'exit_price': 39850, 'pnl': -0.5, 'reason': 'Stop Loss', 'time': '2024-04-10 14:15:00'}
    ]
    return jsonify(simulated_trades)

# --- Endpoints de Control (Ejemplo - ¡Requieren Lógica Segura!) ---
@app.route('/api/control/stop_trade', methods=['POST'])
def stop_trade():
    """Endpoint para cerrar la posición actual manualmente."""
    # ¡¡IMPLEMENTAR CON CUIDADO Y SEGURIDAD!!
    # 1. Obtener ID de la posición/orden a cerrar
    # 2. Llamar a kraken_api.place_order para cerrar al mercado
    # 3. Actualizar estado interno del bot
    logger.warning("API: Solicitud /api/control/stop_trade recibida (No implementado)")
    try:
        # Asumiendo que tienes acceso al estado actual de la posición
        # y a la función para obtener el ID de la orden asociada.
        # Esto es un ejemplo y DEBE ser adaptado a tu implementación real.

        # 1. Obtener la posición actual (ejemplo)
        position = { # Datos simulados - DEBERÍA venir del estado del bot
             'pair': 'XBT/USD', 'direction': 'LONG', 'size': 0.01, 'entry_price': 40000,
             'sl': 39800, 'tp1': 40400, 'current_price': 40150,
             'pnl': (40150-40000)*0.01, 'pnl_pct': (40150/40000 - 1)*100
        } if True else None

        if not position:
            return jsonify({"message": "No hay posición abierta para cerrar"}), 400

        # Determinar el tipo de orden para cerrar (opuesto a la dirección)
        order_type = 'sell' if position['direction'] == 'LONG' else 'buy'

        # 2. Llamar a kraken_api.place_order para cerrar al mercado
        #  Adaptar los parámetros a los que requiere tu función place_order
        #  Esto es un ejemplo y puede requerir ajustes significativos.
        pair = position['pair'].replace('/', '') # Formato del par para Kraken
        volume = position['size'] # Cantidad a cerrar
        order_params = {
            'pair': pair,
            'type': order_type,
            'ordertype': 'market', # Cierra al precio actual de mercado
            'volume': volume
        }
        order_result = kraken_api.place_order(**order_params)

        if order_result and order_result['status'] == 'ok': # Adaptar según la respuesta de Kraken
            # 3. Actualizar estado interno del bot
            #  Esto implica limpiar la posición actual, registrar el trade cerrado, etc.
            #  Depende de cómo gestionas el estado en tu bot.
            # bot_main.clear_position() # Ejemplo: Limpiar la posición
            logger.info(f"API: Orden de cierre enviada: {order_result}")
            return jsonify({"message": "Orden de cierre enviada", "order_info": order_result}), 200
        else:
            logger.error(f"API: Error al enviar orden de cierre: {order_result}")
            return jsonify({"error": "Error al enviar orden de cierre", "details": order_result}), 500

    except Exception as e:
        logger.error(f"API Error en /api/control/stop_trade: {e}", exc_info=True)
        return jsonify({"error": "Error interno al cerrar la posición"}), 500

# --- Ejecución de la API Flask ---
if __name__ == '__main__':
    logger.info("Iniciando API Flask para Dashboard...")
    # Usar socketio.run(app) si se usa SocketIO
    app.run(host='0.0.0.0', port=5000, debug=False) # debug=False en producción