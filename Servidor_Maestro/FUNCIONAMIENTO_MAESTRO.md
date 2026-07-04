# Funcionamiento y Ejecución del Servidor Maestro (Controlador ZMQ)

## Descripción General

El **Servidor Maestro** ahora funciona como un orquestador central que se comunica con múltiples instancias del **Cliente Trader** en una red distribuida. Se ha implementado utilizando **ZeroMQ**, que es una librería de mensajería asíncrona de alto rendimiento, ideal para este tipo de arquitecturas.

La arquitectura de red se compone de 3 canales principales:
1. **Canal de Autenticación (Puerto 5556 - REP/REQ):** Utilizado por los clientes para conectarse inicial y de forma segura utilizando el "Código de Sala".
2. **Canal de Broadcast (Puerto 5555 - PUB/SUB):** El servidor usa este canal para enviar instrucciones globales a todos los clientes al mismo tiempo (ej. "Cambiar el algoritmo a EMA Cross").
3. **Canal de Mensajería Bidireccional (Puerto 5557 - ROUTER/DEALER):** Utilizado para comunicación asíncrona y directa. El servidor envía comandos a un cliente específico (ej. "Envíame tu reporte de métricas actual") y el cliente responde enviando sus operaciones a través del mismo canal.

---

## Archivos Principales

1. **`Servidor_Maestro/servidor_central.py`**: El código completo del nodo central. Contiene una interfaz gráfica oscura (CustomTkinter) desde la que se pueden gestionar los clientes conectados, solicitar reportes y enviar comandos de cambio de algoritmo.
2. **`Cliente_Trader/cliente_zmq.py`**: El script de red que se ejecuta del lado del cliente en un hilo (Thread) separado, escuchando ininterrumpidamente las instrucciones del Servidor Maestro.
3. **`Cliente_Trader/dashboard.py`**: Interfaz del cliente, actualizada para integrar la instancia de `cliente_zmq.py`, enviar reportes al maestro, y reaccionar automáticamente a los cambios de algoritmo.

---

## Requisitos y Preparación

Antes de poder iniciar el Servidor Maestro, asegúrate de instalar las dependencias necesarias. En la carpeta `Servidor_Maestro`, hemos creado un archivo de requisitos:

```bash
cd Servidor_Maestro
pip install -r requirements_server.txt
```

Esto instalará paquetes esenciales como `pyzmq` (ZeroMQ), `customtkinter`, `pandas` y `fpdf2`.

---

## Cómo Ejecutar y Probar el Sistema

### 1. Iniciar el Servidor Maestro
Abre una terminal, ubícate en la carpeta del servidor y ejecuta el script central:
```bash
cd Servidor_Maestro
python servidor_central.py
```
Aparecerá el panel del "NODO MAESTRO". En la parte lateral izquierda, notarás que se ha generado un **CÓDIGO DE SALA** (por ejemplo: `8KF71P0L`). 

### 2. Conectar los Clientes (Nodos)
Abre otra terminal (o varias, si quieres simular múltiples clientes), ubícate en la carpeta del cliente e inicia el dashboard:
```bash
cd Cliente_Trader
python dashboard.py
```
Al arrancar el cliente, aparecerá una ventana emergente ("CONEXION A SERVIDOR MAESTRO"). 
- En el campo, ingresa el **CÓDIGO DE SALA** que generó el Servidor Maestro.
- Haz clic en **CONECTAR AL MAESTRO**.

### 3. Verificar la Sesión
En el panel del **Servidor Maestro**, observarás que aparece un nuevo registro en la lista de "CLIENTES CONECTADOS" con el nombre del PC y un estado de `● Conectado`. Además, en la consola de logs verás el aviso de autenticación exitosa.

---

## Funcionalidades del Servidor Maestro

### 1. Cambio de Algoritmo Global
En la interfaz del maestro, en el panel izquierdo de **COMANDOS GLOBALES**, selecciona un algoritmo del menú desplegable (por ejemplo, `bollinger_bands`) y presiona **CAMBIAR ALGORITMO (TODOS)**.
- **Lo que sucede:** El servidor publica el comando a través del socket PUB. Todos los clientes conectados escuchan, y su interfaz de forma automática cambiará el "Algoritmo de Trading" al seleccionado.

### 2. Descarga de Reportes (Métricas Unitarias o Consolidadas)
El Servidor Maestro tiene la capacidad de pedir el informe de operaciones y estado actual de cualquier cliente sin interrumpir su funcionamiento.

- **Reporte Individual:** En la lista de "CLIENTES CONECTADOS", verás un botón **Descargar Reporte** junto a cada cliente. Al presionarlo:
  1. El servidor envía una señal privada (vía ROUTER) a ese cliente específico.
  2. El cliente reacciona empaquetando todas las métricas de su sesión (su historial de operaciones).
  3. El cliente devuelve los datos al maestro.
  4. El maestro guarda los datos recibidos automáticamente como un archivo CSV en la carpeta `Servidor_Maestro/Reportes_Central/`.
  
- **Reporte Global:** En la barra izquierda, el botón **DESCARGAR REPORTE GLOBAL** envía una señal de "solicitud de métricas" a *todos* los clientes al mismo tiempo, los cuales enviarán sus reportes individuales al maestro en milisegundos.

### 3. Latido del Corazón (Ping/Timeout)
Los clientes ejecutan en segundo plano una rutina que envía periódicamente un "Ping" (cada 5 segundos) al Maestro. Si el Servidor Maestro no recibe un ping de un cliente en más de 15 segundos, lo marca automáticamente como "Desconectado" y lo elimina de la lista de sesiones.
