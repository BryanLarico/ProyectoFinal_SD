# App Cliente Trader — Nodo Esclavo de Copy Trading

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                  App_Cliente_Trader                 │
│                                                     │
│  ┌─────────────┐    ┌──────────────────────────┐   │
│  │ dashboard.py │───▶│ IQ Option WebSocket API  │   │
│  │  (GUI CTk)   │    │  • Descarga de velas     │   │
│  │              │    │  • Ejecución de órdenes  │   │
│  │  ┌──────────┐│    │  • Streaming en vivo     │   │
│  │  │  Modal   ││    └──────────────────────────┘   │
│  │  │  Código  ││                                   │
│  │  │  Maestro ││    ┌──────────────────────────┐   │
│  │  └──────────┘│    │ motor_cuantitativo.py    │   │
│  │       │      │    │  • GBM + EWMA drift      │   │
│  │       ▼      │    │  • Monte Carlo 50k iter  │   │
│  │  ┌──────────┐│    │  • P(subida)/P(bajada)   │   │
│  │  │  Stub    ││    └──────────────────────────┘   │
│  │  │  ZMQ SUB ││                                   │
│  │  │  (futuro)││    ┌──────────────────────────┐   │
│  │  └──────────┘│    │ generarPDF.py            │   │
│  └─────────────┘    │  • Reportes auditoría     │   │
│                     │  • Estilo fintech          │   │
│  ┌─────────────┐    └──────────────────────────┘   │
│  │ iq_option.py│                                   │
│  │  (bot loop) │    ┌──────────────────────────┐   │
│  └─────────────┘    │ escaner_mercados.py      │   │
│                     │  • get_all_ACTIVES_OPCODE │   │
│  ┌─────────────┐    │  • get_all_open_time      │   │
│  │veriffy_user │    └──────────────────────────┘   │
│  └─────────────┘                                   │
└─────────────────────────────────────────────────────┘
```

## Estructura de archivos

| Archivo | Rol | Líneas |
|---|---|---|
| `dashboard.py` | GUI principal (CustomTkinter modo oscuro). Panel lateral con parámetros de riesgo, gráfico de velas en vivo (mplfinance), botones CALL/PUT, bot automático, consola de logs. **Antes de habilitar trading, solicita código de conexión al Servidor Maestro vía modal.** | ~1036 |
| `iq_option.py` | Bucle del bot algorítmico. Descarga velas → ejecuta Monte Carlo → decide CALL/PUT → ordena al broker. Soporta modo CLI y delegación desde `dashboard.py`. | ~327 |
| `motor_cuantitativo.py` | Motor estocástico GBM con drift EWMA. Simulación de Monte Carlo vectorizada (50,000 iteraciones numba-accelerated via NumPy). Retorna `ResultadoAnalisis` con μ, σ, P(subida), dirección. | ~240 |
| `escaner_mercados.py` | Descubre activos abiertos combinando `get_all_ACTIVES_OPCODE()` + `get_all_open_time()`. Filtra por tipo de mercado (binary, turbo, digital, forex, crypto). | ~162 |
| `generarPDF.py` | Genera reportes PDF corporativos con KPIs (ROI, Win Rate), tabla de transacciones auditadas con estilo cebra y disclaimer de riesgo. Usa `fpdf2`. | ~361 |
| `veriffy_user.py` | Script de diagnóstico: verifica credenciales IQ Option y conectividad WebSocket. | ~35 |
| `iq_option_first.py` | Prototipo legacy con señales aleatorias (3 ciclos, EURUSD-OTC). Conservado como referencia. | ~93 |
| `requirements.txt` | Dependencias: numpy, pandas, fpdf2, customtkinter, matplotlib, mplfinance, iqoptionapi. | 6 paquetes |
| `user.py.example` | Template de credenciales. **El archivo real `user.py` está en `.gitignore` y NUNCA se sube al repositorio.** | 2 líneas |

## Flujo de operación

```
1. INICIO
   └─► dashboard.py se ejecuta
       └─► Conexión WebSocket a IQ Option (hilo secundario, no bloquea GUI)

2. AUTENTICACIÓN DOBLE
   ├─► IQ Option: email + password (desde user.py)
   └─► Servidor Maestro: modal CTkInputDialog solicita código de sala
       ├─► Código ingresado → _conectar_al_maestro() → UI habilitada
       └─► Sin código (cancelar) → Modo standalone → UI habilitada igual

