# algoritmos/tendencia.py
# ============================================================================
# Algoritmo: Cruce de Medias Moviles Simples (SMA)
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from algoritmos import AlgoritmoBase


class AlgoritmoTendencia(AlgoritmoBase):
    nombre = "Tendencia SMA"
    descripcion = "Cruce de medias moviles simples. SMA rapida vs SMA lenta. Si la rapida esta por encima: CALL, por debajo: PUT."

    def __init__(self, ventana_rapida: int = 5, ventana_lenta: int = 20, velas_minimas: int = 50, **kwargs):
        self.ventana_rapida = ventana_rapida
        self.ventana_lenta = ventana_lenta
        self.velas_minimas = velas_minimas

    def analizar(self, precios: List[float]) -> Optional[Dict[str, Any]]:
        if not precios or len(precios) < self.velas_minimas:
            return None

        arr = np.array(precios, dtype=np.float64)

        sma_rapida = np.mean(arr[-self.ventana_rapida:])
        sma_lenta = np.mean(arr[-self.ventana_lenta:])

        direccion = "call" if sma_rapida > sma_lenta else "put"

        diff = sma_rapida - sma_lenta
        rango = sma_lenta if sma_lenta != 0 else 1.0
        fuerza = min(1.0, abs(diff) / (rango * 0.01))

        return {
            "direccion": direccion,
            "sma_rapida": float(sma_rapida),
            "sma_lenta": float(sma_lenta),
            "diferencia": float(diff),
            "confianza": fuerza,
            "prob_subida": 0.65 if direccion == "call" else 0.35,
            "prob_bajada": 0.35 if direccion == "call" else 0.65,
            "precio_actual": float(arr[-1]),
        }
