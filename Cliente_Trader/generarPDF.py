# generarPDF.py
# ============================================================================
# Generador de Reportes PDF Premium - Estilo Estado de Cuenta Institucional
# Utiliza la librería fpdf2 con diseño corporativo avanzado
# ============================================================================

"""
Módulo para la generación de reportes financieros en formato PDF.

Implementa un diseño de Estado de Cuenta Institucional tipo Broker/Fintech:
- Encabezado profesional con título estilizado y barra corporativa
- Cuadrícula de KPIs con rectángulos de fondo semántico
- Tabla formal de métricas resumidas con filas estilo cebra
- Desglose completo de operaciones con colores semánticos
- Pie de página con paginación y disclaimer legal
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List

from fpdf import FPDF

logger = logging.getLogger("SystemPDFGenerator")
logger.setLevel(logging.INFO)

COLOR_OXFORD = (30, 30, 36)
COLOR_WHITE = (255, 255, 255)
COLOR_MUTED = (142, 142, 147)
COLOR_GREEN = (0, 176, 116)
COLOR_RED = (255, 59, 48)
COLOR_BG_LIGHT = (245, 246, 248)
COLOR_BORDER = (220, 224, 230)
COLOR_BLUE_CORP = (0, 82, 204)
COLOR_BLACK = (30, 30, 36)


def enmascarar_correo(correo: str) -> str:
    """Enmascara un correo electrónico para proteger la privacidad del usuario."""
    if "@" not in correo:
        return "********"
    parts = correo.split("@")
    name = parts[0]
    domain = parts[1]
    if len(name) <= 4:
        return f"{name[0]}**@{domain}"
    return f"{name[:2]}******{name[-2:]}@{domain}"


class FintechSessionPDF(FPDF):
    """PDF personalizado con header/footer de estilo institucional Fintech."""

    def __init__(
        self,
        tipo_cuenta: str,
        cuenta_id: str,
        *args: Any,
        **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.tipo_cuenta = tipo_cuenta
        self.cuenta_id = cuenta_id
        self.alias_nb_pages()

    def header(self) -> None:
        self.set_fill_color(*COLOR_OXFORD)
        self.set_text_color(*COLOR_WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 8, "  QUANT-BOT AUTOMATED TRADING  |  REPORTE DE AUDITORIA CUANTITATIVA", ln=1, fill=True)
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-18)

        # Línea separadora fina
        self.set_draw_color(*COLOR_BORDER)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)

        ahora_gmt5 = datetime.utcnow() - timedelta(hours=5)
        time_str = ahora_gmt5.strftime("%d/%m/%Y %H:%M:%S") + " (GMT-5)"
        masked_id = enmascarar_correo(self.cuenta_id)

        self.set_font("Helvetica", "", 7)
        self.set_text_color(*COLOR_MUTED)
        self.cell(
            0, 4,
            f"Pag. {self.page_no()}/{{nb}}  |  {time_str}  |  Usuario: {masked_id}",
            align="C"
        )
        self.ln(3)
        self.set_font("Helvetica", "I", 6)
        self.cell(
            0, 4,
            "Reporte generado por App Cliente Trader - Uso estrictamente academico",
            align="C"
        )


def _draw_kpi_card(
    pdf: FPDF, x: float, y: float, w: float, h: float,
    label: str, value: str, value_color: tuple
) -> None:
    """Dibuja una tarjeta KPI individual con fondo y bordes redondeados."""
    pdf.set_fill_color(*COLOR_BG_LIGHT)
    pdf.set_draw_color(*COLOR_BORDER)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, w, h, style="DF")

    # Indicador de color superior (barra tiny)
    pdf.set_fill_color(*value_color)
    pdf.rect(x, y, w, 1.5, style="F")

    pdf.set_text_color(*COLOR_MUTED)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.text(x + 3, y + 5.5, label)

    pdf.set_text_color(*value_color)
    pdf.set_font("Helvetica", "B", 11)
    pdf.text(x + 3, y + 12.5, value)


def _draw_summary_table(pdf: FPDF, datos_sesion: Dict[str, Any]) -> None:
    """Dibuja la tabla resumen de métricas con estilo cebra."""
    total_ops = datos_sesion.get("total_ops", 0)
    ganadas = datos_sesion.get("ganadas", 0)
    perdidas = datos_sesion.get("perdidas", 0)
    empates = datos_sesion.get("empates", 0)

    labels = ["Operaciones Totales", "Ganadas", "Perdidas", "Empates"]
    values = [str(total_ops), str(ganadas), str(perdidas), str(empates)]
    colors = [COLOR_BLACK, COLOR_GREEN, COLOR_RED, COLOR_MUTED]

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*COLOR_BLACK)
    pdf.cell(0, 8, "RESUMEN DE OPERACIONES", ln=1, align="L")
    pdf.ln(2)

    col_widths = [55, 45, 45, 45]
    header_w = sum(col_widths)

    # Centramos la tabla
    x_start = (210 - header_w) / 2
    pdf.set_x(x_start)

    pdf.set_fill_color(*COLOR_OXFORD)
    pdf.set_text_color(*COLOR_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    for i, label in enumerate(labels):
        pdf.cell(col_widths[i], 7, label, border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(x_start)
    for i, (val, color) in enumerate(zip(values, colors)):
        bg = (250, 251, 252) if i % 2 == 0 else COLOR_WHITE
        pdf.set_fill_color(*bg)
        pdf.set_text_color(*color)
        pdf.set_font("Helvetica", "B" if i > 0 else "", 9)
        pdf.cell(col_widths[i], 7, val, border=1, align="C", fill=True)
    pdf.ln(6)


def generar_reporte_pdf(
    datos_sesion: Dict[str, Any],
    operaciones: List[Dict[str, Any]],
    ruta_salida: str
) -> str:
    """
    Genera un reporte PDF con estilo de Estado de Cuenta Institucional.

    Parametros
    ----------
    datos_sesion : dict
        Metadatos financieros y estadisticos de la sesion de trading.
    operaciones : list[dict]
        Lista de transacciones auditadas durante la sesion.
    ruta_salida : str
        Direccion absoluta o relativa donde se guardara el archivo PDF.

    Retorna
    -------
    str
        Ruta completa del archivo PDF generado.
    """
    tipo_cuenta = datos_sesion.get("tipo_cuenta", "PRACTICE")
    cuenta_id = datos_sesion.get("cuenta_id", "Desconocido")

    pdf = FintechSessionPDF(tipo_cuenta=tipo_cuenta, cuenta_id=cuenta_id)
    pdf.add_page()

    # =========================================================================
    # 1. TITULO PRINCIPAL
    # =========================================================================
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*COLOR_OXFORD)
    pdf.cell(0, 10, "Reporte de Auditoria Cuantitativa", ln=1, align="L")
    pdf.ln(1)

    # Linea separadora elegante (doble linea)
    pdf.set_draw_color(*COLOR_BLUE_CORP)
    pdf.set_line_width(0.8)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.set_draw_color(*COLOR_BORDER)
    pdf.set_line_width(0.2)
    pdf.line(10, pdf.get_y() + 0.8, 200, pdf.get_y() + 0.8)
    pdf.ln(4)

    # =========================================================================
    # 2. TARJETA DE METADATOS DE SESION
    # =========================================================================
    pdf.set_fill_color(*COLOR_BG_LIGHT)
    pdf.set_draw_color(*COLOR_BORDER)
    pdf.set_line_width(0.2)
    pdf.rect(10, pdf.get_y(), 190, 22, style="DF")

    y_card = pdf.get_y()

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.text(15, y_card + 5, "ID Cuenta:")
    pdf.text(15, y_card + 11, "Tipo de Cuenta:")
    pdf.text(15, y_card + 17, "Periodo de Ejecucion:")

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*COLOR_BLACK)
    pdf.text(60, y_card + 5, enmascarar_correo(cuenta_id))

    color_tipo = COLOR_RED if tipo_cuenta == "REAL" else COLOR_BLUE_CORP
    pdf.set_text_color(*color_tipo)
    pdf.set_font("Helvetica", "B", 8)
    pdf.text(60, y_card + 11, tipo_cuenta)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*COLOR_BLACK)
    
    p_ini = datos_sesion.get('fecha_inicio', '-')
    hi = datos_sesion.get('hora_inicio')
    if hi and hi not in p_ini:
        p_ini += f" {hi}"
        
    p_fin = datos_sesion.get('fecha_fin', '-')
    hf = datos_sesion.get('hora_fin')
    if hf and hf not in p_fin:
        p_fin += f" {hf}"
        
    pdf.text(60, y_card + 17, f"{p_ini}  a  {p_fin}")

    pdf.ln(26)

    # =========================================================================
    # 3. CUADRICULA DE KPIS
    # =========================================================================
    x0 = datos_sesion.get("x0", 0.0)
    x_final = datos_sesion.get("x_final", 0.0)
    rendimiento = datos_sesion.get("rendimiento", 0.0)
    total_ops = datos_sesion.get("total_ops", 0)
    ganadas = datos_sesion.get("ganadas", 0)

    roi = (rendimiento / x0 * 100) if x0 > 0 else 0.0
    win_rate = (ganadas / total_ops * 100) if total_ops > 0 else 0.0

    kpis = [
        ("BALANCE INICIAL", f"${x0:.2f} USD", COLOR_BLUE_CORP),
        ("BALANCE FINAL", f"${x_final:.2f} USD", COLOR_GREEN),
        (
            "RENDIMIENTO NETO",
            f"{'$' if rendimiento >= 0 else '-$'}{abs(rendimiento):.2f} USD",
            COLOR_GREEN if rendimiento >= 0 else COLOR_RED
        ),
        ("WIN RATE", f"{win_rate:.1f}%  |  ROI {roi:+.2f}%", COLOR_BLACK),
    ]

    card_w = 45
    card_h = 18
    spacing = 3.3
    start_x = 10
    y_kpi = pdf.get_y()

    for i, (label, val, color) in enumerate(kpis):
        x_pos = start_x + i * (card_w + spacing)
        _draw_kpi_card(pdf, x_pos, y_kpi, card_w, card_h, label, val, color)
    pdf.ln(22)

    # =========================================================================
    # 4. TABLA RESUMEN DE OPERACIONES
    # =========================================================================
    _draw_summary_table(pdf, datos_sesion)

    # =========================================================================
    # 5. TABLA DETALLADA DE OPERACIONES AUDITADAS
    # =========================================================================
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*COLOR_BLACK)
    pdf.cell(0, 8, "Detalle de Operaciones", ln=1, align="L")
    pdf.ln(1)

    # Cabecera
    pdf.set_fill_color(*COLOR_OXFORD)
    pdf.set_text_color(*COLOR_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(18, 7, "Hora", border=1, align="C", fill=True)
    pdf.cell(34, 7, "Activo", border=1, align="C", fill=True)
    pdf.cell(22, 7, "Tipo", border=1, align="C", fill=True)
    pdf.cell(24, 7, "Inversion", border=1, align="C", fill=True)
    pdf.cell(32, 7, "Resultado", border=1, align="C", fill=True)
    pdf.cell(60, 7, "Profit / Loss", border=1, align="C", fill=True, ln=1)

    # Filas
    pdf.set_font("Helvetica", "", 8)

    if not operaciones:
        pdf.set_text_color(*COLOR_MUTED)
        pdf.cell(190, 8, "Sin operaciones registradas en esta sesion.", border=1, align="C", ln=1)
    else:
        for idx, op in enumerate(operaciones):
            if pdf.get_y() + 7 > 265:
                pdf.add_page()
                pdf.set_fill_color(*COLOR_OXFORD)
                pdf.set_text_color(*COLOR_WHITE)
                pdf.set_font("Helvetica", "B", 8)
                pdf.cell(18, 7, "Hora", border=1, align="C", fill=True)
                pdf.cell(34, 7, "Activo", border=1, align="C", fill=True)
                pdf.cell(22, 7, "Tipo", border=1, align="C", fill=True)
                pdf.cell(24, 7, "Inversion", border=1, align="C", fill=True)
                pdf.cell(32, 7, "Resultado", border=1, align="C", fill=True)
                pdf.cell(60, 7, "Profit / Loss", border=1, align="C", fill=True, ln=1)
                pdf.set_font("Helvetica", "", 8)

            bg = COLOR_BG_LIGHT if idx % 2 == 0 else COLOR_WHITE
            pdf.set_fill_color(*bg)
            pdf.set_draw_color(*COLOR_BORDER)

            hora = op.get("hora", "")
            activo = op.get("activo", "")
            tipo = op.get("tipo", "").upper()
            inversion = f"${op.get('inversion', 0.0):.2f}"
            resultado = op.get("resultado", "").upper()
            profit_val = op.get("profit", 0.0)

            res_color = COLOR_BLACK
            if "GANADA" in resultado:
                res_color = COLOR_GREEN
            elif "PERDIDA" in resultado:
                res_color = COLOR_RED

            profit_text = f"${profit_val:+.2f}" if profit_val != 0 else "$0.00"
            profit_color = COLOR_GREEN if profit_val > 0 else (COLOR_RED if profit_val < 0 else COLOR_MUTED)

            pdf.set_text_color(*COLOR_BLACK)
            pdf.cell(18, 6.5, hora, border=1, align="C", fill=True)
            pdf.cell(34, 6.5, f" {activo}", border=1, align="L", fill=True)

            tipo_color = COLOR_GREEN if tipo == "CALL" else COLOR_RED
            pdf.set_text_color(*tipo_color)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(22, 6.5, tipo, border=1, align="C", fill=True)

            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*COLOR_BLACK)
            pdf.cell(24, 6.5, inversion, border=1, align="R", fill=True)

            pdf.set_text_color(*res_color)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(32, 6.5, resultado, border=1, align="C", fill=True)

            pdf.set_text_color(*profit_color)
            pdf.cell(60, 6.5, profit_text, border=1, align="R", fill=True, ln=1)
            pdf.set_font("Helvetica", "", 8)

    # =========================================================================
    # 6. DISCLAIMER LEGAL
    # =========================================================================
    if pdf.get_y() + 25 > 265:
        pdf.add_page()

    pdf.ln(6)
    pdf.set_fill_color(*COLOR_BG_LIGHT)
    pdf.set_draw_color(*COLOR_BLUE_CORP)
    pdf.set_line_width(0.4)
    pdf.rect(10, pdf.get_y(), 190, 16, style="DF")

    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(*COLOR_BLUE_CORP)
    pdf.text(13, pdf.get_y() + 4, "DECLARACION DE RIESGO Y METODOLOGIA CUANTITATIVA")

    pdf.set_font("Helvetica", "I", 6)
    pdf.set_text_color(*COLOR_MUTED)
    pdf.text(13, pdf.get_y() + 7.5, "Este documento representa una auditoria automatica de transacciones ejecutadas en IQ Option mediante algoritmos probabilisticos.")
    pdf.text(13, pdf.get_y() + 10.5, "Las decisiones operativas se fundamentan en simulaciones de Monte Carlo vectorizadas (50,000 iteraciones) y estimaciones estocasticas")
    pdf.text(13, pdf.get_y() + 13.5, "del drift de micro-tendencia utilizando Media Movil Exponencialmente Ponderada (EWMA). El trading conlleva riesgos financieros elevados.")

    # Guardar
    pdf.output(ruta_salida)
    logger.info(f"Reporte PDF generado exitosamente en: {ruta_salida}")
    return ruta_salida


def crear_reporte(
    mercado: str,
    x0: float,
    x_final: float,
    rendimiento: float,
    total_ops: int,
    ganadas: int,
    perdidas: int,
    empates: int
) -> None:
    """Wrapper heredado para compatibilidad con CLI."""
    carpeta = "Reportes_Inversion"
    os.makedirs(carpeta, exist_ok=True)

    ahora = datetime.now()
    fecha_str = ahora.strftime("%Y-%m-%d")
    hora_str = ahora.strftime("%H-%M-%S")
    nombre_archivo = f"{mercado}_{fecha_str}_{hora_str}.pdf"
    ruta_completa = os.path.join(carpeta, nombre_archivo)

    datos = {
        "cuenta_id": "Usuario CLI Standalone",
        "tipo_cuenta": "PRACTICE",
        "fecha_inicio": ahora.strftime("%d/%m/%Y %H:%M:%S"),
        "fecha_fin": ahora.strftime("%d/%m/%Y %H:%M:%S"),
        "x0": x0,
        "x_final": x_final,
        "rendimiento": rendimiento,
        "total_ops": total_ops,
        "ganadas": ganadas,
        "perdidas": perdidas,
        "empates": empates,
    }

    generar_reporte_pdf(datos, [], ruta_completa)
