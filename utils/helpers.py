import os
import json
import platform
import sys
import io
from datetime import datetime
from typing import Dict, List, Any, Optional

def setup_windows_compatibility():
    """Configura la compatibilidad con Windows"""
    if platform.system() == 'Windows':
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        print("✅ Configurado evento compatible con Windows")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        print("✅ Configurada codificación UTF-8 para la consola")

def save_config_to_file(config: Dict, filename: str = "config/settings.json") -> bool:
    """Guarda la configuración en un archivo JSON"""
    try:
        with open(filename, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error guardando configuración: {e}")
        return False

def load_config_from_file(filename: str = "config/settings.json") -> Optional[Dict]:
    """Carga la configuración desde un archivo JSON"""
    try:
        if not os.path.exists(filename):
            return None
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return None

def format_price(price: float, decimals: int = 2) -> str:
    """Formatea un precio con el número de decimales especificado"""
    return f"${price:.{decimals}f}"

def format_percentage(value: float) -> str:
    """Formatea un valor como porcentaje"""
    return f"{value:.2f}%"

def format_timestamp(timestamp: datetime) -> str:
    """Formatea una fecha y hora"""
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")

def print_banner(title: str, width: int = 70):
    """Imprime un banner con un título"""
    print("\n" + "="*width)
    print(f"{title} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*width)

def print_section(title: str, width: int = 70):
    """Imprime un encabezado de sección"""
    print(f"\n{'-'*10} {title} {'-'*10}")

def remove_emojis(text: str) -> str:
    """Reemplaza emojis con texto alternativo para logs"""
    emoji_replacements = {
        "🔍": "[SCAN]",
        "📊": "[STATS]",
        "✅": "[OK]",
        "❌": "[ERROR]",
        "⚠️": "[WARN]",
        "💰": "[MONEY]",
        "📈": "[UP]",
        "📉": "[DOWN]",
        "🚀": "[LAUNCH]",
        "🤖": "[BOT]",
        "🔔": "[ALERT]",
        "⏱️": "[TIME]",
        "💵": "[CASH]",
        "🎯": "[TARGET]",
        "🔄": "[RELOAD]",
        "📡": "[SIGNAL]"
    }
    for emoji, replacement in emoji_replacements.items():
        text = text.replace(emoji, replacement)
    return text
