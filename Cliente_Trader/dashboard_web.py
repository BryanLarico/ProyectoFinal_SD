# dashboard_web.py
# ====================================================================
# Panel de Control Web — Flask + Chart.js + Multi-Mercado
# Sin Tkinter. Corre en navegador (localhost:8080).
# pip install flask && python dashboard_web.py
# ====================================================================

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, render_template_string, request, send_from_directory
from iqoptionapi.stable_api import IQ_Option

import generarPDF
import iq_option
import registro_operaciones
import user
from algoritmos import obtener_lista

# ---------------------------------------------------------------------------
# ESTADO COMPARTIDO — locks separados por categoria (minimiza contencion)
# ---------------------------------------------------------------------------
_lock_meta = threading.Lock()
_lock_ops = threading.Lock()
_lock_logs = threading.Lock()
_lock_pnl = threading.Lock()

_meta: Dict[str, Any] = {
    "connected": False, "balance": 0.0, "balance_inicial": 0.0, "rendimiento": 0.0,
    "total_ops": 0, "ganadas": 0, "perdidas": 0, "empates": 0,
    "bot_activo": False, "bots_pendientes": 0, "bots_activos": 0, "tipo_cuenta": "PRACTICE",
    "simbolo_moneda": "$",
    "activo": "EURUSD-OTC", "activos": [], "mercados_operando": [],
    "maestro_verificado": False, "codigo_maestro": "",
}
_operaciones: List[Dict[str, Any]] = []
_logs: List[Dict[str, Any]] = []
_pnl_history: List[float] = [0.0]

MAX_LOGS, MAX_OPS = 200, 200


def _update_meta(**kw):
    with _lock_meta:
        _meta.update(kw)


def _append_log(level: str, msg: str):
    with _lock_logs:
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": msg})
        if len(_logs) > MAX_LOGS:
            _logs[:] = _logs[-MAX_LOGS:]


def _append_op(op: dict, **persist_extras):
    with _lock_ops:
        _operaciones.append(op)
        if len(_operaciones) > MAX_OPS:
            _operaciones[:] = _operaciones[-MAX_OPS:]
    # Persistir al JSON histórico
    try:
        registro_operaciones.guardar_operacion(op, **persist_extras)
    except Exception:
        pass


def _append_pnl(val: float):
    with _lock_pnl:
        _pnl_history.append(val)
        if len(_pnl_history) > 200:
            _pnl_history[:] = _pnl_history[-200:]


def _snapshot() -> str:
    """Snapshot rapido: copia bajo locks y devuelve JSON string."""
    with _lock_meta:
        m = dict(_meta)
    with _lock_ops:
        ops = list(_operaciones)
    with _lock_logs:
        logs = list(_logs)
    with _lock_pnl:
        pnl = list(_pnl_history)
    return json.dumps({"meta": m, "ops": ops[-40:], "logs": logs[-20:], "pnl": pnl})


