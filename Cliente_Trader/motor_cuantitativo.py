# motor_cuantitativo.py
# ============================================================================
# Motor Estocástico Independiente: Simulación de Monte Carlo con EWMA
# Implementa el Movimiento Browniano Geométrico (GBM) vectorizado.
# ============================================================================

"""
Módulo de análisis cuantitativo basado en Movimiento Browniano Geométrico (GBM).

Proporciona la clase ``MotorMonteCarlo`` que encapsula:
- Cálculo del Drift (μ) mediante EWMA (Exponentially Weighted Moving Average).
- Estimación de Volatilidad (σ) global sobre rendimientos logarítmicos.
- Simulación de Monte Carlo completamente vectorizada con NumPy.

Uso típico::

    motor = MotorMonteCarlo(simulaciones=50_000, ventana_ewma=5)
    resultado = motor.analizar(lista_de_precios_cierre)
    print(resultado["direccion"])  # "call" o "put"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Estructura de datos para los resultados del análisis
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResultadoAnalisis:
    """Resultado inmutable de una simulación Monte Carlo."""

    mu: float                # Drift estimado via EWMA
    sigma: float             # Volatilidad global (desv. estándar de retornos log)
    prob_subida: float       # P(precio_futuro > precio_actual)
    prob_bajada: float       # 1 - prob_subida
    direccion: str           # "call" si prob_subida > 0.5, sino "put"
    precio_actual: float     # Último precio de cierre observado
    precio_medio_sim: float  # Media de los precios simulados

    def to_dict(self) -> dict:
        """Serializa el resultado a diccionario plano."""
        return {
            "mu": self.mu,
            "sigma": self.sigma,
            "prob_subida": self.prob_subida,
            "prob_bajada": self.prob_bajada,
            "direccion": self.direccion,
            "precio_actual": self.precio_actual,
            "precio_medio_sim": self.precio_medio_sim,
        }


# ---------------------------------------------------------------------------
# Clase principal del motor cuantitativo
# ---------------------------------------------------------------------------
class MotorMonteCarlo:
    """
    Motor de predicción basado en GBM con drift EWMA y Monte Carlo vectorizado.

    Parámetros
    ----------
    simulaciones : int
        Número de trayectorias a simular (por defecto 50,000).
    ventana_ewma : int
        *Span* del EWMA para ponderar el drift. Un span de 5 otorga
        ~95 % del peso acumulado a las últimas 8 observaciones, lo que
        captura la micro‑tendencia de los últimos 5 minutos.
    ventana_tendencia : int
        Cantidad de retornos recientes sobre los cuales se aplica EWMA
        para estimar μ (por defecto 30, equivalente a 30 min con velas
        de 1 min).
    velas_minimas : int
        Cantidad mínima de precios para considerar el análisis válido.
    """

    def __init__(
        self,
        simulaciones: int = 50_000,
        ventana_ewma: int = 5,
        ventana_tendencia: int = 30,
        velas_minimas: int = 200,
    ) -> None:
        if simulaciones < 1:
            raise ValueError("El número de simulaciones debe ser >= 1.")
        self.simulaciones: int = simulaciones
        self.ventana_ewma: int = ventana_ewma
        self.ventana_tendencia: int = ventana_tendencia
        self.velas_minimas: int = velas_minimas

    # ------------------------------------------------------------------
    # Métodos públicos
    # ------------------------------------------------------------------
    def analizar(self, precios: list[float]) -> Optional[ResultadoAnalisis]:
        """
        Ejecuta el pipeline completo de análisis cuantitativo.

        1. Valida los datos de entrada.
        2. Calcula rendimientos logarítmicos.
        3. Estima σ (volatilidad global) y μ (drift EWMA).
        4. Ejecuta Monte Carlo vectorizado.
        5. Retorna un ``ResultadoAnalisis``.

        Parámetros
        ----------
        precios : list[float]
            Precios de cierre históricos (mínimo ``self.velas_minimas``).

        Retorna
        -------
        ResultadoAnalisis o None si los datos son insuficientes.
        """
        if not precios or len(precios) < self.velas_minimas:
            return None

        precios_arr: np.ndarray = np.array(precios, dtype=np.float64)

        # --- 1. Rendimientos logarítmicos ---
        rendimientos: np.ndarray = np.log(precios_arr[1:] / precios_arr[:-1])

        # --- 2. Volatilidad global (σ) ---
        sigma: float = float(np.std(rendimientos))
        if sigma == 0.0:
            sigma = 1e-8  # Evitar divisiones por cero

        # --- 3. Drift local (μ) vía EWMA ---
        ventana: np.ndarray = rendimientos[-self.ventana_tendencia:]
        mu: float = self._calcular_ewma(ventana, self.ventana_ewma)

        # --- 4. Simulación Monte Carlo vectorizada ---
        precio_actual: float = float(precios_arr[-1])
        precios_simulados = self._simular_gbm(precio_actual, mu, sigma)

        # --- 5. Probabilidades ---
        prob_subida: float = float(np.mean(precios_simulados > precio_actual))
        prob_bajada: float = 1.0 - prob_subida
        precio_medio_sim: float = float(np.mean(precios_simulados))

        direccion: str = "call" if prob_subida > prob_bajada else "put"

        return ResultadoAnalisis(
            mu=mu,
            sigma=sigma,
            prob_subida=prob_subida,
            prob_bajada=prob_bajada,
            direccion=direccion,
            precio_actual=precio_actual,
            precio_medio_sim=precio_medio_sim,
        )

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------
    @staticmethod
    def _calcular_ewma(datos: np.ndarray, span: int) -> float:
        """
        Calcula la Media Móvil Exponencialmente Ponderada (EWMA) recursiva.

        Fórmula recursiva:
            EWMA_0 = r_0
            EWMA_t = α · r_t  +  (1 − α) · EWMA_{t−1}

        donde  α = 2 / (span + 1).

        Con ``span = 5`` →  α ≈ 0.333, otorgando peso dominante a las
        últimas ≈ 5 observaciones en la ventana.

        Parámetros
        ----------
        datos : np.ndarray
            Ventana de rendimientos logarítmicos.
        span : int
            Parámetro de decaimiento exponencial.

        Retorna
        -------
        float  —  Valor EWMA del último período.
        """
        if len(datos) == 0:
            return 0.0
        alpha: float = 2.0 / (span + 1)
        ewma: float = float(datos[0])
        for valor in datos[1:]:
            ewma = alpha * float(valor) + (1.0 - alpha) * ewma
        return ewma

    def _simular_gbm(
        self, precio_actual: float, mu: float, sigma: float
    ) -> np.ndarray:
        """
        Simulación vectorizada del Movimiento Browniano Geométrico.

        S_T = S_0 · exp[(μ − ½σ²)Δt + σ·√Δt·Z]

        donde Z ~ N(0, 1) y Δt = 1.0 (un período).

        Retorna un array de ``self.simulaciones`` precios simulados.
        """
        dt: float = 1.0
        z: np.ndarray = np.random.standard_normal(self.simulaciones)

        componente_drift: float = (mu - 0.5 * sigma**2) * dt
        componente_estocastico: np.ndarray = sigma * z * np.sqrt(dt)

        precios_simulados: np.ndarray = precio_actual * np.exp(
            componente_drift + componente_estocastico
        )
        return precios_simulados


# ---------------------------------------------------------------------------
# Ejecución standalone para pruebas rápidas
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import random

    print("=== Test del Motor Cuantitativo ===")
    motor = MotorMonteCarlo(simulaciones=50_000, ventana_ewma=5)

    # Generar precios sintéticos (tendencia alcista leve)
    precios_test: list[float] = [100.0]
    for _ in range(999):
        cambio = random.gauss(0.0001, 0.001)
        precios_test.append(precios_test[-1] * (1 + cambio))

    resultado = motor.analizar(precios_test)
    if resultado:
        print(f"Precio Actual:    {resultado.precio_actual:.4f}")
        print(f"Drift (μ EWMA):   {resultado.mu:.8f}")
        print(f"Volatilidad (σ):  {resultado.sigma:.8f}")
        print(f"P(Subida):        {resultado.prob_subida * 100:.2f}%")
        print(f"P(Bajada):        {resultado.prob_bajada * 100:.2f}%")
        print(f"Dirección:        {resultado.direccion.upper()}")
        print(f"Precio Medio Sim: {resultado.precio_medio_sim:.4f}")
    else:
        print("Datos insuficientes para el análisis.")
