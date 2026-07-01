# dashboard_demo.py
# ============================================================================
# DEMO AUTONOMO — Prueba de velocidad del grafico de velas nativo Canvas
# NO depende de IQ Option. Genera datos OHLC sinteticos localmente.
# Ejecuta: python dashboard_demo.py
# ============================================================================

from __future__ import annotations

import math
import random
import threading
import time
import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------------
COLOR_BG = "#121214"
COLOR_CARD = "#1E1E24"
COLOR_BORDER = "#2C2C35"
COLOR_GREEN = "#00B074"
COLOR_RED = "#FF3B30"
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_MUTED = "#8E8E93"

MAX_CANDLES = 80


# ===========================================================================
# GENERADOR DE VELAS FALSAS (Movimiento Browniano Geometrico simplificado)
# ===========================================================================
class FakeMarket:
    """Simula un mercado OTC generando velas OHLC en tiempo real."""

    def __init__(self, symbol: str = "EURUSD-OTC", start_price: float = 1.0850):
        self.symbol = symbol
        self.price = start_price
        self._history: list[dict] = []
        self._lock = threading.Lock()

        # Generar 100 velas historicas iniciales
        for _ in range(MAX_CANDLES):
            self._tick()

    def _tick(self) -> dict:
        volatility = self.price * 0.0008
        drift = 0.0
        shock = random.gauss(drift, volatility)
        high = self.price + abs(shock) * random.uniform(0.3, 1.2)
        low = self.price - abs(shock) * random.uniform(0.3, 1.2)
        close = self.price + shock
        open_p = self.price
        self.price = close
        ts = datetime.now()
        return {
            "Open": open_p,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": random.randint(100, 5000),
            "Time": ts,
        }

    def update(self) -> pd.DataFrame:
        """Genera una nueva vela y retorna el DataFrame completo."""
        with self._lock:
            self._history.append(self._tick())
            if len(self._history) > MAX_CANDLES:
                self._history = self._history[-MAX_CANDLES:]
            records = self._history[-MAX_CANDLES:]
        df = pd.DataFrame(records)
        df.index = pd.DatetimeIndex(df["Time"])
        df.sort_index(inplace=True)
        return df[["Open", "High", "Low", "Close", "Volume"]]


