# iq_option.py
# ============================================================================
# Nodo Maestro del Sistema de Trading Algorítmico
# Integrado con MotorMonteCarlo (EWMA + GBM vectorizado de 50,000 iteraciones)
# Soporta ejecución standalone (CLI) y ejecución delegada desde dashboard.py
# ============================================================================

"""
Módulo principal de ejecución del bot de trading algorítmico.

Flujo de operación:
    1. Conecta al broker vía WebSocket.
    2. Para cada ciclo: descarga velas → analiza con MotorMonteCarlo → ejecuta orden.
    3. Genera reporte PDF al finalizar.

Modo CLI::
    python iq_option.py

Modo integrado (desde dashboard.py)::
    ejecutar_bot_completo(api=api_existente, callback_log=fn, evento_parada=evento)
"""

from __future__ import annotations

import signal
import time
from datetime import datetime
from typing import Any, Callable, Optional

import numpy as np
from iqoptionapi.stable_api import IQ_Option

import generarPDF
import user
from motor_cuantitativo import MotorMonteCarlo
from algoritmos import crear_algoritmo

# Colores ANSI para salida en terminal
COLOR_VERDE: str = "\033[92m"
COLOR_ROJO: str = "\033[91m"
COLOR_RESET: str = "\033[0m"

# =========================================================================
# ⚙️ PANEL DE CONTROL (VARIABLES MODIFICABLES POR EL USUARIO)
# =========================================================================
# Parámetros Financieros
INVERSION_FIJA: int = 4              # Inversión fija de 4 USD (mínimo en Dólares)
PCT_PERDIDA_MAXIMA: float = 1.00     # 100% de pérdida permitida
PCT_GANANCIA_MAXIMA: float = 0.50    # 50% de ganancia meta

# Parámetros Operativos
ACTIVO: str = "EURUSD-OTC"           # Mercado por defecto
EXPIRACION: int = 1                  # Duración del contrato en minutos
HORIZONTE_T: int = 50                # Número máximo de operaciones seguidas

# Parámetros Técnicos (Red y Procesamiento)
VELAS_HISTORICAS: int = 1000         # Muestra global para volatilidad robusta
SIMULACIONES_MC: int = 50_000        # Iteraciones de Monte Carlo (vectorizado)
VENTANA_EWMA: int = 5               # Span EWMA para drift (peso en últimos 5 min)
VENTANA_TENDENCIA: int = 30          # Ventana de retornos para calcular μ
# =========================================================================

# --- Control de parada suave (modo CLI) ---
_solicitud_parada: bool = False


def _manejador_parada_suave(signum: int, frame: Any) -> None:
    """Captura SIGINT para permitir un cierre limpio del ciclo activo."""
    global _solicitud_parada
    print(f"\n{COLOR_ROJO}[ALERTA] Señal de parada recibida. "
          f"Finalizando ciclo actual...{COLOR_RESET}")
    _solicitud_parada = True


signal.signal(signal.SIGINT, _manejador_parada_suave)


