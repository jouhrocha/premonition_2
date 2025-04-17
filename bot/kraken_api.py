# -*- coding: utf-8 -*-
import krakenex
from pykrakenapi import KrakenAPI # Otra opción popular
from bot import config
from bot.utils import logger, exponential_backoff_retry
import pandas as pd
import time

# --- Inicialización del Cliente API ---
# Usando krakenex
k_conn = krakenex.API(config.KRAKEN_API_KEY, config.KRAKEN_API_SECRET)

# O usando pykrakenapi (puede requerir instalación: pip install pykrakenapi)
# api = KrakenAPI(k_conn)

# Nota: La elección de la librería depende de las preferencias y funcionalidades.
# krakenex es más ligero, pykrakenapi ofrece DataFrames directamente.

def check_connection():
    """Verifica la conexión con la API de Kraken."""
    try:
        # Intenta obtener la hora del servidor como prueba de conexión
        response = k_conn.query_public('Time')
        if response.get('error'):
            logger.error(f"Error al conectar con Kraken API: {response['error']}")
            return False
        logger.info("Conexión con Kraken API exitosa.")
        return True
    except Exception as e:
        logger.error(f"Excepción al conectar con Kraken API: {e}", exc_info=True)
        return False

@exponential_backoff_retry
def get_historical_data(pair, interval, since=None):
    """
    Obtiene datos OHLC históricos de Kraken.
    ¡Placeholder! Necesita implementar paginación real y manejo de errores/formato.
    """
    logger.debug(f"Solicitando datos históricos para {pair}, intervalo {interval}, since {since}")
    params = {'pair': pair, 'interval': interval}
    if since:
        params['since'] = since

    try:
        # Usando krakenex directamente
        response = k_conn.query_public('OHLC', params)

        if response.get('error'):
            logger.error(f"Error API al obtener OHLC: {response['error']}")
            # Manejar errores específicos de Kraken aquí (ej. 'EQuery:Unknown asset pair')
            return None

        result = response.get('result', {})
        data = result.get(pair) # Kraken puede devolver el par con formato diferente (ej. XXBTZUSD)
        last_timestamp = result.get('last') # Timestamp de la última vela devuelta, útil para paginación

        if not data:
             # Intentar encontrar el par correcto si el formato difiere
            found_pair = None
            for key in result.keys():
                if key != 'last':
                    found_pair = key
                    data = result[key]
                    logger.warning(f"Formato de par devuelto por API '{found_pair}' difiere de solicitado '{pair}'. Usando datos de '{found_pair}'.")
                    break
            if not data:
                logger.warning(f"No se recibieron datos OHLC para {pair}. Respuesta: {response}")
                return None, None

        # Convertir a DataFrame de Pandas
        # Columnas: time, open, high, low, close, vwap, volume, count
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        # Convertir columnas numéricas
        for col in ['open', 'high', 'low', 'close', 'vwap', 'volume']:
            df[col] = pd.to_numeric(df[col])

        logger.info(f"Recibidos {len(df)} velas históricas para {pair} hasta {df.index.max()}")
        return df, last_timestamp

    except Exception as e:
        logger.error(f"Excepción al obtener datos históricos: {e}", exc_info=True)
        # Re-lanzar la excepción para que exponential_backoff_retry funcione
        raise e

# --- Funciones Placeholder Adicionales (Implementación Real Necesaria) ---

def get_account_balance():
    """Obtiene el balance de la cuenta."""
    logger.info("Obteniendo balance de cuenta (Placeholder)")
    # Aquí iría la llamada a k_conn.query_private('Balance')
    # Ejemplo de respuesta simulada:
    return {'USD': 10000.0, 'XBT': 0.5} # Retornar dict con balances relevantes

def get_ticker_info(pair):
    """Obtiene la información de ticker actual para un par."""
    logger.debug(f"Obteniendo ticker para {pair} (Placeholder)")
    # Aquí iría la llamada a k_conn.query_public('Ticker', {'pair': pair})
    # Ejemplo:
    return {'last_price': 40000.0, 'ask': 40001.0, 'bid': 39999.0}

