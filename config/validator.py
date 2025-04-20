import json
from PyQt5.QtWidgets import QMessageBox, QTimer # type: ignore
config = 'config/settings.json'
def cargar_configuracion(config):
    try:
        with open(config, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return None

def validar_configuracion(config):
    modulos_requeridos = {
        'api': ['exchange', 'api_key', 'api_secret', 'testnet'],
        'exchange': ['name', 'api_key', 'api_secret', 'testnet', 'rate_limit'],
        'trading': ['symbol', 'timeframe', 'historical_days', 'position_size', 'leverage', 'mode'],
        'data_collection': ['symbols', 'timeframes', 'days_to_collect', 'batch_size']
    }

    errores = []

    for modulo, claves in modulos_requeridos.items():
        if modulo not in config:
            errores.append(f"Falta módulo '{modulo}'")
            continue

        for clave in claves:
            if clave not in config[modulo] or config[modulo][clave] in [None, '', []]:
                errores.append(f"Configuración incorrecta en '{modulo}': Falta o vacío '{clave}'")

    return errores

def run(self):
    self.show()

    self.config = cargar_configuracion()

    if not self.config:
        QMessageBox.critical(self, 'Error', 'No se pudo cargar la configuración. Verifica settings.json')
        return

    errores_config = validar_configuracion(self.config)

    if errores_config:
        mensaje_error = "Errores en configuración:\n" + "\n".join(errores_config)
        QMessageBox.critical(self, 'Error en Configuración', mensaje_error)
        return

    # Configuración correcta; iniciar lógica habitual
    if self.config.get('auto_start_collection', False):
        self.start_collection_btn.setEnabled(False)
        self.collect_data_btn.setEnabled(False)
        self.stop_collection_btn.setEnabled(True)

    # Actualización periódica cada 5 minutos
    self.update_timer = QTimer(self)
    self.update_timer.timeout.connect(self.update_data_table)
    self.update_timer.start(300000)
    self.update_data_table()
    self.show()
    
