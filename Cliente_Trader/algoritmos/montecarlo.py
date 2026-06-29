# algoritmos/montecarlo.py
# ============================================================================
# Algoritmo: Monte Carlo GBM con Drift EWMA
# Basado en el articulo "Analytical Modeling and Empirical Analysis of Binary Options"
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from algoritmos import AlgoritmoBase


class AlgoritmoMonteCarlo(AlgoritmoBase):
    nombre = "Monte Carlo GBM + EWMA"
    descripcion = "Simulacion de Monte Carlo con Movimiento Browniano Geometrico y drift estimado via EWMA. 50,000 iteraciones vectorizadas con NumPy."

    def __init__(self, simulaciones: int = 50_000, ventana_ewma: int = 5,
                 ventana_tendencia: int = 30, velas_minimas: int = 200):
        self.simulaciones = simulaciones
        self.ventana_ewma = ventana_ewma
        self.ventana_tendencia = ventana_tendencia
        self.velas_minimas = velas_minimas

    def analizar(self, precios: List[float]) -> Optional[Dict[str, Any]]:
        if not precios or len(precios) < self.velas_minimas:
            return None

        arr = np.array(precios, dtype=np.float64)
        rendimientos = np.log(arr[1:] / arr[:-1])

        sigma = float(np.std(rendimientos))
        if sigma == 0.0:
            sigma = 1e-8

        ventana = rendimientos[-self.ventana_tendencia:]
        mu = self._ewma(ventana, self.ventana_ewma)

        precio_actual = float(arr[-1])
        dt = 1.0
        z = np.random.standard_normal(self.simulaciones)
        drift = (mu - 0.5 * sigma**2) * dt
        stoch = sigma * z * np.sqrt(dt)
        simulados = precio_actual * np.exp(drift + stoch)

        prob_subida = float(np.mean(simulados > precio_actual))
        direccion = "call" if prob_subida > 0.5 else "put"

        return {
            "direccion": direccion,
            "prob_subida": prob_subida,
            "prob_bajada": 1.0 - prob_subida,
            "mu": mu,
            "sigma": sigma,
            "precio_actual": precio_actual,
            "precio_medio_sim": float(np.mean(simulados)),
            "confianza": abs(prob_subida - 0.5) * 2,
        }

    @staticmethod
    def _ewma(datos: np.ndarray, span: int) -> float:
        if len(datos) == 0:
            return 0.0
        alpha = 2.0 / (span + 1)
        ewma = float(datos[0])
        for v in datos[1:]:
            ewma = alpha * float(v) + (1.0 - alpha) * ewma
        return ewma