def place_order(pair, direction, order_type, volume, price=None, stop_price=None, take_profit_price=None):
    """
    Coloca una orden en Kraken.
    ¡Placeholder MUY simplificado! La lógica real necesita manejar la creación de órdenes
    separadas para SL/TP si no hay OCO nativo, y gestionar IDs de órdenes.
    """

    logger.info(f"Intentando colocar orden: {direction} {volume} {pair} @ {price or 'Market'} "
                f"(SL={stop_price}, TP={take_profit_price})")

    try:
        # 1. Construir el diccionario de parámetros para k_conn.query_private('AddOrder', params)
        params = {
            'pair': pair,
            'type': direction,  # 'buy' o 'sell'
            'ordertype': order_type,  # 'market', 'limit', etc.
            'volume': str(volume)  # Debe ser string
        }

        # 2. Manejar 'ordertype': 'market', 'limit', etc.
        if order_type == 'limit' and price:
            params['price'] = str(price)

        #Kraken API permite ordenes OCO (One-Cancels-the-Other) nativas, pero no en todos los pares
        #Para asegurar compatibilidad, implementaremos SL/TP como ordenes separadas.

        # 3. Enviar orden principal.
        response = k_conn.query_private('AddOrder', params)

        if response.get('error'):
            logger.error(f"Error al colocar orden principal: {response['error']}")
            return None

        # 4. Si la orden principal es exitosa (obtener txid), enviar órdenes separadas para SL y TP
        txid = response['result']['txid'][0]  # Obtener el ID de la transacción de la orden principal
        logger.info(f"Orden principal colocada con txid: {txid}")

        # Funciones auxiliares para colocar SL/TP
        def place_sl_tp_order(order_type, price):
            sl_tp_params = {
                'pair': pair,
                'type': order_type,
                'ordertype': 'stop-loss' if 'stop-loss' in order_type else 'take-profit',
                'price': str(price),
                'volume': str(volume),
                'close[ordertype]': 'market' #Cerrar al precio de mercado
            }
            sl_tp_response = k_conn.query_private('AddOrder', sl_tp_params)
            if sl_tp_response.get('error'):
                logger.error(f"Error al colocar orden {order_type}: {sl_tp_response['error']}")
                return None
            sl_tp_txid = sl_tp_response['result']['txid'][0]
            logger.info(f"Orden {order_type} colocada con txid: {sl_tp_txid}")
            return sl_tp_txid

        sl_txid = None
        tp_txid = None

        if stop_price:
            sl_direction = 'buy' if direction == 'sell' else 'sell' #Dirección opuesta para SL
            sl_txid = place_sl_tp_order(sl_direction, stop_price)

        if take_profit_price:
             tp_direction = 'sell' if direction == 'buy' else 'buy' #Dirección opuesta para TP
             tp_txid = place_sl_tp_order(tp_direction, take_profit_price)

        # 5. Registrar IDs de órdenes para seguimiento.
        order_ids = {'main': txid}
        if sl_txid:
            order_ids['stop_loss'] = sl_txid
        if tp_txid:
            order_ids['take_profit'] = tp_txid

        logger.info(f"IDs de órdenes registradas: {order_ids}")

        return order_ids #Retornar dict con todos los IDs

    except Exception as e:
        logger.error(f"Excepción al colocar orden: {e}", exc_info=True)
        return None

    # # Ejemplo de retorno simulado (txid de la orden principal)
    # simulated_txid = f"OFAKE-{int(time.time())}"
    # logger.info(f"Orden simulada colocada con txid: {simulated_txid}")
    # return simulated_txid # Retornar ID de la orden principal

def cancel_order(txid):
    """Cancela una orden abierta."""
    logger.info(f"Cancelando orden {txid} (Placeholder)")
    # Aquí iría la llamada a k_conn.query_private('CancelOrder', {'txid': txid})
    # Retornar True si fue exitoso, False si no.
    return True

def get_open_orders():
    """Obtiene las órdenes abiertas."""
    logger.debug("Consultando órdenes abiertas (Placeholder)")
    # Aquí iría la llamada a k_conn.query_private('OpenOrders')
    # Retornar un diccionario o lista de órdenes abiertas.
    return {}

def get_trade_history(start_time=None):
    """Obtiene el historial de trades."""
    logger.debug("Consultando historial de trades (Placeholder)")
    # Aquí iría la llamada a k_conn.query_private('TradesHistory', {'start': start_time})
    return {}