# ---------------------------------------------------------------------------
# FLASK APP
# ---------------------------------------------------------------------------
app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QUANT-BOT — Panel de Trading</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,sans-serif;background:#0A0A0F;color:#E8E8ED;display:flex;flex-direction:column;height:100vh}
.nav-top{background:#121218;border-bottom:1px solid #1E1E28;padding:0 24px;display:flex;align-items:center;gap:0;flex-shrink:0}
.nav-top .nb{color:#00B074;font-size:18px;font-weight:800;margin-right:32px;letter-spacing:-0.5px}
.nav-top a{color:#6B6B78;text-decoration:none;padding:14px 20px;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:2px solid transparent;transition:all .2s}
.nav-top a:hover{color:#E8E8ED}
.nav-top a.act{color:#00B074;border-bottom-color:#00B074}
.main-wrap{display:flex;flex:1;overflow:hidden}
#sb{width:340px;min-width:340px;background:linear-gradient(145deg,#141420,#18182A);border-right:1px solid #252535;padding:20px;display:flex;flex-direction:column;overflow-y:auto}
#sb h1{color:#00B074;font-size:22px;margin-bottom:4px;font-weight:800;letter-spacing:-0.5px}
#sb .st{color:#6B6B78;font-size:12px;margin-bottom:14px;font-weight:600}
#mn{flex:1;display:flex;flex-direction:column;padding:20px;overflow-y:auto;background:#0A0A0F}
.cr{display:flex;gap:12px;margin-bottom:12px}
.cd{flex:1;background:linear-gradient(145deg,#141420,#18182A);border:1px solid #252535;border-radius:12px;padding:16px 18px}
.cd .lb{font-size:11px;font-weight:700;color:#6B6B78;text-transform:uppercase;letter-spacing:0.5px}
.cd .vl{font-size:26px;font-weight:800;margin-top:4px;letter-spacing:-0.5px}
.rp{display:flex;gap:12px;flex:1;min-height:0;margin-bottom:12px}
#ch{flex:3;background:linear-gradient(145deg,#141420,#18182A);border:1px solid #252535;border-radius:12px;padding:14px;display:flex;flex-direction:column}
#ch h3{font-size:12px;color:#6B6B78;margin-bottom:6px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px}
#ch canvas{flex:1;min-height:140px}
#tb{flex:2;background:linear-gradient(145deg,#141420,#18182A);border:1px solid #252535;border-radius:12px;padding:14px;display:flex;flex-direction:column;overflow:hidden;min-width:300px}
#tb h3{font-size:12px;color:#6B6B78;margin-bottom:6px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px}
#tbl{flex:1;overflow-y:auto;font:13px 'Courier New',monospace;line-height:1.7;color:#E8E8ED}
.trow{padding:3px 0;border-bottom:1px solid #1A1A2A}
#lg{background:linear-gradient(145deg,#141420,#18182A);border:1px solid #252535;border-radius:12px;padding:14px;min-height:100px;max-height:180px;overflow-y:auto;font:12px 'Courier New',monospace;line-height:1.6;color:#E8E8ED}
.fs{border:1px solid #252535;border-radius:8px;padding:10px 12px;margin-bottom:12px}
.fs legend{color:#6B6B78;font-size:11px;font-weight:700;padding:0 6px;text-transform:uppercase;letter-spacing:0.5px}
.fr{margin-bottom:8px}
.fr label{display:block;font-size:11px;font-weight:700;color:#6B6B78;margin-bottom:3px;text-transform:uppercase;letter-spacing:0.5px}
.fr input,.fr select{width:100%;padding:8px 10px;border-radius:6px;border:1px solid #252535;background:#0A0A0F;color:#E8E8ED;font-size:13px;font-family:'Inter',sans-serif}
.fr select{appearance:none;cursor:pointer}
.btn{width:100%;padding:12px;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;margin-bottom:8px;color:#fff;transition:all 0.2s;text-transform:uppercase;letter-spacing:0.5px}
.bg{background:linear-gradient(135deg,#00B074,#00D68F)}.bg:hover{transform:translateY(-1px);box-shadow:0 4px 15px rgba(0,176,116,.3)}
.br{background:linear-gradient(135deg,#FF3B30,#FF6B60)}.br:hover{transform:translateY(-1px);box-shadow:0 4px 15px rgba(255,59,48,.3)}
.bk{background:transparent;border:1px solid #252535;color:#E8E8ED}.bk:hover{border-color:#6B6B78}
.bb{background:linear-gradient(135deg,#0066FF,#3388FF)}.bb:hover{transform:translateY(-1px);box-shadow:0 4px 15px rgba(0,102,255,.3)}
.tgl{display:flex;align-items:center;gap:6px;margin-bottom:10px;font-size:13px}
.tgl input[type=checkbox]{width:18px;height:18px;accent-color:#00B074}
.gr{color:#00D68F}.rd{color:#FF6B60}.mu{color:#6B6B78}
.bdg{display:inline-block;padding:3px 8px;border-radius:4px;font-size:11px;font-weight:700}
/* Modal */
.modal{display:flex;position:fixed;z-index:99;left:0;top:0;width:100%;height:100%;background:rgba(0,0,0,0.85)}
.modal-content{background:linear-gradient(145deg,#141420,#18182A);border:1px solid #252535;border-radius:12px;padding:28px 32px;width:460px;margin:12% auto;text-align:center}
.modal-content h2{color:#00B074;margin-bottom:12px;font-size:20px;font-weight:800;letter-spacing:-0.5px}
.modal-content p{color:#6B6B78;font-size:13px;margin-bottom:18px}
.modal-content input{width:100%;padding:10px;border-radius:6px;border:1px solid #252535;background:#0A0A0F;color:#E8E8ED;font-size:15px;margin-bottom:14px;text-align:center;font-family:'Inter',sans-serif}
.modal-content .btn{margin:5px 0}
</style></head>
<body>

<div class="nav-top">
  <span class="nb">QUANT-BOT</span>
  <a href="/" class="act">TRADING EN VIVO</a>
  <a href="/analytics">ANALYTICS & HISTORIAL</a>
</div>

<div class="modal" id="maestroModal">
<div class="modal-content">
<h2>CONEXION A SERVIDOR MAESTRO</h2>
<p>Ingrese el codigo de conexion proporcionado por el Nodo Maestro,<br>o continue en <b>Modo Autonomo</b> sin Copiado de Operaciones.</p>
<input type="text" id="codigoMaestro" placeholder="Codigo de Sala (opcional)">
<button class="btn bg" onclick="conectarMaestro()">CONECTAR AL MAESTRO</button>
<button class="btn bk" onclick="saltarMaestro()">CONTINUAR SIN MAESTRO (Autonomo)</button>
</div></div>
<div class="main-wrap">
<div id="sb">
<h1>NODO CLIENTE QUANT</h1>
<div class="st">Trading Algoritmico & Monte Carlo</div>
<fieldset class="fs"><legend>ESTADO</legend>
<div style="font-size:11px;color:#8E8E93">Usuario: {{ user_email }}</div>
<div style="font-size:11px">Maestro: <span id="mst" class="mu">Autonomo</span></div>
<div style="font-size:11px" id="botsInfo" class="mu"></div>
</fieldset>
<fieldset class="fs"><legend>PARAMETROS</legend>
<div class="fr"><label>Activo Principal</label><select id="activo"><option>EURUSD-OTC</option></select></div>
<div class="fr"><label>Algoritmo</label><select id="algoritmo">
{% for a in algoritmos_lista %}<option value="{{ a.id }}">{{ a.nombre }}</option>
{% endfor %}</select></div>
<div class="fr"><label>Tipo de Cuenta</label>
<select id="tipoCuenta" onchange="cambiarCuenta(this.value)"><option value="PRACTICE">PRACTICA (Demo)</option><option value="REAL">REAL (Riesgo)</option></select></div>
<div class="fr"><label>Inversion Fija (USD)</label><input id="inv" type="number" value="4" min="1"></div>
<div class="fr"><label>Limite de Perdida (%)</label><input id="sl" type="number" value="1.00" step="0.01"></div>
<div class="fr"><label>Toma de Ganancia (%)</label><input id="tp" type="number" value="0.50" step="0.01"></div>
<div class="fr"><label>Expiracion (min)</label><input id="exp" type="number" value="1" min="1"></div>
</fieldset>
<button id="btnBot" class="btn bg" onclick="toggleBot()">INICIAR BOT AUTOMATICO</button>
<button class="btn bk" onclick="genPDF()">GENERAR REPORTE PDF</button>
<div style="display:flex;gap:6px">
<button class="btn bg" style="flex:1;font-size:12px" onclick="orden('call')">CALL</button>
<button class="btn br" style="flex:1;font-size:12px" onclick="orden('put')">PUT</button>
</div>
</div>

<div id="mn">
<div class="cr">
<div class="cd"><div class="lb">SALDO ACTUAL</div><div class="vl gr" id="vSaldo">---</div></div>
<div class="cd"><div class="lb">OPERACIONES</div><div class="vl" id="vOps">0 G / 0 P / 0 E</div></div>
<div class="cd"><div class="lb">RENDIMIENTO NETO</div><div class="vl" id="vRend">$0.00</div></div>
<div class="cd"><div class="lb">ESTADO</div><div class="vl mu" id="vStatus">INACTIVO</div></div>
</div>
<div class="rp">
<div id="ch"><h3>RENDIMIENTO ACUMULADO (USD)</h3><canvas id="pnlCnv"></canvas></div>
<div id="tb"><h3>ULTIMAS OPERACIONES</h3><div id="tbl"></div></div>
</div>
<div id="lg"></div>
</div>
</div><!-- /main-wrap -->

 <script>
var chart=null,abort=new AbortController();
var simb="$";

function ocultarModal(){var m=document.getElementById('maestroModal');if(m)m.style.display='none';}
function conectarMaestro(){
  ocultarModal();
  var c=document.getElementById('codigoMaestro');var v=c?c.value.trim():"";
  fetch('/api/maestro',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codigo:v})});
}
function saltarMaestro(){
  ocultarModal();
  fetch('/api/maestro',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codigo:""})});
}

function initChart(){
  var ctx=document.getElementById('pnlCnv');
  if(!ctx)return;
  chart=new Chart(ctx.getContext('2d'),{
    type:'line',
    data:{labels:[],datasets:[{label:'P&L',data:[],borderColor:'#00B074',borderWidth:2,pointRadius:0,fill:{target:'origin',below:'rgba(0,176,116,0.08)',above:'rgba(0,176,116,0.08)'},tension:0.1}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:false},y:{grid:{color:'#252535'},ticks:{color:'#6B6B78',font:{size:12},callback:function(v){return simb+v.toFixed(2)}}}},animation:{duration:150}}
  });
}

async function poll(){
  try{
    abort.abort();abort=new AbortController();
    var r=await fetch('/api/state',{signal:abort.signal});
    var s=await r.json();
    var m=s.meta,ops=s.ops||[],logs=s.logs||[],pnl=s.pnl||[];
    simb=m.simbolo_moneda||"$";

    var el=document.getElementById('vSaldo');if(el){el.textContent=simb+m.balance.toFixed(2);el.className='vl '+(m.rendimiento>=0?'gr':'rd');}
    el=document.getElementById('vOps');if(el)el.textContent=m.ganadas+' G / '+m.perdidas+' P / '+m.empates+' E';
    el=document.getElementById('vRend');if(el){var rd=m.rendimiento;el.textContent=(rd>=0?'+':'')+simb+rd.toFixed(2);el.className='vl '+(rd>=0?'gr':'rd');}
    el=document.getElementById('vStatus');if(el){
      if(m.bot_activo===true){el.textContent='BOT OPERANDO';el.className='vl gr';}
      else if(m.bot_activo==='deteniendo'){el.textContent='FINALIZANDO...';el.className='vl mu';}
      else if(m.connected){el.textContent='SISTEMA ACTIVO';el.className='vl gr';}
      else{el.textContent='INACTIVO';el.className='vl mu';}
    }
    el=document.getElementById('btnBot');if(el){
      if(m.bot_activo===true){el.textContent='DETENER BOT';el.className='btn br';el.disabled=false;}
      else if(m.bot_activo==='deteniendo'){el.textContent='FINALIZANDO...';el.className='btn bk';el.disabled=true;}
      else{el.textContent='INICIAR BOT AUTOMATICO';el.className='btn bg';el.disabled=false;}
    }

    if(chart&&pnl.length>0){
      chart.data.labels=pnl.map(function(_,i){return i;});
      chart.data.datasets[0].data=pnl;
      chart.data.datasets[0].borderColor=(pnl[pnl.length-1]>=0?'#00B074':'#FF3B30');
      chart.update('none');
    }

    el=document.getElementById('tbl');if(el){
      var rows='';
      for(var i=ops.length-1;i>=Math.max(0,ops.length-35);i--){
        var o=ops[i],p=o.profit||0,pc=p>0?'gr':(p<0?'rd':'mu');
        var rc=String(o.resultado).indexOf('GANADA')>=0?'gr':String(o.resultado).indexOf('PERDIDA')>=0?'rd':'mu';
        rows+='<div class="trow"><span class="mu">'+o.hora+'</span> &nbsp;<span>'+String(o.activo).substring(0,12)+'</span> &nbsp;<span class="'+(o.tipo==='CALL'?'gr':'rd')+'"><b>'+o.tipo+'</b></span> &nbsp;'+simb+Number(o.inversion).toFixed(2)+' &nbsp;<span class="'+rc+'"><b>'+o.resultado+'</b></span> &nbsp;<span class="'+pc+'">'+(p!=0?simb+p.toFixed(2):simb+'0.00')+'</span></div>';
      }
      el.innerHTML=rows||'<span class="mu">Sin operaciones...</span>';
    }

    el=document.getElementById('lg');if(el){
      var lr='';
      for(var j=logs.length-1;j>=0;j--){
        var l=logs[j],lc=l.level==='ERROR'||l.level==='ALERTA'?'rd':l.level==='OK'?'gr':'mu';
        lr=lr+'<span class="mu">['+l.time+']</span> <span class="'+lc+'">['+l.level+']</span> '+l.msg+'<br>';
      }
      el.innerHTML=lr;
    }
  }catch(e){if(e.name!=='AbortError')console.error(e)}
  setTimeout(poll,800);
}

function toggleBot(){
  fetch('/api/toggle_bot',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      inv:document.getElementById('inv').value,
      sl:document.getElementById('sl').value,
      tp:document.getElementById('tp').value,
      exp:document.getElementById('exp').value,
      activo:document.getElementById('activo').value,
      cuenta:document.getElementById('tipoCuenta').value,
      algoritmo:document.getElementById('algoritmo').value
    })
  });
}
function orden(dir){
  fetch('/api/orden_manual',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({dir:dir,inv:document.getElementById('inv').value,exp:document.getElementById('exp').value})
  });
}
function genPDF(){fetch('/api/generar_pdf',{method:'POST'});}
function cambiarCuenta(tipo){fetch('/api/cambiar_cuenta',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cuenta:tipo})});}

window.onload=function(){initChart();poll();}
</script>
</body></html>"""


@app.route("/")
def index():
    return render_template_string(HTML, user_email=user.EMAIL, algoritmos_lista=obtener_lista())


@app.route("/api/state")
def api_state():
    return _snapshot(), 200, {"Content-Type": "application/json"}


@app.route("/api/maestro", methods=["POST"])
def api_maestro():
    data = request.get_json(force=True)
    codigo = data.get("codigo", "")
    if codigo:
        _update_meta(maestro_verificado=True, codigo_maestro=codigo)
        _append_log("OK", f"Conectado al Maestro [{codigo}].")
    else:
        _update_meta(maestro_verificado=False, codigo_maestro="")
        _append_log("INFO", "Modo Autonomo.")
    return '{"ok":true}'


@app.route("/api/toggle_bot", methods=["POST"])
def api_toggle_bot():
    data = request.get_json(force=True)
    activo = data.get("activo", _meta["activo"])
    cuenta = data.get("cuenta", "PRACTICE")
    algoritmo_id = data.get("algoritmo", "montecarlo")
    inv = int(data.get("inv", 4))
    sl = float(data.get("sl", 1.0))
    tp = float(data.get("tp", 0.5))
    exp = int(data.get("exp", 1))

    _update_meta(activo=activo, tipo_cuenta=cuenta)

    if not _meta["bot_activo"]:
        trade_logic.start_bot(activo, cuenta, inv, sl, tp, exp, algoritmo_id)
    else:
        _update_meta(bot_activo="deteniendo")
        _append_log("ALERTA", "Solicitando parada. Finalizando operaciones en curso...")
        trade_logic.stop_bots()
    return '{"ok":true}'


@app.route("/api/orden_manual", methods=["POST"])
def api_orden_manual():
    data = request.get_json(force=True)
    trade_logic.orden_manual(data.get("dir", "call"), int(data.get("inv", 4)), int(data.get("exp", 1)))
    return '{"ok":true}'


@app.route("/api/generar_pdf", methods=["POST"])
def api_generar_pdf():
    trade_logic.gen_pdf()
    return '{"ok":true}'


@app.route("/api/cambiar_cuenta", methods=["POST"])
def api_cambiar_cuenta():
    data = request.get_json(force=True)
    trade_logic.cambiar_cuenta(data.get("cuenta", "PRACTICE"))
    return '{"ok":true}'


# ===========================================================================
# ANALYTICS ENDPOINTS
# ===========================================================================
@app.route("/analytics")
def analytics_page():
    return render_template("analytics.html")


@app.route("/api/analytics/query", methods=["POST"])
def api_analytics_query():
    data = request.get_json(force=True)
    fi = data.get("fecha_inicio") or None
    ff = data.get("fecha_fin") or None
    hi = data.get("hora_inicio") or None
    hf = data.get("hora_fin") or None
    ops = registro_operaciones.consultar_operaciones(fi, ff, hi, hf)
    kpis = registro_operaciones.obtener_kpis(ops)
    por_activo = registro_operaciones.obtener_resumen_por_activo(ops)
    pnl_temporal = registro_operaciones.obtener_pnl_temporal(ops)
    por_hora = registro_operaciones.obtener_distribucion_horaria(ops)
    return jsonify({
        "operaciones": ops,
        "kpis": kpis,
        "por_activo": por_activo,
        "pnl_temporal": pnl_temporal,
        "por_hora": por_hora,
    })


@app.route("/api/analytics/report", methods=["POST"])
def api_analytics_report():
    data = request.get_json(force=True)
    fi = data.get("fecha_inicio") or None
    ff = data.get("fecha_fin") or None
    hi = data.get("hora_inicio") or None
    hf = data.get("hora_fin") or None
    ops = registro_operaciones.consultar_operaciones(fi, ff, hi, hf)
    if not ops:
        return jsonify({"error": "No hay operaciones en este rango"}), 400
    kpis = registro_operaciones.obtener_kpis(ops)
    datos_sesion = {
        "cuenta_id": user.EMAIL,
        "tipo_cuenta": _meta.get("tipo_cuenta", "PRACTICE"),
        "fecha_inicio": fi or "Inicio",
        "fecha_fin": ff or "Fin",
        "x0": 0.0,
        "x_final": kpis["pnl_neto"],
        "rendimiento": kpis["pnl_neto"],
        "total_ops": kpis["total_ops"],
        "ganadas": kpis["ganadas"],
        "perdidas": kpis["perdidas"],
        "empates": kpis["empates"],
    }
    os.makedirs("Reportes_Inversion", exist_ok=True)
    nombre = f"Analytics_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.pdf"
    ruta = os.path.join("Reportes_Inversion", nombre)
    try:
        generarPDF.generar_reporte_pdf(datos_sesion, ops, ruta)
        return jsonify({"ok": True, "url": f"/api/analytics/download/{nombre}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics/download/<filename>")
def api_analytics_download(filename):
    return send_from_directory("Reportes_Inversion", filename, as_attachment=True)

# ===========================================================================
# LOGICA DE TRADING
# ===========================================================================
class TradingLogic:
    def __init__(self):
        self.api: Optional[IQ_Option] = None
        self.api_connected = False
        self.bot_stop = threading.Event()
        self.bot_threads: List[threading.Thread] = []

    def log(self, level: str, msg: str):
        _append_log(level, msg)

    def start(self):
        threading.Thread(target=self._conectar, daemon=True).start()

    def _conectar(self):
        try:
            self.log("INFO", "Conectando al servidor financiero...")
            api = IQ_Option(user.EMAIL, user.PASSWORD)
            ok, msg = api.connect()
            if ok:
                self.api = api
                self.api_connected = True
                api.change_balance("PRACTICE")
                saldo = api.get_balance()
                _update_meta(connected=True, balance=saldo, balance_inicial=saldo, rendimiento=0.0, simbolo_moneda="$")
                _update_meta(activos=["EURUSD-OTC"], activo="EURUSD-OTC")
                self.log("OK", "Conexion WebSocket establecida. EURUSD-OTC listo.")
            else:
                self.log("ERROR", f"Fallo conexion: {msg}")
        except Exception as e:
            self.log("ERROR", f"Excepcion conexion: {e}")

    # ------------------------------------------------------------------
    # BOT UNICO
    # ------------------------------------------------------------------
    def start_bot(self, activo: str, cuenta: str, inv: int, sl: float, tp: float, exp: int, algoritmo_id: str = "montecarlo"):
        if not self.api_connected or not self.api:
            self.log("ERROR", "Sin conexion API.")
            return

        self.log("INFO", f"Iniciando bot en: {activo} | Algoritmo: {algoritmo_id}")
        _update_meta(bot_activo=True, bots_activos=1,
                      mercados_operando=[activo], bots_pendientes=1)

        self.bot_stop.clear()

        if self.api:
            try:
                self.api.change_balance(cuenta)
                bal = self.api.get_balance()
                simb = "S/" if cuenta == "REAL" else "$"
                _update_meta(balance_inicial=bal, balance=bal, rendimiento=0.0,
                              tipo_cuenta=cuenta, simbolo_moneda=simb)
            except Exception:
                pass

        t = threading.Thread(
            target=self._bot_worker, args=(activo, cuenta, inv, sl, tp, exp, algoritmo_id), daemon=True
        )
        t.start()
        self.bot_threads.append(t)

    def stop_bots(self):
        self.log("ALERTA", "Parando bot...")
        self.bot_stop.set()

    def cambiar_cuenta(self, cuenta: str):
        if not self.api_connected or not self.api:
            return
        self.api.change_balance(cuenta)
        s = self.api.get_balance()
        simb = "S/" if cuenta == "REAL" else "$"
        _update_meta(balance=s, balance_inicial=s, rendimiento=0.0, tipo_cuenta=cuenta, simbolo_moneda=simb)
        self.log("INFO", f"Cuenta cambiada a {cuenta}. Saldo: {simb}{s:.2f}")

    def _bot_worker(self, activo: str, cuenta: str, inv: int, sl: float, tp: float, exp: int, algoritmo_id: str):
        """Un bot por mercado. Callbacks ligeros, sin get_balance() en cada log."""

        def log_cb(nivel: str, msg: str):
            _append_log(nivel, f"[{activo}] {msg}")
            # Refrescar saldo cuando se acepta una orden (refleja deduccion inmediata)
            if "Orden aceptada" in msg:
                if self.api_connected and self.api:
                    try:
                        bal = self.api.get_balance()
                        rend = bal - _meta["balance_inicial"]
                        _update_meta(balance=bal, rendimiento=rend)
                    except Exception:
                        pass

        def op_cb(op_dict: dict):
            op_dict["activo"] = activo
            saldo_post = 0.0
            if self.api_connected and self.api:
                try:
                    saldo_post = self.api.get_balance()
                except Exception:
                    pass
            _append_op(op_dict, algoritmo=algoritmo_id,
                       tipo_cuenta=cuenta, saldo_post=saldo_post)
            pnl_acum = (_pnl_history[-1] if _pnl_history else 0) + op_dict.get("profit", 0)
            _append_pnl(pnl_acum)
            # Actualizar contadores desde el resultado real de la operacion
            res = op_dict.get("resultado", "").upper()
            with _lock_meta:
                _meta["total_ops"] += 1
                if "GANADA" in res:
                    _meta["ganadas"] += 1
                elif "PERDIDA" in res:
                    _meta["perdidas"] += 1
                else:
                    _meta["empates"] += 1
            # Actualizar balance al completar trade
            if self.api_connected and self.api:
                try:
                    bal = self.api.get_balance()
                    rend = bal - _meta["balance_inicial"]
                    _update_meta(balance=bal, rendimiento=rend)
                except Exception:
                    pass

        try:
            iq_option.ejecutar_bot_completo(
                api=self.api, callback_log=log_cb, evento_parada=self.bot_stop,
                activo=activo, inversion=inv, expiracion=exp, horizonte=50,
                pct_sl=sl, pct_tp=tp, modo_balance=cuenta,
                callback_operacion=op_cb, algoritmo_id=algoritmo_id,
            )
        except Exception as e:
            _append_log("ERROR", f"[{activo}] Bot fallo: {e}")
        finally:
            with _lock_meta:
                _meta["bots_pendientes"] = max(0, _meta.get("bots_pendientes", 1) - 1)
                if _meta["bots_pendientes"] <= 0:
                    _meta["bot_activo"] = False
                    _meta["bots_activos"] = 0
                    _meta["mercados_operando"] = []
            _append_log("INFO", f"[{activo}] Bot detenido.")
            # Auto-generar PDF con historial completo al detener bot
            if _operaciones:
                self.gen_pdf()

    # ------------------------------------------------------------------
    # ORDEN MANUAL
    # ------------------------------------------------------------------
    def orden_manual(self, direction: str, inv: int, exp: int):
        if not self.api_connected or not self.api:
            self.log("ERROR", "Sin conexion API.")
            return
        threading.Thread(target=self._manual_worker, args=(direction, inv, exp), daemon=True).start()

    def _manual_worker(self, direction: str, inv: int, exp: int):
        activo = _meta["activo"]
        try:
            ok, oid = self.api.buy(inv, activo, direction, exp)
            if ok:
                _append_log("OK", f"[MANUAL] {direction.upper()} en {activo}. ID: {oid}")
                res = self.api.check_win_v3(oid)
                with _lock_meta:
                    _meta["total_ops"] += 1
                    if res < 0: _meta["perdidas"] += 1
                    elif res > 0: _meta["ganadas"] += 1
                    else: _meta["empates"] += 1
                rs = "GANADA" if res > 0 else ("PERDIDA" if res < 0 else "EMPATE")
                op = {"hora": datetime.now().strftime("%H:%M:%S"), "activo": activo,
                       "tipo": direction.upper(), "inversion": inv, "resultado": rs, "profit": res}
                saldo_post = 0.0
                if self.api:
                    try:
                        saldo_post = self.api.get_balance()
                    except Exception:
                        pass
                _append_op(op, algoritmo="manual",
                           tipo_cuenta=_meta.get("tipo_cuenta", "PRACTICE"),
                           saldo_post=saldo_post)
                pnl_acum = (_pnl_history[-1] if _pnl_history else 0) + res
                _append_pnl(pnl_acum)
                if self.api:
                    bal = self.api.get_balance()
                    rend = bal - _meta["balance_inicial"]
                    _update_meta(balance=bal, rendimiento=rend)
                _append_log("INFO" if res == 0 else ("OK" if res > 0 else "ALERTA"),
                            f"[MANUAL] {rs}: {_meta.get('simbolo_moneda','$')}{res:.2f}")
            else:
                _append_log("ERROR", "[MANUAL] Orden rechazada.")
        except Exception as e:
            _append_log("ERROR", f"[MANUAL] Excepcion: {e}")

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    def gen_pdf(self):
        if not self.api_connected or not self.api:
            self.log("ERROR", "Sin conexion para PDF.")
            return
        try:
            sf = self.api.get_balance()
            datos = {
                "cuenta_id": user.EMAIL, "tipo_cuenta": _meta["tipo_cuenta"],
                "fecha_inicio": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "fecha_fin": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "x0": _meta["balance_inicial"], "x_final": sf,
                "rendimiento": sf - _meta["balance_inicial"],
                "total_ops": _meta["total_ops"], "ganadas": _meta["ganadas"],
                "perdidas": _meta["perdidas"], "empates": _meta["empates"],
            }
            os.makedirs("Reportes_Inversion", exist_ok=True)
            ruta = os.path.join("Reportes_Inversion",
                f"{_meta['activo']}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.pdf")
            with _lock_ops:
                ops = list(_operaciones)
            generarPDF.generar_reporte_pdf(datos, ops, ruta)
            self.log("OK", f"PDF: {ruta}")
        except Exception as e:
            self.log("ERROR", f"PDF: {e}")


trade_logic = TradingLogic()

_shutdown_flag = False


def _graceful_shutdown(signum=None, frame=None):
    global _shutdown_flag
    if _shutdown_flag:
        os._exit(0)
    _shutdown_flag = True
    print("\n[APAGADO] Ctrl+C detectado. Finalizando bots y conexiones...")
    trade_logic.stop_bots()
    time.sleep(0.3)
    if trade_logic.api_connected and trade_logic.api:
        try:
            trade_logic.api.api.close()
            print("[APAGADO] WebSocket cerrado.")
        except Exception:
            pass
    print("[APAGADO] Servidor detenido.")
    os._exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    print("=" * 55)
    print("  QUANT-BOT PANEL DE CONTROL WEB — http://localhost:8080")
    print("  Multi-mercado · Flask + Chart.js · Sin Tkinter")
    print("  Ctrl+C para detener")
    print("=" * 55)
    trade_logic.start()

    try:
        app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        _graceful_shutdown()
