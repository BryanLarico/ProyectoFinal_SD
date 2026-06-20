# App Servidor Maestro — Nodo Controlador de Copy Trading

> **Estado actual:** Cascarón arquitectónico (v0.1.0). Las funciones de red son stubs listos para implementación con ZeroMQ.

## Visión general

El Servidor Maestro es el **cerebro central** del sistema de Copy Trading distribuido. Su función es coordinar múltiples nodos cliente (App_Cliente_Trader), autenticarlos mediante un código de sala criptográfico, y retransmitir las señales de trading para que todos los clientes operen de forma sincronizada.

```
┌──────────────────────────────────────────────────────────┐
│                  App_Servidor_Maestro                     │
│                                                           │
│  ┌──────────────────┐       ┌────────────────────────┐   │
│  │ servidor_central │       │     RED DE CLIENTES     │   │
│  │                  │       │                         │   │
│  │ • Código sala    │──┬───▶│  Cliente 1 (PC remota)  │   │
│  │ • Auth clientes  │  │    │  Cliente 2 (PC remota)  │   │
│  │ • Broadcast      │──┤    │  Cliente 3 (PC remota)  │   │
│  │ • Monitoreo      │  │    │  ...                    │   │
│  └──────────────────┘  │    └────────────────────────┘   │
│           │             │                                 │
│           ▼             │                                 │
│  ┌──────────────────┐   │                                 │
│  │ Motor Cuantitativo│  │ PUB/SUB ZeroMQ                 │
│  │ Monte Carlo GBM  │   │ tcp://0.0.0.0:5555             │
│  └──────────────────┘   │                                 │
└─────────────────────────┴─────────────────────────────────┘
```

## Estructura de archivos

| Archivo | Rol | Estado |
|---|---|---|
| `servidor_central.py` | Clase `ServidorMaestro` con stubs: código de sala, autenticación, broadcast de señales. | Cascarón funcional |
| `requirements_server.txt` | Dependencias mínimas (pyzmq, numpy). | Completo |

## API del cascarón

### `ServidorMaestro()`

Constructor. Inicializa el servidor con:
- `codigo_sala` — string vacío, se genera al iniciar
- `clientes` — lista de dicts con clientes autenticados
- `servidor_activo` — flag booleano

```python
servidor = ServidorMaestro()
```

### `generar_codigo_sala(longitud=8) -> str`

Genera un código aleatorio con entropía criptográfica (`secrets.choice`) usando letras mayúsculas y dígitos. Este código es el que el operador comparte con los clientes para autenticarse.

```python
codigo = servidor.generar_codigo_sala()
# → "A3K9M7X2"
```

### `iniciar_servidor() -> None`

**[STUB]** Simula el arranque. Imprime estado, código de sala e instrucciones.

En la implementación real:
- Creará un socket ZeroMQ **PUB** en `tcp://0.0.0.0:5555` para broadcast de señales
- Creará un socket ZeroMQ **REP** en `tcp://0.0.0.0:5556` para autenticación de clientes
- Iniciará hilos de escucha para cada socket
- Activarà heartbeat periódico para detectar desconexiones

### `detener_servidor() -> None`

**[STUB]** Simula la parada. Limpia la lista de clientes.

En la implementación real:
- Cerrará todos los sockets ZeroMQ
- Enviará señal de cierre a los clientes
- Liberará recursos de red

### `enviar_senal_global(accion: str, activo: str) -> None`

**[STUB]** Transmite una orden de trading a todos los clientes conectados.

```python
servidor.enviar_senal_global("CALL", "EURUSD-OTC")
# [STUB] >>> ENVIANDO SEÑAL GLOBAL >>> CALL | EURUSD-OTC
# [STUB] La señal se transmitiría a 2 cliente(s).
```

En la implementación real:
- Empaquetará la orden en JSON con todos los metadatos
- La publicará vía ZeroMQ PUB → todos los clientes SUB la reciben simultáneamente
- Incluirá: tipo de orden, activo, monto, expiración, timestamp

### `autenticar_cliente(codigo: str) -> bool`

**[STUB]** Compara el código recibido contra el código de sala.

```python
servidor.autenticar_cliente("A3K9M7X2")  # → True (coincide)
servidor.autenticar_cliente("WRONG123")   # → False
```

En la implementación real:
- Recibirá el código vía socket ZeroMQ REP
- Validará contra `self.codigo_sala`
- Registrará cliente autenticado con ID, timestamp y IP
- Responderá OK/DENIED al cliente

## Plan de construcción (roadmap)

### Fase 1 — Red ZeroMQ básica

Implementar comunicación PUB/SUB + REP/REQ real.

**Archivos a modificar:** `servidor_central.py`
**Archivos nuevos:** ninguno (el cliente ya tiene el stub `_conectar_al_maestro()`)
**Dependencia:** `pyzmq`

