# -*- coding: utf-8 -*-
import logging
import time
from bot import config

def setup_logging():
    """Configura el sistema de logging."""
    log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler("trading_bot.log"), # Escribir a archivo
            logging.StreamHandler()                # Escribir a consola
        ]
    )
    # Silenciar logs muy verbosos de librerías externas si es necesario
    # logging.getLogger("requests").setLevel(logging.WARNING)
    # logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger("TradingBot")

logger = setup_logging()

def exponential_backoff_retry(func, *args, **kwargs):
    """
    Decorador o función helper para reintentar una función con backoff exponencial.
    Útil para llamadas a API que pueden fallar temporalmente.
    """
    retries = 0
    delay = config.API_RETRY_DELAY
    while retries < config.MAX_API_RETRIES:
        try:
            result = func(*args, **kwargs)
            return result # Éxito
        except Exception as e:
            retries += 1
            if retries >= config.MAX_API_RETRIES:
                logger.error(f"Error en {func.__name__} tras {retries} intentos: {e}", exc_info=True)
                raise # Propagar el error final
            else:
                logger.warning(f"Intento {retries}/{config.MAX_API_RETRIES} fallido para {func.__name__}: {e}. Reintentando en {delay}s...")
                time.sleep(delay)
                delay *= 2 # Backoff exponencial
    # Esta línea no debería alcanzarse si MAX_API_RETRIES > 0
    return None