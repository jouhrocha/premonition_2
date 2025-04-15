# -*- coding: utf-8 -*-
import time
import schedule # Librería para tareas programadas (pip install schedule)
from bot import config, kraken_api, indicators, strategies, risk_manager, backtester
from bot.utils import logger

# --- Estado del Bot ---
current_position = None # Almacena info de la posición actual: {'id', 'pair', 'direction', 'size', 'entry_price', 'sl', 'tp1', 'tp2', 'entry_time'}
active_orders = {}    # Almacena IDs de órdenes activas: {'order_id': 'type'} (ej: 'sl', 'tp1')
last_candle_time = None # Para evitar procesar la misma vela múltiples veces

def check_and_trade():
    """Función principal que se ejecuta periódicamente."""
    global current_position, active_orders, last_candle_time
    logger.debug("Iniciando ciclo de chequeo...")

    # --- 1. Obtener Datos Recientes ---
    # ¡Necesita lógica robusta para obtener la última vela cerrada y evitar datos incompletos!
    # Aquí usamos un placeholder simple.
    try:
        # Obtener últimas N velas (ej. las últimas 200 para calcular indicadores)
        # La función get_historical_data necesita ser adaptada para obtener solo datos recientes
        # o usar otro endpoint de Kraken API si existe.
        # ¡ESTA PARTE ES CRÍTICA Y COMPLEJA EN LA REALIDAD!
        num_candles_needed = max(config.SMA_TREND_PERIOD, config.BREAKOUT_LOOKBACK_PERIOD) + 5
        df_recent, _ = kraken_api.get_historical_data(config.TRADING_PAIR, config.TIMEFRAME) # Simplificado!

        if df_recent is None or df_recent.empty:
            logger.warning("No se obtuvieron datos recientes.")
            return

        # Verificar si hay una nueva vela
        latest_time = df_recent.index[-1]
        if last_candle_time is not None and latest_time <= last_candle_time:
             logger.debug("Sin nueva vela para procesar.")
             return
        last_candle_time = latest_time
        logger.info(f"Procesando nueva vela: {latest_time}")

        # Calcular indicadores
        df_recent = indicators.add_indicators(df_recent)
        if df_recent is None: return

    except Exception as e:
        logger.error(f"Error al obtener/procesar datos: {e}", exc_info=True)
        return

    # --- 2. Gestionar Posición Abierta (Si existe) ---
    if current_position:
        # A. Verificar SL/TP (Kraken podría hacerlo, pero confirmamos)
        #    (Necesitaría consultar estado de órdenes SL/TP o precio actual)
        # B. Mover a Break-Even
        # C. Aplicar Trailing Stop
        #    (Estas lógicas necesitan implementación detallada consultando precios actuales
        #     y modificando órdenes SL vía API)
        logger.debug(f"Posición abierta detectada: {current_position['direction']} {current_position['size']} {current_position['pair']}")
        # Placeholder para lógica de gestión
        pass # Implementar gestión de posición activa

    # --- 3. Buscar Señales de Entrada (Si no hay posición) ---
    else:
        # Aplicar Filtros (Noticias, Horario, Correlación - Placeholders)
        is_safe_to_trade = True # Asumir True, implementar filtros reales
        # if not filtro_noticias() or not filtro_horario(): is_safe_to_trade = False

        if is_safe_to_trade:
            # Evaluar estrategias
            signal_status_rev, signal_details_rev = strategies.check_reversal_signal(df_recent)
            signal_status_brk, signal_details_brk = strategies.check_breakout_signal(df_recent)

            signal_to_execute = None
            if signal_status_rev == strategies.SIGNAL_GREEN:
                signal_to_execute = signal_details_rev
            elif signal_status_brk == strategies.SIGNAL_GREEN:
                # Podríamos tener lógica para priorizar una sobre otra si ambas dan señal
                signal_to_execute = signal_details_brk

            if signal_to_execute:
                logger.info(f"¡Señal Verde encontrada! {signal_to_execute['details']}")
                try:
                    # Calcular tamaño
                    entry_p = signal_to_execute['entry_price'] # Precio de entrada propuesto
                    sl_p = signal_to_execute['stop_loss']
                    tp1_p = signal_to_execute['take_profit_1']
                    tp2_p = signal_to_execute.get('take_profit_2')

                    # Podríamos ajustar entry_p al precio actual de mercado o ask/bid
                    ticker = kraken_api.get_ticker_info(config.TRADING_PAIR)
                    actual_entry_price = ticker['ask'] if signal_to_execute['direction'] == 'LONG' else ticker['bid']
                    # Recalcular TPs basados en el precio de entrada real
                    risk_real = abs(actual_entry_price - sl_p)
                    tp1_p_real = actual_entry_price + config.TP_RR_RATIO_1 * risk_real if signal_to_execute['direction'] == 'LONG' else actual_entry_price - config.TP_RR_RATIO_1 * risk_real
                    tp2_p_real = actual_entry_price + config.TP_RR_RATIO_2 * risk_real if signal_to_execute['direction'] == 'LONG' and tp2_p else (actual_entry_price - config.TP_RR_RATIO_2 * risk_real if signal_to_execute['direction'] != 'LONG' and tp2_p else None)


                    size = risk_manager.calculate_position_size(actual_entry_price, sl_p)

                    if size > 0:
                        # Colocar Orden Bracket (Entrada + SL + TP)
                        # ¡La lógica real aquí es compleja! Debe manejar la colocación
                        # secuencial si Kraken no tiene OCO nativo.
                        order_id = kraken_api.place_order(
                            pair=config.TRADING_PAIR,
                            direction=signal_to_execute['direction'],
                            order_type='market', # O 'limit' con actual_entry_price
                            volume=size,
                            price=None, # Para market order
                            stop_price=sl_p,
                            take_profit_price=tp1_p_real # Asumimos que place_order maneja TPs múltiples o lo hacemos aquí
                        )

                        if order_id:
                            logger.info(f"Orden de entrada {signal_to_execute['strategy']} {signal_to_execute['direction']} enviada. Size={size:.8f}. OrderID={order_id}")
                            # Actualizar estado interno (asumiendo que la orden se ejecutará pronto)
                            # ¡En un bot real, se debe esperar confirmación de ejecución!
                            current_position = {
                                'id': order_id, # ID de la orden principal
                                'pair': config.TRADING_PAIR,
                                'direction': signal_to_execute['direction'],
                                'size': size,
                                'entry_price': actual_entry_price, # Precio estimado/real
                                'sl': sl_p,
                                'tp1': tp1_p_real,
                                'tp2': tp2_p_real,
                                'entry_time': latest_time # O tiempo de ejecución real
                            }
                            # Registrar órdenes SL/TP asociadas en active_orders (si se crearon separadas)
                            # active_orders[sl_order_id] = 'sl'
                            # active_orders[tp1_order_id] = 'tp1'
                        else:
                            logger.error("Fallo al colocar la orden de entrada.")
                    else:
                         logger.warning("Tamaño de posición calculado es 0. No se abre trade.")

                except Exception as e:
                    logger.error(f"Error al intentar ejecutar la señal: {e}", exc_info=True)

        else:
             logger.info("Filtros activos (Noticias/Horario/Correlación). No se buscan entradas.")


def run_bot():
    """Configura y ejecuta el bucle principal del bot."""
    logger.info("Iniciando Trading Bot...")
    if not kraken_api.check_connection():
        logger.critical("No se pudo conectar a Kraken API. Saliendo.")
        return

    # --- Programar la ejecución periódica ---
    # Ejecutar cada minuto (ajustar según timeframe y estrategia)
    schedule.every(1).minute.at(":01").do(check_and_trade) # Ejecutar 1 seg después del inicio del minuto
    logger.info(f"Bot programado para ejecutarse cada minuto (Timeframe: {config.TIMEFRAME}m)")

    # Ejecutar la primera vez inmediatamente
    check_and_trade()

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # Opción para correr backtest en lugar del bot en vivo
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'backtest':
        backtester.run_backtest(
            pair=config.TRADING_PAIR,
            interval=config.TIMEFRAME,
            start_date='2024-01-01', # Fechas de ejemplo
            end_date='2024-03-31'
        )
    else:
        run_bot()