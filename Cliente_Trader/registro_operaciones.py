# registro_operaciones.py
# ============================================================================
# Módulo de Persistencia de Operaciones — JSON Thread-Safe
# Almacena cada operación ejecutada con fecha/hora para análisis histórico.
# ============================================================================

"""
Módulo de registro y consulta de operaciones históricas.

Persiste cada operación en ``data/historial_operaciones.json`` de forma
thread-safe (escritura atómica con lock). Provee funciones de consulta
con filtrado por rango de fecha y hora, cálculo de KPIs, y agregaciones
temporales para alimentar gráficos del dashboard Analytics.

Uso::

    from registro_operaciones import guardar_operacion, consultar_operaciones

    guardar_operacion({
        "hora": "14:32:05", "activo": "EURUSD-OTC", "tipo": "CALL",
        "inversion": 4, "resultado": "GANADA", "profit": 3.12
    })

    ops = consultar_operaciones("2026-07-01", "2026-07-06", "08:00", "22:00")
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_JSON_PATH = os.path.join(_DATA_DIR, "historial_operaciones.json")

_file_lock = threading.Lock()


# ---------------------------------------------------------------------------
# FUNCIONES DE PERSISTENCIA
# ---------------------------------------------------------------------------
def _asegurar_directorio() -> None:
    """Crea el directorio data/ si no existe."""
    os.makedirs(_DATA_DIR, exist_ok=True)


def _leer_json() -> List[Dict[str, Any]]:
    """Lee el archivo JSON de historial. Retorna lista vacía si no existe."""
    if not os.path.exists(_JSON_PATH):
        return []
    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _escribir_json(data: List[Dict[str, Any]]) -> None:
    """Escribe la lista completa al archivo JSON de forma atómica."""
    _asegurar_directorio()
    tmp_path = _JSON_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, _JSON_PATH)


def guardar_operacion(op: Dict[str, Any], **extras) -> Dict[str, Any]:
    """
    Persiste una operación al archivo JSON con metadata enriquecida.

    Parámetros
    ----------
    op : dict
        Diccionario de operación (como viene del callback del bot).
        Claves esperadas: hora, activo, tipo, inversion, resultado, profit.
    **extras
        Campos adicionales: algoritmo, tipo_cuenta, saldo_post, etc.

    Retorna
    -------
    dict
        El registro completo guardado (con id, fecha, timestamp añadidos).
    """
    ahora = datetime.now()

    registro = {
        "id": str(uuid.uuid4())[:8],
        "fecha": ahora.strftime("%Y-%m-%d"),
        "hora": op.get("hora", ahora.strftime("%H:%M:%S")),
        "timestamp": ahora.strftime("%Y-%m-%dT%H:%M:%S"),
        "activo": op.get("activo", ""),
        "tipo": op.get("tipo", "").upper(),
        "algoritmo": extras.get("algoritmo", "montecarlo"),
        "inversion": float(op.get("inversion", 0)),
        "resultado": op.get("resultado", "").upper(),
        "profit": float(op.get("profit", 0)),
        "tipo_cuenta": extras.get("tipo_cuenta", "PRACTICE"),
        "saldo_post": float(extras.get("saldo_post", 0)),
    }

    with _file_lock:
        data = _leer_json()
        data.append(registro)
        _escribir_json(data)

    return registro


# ---------------------------------------------------------------------------
# FUNCIONES DE CONSULTA
# ---------------------------------------------------------------------------
def consultar_operaciones(
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    hora_inicio: Optional[str] = None,
    hora_fin: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Consulta operaciones con filtros opcionales de fecha y hora.

    Parámetros
    ----------
    fecha_inicio : str, optional
        Fecha mínima en formato "YYYY-MM-DD".
    fecha_fin : str, optional
        Fecha máxima en formato "YYYY-MM-DD".
    hora_inicio : str, optional
        Hora mínima en formato "HH:MM".
    hora_fin : str, optional
        Hora máxima en formato "HH:MM".

    Retorna
    -------
    list[dict]
        Operaciones que coinciden con los filtros, ordenadas cronológicamente.
    """
    with _file_lock:
        data = _leer_json()

    resultado: List[Dict[str, Any]] = []

    for op in data:
        fecha_op = op.get("fecha", "")
        hora_op = op.get("hora", "")[:5]  # "HH:MM"

        # Filtro por fecha
        if fecha_inicio and fecha_op < fecha_inicio:
            continue
        if fecha_fin and fecha_op > fecha_fin:
            continue

        # Filtro por hora
        if hora_inicio and hora_op < hora_inicio:
            continue
        if hora_fin and hora_op > hora_fin:
            continue

        resultado.append(op)

    # Ordenar cronológicamente
    resultado.sort(key=lambda x: x.get("timestamp", ""))
    return resultado


