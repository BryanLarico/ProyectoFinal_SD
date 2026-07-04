# dashboard.py
# ====================================================================
# Panel de Control Tkinter — Paridad completa con dashboard_web.py
# Mismas funcionalidades, misma velocidad. Render nativo Canvas.
# ====================================================================

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from iqoptionapi.stable_api import IQ_Option

import generarPDF
import iq_option
import registro_operaciones
import user
from algoritmos import obtener_lista
import cliente_zmq

# ---------------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------------
BG = "#121214"
CARD = "#1E1E24"
BORDER = "#2C2C35"
GREEN = "#00B074"
RED = "#FF3B30"
WHITE = "#FFFFFF"
MUTED = "#8E8E93"
BLUE = "#0052CC"

# ---------------------------------------------------------------------------
# MICRO-GRAFICO P&L EN CANVAS TKINTER (sin matplotlib)
# ---------------------------------------------------------------------------
class _PnlSparkline:
    def __init__(self, master):
        self.cv = tk.Canvas(master, bg=CARD, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True, padx=0, pady=0)
        self._data: List[float] = [0.0]
        self._simbolo = "$"

    def push(self, val, simbolo="$"):
        self._simbolo = simbolo
        self._data.append(val)
        if len(self._data) > 120:
            self._data = self._data[-120:]
        self._redraw()

    def _redraw(self):
        cv = self.cv; cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 30 or h < 30 or len(self._data) < 2:
            if len(self._data) < 2:
                cv.create_text(w // 2, h // 2, text="Esperando operaciones...",
                               fill=MUTED, font=("Helvetica", 12))
            return
        mg = {"l": 65, "r": 20, "t": 30, "b": 35}
        cw, ch = w - mg["l"] - mg["r"], h - mg["t"] - mg["b"]
        if cw <= 0 or ch <= 0: return
        vals = self._data
        mn, mx = min(vals), max(vals)
        rng = mx - mn
        if rng == 0: rng = max(abs(mx) * 0.1, 0.01)
        mn -= rng * 0.1; mx += rng * 0.1; rng = mx - mn

        def xy(i, v):
            return (mg["l"] + (i / max(1, len(vals) - 1)) * cw,
                    mg["t"] + ch - ((v - mn) / rng) * ch)

        for frac in (0, 0.5, 1.0):
            gv = mn + rng * frac; _, gy = xy(0, gv)
            cv.create_line(mg["l"], gy, mg["l"] + cw, gy, fill=BORDER, dash=(2, 4), width=0.5)
            cv.create_text(mg["l"] - 5, gy, text=f"{self._simbolo}{gv:+.1f}", fill=MUTED, font=("Courier", 10), anchor="e")

        zy = xy(0, 0)[1]
        cv.create_line(mg["l"], zy, mg["l"] + cw, zy, fill=BORDER, width=1)
        color = GREEN if vals[-1] >= 0 else RED
        pts = [c for i, v in enumerate(vals) for c in xy(i, v)]
        if len(pts) >= 4: cv.create_line(*pts, fill=color, width=2, smooth=False)
        for i, v in enumerate(vals):
            x, y = xy(i, v); _, z = xy(i, 0)
            cv.create_line(x, y, x, z, fill=_blend(color, CARD, 0.12), width=2)
        lx, ly = xy(len(vals) - 1, vals[-1])
        cv.create_oval(lx - 5, ly - 5, lx + 5, ly + 5, fill=color, outline=color)
        cv.create_text(min(lx + 10, w - 50), ly - 12, text=f"{self._simbolo}{vals[-1]:+.2f}",
                       fill=color, font=("Helvetica", 12, "bold"), anchor="w")
        cv.create_text(mg["l"] + cw / 2, 12, text="RENDIMIENTO ACUMULADO (USD)",
                       fill=MUTED, font=("Helvetica", 11, "bold"))


def _blend(hex_color, bg_hex, alpha):
    r1, g1, b1 = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r2, g2, b2 = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
    return f"#{int(r1*alpha+r2*(1-alpha)):02x}{int(g1*alpha+g2*(1-alpha)):02x}{int(b1*alpha+b2*(1-alpha)):02x}"


