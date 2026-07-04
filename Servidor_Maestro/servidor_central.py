import customtkinter as ctk
import threading
import time
import json
import zmq
import secrets
import string
from datetime import datetime
import pandas as pd
import os
import generarPDF

# ---------------------------------------------------------------------------
# CONSTANTES Y COLORES (Estilo oscuro)
# ---------------------------------------------------------------------------
BG = "#121214"
CARD = "#1E1E24"
BORDER = "#2C2C35"
GREEN = "#00B074"
RED = "#FF3B30"
WHITE = "#FFFFFF"
MUTED = "#8E8E93"
BLUE = "#0052CC"

class ServidorMaestroGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NODO MAESTRO - Controlador de Copy Trading")
        self.geometry("1200x800")
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")
        
        self.codigo_sala = self._generar_codigo_sala()
        self.clientes_conectados = {}  # {cliente_id: {"ip": ip, "last_ping": time, "status": "activo"}}
        self.servidor_activo = False
        
        self.operaciones_globales = [] # Para el reporte global
        
        # ZMQ Context
        self.ctx = zmq.Context()
        self.socket_pub = None
        self.socket_rep = None
        self.socket_router = None
        
        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Iniciar servidor
        self._iniciar_servidor()

    def _generar_codigo_sala(self, longitud=8):
        alfabeto = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alfabeto) for _ in range(longitud))
        
    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1, minsize=320)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)
        
        # SIDEBAR
        sb = ctk.CTkFrame(self, fg_color=CARD, border_color=BORDER, border_width=1)
        sb.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        sb.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(sb, text="NODO MAESTRO", font=ctk.CTkFont(size=20, weight="bold"), text_color=BLUE).grid(row=0, column=0, pady=(20, 5), padx=20)
        ctk.CTkLabel(sb, text="Controlador Distribuidor ZMQ", font=ctk.CTkFont(size=12), text_color=MUTED).grid(row=1, column=0, pady=(0, 20), padx=20)
        
        # Info Sala
        cb = ctk.CTkFrame(sb, fg_color=BG, border_color=BORDER, border_width=1)
        cb.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 20))
        cb.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cb, text="CÓDIGO DE SALA", font=ctk.CTkFont(size=11, weight="bold"), text_color=MUTED).grid(row=0, column=0, pady=(10, 0))
        ctk.CTkLabel(cb, text=self.codigo_sala, font=ctk.CTkFont(size=24, weight="bold"), text_color=GREEN).grid(row=1, column=0, pady=(0, 10))
        
        # Controles Globales
        frm = ctk.CTkScrollableFrame(sb, fg_color="transparent")
        frm.grid(row=3, column=0, sticky="nsew", padx=15)
        frm.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(3, weight=1)
        
        ctk.CTkLabel(frm, text="COMANDOS GLOBALES", text_color=WHITE, font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(10, 5))
        
        ctk.CTkLabel(frm, text="Algoritmo", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=1, column=0, sticky="w")
        self.cmb_algo = ctk.CTkComboBox(frm, values=["montecarlo", "ema_cross", "rsi_divergence", "bollinger_bands"])
        self.cmb_algo.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frm, text="Cuenta", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=3, column=0, sticky="w")
        self.cmb_cuenta = ctk.CTkComboBox(frm, values=["PRACTICA (Demo)", "REAL (Riesgo)"])
        self.cmb_cuenta.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frm, text="Inversión ($)", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=5, column=0, sticky="w")
        self.ent_inv = ctk.CTkEntry(frm); self.ent_inv.insert(0, "4")
        self.ent_inv.grid(row=6, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frm, text="Stop Loss (%)", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=7, column=0, sticky="w")
        self.ent_sl = ctk.CTkEntry(frm); self.ent_sl.insert(0, "1.00")
        self.ent_sl.grid(row=8, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frm, text="Take Profit (%)", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=9, column=0, sticky="w")
        self.ent_tp = ctk.CTkEntry(frm); self.ent_tp.insert(0, "0.50")
        self.ent_tp.grid(row=10, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkLabel(frm, text="Expiración (min)", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=11, column=0, sticky="w")
        self.ent_exp = ctk.CTkEntry(frm); self.ent_exp.insert(0, "1")
        self.ent_exp.grid(row=12, column=0, sticky="ew", pady=(0, 10))
        
        ctk.CTkButton(frm, text="APLICAR A TODOS", fg_color=BLUE, hover_color="#003D99", 
                      command=self._cmd_aplicar_global).grid(row=13, column=0, sticky="ew", pady=(10, 20))
                      
        ctk.CTkButton(sb, text="DESCARGAR REPORTE GLOBAL", fg_color=GREEN, hover_color="#008E5D", 
                      command=self._cmd_solicitar_reporte_global).grid(row=4, column=0, sticky="ew", padx=15, pady=(10, 10))
        
        # MAIN AREA
        mn = ctk.CTkFrame(self, fg_color="transparent")
        mn.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        mn.grid_columnconfigure(0, weight=1)
        mn.grid_rowconfigure(0, weight=1)
        mn.grid_rowconfigure(1, weight=1)
        
        # Panel Clientes
        panel_clientes = ctk.CTkFrame(mn, fg_color=CARD, border_color=BORDER, border_width=1)
        panel_clientes.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        panel_clientes.grid_columnconfigure(0, weight=1)
        panel_clientes.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(panel_clientes, text="CLIENTES CONECTADOS", font=ctk.CTkFont(size=14, weight="bold"), text_color=WHITE).grid(row=0, column=0, sticky="w", padx=15, pady=10)
        
        self.scroll_clientes = ctk.CTkScrollableFrame(panel_clientes, fg_color="transparent")
        self.scroll_clientes.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.scroll_clientes.grid_columnconfigure(0, weight=2)
        self.scroll_clientes.grid_columnconfigure(1, weight=1)
        self.scroll_clientes.grid_columnconfigure(2, weight=1)
        self.scroll_clientes.grid_columnconfigure(3, weight=1)
        self.scroll_clientes.grid_columnconfigure(4, weight=1)
        
        # Log Console
        lf = ctk.CTkFrame(mn, fg_color=CARD, border_color=BORDER, border_width=1)
        lf.grid(row=1, column=0, sticky="nsew")
        lf.grid_columnconfigure(0, weight=1); lf.grid_rowconfigure(0, weight=1)
        self.tb_logs = ctk.CTkTextbox(lf, fg_color="transparent", text_color=WHITE, font=ctk.CTkFont(family="Courier", size=12), wrap="word")
        self.tb_logs.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.tb_logs.configure(state="disabled")

    def log(self, level, msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}\n"
        self.tb_logs.configure(state="normal")
        self.tb_logs.insert("end", line)
        self.tb_logs.see("end")
        self.tb_logs.configure(state="disabled")

    def _iniciar_servidor(self):
        self.servidor_activo = True
        
        # PUB - Broadcast de señales/comandos (Puerto 5555)
        self.socket_pub = self.ctx.socket(zmq.PUB)
        self.socket_pub.bind("tcp://*:5555")
        
        # REP - Autenticación inicial (Puerto 5556)
        self.socket_rep = self.ctx.socket(zmq.REP)
        self.socket_rep.bind("tcp://*:5556")
        
        # ROUTER - Mensajería directa (ej. recibir reportes) (Puerto 5557)
        self.socket_router = self.ctx.socket(zmq.ROUTER)
        self.socket_router.bind("tcp://*:5557")
        
        self.log("INFO", f"Servidor ZMQ Iniciado.")
        self.log("INFO", f"Código de Sala: {self.codigo_sala}")
        self.log("INFO", f"Puertos: PUB(5555), REP(5556), ROUTER(5557)")
        
        threading.Thread(target=self._worker_rep_auth, daemon=True).start()
        threading.Thread(target=self._worker_router, daemon=True).start()
        threading.Thread(target=self._worker_monitor, daemon=True).start()

    def _worker_rep_auth(self):
        while self.servidor_activo:
            try:
                # Polling for non-blocking exit
                if self.socket_rep.poll(1000):
                    msg = self.socket_rep.recv_json()
                    if msg.get("type") == "auth":
                        codigo = msg.get("codigo")
                        cliente_id = msg.get("cliente_id")
                        if codigo == self.codigo_sala:
                            self.clientes_conectados[cliente_id] = {
                                "last_ping": time.time(),
                                "status": "conectado"
                            }
                            self.socket_rep.send_json({"type": "auth_response", "status": "OK", "sala": self.codigo_sala})
                            self.log("OK", f"Cliente Autenticado: {cliente_id}")
                            self.after(0, self._actualizar_ui_clientes)
                        else:
                            self.socket_rep.send_json({"type": "auth_response", "status": "DENIED"})
                            self.log("ERROR", f"Fallo autenticación. ID: {cliente_id}, Código: {codigo}")
            except Exception as e:
                pass

    def _worker_router(self):
        while self.servidor_activo:
            try:
                if self.socket_router.poll(1000):
                    parts = self.socket_router.recv_multipart()
                    identidad = parts[0]
                    payload_bytes = parts[-1]
                    try:
                        msg = json.loads(payload_bytes.decode('utf-8'))
                        cliente_id = msg.get("cliente_id")
                        
                        if cliente_id in self.clientes_conectados:
                            self.clientes_conectados[cliente_id]["last_ping"] = time.time()
                            self.clientes_conectados[cliente_id]["identidad"] = identidad
                            
                            if msg.get("type") == "ping":
                                pass
                            elif msg.get("type") == "report_response":
                                self.log("OK", f"Reporte recibido de {cliente_id}. Procesando...")
                                self._generar_reporte_cliente(cliente_id, msg.get("operaciones", []))
                    except Exception as e:
                        self.log("ERROR", f"Error procesando mensaje ROUTER: {e}")
            except Exception as e:
                pass

    def _worker_monitor(self):
        while self.servidor_activo:
            time.sleep(5)
            # Limpiar desconectados (timeout > 15s)
            now = time.time()
            cambios = False
            to_remove = []
            for cid, info in self.clientes_conectados.items():
                if now - info["last_ping"] > 15:
                    to_remove.append(cid)
                    cambios = True
            
            for cid in to_remove:
                del self.clientes_conectados[cid]
                self.log("ALERTA", f"Cliente Desconectado (Timeout): {cid}")
                
            if cambios:
                self.after(0, self._actualizar_ui_clientes)

    def _actualizar_ui_clientes(self):
        for widget in self.scroll_clientes.winfo_children():
            widget.destroy()
            
        row = 0
        for cid, info in self.clientes_conectados.items():
            f = ctk.CTkFrame(self.scroll_clientes, fg_color=BG, border_color=BORDER, border_width=1)
            f.grid(row=row, column=0, columnspan=5, sticky="ew", pady=5)
            f.grid_columnconfigure(0, weight=2)
            
            ctk.CTkLabel(f, text=cid, font=ctk.CTkFont(weight="bold"), text_color=WHITE).grid(row=0, column=0, padx=10, pady=10, sticky="w")
            
            ctk.CTkLabel(f, text="● Conectado", text_color=GREEN).grid(row=0, column=1, padx=10)
            
            btn_cfg = ctk.CTkButton(f, text="⚙ Configurar", fg_color=BLUE, hover_color="#003D99", width=100, height=24,
                                    command=lambda c=cid: self._abrir_modal_configurar(c))
            btn_cfg.grid(row=0, column=2, padx=5, pady=10)
            
            btn_rep = ctk.CTkButton(f, text="Descargar PDF", fg_color=BORDER, hover_color="#3C3C47", width=120, height=24,
                                    command=lambda c=cid: self._cmd_solicitar_reporte_individual(c))
            btn_rep.grid(row=0, column=3, padx=5, pady=10)
            
            btn_kick = ctk.CTkButton(f, text="[ X ] Desconectar", fg_color=RED, hover_color="#D8231B", width=120, height=24,
                                     command=lambda c=cid: self._cmd_desconectar(c))
            btn_kick.grid(row=0, column=4, padx=5, pady=10)
            
            row += 1

    def _abrir_modal_configurar(self, cliente_id):
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Configurar: {cliente_id}")
        dlg.geometry("300x480")
        dlg.configure(fg_color=CARD)
        dlg.transient(self)
        dlg.resizable(False, False)
        
        ctk.CTkLabel(dlg, text="PARÁMETROS DEL CLIENTE", font=ctk.CTkFont(size=14, weight="bold"), text_color=WHITE).pack(pady=(15, 15))
        
        # Campos
        ctk.CTkLabel(dlg, text="Algoritmo", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        c_algo = ctk.CTkComboBox(dlg, values=["montecarlo", "ema_cross", "rsi_divergence", "bollinger_bands"])
        c_algo.pack(fill="x", padx=20, pady=(0, 10))
        
        ctk.CTkLabel(dlg, text="Cuenta", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        c_cuenta = ctk.CTkComboBox(dlg, values=["PRACTICA (Demo)", "REAL (Riesgo)"])
        c_cuenta.pack(fill="x", padx=20, pady=(0, 10))
        
        ctk.CTkLabel(dlg, text="Inversión ($)", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        e_inv = ctk.CTkEntry(dlg); e_inv.insert(0, "4")
        e_inv.pack(fill="x", padx=20, pady=(0, 10))
        
        ctk.CTkLabel(dlg, text="Stop Loss (%)", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        e_sl = ctk.CTkEntry(dlg); e_sl.insert(0, "1.00")
        e_sl.pack(fill="x", padx=20, pady=(0, 10))
        
        ctk.CTkLabel(dlg, text="Take Profit (%)", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        e_tp = ctk.CTkEntry(dlg); e_tp.insert(0, "0.50")
        e_tp.pack(fill="x", padx=20, pady=(0, 10))
        
        ctk.CTkLabel(dlg, text="Expiración (min)", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        e_exp = ctk.CTkEntry(dlg); e_exp.insert(0, "1")
        e_exp.pack(fill="x", padx=20, pady=(0, 20))
        
        def enviar_cfg():
            msg = {
                "type": "cmd_direct",
                "action": "cambiar_parametros",
                "parametros": {
                    "algoritmo": c_algo.get(),
                    "cuenta": c_cuenta.get(),
                    "inv": e_inv.get(),
                    "sl": e_sl.get(),
                    "tp": e_tp.get(),
                    "exp": e_exp.get()
                }
            }
            self._send_direct(cliente_id, msg)
            self.log("INFO", f"Parámetros enviados a {cliente_id}")
            dlg.destroy()
            
        ctk.CTkButton(dlg, text="APLICAR Y ENVIAR", fg_color=BLUE, hover_color="#003D99", command=enviar_cfg).pack(fill="x", padx=20)

    def _cmd_aplicar_global(self):
        msg = {
            "type": "cmd_global",
            "action": "cambiar_parametros",
            "parametros": {
                "algoritmo": self.cmb_algo.get(),
                "cuenta": self.cmb_cuenta.get(),
                "inv": self.ent_inv.get(),
                "sl": self.ent_sl.get(),
                "tp": self.ent_tp.get(),
                "exp": self.ent_exp.get()
            }
        }
        self.socket_pub.send_json(msg)
        self.log("INFO", f"Comando Global: Parámetros cambiados para todos.")

    def _cmd_desconectar(self, cliente_id):
        msg = {
            "type": "cmd_direct",
            "action": "desconectar"
        }
        self._send_direct(cliente_id, msg)
        self.log("ALERTA", f"Comando de Desconexión enviado a {cliente_id}")
        # Eliminarlo de la interfaz local
        if cliente_id in self.clientes_conectados:
            del self.clientes_conectados[cliente_id]
            self._actualizar_ui_clientes()

    def _cmd_solicitar_reporte_global(self):
        self.operaciones_globales = [] # reset global ops
        msg = {
            "type": "cmd_global",
            "action": "solicitar_reporte_para_global"
        }
        self.socket_pub.send_json(msg)
        self.log("INFO", f"Solicitando reportes a todos para PDF Global...")
        
        # Programar un timeout para generar el PDF global después de esperar respuestas
        self.after(3000, self._generar_reporte_global_pdf)

    def _cmd_solicitar_reporte_individual(self, cliente_id):
        msg = {
            "type": "cmd_direct",
            "action": "solicitar_reporte"
        }
        self._send_direct(cliente_id, msg)
        self.log("INFO", f"Solicitado reporte individual a {cliente_id}")

    def _send_direct(self, cliente_id, msg_dict):
        info = self.clientes_conectados.get(cliente_id)
        if info and "identidad" in info:
            try:
                self.socket_router.send_multipart([info["identidad"], b"", json.dumps(msg_dict).encode('utf-8')])
            except Exception as e:
                self.log("ERROR", f"Fallo envío directo: {e}")

    def _generar_reporte_cliente(self, cliente_id, operaciones):
        # Cuando piden para el global, también llega aquí (o podríamos separarlo)
        # Vamos a guardar en CSV y generar un PDF con fpdf
        os.makedirs("Reportes_Central", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Acumular para el global
        self.operaciones_globales.extend(operaciones)
        
        if not operaciones:
            return # Sin operaciones, no generamos PDF individual
            
        # Generar PDF Individual
        datos = {
            "cuenta_id": cliente_id,
            "tipo_cuenta": "N/A",
            "fecha_inicio": operaciones[0].get("fecha", "N/A"),
            "fecha_fin": operaciones[-1].get("fecha", "N/A"),
            "x0": 0.0, "x_final": 0.0,
            "rendimiento": sum(op.get("profit", 0) for op in operaciones),
            "total_ops": len(operaciones),
            "ganadas": len([op for op in operaciones if "GANADA" in str(op.get("resultado", "")).upper()]),
            "perdidas": len([op for op in operaciones if "PERDIDA" in str(op.get("resultado", "")).upper()]),
            "empates": len([op for op in operaciones if "EMPATE" in str(op.get("resultado", "")).upper()]),
        }
        ruta_pdf = f"Reportes_Central/Reporte_{cliente_id}_{ts}.pdf"
        try:
            generarPDF.generar_reporte_pdf(datos, operaciones, ruta_pdf)
            self.log("OK", f"PDF Individual generado: {ruta_pdf}")
        except Exception as e:
            self.log("ERROR", f"Fallo al generar PDF Individual: {e}")

    def _generar_reporte_global_pdf(self):
        if not self.operaciones_globales:
            self.log("ALERTA", "No se recibieron operaciones para el reporte global.")
            return
            
        os.makedirs("Reportes_Central", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        ops = self.operaciones_globales
        datos = {
            "cuenta_id": "REPORTE GLOBAL (TODOS LOS NODOS)",
            "tipo_cuenta": "MULTI-NODO",
            "fecha_inicio": ops[0].get("fecha", "N/A"),
            "fecha_fin": ops[-1].get("fecha", "N/A"),
            "x0": 0.0, "x_final": 0.0,
            "rendimiento": sum(op.get("profit", 0) for op in ops),
            "total_ops": len(ops),
            "ganadas": len([op for op in ops if "GANADA" in str(op.get("resultado", "")).upper()]),
            "perdidas": len([op for op in ops if "PERDIDA" in str(op.get("resultado", "")).upper()]),
            "empates": len([op for op in ops if "EMPATE" in str(op.get("resultado", "")).upper()]),
        }
        ruta_pdf = f"Reportes_Central/Reporte_GLOBAL_{ts}.pdf"
        try:
            generarPDF.generar_reporte_pdf(datos, ops, ruta_pdf)
            self.log("OK", f"PDF GLOBAL generado con {len(ops)} operaciones: {ruta_pdf}")
        except Exception as e:
            self.log("ERROR", f"Fallo al generar PDF Global: {e}")


    def _on_close(self):
        self.servidor_activo = False
        self.destroy()

if __name__ == "__main__":
    app = ServidorMaestroGUI()
    app.mainloop()
