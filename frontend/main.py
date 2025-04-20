#!/usr/bin/env python3
import sys
import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import gc
import ccxt
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, # type: ignore
                             QPushButton, QLabel, QComboBox, QTabWidget, QLineEdit, QTableWidget,
                             QHeaderView, QCheckBox, QGroupBox, QGridLayout, QSpinBox, QMessageBox, QFileDialog,
                             QTableWidgetItem, QSplitter, QTextEdit, QProgressBar,QDoubleSpinBox, QAction, QListWidget, QCompleter)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer # type: ignore
from PyQt5.QtGui import QFont # type: ignore

# Helpers y utils
from utils.helpers import setup_windows_compatibility, save_config_to_file, load_config_from_file
from utils.database import PatternDatabase
from core.bot import MultiSymbolTradingBot
from core.backtester import Backtester
from core.data_collector import DataCollector
from core.pattern_analyzer import PatternAnalyzer

logger = logging.getLogger(__name__)

# Ajustar compatibilidad Windows
setup_windows_compatibility()
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('main')

# Ahora inicializar el exchange
exchange = None
markets = {}
symbols = []

try:
    exchange = ccxt.kraken()
    markets = exchange.load_markets()
    symbols = list(markets.keys())
    logger.info("Exchange inicializado correctamente (Símbolos cargados).")
except Exception as e:
    logger.error(f"Error al cargar símbolos de Kraken por defecto: {e}")
    symbols = ["BTC/USD", "ETH/USD", "XRP/USD"]  # fallback

