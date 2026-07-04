import zmq
import json
import threading
import time
import socket

class ClienteZMQ:
    def __init__(self, ip_maestro, codigo_sala, callback_comando=None, callback_log=None):
        self.ip_maestro = ip_maestro
        self.codigo_sala = codigo_sala
        self.cliente_id = f"Cliente-{socket.gethostname()}-{time.time()}"
        
        self.ctx = zmq.Context()
        self.activo = False
        
        self.callback_comando = callback_comando # (action, data)
        self.callback_log = callback_log
        
        self.socket_sub = None
        self.socket_req = None
        self.socket_dealer = None

    def log(self, level, msg):
        if self.callback_log:
            self.callback_log(level, f"[ZMQ] {msg}")
        else:
            print(f"[{level}] [ZMQ] {msg}")

    def iniciar(self):
        # Socket REQ para autenticacion
        self.socket_req = self.ctx.socket(zmq.REQ)
        self.socket_req.connect(f"tcp://{self.ip_maestro}:5556")
        
        self.log("INFO", f"Autenticando con Maestro ({self.ip_maestro}) - Código: {self.codigo_sala}")
        
        self.socket_req.send_json({
            "type": "auth",
            "codigo": self.codigo_sala,
            "cliente_id": self.cliente_id
        })
        
        if self.socket_req.poll(3000): # timeout de 3s
            resp = self.socket_req.recv_json()
            if resp.get("status") == "OK":
                self.log("OK", "Autenticación exitosa. Conectando canales PUB/SUB y DEALER/ROUTER...")
                self.activo = True
                self._iniciar_conexiones_persistentes()
                return True
            else:
                self.log("ERROR", "Autenticación denegada. Código de sala incorrecto.")
                return False
        else:
            self.log("ERROR", "Tiempo de espera agotado conectando al Servidor Maestro.")
            return False

    def _iniciar_conexiones_persistentes(self):
        # Socket SUB para recibir comandos globales
        self.socket_sub = self.ctx.socket(zmq.SUB)
        self.socket_sub.connect(f"tcp://{self.ip_maestro}:5555")
        self.socket_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        
        # Socket DEALER para comunicación asincrona bidireccional
        self.socket_dealer = self.ctx.socket(zmq.DEALER)
        # Identidad es importante para el ROUTER del maestro
        self.socket_dealer.setsockopt(zmq.IDENTITY, self.cliente_id.encode('utf-8'))
        self.socket_dealer.connect(f"tcp://{self.ip_maestro}:5557")
        
        threading.Thread(target=self._worker_sub, daemon=True).start()
        threading.Thread(target=self._worker_dealer, daemon=True).start()
        threading.Thread(target=self._worker_ping, daemon=True).start()

    def _worker_sub(self):
        while self.activo:
            try:
                if self.socket_sub.poll(1000):
                    msg = self.socket_sub.recv_json()
                    if msg.get("type") == "cmd_global":
                        self.log("INFO", f"Comando Global recibido: {msg.get('action')}")
                        if self.callback_comando:
                            self.callback_comando(msg.get("action"), msg)
            except Exception as e:
                pass

    def _worker_dealer(self):
        while self.activo:
            try:
                if self.socket_dealer.poll(1000):
                    # ZeroMQ multipart para DEALER es [vacio, msj] o solo [msj]
                    payload = self.socket_dealer.recv() 
                    # Probamos parsear
                    try:
                        msg = json.loads(payload.decode('utf-8'))
                        if msg.get("type") == "cmd_direct":
                            self.log("INFO", f"Comando Directo recibido: {msg.get('action')}")
                            if self.callback_comando:
                                self.callback_comando(msg.get("action"), msg)
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                pass

    def _worker_ping(self):
        while self.activo:
            time.sleep(5)
            try:
                ping_msg = {
                    "type": "ping",
                    "cliente_id": self.cliente_id
                }
                # DEALER no necesita vacio delante en send normal de string
                self.socket_dealer.send_string(json.dumps(ping_msg))
            except Exception:
                pass

    def enviar_reporte(self, operaciones):
        if self.activo and self.socket_dealer:
            try:
                msg = {
                    "type": "report_response",
                    "cliente_id": self.cliente_id,
                    "operaciones": operaciones
                }
                self.socket_dealer.send_string(json.dumps(msg))
                self.log("OK", "Reporte enviado al Servidor Maestro.")
            except Exception as e:
                self.log("ERROR", f"Fallo enviando reporte: {e}")

    def detener(self):
        self.activo = False
        if self.socket_sub: self.socket_sub.close()
        if self.socket_req: self.socket_req.close()
        if self.socket_dealer: self.socket_dealer.close()
