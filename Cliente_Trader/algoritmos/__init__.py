# algoritmos/__init__.py
# ============================================================================
# Registro de Algoritmos de Trading — Interfaz comun para todos los motores
# ============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional


class AlgoritmoBase:
    """Interfaz comun que deben implementar todos los algoritmos de trading."""

    nombre: str = "base"
    descripcion: str = "Algoritmo base"

    def analizar(self, precios: List[float]) -> Optional[Dict[str, Any]]:
        """
        Analiza una serie de precios y retorna la senal de trading.

        Parametros
        ----------
        precios : list[float]
            Lista de precios de cierre historicos (del mas antiguo al mas reciente).

        Retorna
        -------
        dict o None
            Diccionario con al menos la clave 'direccion' ('call' o 'put').
            Puede incluir metadatos adicionales como 'prob_subida', 'confianza', etc.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Importar y registrar todos los algoritmos disponibles
# ---------------------------------------------------------------------------
from algoritmos.montecarlo import AlgoritmoMonteCarlo
from algoritmos.aleatorio import AlgoritmoAleatorio
from algoritmos.tendencia import AlgoritmoTendencia

ALGORITMOS: Dict[str, type] = {
    "montecarlo": AlgoritmoMonteCarlo,
    "aleatorio": AlgoritmoAleatorio,
    "tendencia": AlgoritmoTendencia,
}

ALGORITMOS_LISTA: List[Dict[str, str]] = [
    {"id": "montecarlo", "nombre": "Monte Carlo GBM + EWMA", "descripcion": "Simulacion de Monte Carlo con Movimiento Browniano Geometrico y drift EWMA (50,000 iteraciones vectorizadas). Basado en modelado estocastico."},
    {"id": "aleatorio", "nombre": "Aleatorio (Random)", "descripcion": "Seleccion aleatoria simple (call/put). Util como baseline de comparacion."},
    {"id": "tendencia", "nombre": "Tendencia SMA", "descripcion": "Cruce de medias moviles simples (SMA rapida vs SMA lenta). Si la rapida cruza arriba: CALL, abajo: PUT."},
]


def crear_algoritmo(algoritmo_id: str, **kwargs) -> AlgoritmoBase:
    """Fabrica de algoritmos. Retorna una instancia del algoritmo solicitado."""
    clase = ALGORITMOS.get(algoritmo_id)
    if clase is None:
        raise ValueError(f"Algoritmo desconocido: {algoritmo_id}. Disponibles: {list(ALGORITMOS.keys())}")
    return clase(**kwargs)


def obtener_lista() -> List[Dict[str, str]]:
    """Retorna la lista de algoritmos disponibles para la UI."""
    return ALGORITMOS_LISTA