# Un tema oscuro simple
DARK_THEME = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #45475a;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #b4befe;
}
QPushButton:pressed {
    background-color: #74c7ec;
}
QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 2px 4px;
}
QTableWidget {
    background-color: #313244;
    alternate-background-color: #45475a;
    color: #cdd6f4;
    gridline-color: #45475a;
    border: none;
}
QTableWidget::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QHeaderView::section {
    background-color: #45475a;
    color: #cdd6f4;
    padding: 6px;
    border: none;
}
QProgressBar {
    border: none;
    background-color: #313244;
    text-align: center;
    color: #1e1e2e;
    border-radius: 4px;
}
QProgressBar::chunk {
    background-color: #a6e3a1;
    border-radius: 4px;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 4px;
    margin-top: 12px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
}
QTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
}
QSplitter::handle {
    background-color: #45475a;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 3px;
    border: 1px solid #45475a;
}
QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border: 1px solid #89b4fa;
}
"""

class LogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal
    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

class WorkerThread(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)    
    finished_signal = pyqtSignal(bool, object)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.func(*self.args, **self.kwargs))
            self.finished_signal.emit(True, result)
        except Exception as e:
            logging.error(f"Error en hilo de trabajo: {e}")
            self.finished_signal.emit(False, str(e))
class SymbolCompleter(QCompleter):
    """Completer personalizado para símbolos de trading"""
    def __init__(self, symbols, parent=None):
        super().__init__(symbols, parent)
        self.setCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterMode(Qt.MatchContains)
        
class TradingPatternAnalyzerApp(QMainWindow):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.config: Dict[str, Any] = {}
        self.data_collector = None
        self.pattern_analyzer = None
        self.backtester = None
        self.trading_bot = None

        self.init_ui()         
        self.load_config()    # Carga config de settings.json (sin crear nueva)
        self.setup_logging()  
        self.update_ui_from_config()

    def setup_logging(self):
        handler = LogHandler(self.log_signal)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        self.log_signal.connect(self.append_log_message)

    @pyqtSlot(str)
    def append_log_message(self, msg: str):
        self.log_text.append(msg)

    def load_config(self):
        """
        Intenta cargar 'config/settings.json'.
        Si no existe, muestra un warning pero no crea archivo nuevo.
        """
        path = "config/settings.json"
        cfg = load_config_from_file(path)
        if cfg is None:
            logger.warning("No se pudo cargar config/settings.json. Asegúrate de que exista.")
            cfg = {}
        self.config = cfg
        logger.info("Configuración cargada correctamente")

    def save_config(self):
        # Asegurar que existan secciones mínimas
        if "exchange" not in self.config:
            self.config["exchange"] = {}
        path = "config/settings.json"
        ok = save_config_to_file(self.config, path)
        if ok:
            self.statusBar().showMessage("Configuración guardada con éxito")
        else:
            self.statusBar().showMessage("Error al guardar configuración")

    def update_ui_from_config(self):
        """Refleja los valores de self.config en la interfaz (combos, etc.)."""
        trading_cfg = self.config.get('trading', {})
        symbol = trading_cfg.get('symbol', "BTC/USD")
        timeframe = trading_cfg.get('timeframe', "1h")

        idx_s = self.symbols_combo.findText(symbol)
        if idx_s >= 0:
            self.symbols_combo.setCurrentIndex(idx_s)
        idx_t = self.timeframe_combo.findText(timeframe)
        if idx_t >= 0:
            self.timeframe_combo.setCurrentIndex(idx_t)

    def init_ui(self):
        self.setWindowTitle("Trading Pattern Analyzer")
        self.setMinimumSize(1200, 800)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("Archivo")

        load_config_action = QAction("Cargar configuración", self)
        # que use self.load_config (ya NO load_or_create_config)
        load_config_action.triggered.connect(self.load_config)
        file_menu.addAction(load_config_action)

        save_config_action = QAction("Guardar configuración", self)
        save_config_action.triggered.connect(self.save_config)
        file_menu.addAction(save_config_action)

        file_menu.addSeparator()

        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # 1) Dashboard
        self.dashboard_tab = QWidget()
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.setup_dashboard_tab()

        # 2) Data Collection
        self.data_collection_tab = QWidget()
        self.tabs.addTab(self.data_collection_tab, "Recopilación de Datos")
        self.setup_data_collection_tab()

        # 3) Pattern Analysis
        self.pattern_analysis_tab = QWidget()
        self.tabs.addTab(self.pattern_analysis_tab, "Análisis de Patrones")
        self.setup_pattern_analysis_tab()

        # 4) Backtesting
        self.backtest_tab = QWidget()
        self.tabs.addTab(self.backtest_tab, "Backtesting")
        self.setup_backtest_tab()

        # 5) Live Trading
        self.live_trading_tab = QWidget()
        self.tabs.addTab(self.live_trading_tab, "Trading en Vivo")
        self.setup_live_trading_tab()

        # 6) Settings
        self.settings_tab = QWidget()
        self.tabs.addTab(self.settings_tab, "Configuración")
        self.setup_settings_tab()

        self.statusBar().showMessage("Listo")
        self.setStyleSheet(DARK_THEME)

    def setup_dashboard_tab(self):
        layout = QVBoxLayout()
        title_label = QLabel("Dashboard Principal")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Contenedor principal
        main_container = QSplitter(Qt.Horizontal)
        
        # Panel izquierdo - Resumen
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Grupo de estadísticas
        stats_group = QGroupBox("Estadísticas de Trading")
        stats_layout = QGridLayout()
        
        stats_layout.addWidget(QLabel("Patrones detectados:"), 0, 0)
        self.patterns_count_label = QLabel("0")
        stats_layout.addWidget(self.patterns_count_label, 0, 1)
        
        stats_layout.addWidget(QLabel("Patrones rentables:"), 1, 0)
        self.profitable_patterns_label = QLabel("0")
        stats_layout.addWidget(self.profitable_patterns_label, 1, 1)
        
        stats_layout.addWidget(QLabel("Tasa de éxito:"), 2, 0)
        self.success_rate_label = QLabel("0%")
        stats_layout.addWidget(self.success_rate_label, 2, 1)
        
        stats_layout.addWidget(QLabel("Balance actual:"), 3, 0)
        self.current_balance_label = QLabel("$0.00")
        stats_layout.addWidget(self.current_balance_label, 3, 1)
        
        stats_group.setLayout(stats_layout)
        left_layout.addWidget(stats_group)
        
        # Grupo de acciones rápidas
        actions_group = QGroupBox("Acciones Rápidas")
        actions_layout = QVBoxLayout()
        
        self.collect_data_btn = QPushButton("Recopilar Datos")
        self.collect_data_btn.clicked.connect(self.start_data_collection)
        actions_layout.addWidget(self.collect_data_btn)
        
        self.analyze_patterns_btn = QPushButton("Analizar Patrones")
        self.analyze_patterns_btn.clicked.connect(self.start_pattern_analysis)
        actions_layout.addWidget(self.analyze_patterns_btn)
        
        self.run_backtest_button = QPushButton("Ejecutar Backtest")
        self.run_backtest_button.clicked.connect(self.start_backtest)
        actions_layout.addWidget(self.run_backtest_button)
        
        self.start_trading_btn = QPushButton("Iniciar Trading")
        self.start_trading_btn.clicked.connect(self.start_live_trading)
        actions_layout.addWidget(self.start_trading_btn)
        
        actions_group.setLayout(actions_layout)
        left_layout.addWidget(actions_group)
        
        # Espacio flexible
        left_layout.addStretch()
        
        # Panel derecho - Logs y gráficos
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Logs
        logs_group = QGroupBox("Logs del Sistema")
        logs_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        logs_layout.addWidget(self.log_text)
        logs_group.setLayout(logs_layout)
        right_layout.addWidget(logs_group)
        
        # Añadir paneles al contenedor principal
        main_container.addWidget(left_panel)
        main_container.addWidget(right_panel)
        main_container.setSizes([300, 700])
        
        layout.addWidget(main_container)
        self.dashboard_tab.setLayout(layout)

    def setup_data_collection_tab(self):
        layout = QVBoxLayout()
        
        # Título
        title_label = QLabel("Recopilación de Datos Históricos")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Formulario de configuración
        form_group = QGroupBox("Configuración de Recopilación")
        form_layout = QGridLayout()

        form_layout.addWidget(QLabel("Símbolos:"), 0, 0)
        self.symbols_combo = QComboBox()
        self.symbols_combo.setEditable(True)
        self.symbols_combo.addItems(symbols)

        # Autocompletado
        completer = SymbolCompleter(symbols, self.symbols_combo)

        self.symbols_combo.setCompleter(completer)
        self.selected_symbols = []
        self.symbols_combo.currentTextChanged.connect(self.on_symbol_text_changed)
        form_layout.addWidget(self.symbols_combo, 0, 1)

        # Botón para eliminar símbolos seleccionados
        self.clear_symbols_btn = QPushButton("Limpiar selección")
        self.clear_symbols_btn.clicked.connect(self.clear_selected_symbols)
        form_layout.addWidget(self.clear_symbols_btn, 0, 2)
        
        # Mostrar símbolos seleccionados en un widget más interactivo
        self.selected_symbols_widget = QWidget()
        self.selected_symbols_layout = QHBoxLayout(self.selected_symbols_widget)
        self.selected_symbols_layout.setContentsMargins(0, 0, 0, 0)
        self.selected_symbols_layout.setSpacing(5)
        self.selected_symbols_layout.addStretch()
        form_layout.addWidget(self.selected_symbols_widget, 1, 0, 1, 3)
        
        # Timeframes
        form_layout.addWidget(QLabel("Timeframes:"), 2, 0)
        self.timeframes_combo = QComboBox()
        self.timeframes_combo.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        form_layout.addWidget(self.timeframes_combo, 2, 1)
        
        # Días a recopilar
        form_layout.addWidget(QLabel("Días a recopilar:"), 3, 0)
        self.days_spinbox = QSpinBox()
        self.days_spinbox.setRange(1, 1000)
        self.days_spinbox.setValue(30)
        form_layout.addWidget(self.days_spinbox, 3, 1)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Botones de acción
        buttons_layout = QHBoxLayout()
        
        self.start_collection_btn = QPushButton("Iniciar Recopilación")
        self.start_collection_btn.clicked.connect(self.start_data_collection)
        buttons_layout.addWidget(self.start_collection_btn)
        
        self.stop_collection_btn = QPushButton("Detener Recopilación")
        self.stop_collection_btn.setEnabled(False)
        buttons_layout.addWidget(self.stop_collection_btn)
        
        layout.addLayout(buttons_layout)
        
        # Barra de progreso
        self.collection_progress = QProgressBar()
        layout.addWidget(self.collection_progress)
        
        # Tabla de datos recopilados
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(4)
        self.data_table.setHorizontalHeaderLabels(["Símbolo", "Timeframe", "Desde", "Hasta"])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.data_table)
        
        self.data_collection_tab.setLayout(layout)
    def on_symbol_text_changed(self, text):
        """Maneja los cambios en el texto del combo de símbolos"""
        if not text:
            return
            
        # Si se presiona Enter o se selecciona un símbolo
        if text in symbols and text not in self.selected_symbols:
            self.selected_symbols.append(text)
            self.update_selected_symbols_widget()
            self.symbols_combo.setCurrentText("")  # Limpiar el campo
    def update_selected_symbols_widget(self):
        """Actualiza el widget con los símbolos seleccionados como etiquetas interactivas"""
        # Limpiar el layout actual
        while self.selected_symbols_layout.count() > 1:
            item = self.selected_symbols_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Añadir cada símbolo como una etiqueta con botón de eliminar
        for symbol in self.selected_symbols:
            symbol_widget = QWidget()
            symbol_layout = QHBoxLayout(symbol_widget)
            symbol_layout.setContentsMargins(5, 2, 5, 2)
            symbol_layout.setSpacing(3)
            
            # Etiqueta con el símbolo
            label = QLabel(symbol)
            label.setStyleSheet("background-color: #45475a; padding: 3px 6px; border-radius: 3px;")
            symbol_layout.addWidget(label)
            
            # Botón para eliminar el símbolo
            remove_btn = QPushButton("×")
            remove_btn.setFixedSize(20, 20)
            remove_btn.setStyleSheet("background-color: transparent; color: #f38ba8; font-weight: bold; border: none;")
            remove_btn.clicked.connect(lambda checked, s=symbol: self.remove_selected_symbol(s))
            symbol_layout.addWidget(remove_btn)
            
            self.selected_symbols_layout.insertWidget(self.selected_symbols_layout.count()-1, symbol_widget)

    def remove_selected_symbol(self, symbol):
        """Elimina un símbolo de la lista de seleccionados"""
        if symbol in self.selected_symbols:
            self.selected_symbols.remove(symbol)
            self.update_selected_symbols_widget()
    def clear_selected_symbols(self):
        """Limpia todos los símbolos seleccionados"""
        self.selected_symbols = []
        self.update_selected_symbols_widget()
    async def start_data_collection_async(self):
        data_collector = None
        try:
            self.save_settings(False)
            os.makedirs('data/historical', exist_ok=True)
            
            if 'api' not in self.config:
                exchange_config = self.config.get('exchange', {})
                self.config['api'] = {
                    'exchange': exchange_config.get('name', 'binance'),
                    'api_key': exchange_config.get('api_key', ''),
                    'api_secret': exchange_config.get('api_secret', ''),
                    'testnet': exchange_config.get('testnet', False)
                }
            
            # Usar los símbolos seleccionados en lugar del texto del campo
            if hasattr(self, 'selected_symbols') and self.selected_symbols:
                self.config['data_collection']['symbols'] = self.selected_symbols
            else:
                # Si no hay símbolos seleccionados, usar el texto actual del combo
                symbol_text = self.symbols_combo.currentText()
                if symbol_text:
                    self.config['data_collection']['symbols'] = [symbol_text]
            
            # Guardar la referencia al data_collector como atributo de la clase
            self.data_collector = DataCollector(self.config)
            await self.data_collector.initialize()
            result = await self.data_collector.run()
            
            # No cerramos el data_collector aquí, lo haremos en closeEvent
            return result
        except Exception as e:
            logger.error(f"Error en la recopilación asíncrona: {e}")
            # Solo cerramos en caso de error
            if self.data_collector and hasattr(self.data_collector, 'close'):
                try:
                    await self.data_collector.close()
                    logger.info("Data collector cerrado debido a error")
                except Exception as close_error:
                    logger.error(f"Error al cerrar data_collector: {close_error}")
            raise


    def setup_pattern_analysis_tab(self):
        layout = QVBoxLayout()

        title_label = QLabel("Análisis de Patrones de Trading")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Contenedor principal
        main_container = QSplitter(Qt.Horizontal)
        
        # Panel izquierdo - Configuración
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Grupo de configuración
        config_group = QGroupBox("Configuración de Análisis")
        config_layout = QGridLayout()
        
        config_layout.addWidget(QLabel("Símbolo:"), 0, 0)
        self.analysis_symbol_combo = QComboBox()
        config_layout.addWidget(self.analysis_symbol_combo, 0, 1)
        
        config_layout.addWidget(QLabel("Timeframe:"), 1, 0)
        self.analysis_timeframe_combo = QComboBox()
        self.analysis_timeframe_combo.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        config_layout.addWidget(self.analysis_timeframe_combo, 1, 1)
        
        config_layout.addWidget(QLabel("Velas de lookback:"), 2, 0)
        self.lookback_spinbox = QSpinBox()
        self.lookback_spinbox.setRange(1, 100)
        self.lookback_spinbox.setValue(5)
        config_layout.addWidget(self.lookback_spinbox, 2, 1)
        
        config_layout.addWidget(QLabel("Velas de lookforward:"), 3, 0)
        self.lookforward_spinbox = QSpinBox()
        self.lookforward_spinbox.setRange(1, 100)
        self.lookforward_spinbox.setValue(10)
        config_layout.addWidget(self.lookforward_spinbox, 3, 1)
        
        config_layout.addWidget(QLabel("Tasa de éxito mínima (%):"), 4, 0)
        self.min_success_rate_spinbox = QDoubleSpinBox()
        self.min_success_rate_spinbox.setRange(1, 100)
        self.min_success_rate_spinbox.setValue(60)
        config_layout.addWidget(self.min_success_rate_spinbox, 4, 1)
        
        config_group.setLayout(config_layout)
        left_layout.addWidget(config_group)
        
        # Botones de acción
        self.run_analysis_btn = QPushButton("Ejecutar Análisis")
        self.run_analysis_btn.clicked.connect(self.start_pattern_analysis)
        left_layout.addWidget(self.run_analysis_btn)
        
        # Espacio flexible
        left_layout.addStretch()
        
        # Panel derecho - Resultados
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Tabla de patrones
        self.patterns_table = QTableWidget()
        self.patterns_table.setColumnCount(5)
        self.patterns_table.setHorizontalHeaderLabels(["ID", "Tipo", "Tasa de Éxito", "Ocurrencias", "Ratio P/L"])
        self.patterns_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.patterns_table)
        
        # Añadir paneles al contenedor principal
        main_container.addWidget(left_panel)
        main_container.addWidget(right_panel)
        main_container.setSizes([300, 700])
        
        layout.addWidget(main_container)
        self.pattern_analysis_tab.setLayout(layout)

    def start_pattern_analysis(self):
        logger.info("Iniciando análisis de patrones...")
        self.run_analysis_btn.setEnabled(False)
        self.analysis_thread = WorkerThread(self.analyze_patterns_async)
        self.analysis_thread.finished_signal.connect(self.on_analysis_finished)
        self.analysis_thread.start()

    async def analyze_patterns_async(self):
        try:
            # Configuración del análisis de patrones (de start_pattern_analysis_async)
            if 'pattern_analysis' not in self.config:
                self.config['pattern_analysis'] = {}
            
            self.config['pattern_analysis'].update({
                'min_success_rate': self.min_success_rate_spinbox.value(),
                'lookback_candles': self.lookback_spinbox.value(),
                'lookforward_candles': self.lookforward_spinbox.value(),
                'min_profit_ratio': 1.5,
                'max_error_rate': 5.0
            })
            
            self.config['trading']['symbol'] = self.analysis_symbol_combo.currentText()
            self.config['trading']['timeframe'] = self.analysis_timeframe_combo.currentText()
            
            # Configuración de la base de datos
            if 'database' not in self.config:
                self.config['database'] = {}
            
            pattern_db_path = self.config['database'].get('path', 'data/patterns.db')
            os.makedirs(os.path.dirname(pattern_db_path), exist_ok=True)
            
            # Cerrar analizador de patrones anterior si existe
            if hasattr(self, 'pattern_analyzer') and self.pattern_analyzer:
                if hasattr(self.pattern_analyzer, 'close'):
                    await self.pattern_analyzer.close()
            
            # Inicializar la base de datos de patrones
            from core.pattern_analyzer import PatternAnalyzer
            from utils.database import PatternDatabase
            
            pdb = PatternDatabase(pattern_db_path)
            await pdb.initialize()
            
            # Crear y configurar el analizador
            self.pattern_analyzer = PatternAnalyzer(self.config, pdb)
            
            if hasattr(self.pattern_analyzer, 'initialize'):
                await self.pattern_analyzer.initialize()
            
            # Ejecutar el análisis con verificación de métodos disponibles
            results = None
            
            if hasattr(self.pattern_analyzer, 'run_analysis'):
                results = await self.pattern_analyzer.run_analysis()
            elif hasattr(self.pattern_analyzer, 'analyze'):
                results = await self.pattern_analyzer.analyze()
            elif hasattr(self.pattern_analyzer, 'run'):
                results = await self.pattern_analyzer.run()
            else:
                logger.info("No se encontró un método de análisis específico, usando el objeto directamente")
                # Intentar extraer patrones directamente
                if hasattr(self.pattern_analyzer, 'patterns'):
                    results = self.pattern_analyzer.patterns
                else:
                    results = self.pattern_analyzer
            
            # Registrar el tipo de resultado para depuración
            logger.info(f"Tipo de resultado del análisis: {type(results)}")
            
            # Cerrar la base de datos
            await pdb.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Error en el análisis asíncrono de patrones: {e}")
            raise

    def on_analysis_finished(self, success, message):
        self.run_analysis_btn.setEnabled(True)
        self.analyze_patterns_btn.setEnabled(True)

        if success:
            logger.info("Análisis de patrones completado")
            patterns = message if isinstance(message, list) else []
            if not patterns:
                logger.info("No se encontraron patrones relevantes")
                self.statusBar().showMessage("No se encontraron patrones relevantes")
            else:
                logger.info(f"Patrones detectados: {len(patterns)}")
                self.statusBar().showMessage("Análisis completado")
                self.show_patterns_in_table(patterns)
        else:
            logger.error(f"Error en el análisis de patrones: {message}")
            self.statusBar().showMessage(f"Error: {message}")

    def show_patterns_in_table(self, patterns):
        """Rellena la tabla patterns_table con los patrones."""
        self.patterns_table.setRowCount(0)
        self.patterns_table.setRowCount(len(patterns))
        for i, pat in enumerate(patterns):
            pid = pat.get("id","")
            pname = pat.get("name","")
            sr = f"{pat.get('success_rate',0):.2f}%"
            occ = str(pat.get("total_occurrences",0))
            self.patterns_table.setItem(i,0, QTableWidgetItem(pid))
            self.patterns_table.setItem(i,1, QTableWidgetItem(pname))
            self.patterns_table.setItem(i,2, QTableWidgetItem(sr))
            self.patterns_table.setItem(i,3, QTableWidgetItem(occ))

    def setup_backtest_tab(self):
        layout = QVBoxLayout()
        title_label = QLabel("Backtesting de Estrategias")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        main_container = QSplitter(Qt.Horizontal)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        config_group = QGroupBox("Configuración de Backtest")
        config_layout = QGridLayout()
        
        config_layout.addWidget(QLabel("Símbolo:"), 0, 0)
        self.backtest_symbol_combo = QComboBox()
        self.backtest_symbol_combo.addItems(symbols)
        config_layout.addWidget(self.backtest_symbol_combo, 0, 1)
        
        config_layout.addWidget(QLabel("Timeframe:"), 1, 0)
        self.backtest_timeframe_combo = QComboBox()
        self.backtest_timeframe_combo.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        config_layout.addWidget(self.backtest_timeframe_combo, 1, 1)
        
        config_layout.addWidget(QLabel("Período de backtesting:"), 2, 0)
        self.backtest_period_combo = QComboBox()
        self.backtest_period_combo.addItems(["1 día", "1 semana", "1 mes", "3 meses", "6 meses", "1 año"])
        config_layout.addWidget(self.backtest_period_combo, 2, 1)
        
        config_layout.addWidget(QLabel("Capital inicial:"), 3, 0)
        self.initial_capital_spinbox = QDoubleSpinBox()
        self.initial_capital_spinbox.setRange(1, 1000000)
        self.initial_capital_spinbox.setValue(1000)
        self.initial_capital_spinbox.setPrefix("$")
        config_layout.addWidget(self.initial_capital_spinbox, 3, 1)
        
        config_layout.addWidget(QLabel("Riesgo por operación (%):"), 4, 0)
        self.risk_per_trade_spinbox = QDoubleSpinBox()
        self.risk_per_trade_spinbox.setRange(0.1, 100)
        self.risk_per_trade_spinbox.setValue(2)
        self.risk_per_trade_spinbox.setSuffix("%")
        config_layout.addWidget(self.risk_per_trade_spinbox, 4, 1)
        
        config_layout.addWidget(QLabel("Take Profit (%):"), 5, 0)
        self.take_profit_spinbox = QDoubleSpinBox()
        self.take_profit_spinbox.setRange(0.1, 100)
        self.take_profit_spinbox.setValue(2)
        self.take_profit_spinbox.setSuffix("%")
        config_layout.addWidget(self.take_profit_spinbox, 5, 1)
        
        config_layout.addWidget(QLabel("Stop Loss (%):"), 6, 0)
        self.stop_loss_spinbox = QDoubleSpinBox()
        self.stop_loss_spinbox.setRange(0.1, 100)
        self.stop_loss_spinbox.setValue(1)
        self.stop_loss_spinbox.setSuffix("%")
        config_layout.addWidget(self.stop_loss_spinbox, 6, 1)
        
        config_group.setLayout(config_layout)
        left_layout.addWidget(config_group)
        
        self.run_backtest_button = QPushButton("Ejecutar Backtest")
        self.run_backtest_button.clicked.connect(self.start_backtest)
        left_layout.addWidget(self.run_backtest_button)
        
        left_layout.addStretch()
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

         # Result table
        self.backtest_results_table = QTableWidget()
        self.backtest_results_table.setColumnCount(2)
        results_group = QGroupBox("Resultados del Backtest")
        results_layout = QGridLayout()
        
        results_layout.addWidget(QLabel("Balance final:"), 0, 0)
        self.final_balance_label = QLabel("$0.00")
        results_layout.addWidget(self.final_balance_label, 0, 1)
        
        results_layout.addWidget(QLabel("Retorno total:"), 1, 0)
        self.total_return_label = QLabel("0%")
        results_layout.addWidget(self.total_return_label, 1, 1)
        
        results_layout.addWidget(QLabel("Operaciones totales:"), 2, 0)
        self.total_trades_label = QLabel("0")
        results_layout.addWidget(self.total_trades_label, 2, 1)
        
        results_layout.addWidget(QLabel("Operaciones ganadoras:"), 3, 0)
        self.winning_trades_label = QLabel("0")
        results_layout.addWidget(self.winning_trades_label, 3, 1)
        
        results_layout.addWidget(QLabel("Operaciones perdedoras:"), 4, 0)
        self.losing_trades_label = QLabel("0")
        results_layout.addWidget(self.losing_trades_label, 4, 1)
        
        results_layout.addWidget(QLabel("Tasa de acierto:"), 5, 0)
        self.win_rate_label = QLabel("0%")
        results_layout.addWidget(self.win_rate_label, 5, 1)
        
        results_layout.addWidget(QLabel("Ratio de beneficio:"), 6, 0)
        self.profit_factor_label = QLabel("0")
        results_layout.addWidget(self.profit_factor_label, 6, 1)
        
        results_group.setLayout(results_layout)
        right_layout.addWidget(results_group)
        
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(8)
        self.trades_table.setHorizontalHeaderLabels([
            "Fecha", "Patrón", "Dirección", "Entrada", 
            "Salida", "Tamaño", "P/L", "Balance"
        ])
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.trades_table)
        
        main_container.addWidget(left_panel)
        main_container.addWidget(right_panel)
        main_container.setSizes([300, 700])
        
        layout.addWidget(main_container)        
        self.backtest_tab.setLayout(layout)
        self.backtest_results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.backtest_results_table)
        self.backtest_tab.setLayout(layout)
    def start_backtest(self):
        logger.info("Iniciando backtesting...")
        self.run_backtest_button.setEnabled(False)
        self.statusBar().showMessage("Ejecutando backtest...")

        self.backtest_thread = WorkerThread(self.run_backtest_async)
        self.backtest_thread.finished_signal.connect(self.on_backtest_finished)
        self.backtest_thread.start()

    async def run_backtest_async(self):
        backtester = None
        try:
            from core.backtester import Backtester
            
            # Guardar la configuración actual
            self.save_settings(False)
            
            # Actualizar configuración de backtest
            if 'backtest' not in self.config:
                self.config['backtest'] = {}
            
            self.config['backtest'].update({
                'initial_capital': self.initial_capital_spinbox.value(),
                'risk_per_trade': self.risk_per_trade_spinbox.value() / 100,  # Convertir de % a decimal
                'take_profit_pct': self.take_profit_spinbox.value(),
                'stop_loss_pct': self.stop_loss_spinbox.value(),
                'days': 90  # Período de backtest
            })
            
            # Actualizar símbolo y timeframe
            self.config['trading']['symbol'] = self.backtest_symbol_combo.currentText()
            self.config['trading']['timeframe'] = self.backtest_timeframe_combo.currentText()
            
            # Inicializar backtester
            backtester = Backtester(self.config)
            await backtester.initialize()
            
            # Ejecutar backtest
            results = await backtester.run_backtest()
            
            return results
        except Exception as e:
            logger.error(f"Error en el backtesting: {e}")
            # Asegurarse de que se devuelve un objeto que puede ser manejado por la señal
            return {"error": str(e)}
        finally:
            # Cerrar recursos independientemente del resultado
            if backtester:
                # Cerrar data_fetcher
                if hasattr(backtester, 'data_fetcher') and backtester.data_fetcher:
                    try:
                        await backtester.data_fetcher.close()
                        logger.info("Data fetcher del backtester cerrado correctamente")
                    except Exception as e:
                        logger.error(f"Error al cerrar data_fetcher del backtester: {e}")
                
                # Cerrar pattern_db
                if hasattr(backtester, 'pattern_db') and backtester.pattern_db:
                    try:
                        await backtester.pattern_db.close()
                        logger.info("Pattern DB del backtester cerrada correctamente")
                    except Exception as e:
                        logger.error(f"Error al cerrar pattern_db del backtester: {e}")
                
                # Cerrar cualquier sesión aiohttp pendiente
                try:
                    import aiohttp
                    import asyncio
                    
                    # Intentar cerrar sesiones aiohttp pendientes
                    for task in asyncio.all_tasks():
                        if isinstance(getattr(task, '_coro', None), aiohttp.ClientSession.close):
                            await task
                    
                    # Cerrar el exchange de ccxt si existe
                    if hasattr(backtester.data_fetcher, 'async_exchange'):
                        await backtester.data_fetcher.async_exchange.close()
                        logger.info("Exchange async del backtester cerrado correctamente")
                except Exception as e:
                    logger.error(f"Error al cerrar sesiones aiohttp: {e}")

    @pyqtSlot(bool, object)
    def on_backtest_finished(self, success, message):
        self.run_backtest_button.setEnabled(True)
        if success:
            logger.info("Backtesting completado con éxito")
            results = message if isinstance(message, dict) else {}
            self.show_backtest_results(results)
            self.statusBar().showMessage("Backtest completado")
        else:
            logger.error(f"Error en el backtesting: {message}")
            self.statusBar().showMessage(f"Error en backtesting: {message}")

    def show_backtest_results(self, results: dict):
        self.backtest_results_table.setRowCount(0)
        row = 0
        metrics = ["initial_capital","final_balance","total_trades","winning_trades","losing_trades",
                   "win_rate","profit_factor","total_return"]
        for key in metrics:
            val = results.get(key, None)
            self.backtest_results_table.insertRow(row)
            self.backtest_results_table.setItem(row,0, QTableWidgetItem(key))
            self.backtest_results_table.setItem(row,1, QTableWidgetItem(str(val)))
            row += 1

    def update_multi_trading_status(self, message):
        """Actualiza el estado del trading múltiple en la interfaz"""
        try:
            # Obtener símbolo del mensaje
            symbol = message.get('symbol', '')
            
            # Actualizar tabla de operaciones activas
            if 'active_trades' in message:
                for trade in message.get('active_trades', []):
                    # Añadir símbolo al trade si no lo tiene
                    if 'symbol' not in trade:
                        trade['symbol'] = symbol
                    
                    # Buscar si ya existe esta operación en la tabla
                    found = False
                    for row in range(self.active_trades_table.rowCount()):
                        if self.active_trades_table.item(row, 0).text() == trade.get('id', ''):
                            found = True
                            # Actualizar datos
                            self.active_trades_table.item(row, 5).setText(f"${trade.get('current_pl', 0):.2f}")
                            break
                    
                    # Si no existe, añadirla
                    if not found:
                        row = self.active_trades_table.rowCount()
                        self.active_trades_table.insertRow(row)
                        
                        self.active_trades_table.setItem(row, 0, QTableWidgetItem(str(trade.get('id', ''))))
                        self.active_trades_table.setItem(row, 1, QTableWidgetItem(trade.get('symbol', '')))
                        self.active_trades_table.setItem(row, 2, QTableWidgetItem(trade.get('direction', '')))
                        self.active_trades_table.setItem(row, 3, QTableWidgetItem(f"${trade.get('entry_price', 0):.2f}"))
                        self.active_trades_table.setItem(row, 4, QTableWidgetItem(f"{trade.get('size', 0):.4f}"))
                        self.active_trades_table.setItem(row, 5, QTableWidgetItem(f"${trade.get('current_pl', 0):.2f}"))
            
            # Actualizar historial de operaciones
            if 'trade_history' in message:
                for trade in message.get('trade_history', []):
                    # Añadir símbolo al trade si no lo tiene
                    if 'symbol' not in trade:
                        trade['symbol'] = symbol
                    
                    # Buscar si ya existe esta operación en la tabla
                    found = False
                    for row in range(self.trade_history_table.rowCount()):
                        if self.trade_history_table.item(row, 0).text() == trade.get('id', ''):
                            found = True
                            break
                    
                    # Si no existe, añadirla
                    if not found:
                        row = self.trade_history_table.rowCount()
                        self.trade_history_table.insertRow(row)
                        
                        self.trade_history_table.setItem(row, 0, QTableWidgetItem(trade.get('exit_time', '')))
                        self.trade_history_table.setItem(row, 1, QTableWidgetItem(trade.get('symbol', '')))
                        self.trade_history_table.setItem(row, 2, QTableWidgetItem(trade.get('direction', '')))
                        self.trade_history_table.setItem(row, 3, QTableWidgetItem(f"${trade.get('entry_price', 0):.2f}"))
                        self.trade_history_table.setItem(row, 4, QTableWidgetItem(f"${trade.get('exit_price', 0):.2f}"))
                        self.trade_history_table.setItem(row, 5, QTableWidgetItem(f"{trade.get('size', 0):.4f}"))
                        self.trade_history_table.setItem(row, 6, QTableWidgetItem(f"${trade.get('pl', 0):.2f}"))
            
        except Exception as e:
            logger.error(f"Error al actualizar estado del trading múltiple: {e}")

    def setup_live_trading_tab(self):

        # Añadir sección para trading múltiple
        multi_trading_group = QGroupBox("Trading Múltiple")
        multi_layout = QVBoxLayout()
        
        # Lista de símbolos seleccionados
        self.multi_symbols_list = QListWidget()
        multi_layout.addWidget(QLabel("Símbolos seleccionados:"))
        multi_layout.addWidget(self.multi_symbols_list)
        
        # Botones para añadir/quitar símbolos
        buttons_layout = QHBoxLayout()
        self.add_symbol_btn = QPushButton("Añadir Símbolo")
        self.add_symbol_btn.clicked.connect(self.add_symbol_to_list)
        buttons_layout.addWidget(self.add_symbol_btn)
        
        self.remove_symbol_btn = QPushButton("Quitar Símbolo")
        self.remove_symbol_btn.clicked.connect(self.remove_symbol_from_list)
        buttons_layout.addWidget(self.remove_symbol_btn)
        
        multi_layout.addLayout(buttons_layout)

        layout = QVBoxLayout()
        title_label = QLabel("Trading en Vivo")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        main_container = QSplitter(Qt.Horizontal)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        config_group = QGroupBox("Configuración de Trading")
        config_layout = QGridLayout()
        
        config_layout.addWidget(QLabel("Símbolo:"), 0, 0)
        self.trading_symbol_combo = QComboBox()
        self.trading_symbol_combo.addItems(symbols)
        config_layout.addWidget(self.trading_symbol_combo, 0, 1)
        
        config_layout.addWidget(QLabel("Timeframe:"), 1, 0)
        self.trading_timeframe_combo = QComboBox()
        self.trading_timeframe_combo.addItems(["1m", "5m", "15m", "1h", "4h", "1d"])
        config_layout.addWidget(self.trading_timeframe_combo, 1, 1)
        
        config_layout.addWidget(QLabel("Modo:"), 2, 0)
        self.trading_mode_combo = QComboBox()
        self.trading_mode_combo.addItems(["Paper", "Live"])
        config_layout.addWidget(self.trading_mode_combo, 2, 1)
        
        config_layout.addWidget(QLabel("Tamaño de posición:"), 3, 0)
        self.position_size_spinbox = QDoubleSpinBox()
        self.position_size_spinbox.setRange(0.001, 100)
        self.position_size_spinbox.setValue(1)
        config_layout.addWidget(self.position_size_spinbox, 3, 1)
        
        config_layout.addWidget(QLabel("Apalancamiento:"), 4, 0)
        self.leverage_spinbox = QSpinBox()
        self.leverage_spinbox.setRange(1, 100)
        self.leverage_spinbox.setValue(1)
        config_layout.addWidget(self.leverage_spinbox, 4, 1)
        
        config_group.setLayout(config_layout)
        left_layout.addWidget(config_group)
        left_layout.addWidget(multi_trading_group)
        
        buttons_layout = QHBoxLayout()
        # Botón para iniciar trading múltiple
        self.start_multi_trading_btn = QPushButton("Iniciar Trading Múltiple")
        self.start_multi_trading_btn.clicked.connect(self.start_multi_trading)
        multi_layout.addWidget(self.start_multi_trading_btn)
        
        multi_trading_group.setLayout(multi_layout)
        
        self.stop_bot_btn = QPushButton("Detener Bot")
        self.stop_bot_btn.setEnabled(False)
        buttons_layout.addWidget(self.stop_bot_btn)
        
        left_layout.addLayout(buttons_layout)
        
        left_layout.addStretch()
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        status_group = QGroupBox("Estado del Bot")
        status_layout = QGridLayout()
        
        status_layout.addWidget(QLabel("Estado:"), 0, 0)
        self.bot_status_label = QLabel("Detenido")
        status_layout.addWidget(self.bot_status_label, 0, 1)
        
        status_layout.addWidget(QLabel("Tiempo en ejecución:"), 1, 0)
        self.runtime_label = QLabel("00:00:00")
        status_layout.addWidget(self.runtime_label, 1, 1)
        
        status_layout.addWidget(QLabel("Operaciones abiertas:"), 2, 0)
        self.open_trades_label = QLabel("0")
        status_layout.addWidget(self.open_trades_label, 2, 1)
        
        status_layout.addWidget(QLabel("Balance:"), 3, 0)
        self.live_balance_label = QLabel("$0.00")
        status_layout.addWidget(self.live_balance_label, 3, 1)
        
        status_layout.addWidget(QLabel("P/L total:"), 4, 0)
        self.total_pl_label = QLabel("$0.00")
        status_layout.addWidget(self.total_pl_label, 4, 1)
        
        status_group.setLayout(status_layout)
        right_layout.addWidget(status_group)
        
        active_trades_group = QGroupBox("Operaciones Activas")
        active_trades_layout = QVBoxLayout()
        
        self.active_trades_table = QTableWidget()
        self.active_trades_table.setColumnCount(6)
        self.active_trades_table.setHorizontalHeaderLabels(["ID", "Símbolo", "Tipo", "Entrada", "Tamaño", "P/L Actual"])
        self.active_trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        active_trades_layout.addWidget(self.active_trades_table)
        
        active_trades_group.setLayout(active_trades_layout)
        right_layout.addWidget(active_trades_group)
        
        history_group = QGroupBox("Historial de Operaciones")
        history_layout = QVBoxLayout()
        
        self.trade_history_table = QTableWidget()
        self.trade_history_table.setColumnCount(7)
        self.trade_history_table.setHorizontalHeaderLabels(["Fecha", "Símbolo", "Tipo", "Entrada", "Salida", "Tamaño", "P/L"])
        self.trade_history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        history_layout.addWidget(self.trade_history_table)
        
        history_group.setLayout(history_layout)
        right_layout.addWidget(history_group)
        
        main_container.addWidget(left_panel)
        main_container.addWidget(right_panel)
        main_container.setSizes([300, 700])
        
        layout.addWidget(main_container)
        self.live_trading_tab.setLayout(layout)

    def add_symbol_to_list(self):
        symbol = self.trading_symbol_combo.currentText()
        if symbol and self.multi_symbols_list.findItems(symbol, Qt.MatchExactly) == []:
            self.multi_symbols_list.addItem(symbol)
            
    def remove_symbol_from_list(self):
        selected_items = self.multi_symbols_list.selectedItems()
        for item in selected_items:
            self.multi_symbols_list.takeItem(self.multi_symbols_list.row(item))
            
    def start_multi_trading(self):
        try:
            # Obtener símbolos seleccionados
            symbols = []
            for i in range(self.multi_symbols_list.count()):
                symbols.append(self.multi_symbols_list.item(i).text())
                
            if not symbols:
                QMessageBox.warning(self, "Advertencia", "No hay símbolos seleccionados")
                return
                
            # Guardar configuración
            self.save_settings(False)
            
            # Actualizar configuración para trading múltiple
            if 'multi_trading' not in self.config:
                self.config['multi_trading'] = {}
                
            self.config['multi_trading']['symbols'] = symbols
            self.config['multi_trading']['timeframe'] = self.trading_timeframe_combo.currentText()
            self.config['multi_trading']['mode'] = self.trading_mode_combo.currentText().lower()
            
            # Iniciar trading múltiple
            logger.info(f"Iniciando trading múltiple para {len(symbols)} símbolos")
            self.statusBar().showMessage(f"Iniciando trading múltiple para {len(symbols)} símbolos")
            
            # Deshabilitar botones (solo los que existen)
            self.start_multi_trading_btn.setEnabled(False)
            self.start_trading_btn.setEnabled(False)
            
            # Crear bot múltiple
            self.multi_trading_bot = MultiSymbolTradingBot(self.config)
            
            # Conectar señales
            self.multi_trading_bot.log_signal.connect(self.update_log)
            self.multi_trading_bot.update_signal.connect(self.update_multi_trading_status)
            self.multi_trading_bot.finished_signal.connect(self.on_multi_trading_finished)
            
            # Crear e iniciar hilo
            self.multi_trading_thread = QThread()
            self.multi_trading_bot.moveToThread(self.multi_trading_thread)
            self.multi_trading_thread.started.connect(self.multi_trading_bot.run)
            
            # Habilitar botón de detener
            self.stop_bot_btn.setEnabled(True)
            self.stop_bot_btn.clicked.connect(self.stop_multi_trading)
            
            # Iniciar hilo
            self.multi_trading_thread.start()
            
        except Exception as e:
            logger.error(f"Error al iniciar trading múltiple: {e}")
            self.statusBar().showMessage(f"Error: {str(e)}")
            self.start_multi_trading_btn.setEnabled(True)
            self.start_trading_btn.setEnabled(True)

    def on_multi_trading_finished(self, success, message):
        """Callback cuando el trading múltiple ha finalizado"""
        self.start_multi_trading_btn.setEnabled(True)
        self.start_trading_btn.setEnabled(True)
        self.stop_bot_btn.setEnabled(False)
        
        if success:
            logger.info("Trading múltiple finalizado con éxito")
            self.statusBar().showMessage("Trading múltiple finalizado")
        else:
            logger.error(f"Error en el trading múltiple: {message}")
            self.statusBar().showMessage(f"Error: {message}")

    def stop_multi_trading(self):
        """Detiene el trading múltiple"""
        try:
            if hasattr(self, 'multi_trading_bot') and self.multi_trading_bot:
                self.multi_trading_bot.stop()  # Llamar al método stop() en lugar de self.stop_bot_btn()
                logger.info("Señal de detención enviada a todos los bots")
                self.statusBar().showMessage("Deteniendo todos los bots...")
                
                # Desactivar botón de detener
                self.stop_bot_btn.setEnabled(False)
                
                # Programar verificación
                QTimer.singleShot(5000, self.check_multi_bots_stopped)
        except Exception as e:
            logger.error(f"Error al detener trading múltiple: {e}")
            self.statusBar().showMessage(f"Error: {str(e)}")
            self.start_multi_trading_btn.setEnabled(True)
            self.start_trading_btn.setEnabled(True)
            self.stop_bot_btn.setEnabled(False)

    def start_live_trading(self):
        try:
            self.start_multi_trading_btn.setEnabled(False)
            self.start_trading_btn.setEnabled(False)
            
            # Guardar la configuración actual
            self.save_settings(False)
            
            # Actualizar configuración de trading
            self.config['trading']['symbol'] = self.trading_symbol_combo.currentText()
            self.config['trading']['timeframe'] = self.trading_timeframe_combo.currentText()
            self.config['trading']['mode'] = self.trading_mode_combo.currentText().lower()
            self.config['trading']['position_size'] = self.position_size_spinbox.value()
            self.config['trading']['leverage'] = self.leverage_spinbox.value()
            
            logger.info("Iniciando trading en vivo...")
            self.statusBar().showMessage("Iniciando trading en vivo...")
            
            # Crear el bot en el hilo principal
            self.trading_bot = MultiSymbolTradingBot(self.config)
            
            # Conectar señales
            self.trading_bot.log_signal.connect(self.update_log)
            self.trading_bot.update_signal.connect(self.update_live_trading_status)
            self.trading_bot.finished_signal.connect(self.on_live_trading_finished)
            
            # Crear e iniciar el hilo de trading
            self.trading_thread = QThread()
            self.trading_bot.moveToThread(self.trading_thread)
            
            # Conectar la señal started del hilo al método run del bot
            self.trading_thread.started.connect(self.trading_bot.run)
            
            # Habilitar el botón de detener
            self.stop_bot_btn.setEnabled(True)
            self.stop_bot_btn.clicked.connect(self.stop_live_trading)
            
            # Iniciar el hilo
            self.trading_thread.start()
            
        except Exception as e:
            logger.error(f"Error al iniciar trading en vivo: {e}")
            self.statusBar().showMessage(f"Error: {str(e)}")
            self.start_multi_trading_btn.setEnabled(True)
            self.start_trading_btn.setEnabled(True)

    def _create_and_run_bot(self):
        """Crea y ejecuta el bot en el hilo actual"""
        try:
            # Crear el bot en el hilo actual
            self.trading_bot = MultiSymbolTradingBot(self.config)
            
            # Conectar señales
            self.trading_bot.log_signal.connect(self.update_log)
            self.trading_bot.update_signal.connect(self.update_live_trading_status)
            self.trading_bot.finished_signal.connect(self.on_live_trading_finished)
            
            # Ejecutar el bot (esto no debería bloquear el hilo)
            self.trading_bot.run()
        except Exception as e:
            # Usar QMetaObject.invokeMethod para actualizar la UI desde otro hilo
            from PyQt5.QtCore import QMetaObject, Qt # type: ignore
            
            def update_ui_after_error():
                logger.error(f"Error al crear y ejecutar el bot: {e}")
                self.statusBar().showMessage(f"Error: {str(e)}")
                self.start_multi_trading_btn.setEnabled(True)
                self.start_trading_btn.setEnabled(True)
                self.stop_bot_btn.setEnabled(False)
            
            QMetaObject.invokeMethod(self, "update_ui_after_error", Qt.QueuedConnection)


    async def _initialize_bot_async(self):
        """Inicializa el bot de trading de forma asíncrona"""
        try:
            # Crear el bot
            self.trading_bot = MultiSymbolTradingBot(self.config)
            
            # Inicializar el bot
            success = await self.trading_bot.initialize()
            if not success:
                raise Exception("No se pudo inicializar el bot de trading")
            
            return True
        except Exception as e:
            logger.error(f"Error al inicializar el bot: {e}")
            return False

    def _on_bot_initialized(self, success, result):
        """Callback cuando el bot ha sido inicializado"""
        if success and result:
            # Conectar señales
            self.trading_bot.log_signal.connect(self.update_log)
            self.trading_bot.update_signal.connect(self.update_live_trading_status)
            self.trading_bot.finished_signal.connect(self.on_live_trading_finished)
            
            # Configurar y iniciar el thread
            self.trading_thread = QThread()
            self.trading_bot.moveToThread(self.trading_thread)
            self.trading_thread.started.connect(self.trading_bot.run)
            self.trading_thread.start()
            
            # Habilitar el botón de detener
            self.stop_bot_btn.setEnabled(True)
            self.stop_bot_btn.clicked.connect(self.stop_live_trading)
            
            self.statusBar().showMessage("Trading en vivo iniciado")
        else:
            logger.error("No se pudo inicializar el bot de trading")
            self.statusBar().showMessage("Error al inicializar el bot de trading")
            self.start_multi_trading_btn.setEnabled(True)
            self.start_trading_btn.setEnabled(True)

    def update_live_trading_status(self, message):
        try:
            status = message.get('status', 'Detenido')
            runtime = message.get('runtime', '00:00:00')
            open_trades = message.get('open_trades', 0)
            balance = message.get('balance', 0.0)
            total_pl = message.get('total_pl', 0.0)
            
            self.bot_status_label.setText(status)
            self.runtime_label.setText(runtime)
            self.open_trades_label.setText(str(open_trades))
            self.live_balance_label.setText(f"${balance:.2f}")
            self.total_pl_label.setText(f"${total_pl:.2f}")
            
            active_trades = message.get('active_trades', [])
            self.update_active_trades_table(active_trades)
            
            trade_history = message.get('trade_history', [])
            self.update_trade_history_table(trade_history)
            
        except Exception as e:
            logger.error(f"Error al actualizar estado del trading en vivo: {e}")
    def update_active_trades_table(self, trades):
        try:
            self.active_trades_table.setRowCount(0)
            
            for trade in trades:
                row = self.active_trades_table.rowCount()
                self.active_trades_table.insertRow(row)
                logger.info(f"Actualizando trade {trade.get('id', '')}: P/L = ${trade.get('current_pl', 0):.2f}")
                self.active_trades_table.setItem(row, 0, QTableWidgetItem(str(trade.get('id', ''))))
                self.active_trades_table.setItem(row, 1, QTableWidgetItem(trade.get('symbol', '')))
                self.active_trades_table.setItem(row, 2, QTableWidgetItem(trade.get('type', '')))
                self.active_trades_table.setItem(row, 3, QTableWidgetItem(f"${trade.get('entry_price', 0):.2f}"))
                self.active_trades_table.setItem(row, 4, QTableWidgetItem(f"{trade.get('size', 0):.4f}"))
                self.active_trades_table.setItem(row, 5, QTableWidgetItem(f"${trade.get('current_pl', 0):.2f}"))
                
        except Exception as e:
            logger.error(f"Error al actualizar tabla de operaciones activas: {e}")
    def update_trade_history_table(self, trades):
        try:
            self.trade_history_table.setRowCount(0)
            
            for trade in trades:
                row = self.trade_history_table.rowCount()
                self.trade_history_table.insertRow(row)
                
                self.trade_history_table.setItem(row, 0, QTableWidgetItem(trade.get('date', '')))
                self.trade_history_table.setItem(row, 1, QTableWidgetItem(trade.get('symbol', '')))
                self.trade_history_table.setItem(row, 2, QTableWidgetItem(trade.get('type', '')))
                self.trade_history_table.setItem(row, 3, QTableWidgetItem(f"${trade.get('entry_price', 0):.2f}"))
                self.trade_history_table.setItem(row, 4, QTableWidgetItem(f"${trade.get('exit_price', 0):.2f}"))
                self.trade_history_table.setItem(row, 5, QTableWidgetItem(f"{trade.get('size', 0):.4f}"))
                self.trade_history_table.setItem(row, 6, QTableWidgetItem(f"${trade.get('pl', 0):.2f}"))
                
        except Exception as e:
            logger.error(f"Error al actualizar tabla de historial de operaciones: {e}")
    def on_live_trading_finished(self, success, message):
        try:
            self.start_multi_trading_btn.setEnabled(True)
            self.start_trading_btn.setEnabled(True)
            self.stop_bot_btn.setEnabled(False)
            
            if success:
                logger.info("Trading en vivo finalizado con éxito")
                self.statusBar().showMessage("Trading en vivo finalizado")
            else:
                logger.error(f"Error en el trading en vivo: {message}")
                self.statusBar().showMessage(f"Error: {message}")
                
        except Exception as e:
            logger.error(f"Error al finalizar trading en vivo: {e}")
    def stop_live_trading(self):
        try:
            if hasattr(self, 'trading_bot') and self.trading_bot:
                self.trading_bot.stop()
                logger.info("Señal de detención enviada al bot")
                self.statusBar().showMessage("Deteniendo bot...")
                
                # Desactivar el botón de detener hasta que el bot confirme que ha terminado
                self.stop_bot_btn.setEnabled(False)
                
                # Programar una verificación después de un tiempo para asegurarse de que el bot se detuvo
                QTimer.singleShot(5000, self.check_bot_stopped)
        except Exception as e:
            logger.error(f"Error al detener trading en vivo: {e}")
            self.statusBar().showMessage(f"Error: {str(e)}")
            # En caso de error, habilitar los botones de inicio y deshabilitar el de detener
            self.start_multi_trading_btn.setEnabled(True)
            self.start_trading_btn.setEnabled(True)
            self.stop_bot_btn.setEnabled(False)

    def check_bot_stopped(self):
        """Verifica si el bot se detuvo correctamente"""
        if hasattr(self, 'trading_bot') and self.trading_bot and self.trading_bot.is_running:
            # Si el bot sigue ejecutándose, programar otra verificación
            logger.warning("El bot sigue ejecutándose, esperando...")
            QTimer.singleShot(2000, self.check_bot_stopped)
        else:
            # El bot se detuvo, actualizar la interfaz
            logger.info("Bot detenido correctamente")
            self.statusBar().showMessage("Bot detenido")
            self.start_multi_trading_btn.setEnabled(True)
            self.start_trading_btn.setEnabled(True)
            self.stop_bot_btn.setEnabled(False)
            
            # Terminar el hilo si aún está en ejecución
            if hasattr(self, 'trading_thread') and self.trading_thread.isRunning():
                self.trading_thread.quit()
                if not self.trading_thread.wait(3000):  # Esperar hasta 3 segundos
                    self.trading_thread.terminate()

    def setup_settings_tab(self):
        layout = QVBoxLayout()
        title_label = QLabel("Configuración del Sistema")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        main_container = QSplitter(Qt.Horizontal)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        api_group = QGroupBox("Configuración de API")
        api_layout = QGridLayout()
        
        api_layout.addWidget(QLabel("Exchange:"), 0, 0)
        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(["binance", "kraken", "coinbase", "kucoin", "bybit"])
        api_layout.addWidget(self.exchange_combo, 0, 1)
        
        api_layout.addWidget(QLabel("API Key:"), 1, 0)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        api_layout.addWidget(self.api_key_input, 1, 1)
        
        api_layout.addWidget(QLabel("API Secret:"), 2, 0)
        self.api_secret_input = QLineEdit()
        self.api_secret_input.setEchoMode(QLineEdit.Password)
        api_layout.addWidget(self.api_secret_input, 2, 1)
        
        api_layout.addWidget(QLabel("Testnet:"), 3, 0)
        self.testnet_checkbox = QCheckBox()
        api_layout.addWidget(self.testnet_checkbox, 3, 1)
        
        api_group.setLayout(api_layout)
        left_layout.addWidget(api_group)
        
        db_group = QGroupBox("Configuración de Base de Datos")
        db_layout = QGridLayout()
        
        db_layout.addWidget(QLabel("Ruta de la base de datos:"), 0, 0)
        self.pattern_db_path_input = QLineEdit()
        db_layout.addWidget(self.pattern_db_path_input, 0, 1)
        
        self.browse_db_btn = QPushButton("Examinar...")
        self.browse_db_btn.clicked.connect(self.browse_db_path)
        db_layout.addWidget(self.browse_db_btn, 0, 2)
        
        db_group.setLayout(db_layout)
        left_layout.addWidget(db_group)
        
        viz_group = QGroupBox("Configuración de Visualización")
        viz_layout = QGridLayout()
        
        viz_layout.addWidget(QLabel("Habilitar gráficos:"), 0, 0)
        self.enable_charts_checkbox = QCheckBox()
        self.enable_charts_checkbox.setChecked(True)
        viz_layout.addWidget(self.enable_charts_checkbox, 0, 1)
        
        viz_layout.addWidget(QLabel("Guardar gráficos:"), 1, 0)
        self.save_charts_checkbox = QCheckBox()
        self.save_charts_checkbox.setChecked(True)
        viz_layout.addWidget(self.save_charts_checkbox, 1, 1)
        
        viz_layout.addWidget(QLabel("Directorio de gráficos:"), 2, 0)
        self.charts_dir_input = QLineEdit()
        viz_layout.addWidget(self.charts_dir_input, 2, 1)
        
        self.browse_charts_btn = QPushButton("Examinar...")
        self.browse_charts_btn.clicked.connect(self.browse_charts_dir)
        viz_layout.addWidget(self.browse_charts_btn, 2, 2)
        
        viz_group.setLayout(viz_layout)
        left_layout.addWidget(viz_group)
        
        left_layout.addStretch()
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        rate_limit_group = QGroupBox("Configuración de Límites de Tasa")
        rate_limit_layout = QGridLayout()
        
        rate_limit_layout.addWidget(QLabel("Solicitudes por minuto:"), 0, 0)
        self.requests_per_minute_spinbox = QSpinBox()
        self.requests_per_minute_spinbox.setRange(1, 1000)
        self.requests_per_minute_spinbox.setValue(60)
        rate_limit_layout.addWidget(self.requests_per_minute_spinbox, 0, 1)
        
        rate_limit_layout.addWidget(QLabel("Retraso entre solicitudes (s):"), 1, 0)
        self.retry_delay_spinbox = QDoubleSpinBox()
        self.retry_delay_spinbox.setRange(0.1, 60)
        self.retry_delay_spinbox.setValue(2.0)
        rate_limit_layout.addWidget(self.retry_delay_spinbox, 1, 1)
        
        rate_limit_layout.addWidget(QLabel("Máximo de reintentos:"), 2, 0)
        self.max_retries_spinbox = QSpinBox()
        self.max_retries_spinbox.setRange(1, 20)
        self.max_retries_spinbox.setValue(5)
        rate_limit_layout.addWidget(self.max_retries_spinbox, 2, 1)
        
        rate_limit_group.setLayout(rate_limit_layout)
        right_layout.addWidget(rate_limit_group)
        
        notifications_group = QGroupBox("Configuración de Notificaciones")
        notifications_layout = QGridLayout()
        
        notifications_layout.addWidget(QLabel("Habilitar notificaciones:"), 0, 0)
        self.enable_notifications_checkbox = QCheckBox()
        notifications_layout.addWidget(self.enable_notifications_checkbox, 0, 1)
        
        notifications_layout.addWidget(QLabel("Email:"), 1, 0)
        self.email_input = QLineEdit()
        notifications_layout.addWidget(self.email_input, 1, 1)
        
        notifications_layout.addWidget(QLabel("Telegram Bot Token:"), 2, 0)
        self.telegram_token_input = QLineEdit()
        notifications_layout.addWidget(self.telegram_token_input, 2, 1)
        
        notifications_layout.addWidget(QLabel("Telegram Chat ID:"), 3, 0)
        self.telegram_chat_id_input = QLineEdit()
        notifications_layout.addWidget(self.telegram_chat_id_input, 3, 1)
        
        notifications_group.setLayout(notifications_layout)
        right_layout.addWidget(notifications_group)
        
        buttons_layout = QHBoxLayout()
        
        self.save_settings_btn = QPushButton("Guardar Configuración")
        self.save_settings_btn.clicked.connect(self.save_settings)
        buttons_layout.addWidget(self.save_settings_btn)
        
        self.reset_settings_btn = QPushButton("Restablecer Valores Predeterminados")
        self.reset_settings_btn.clicked.connect(self.reset_settings)
        buttons_layout.addWidget(self.reset_settings_btn)
        
        right_layout.addLayout(buttons_layout)
        
        right_layout.addStretch()
        
        main_container.addWidget(left_panel)
        main_container.addWidget(right_panel)
        main_container.setSizes([500, 500])
        
        layout.addWidget(main_container)
        self.settings_tab.setLayout(layout)

    def setup_logging(self):
        handler = LogHandler(self.log_signal)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        self.log_signal.connect(self.update_log)
    def update_log(self, message):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    def load_config(self):
        try:
            config_path = 'config/settings.json'
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    self.config = json.load(f)
                logger.info("Configuración cargada correctamente")
                self.update_ui_from_config()
            else:
                logger.warning(f"Archivo de configuración no encontrado: {config_path}")
                self.config = {}
        except Exception as e:
            logger.error(f"Error al cargar la configuración: {e}")
            self.config = {}
    def update_ui_from_config(self):
        try:
            exchange_config = self.config.get('exchange', {})
            exchange_name = exchange_config.get('name', 'kraken')
            index = self.exchange_combo.findText(exchange_name)
            if index >= 0:
                self.exchange_combo.setCurrentIndex(index)
            
            self.api_key_input.setText(exchange_config.get('api_key', ''))
            self.api_secret_input.setText(exchange_config.get('api_secret', ''))
            self.testnet_checkbox.setChecked(exchange_config.get('testnet', False))
            
            trading_config = self.config.get('trading', {})
            symbol = trading_config.get('symbol', list(markets.keys())[0])
            timeframe = trading_config.get('timeframe', '1h')
            
            for combo in [self.trading_symbol_combo, self.backtest_symbol_combo, self.analysis_symbol_combo]:
                combo.clear()
                combo.addItems(symbols)
                index = combo.findText(symbol)
                if index >= 0:
                    combo.setCurrentIndex(index)
            
            for combo in [self.trading_timeframe_combo, self.backtest_timeframe_combo, self.analysis_timeframe_combo, self.timeframes_combo]:
                index = combo.findText(timeframe)
                if index >= 0:
                    combo.setCurrentIndex(index)
            
            # Update symbols_combo instead of symbols_input
            self.symbols_combo.setCurrentText(symbol)
            
            # Clear and update selected symbols
            self.selected_symbols = [symbol]
            self.update_selected_symbols_widget()
            
            self.days_spinbox.setValue(trading_config.get('historical_days', 30))
            
            backtest_config = self.config.get('backtest', {})
            self.initial_capital_spinbox.setValue(backtest_config.get('initial_capital', 1000.0))
            self.risk_per_trade_spinbox.setValue(backtest_config.get('risk_per_trade', 0.02) * 100)
            self.take_profit_spinbox.setValue(backtest_config.get('take_profit_pct', 2.0))
            self.stop_loss_spinbox.setValue(backtest_config.get('stop_loss_pct', 1.0))
            
            pattern_config = self.config.get('pattern_analysis', {})
            self.lookback_spinbox.setValue(pattern_config.get('lookback_candles', 5))
            self.lookforward_spinbox.setValue(pattern_config.get('lookforward_candles', 10))
            self.min_success_rate_spinbox.setValue(pattern_config.get('min_success_rate', 60.0))
            
            self.position_size_spinbox.setValue(trading_config.get('position_size', 1.0))
            self.leverage_spinbox.setValue(trading_config.get('leverage', 1))
            
            mode = trading_config.get('mode', 'paper')
            index = self.trading_mode_combo.findText(mode.capitalize())
            if index >= 0:
                self.trading_mode_combo.setCurrentIndex(index)
            
            db_config = self.config.get('database', {})
            self.pattern_db_path_input.setText(db_config.get('path', 'data/patterns.db'))
            
            viz_config = self.config.get('visualization', {})
            self.enable_charts_checkbox.setChecked(viz_config.get('enabled', True))
            self.save_charts_checkbox.setChecked(viz_config.get('save_charts', True))
            self.charts_dir_input.setText(viz_config.get('charts_dir', 'charts'))
            
            rate_limit_config = exchange_config.get('rate_limit', {})
            self.requests_per_minute_spinbox.setValue(rate_limit_config.get('requests_per_minute', 60))
            self.retry_delay_spinbox.setValue(rate_limit_config.get('retry_delay', 2.0))
            self.max_retries_spinbox.setValue(rate_limit_config.get('max_retries', 5))
            
            logger.info("Interfaz actualizada con la configuración cargada")
            
        except Exception as e:
            logger.error(f"Error al actualizar la interfaz: {e}")
    def save_settings(self, show_message=True):
        try:
            exchange_name = self.exchange_combo.currentText()
            api_key = self.api_key_input.text()
            api_secret = self.api_secret_input.text()
            testnet = self.testnet_checkbox.isChecked()
            
            self.config = {
                'api': {
                    'exchange': exchange_name,
                    'api_key': api_key,
                    'api_secret': api_secret,
                    'testnet': testnet
                },
                'exchange': {
                    'name': exchange_name,
                    'api_key': api_key,
                    'api_secret': api_secret,
                    'testnet': testnet,
                    'rate_limit': {
                        'requests_per_minute': self.requests_per_minute_spinbox.value(),
                        'retry_delay': self.retry_delay_spinbox.value(),
                        'max_retries': self.max_retries_spinbox.value()
                    }
                },
                'trading': {
                    'symbol': self.trading_symbol_combo.currentText(),
                    'timeframe': self.trading_timeframe_combo.currentText(),
                    'historical_days': self.days_spinbox.value(),
                    'position_size': self.position_size_spinbox.value(),
                    'leverage': self.leverage_spinbox.value(),
                    'mode': self.trading_mode_combo.currentText().lower()
                },
                'data_collection': {
                    'symbols': self.selected_symbols if hasattr(self, 'selected_symbols') and self.selected_symbols else [self.symbols_combo.currentText()],
                    'timeframes': [self.timeframes_combo.currentText()],
                    'days_to_collect': self.days_spinbox.value(),
                    'batch_size': 1000
                },
            }
            
            os.makedirs('config', exist_ok=True)
            with open('config/settings.json', 'w') as f:
                json.dump(self.config, f, indent=4)
            
            logger.info("Configuración guardada correctamente")
            
            if show_message:
                QMessageBox.information(self, "Configuración", "Configuración guardada correctamente")
            
        except Exception as e:
            logger.error(f"Error al guardar la configuración: {e}")
            if show_message:
                QMessageBox.critical(self, "Error", f"Error al guardar la configuración: {e}")
    def reset_settings(self):
        try:
            reply = QMessageBox.question(
                self, 
                "Restablecer Configuración", 
                "¿Estás seguro de que deseas restablecer todos los valores a los predeterminados?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                default_config = {
                    'api': {
                        'exchange': 'kraken',
                        'api_key': '',
                        'api_secret': '',
                        'testnet': False
                    },
                    'trading': {
                        'symbol': list(markets.keys())[0],
                        'timeframe': '1h',
                        'historical_days': 30,
                        'position_size': 1.0,
                        'leverage': 1,
                        'mode': 'paper'
                    },
                    'backtest': {
                        'initial_capital': 1000.0,
                        'risk_per_trade': 0.02,
                        'take_profit_pct': 2.0,
                        'stop_loss_pct': 1.0
                    },
                    'pattern_analysis': {
                        'min_success_rate': 60.0,
                        'lookback_candles': 5,
                        'lookforward_candles': 10,
                        'min_profit_ratio': 1.5,
                        'max_error_rate': 5.0
                    },
                    'database': {
                        'path': 'data/patterns.db'
                    },
                    'exchange': {
                        'name': 'kraken',
                        'api_key': '',
                        'api_secret': '',
                        'testnet': False,
                        'rate_limit': {
                            'requests_per_minute': 60,
                            'retry_delay': 2.0,
                            'max_retries': 5
                        }
                    },
                    'data_collection': {
                        'symbols': list(markets.keys())[0],
                        'timeframes': ['1h', '4h', '1d'],
                        'days_to_collect': 30,
                        'batch_size': 1000
                    },
                    'visualization': {
                        'enabled': True,
                        'save_charts': True,
                        'charts_dir': 'charts'
                    }
                }
                
                self.config = default_config
                self.update_ui_from_config()
                
                logger.info("Configuración restablecida a valores predeterminados")
                QMessageBox.information(self, "Configuración", "Configuración restablecida a valores predeterminados")
                
        except Exception as e:
            logger.error(f"Error al restablecer la configuración: {e}")
            QMessageBox.critical(self, "Error", f"Error al restablecer la configuración: {e}")
    def load_config_dialog(self):
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Cargar Configuración", 
                "config", 
                "Archivos JSON (*.json)"
            )
            
            if file_path:
                with open(file_path, 'r') as f:
                    self.config = json.load(f)
                
                self.update_ui_from_config()
                logger.info(f"Configuración cargada desde {file_path}")
                QMessageBox.information(self, "Configuración", f"Configuración cargada desde {file_path}")
                
        except Exception as e:
            logger.error(f"Error al cargar la configuración: {e}")
            QMessageBox.critical(self, "Error", f"Error al cargar la configuración: {e}")
    def save_config_dialog(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Guardar Configuración", 
                "config/settings.json", 
                "Archivos JSON (*.json)"
            )
            
            if file_path:
                self.save_settings()
                
                with open(file_path, 'w') as f:
                    json.dump(self.config, f, indent=4)
                
                logger.info(f"Configuración guardada en {file_path}")
                QMessageBox.information(self, "Configuración", f"Configuración guardada en {file_path}")
                
        except Exception as e:
            logger.error(f"Error al guardar la configuración: {e}")
            QMessageBox.critical(self, "Error", f"Error al guardar la configuración: {e}")
    def browse_db_path(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Seleccionar Base de Datos", 
                self.pattern_db_path_input.text(), 
                "Archivos SQLite (*.db)"
            )
            
            if file_path:
                self.pattern_db_path_input.setText(file_path)
                
        except Exception as e:
            logger.error(f"Error al seleccionar la ruta de la base de datos: {e}")
    
    def browse_charts_dir(self):
        try:
            dir_path = QFileDialog.getExistingDirectory(
                self, 
                "Seleccionar Directorio de Gráficos", 
                self.charts_dir_input.text()
            )
            
            if dir_path:
                self.charts_dir_input.setText(dir_path)
                
        except Exception as e:
            logger.error(f"Error al seleccionar el directorio de gráficos: {e}")

    def start_data_collection(self):
        try:
            self.start_collection_btn.setEnabled(False)
            self.collect_data_btn.setEnabled(False)
            self.stop_collection_btn.setEnabled(True)
            
            logger.info("Iniciando recopilación de datos...")
            self.statusBar().showMessage("Recopilando datos...")
            
            self.collection_thread = WorkerThread(self.start_data_collection_async)
            self.collection_thread.update_signal.connect(self.update_collection_progress)
            self.collection_thread.finished_signal.connect(self.on_collection_finished)
            
            self.collection_thread.start()
            
        except Exception as e:
            logger.error(f"Error al iniciar la recopilación de datos: {e}")
            self.statusBar().showMessage(f"Error: {str(e)}")
            self.start_collection_btn.setEnabled(True)
            self.collect_data_btn.setEnabled(True)
            self.stop_collection_btn.setEnabled(False)
    def update_collection_progress(self, message):
        self.collection_progress.setValue(int(message))
    def on_collection_finished(self, success, message):
        self.start_collection_btn.setEnabled(True)
        self.collect_data_btn.setEnabled(True)
        self.stop_collection_btn.setEnabled(False)
        
        if success:
            logger.info("Recopilación de datos completada")
            self.statusBar().showMessage("Recopilación completada")
            self.collection_progress.setValue(100)
            self.update_data_table()
            
            # Programar el cierre del data_collector para después de actualizar la UI
            QTimer.singleShot(1000, self.close_data_collector)
        else:
            logger.error(f"Error en la recopilación de datos: {message}")
            self.statusBar().showMessage(f"Error: {message}")
            self.collection_progress.setValue(0)
            
            # Cerrar inmediatamente en caso de error
            self.close_data_collector()
    def close_data_collector(self):
        """Cierra el data_collector de manera asíncrona"""
        if hasattr(self, 'data_collector') and self.data_collector:
            # Crear un worker thread para cerrar el data_collector
            class CloseWorker(QThread):
                finished_signal = pyqtSignal()
                
                def __init__(self, data_collector):
                    super().__init__()
                    self.data_collector = data_collector
                    
                def run(self):
                    try:
                        # En lugar de cerrar directamente, solo marcamos que debe cerrarse
                        # y lo liberamos en el closeEvent
                        self.data_collector._should_close = True
                        logger.info("Data collector marcado para cierre")
                        self.finished_signal.emit()
                    except Exception as e:
                        logger.error(f"Error al marcar data_collector para cierre: {e}")
            
            # Iniciar el worker thread
            self.close_thread = CloseWorker(self.data_collector)
            self.close_thread.finished_signal.connect(lambda: setattr(self, 'data_collector', None))
            self.close_thread.start()
    def update_data_table(self):
        try:
            self.data_table.setRowCount(0)
            data_dir = 'data/historical'
            if os.path.exists(data_dir):
                files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
                
                for file in files:
                    parts = file.replace('.json', '').split('_')
                    if len(parts) >= 2:
                        symbol = parts[0] + '/' + parts[1]
                        timeframe = parts[2] if len(parts) > 2 else ''
                    
                        file_path = os.path.join(data_dir, file)
                        try:
                            with open(file_path, 'r') as f:
                                data = json.load(f)
                                
                                if data:
                                    first_candle = data[0]
                                    last_candle = data[-1]
                                    
                                    from_date = datetime.fromtimestamp(first_candle.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M')
                                    to_date = datetime.fromtimestamp(last_candle.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M')
                                    
                                    row = self.data_table.rowCount()
                                    self.data_table.insertRow(row)
                                    
                                    self.data_table.setItem(row, 0, QTableWidgetItem(symbol))
                                    self.data_table.setItem(row, 1, QTableWidgetItem(timeframe))
                                    self.data_table.setItem(row, 2, QTableWidgetItem(from_date))
                                    self.data_table.setItem(row, 3, QTableWidgetItem(to_date))
                        except Exception as e:
                            logger.error(f"Error al leer archivo {file}: {e}")
                
        except Exception as e:
            logger.error(f"Error al actualizar tabla de datos: {e}")
            
    def closeEvent(self, event):
        """Maneja el evento de cierre de la aplicación para limpiar recursos correctamente"""
        try:
            # Cerrar hilos activos
            for thread_name in ['collection_thread', 'analysis_thread', 'trading_thread', 'close_thread', 'backtest_thread']:
                if hasattr(self, thread_name):
                    thread = getattr(self, thread_name)
                    if thread and thread.isRunning():
                        thread.quit()
                        if not thread.wait(1000):  # Esperar hasta 1 segundo
                            thread.terminate()  # Forzar terminación si no responde
            
            # Crear un nuevo loop para operaciones asíncronas de limpieza
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Función asíncrona para limpiar recursos
            async def cleanup():
                # Lista de objetos a cerrar
                objects_to_check = [
                    ('pattern_analyzer', getattr(self, 'pattern_analyzer', None)),
                    ('data_collector', getattr(self, 'data_collector', None)),
                    ('backtester', getattr(self, 'backtester', None)),
                    ('trading_bot', getattr(self, 'trading_bot', None))
                ]
                
                # Cerrar cada objeto si existe y tiene un método close
                for name, obj in objects_to_check:
                    if obj and hasattr(obj, 'close') and callable(obj.close):
                        try:
                            await obj.close()
                            logger.info(f"{name} cerrado correctamente")
                        except Exception as e:
                            logger.error(f"Error al cerrar {name}: {e}")
                
                # Cerrar la instancia global del exchange
                global exchange
                if exchange is not None:
                    if hasattr(exchange, 'close') and callable(exchange.close):
                        try:
                            await exchange.close()
                            logger.info("Exchange global cerrado correctamente")
                        except Exception as e:
                            logger.error(f"Error al cerrar exchange global: {e}")
                
                # Cerrar sesiones aiohttp pendientes
                try:
                    import aiohttp
                    
                    # Cerrar todas las sesiones de cliente pendientes
                    for task in asyncio.all_tasks():
                        if isinstance(getattr(task, '_coro', None), aiohttp.ClientSession.close):
                            await task
                    
                    # Intentar cerrar sesiones de cliente directamente
                    for obj in gc.get_objects():
                        if isinstance(obj, aiohttp.ClientSession) and not obj.closed:
                            await obj.close()
                            logger.info("Sesión aiohttp cerrada correctamente")
                except Exception as e:
                    logger.error(f"Error al cerrar sesiones aiohttp: {e}")
                
                # Cerrar exchanges de ccxt pendientes
                try:
                    import ccxt.async_support as ccxtasync
                    
                    # Cerrar todos los exchanges asíncronos
                    for obj in gc.get_objects():
                        if isinstance(obj, ccxtasync.Exchange):
                            try:
                                await obj.close()
                                logger.info(f"Exchange ccxt {obj.id} cerrado correctamente")
                            except Exception as ex:
                                logger.error(f"Error al cerrar exchange ccxt {getattr(obj, 'id', 'unknown')}: {ex}")
                except Exception as e:
                    logger.error(f"Error al cerrar exchanges ccxt: {e}")
            
            # Ejecutar la limpieza asíncrona
            loop.run_until_complete(cleanup())
            loop.close()
            
            logger.info("Recursos de la aplicación limpiados correctamente")
            
        except Exception as e:
            logger.error(f"Error durante la limpieza de la aplicación: {e}")
        
        # Aceptar el evento de cierre
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = TradingPatternAnalyzerApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