3. OPERACIÓN (dos modos simultáneos)
   ├─► MANUAL: botones CALL/PUT → _ejecutar_orden_manual() → api.buy() → check_win_v3()
   └─► AUTOMÁTICO: toggle bot → _bot_worker() llama a iq_option.ejecutar_bot_completo()
       └─► Bucle de horizonte=50 ciclos:
           1. Descarga 1000 velas via api.get_candles()
           2. MotorMonteCarlo.analizar(precios) → dirección CALL/PUT
           3. api.buy() → api.check_win_v3()
           4. Guardianes de riesgo: Stop Loss / Take Profit

4. CIERRE
   └─► _on_close(): detiene hilos, cierra WebSocket, libera matplotlib, genera PDF
```

## Motor cuantitativo — Detalle técnico

```
Modelo: Movimiento Browniano Geométrico (GBM)

  S_T = S_0 · exp[(μ − ½σ²)Δt + σ·√Δt·Z]

Donde:
  μ  = Drift estimado vía EWMA (span=5, ventana=30) sobre retornos logarítmicos
  σ  = Volatilidad global — desviación estándar de retornos log
  Z  ~ N(0,1) — 50,000 muestras aleatorias vectorizadas (numpy.random.standard_normal)

Fórmula EWMA recursiva:
  EWMA_0 = r_0
  EWMA_t = α · r_t + (1 − α) · EWMA_{t−1}
  donde α = 2/(span + 1) = 2/6 ≈ 0.333

Decisión:
  P(subida) = media(precios_simulados > precio_actual)
  Si P(subida) > 0.5 → CALL (compra)
  Si P(subida) ≤ 0.5 → PUT (venta)
```

## Gestión de riesgo

| Parámetro | Default | Descripción |
|---|---|---|
| Inversión fija | $4 USD | Monto fijo por operación (mínimo del broker) |
| Stop Loss | 1.00% | Límite de pérdida sobre capital inicial |
| Take Profit | 0.50% | Objetivo de ganancia sobre capital inicial |
| Expiración | 1 min | Duración del contrato binario |
| Horizonte | 50 ops | Máximo de operaciones por sesión |
| Velas históricas | 1000 | Muestra para estimar volatilidad |
| Simulaciones MC | 50,000 | Iteraciones de Monte Carlo |
| EWMA span | 5 | Decaimiento exponencial del drift |

## Conexión al Servidor Maestro (stub actual)

El método `_conectar_al_maestro()` en `dashboard.py:435` es un cascarón listo para implementación:

```python
def _conectar_al_maestro(self, codigo: str) -> None:
    print(f"[CLIENTE] Conectando al Servidor Maestro con código: {codigo}...")
    # STUB: Aquí se implementará la lógica real de conexión
    # Futuro: ZeroMQ SUB → connect(tcp://maestro_ip:5555) → subscribe
    self.maestro_verificado = True
    self._habilitar_ui_completo()
```

Implementación prevista con ZeroMQ:
```python
import zmq, json

ctx = zmq.Context()
socket = ctx.socket(zmq.SUB)
socket.connect(f"tcp://{IP_MAESTRO}:5555")
socket.setsockopt_string(zmq.SUBSCRIBE, "")

# Recibir señales del maestro en un hilo dedicado
while True:
    msg = json.loads(socket.recv_string())
    if msg["type"] == "signal":
        ejecutar_orden_remota(msg["accion"], msg["activo"])
```

## Instalación y ejecución

```bash
# 1. Clonar el repositorio
git clone https://github.com/TU_USUARIO/IQOption-Trading-Analytics.git
cd IQOption-Trading-Analytics/App_Cliente_Trader

# 2. Configurar credenciales
cp user.py.example user.py
nano user.py  # Editar EMAIL y PASSWORD con tus credenciales de IQ Option

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Verificar conexión al broker (opcional)
python veriffy_user.py

# 5. Ejecutar el dashboard
python dashboard.py
```

## Dependencias

| Paquete | Uso |
|---|---|
| `numpy` | Cálculo vectorizado para Monte Carlo |
| `pandas` | Estructuras de datos OHLCV |
| `fpdf2` | Generación de reportes PDF |
| `customtkinter` | Framework GUI moderna (Dark Mode nativo) |
| `matplotlib` | Backend de renderizado de gráficos |
| `mplfinance` | Gráficos de velas financieras (candlestick) |
| `iqoptionapi` | API WebSocket IQ Option (fork comunitario) |

---

*Sistema desarrollado como proyecto final de Tecnología de la Información — Universidad Nacional de San Agustín, Arequipa, Perú. Las operaciones de trading conllevan riesgos financieros significativos. Este software tiene fines educativos y de investigación.*