```python
# Fragmento de la implementación prevista
import zmq, json, threading

class ServidorMaestro:
    def iniciar_servidor(self):
        self.codigo_sala = self.generar_codigo_sala()
        self.ctx = zmq.Context()

        # Canal de broadcast (PUB)
        self.socket_pub = self.ctx.socket(zmq.PUB)
        self.socket_pub.bind(f"tcp://*:{self._puerto}")

        # Canal de autenticación (REP)
        self.socket_auth = self.ctx.socket(zmq.REP)
        self.socket_auth.bind(f"tcp://*:{self._puerto + 1}")

        # Hilo de autenticación
        self._hilo_auth = threading.Thread(target=self._loop_auth, daemon=True)
        self._hilo_auth.start()

    def enviar_senal_global(self, accion, activo):
        msg = json.dumps({
            "type": "signal", "accion": accion, "activo": activo,
            "inversion": self.inversion, "expiracion": self.expiracion,
            "timestamp": datetime.now().isoformat()
        })
        self.socket_pub.send_string(msg)
```

### Fase 2 — Panel de control del servidor

Agregar una interfaz para que el operador humano controle el servidor.

**Opciones de implementación:**
- **CustomTkinter** — mismo stack que el cliente, GUI nativa consistente
- **Flask + WebSocket** — panel web accesible desde navegador
- **Terminal interactiva** — comandos por consola con `cmd` o `prompt_toolkit`

### Fase 3 — Motor cuantitativo integrado

El servidor puede ejecutar su propia instancia de `MotorMonteCarlo` para:
- Generar las señales de trading centralizadamente
- O recibir señales de un cliente designado como "analista"
- Comparar señales de múltiples fuentes (consenso)

### Fase 4 — Monitoreo y persistencia

- Dashboard de estado: clientes conectados, balance, última operación
- Historial de señales enviadas con timestamp
- Base de datos SQLite para registro de sesiones
- Notificaciones de desconexión de clientes

## Protocolo de comunicación (diseño JSON)

### Señal de trading (Servidor → Clientes)

```json
{
  "type": "signal",
  "accion": "CALL",
  "activo": "EURUSD-OTC",
  "inversion": 4,
  "expiracion": 1,
  "mu": 0.000342,
  "sigma": 0.000891,
  "prob_subida": 0.6234,
  "timestamp": "2026-06-29T12:00:00"
}
```

### Autenticación (Cliente → Servidor)

```json
{
  "type": "auth",
  "codigo": "A3K9M7X2",
  "cliente_id": "PC-Trader-01"
}
```

### Respuesta de autenticación (Servidor → Cliente)

```json
{
  "type": "auth_response",
  "status": "OK",
  "sala": "A3K9M7X2",
  "timestamp": "2026-06-29T12:00:00"
}
```

### Heartbeat (bidireccional, cada 5s)

```json
{
  "type": "heartbeat",
  "timestamp": "2026-06-29T12:00:05"
}
```

## Prueba del cascarón

```bash
cd App_Servidor_Maestro
python servidor_central.py
```

**Sin dependencias externas** — solo usa `secrets`, `string`, `datetime` de la stdlib.

Salida esperada:
```
=======================================================
  PRUEBA DEL CASCARÓN — SERVIDOR MAESTRO CONTROLADOR
=======================================================

[1] Instancia creada: ServidorMaestro(codigo='', activo=False, clientes=0)

=======================================================
  SERVIDOR MAESTRO CONTROLADOR — Copy Trading System
=======================================================
  Estado:        ACTIVO
  Dirección:     tcp://0.0.0.0:5555
  Código Sala:   Z27PHYY4
  Clientes:      0
=======================================================

[STUB] Cliente #1 autenticado correctamente.
[STUB] Intento de autenticación fallido con código: WRONG123
[STUB] Cliente #2 autenticado correctamente.
[STUB] >>> ENVIANDO SEÑAL GLOBAL >>> CALL | EURUSD-OTC
[STUB] La señal se transmitiría a 2 cliente(s).
```

## Dependencias previstas

```bash
pip install -r requirements_server.txt
```

| Paquete | Fase | Uso |
|---|---|---|
| `pyzmq` | Fase 1 | ZeroMQ — mensajería distribuida PUB/SUB + REP/REQ |
| `numpy` | Fase 3 | Motor cuantitativo si corre en el servidor |
| *(stdlib)* | Todas | `secrets`, `threading`, `json`, `datetime` — sin dependencias externas |

---

*Sistema en desarrollo. Las funciones marcadas como [STUB] son cascarones arquitectónicos listos para recibir la implementación de red. Proyecto final — Tecnología de la Información, UNSA.*
