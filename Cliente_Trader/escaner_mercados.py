# escaner_mercados.py
# ============================================================================
# Escáner de Mercados Refactorizado — Mapeo Dinámico de Activos
# Utiliza get_all_ACTIVES_OPCODE() + get_all_open_time() en lugar de
# la función obsoleta get_all_profit().
# ============================================================================

"""
Módulo de escaneo y descubrimiento de activos del broker IQ Option.

Expone la función pública ``obtener_activos_disponibles(api)`` que devuelve
una lista de diccionarios con información estructurada de cada activo abierto,
incluyendo nombre legible, tipo de mercado y opcode.

Uso como módulo::

    from escaner_mercados import obtener_activos_disponibles
    activos = obtener_activos_disponibles(api)

Uso standalone::

    python escaner_mercados.py
"""

from __future__ import annotations

from typing import Any

# Colores ANSI para la terminal
COLOR_VERDE: str = "\033[92m"
COLOR_ROJO: str = "\033[91m"
COLOR_AZUL: str = "\033[94m"
COLOR_AMARILLO: str = "\033[93m"
COLOR_RESET: str = "\033[0m"

# Tipos de mercado reconocidos por la API
TIPOS_MERCADO: list[str] = ["binary", "turbo", "digital", "cfd", "forex", "crypto"]


def obtener_activos_disponibles(api: Any) -> list[dict[str, Any]]:
    """
    Obtiene todos los activos actualmente abiertos en el broker.

    Combina ``api.get_all_ACTIVES_OPCODE()`` (mapeo nombre→opcode) con
    ``api.get_all_open_time()`` (estado abierto/cerrado por tipo de mercado)
    para generar una lista filtrada de activos operables.

    Parámetros
    ----------
    api : IQ_Option
        Instancia conectada de la API de IQ Option.

    Retorna
    -------
    list[dict[str, Any]]
        Lista de diccionarios con las claves:
        - ``nombre`` (str): Ticker legible (ej. "EURUSD", "Apple-OTC").
        - ``tipo`` (str): Tipo de mercado ("binary", "turbo", "digital", etc.).
        - ``opcode`` (int): Código identificador interno del activo.
        - ``abierto`` (bool): Siempre True (solo se devuelven activos abiertos).
    """
    activos_disponibles: list[dict[str, Any]] = []

    try:
        # 1. Obtener el mapeo completo nombre → opcode
        api.update_ACTIVES_OPCODE()
        opcodes: dict[str, int] = api.get_all_ACTIVES_OPCODE()
    except Exception:
        opcodes = {}

    try:
        # 2. Obtener el estado abierto/cerrado de cada activo por tipo
        tiempos_apertura: dict = api.get_all_open_time()
    except Exception:
        tiempos_apertura = {}

    # 3. Cruzar ambas fuentes de datos
    nombres_agregados: set[str] = set()

    for tipo_mercado in TIPOS_MERCADO:
        activos_tipo: dict = tiempos_apertura.get(tipo_mercado, {})
        if not isinstance(activos_tipo, dict):
            continue

        for nombre_activo, info in activos_tipo.items():
            if not isinstance(info, dict):
                continue

            esta_abierto: bool = info.get("open", False)
            if not esta_abierto:
                continue

            # Buscar el opcode correspondiente
            opcode: int = opcodes.get(nombre_activo, -1)

            # Clave de deduplicación: solo por nombre (evitar duplicados en UI)
            if nombre_activo in nombres_agregados:
                continue
            nombres_agregados.add(nombre_activo)

            activos_disponibles.append({
                "nombre": nombre_activo,
                "tipo": tipo_mercado,
                "opcode": opcode,
                "abierto": True,
            })

    # Ordenar alfabéticamente por nombre para presentación limpia
    activos_disponibles.sort(key=lambda x: x["nombre"])
    return activos_disponibles


def escanear_servidor_sin_filtros() -> None:
    """
    Función standalone para escaneo completo desde la terminal.

    Conecta al broker, ejecuta ``obtener_activos_disponibles()`` e imprime
    los resultados en una tabla formateada con colores ANSI.
    """
    from iqoptionapi.stable_api import IQ_Option
    import user

    print(f"{COLOR_AZUL}[INICIANDO] Escáner Global Refactorizado - IQ Option{COLOR_RESET}")

    api = IQ_Option(user.EMAIL, user.PASSWORD)
    status, message = api.connect()

    if not status:
        print(f"{COLOR_ROJO}[ERROR] No se pudo conectar: {message}{COLOR_RESET}")
        return

    print("Conexión exitosa. Escaneando activos abiertos...\n")

    activos = obtener_activos_disponibles(api)

    # Imprimir tabla formateada
    print("=" * 70)
    print(f"{'TICKER':<22} | {'TIPO':<10} | {'OPCODE':<8} | {'ESTADO'}")
    print("=" * 70)

    for activo in activos:
        nombre: str = activo["nombre"]
        tipo: str = activo["tipo"]
        opcode: int = activo["opcode"]
        color = COLOR_VERDE

        print(
            f"{nombre:<22} | {tipo:<10} | {opcode:<8} | "
            f"{color}ABIERTO{COLOR_RESET}"
        )

    print("=" * 70)
    print(f"Total de activos abiertos encontrados: {len(activos)}")

    try:
        api.api.close()
    except Exception:
        pass


if __name__ == "__main__":
    escanear_servidor_sin_filtros()