# ===========================================================================
# GRAFICO DE VELAS ULTRARAPIDO (Canvas nativo Tkinter)
# ===========================================================================
class _TkCandleChart:
    """Renderiza velas japonesas directamente sobre tk.Canvas."""

    def __init__(self, master: tk.Widget) -> None:
        self._canvas = tk.Canvas(
            master, bg=COLOR_CARD, highlightthickness=0, bd=0,
        )
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self._render_count = 0
        self._total_render_time = 0.0

    def redraw(self, df: pd.DataFrame, title: str) -> None:
        """Borra y redibuja todo el grafico con velas OHLC."""
        t0 = time.perf_counter()
        cav = self._canvas
        cav.delete("all")

        w = cav.winfo_width()
        h = cav.winfo_height()
        if w < 50 or h < 50 or df is None or len(df) < 2:
            cav.create_text(w // 2, h // 2, text="Sin datos", fill=COLOR_TEXT_MUTED, font=("Helvetica", 11))
            return

        df = df.tail(min(len(df), MAX_CANDLES))
        n = len(df)

        mg = {"l": 70, "r": 15, "t": 35, "b": 45}
        cw = w - mg["l"] - mg["r"]
        ch = h - mg["t"] - mg["b"]
        if cw <= 0 or ch <= 0:
            return

        ph = float(df["High"].max())
        pl = float(df["Low"].min())
        prange = ph - pl
        if prange == 0:
            prange = max(ph * 0.02, 0.0001)
        ph += prange * 0.06
        pl -= prange * 0.06
        prange = ph - pl

        def py(price: float) -> float:
            return mg["t"] + ch - ((price - pl) / prange) * ch

        # Grid
        grid_steps = 4
        for i in range(grid_steps + 1):
            price = pl + (prange * i / grid_steps)
            y = py(price)
            cav.create_line(mg["l"], y, mg["l"] + cw, y, fill=COLOR_BORDER, dash=(3, 5), width=0.5, tags="grid")
            cav.create_text(mg["l"] - 6, y, text=f"{price:.5f}", fill=COLOR_TEXT_MUTED, font=("Courier", 7), anchor="e", tags="grid")

        # Velas
        spacing = cw / n
        body_w = max(2.0, min(10.0, spacing * 0.65))
        for i, (_, row) in enumerate(df.iterrows()):
            op, hi, lo, cl = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            xc = mg["l"] + (i + 0.5) * spacing
            is_bull = cl >= op
            color = COLOR_GREEN if is_bull else COLOR_RED

            # Wick
            cav.create_line(xc, py(hi), xc, py(lo), fill=color, width=1, tags="candle")
            # Body
            y_top = py(max(op, cl))
            y_bot = py(min(op, cl))
            body_h = max(1, y_bot - y_top)
            cav.create_rectangle(
                xc - body_w / 2, y_top, xc + body_w / 2, y_top + body_h,
                fill=color, outline=color, width=0, tags="candle",
            )

        # Etiquetas de tiempo
        for idx in [0, n // 4, n // 2, 3 * n // 4, n - 1]:
            if idx < 0 or idx >= n:
                continue
            if isinstance(df.index, pd.DatetimeIndex):
                lbl = df.index[idx].strftime("%H:%M:%S")
            else:
                lbl = str(df.index[idx])[:8]
            x = mg["l"] + (idx + 0.5) * spacing
            cav.create_text(x, mg["t"] + ch + 16, text=lbl, fill=COLOR_TEXT_MUTED, font=("Helvetica", 7), tags="time")

        # Titulo + contador de FPS
        cav.create_text(mg["l"] + cw / 2, 10, text=title, fill=COLOR_TEXT_MUTED, font=("Helvetica", 8), tags="title")

        # Borde
        cav.create_rectangle(mg["l"], mg["t"], mg["l"] + cw, mg["t"] + ch, outline=COLOR_BORDER, width=0.5, tags="border")

        elapsed = (time.perf_counter() - t0) * 1000
        self._render_count += 1
        self._total_render_time += elapsed

        # Mostrar ms de render
        avg_ms = self._total_render_time / self._render_count
        cav.create_text(
            mg["l"] + cw - 5, mg["t"] + ch + 2,
            text=f"render: {elapsed:.1f}ms | avg: {avg_ms:.1f}ms",
            fill=COLOR_TEXT_MUTED, font=("Courier", 7), anchor="e", tags="perf",
        )


# ===========================================================================
# DASHBOARD DEMO
# ===========================================================================
class DemoDashboard(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DEMO — Grafico de Velas Nativo Canvas (Sin IQ Option)")
        self.geometry("1100x700")
        self.configure(fg_color=COLOR_BG)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._market = FakeMarket("EURUSD-OTC", 1.0850)
        self._running = True
        self._frame_count = 0
        self._start_time = time.time()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # Barra superior de estadisticas
        top = ctk.CTkFrame(self, fg_color=COLOR_CARD, height=50)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        top.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._lbl_fps = ctk.CTkLabel(top, text="FPS: --", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLOR_GREEN)
        self._lbl_fps.grid(row=0, column=0, pady=10)
        self._lbl_candles = ctk.CTkLabel(top, text="Velas: 0", font=ctk.CTkFont(size=14), text_color=COLOR_TEXT_PRIMARY)
        self._lbl_candles.grid(row=0, column=1, pady=10)
        self._lbl_price = ctk.CTkLabel(top, text="Precio: 1.08500", font=ctk.CTkFont(size=14), text_color=COLOR_TEXT_PRIMARY)
        self._lbl_price.grid(row=0, column=2, pady=10)
        self._lbl_mode = ctk.CTkLabel(top, text="MODO: SIMULACION LOCAL", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_TEXT_MUTED)
        self._lbl_mode.grid(row=0, column=3, pady=10)

        # Botones de velocidad
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=0, sticky="w", padx=20, pady=(55, 0))

        self._speed_ms = 200
        speeds = [("Lento (1s)", 1000), ("Normal (500ms)", 500), ("Rapido (200ms)", 200), ("Ultra (50ms)", 50)]
        for i, (label, ms) in enumerate(speeds):
            btn = ctk.CTkButton(btn_frame, text=label, width=110, font=ctk.CTkFont(size=11),
                                command=lambda m=ms: self._set_speed(m))
            btn.grid(row=0, column=i, padx=3)

        # Grafico
        self.chart_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        self.chart_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        self.chart_frame.grid_columnconfigure(0, weight=1)
        self.chart_frame.grid_rowconfigure(0, weight=1)
        self._chart = _TkCandleChart(self.chart_frame)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Iniciar hilo generador de datos
        self._data_thread = threading.Thread(target=self._data_loop, daemon=True)
        self._data_thread.start()

        # Iniciar refresco del grafico
        self._latest_df: Optional[pd.DataFrame] = None
        self._data_ready = threading.Event()
        self._render_lock = threading.Lock()
        self.after(50, self._render_loop)

        print("[DEMO] Dashboard iniciado. Datos sinteticos generandose en background.")
        print("[DEMO] El grafico se actualiza con el timer de la UI. Prueba cambiar velocidad.")

    def _set_speed(self, ms: int) -> None:
        self._speed_ms = ms
        print(f"[DEMO] Velocidad de generacion: {ms}ms por vela")

    def _data_loop(self) -> None:
        """Hilo separado: genera velas falsas sin tocar la UI."""
        while self._running:
            df = self._market.update()
            self._latest_df = df.copy()
            self._data_ready.set()
            time.sleep(self._speed_ms / 1000.0)

    def _render_loop(self) -> None:
        """Timer de Tkinter: solo dibuja si hay datos nuevos listos."""
        if self._data_ready.is_set() and self._latest_df is not None:
            self._data_ready.clear()
            df = self._latest_df
            last_price = float(df["Close"].iloc[-1])
            is_up = float(df["Close"].iloc[-1]) >= float(df["Open"].iloc[-1])
            color_price = COLOR_GREEN if is_up else COLOR_RED

            self._chart.redraw(df, f"Grafico en Vivo: EURUSD-OTC (1M) — {MAX_CANDLES} velas")
            self._lbl_candles.configure(text=f"Velas: {len(df)}")
            self._lbl_price.configure(text=f"Precio: {last_price:.5f}", text_color=color_price)

            self._frame_count += 1

        if self._frame_count > 0:
            elapsed = time.time() - self._start_time
            fps = self._frame_count / elapsed
            self._lbl_fps.configure(text=f"FPS (render): {fps:.1f}")

        if self._running:
            self.after(33, self._render_loop)  # ~30 FPS max

    def _on_close(self) -> None:
        self._running = False
        try:
            self.destroy()
        except Exception:
            pass
        print("[DEMO] Cerrado.")


if __name__ == "__main__":
    print("=" * 60)
    print("  DEMO — Grafico de Velas Nativo Canvas (Tkinter)")
    print("  Sin IQ Option, sin matplotlib, sin mplfinance")
    print("  Datos OHLC generados localmente con Mov. Browniano")
    print("=" * 60)
    app = DemoDashboard()
    app.mainloop()