# ---------------------------------------------------------------------------
# GRAFICO DONUT RECT NATIVO CANVAS
# ---------------------------------------------------------------------------
class _DonutChartCanvas(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg=CARD, highlightthickness=0, bd=0, **kwargs)
        self.ganadas = 0
        self.perdidas = 0
        self.empates = 0
        self.bind("<Configure>", lambda e: self.redraw())

    def update_data(self, ganadas, perdidas, empates):
        self.ganadas = ganadas
        self.perdidas = perdidas
        self.empates = empates
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 30 or h < 30: return

        # Titulo
        self.create_text(w // 2, 15, text="DISTRIBUCIÓN DE RESULTADOS", fill=MUTED, font=("Helvetica", 10, "bold"))

        total = self.ganadas + self.perdidas + self.empates
        if total == 0:
            self.create_text(w // 2, h // 2, text="Sin operaciones registradas", fill=MUTED, font=("Helvetica", 11))
            return

        cx, cy = w // 2, h // 2 + 10
        r = min(w, h - 50) // 2.8
        if r <= 10: r = 30

        slices = [
            (self.ganadas, GREEN, "G"),
            (self.perdidas, RED, "P"),
            (self.empates, MUTED, "E")
        ]

        start_angle = 0
        import math
        for val, color, label in slices:
            if val == 0: continue
            extent = (val / total) * 360.0
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=start_angle, extent=extent, fill=color, outline=CARD, width=1.5)
            if extent > 15:
                mid_angle = start_angle + extent / 2
                rad = math.radians(mid_angle)
                lx = cx + (r * 0.7) * math.cos(rad)
                ly = cy - (r * 0.7) * math.sin(rad)
                self.create_text(lx, ly, text=f"{val}", fill=WHITE, font=("Helvetica", 9, "bold"))
            start_angle += extent

        r_inner = r * 0.55
        self.create_oval(cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner, fill=CARD, outline="")

        leg = f"Ganadas: {self.ganadas} | Perdidas: {self.perdidas} | Empates: {self.empates}"
        self.create_text(w // 2, h - 18, text=leg, fill=WHITE, font=("Helvetica", 9, "bold"))


# ---------------------------------------------------------------------------
# GRAFICO BARRAS NATIVO CANVAS
# ---------------------------------------------------------------------------
class _BarChartCanvas(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg=CARD, highlightthickness=0, bd=0, **kwargs)
        self.por_activo = {}
        self.bind("<Configure>", lambda e: self.redraw())

    def update_data(self, por_activo):
        self.por_activo = por_activo
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 30 or h < 30: return

        self.create_text(w // 2, 15, text="PROFIT POR ACTIVO", fill=MUTED, font=("Helvetica", 10, "bold"))

        if not self.por_activo:
            self.create_text(w // 2, h // 2, text="Sin operaciones registradas", fill=MUTED, font=("Helvetica", 11))
            return

        mg = {"l": 55, "r": 15, "t": 35, "b": 35}
        cw, ch = w - mg["l"] - mg["r"], h - mg["t"] - mg["b"]
        if cw <= 0 or ch <= 0: return

        assets = list(self.por_activo.keys())[:6]
        values = [self.por_activo[a]["pnl"] for a in assets]

        mn, mx = min(values), max(values)
        if mn > 0: mn = 0.0
        if mx < 0: mx = 0.0
        rng = mx - mn
        if rng == 0: rng = 1.0
        mn -= rng * 0.05
        mx += rng * 0.05
        rng = mx - mn

        zy = mg["t"] + ch - ((0.0 - mn) / rng) * ch
        self.create_line(mg["l"], zy, mg["l"] + cw, zy, fill=BORDER, width=1.5)

        for frac in (0.0, 0.5, 1.0):
            gv = mn + rng * frac
            gy = mg["t"] + ch - ((gv - mn) / rng) * ch
            self.create_line(mg["l"], gy, mg["l"] + cw, gy, fill=BORDER, dash=(2, 4), width=0.5)
            self.create_text(mg["l"] - 5, gy, text=f"${gv:+.1f}", fill=MUTED, font=("Courier", 8), anchor="e")

        bar_width = (cw / len(assets)) * 0.6
        spacing = (cw / len(assets)) * 0.4
        start_x = mg["l"] + spacing / 2

        for i, (asset, val) in enumerate(zip(assets, values)):
            bx = start_x + i * (bar_width + spacing)
            by = mg["t"] + ch - ((val - mn) / rng) * ch
            color = GREEN if val >= 0 else RED

            if val >= 0:
                self.create_rectangle(bx, by, bx + bar_width, zy, fill=color, outline="")
                self.create_text(bx + bar_width/2, by - 8, text=f"${val:.1f}", fill=GREEN, font=("Helvetica", 8, "bold"))
            else:
                self.create_rectangle(bx, zy, bx + bar_width, by, fill=color, outline="")
                self.create_text(bx + bar_width/2, by + 8, text=f"${val:.1f}", fill=RED, font=("Helvetica", 8, "bold"))

            asset_short = asset.split("-")[0]
            self.create_text(bx + bar_width/2, h - 15, text=asset_short, fill=WHITE, font=("Helvetica", 9))


# ====================================================================
# DASHBOARD
# ====================================================================
class MasterQuantDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NODO CLIENTE QUANT - Panel de Control [Copiado de Operaciones]")
        self.geometry("1300x850")
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.api: Optional[IQ_Option] = None
        self.api_connected = False
        self.activos_disponibles: List[Dict[str, Any]] = []
        self.activo_seleccionado = "EURUSD-OTC"
        self._cerrando = False

        self.maestro_verificado = False
        self.codigo_maestro = ""
        self.cliente_zmq = None

        self.ui_queue: queue.Queue = queue.Queue()
        self.bot_threads: List[threading.Thread] = []
        self.bot_stop_event = threading.Event()

        self.bot_activo = False
        self._bots_pendientes = 0
        self._simbolo_moneda = "$"
        self.total_ops = 0; self.ganadas = 0; self.perdidas = 0; self.empates = 0
        self.saldo_inicial = 0.0
        self.historial_operaciones: List[Dict[str, Any]] = []
        self.fecha_inicio_sesion = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self._pnl_acumulado = 0.0

        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._procesar_cola)
        self.write_log("INFO", "Iniciando autenticacion...")
        threading.Thread(target=self._conectar_broker_async, daemon=True).start()

    # ================================================================
    # UI
    # ================================================================
    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=1, minsize=320)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(0, weight=1)

        # --- SIDEBAR ---
        sb = ctk.CTkFrame(self, fg_color=CARD, border_color=BORDER, border_width=1)
        sb.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        sb.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sb, text="NODO CLIENTE QUANT", font=ctk.CTkFont(size=20, weight="bold"), text_color=GREEN).grid(row=0, column=0, pady=(20, 5), padx=20)
        ctk.CTkLabel(sb, text="Trading Algoritmico & Monte Carlo", font=ctk.CTkFont(size=12), text_color=MUTED).grid(row=1, column=0, pady=(0, 20), padx=20)

        cb = ctk.CTkFrame(sb, fg_color=BG, border_color=BORDER, border_width=1)
        cb.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 20))
        cb.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cb, text=f"Usuario: {user.EMAIL}", font=ctk.CTkFont(size=11), text_color=MUTED).grid(row=0, column=0, pady=10, padx=10)
        self.lbl_maestro = ctk.CTkLabel(cb, text="Maestro: Modo Autonomo", font=ctk.CTkFont(size=10), text_color=MUTED)
        self.lbl_maestro.grid(row=1, column=0, pady=(0, 10), padx=10)

        frm = ctk.CTkFrame(sb, fg_color="transparent")
        frm.grid(row=3, column=0, sticky="nsew", padx=15)
        frm.grid_columnconfigure(0, weight=1)

        self._lbl(frm, 0, "Activo Principal")
        self.cb_activo = ctk.CTkComboBox(frm, values=[self.activo_seleccionado])
        self.cb_activo.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        self._lbl(frm, 2, "Algoritmo de Trading")
        algos = obtener_lista()
        self.cmb_algoritmo = ctk.CTkComboBox(frm, values=[a["nombre"] for a in algos])
        self.cmb_algoritmo.set(algos[0]["nombre"])
        self.cmb_algoritmo.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self._lbl(frm, 4, "Tipo de Cuenta")
        self.cmb_cuenta = ctk.CTkComboBox(frm, values=["PRACTICA (Demo)", "REAL (Riesgo)"], command=self._on_cuenta_changed)
        self.cmb_cuenta.set("PRACTICA (Demo)")
        self.cmb_cuenta.grid(row=5, column=0, sticky="ew", pady=(0, 10))

        self._lbl(frm, 6, "Inversion Fija (USD)")
        self.ent_inv = ctk.CTkEntry(frm, placeholder_text="4"); self.ent_inv.insert(0, "4")
        self.ent_inv.grid(row=7, column=0, sticky="ew", pady=(0, 10))

        self._lbl(frm, 8, "Limite de Perdida (%)")
        self.ent_sl = ctk.CTkEntry(frm, placeholder_text="1.00"); self.ent_sl.insert(0, "1.00")
        self.ent_sl.grid(row=9, column=0, sticky="ew", pady=(0, 10))

        self._lbl(frm, 10, "Toma de Ganancia (%)")
        self.ent_tp = ctk.CTkEntry(frm, placeholder_text="0.50"); self.ent_tp.insert(0, "0.50")
        self.ent_tp.grid(row=11, column=0, sticky="ew", pady=(0, 10))

        self._lbl(frm, 12, "Expiracion (min)")
        self.ent_exp = ctk.CTkEntry(frm, placeholder_text="1"); self.ent_exp.insert(0, "1")
        self.ent_exp.grid(row=13, column=0, sticky="ew", pady=(0, 20))

        self.btn_bot = ctk.CTkButton(sb, text="INICIAR BOT AUTOMATICO", fg_color=GREEN, hover_color="#008E5D", font=ctk.CTkFont(weight="bold"), command=self._toggle_bot)
        self.btn_bot.grid(row=4, column=0, sticky="ew", padx=15, pady=(10, 5))
        self.btn_pdf = ctk.CTkButton(sb, text="Generar Reporte PDF", fg_color=BORDER, hover_color="#3C3C47", text_color=WHITE, command=self._gen_pdf)
        self.btn_pdf.grid(row=5, column=0, sticky="ew", padx=15, pady=(5, 20))

        # --- MAIN AREA WITH TABS ---
        main_area = ctk.CTkFrame(self, fg_color="transparent")
        main_area.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        main_area.grid_columnconfigure(0, weight=1)
        main_area.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(main_area, fg_color=BG, segmented_button_selected_color=GREEN,
                                       segmented_button_selected_hover_color="#008E5D",
                                       segmented_button_unselected_color=CARD,
                                       segmented_button_unselected_hover_color=BORDER)
        self.tabview.grid(row=0, column=0, sticky="nsew")
        tab_trading = self.tabview.add("TRADING EN VIVO")
        tab_analytics = self.tabview.add("ANALYTICS & HISTORIAL")

        # ============== TAB 1: TRADING EN VIVO ==============
        mn = tab_trading
        mn.grid_columnconfigure(0, weight=1)
        mn.grid_rowconfigure(0, weight=1)
        mn.grid_rowconfigure(1, weight=5)
        mn.grid_rowconfigure(2, weight=1)
        mn.grid_rowconfigure(3, weight=2)

        cards = ctk.CTkFrame(mn, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for c in range(4): cards.grid_columnconfigure(c, weight=1, uniform="eq")
        self.card_saldo  = self._card(cards, 0, "SALDO ACTUAL", "---", GREEN)
        self.card_ops    = self._card(cards, 1, "OPERACIONES", "0 G / 0 P / 0 E", WHITE)
        self.card_rend   = self._card(cards, 2, "RENDIMIENTO NETO", f"{self._simbolo_moneda}0.00", WHITE)
        self.card_status = self._card(cards, 3, "ESTADO", "INACTIVO", MUTED)

        # Panel resultados
        res = ctk.CTkFrame(mn, fg_color=CARD, border_color=BORDER, border_width=1)
        res.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        res.grid_rowconfigure(0, weight=1)
        res.grid_columnconfigure(0, weight=3)
        res.grid_columnconfigure(1, weight=2)

        pnl_frm = ctk.CTkFrame(res, fg_color="transparent")
        pnl_frm.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=5)
        self._sparkline = _PnlSparkline(pnl_frm)

        tbl_frm = ctk.CTkFrame(res, fg_color="transparent")
        tbl_frm.grid(row=0, column=1, sticky="nsew", padx=(2, 5), pady=5)
        tbl_frm.grid_rowconfigure(0, weight=0)
        tbl_frm.grid_rowconfigure(1, weight=1)
        tbl_frm.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(tbl_frm, fg_color=BORDER, height=30)
        hdr.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(hdr, text=f"{'Hora':<8} {'Activo':<14} {'Ord':<5} {'Inv':<8} {'Resultado':<10} {'G&P':>10}",
                     font=ctk.CTkFont(family="Courier", size=12, weight="bold"), text_color=WHITE).pack(padx=6, pady=4)

        self._tbl = ctk.CTkTextbox(tbl_frm, fg_color=CARD, text_color=WHITE,
                                    font=ctk.CTkFont(family="Courier", size=12), wrap="none")
        self._tbl.grid(row=1, column=0, sticky="nsew")
        self._tbl.configure(state="disabled")
        self._tbl_lines = 0

        # Botones
        ex = ctk.CTkFrame(mn, fg_color="transparent")
        ex.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ex.grid_columnconfigure(0, weight=1); ex.grid_columnconfigure(1, weight=1)
        self.btn_call = ctk.CTkButton(ex, text="COMPRAR (CALL)", fg_color=GREEN, hover_color="#008E5D", font=ctk.CTkFont(size=16, weight="bold"), height=50, command=lambda: self._manual("call"))
        self.btn_call.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.btn_put = ctk.CTkButton(ex, text="VENDER (PUT)", fg_color=RED, hover_color="#D8231B", font=ctk.CTkFont(size=16, weight="bold"), height=50, command=lambda: self._manual("put"))
        self.btn_put.grid(row=0, column=1, padx=(10, 0), sticky="ew")

        # Log
        lf = ctk.CTkFrame(mn, fg_color=CARD, border_color=BORDER, border_width=1)
        lf.grid(row=3, column=0, sticky="nsew")
        lf.grid_columnconfigure(0, weight=1); lf.grid_rowconfigure(0, weight=1)
        self.tb_logs = ctk.CTkTextbox(lf, fg_color="transparent", text_color=WHITE,
                                       font=ctk.CTkFont(family="Courier", size=12), wrap="word")
        self.tb_logs.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.tb_logs.configure(state="disabled")

        # ============== TAB 2: ANALYTICS & HISTORIAL ==============
        self._build_analytics_tab(tab_analytics)

        self._set_ui(False)

    def _lbl(self, p, r, t):
        ctk.CTkLabel(p, text=t, text_color=WHITE, font=ctk.CTkFont(weight="bold")).grid(row=r, column=0, sticky="w", pady=(5, 2))

    def _card(self, p, c, t, v, cl):
        cd = ctk.CTkFrame(p, fg_color=CARD, border_color=BORDER, border_width=1)
        cd.grid(row=0, column=c, sticky="nsew", padx=5)
        cd.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cd, text=t, font=ctk.CTkFont(size=13, weight="bold"), text_color=MUTED).grid(row=0, column=0, pady=(12, 2), padx=14, sticky="w")
        lb = ctk.CTkLabel(cd, text=v, font=ctk.CTkFont(size=26, weight="bold"), text_color=cl)
        lb.grid(row=1, column=0, pady=(2, 14), padx=14, sticky="w")
        return lb

    # ================================================================
    # ANALYTICS TAB
    # ================================================================
    def _build_analytics_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=0)  # Filters
        tab.grid_rowconfigure(1, weight=0)  # KPIs
        tab.grid_rowconfigure(2, weight=1)  # Table & Charts panel
        tab.grid_rowconfigure(3, weight=0)  # Buttons

        # --- FILTER BAR ---
        fbar = ctk.CTkFrame(tab, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
        fbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for i in range(9):
            fbar.grid_columnconfigure(i, weight=1 if i in (1, 3, 5, 7) else 0)

        ctk.CTkLabel(fbar, text="Fecha Inicio:", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED).grid(row=0, column=0, padx=(12, 4), pady=10)
        self._an_fecha_ini = ctk.CTkEntry(fbar, placeholder_text="YYYY-MM-DD", width=120)
        self._an_fecha_ini.grid(row=0, column=1, padx=4, pady=10, sticky="ew")
        self._an_fecha_ini.insert(0, datetime.now().strftime("%Y-%m-%d"))

        ctk.CTkLabel(fbar, text="Fecha Fin:", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED).grid(row=0, column=2, padx=(12, 4), pady=10)
        self._an_fecha_fin = ctk.CTkEntry(fbar, placeholder_text="YYYY-MM-DD", width=120)
        self._an_fecha_fin.grid(row=0, column=3, padx=4, pady=10, sticky="ew")
        self._an_fecha_fin.insert(0, datetime.now().strftime("%Y-%m-%d"))

        ctk.CTkLabel(fbar, text="Hora Ini:", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED).grid(row=0, column=4, padx=(12, 4), pady=10)
        self._an_hora_ini = ctk.CTkEntry(fbar, placeholder_text="HH:MM", width=80)
        self._an_hora_ini.grid(row=0, column=5, padx=4, pady=10, sticky="ew")
        self._an_hora_ini.insert(0, "00:00")

        ctk.CTkLabel(fbar, text="Hora Fin:", font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED).grid(row=0, column=6, padx=(12, 4), pady=10)
        self._an_hora_fin = ctk.CTkEntry(fbar, placeholder_text="HH:MM", width=80)
        self._an_hora_fin.grid(row=0, column=7, padx=4, pady=10, sticky="ew")
        self._an_hora_fin.insert(0, "23:59")

        ctk.CTkButton(fbar, text="BUSCAR", fg_color=GREEN, hover_color="#008E5D",
                      font=ctk.CTkFont(weight="bold"), width=100,
                      command=self._analytics_buscar).grid(row=0, column=8, padx=(8, 12), pady=10)

        # --- KPI CARDS ---
        kpi_row = ctk.CTkFrame(tab, fg_color="transparent")
        kpi_row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for i in range(5):
            kpi_row.grid_columnconfigure(i, weight=1, uniform="kpi")

        self._ak_total = self._card(kpi_row, 0, "TOTAL OPS", "0", GREEN)
        self._ak_winrate = self._card(kpi_row, 1, "WIN RATE", "0.0%", BLUE)
        self._ak_pnl = self._card(kpi_row, 2, "P&L NETO", "$0.00", WHITE)
        self._ak_racha = self._card(kpi_row, 3, "MEJOR RACHA", "0", "#A78BFA")
        self._ak_dd = self._card(kpi_row, 4, "MAX DRAWDOWN", "$0.00", RED)

        # --- MAIN SPLIT AREA (Table on left, Charts on right) ---
        split_frame = ctk.CTkFrame(tab, fg_color="transparent")
        split_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        split_frame.grid_columnconfigure(0, weight=3) # Table
        split_frame.grid_columnconfigure(1, weight=2) # Charts
        split_frame.grid_rowconfigure(0, weight=1)

        # --- RESULTS TABLE (Left) ---
        tbl_wrap = ctk.CTkFrame(split_frame, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
        tbl_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        tbl_wrap.grid_columnconfigure(0, weight=1)
        tbl_wrap.grid_rowconfigure(0, weight=0)
        tbl_wrap.grid_rowconfigure(1, weight=1)

        self._an_count_lbl = ctk.CTkLabel(tbl_wrap, text="OPERACIONES FILTRADAS",
                                           font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED)
        self._an_count_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        an_hdr = ctk.CTkFrame(tbl_wrap, fg_color=BORDER, height=28)
        an_hdr.grid(row=1, column=0, sticky="new", padx=8)
        ctk.CTkLabel(an_hdr, text=f"{'Fecha':<12} {'Hora':<10} {'Activo':<14} {'Algo':<12} {'Tipo':<6} {'Inv':>8} {'Resultado':<10} {'P&L':>10}",
                     font=ctk.CTkFont(family="Courier", size=11, weight="bold"), text_color=WHITE).pack(padx=6, pady=3)

        self._an_tbl = ctk.CTkTextbox(tbl_wrap, fg_color=CARD, text_color=WHITE,
                                       font=ctk.CTkFont(family="Courier", size=11), wrap="none")
        self._an_tbl.grid(row=1, column=0, sticky="nsew", padx=8, pady=(28, 8))
        self._an_tbl.configure(state="disabled")

        # --- CHARTS SIDE PANEL (Right) ---
        charts_wrap = ctk.CTkFrame(split_frame, fg_color="transparent")
        charts_wrap.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        charts_wrap.grid_columnconfigure(0, weight=1)
        charts_wrap.grid_rowconfigure(0, weight=1, uniform="ch")
        charts_wrap.grid_rowconfigure(1, weight=1, uniform="ch")

        donut_frm = ctk.CTkFrame(charts_wrap, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
        donut_frm.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        self._an_chart_donut = _DonutChartCanvas(donut_frm)
        self._an_chart_donut.pack(fill="both", expand=True, padx=4, pady=4)

        bar_frm = ctk.CTkFrame(charts_wrap, fg_color=CARD, border_color=BORDER, border_width=1, corner_radius=8)
        bar_frm.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        self._an_chart_bar = _BarChartCanvas(bar_frm)
        self._an_chart_bar.pack(fill="both", expand=True, padx=4, pady=4)

        # --- ACTION BUTTONS ---
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew")
        for i in range(3): btn_row.grid_columnconfigure(i, weight=1)

        ctk.CTkButton(btn_row, text="GENERAR REPORTE PDF FILTRADO", fg_color=BLUE,
                      hover_color="#003D99", font=ctk.CTkFont(weight="bold"), height=40,
                      command=self._analytics_gen_pdf).grid(row=0, column=0, padx=(0, 4), sticky="ew")

        ctk.CTkButton(btn_row, text="EXPORTAR A CSV", fg_color=GREEN,
                      hover_color="#008E5D", font=ctk.CTkFont(weight="bold"), height=40,
                      command=self._analytics_exportar_csv).grid(row=0, column=1, padx=4, sticky="ew")

        ctk.CTkButton(btn_row, text="LIMPIAR FILTROS", fg_color=BORDER,
                      hover_color="#3C3C47", text_color=WHITE, height=40,
                      command=self._analytics_limpiar).grid(row=0, column=2, padx=(4, 0), sticky="ew")

        # Cargar datos iniciales
        self.after(500, self._analytics_buscar)

    def _analytics_buscar(self):
        """Consulta operaciones con los filtros actuales y actualiza la UI."""
        fi = self._an_fecha_ini.get().strip() or None
        ff = self._an_fecha_fin.get().strip() or None
        hi = self._an_hora_ini.get().strip() or None
        hf = self._an_hora_fin.get().strip() or None

        ops = registro_operaciones.consultar_operaciones(fi, ff, hi, hf)
        kpis = registro_operaciones.obtener_kpis(ops)
        por_activo = registro_operaciones.obtener_resumen_por_activo(ops)

        self._an_last_ops = ops
        self._analytics_render_kpis(kpis)
        self._analytics_render_table(ops)

        # Actualizar graficos nativos
        self._an_chart_donut.update_data(kpis.get("ganadas", 0), kpis.get("perdidas", 0), kpis.get("empates", 0))
        self._an_chart_bar.update_data(por_activo)

    def _analytics_render_kpis(self, k):
        """Actualiza los KPI cards del tab Analytics."""
        self._ak_total.configure(text=str(k.get("total_ops", 0)))
        wr = k.get("win_rate", 0.0)
        self._ak_winrate.configure(text=f"{wr:.1f}%")
        pnl = k.get("pnl_neto", 0.0)
        self._ak_pnl.configure(text=f"{'+'if pnl>=0 else ''}${abs(pnl):.2f}",
                                text_color=GREEN if pnl >= 0 else RED)
        self._ak_racha.configure(text=str(k.get("mejor_racha", 0)))
        dd = k.get("max_drawdown", 0.0)
        self._ak_dd.configure(text=f"${dd:.2f}")

    def _analytics_render_table(self, ops):
        """Dibuja la tabla de operaciones filtradas."""
        self._an_count_lbl.configure(text=f"OPERACIONES FILTRADAS ({len(ops)} registros)")
        self._an_tbl.configure(state="normal")
        self._an_tbl.delete("1.0", "end")
        if not ops:
            self._an_tbl.insert("end", "\n  Sin operaciones en este rango de fecha/hora.\n")
            self._an_tbl.configure(state="disabled")
            return
        tag_idx = 0
        for op in reversed(ops):
            f = op.get("fecha", "")
            h = op.get("hora", "")
            a = str(op.get("activo", ""))[:13]
            al = str(op.get("algoritmo", "-"))[:11]
            t = op.get("tipo", "")
            inv = op.get("inversion", 0)
            r = op.get("resultado", "")
            p = op.get("profit", 0.0)
            pnl_str = f"{'+'if p>=0 else ''}{self._simbolo_moneda}{abs(p):.2f}"
            line = f"{f:<12} {h:<10} {a:<14} {al:<12} {t:<6} {self._simbolo_moneda}{inv:>7.2f} {r:<10} {pnl_str:>10}\n"
            tag = f"an_row_{tag_idx}"
            if "GANADA" in r.upper():
                color = GREEN
            elif "PERDIDA" in r.upper():
                color = RED
            else:
                color = MUTED
            self._an_tbl.insert("end", line, tag)
            self._an_tbl.tag_config(tag, foreground=color)
            tag_idx += 1
        self._an_tbl.configure(state="disabled")

    def _analytics_limpiar(self):
        """Resetea filtros y recarga."""
        self._an_fecha_ini.delete(0, "end")
        self._an_fecha_ini.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._an_fecha_fin.delete(0, "end")
        self._an_fecha_fin.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._an_hora_ini.delete(0, "end")
        self._an_hora_ini.insert(0, "00:00")
        self._an_hora_fin.delete(0, "end")
        self._an_hora_fin.insert(0, "23:59")
        self._analytics_buscar()

    def _analytics_gen_pdf(self):
        """Genera un PDF con las operaciones filtradas actuales."""
        ops = getattr(self, "_an_last_ops", [])
        if not ops:
            self.write_log("ERROR", "[Analytics] No hay operaciones para el reporte.")
            return
        try:
            kpis = registro_operaciones.obtener_kpis(ops)
            fi = self._an_fecha_ini.get().strip() or "Inicio"
            ff = self._an_fecha_fin.get().strip() or "Fin"
            hi = self._an_hora_ini.get().strip() or "00:00"
            hf = self._an_hora_fin.get().strip() or "23:59"
            datos = {
                "cuenta_id": user.EMAIL,
                "tipo_cuenta": "REAL" if "REAL" in self.cmb_cuenta.get() else "PRACTICE",
                "fecha_inicio": fi, "fecha_fin": ff,
                "hora_inicio": hi, "hora_fin": hf,
                "x0": 0.0, "x_final": kpis["pnl_neto"],
                "rendimiento": kpis["pnl_neto"],
                "total_ops": kpis["total_ops"], "ganadas": kpis["ganadas"],
                "perdidas": kpis["perdidas"], "empates": kpis["empates"],
            }
            os.makedirs("Reportes_Inversion", exist_ok=True)
            ruta = os.path.join("Reportes_Inversion",
                                f"Analytics_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.pdf")
            generarPDF.generar_reporte_pdf(datos, ops, ruta)
            self.write_log("OK", f"[Analytics] PDF generado: {ruta}")
        except Exception as e:
            self.write_log("ERROR", f"[Analytics] PDF error: {e}")

    def _analytics_exportar_csv(self):
        """Exporta las operaciones filtradas actuales a un archivo CSV."""
        ops = getattr(self, "_an_last_ops", [])
        if not ops:
            self.write_log("ERROR", "[Analytics] No hay operaciones para exportar a CSV.")
            return
        import csv
        from tkinter import filedialog
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivos CSV", "*.csv")],
            initialfile=f"operaciones_{datetime.now().strftime('%Y-%m-%d')}.csv"
        )
        if not file_path:
            return
        try:
            with open(file_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Fecha", "Hora", "Activo", "Algoritmo", "Tipo", "Inversion", "Resultado", "Profit"])
                for o in ops:
                    writer.writerow([
                        o.get("fecha", ""),
                        o.get("hora", ""),
                        o.get("activo", ""),
                        o.get("algoritmo", ""),
                        o.get("tipo", ""),
                        o.get("inversion", 0.0),
                        o.get("resultado", ""),
                        o.get("profit", 0.0)
                    ])
            self.write_log("OK", f"[Analytics] CSV exportado: {file_path}")
        except Exception as e:
            self.write_log("ERROR", f"[Analytics] CSV error: {e}")


    def _set_ui(self, ok):
        s = "normal" if ok else "disabled"
        for w in [self.cb_activo, self.cmb_cuenta, self.ent_inv, self.ent_sl,
                   self.ent_tp, self.ent_exp, self.btn_bot,
                   self.btn_pdf, self.btn_call, self.btn_put]:
            w.configure(state=s)

    # ================================================================
    # MAESTRO (dialogo al inicio, robusto)
    # ================================================================
    def _solicitar_maestro(self):
        self.write_log("INFO", "Abriendo dialogo de conexion al Maestro...")
        self._crear_dialogo_maestro()

    def _crear_dialogo_maestro(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("CONEXION A SERVIDOR MAESTRO")
        dlg.geometry("420x260")
        dlg.configure(fg_color=CARD)
        dlg.transient(self)
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text="CONEXION A SERVIDOR MAESTRO",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=GREEN).pack(pady=(20, 8))
        ctk.CTkLabel(dlg, text="Ingrese el codigo del Nodo Maestro\no continue en modo Autonomo.",
                     font=ctk.CTkFont(size=12),
                     text_color=MUTED).pack(pady=(0, 10))

        ent = ctk.CTkEntry(dlg, placeholder_text="Codigo de Sala (opcional)",
                           width=260, font=ctk.CTkFont(size=13))
        ent.pack(pady=(0, 12))

        def _zmq_log(level, msg):
            self.ui_queue.put({"type": "log", "level": level, "message": msg})

        def _zmq_comando(accion, msg_dict):
            if accion == "cambiar_algoritmo":
                algo = msg_dict.get("algoritmo")
                self.ui_queue.put({"type": "cmd_cambiar_algoritmo", "algoritmo": algo})
            elif accion == "cambiar_parametros":
                params = msg_dict.get("parametros", {})
                self.ui_queue.put({"type": "cmd_cambiar_parametros", "parametros": params})
            elif accion in ["solicitar_reporte", "solicitar_reporte_para_global"]:
                self.ui_queue.put({"type": "cmd_enviar_reporte"})
            elif accion == "desconectar":
                self.ui_queue.put({"type": "cmd_desconectar"})

        def conectar():
            c = ent.get().strip()
            if c:
                self.codigo_maestro = c
                self.cliente_zmq = cliente_zmq.ClienteZMQ(
                    ip_maestro="127.0.0.1", 
                    codigo_sala=c,
                    callback_comando=_zmq_comando,
                    callback_log=_zmq_log
                )
                if self.cliente_zmq.iniciar():
                    self.maestro_verificado = True
                    self.lbl_maestro.configure(text=f"Maestro: AUTENTICADO [{c}]", text_color=GREEN)
                    self.write_log("OK", f"Conectado al Maestro [{c}].")
                else:
                    self.maestro_verificado = False
                    self.lbl_maestro.configure(text="Maestro: FALLO AUTENTICACION", text_color=RED)
            dlg.destroy()
            self._habilitar_ui()

        def saltar():
            self.lbl_maestro.configure(text="Maestro: NO CONECTADO (Autonomo)", text_color=MUTED)
            self.write_log("INFO", "Modo Autonomo.")
            dlg.destroy()
            self._habilitar_ui()

        ctk.CTkButton(dlg, text="CONECTAR AL MAESTRO", fg_color=GREEN,
                      hover_color="#008E5D", font=ctk.CTkFont(weight="bold"),
                      command=conectar, width=260).pack(pady=(0, 6))

        ctk.CTkButton(dlg, text="CONTINUAR SIN MAESTRO (Autonomo)", fg_color=BORDER,
                      hover_color="#3C3C47", text_color=WHITE,
                      command=saltar, width=260).pack()

        dlg.protocol("WM_DELETE_WINDOW", saltar)
        dlg.lift()
        dlg.after(50, dlg.focus_force)

    def _habilitar_ui(self):
        self._set_ui(True)
        self.card_status.configure(text="SISTEMA ACTIVO", text_color=GREEN)
    # ================================================================
    def write_log(self, level, msg):
        if self._cerrando: return
        line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}\n"
        try:
            self.tb_logs.configure(state="normal")
            self.tb_logs.insert("end", line)
            self.tb_logs.see("end")
            self.tb_logs.configure(state="disabled")
        except Exception: pass

    def _add_trade_row(self, op):
        h = op.get("hora", ""); a = str(op.get("activo", ""))[:12]
        t = op.get("tipo", ""); inv = op.get("inversion", 0)
        r = op.get("resultado", ""); p = op.get("profit", 0.0)
        pnl = f"{self._simbolo_moneda}{p:+.2f}" if p != 0 else f"{self._simbolo_moneda}0.00"
        line = f"{h:<8} {a:<14} {t:<5} {self._simbolo_moneda}{inv:<7.2f} {r:<10} {pnl:>10}\n"
        # Determinar color según resultado
        if "GANADA" in r.upper():
            tag_color = GREEN
        elif "PERDIDA" in r.upper():
            tag_color = RED
        else:
            tag_color = MUTED
        tag_name = f"row_{self._tbl_lines}"
        self._tbl.configure(state="normal")
        self._tbl.insert("end", line, tag_name)
        self._tbl.tag_config(tag_name, foreground=tag_color)
        self._tbl_lines += 1
        if self._tbl_lines > 50:
            self._tbl.delete("1.0", "2.0")
            self._tbl_lines -= 1
        self._tbl.see("end")
        self._tbl.configure(state="disabled")

    def _procesar_cola(self):
        try:
            while True:
                ev = self.ui_queue.get_nowait()
                t = ev.get("type")
                if t == "log": self.write_log(ev["level"], ev["message"])
                elif t == "cmd_cambiar_algoritmo":
                    algo = ev["algoritmo"]
                    self.cmb_algoritmo.set(algo)
                    self.write_log("INFO", f"Algoritmo cambiado a {algo} por el Maestro.")
                elif t == "cmd_cambiar_parametros":
                    p = ev["parametros"]
                    if "algoritmo" in p: self.cmb_algoritmo.set(p["algoritmo"])
                    if "cuenta" in p: self.cmb_cuenta.set(p["cuenta"])
                    if "inv" in p: 
                        self.ent_inv.delete(0, "end"); self.ent_inv.insert(0, p["inv"])
                    if "sl" in p: 
                        self.ent_sl.delete(0, "end"); self.ent_sl.insert(0, p["sl"])
                    if "tp" in p: 
                        self.ent_tp.delete(0, "end"); self.ent_tp.insert(0, p["tp"])
                    if "exp" in p: 
                        self.ent_exp.delete(0, "end"); self.ent_exp.insert(0, p["exp"])
                    self.write_log("INFO", "Parámetros actualizados por el Maestro.")
                elif t == "cmd_desconectar":
                    self.maestro_verificado = False
                    self.lbl_maestro.configure(text="Maestro: DESCONECTADO (Kick)", text_color=RED)
                    self.write_log("ALERTA", "Has sido desconectado por el Maestro.")
                    if self.cliente_zmq:
                        self.cliente_zmq.detener()
                        self.cliente_zmq = None
                    if self.bot_activo:
                        self._toggle_bot() # Detener bot si estaba corriendo
                elif t == "cmd_enviar_reporte":
                    if self.cliente_zmq:
                        self.cliente_zmq.enviar_reporte(self.historial_operaciones)
                elif t == "connection_success":
                    self.card_saldo.configure(text=f"{self._simbolo_moneda}{ev['balance']:.2f}", text_color=GREEN)
                    self.card_status.configure(text="SOLICITANDO MAESTRO", text_color=MUTED)
                    self._solicitar_maestro()
                elif t == "connection_failed":
                    self.card_saldo.configure(text="FALLO CONEXION", text_color=RED)
                    self.card_status.configure(text="SOLICITANDO MAESTRO", text_color=MUTED)
                    self._solicitar_maestro()
                elif t == "activos_loaded":
                    pass
                elif t == "status_update":
                    self.card_saldo.configure(text=f"{self._simbolo_moneda}{ev['balance']:.2f}")
                    rd = ev["balance"] - self.saldo_inicial
                    c = GREEN if rd >= 0 else RED
                    self.card_rend.configure(text=f"{'+' if rd >= 0 else ''}{self._simbolo_moneda}{rd:.2f}", text_color=c)
                elif t == "bot_stopped":
                    self.bot_activo = False
                    self._bots_pendientes = 0
                    self.bot_stop_event.set()
                    self.btn_bot.configure(text="INICIAR BOT AUTOMATICO", fg_color=GREEN, hover_color="#008E5D", state="normal")
                    self.card_status.configure(text="SISTEMA ACTIVO", text_color=GREEN)
                    self.write_log("INFO", "Todos los bots finalizados.")
                    # Auto-generar PDF con historial completo al detener bot
                    if self.historial_operaciones:
                        self._gen_pdf()
                elif t == "manual_complete":
                    self.btn_call.configure(state="normal", text="COMPRAR (CALL)")
                    self.btn_put.configure(state="normal", text="VENDER (PUT)")
                elif t == "trade_completed":
                    op = ev["op"]
                    self.historial_operaciones.append(op)
                    self._pnl_acumulado += op.get("profit", 0)
                    self._add_trade_row(op)
                    self._sparkline.push(self._pnl_acumulado, self._simbolo_moneda)
                    # Persistir al JSON histórico
                    try:
                        extras = ev.get("persist_extras", {})
                        registro_operaciones.guardar_operacion(op, **extras)
                    except Exception:
                        pass
                    # Actualizar contadores desde el resultado real de la operacion
                    res = op.get("resultado", "").upper()
                    self.total_ops += 1
                    if "GANADA" in res:
                        self.ganadas += 1
                    elif "PERDIDA" in res:
                        self.perdidas += 1
                    else:
                        self.empates += 1
                    self.card_ops.configure(text=f"{self.ganadas} G / {self.perdidas} P / {self.empates} E")
                self.ui_queue.task_done()
        except queue.Empty: pass
        finally:
            if not self._cerrando: self.after(80, self._procesar_cola)

    # ================================================================
    # CONEXION BROKER
    # ================================================================
    def _conectar_broker_async(self):
        try:
            self.ui_queue.put({"type": "log", "level": "INFO", "message": "Conectando al broker..."})
            api = IQ_Option(user.EMAIL, user.PASSWORD)
            ok, msg = api.connect()
            if ok:
                self.api = api; self.api_connected = True
                api.change_balance("PRACTICE")
                s = api.get_balance(); self.saldo_inicial = s
                self.fecha_inicio_sesion = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                self.ui_queue.put({"type": "log", "level": "OK", "message": "WebSocket establecido."})
                self.ui_queue.put({"type": "connection_success", "balance": s})
            else:
                self.ui_queue.put({"type": "log", "level": "ERROR", "message": f"Fallo: {msg}"})
                self.ui_queue.put({"type": "connection_failed"})
        except Exception as e:
            self.ui_queue.put({"type": "log", "level": "ERROR", "message": f"Excepcion: {e}"})
            self.ui_queue.put({"type": "connection_failed"})

    # ================================================================
    # CUENTA
    # ================================================================
    def _on_cuenta_changed(self, choice):
        if not self.api_connected or not self.api: return
        if "REAL" in choice:
            dlg = ctk.CTkInputDialog(text="Cambiando a CUENTA REAL.\nEscriba 'CONFIRMAR':", title="ADVERTENCIA")
            if dlg.get_input() == "CONFIRMAR":
                self.api.change_balance("REAL")
                s = self.api.get_balance()
                self.saldo_inicial = s
                self._simbolo_moneda = "S/"
                self.card_saldo.configure(text=f"S/{s:.2f}")
                self.write_log("ALERTA", f"MODO REAL! Saldo: S/{s:.2f}")
            else:
                self.cmb_cuenta.set("PRACTICA (Demo)")
                return
        else:
            self.api.change_balance("PRACTICE")
            s = self.api.get_balance()
            self.saldo_inicial = s
            self._simbolo_moneda = "$"
            self.card_saldo.configure(text=f"${s:.2f}")
            self.write_log("INFO", f"Modo practica. Saldo: ${s:.2f}")

    # ================================================================
    # BOT MULTI-MERCADO
    # ================================================================
    def _toggle_bot(self):
        if not self.api_connected or not self.api:
            self.write_log("ERROR", "Sin conexion API."); return
        if not self.bot_activo:
            inv = self._si(self.ent_inv.get(), 4)
            sl = self._sf(self.ent_sl.get(), 1.0)
            tp = self._sf(self.ent_tp.get(), 0.5)
            exp = self._si(self.ent_exp.get(), 1)
            cuenta = "REAL" if "REAL" in self.cmb_cuenta.get() else "PRACTICE"
            activo = self.cb_activo.get()
            algo_nombre = self.cmb_algoritmo.get()
            algos = obtener_lista()
            algo_id = "montecarlo"
            for a in algos:
                if a["nombre"] == algo_nombre:
                    algo_id = a["id"]
                    break

            if inv <= 0: self.write_log("ERROR", "Inversion > 0."); return

            self.write_log("INFO", f"Iniciando bot en: {activo}")
            self.bot_activo = True
            self.btn_bot.configure(text="DETENER BOT", fg_color=RED, hover_color="#D8231B")
            self.card_status.configure(text="BOT OPERANDO", text_color=GREEN)
            self.bot_stop_event.clear()
            self.bot_threads.clear()

            if self.api:
                try:
                    self.api.change_balance(cuenta)
                    bal = self.api.get_balance()
                    self.saldo_inicial = bal
                    self.card_saldo.configure(text=f"{self._simbolo_moneda}{bal:.2f}")
                except Exception: pass

            t = threading.Thread(target=self._bot_worker, args=(activo, cuenta, inv, sl, tp, exp, algo_id), daemon=True)
            t.start()
            self.bot_threads.append(t)
            self._bots_pendientes = 1
        else:
            self.write_log("ALERTA", "Solicitando parada. Finalizando operaciones en curso...")
            self.bot_stop_event.set()
            self.btn_bot.configure(text="FINALIZANDO...", fg_color=MUTED, hover_color=MUTED, state="disabled")

    def _bot_worker(self, activo, cuenta, inv, sl, tp, exp, algo_id):
        def log_cb(nivel, msg):
            self.ui_queue.put({"type": "log", "level": nivel, "message": f"[{activo}] {msg}"})
            # Refrescar saldo cuando se acepta una orden (refleja deduccion inmediata)
            if "Orden aceptada" in msg:
                if self.api_connected and self.api:
                    try:
                        bal = self.api.get_balance()
                        self.ui_queue.put({"type": "status_update", "balance": bal})
                    except Exception: pass

        def op_cb(op_dict):
            op_dict["activo"] = activo
            saldo_post = 0.0
            if self.api_connected and self.api:
                try:
                    saldo_post = self.api.get_balance()
                except Exception:
                    pass
            self.ui_queue.put({"type": "trade_completed", "op": op_dict,
                              "persist_extras": {"algoritmo": algo_id, "tipo_cuenta": cuenta, "saldo_post": saldo_post}})
            if self.api_connected and self.api:
                try:
                    bal = self.api.get_balance()
                    self.ui_queue.put({"type": "status_update", "balance": bal})
                except Exception: pass

        try:
            iq_option.ejecutar_bot_completo(
                api=self.api, callback_log=log_cb, evento_parada=self.bot_stop_event,
                activo=activo, inversion=inv, expiracion=exp, horizonte=50,
                pct_sl=sl, pct_tp=tp, modo_balance=cuenta,
                callback_operacion=op_cb, algoritmo_id=algo_id,
            )
        except Exception as e:
            self.ui_queue.put({"type": "log", "level": "ERROR", "message": f"[{activo}] Bot: {e}"})
        finally:
            self._bots_pendientes -= 1
            if self._bots_pendientes <= 0:
                self.ui_queue.put({"type": "bot_stopped"})

    # ================================================================
    # MANUAL
    # ================================================================
    def _manual(self, direction):
        if not self.api_connected or not self.api:
            self.write_log("ERROR", "Sin conexion."); return
        inv = self._si(self.ent_inv.get(), 4)
        exp = self._si(self.ent_exp.get(), 1)
        if inv <= 0: self.write_log("ERROR", "Inversion > 0."); return
        self.btn_call.configure(state="disabled", text="Enviando...")
        self.btn_put.configure(state="disabled", text="Enviando...")
        self.write_log("INFO", f"[MANUAL] {direction.upper()} {self.cb_activo.get()} {self._simbolo_moneda}{inv}")
        threading.Thread(target=self._manual_worker, args=(direction, inv, exp), daemon=True).start()

    def _manual_worker(self, direction, inv, exp):
        activo = self.cb_activo.get()
        try:
            ok, oid = self.api.buy(inv, activo, direction, exp)
            if ok:
                self.ui_queue.put({"type": "log", "level": "OK", "message": f"[MANUAL] OK. ID: {oid}"})
                self.ui_queue.put({"type": "manual_complete"})
                res = self.api.check_win_v3(oid)
                t, g, p, e = self.total_ops + 1, self.ganadas, self.perdidas, self.empates
                if res < 0:
                    self.ui_queue.put({"type": "log", "level": "ALERTA", "message": f"[MANUAL] Perdida {self._simbolo_moneda}{res:.2f}"})
                    p += 1
                elif res > 0:
                    self.ui_queue.put({"type": "log", "level": "OK", "message": f"[MANUAL] Ganancia +{self._simbolo_moneda}{res:.2f}"})
                    g += 1
                else:
                    self.ui_queue.put({"type": "log", "level": "INFO", "message": "[MANUAL] Empate"})
                    e += 1
                self.ui_queue.put({"type": "ops_update", "total_ops": t, "ganadas": g, "perdidas": p, "empates": e})
                rs = "GANADA" if res > 0 else ("PERDIDA" if res < 0 else "EMPATE")
                self.ui_queue.put({"type": "trade_completed", "op": {"hora": datetime.now().strftime("%H:%M:%S"), "activo": activo, "tipo": direction.upper(), "inversion": inv, "resultado": rs, "profit": res},
                                   "persist_extras": {"algoritmo": "manual", "tipo_cuenta": "REAL" if "REAL" in self.cmb_cuenta.get() else "PRACTICE", "saldo_post": self.api.get_balance()}})
                self.ui_queue.put({"type": "status_update", "balance": self.api.get_balance()})
            else:
                self.ui_queue.put({"type": "log", "level": "ERROR", "message": "[MANUAL] Rechazada."})
                self.ui_queue.put({"type": "manual_complete"})
        except Exception as e:
            self.ui_queue.put({"type": "log", "level": "ERROR", "message": f"[MANUAL] {e}"})
            self.ui_queue.put({"type": "manual_complete"})

    # ================================================================
    # PDF
    # ================================================================
    def _gen_pdf(self):
        if not self.api_connected or not self.api:
            self.write_log("ERROR", "Sin conexion."); return
        self.write_log("INFO", "Generando PDF...")
        try:
            sf = self.api.get_balance()
            datos = {"cuenta_id": user.EMAIL, "tipo_cuenta": "REAL" if "REAL" in self.cmb_cuenta.get() else "PRACTICE",
                     "fecha_inicio": self.fecha_inicio_sesion, "fecha_fin": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                     "x0": self.saldo_inicial, "x_final": sf, "rendimiento": sf - self.saldo_inicial,
                     "total_ops": self.total_ops, "ganadas": self.ganadas, "perdidas": self.perdidas, "empates": self.empates}
            os.makedirs("Reportes_Inversion", exist_ok=True)
            ruta = os.path.join("Reportes_Inversion", f"{self.cb_activo.get()}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.pdf")
            generarPDF.generar_reporte_pdf(datos, self.historial_operaciones, ruta)
            self.write_log("OK", f"PDF: {ruta}")
        except Exception as e:
            self.write_log("ERROR", f"PDF: {e}")

    # ================================================================
    # UTILES
    # ================================================================
    @staticmethod
    def _si(v, d):
        try: return int(str(v).strip())
        except: return d

    @staticmethod
    def _sf(v, d):
        try: return float(str(v).strip())
        except: return d

    def _on_close(self):
        self._cerrando = True
        if self.cliente_zmq:
            self.cliente_zmq.detener()
        self.bot_stop_event.set()
        if self.api_connected and self.api:
            try: self.api.api.close()
            except Exception: pass
        try: self.destroy()
        except Exception: pass
        os._exit(0)


if __name__ == "__main__":
    app = MasterQuantDashboard()
    app.mainloop()
