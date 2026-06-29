# algoritmos/aleatorio.py
# ============================================================================
# Algoritmo: Seleccion Aleatoria (Baseline)
# ============================================================================

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from algoritmos import AlgoritmoBase


class AlgoritmoAleatorio(AlgoritmoBase):
    nombre = "Aleatorio (Random)"
    descripcion = "Seleccion aleatoria simple entre CALL y PUT. Util como linea base de comparacion."

    def __init__(self, **kwargs):
        pass

    def analizar(self, precios: List[float]) -> Optional[Dict[str, Any]]:
        direccion = random.choice(["call", "put"])
        return {
            "direccion": direccion,
            "prob_subida": 0.5,
            "prob_bajada": 0.5,
            "confianza": 0.0,
            "precio_actual": precios[-1] if precios else 0.0,
        }