def ejecutar_bot_completo(
    api: Optional[IQ_Option] = None,
    callback_log: Optional[Callable[[str, str], None]] = None,
    evento_parada: Optional[Any] = None,
    activo: str = ACTIVO,
    inversion: int = INVERSION_FIJA,
    expiracion: int = EXPIRACION,
    horizonte: int = HORIZONTE_T,
    pct_sl: float = PCT_PERDIDA_MAXIMA,
    pct_tp: float = PCT_GANANCIA_MAXIMA,
    modo_balance: str = "PRACTICE",
    callback_operacion: Optional[Callable[[dict], None]] = None,
    algoritmo_id: str = "montecarlo",
) -> None:
    """
    Ejecuta el bucle completo del bot de trading algorítmico.

    Parámetros
    ----------
    api : IQ_Option, optional
        Instancia conectada. Si es None, crea una nueva conexión.
    callback_log : callable, optional
        Función ``(nivel: str, mensaje: str) -> None`` para redirigir logs.
        Si es None, usa ``print()`` estándar.
    evento_parada : threading.Event, optional
        Evento para solicitar parada desde otro hilo.
    activo : str
        Ticker del activo a operar.
    inversion : int
        Monto fijo por operación.
    expiracion : int
        Duración del contrato en minutos.
    horizonte : int
        Número máximo de operaciones.
    pct_sl : float
        Porcentaje máximo de pérdida (Stop Loss).
    pct_tp : float
        Porcentaje de ganancia objetivo (Take Profit).
    modo_balance : str
        "PRACTICE" o "REAL".
    """
    global _solicitud_parada

    # --- Función de logging flexible ---
    def log(nivel: str, mensaje: str) -> None:
        if callback_log:
            callback_log(nivel, mensaje)
        else:
            prefijo = COLOR_VERDE if nivel == "OK" else (
                COLOR_ROJO if nivel in ("ERROR", "ALERTA") else ""
            )
            sufijo = COLOR_RESET if prefijo else ""
            print(f"{prefijo}[{nivel}] {mensaje}{sufijo}")

    log("INFO", "SISTEMA DISTRIBUIDO: NODO MAESTRO (MODO CUANTITATIVO)")
    log("INFO", "Cargando parámetros del Panel de Control...")

    # --- Conexión ---
    gestion_propia: bool = api is None
    if gestion_propia:
        api = IQ_Option(user.EMAIL, user.PASSWORD)
        status, message = api.connect()
        if not status:
            log("ERROR", f"No se pudo iniciar el Core: {message}")
            return
        log("OK", "Enlace WebSocket establecido con el servidor financiero")

    api.change_balance(modo_balance)
    X_0: float = api.get_balance()
    LIMITE_DRAWDOWN: float = X_0 * (1 - pct_sl)
    LIMITE_TAKE_PROFIT: float = X_0 * (1 + pct_tp)
    I_t: int = inversion

    ops_ganadas: int = 0
    ops_perdidas: int = 0
    ops_empates: int = 0
    operaciones_realizadas: int = 0

    log("INFO", f"Capital Inicial (X0): ${X_0:.2f} USD")
    log("INFO", f"Inversion Fija: ${I_t} USD | Algoritmo: {algoritmo_id}")

    # --- Instanciar algoritmo seleccionado ---
    try:
        motor = crear_algoritmo(algoritmo_id, simulaciones=SIMULACIONES_MC,
                                ventana_ewma=VENTANA_EWMA, ventana_tendencia=VENTANA_TENDENCIA)
        velas_requeridas = getattr(motor, 'velas_minimas', 200)
    except Exception as e:
        log("ERROR", f"No se pudo crear algoritmo '{algoritmo_id}': {e}")
        return

    # --- Bucle principal de operaciones ---
    for t in range(1, horizonte + 1):
        # Verificar señales de parada
        if _solicitud_parada:
            break
        if evento_parada and evento_parada.is_set():
            log("ALERTA", "Parada solicitada desde el dashboard.")
            break

        log("INFO", f"[Ciclo {t}/{horizonte}] Obteniendo datos de mercado...")

        try:
            X_t: float = api.get_balance()
        except Exception as e:
            log("ERROR", f"Error al obtener saldo: {e}")
            time.sleep(3)
            continue

        log("INFO", f"Capital actual: ${X_t:.2f} USD")

        # --- Guardianes de riesgo ---
        if X_t <= LIMITE_DRAWDOWN:
            log("ALERTA", "STOP LOSS ALCANZADO. Protegiendo capital restante.")
            break

        if X_t >= LIMITE_TAKE_PROFIT:
            log("OK", "TAKE PROFIT ALCANZADO. Ganancia objetivo lograda.")
            break

        if X_t < I_t:
            log("ALERTA", f"Capital insuficiente para operar S/{I_t}.")
            break

        # --- Descarga de datos históricos ---
        log("INFO", f"Descargando {VELAS_HISTORICAS} velas de {activo}...")
        try:
            velas = api.get_candles(activo, 60, VELAS_HISTORICAS, time.time())
        except Exception as e:
            log("ERROR", f"Error al obtener velas: {e}")
            time.sleep(5)
            continue

        if not velas or len(velas) < velas_requeridas:
            log("ERROR", f"Datos incompletos ({len(velas) if velas else 0} velas, "
                         f"necesarias {velas_requeridas}). Reintentando...")
            time.sleep(5)
            continue

        precios: list[float] = [v["close"] for v in velas]

        # --- Analisis con el algoritmo seleccionado ---
        resultado = motor.analizar(precios)
        if resultado is None:
            log("ERROR", "Algoritmo retorno resultado nulo.")
            continue

        direccion_senal: str = resultado["direccion"]

        confianza = resultado.get("confianza", 0.0)
        prob_subida = resultado.get("prob_subida", 0.5)

        if "mu" in resultado:
            log("INFO", f"Drift EWMA: {resultado['mu']:.6f} | "
                         f"Volatilidad: {resultado.get('sigma', 0):.6f}")
        if "sma_rapida" in resultado:
            log("INFO", f"SMA Rapida: {resultado['sma_rapida']:.4f} | "
                         f"SMA Lenta: {resultado['sma_lenta']:.4f}")
        log("INFO", f"P(Subida): {prob_subida * 100:.2f}% | "
                     f"Confianza: {confianza * 100:.1f}%")
        log("INFO", f"Direccion: {direccion_senal.upper()}")

        # --- Ejecución de la orden ---
        log("INFO", f"Ejecutando orden {direccion_senal.upper()} en {activo} "
                     f"por ${I_t} USD")
        try:
            check, id_orden = api.buy(I_t, activo, direccion_senal, expiracion)
        except KeyError:
            log("ERROR", f"El mercado '{activo}' no existe o no está habilitado.")
            break
        except Exception as e:
            log("ERROR", f"Error al ejecutar orden: {e}")
            time.sleep(5)
            continue

        if check:
            log("OK", f"Orden aceptada. ID: {id_orden}")
            log("INFO", "Monitoreando resultado del contrato...")

            try:
                resultado = api.check_win_v3(id_orden)
            except Exception as e:
                log("ERROR", f"Error al verificar resultado: {e}")
                continue

            operaciones_realizadas += 1

            res_str = "GANADA" if resultado > 0 else ("PERDIDA" if resultado < 0 else "EMPATE")
            if resultado < 0:
                log("ALERTA", f"Pérdida: ${resultado:.2f} USD")
                ops_perdidas += 1
            elif resultado > 0:
                log("OK", f"Ganancia: +${resultado:.2f} USD")
                ops_ganadas += 1
            else:
                log("INFO", "Empate: $0.00 USD")
                ops_empates += 1

            if callback_operacion:
                try:
                    op_data = {
                        "hora": datetime.now().strftime("%H:%M:%S"),
                        "activo": activo,
                        "tipo": direccion_senal.upper(),
                        "inversion": I_t,
                        "resultado": res_str,
                        "profit": resultado
                    }
                    callback_operacion(op_data)
                except Exception as ex:
                    log("ERROR", f"Error en callback de operación: {ex}")
        else:
            log("ERROR", "El broker rechazó la orden. Posible falta de liquidez.")
            time.sleep(5)

    # --- Cierre y generación de reporte ---
    try:
        X_final: float = api.get_balance()
    except Exception:
        X_final = X_0

    rendimiento_neto: float = X_final - X_0

    log("INFO", "=" * 40)
    log("INFO", "       RESUMEN DE LA SESIÓN")
    log("INFO", "=" * 40)
    log("INFO", f"Capital Inicial: ${X_0:.2f} USD")
    log("INFO", f"Capital Final:   ${X_final:.2f} USD")

    if rendimiento_neto > 0:
        log("OK", f"Ganancia Neta: ${rendimiento_neto:.2f} USD")
    elif rendimiento_neto < 0:
        log("ALERTA", f"Pérdida Neta: ${abs(rendimiento_neto):.2f} USD")
    else:
        log("INFO", "Sin variación en el capital.")

    # Solo generar PDF en modo standalone (CLI).
    # Cuando se ejecuta desde un dashboard, este genera su propio PDF con historial completo.
    if not callback_operacion:
        log("INFO", "Generando auditoría en PDF...")
        try:
            generarPDF.crear_reporte(
                mercado=activo,
                x0=X_0,
                x_final=X_final,
                rendimiento=rendimiento_neto,
                total_ops=operaciones_realizadas,
                ganadas=ops_ganadas,
                perdidas=ops_perdidas,
                empates=ops_empates,
            )
        except Exception as e:
            log("ERROR", f"No se pudo generar el PDF: {e}")

    if gestion_propia:
        try:
            api.api.close()
        except Exception:
            pass
        log("INFO", "Ecosistema desconectado de forma segura.")


if __name__ == "__main__":
    ejecutar_bot_completo()