#!/usr/bin/env python3
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from datetime import datetime

logger = logging.getLogger('chart_generator')

class ChartGenerator:
    """Clase para generar gráficos de trading"""
    
    def __init__(self, config=None):
        """
        Inicializa el generador de gráficos
        
        Args:
            config: Configuración para el generador de gráficos
        """
        self.config = config or {}
        self.charts_dir = self.config.get('visualization', {}).get('charts_dir', 'charts')
        self.enabled = self.config.get('visualization', {}).get('enabled', True)
        self.save_charts = self.config.get('visualization', {}).get('save_charts', True)
        
        # Crear directorio de gráficos si no existe
        if self.save_charts and not os.path.exists(self.charts_dir):
            os.makedirs(self.charts_dir, exist_ok=True)
    
    async def generate_candlestick_chart(self, data, symbol, timeframe, patterns=None, trades=None, filename=None):
        """
        Genera un gráfico de velas con patrones y operaciones
        
        Args:
            data: Lista de datos de velas (OHLCV)
            symbol: Símbolo del instrumento
            timeframe: Timeframe de los datos
            patterns: Lista de patrones detectados (opcional)
            trades: Lista de operaciones (opcional)
            filename: Nombre del archivo para guardar (opcional)
            
        Returns:
            str: Ruta del archivo guardado o None si no se guardó
        """
        if not self.enabled:
            logger.info("Generación de gráficos deshabilitada")
            return None
        
        try:
            # Convertir datos a DataFrame
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Crear figura y ejes
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
            
            # Configurar título y etiquetas
            fig.suptitle(f'{symbol} - {timeframe}', fontsize=16)
            ax1.set_ylabel('Precio')
            ax2.set_ylabel('Volumen')
            ax2.set_xlabel('Fecha')
            
            # Configurar formato de fecha
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            
            # Dibujar velas
            width = 0.6
            width2 = 0.05
            up = df[df.close >= df.open]
            down = df[df.close < df.open]
            
            # Velas alcistas (verdes)
            ax1.bar(up.index, up.close-up.open, width, bottom=up.open, color='green')
            ax1.bar(up.index, up.high-up.close, width2, bottom=up.close, color='green')
            ax1.bar(up.index, up.low-up.open, width2, bottom=up.open, color='green')
            
            # Velas bajistas (rojas)
            ax1.bar(down.index, down.close-down.open, width, bottom=down.open, color='red')
            ax1.bar(down.index, down.high-down.open, width2, bottom=down.open, color='red')
            ax1.bar(down.index, down.low-down.close, width2, bottom=down.close, color='red')
            
            # Dibujar volumen
            ax2.bar(up.index, up.volume, width, color='green')
            ax2.bar(down.index, down.volume, width, color='red')
            
            # Dibujar patrones si existen
            if patterns:
                for pattern in patterns:
                    start_idx = pattern.get('start_idx')
                    end_idx = pattern.get('end_idx')
                    pattern_type = pattern.get('type', 'Unknown')
                    
                    if start_idx is not None and end_idx is not None and start_idx < len(df) and end_idx < len(df):
                        start_date = df.index[start_idx]
                        end_date = df.index[end_idx]
                        
                        # Dibujar rectángulo para marcar el patrón
                        min_price = df.iloc[start_idx:end_idx+1]['low'].min()
                        max_price = df.iloc[start_idx:end_idx+1]['high'].max()
                        
                        # Añadir un margen
                        margin = (max_price - min_price) * 0.1
                        
                        # Dibujar rectángulo con transparencia
                        ax1.axvspan(start_date, end_date, 
                                   alpha=0.2, 
                                   color='blue')
                        
                        # Añadir etiqueta
                        ax1.text(end_date, max_price + margin, 
                                pattern_type, 
                                fontsize=9, 
                                color='blue')
            
            # Dibujar operaciones si existen
            if trades:
                for trade in trades:
                    entry_time = pd.to_datetime(trade.get('entry_time'), unit='ms')
                    exit_time = pd.to_datetime(trade.get('exit_time'), unit='ms')
                    entry_price = trade.get('entry_price')
                    exit_price = trade.get('exit_price')
                    trade_type = trade.get('type', 'Unknown')
                    
                    # Color según tipo de operación
                    color = 'green' if trade_type.lower() == 'long' else 'red'
                    
                    # Dibujar puntos de entrada y salida
                    ax1.scatter(entry_time, entry_price, color=color, marker='^' if trade_type.lower() == 'long' else 'v', s=100)
                    ax1.scatter(exit_time, exit_price, color=color, marker='o', s=100)
                    
                    # Dibujar línea conectando entrada y salida
                    ax1.plot([entry_time, exit_time], [entry_price, exit_price], color=color, linestyle='--')
                    
                    # Añadir etiqueta con resultado
                    pnl = trade.get('pnl', 0)
                    pnl_text = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
                    ax1.text(exit_time, exit_price, 
                            f"{trade_type} {pnl_text}", 
                            fontsize=9, 
                            color=color)
            
            # Ajustar diseño
            plt.tight_layout()
            
            # Guardar gráfico si está habilitado
            if self.save_charts:
                if not filename:
                    # Generar nombre de archivo basado en símbolo y timeframe
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{symbol.replace('/', '_')}_{timeframe}_{timestamp}.png"
                
                filepath = os.path.join(self.charts_dir, filename)
                plt.savefig(filepath, dpi=300, bbox_inches='tight')
                logger.info(f"Gráfico guardado en {filepath}")
                
                # Cerrar figura para liberar memoria
                plt.close(fig)
                
                return filepath
            else:
                # Mostrar gráfico
                plt.show()
                return None
                
        except Exception as e:
            logger.error(f"Error al generar gráfico: {e}")
            # Cerrar figura si existe
            try:
                plt.close(fig)
            except:
                pass
            return None
    
    async def generate_performance_chart(self, backtest_results, filename=None):
        """
        Genera un gráfico de rendimiento del backtest
        
        Args:
            backtest_results: Resultados del backtest
            filename: Nombre del archivo para guardar (opcional)
            
        Returns:
            str: Ruta del archivo guardado o None si no se guardó
        """
        if not self.enabled:
            logger.info("Generación de gráficos deshabilitada")
            return None
        
        try:
            # Extraer datos de balance y operaciones
            trades = backtest_results.get('trades', [])
            
            if not trades:
                logger.warning("No hay operaciones para generar gráfico de rendimiento")
                return None
            
            # Crear DataFrame con datos de balance
            balance_data = []
            for trade in trades:
                balance_data.append({
                    'date': pd.to_datetime(trade.get('date')),
                    'balance': trade.get('balance', 0)
                })
            
            df_balance = pd.DataFrame(balance_data)
            df_balance.set_index('date', inplace=True)
            
            # Crear figura y ejes
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
            
            # Configurar título y etiquetas
            fig.suptitle('Resultados del Backtest', fontsize=16)
            ax1.set_ylabel('Balance')
            ax2.set_ylabel('P/L por operación')
            ax2.set_xlabel('Fecha')
            
            # Dibujar evolución del balance
            ax1.plot(df_balance.index, df_balance['balance'], color='blue', linewidth=2)
            
            # Dibujar P/L por operación
            pnl_data = []
            for trade in trades:
                pnl_data.append({
                    'date': pd.to_datetime(trade.get('date')),
                    'pnl': trade.get('pnl', 0),
                    'type': trade.get('type', 'Unknown')
                })
            
            df_pnl = pd.DataFrame(pnl_data)
            
            # Separar operaciones ganadoras y perdedoras
            winning_trades = df_pnl[df_pnl['pnl'] > 0]
            losing_trades = df_pnl[df_pnl['pnl'] <= 0]
            
            # Dibujar barras de P/L
            ax2.bar(winning_trades['date'], winning_trades['pnl'], color='green', width=0.8)
            ax2.bar(losing_trades['date'], losing_trades['pnl'], color='red', width=0.8)
            
            # Añadir línea de cero
            ax2.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
            
            # Añadir estadísticas
            initial_balance = backtest_results.get('initial_balance', 0)
            final_balance = backtest_results.get('final_balance', 0)
            total_return = backtest_results.get('total_return', 0)
            win_rate = backtest_results.get('win_rate', 0)
            profit_factor = backtest_results.get('profit_factor', 0)
            
            stats_text = (
                f"Capital inicial: ${initial_balance:.2f}\n"
                f"Capital final: ${final_balance:.2f}\n"
                f"Retorno total: {total_return:.2f}%\n"
                f"Tasa de acierto: {win_rate:.2f}%\n"
                f"Factor de beneficio: {profit_factor:.2f}"
            )
            
            # Añadir texto con estadísticas
            ax1.text(0.02, 0.95, stats_text, 
                    transform=ax1.transAxes, 
                    fontsize=10, 
                    verticalalignment='top', 
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
            
            # Ajustar diseño
            plt.tight_layout()
            
            # Guardar gráfico si está habilitado
            if self.save_charts:
                if not filename:
                    # Generar nombre de archivo
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"backtest_results_{timestamp}.png"
                
                filepath = os.path.join(self.charts_dir, filename)
                plt.savefig(filepath, dpi=300, bbox_inches='tight')
                logger.info(f"Gráfico de rendimiento guardado en {filepath}")
                
                # Cerrar figura para liberar memoria
                plt.close(fig)
                
                return filepath
            else:
                # Mostrar gráfico
                plt.show()
                return None
                
        except Exception as e:
            logger.error(f"Error al generar gráfico de rendimiento: {e}")
            # Cerrar figura si existe
            try:
                plt.close(fig)
            except:
                pass
            return None
    
    async def generate_pattern_chart(self, pattern_data, symbol, timeframe, filename=None):
        """
        Genera un gráfico para visualizar un patrón específico
        
        Args:
            pattern_data: Datos del patrón (incluye datos OHLCV y metadatos del patrón)
            symbol: Símbolo del instrumento
            timeframe: Timeframe de los datos
            filename: Nombre del archivo para guardar (opcional)
            
        Returns:
            str: Ruta del archivo guardado o None si no se guardó
        """
        if not self.enabled:
            logger.info("Generación de gráficos deshabilitada")
            return None
        
        try:
            # Extraer datos y metadatos del patrón
            data = pattern_data.get('data', [])
            pattern_type = pattern_data.get('type', 'Unknown Pattern')
            pattern_start = pattern_data.get('start_idx', 0)
            pattern_end = pattern_data.get('end_idx', len(data) - 1)
            
            # Convertir datos a DataFrame
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Crear figura y ejes
            fig, ax1 = plt.subplots(figsize=(10, 6))
            
            # Configurar título y etiquetas
            fig.suptitle(f'{pattern_type} - {symbol} ({timeframe})', fontsize=16)
            ax1.set_ylabel('Precio')
            ax1.set_xlabel('Fecha')
            
            # Configurar formato de fecha
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            
            # Dibujar velas
            width = 0.6
            width2 = 0.05
            up = df[df.close >= df.open]
            down = df[df.close < df.open]
            
            # Velas alcistas (verdes)
            ax1.bar(up.index, up.close-up.open, width, bottom=up.open, color='green')
            ax1.bar(up.index, up.high-up.close, width2, bottom=up.close, color='green')
            ax1.bar(up.index, up.low-up.open, width2, bottom=up.open, color='green')
            
            # Velas bajistas (rojas)
            ax1.bar(down.index, down.close-down.open, width, bottom=down.open, color='red')
            ax1.bar(down.index, down.high-down.open, width2, bottom=down.open, color='red')
            ax1.bar(down.index, down.low-down.close, width2, bottom=down.close, color='red')
            
            # Resaltar el patrón
            if pattern_start is not None and pattern_end is not None:
                # Obtener fechas de inicio y fin del patrón
                if pattern_start < len(df.index) and pattern_end < len(df.index):
                    start_date = df.index[pattern_start]
                    end_date = df.index[pattern_end]
                    
                    # Calcular rango de precios para el patrón
                    pattern_slice = df.iloc[pattern_start:pattern_end+1]
                    min_price = pattern_slice['low'].min()
                    max_price = pattern_slice['high'].max()
                    
                    # Añadir margen
                    price_range = max_price - min_price
                    margin = price_range * 0.1
                    
                    # Resaltar área del patrón
                    ax1.axvspan(start_date, end_date, alpha=0.2, color='blue')
                    
                    # Añadir líneas de soporte/resistencia si están disponibles
                    support = pattern_data.get('support')
                    resistance = pattern_data.get('resistance')
                    
                    if support:
                        ax1.axhline(y=support, color='green', linestyle='--', linewidth=1.5)
                        ax1.text(end_date, support, 'Soporte', fontsize=9, color='green')
                    
                    if resistance:
                        ax1.axhline(y=resistance, color='red', linestyle='--', linewidth=1.5)
                        ax1.text(end_date, resistance, 'Resistencia', fontsize=9, color='red')
                    
                    # Añadir flechas de dirección esperada
                    direction = pattern_data.get('direction', 'unknown')
                    if direction.lower() == 'bullish':
                        ax1.annotate('', xy=(end_date, max_price + margin*2), 
                                    xytext=(end_date, max_price + margin), 
                                    arrowprops=dict(facecolor='green', shrink=0.05))
                    elif direction.lower() == 'bearish':
                        ax1.annotate('', xy=(end_date, min_price - margin*2), 
                                    xytext=(end_date, min_price - margin), 
                                    arrowprops=dict(facecolor='red', shrink=0.05))
            
            # Añadir información adicional del patrón
            reliability = pattern_data.get('reliability', 0)
            description = pattern_data.get('description', '')
            
            info_text = (
                f"Patrón: {pattern_type}\n"
                f"Fiabilidad: {reliability:.2f}%\n"
                f"Dirección: {pattern_data.get('direction', 'Desconocida')}\n"
                f"{description[:100]}..."
            )
            
            # Añadir texto con información
            ax1.text(0.02, 0.02, info_text, 
                    transform=ax1.transAxes, 
                    fontsize=9, 
                    verticalalignment='bottom', 
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
            
            # Ajustar diseño
            plt.tight_layout()
            
            # Guardar gráfico si está habilitado
            if self.save_charts:
                if not filename:
                    # Generar nombre de archivo
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    pattern_name = pattern_type.replace(' ', '_').lower()
                    filename = f"{pattern_name}_{symbol.replace('/', '_')}_{timeframe}_{timestamp}.png"
                
                filepath = os.path.join(self.charts_dir, filename)
                plt.savefig(filepath, dpi=300, bbox_inches='tight')
                logger.info(f"Gráfico de patrón guardado en {filepath}")
                
                # Cerrar figura para liberar memoria
                plt.close(fig)
                
                return filepath
            else:
                # Mostrar gráfico
                plt.show()
                return None
                
        except Exception as e:
            logger.error(f"Error al generar gráfico de patrón: {e}")
            # Cerrar figura si existe
            try:
                plt.close(fig)
            except:
                pass
            return None

    async def close(self):
        """Cierra recursos utilizados por el generador de gráficos"""
        # Cerrar todas las figuras abiertas
        plt.close('all')