def obtener_kpis(operaciones: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcula KPIs sobre un conjunto de operaciones.

    Retorna
    -------
    dict
        Diccionario con: total_ops, ganadas, perdidas, empates, win_rate,
        pnl_neto, pnl_promedio, mejor_racha, peor_racha, max_drawdown,
        profit_factor, mejor_dia, peor_dia.
    """
    total = len(operaciones)
    if total == 0:
        return {
            "total_ops": 0, "ganadas": 0, "perdidas": 0, "empates": 0,
            "win_rate": 0.0, "pnl_neto": 0.0, "pnl_promedio": 0.0,
            "mejor_racha": 0, "peor_racha": 0, "max_drawdown": 0.0,
            "profit_factor": 0.0, "mejor_dia": "-", "peor_dia": "-",
            "inversion_total": 0.0, "roi": 0.0,
        }

    ganadas = sum(1 for o in operaciones if "GANADA" in o.get("resultado", "").upper())
    perdidas = sum(1 for o in operaciones if "PERDIDA" in o.get("resultado", "").upper())
    empates = total - ganadas - perdidas

    profits = [o.get("profit", 0.0) for o in operaciones]
    pnl_neto = sum(profits)
    pnl_promedio = pnl_neto / total if total > 0 else 0.0

    inversion_total = sum(o.get("inversion", 0.0) for o in operaciones)
    roi = (pnl_neto / inversion_total * 100) if inversion_total > 0 else 0.0

    # Mejor y peor racha consecutiva
    mejor_racha = _calcular_racha(operaciones, "GANADA")
    peor_racha = _calcular_racha(operaciones, "PERDIDA")

    # Max Drawdown
    max_drawdown = _calcular_max_drawdown(profits)

    # Profit Factor
    ganancias_brutas = sum(p for p in profits if p > 0)
    perdidas_brutas = abs(sum(p for p in profits if p < 0))
    profit_factor = (ganancias_brutas / perdidas_brutas) if perdidas_brutas > 0 else (
        float("inf") if ganancias_brutas > 0 else 0.0
    )

    # Mejor y peor día
    pnl_por_dia: Dict[str, float] = defaultdict(float)
    for op in operaciones:
        pnl_por_dia[op.get("fecha", "")] += op.get("profit", 0.0)

    mejor_dia = max(pnl_por_dia, key=pnl_por_dia.get) if pnl_por_dia else "-"
    peor_dia = min(pnl_por_dia, key=pnl_por_dia.get) if pnl_por_dia else "-"

    return {
        "total_ops": total,
        "ganadas": ganadas,
        "perdidas": perdidas,
        "empates": empates,
        "win_rate": (ganadas / total * 100) if total > 0 else 0.0,
        "pnl_neto": round(pnl_neto, 2),
        "pnl_promedio": round(pnl_promedio, 2),
        "mejor_racha": mejor_racha,
        "peor_racha": peor_racha,
        "max_drawdown": round(max_drawdown, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else 999.99,
        "mejor_dia": mejor_dia,
        "peor_dia": peor_dia,
        "inversion_total": round(inversion_total, 2),
        "roi": round(roi, 2),
    }


def obtener_resumen_por_activo(operaciones: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Agrupa operaciones por activo y calcula estadísticas por cada uno.

    Retorna
    -------
    dict
        {activo: {ops, ganadas, perdidas, pnl, win_rate}}
    """
    por_activo: Dict[str, list] = defaultdict(list)
    for op in operaciones:
        por_activo[op.get("activo", "Desconocido")].append(op)

    resultado = {}
    for activo, ops in por_activo.items():
        g = sum(1 for o in ops if "GANADA" in o.get("resultado", "").upper())
        p = sum(1 for o in ops if "PERDIDA" in o.get("resultado", "").upper())
        pnl = sum(o.get("profit", 0.0) for o in ops)
        resultado[activo] = {
            "ops": len(ops),
            "ganadas": g,
            "perdidas": p,
            "pnl": round(pnl, 2),
            "win_rate": round(g / len(ops) * 100, 1) if ops else 0.0,
        }

    return resultado


def obtener_pnl_temporal(operaciones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calcula la serie temporal de P&L acumulado para gráficos de línea.

    Retorna
    -------
    list[dict]
        [{label, pnl_acum, profit}] ordenado cronológicamente.
    """
    serie = []
    acumulado = 0.0
    for op in operaciones:
        profit = op.get("profit", 0.0)
        acumulado += profit
        serie.append({
            "label": f"{op.get('fecha', '')} {op.get('hora', '')}",
            "pnl_acum": round(acumulado, 2),
            "profit": round(profit, 2),
        })
    return serie


def obtener_distribucion_horaria(operaciones: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Agrupa operaciones por hora del día (00-23) para gráfico de barras.

    Retorna
    -------
    dict
        {hora: {ops, ganadas, perdidas, pnl}}
    """
    por_hora: Dict[str, list] = defaultdict(list)
    for op in operaciones:
        hora_str = op.get("hora", "00:00:00")[:2]  # "HH"
        por_hora[hora_str].append(op)

    resultado = {}
    for hora in sorted(por_hora.keys()):
        ops = por_hora[hora]
        g = sum(1 for o in ops if "GANADA" in o.get("resultado", "").upper())
        p = sum(1 for o in ops if "PERDIDA" in o.get("resultado", "").upper())
        pnl = sum(o.get("profit", 0.0) for o in ops)
        resultado[f"{hora}:00"] = {
            "ops": len(ops),
            "ganadas": g,
            "perdidas": p,
            "pnl": round(pnl, 2),
        }

    return resultado


# ---------------------------------------------------------------------------
# UTILIDADES INTERNAS
# ---------------------------------------------------------------------------
def _calcular_racha(operaciones: List[Dict[str, Any]], tipo: str) -> int:
    """Calcula la racha consecutiva más larga de un tipo de resultado."""
    max_racha = 0
    racha_actual = 0
    for op in operaciones:
        if tipo in op.get("resultado", "").upper():
            racha_actual += 1
            max_racha = max(max_racha, racha_actual)
        else:
            racha_actual = 0
    return max_racha


def _calcular_max_drawdown(profits: List[float]) -> float:
    """Calcula el máximo drawdown (pérdida máxima desde el pico más alto)."""
    if not profits:
        return 0.0
    pnl_acum = 0.0
    pico = 0.0
    max_dd = 0.0
    for p in profits:
        pnl_acum += p
        if pnl_acum > pico:
            pico = pnl_acum
        dd = pico - pnl_acum
        if dd > max_dd:
            max_dd = dd
    return max_dd


# ---------------------------------------------------------------------------
# STANDALONE TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Test de Registro de Operaciones ===")
    # Test: guardar
    op_test = {
        "hora": "14:30:00", "activo": "EURUSD-OTC", "tipo": "CALL",
        "inversion": 4, "resultado": "GANADA", "profit": 3.12,
    }
    reg = guardar_operacion(op_test, algoritmo="montecarlo", tipo_cuenta="PRACTICE", saldo_post=103.12)
    print(f"Guardado: {reg}")

    # Test: consultar
    ops = consultar_operaciones()
    print(f"Total registros: {len(ops)}")

    # Test: KPIs
    kpis = obtener_kpis(ops)
    print(f"KPIs: {kpis}")
