#!/usr/bin/env python3
"""
Interfaz — Seguidor de satélites, 2 grados de libertad
Proyecto de Diseño Mecatrónica
Integrantes: Juan Andrés Sánchez, Sofía Vega, Andrés Felipe Trujillo

Habla con el PIC16F18446 a 115200 8N1.
Cada muestra llega como:
  B,consigna,posicion,error,mando,E,consigna,posicion,error,mando
B es la base (XD-3420, abajo, 360°, lazo abierto: su posición es la estimada
por la rampa, no la de un encoder). E es el ángulo del NEMA 23 (0° a 90°):
0° es el horizonte y 90° es el cenit. En ese recorrido coincide con la
elevación del telescopio.
La órbita sale del TLE de Celestrak. Skyfield la convierte en azimut y elevación.
"""

import math
import os
import sys
import csv
import threading
import time
import queue
import re
import ctypes
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from orbita import (Orbita, ISS_NORAD, UMBRAL_ELEV, consigna_base, rampa, time_now)
from gemelo import Gemelo


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("[AVISO] pyserial no instalado  →  py -3 -m pip install pyserial")

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("[AVISO] matplotlib no instalado →  py -3 -m pip install matplotlib")


BG      = "#0D1117"
SURFACE = "#161B22"
CARD2   = "#1C2128"
BORDER  = "#30363D"
ACCENT  = "#1F6FEB"
ACCENT2 = "#238636"
CYAN    = "#00D4FF"
WARN    = "#D29922"
DANGER  = "#FF6B35"
PURPLE  = "#BC8CFF"
ORANGE  = "#F0883E"
TEXT    = "#E6EDF3"
TEXTDIM = "#8B949E"
TEXTLOG = "#ADBAC7"

FF  = "Segoe UI"
FS  = 10
FSL = 13
FSH = 22

BAUD_RATE = 115200
BANDA_TE = 0.02
VENTANA_TE = 3.0
PASO_MIN = 1.0
BASE_MIN, BASE_MAX = -360.0, 360.0
ELEV_MIN, ELEV_MAX = 0.0, 90.0
# El NEMA no arranca hasta que la base está a esta distancia del azimut.
# Si después se aleja más de SALIDA_BASE, el NEMA se frena y la base va sola.
LLEGADA_BASE = 3.0
SALIDA_BASE = 8.0
# Rampa de arranque, la misma que trae el PIC al encender.
VEL_MAX_INICIAL = 20.0
ACEL_MAX_INICIAL = 20.0
# Base en lazo abierto, los mismos valores con que arranca el PIC.
BASE_V0_INICIAL = 1.5
BASE_KV_INICIAL = 0.004
POLL_S = 0.05


def paso_rampa(pos, vel, meta, vmax, amax, dt):
    """Un paso de rampa trapezoidal, como la del PIC. Devuelve posición y velocidad."""
    if vmax <= 0:
        return meta, 0.0
    falta = meta - pos
    if abs(falta) < 1e-6 and abs(vel) <= 2 * amax * dt:
        return meta, 0.0
    sentido = 1.0 if falta >= 0 else -1.0
    v = vel * sentido
    dist = abs(falta)
    if v < 0:
        v += amax * dt
    elif v * v >= 2 * amax * dist:
        v = max(0.0, v - amax * dt)
    else:
        v += amax * dt
    v = min(v, vmax)
    if v * dt >= dist and v <= 4 * amax * dt:
        return meta, 0.0
    v *= sentido
    return pos + v * dt, v


def el_a_nema(el_cielo):
    """Ángulo del NEMA para una elevación del cielo. 0° horizonte, 90° cenit."""
    return float(el_cielo)


def nema_a_el(nema):
    """Elevación del telescopio. En este recorrido es el mismo ángulo del NEMA."""
    return float(nema)

UI_SCALE = 1.0

TELEMETRIA_RE = re.compile(
    r"^B,([+-]?\d+\.\d),([+-]?\d+\.\d),([+-]?\d+\.\d),([+-]?\d+\.\d{2}),"
    r"E,([+-]?\d+\.\d),([+-]?\d+\.\d),([+-]?\d+\.\d),([+-]?\d+\.\d{2})$")
ENC_RE = re.compile(r"^([BE])ENC:(-?\d+)$")
AB_RE = re.compile(r"^([BE])AB:([01])([01])$")
NUMERO_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def px(n):
    return int(round(n * UI_SCALE))


def sep_h(parent, pady=4):
    f = tk.Frame(parent, bg=BORDER, height=1)
    f.pack(fill="x", padx=0, pady=pady)
    return f


def card_frame(parent, title, title_color=ACCENT):
    wrapper = tk.Frame(parent, bg=BORDER, bd=0)
    title_bar = tk.Frame(wrapper, bg=CARD2)
    title_bar.pack(fill="x")
    tk.Label(title_bar, text=title, font=(FF, FS, "bold"),
             bg=CARD2, fg=title_color).pack(side="left", padx=10, pady=5)
    body = tk.Frame(wrapper, bg=CARD2)
    body.pack(fill="both", expand=True)
    return wrapper, body


class FlatButton(tk.Frame):
    """Botón de un solo color. El texto y el fondo reciben el clic."""

    def __init__(self, parent, text, command=None,
                 bg_color=ACCENT, fg_color=TEXT,
                 width=160, height=34,
                 font_size=FS, bold=True, **kwargs):
        super().__init__(parent, bg=bg_color,
                         width=px(width), height=px(height),
                         cursor="hand2")
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._bg = bg_color
        self._hbg = self._lighten(bg_color)
        self._fg = fg_color
        self._cmd = command
        self._lbl = tk.Label(
            self, text=text, bg=bg_color, fg=fg_color,
            font=(FF, font_size, "bold" if bold else "normal"),
            cursor="hand2")
        self._lbl.pack(expand=True, fill="both")
        for w in (self, self._lbl):
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))
            w.bind("<Button-1>", lambda _e: self._click())

    @staticmethod
    def _lighten(hex_color):
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "#{:02x}{:02x}{:02x}".format(
            min(255, r + 30), min(255, g + 30), min(255, b + 30))

    def _hover(self, on):
        c = self._hbg if on else self._bg
        self.config(bg=c)
        self._lbl.config(bg=c)

    def _click(self):
        if self._cmd:
            self._cmd()

    def configure_text(self, text):
        self._lbl.config(text=text)

    def set_color(self, bg_color, fg_color=None):
        self._bg = bg_color
        self._hbg = self._lighten(bg_color)
        if fg_color:
            self._fg = fg_color
            self._lbl.config(fg=self._fg)
        self.config(bg=self._bg)
        self._lbl.config(bg=self._bg)


def entry_row(parent, label_text, var, cmd, hint_color=ACCENT, w_label=9):
    row = tk.Frame(parent, bg=CARD2)
    row.pack(fill="x", padx=8, pady=2)
    tk.Label(row, text=label_text, font=(FF, FS - 1),
             bg=CARD2, fg=TEXTDIM, width=w_label,
             anchor="w").pack(side="left")
    FlatButton(row, "▶", command=cmd, bg_color=hint_color, fg_color=BG,
               width=32, height=26, font_size=FS).pack(side="right")
    e = tk.Entry(row, textvariable=var, width=7,
                 font=(FF, FS), bg=SURFACE, fg=TEXT,
                 insertbackground=ACCENT, relief="flat", bd=0,
                 highlightthickness=1, highlightcolor=hint_color,
                 highlightbackground=BORDER)
    e.pack(side="left", fill="x", expand=True, padx=4, ipady=3)
    e.bind("<Return>", lambda _: cmd())
    return e


class SerialWorker(threading.Thread):
    """Lee el puerto en otro hilo. A 150 Hz no se puede hacer desde la ventana."""

    def __init__(self, port, baud, rx_queue):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.rx_queue = rx_queue
        self._tx_queue = queue.Queue()
        self._ser = None
        self._running = False

    def run(self):
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.05)
            self._running = True
            self.rx_queue.put(("CONNECTED", None))
            buf = ""
            while self._running:
                try:
                    msg = self._tx_queue.get_nowait()
                    self._ser.write((msg + "\n").encode("ascii"))
                except queue.Empty:
                    pass
                n = self._ser.in_waiting
                raw = self._ser.read(n if n else 1)
                if not raw:
                    continue
                buf += raw.decode("ascii", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip().replace("\r", "")
                    if line:
                        self.rx_queue.put(("MSG", line))
        except Exception as exc:
            self.rx_queue.put(("ERROR", str(exc)))
        finally:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._running = False

    def send(self, texto):
        self._tx_queue.put(texto)

    def stop(self):
        self._running = False


class SplashFrame(tk.Frame):
    BAR_W = 360

    def __init__(self, parent, on_done):
        super().__init__(parent, bg=BG)
        self._on_done = on_done
        self._progress = 0
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._build()
        self._animate()

    def _build(self):
        outer = tk.Frame(self, bg=BORDER)
        outer.grid(row=0, column=0)
        inner = tk.Frame(outer, bg=CARD2)
        inner.pack(padx=1, pady=1)
        pad = dict(padx=60)
        tk.Frame(inner, bg=CARD2, height=36).pack()
        tk.Label(inner, text="◎", font=(FF, 48), bg=CARD2, fg=ACCENT).pack(**pad)
        tk.Label(inner, text="Seguidor de satélites",
                 font=(FF, FSH, "bold"), bg=CARD2, fg=TEXT).pack(pady=(8, 0), **pad)
        tk.Label(inner, text="D O S   G R A D O S   D E   L I B E R T A D",
                 font=(FF, FSL, "bold"), bg=CARD2, fg=ACCENT).pack(**pad)
        tk.Frame(inner, bg=BORDER, height=1, width=px(380)).pack(pady=22)
        tk.Label(inner, text="Proyecto de Diseño Mecatrónica",
                 font=(FF, FS + 1, "italic"), bg=CARD2, fg=TEXTDIM).pack()
        tk.Frame(inner, bg=CARD2, height=14).pack()
        tk.Label(inner, text="Integrantes", font=(FF, FS, "bold"),
                 bg=CARD2, fg=TEXTDIM).pack()
        for nombre in ("Juan Andrés Sánchez", "Sofía Vega", "Andrés Felipe Trujillo"):
            tk.Label(inner, text=f"  •  {nombre}",
                     font=(FF, FSL), bg=CARD2, fg=TEXT).pack(pady=2)
        tk.Frame(inner, bg=CARD2, height=28).pack()
        bar_outer = tk.Frame(inner, bg=BORDER, height=3, width=px(self.BAR_W))
        bar_outer.pack()
        bar_outer.pack_propagate(False)
        self._bar = tk.Frame(bar_outer, bg=ACCENT, height=3, width=0)
        self._bar.place(x=0, y=0, height=3)
        self._lbl_cargando = tk.Label(
            inner, text="Iniciando...", font=(FF, FS - 1), bg=CARD2, fg=TEXTDIM)
        self._lbl_cargando.pack(pady=6)
        self._btn_cont = FlatButton(
            inner, "  Continuar  →", command=self._on_done,
            bg_color=ACCENT, fg_color=TEXT, width=280, height=56, font_size=FSL + 1)
        self._bottom_space = tk.Frame(inner, bg=CARD2, height=px(36))
        self._bottom_space.pack()

    def _animate(self):
        if self._progress > 100:
            self._lbl_cargando.config(text="Listo")
            self._btn_cont.pack(pady=(10, 0), before=self._bottom_space)
            return
        self._progress += 2
        self._bar.place(x=0, y=0, height=3,
                        width=int(px(self.BAR_W) * self._progress / 100))
        msgs = {0: "Iniciando...", 30: "Cargando módulos...",
                60: "Buscando la órbita de la ISS...", 85: "Preparando interfaz..."}
        for k, v in msgs.items():
            if self._progress >= k:
                self._lbl_cargando.config(text=v)
        self.after(25, self._animate)


class Dial(tk.Canvas):
    """Aguja de un eje. El naranja es la consigna y el cian, la posición."""

    def __init__(self, parent, titulo, modo):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0)
        self._titulo = titulo
        self._modo = modo
        self._pos = None
        self._ref = None
        self.bind("<Configure>", lambda _e: self._dibujar())

    def set_valores(self, pos, ref):
        self._pos = pos
        self._ref = ref
        self._dibujar()

    def _dibujar(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 40 or h < 40:
            return
        cx = w / 2
        cy = h / 2 + 6
        r = min(w, h) * 0.34
        self.create_text(cx, 16, text=self._titulo, fill=TEXT, font=(FF, FS, "bold"))
        self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=BORDER, width=2)
        if self._modo == "azimut":
            self._rosa(cx, cy, r)
        else:
            self._arco_elev(cx, cy, r)
        if self._ref is not None:
            self._aguja(cx, cy, r * 0.72, self._ang(self._ref), ORANGE, 2)
        if self._pos is not None:
            self._aguja(cx, cy, r * 0.88, self._ang(self._pos), CYAN, 3)
            txt = f"{self._pos:.1f}°"
        else:
            txt = "—"
        self.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=TEXT, outline=TEXT)
        self.create_text(cx, cy + r + 18, text=txt, fill=CYAN, font=(FF, FSL, "bold"))

    def _ang(self, grados):
        if self._modo == "azimut":
            return math.radians(grados)
        return math.radians(max(-90.0, min(90.0, grados)))

    def _aguja(self, cx, cy, largo, ang, color, ancho):
        if self._modo == "azimut":
            x = cx + math.sin(ang) * largo
            y = cy - math.cos(ang) * largo
        else:
            x = cx + math.cos(ang) * largo
            y = cy - math.sin(ang) * largo
        self.create_line(cx, cy, x, y, fill=color, width=ancho, capstyle="round")

    def _rosa(self, cx, cy, r):
        for deg, txt in ((0, "N"), (90, "E"), (180, "S"), (270, "O")):
            a = math.radians(deg)
            self.create_text(cx + math.sin(a) * (r - 14),
                             cy - math.cos(a) * (r - 14),
                             text=txt, fill=TEXTDIM, font=(FF, 8, "bold"))
        for deg in range(0, 360, 30):
            a = math.radians(deg)
            interno = r - (8 if deg % 90 == 0 else 4)
            self.create_line(cx + math.sin(a) * interno, cy - math.cos(a) * interno,
                             cx + math.sin(a) * r, cy - math.cos(a) * r,
                             fill=TEXTDIM)

    def _arco_elev(self, cx, cy, r):
        self.create_arc(cx - r, cy - r, cx + r, cy + r,
                        start=-90, extent=180, style="arc", outline=ACCENT, width=3)
        self.create_text(cx, cy + r - 12, text="-90°", fill=TEXTDIM, font=(FF, 8))
        self.create_text(cx + r - 16, cy, text="0°", fill=TEXTDIM, font=(FF, 8))
        self.create_text(cx, cy - r + 14, text="90°", fill=TEXTDIM, font=(FF, 8))


class Escalon:
    """ts del 10 % al 90 %, te al entrar en la banda del 2 %, Mp del sobrepaso."""

    def __init__(self):
        self.reiniciar()

    def reiniciar(self):
        self.t = []
        self.y = []
        self.t0 = None
        self.y0 = 0.0
        self.yf = 0.0
        self.activo = False
        self.fijo = False
        self.marca_ts = None
        self.marca_te = None
        self.ts_s = None
        self.mp_pct = None

    def nuevo(self, y0, yf):
        self.y0 = y0
        self.yf = yf
        self.t = [0.0]
        self.y = [y0]
        self.t0 = time.time()
        self.activo = abs(yf - y0) >= PASO_MIN
        self.fijo = False
        self.marca_ts = None
        self.marca_te = None
        self.ts_s = None
        self.mp_pct = None

    def agregar(self, y):
        if self.activo and not self.fijo and self.t0 is not None:
            self.t.append(time.time() - self.t0)
            self.y.append(y)
            return True
        return False

    def _cruce(self, nivel, sube, ultimo=False):
        hallado = None
        for i in range(1, len(self.y)):
            a, b = self.y[i - 1], self.y[i]
            if b == a:
                continue
            if sube and a < nivel <= b:
                pasa = True
            elif (not sube) and a > nivel >= b:
                pasa = True
            else:
                pasa = False
            if pasa:
                frac = (nivel - a) / (b - a)
                hallado = self.t[i - 1] + frac * (self.t[i] - self.t[i - 1])
                if not ultimo:
                    return hallado
        return hallado

    def evaluar(self):
        if not self.activo or len(self.y) < 2:
            return False
        amp = self.yf - self.y0
        if abs(amp) < PASO_MIN:
            return False
        sube = amp > 0
        banda = BANDA_TE * abs(amp)
        t10 = self._cruce(self.y0 + 0.10 * amp, sube)
        t90 = self._cruce(self.y0 + 0.90 * amp, sube)
        if t10 is not None and t90 is not None and t90 >= t10:
            self.marca_ts = t90
            self.ts_s = t90 - t10
            pico = self.yf - min(self.y) if not sube else max(self.y) - self.yf
            self.mp_pct = max(0.0, pico) / abs(amp) * 100.0
        if abs(self.y[-1] - self.yf) > banda:
            self.marca_te = None
            return False
        borde = (self.yf - banda) if sube else (self.yf + banda)
        te = self._cruce(borde, sube, ultimo=True)
        if te is None or (t90 is not None and te < t90):
            self.marca_te = None
            return False
        self.marca_te = te
        if self.t[-1] >= VENTANA_TE * te:
            self.fijo = True
            self.activo = False
            return True
        return False


class MainFrame(tk.Frame):

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._worker = None
        self._rx_q = queue.Queue()
        self._ui_q = queue.Queue()
        self._orb = Orbita()
        self._modo = None
        self._play_t0 = None
        self._paso_play = None
        self._ultimo_cmd = 0.0
        self._ultimo_cielo = 0.0
        self._cmd_az = 0.0
        self._cmd_el = 0.0
        self._elev_sigue = False
        self._elev_frenado = True
        self._sim_az = 0.0
        self._sim_el = 0.0
        self._rampa_ini = (0.0, 0.0)
        self._rampa_fin = (40.0, 35.0, 30.0)
        self._manual_az = 0.0
        self._manual_el = 0.0
        self._pos_b = None
        self._pos_e = None
        self._ref_b = 0.0
        self._ref_e = 0.0
        self._sat_az = None
        self._sat_el = None
        self._arco = []
        self._texto_cielo = "Buscando la ISS en Celestrak..."
        self._escalon = {"B": Escalon(), "E": Escalon()}
        self._dibujar_escalon = {"B": False, "E": False}
        self._kp = {"B": 1.5, "E": 1.5}
        self._ki = {"B": 0.0, "E": 0.0}
        self._kd = {"B": 0.07, "E": 0.07}
        self._vmax = {"B": VEL_MAX_INICIAL, "E": VEL_MAX_INICIAL}
        self._amax = {"B": ACEL_MAX_INICIAL, "E": ACEL_MAX_INICIAL}
        self._sim_vel = {"B": 0.0, "E": 0.0}
        self._pruebas = []
        self._ventana_pruebas = None
        self._arbol = None
        self._lbls_prom = []
        self._build()
        self._refresh_ports()
        self._bajar_orbita()
        self._poll()

    def _build(self):
        self._build_header()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=(6, 8))
        body.columnconfigure(0, weight=0, minsize=px(500))
        body.columnconfigure(1, weight=0, minsize=px(230))
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=0)
        self._build_left(body)
        self._build_diales(body)
        self._build_graficas(body)
        self._build_log(body)

    def _build_header(self):
        hdr = tk.Frame(self, bg=SURFACE, height=px(52))
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="◎   SEGUIDOR DE SATÉLITES",
                 font=(FF, FSL, "bold"), bg=SURFACE, fg=ACCENT).pack(side="left", padx=16)
        FlatButton(hdr, "PRUEBAS", command=self._abrir_pruebas,
                   bg_color=BORDER, fg_color=TEXT,
                   width=110, height=30).pack(side="left", pady=11)
        self._lbl_status = tk.Label(
            hdr, text="●  DESCONECTADO", font=(FF, FS, "bold"),
            bg=SURFACE, fg=DANGER)
        self._lbl_status.pack(side="right", padx=16)
        tk.Label(hdr, text="115200 8N1", font=(FF, FS - 1),
                 bg=SURFACE, fg=TEXTDIM).pack(side="right", padx=4)
        self._btn_conn = FlatButton(
            hdr, "CONECTAR", command=self._toggle_connect,
            bg_color=ACCENT2, fg_color=TEXT, width=130, height=30)
        self._btn_conn.pack(side="right", padx=6, pady=11)
        self._port_var = tk.StringVar()
        self._port_cb = ttk.Combobox(
            hdr, textvariable=self._port_var, width=10,
            state="readonly", font=(FF, FS))
        self._port_cb.pack(side="right", padx=4)
        tk.Label(hdr, text="Puerto:", font=(FF, FS),
                 bg=SURFACE, fg=TEXTDIM).pack(side="right", padx=(8, 2))
        FlatButton(hdr, "↺", command=self._refresh_ports,
                   bg_color=BORDER, fg_color=TEXT,
                   width=28, height=28, bold=False).pack(side="right", pady=11)

    def _build_left(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=0)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        self._card_parametros(left)
        self._card_trayectoria(left)

    def _card_parametros(self, parent):
        wrap, card = card_frame(parent, "Constantes y parámetros del sistema", ACCENT)
        wrap.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        cols = tk.Frame(card, bg=CARD2)
        cols.pack(fill="x", padx=6, pady=(6, 0))
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)
        abajo = tk.Frame(cols, bg=CARD2)
        arriba = tk.Frame(cols, bg=CARD2)
        abajo.grid(row=0, column=0, sticky="nsew", padx=2)
        arriba.grid(row=0, column=1, sticky="nsew", padx=2)
        self._bloque_eje(abajo, "Abajo  ·  base", "B", ORANGE, BASE_MIN, BASE_MAX)
        self._bloque_eje(arriba, "Arriba  ·  NEMA", "E", CYAN, ELEV_MIN, ELEV_MAX)
        fila = tk.Frame(card, bg=CARD2)
        fila.pack(fill="x", padx=8, pady=(4, 8))
        fila.columnconfigure(0, weight=1)
        fila.columnconfigure(1, weight=1)
        fila.columnconfigure(2, weight=1)
        self._boton_ancho(fila, 0, "PARAR", self._parar, DANGER)
        self._boton_ancho(fila, 1, "LEER ENCODERS", self._leer_encoders, BORDER)
        self._boton_ancho(fila, 2, "SOLTAR NEMA", lambda: self._enviar_simple("EF"), WARN)

    def _bloque_eje(self, parent, titulo, eje, color, minimo, maximo):
        tk.Label(parent, text=titulo, font=(FF, FS, "bold"),
                 bg=CARD2, fg=color).pack(anchor="w", padx=8, pady=(2, 2))
        self.__dict__[f"_kp_{eje}"] = tk.StringVar(value="1.5")
        self.__dict__[f"_ki_{eje}"] = tk.StringVar(value="0")
        self.__dict__[f"_kd_{eje}"] = tk.StringVar(value="0.07")
        self.__dict__[f"_pos_{eje}"] = tk.StringVar(value="0.0")
        entry_row(parent, "Pos NEMA (°):" if eje == "E" else "Pos (°):",
                  self.__dict__[f"_pos_{eje}"],
                  lambda e=eje, lo=minimo, hi=maximo: self._send_pos(e, lo, hi), color)
        if eje == "B":
            self._filas_lazo_abierto(parent)
        else:
            entry_row(parent, "Kp:", self.__dict__[f"_kp_{eje}"],
                      lambda e=eje: self._send_ganancia(e, "Kp", self.__dict__[f"_kp_{eje}"], 20.0),
                      PURPLE)
            entry_row(parent, "Ki:", self.__dict__[f"_ki_{eje}"],
                      lambda e=eje: self._send_ganancia(e, "Ki", self.__dict__[f"_ki_{eje}"], 20.0),
                      PURPLE)
            entry_row(parent, "Kd:", self.__dict__[f"_kd_{eje}"],
                      lambda e=eje: self._send_ganancia(e, "Kd", self.__dict__[f"_kd_{eje}"], 2.0),
                      PURPLE)
        self._fila_rampa(parent, eje)
        fila = tk.Frame(parent, bg=CARD2)
        fila.pack(fill="x", padx=8, pady=(2, 4))
        fila.columnconfigure(0, weight=1)
        fila.columnconfigure(1, weight=1)
        FlatButton(fila, "Ir a 0", command=lambda e=eje: self._send_cero(e),
                   bg_color=ACCENT, fg_color=TEXT, width=1, height=28,
                   font_size=FS - 1).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        FlatButton(fila, "Cero aquí", command=lambda e=eje: self._enviar_simple(f"{eje}0"),
                   bg_color=BORDER, fg_color=TEXT, width=1, height=28,
                   font_size=FS - 1).grid(row=0, column=1, sticky="ew", padx=(3, 0))

    def _entradas(self, row, campos, color):
        for titulo, var in campos:
            tk.Label(row, text=titulo, font=(FF, FS - 2),
                     bg=CARD2, fg=TEXTDIM).pack(side="left", padx=(0, 2))
            tk.Entry(row, textvariable=var, width=5,
                     font=(FF, FS), bg=SURFACE, fg=TEXT,
                     insertbackground=ACCENT, relief="flat", bd=0,
                     highlightthickness=1, highlightcolor=color,
                     highlightbackground=BORDER).pack(
                         side="left", fill="x", expand=True, padx=(0, 6), ipady=3)

    def _filas_lazo_abierto(self, parent):
        """La base sin encoder: V = V0 + Kv · velocidad. Y una prueba para medirlos."""
        self._v0_var = tk.StringVar(value=f"{BASE_V0_INICIAL:g}")
        self._kv_var = tk.StringVar(value=f"{BASE_KV_INICIAL:g}")
        self._prueba_v = tk.StringVar(value="6")
        self._prueba_s = tk.StringVar(value="2")
        self._prueba_grados = tk.StringVar(value="")

        row = tk.Frame(parent, bg=CARD2)
        row.pack(fill="x", padx=8, pady=2)
        FlatButton(row, "▶", command=self._send_lazo_abierto, bg_color=PURPLE, fg_color=BG,
                   width=32, height=26, font_size=FS).pack(side="right")
        self._entradas(row, (("V0 V", self._v0_var), ("Kv V·s/°", self._kv_var)), PURPLE)

        row = tk.Frame(parent, bg=CARD2)
        row.pack(fill="x", padx=8, pady=2)
        FlatButton(row, "Probar", command=self._probar_tension, bg_color=DANGER, fg_color=TEXT,
                   width=58, height=26, font_size=FS - 1).pack(side="right")
        self._entradas(row, (("V", self._prueba_v), ("s", self._prueba_s)), DANGER)

        row = tk.Frame(parent, bg=CARD2)
        row.pack(fill="x", padx=8, pady=2)
        FlatButton(row, "Kv", command=self._calcular_kv, bg_color=BORDER, fg_color=TEXT,
                   width=58, height=26, font_size=FS - 1).pack(side="right")
        self._entradas(row, (("Giró °", self._prueba_grados),), BORDER)

    def _send_lazo_abierto(self):
        v0 = self._leer_numero(self._v0_var.get())
        kv = self._leer_numero(self._kv_var.get())
        if v0 is None or kv is None:
            self._log_add("err", "V0 y Kv tienen que ser números")
            return
        if not (0 <= v0 <= 24 and 0 <= kv <= 24):
            self._log_add("err", "V0 y Kv van de 0 a 24")
            return
        self._send(f"BV0:{v0:.3f}".rstrip("0").rstrip("."))
        self._send(f"BKv:{kv:.3f}".rstrip("0").rstrip("."))

    def _probar_tension(self):
        """Gira la base a tensión fija unos segundos para medir cuánto avanza."""
        v = self._leer_numero(self._prueba_v.get())
        s = self._leer_numero(self._prueba_s.get())
        if v is None or s is None or not (-24 <= v <= 24) or not (0 < s <= 30):
            self._log_add("err", "La prueba va de -24 a 24 V y hasta 30 s")
            return
        self._modo = None
        self._pintar_modos()
        if self._send(f"BU{v:.2f}"):
            self.after(int(s * 1000), lambda: self._send("BS"))
            self._log_add("sys", f"Base a {v:g} V por {s:g} s. Mide cuántos grados giró el plato.")

    def _calcular_kv(self):
        v = self._leer_numero(self._prueba_v.get())
        s = self._leer_numero(self._prueba_s.get())
        grados = self._leer_numero(self._prueba_grados.get())
        v0 = self._leer_numero(self._v0_var.get())
        if None in (v, s, grados, v0) or s <= 0 or grados == 0:
            self._log_add("err", "Pon la tensión, los segundos, los grados que giró y V0")
            return
        vel = abs(grados) / s
        kv = (abs(v) - v0) / vel
        if kv <= 0:
            self._log_add("err", "La tensión de prueba tiene que ser mayor que V0")
            return
        self._kv_var.set(f"{kv:.4f}".rstrip("0").rstrip("."))
        self._log_add("ok", f"{vel:.1f} °/s a {abs(v):g} V → Kv = {kv:.4f} V·s/°. Envíalo con ▶")

    def _fila_rampa(self, parent, eje):
        """Velocidad (°/s) y aceleración (°/s²) máximas de la rampa de ese motor."""
        vmax = tk.StringVar(value=f"{VEL_MAX_INICIAL:g}")
        amax = tk.StringVar(value=f"{ACEL_MAX_INICIAL:g}")
        self.__dict__[f"_vmax_{eje}"] = vmax
        self.__dict__[f"_amax_{eje}"] = amax
        row = tk.Frame(parent, bg=CARD2)
        row.pack(fill="x", padx=8, pady=2)
        enviar = lambda e=eje: self._send_rampa(e)
        FlatButton(row, "▶", command=enviar, bg_color=WARN, fg_color=BG,
                   width=32, height=26, font_size=FS).pack(side="right")
        for titulo, var in (("V°/s", vmax), ("A°/s²", amax)):
            tk.Label(row, text=titulo, font=(FF, FS - 2),
                     bg=CARD2, fg=TEXTDIM).pack(side="left", padx=(0, 2))
            e = tk.Entry(row, textvariable=var, width=5,
                         font=(FF, FS), bg=SURFACE, fg=TEXT,
                         insertbackground=ACCENT, relief="flat", bd=0,
                         highlightthickness=1, highlightcolor=WARN,
                         highlightbackground=BORDER)
            e.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
            e.bind("<Return>", lambda _e, f=enviar: f())

    def _boton_ancho(self, parent, col, texto, cmd, color):
        FlatButton(parent, texto, command=cmd, bg_color=color, fg_color=TEXT,
                   width=1, height=32, font_size=FS - 1).grid(
                       row=0, column=col, sticky="ew", padx=3)

    def _card_trayectoria(self, parent):
        wrap, card = card_frame(parent, "Trayectoria", ORANGE)
        wrap.grid(row=1, column=0, sticky="nsew")
        sitio = tk.Frame(card, bg=CARD2)
        sitio.pack(fill="x", padx=8, pady=(6, 2))
        self._lat_var = tk.StringVar(value="4.627444")
        self._lon_var = tk.StringVar(value="-74.064111")
        self._alt_var = tk.StringVar(value="2640")
        self._norad_var = tk.StringVar(value=str(ISS_NORAD))
        for titulo, var, ancho in (("Lat", self._lat_var, 8),
                                   ("Lon", self._lon_var, 9),
                                   ("Alt m", self._alt_var, 6),
                                   ("NORAD", self._norad_var, 7)):
            tk.Label(sitio, text=titulo, font=(FF, FS - 2),
                     bg=CARD2, fg=TEXTDIM).pack(side="left", padx=(4, 2))
            tk.Entry(sitio, textvariable=var, width=ancho,
                     font=(FF, FS - 1), bg=SURFACE, fg=TEXT,
                     insertbackground=ACCENT, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT).pack(side="left", ipady=2)
        FlatButton(sitio, "Bajar", command=self._bajar_orbita,
                   bg_color=ACCENT, fg_color=TEXT,
                   width=64, height=26, font_size=FS - 1).pack(side="right", padx=4)

        modos = tk.Frame(card, bg=CARD2)
        modos.pack(fill="x", padx=8, pady=2)
        modos.columnconfigure(0, weight=1)
        modos.columnconfigure(1, weight=1)
        modos.columnconfigure(2, weight=1)
        self._btn_vivo = FlatButton(
            modos, "EN VIVO", command=lambda: self._poner_modo("vivo"),
            bg_color=ACCENT2, fg_color=TEXT, width=1, height=30, font_size=FS - 1)
        self._btn_vivo.grid(row=0, column=0, sticky="ew", padx=2)
        self._btn_repetir = FlatButton(
            modos, "REPETIR PASO", command=lambda: self._poner_modo("repetir"),
            bg_color=ACCENT, fg_color=TEXT, width=1, height=30, font_size=FS - 1)
        self._btn_repetir.grid(row=0, column=1, sticky="ew", padx=2)
        self._btn_rampa = FlatButton(
            modos, "RAMPA", command=lambda: self._poner_modo("rampa"),
            bg_color=WARN, fg_color=BG, width=1, height=30, font_size=FS - 1)
        self._btn_rampa.grid(row=0, column=2, sticky="ew", padx=2)

        rampa_f = tk.Frame(card, bg=CARD2)
        rampa_f.pack(fill="x", padx=8, pady=(0, 2))
        tk.Label(rampa_f, text="Rampa a", font=(FF, FS - 2),
                 bg=CARD2, fg=TEXTDIM).pack(side="left")
        self._rampa_az = tk.StringVar(value="40")
        self._rampa_el = tk.StringVar(value="35")
        self._rampa_s = tk.StringVar(value="30")
        for titulo, var in (("az", self._rampa_az), ("NEMA", self._rampa_el), ("s", self._rampa_s)):
            tk.Label(rampa_f, text=titulo, font=(FF, FS - 2),
                     bg=CARD2, fg=TEXTDIM).pack(side="left", padx=(8, 2))
            tk.Entry(rampa_f, textvariable=var, width=5,
                     font=(FF, FS - 1), bg=SURFACE, fg=TEXT,
                     insertbackground=ACCENT, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=WARN).pack(side="left", ipady=2)

        manual_f = tk.Frame(card, bg=CARD2)
        manual_f.pack(fill="x", padx=8, pady=(0, 2))
        tk.Label(manual_f, text="Manual", font=(FF, FS - 2),
                 bg=CARD2, fg=TEXTDIM).pack(side="left")
        self._manual_az_var = tk.StringVar(value="0")
        self._manual_el_var = tk.StringVar(value="0")
        for titulo, var in (("az", self._manual_az_var), ("NEMA", self._manual_el_var)):
            tk.Label(manual_f, text=titulo, font=(FF, FS - 2),
                     bg=CARD2, fg=TEXTDIM).pack(side="left", padx=(8, 2))
            tk.Entry(manual_f, textvariable=var, width=6,
                     font=(FF, FS - 1), bg=SURFACE, fg=TEXT,
                     insertbackground=ACCENT, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=CYAN).pack(side="left", ipady=2)
        FlatButton(manual_f, "IR", command=self._ir_manual,
                   bg_color=CYAN, fg_color=BG,
                   width=52, height=26, font_size=FS - 1).pack(side="right", padx=4)

        self._gemelo = Gemelo(card)
        self._gemelo.pack(fill="both", expand=True, padx=6, pady=(2, 6))

    def _build_diales(self, parent):
        centro = tk.Frame(parent, bg=BG)
        centro.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        centro.rowconfigure(0, weight=1)
        centro.rowconfigure(1, weight=1)
        centro.columnconfigure(0, weight=1)
        wrap_a, body_a = card_frame(centro, "Arriba · elevación del telescopio", CYAN)
        wrap_a.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self._dial_e = Dial(body_a, "Elevación", "elevacion")
        self._dial_e.pack(fill="both", expand=True)
        wrap_b, body_b = card_frame(centro, "Abajo", ORANGE)
        wrap_b.grid(row=1, column=0, sticky="nsew")
        self._dial_b = Dial(body_b, "Base", "azimut")
        self._dial_b.pack(fill="both", expand=True)

    def _build_graficas(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=2, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self._ax_e, self._fig_e, self._mpl_e, self._metricas_e = self._card_escalon(
            right, 0, "Arriba", CYAN, "E")
        self._ax_b, self._fig_b, self._mpl_b, self._metricas_b = self._card_escalon(
            right, 1, "Abajo", ORANGE, "B")
        self._pintar_escalon("E")
        self._pintar_escalon("B")

    def _card_escalon(self, parent, fila, titulo, color, eje):
        wrap, body = card_frame(parent, titulo, color)
        wrap.grid(row=fila, column=0, sticky="nsew", pady=(0, 8 if fila == 0 else 0))
        tk.Label(body,
                 text="ts: 10 % a 90 %      te: se queda dentro del 2 %      Mp: sobrepaso",
                 font=(FF, FS - 2), bg=CARD2, fg=TEXTDIM).pack(anchor="w", padx=8, pady=(2, 0))
        fila_m = tk.Frame(body, bg=CARD2)
        fila_m.pack(fill="x", padx=8)
        metricas = {}
        for nombre, col in (("ts", WARN), ("te", TEXT), ("Mp", DANGER)):
            tk.Label(fila_m, text=nombre, font=(FF, FS - 2, "bold"),
                     bg=CARD2, fg=TEXTDIM).pack(side="left", padx=(0, 2))
            lbl = tk.Label(fila_m, text="—", font=(FF, FS, "bold"), bg=CARD2, fg=col)
            lbl.pack(side="left", padx=(0, 12))
            metricas[nombre] = lbl
        if not HAS_MPL:
            tk.Label(body, text="matplotlib no instalado",
                     bg=CARD2, fg=DANGER, font=(FF, FS)).pack(expand=True)
            return None, None, None, metricas
        # La ventana ya trabaja en píxeles físicos (DPI aware). Si matplotlib
        # vuelve a multiplicar por la escala de Windows, la figura sale al doble
        # del lienzo y solo se ve una esquina. La escala va solo en el dpi.
        fig = Figure(figsize=(5.2, 2.4), dpi=96 * UI_SCALE, facecolor=BG)
        fig.set_layout_engine("tight", pad=0.45)
        ax = fig.add_subplot(111)
        mpl = FigureCanvasTkAgg(fig, master=body)
        mpl.get_tk_widget().unbind("<Map>")
        mpl.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=4)
        return ax, fig, mpl, metricas

    def _build_log(self, parent):
        wrap, body = card_frame(parent, "Terminal", ACCENT)
        wrap.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._log = tk.Text(
            body, bg=BG, fg=TEXTLOG, font=("Consolas", 9), relief="flat",
            height=4, wrap="word", state="disabled",
            selectbackground=ACCENT, insertbackground=ACCENT)
        self._log.pack(fill="x", padx=6, pady=(2, 6))
        self._log.tag_config("ts", foreground="#455a64")
        self._log.tag_config("ok", foreground=ACCENT2)
        self._log.tag_config("err", foreground=DANGER)
        self._log.tag_config("send", foreground=PURPLE)
        self._log.tag_config("sys", foreground=TEXTDIM)
        self._log.tag_config("plain", foreground=TEXTLOG)

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()] if HAS_SERIAL else []
        self._port_cb["values"] = ports
        if ports:
            self._port_cb.set(ports[-1])

    def _toggle_connect(self):
        if self._worker and self._worker._running:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self._port_var.get()
        if not port:
            messagebox.showerror("Sin puerto", "Selecciona un puerto COM.")
            return
        if not HAS_SERIAL:
            messagebox.showerror("pyserial faltante", "py -3 -m pip install pyserial")
            return
        self._rx_q = queue.Queue()
        self._worker = SerialWorker(port, BAUD_RATE, self._rx_q)
        self._worker.start()

    def _disconnect(self):
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._lbl_status.config(text="●  DESCONECTADO", fg=DANGER)
        self._btn_conn.configure_text("CONECTAR")
        self._btn_conn.set_color(ACCENT2, TEXT)
        self._log_add("sys", "Puerto cerrado")

    def _conectado(self):
        return self._worker is not None and self._worker._running

    def _send(self, cmd, anotar=True):
        if self._conectado():
            self._worker.send(cmd)
            if anotar:
                self._log_add("send", f"→  {cmd}")
            return True
        if anotar:
            self._log_add("err", "No hay puerto abierto")
        return False

    def _enviar_simple(self, cmd):
        self._send(cmd)

    def _parar(self):
        self._modo = None
        self._pintar_modos()
        self._send("S")

    def _leer_encoders(self):
        self._send("BC")
        self._send("EC")

    def _leer_numero(self, texto):
        t = texto.strip().replace(",", ".")
        if not NUMERO_RE.fullmatch(t):
            return None
        return float(t)

    def _send_pos(self, eje, minimo, maximo):
        valor = self._leer_numero(self.__dict__[f"_pos_{eje}"].get())
        if valor is None:
            self._log_add("err", "La posición tiene que ser un número")
            return
        if valor < minimo or valor > maximo:
            self._log_add("err", f"Ese eje va de {minimo:.0f}° a {maximo:.0f}°")
            return
        self._arrancar_escalon(eje, valor)
        if self._send(f"{eje}P{valor:.1f}"):
            if eje == "B":
                self._ref_b = valor
            else:
                self._ref_e = valor

    def _send_cero(self, eje):
        self._arrancar_escalon(eje, 0.0)
        if self._send(f"{eje}Z"):
            if eje == "B":
                self._ref_b = 0.0
            else:
                self._ref_e = 0.0

    def _send_ganancia(self, eje, nombre, var, tope):
        valor = self._leer_numero(var.get())
        if valor is None:
            self._log_add("err", f"{nombre} tiene que ser un número")
            return
        if valor < 0 or valor > tope:
            self._log_add("err", f"{nombre} va de 0 a {tope:g}")
            return
        texto = f"{valor:.4f}".rstrip("0").rstrip(".")
        if self._send(f"{eje}{nombre}:{texto}"):
            getattr(self, f"_{nombre.lower()}")[eje] = valor

    def _send_rampa(self, eje):
        vmax = self._leer_numero(self.__dict__[f"_vmax_{eje}"].get())
        amax = self._leer_numero(self.__dict__[f"_amax_{eje}"].get())
        if vmax is None or amax is None:
            self._log_add("err", "La rampa necesita velocidad y aceleración")
            return
        if not (0 <= vmax <= 360):
            self._log_add("err", "La velocidad va de 0 a 360 °/s (0 = sin rampa)")
            return
        if eje == "B" and vmax == 0:
            self._log_add("err", "La base en lazo abierto necesita la rampa: velocidad mayor que 0")
            return
        if not (0 < amax <= 360):
            self._log_add("err", "La aceleración va de más de 0 a 360 °/s²")
            return
        tv = f"{vmax:.3f}".rstrip("0").rstrip(".")
        ta = f"{amax:.3f}".rstrip("0").rstrip(".")
        self._vmax[eje] = vmax
        self._amax[eje] = amax
        self._sim_vel[eje] = 0.0
        if self._conectado():
            self._send(f"{eje}V:{tv}")
            self._send(f"{eje}A:{ta}")
        else:
            self._log_add("sys", f"Rampa {eje}: {tv} °/s, {ta} °/s² (solo el gemelo)")

    def _arrancar_escalon(self, eje, yf):
        y0 = self._pos_b if eje == "B" else self._pos_e
        if y0 is None:
            y0 = 0.0
        esc = self._escalon[eje]
        esc.nuevo(y0, yf)
        self._dibujar_escalon[eje] = True
        metricas = self._metricas_b if eje == "B" else self._metricas_e
        for lbl in metricas.values():
            lbl.config(text="—")

    def _bajar_orbita(self):
        try:
            catnr = int(self._norad_var.get().strip())
            lat = self._leer_numero(self._lat_var.get())
            lon = self._leer_numero(self._lon_var.get())
            alt = self._leer_numero(self._alt_var.get())
        except ValueError:
            self._log_add("err", "El NORAD tiene que ser un entero")
            return
        if None in (lat, lon, alt):
            self._log_add("err", "Latitud, longitud y altura tienen que ser números")
            return
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and -500 <= alt <= 9000):
            self._log_add("err", "Revisa latitud, longitud y altura")
            return
        self._texto_cielo = "Bajando el TLE de Celestrak..."
        self._log_add("sys", f"Descargando NORAD {catnr}")

        def trabajo():
            try:
                self._orb.descargar(catnr)
                self._orb.preparar(lat, lon, alt)
                self._ui_q.put(("ORBITA", None))
            except Exception as exc:
                self._ui_q.put(("ORBITA_ERR", str(exc)))

        threading.Thread(target=trabajo, daemon=True).start()

    def _poner_modo(self, modo):
        if self._modo == modo:
            self._modo = None
            self._pintar_modos()
            self._log_add("sys", "Seguimiento detenido")
            return
        if modo != "rampa" and self._orb._sat is None:
            self._log_add("err", "Todavía no llega la órbita")
            return
        if modo == "repetir":
            paso = (self._orb.paso_en_curso() or self._orb.paso_anterior()
                    or self._orb.paso_siguiente())
            if paso is None:
                self._log_add("err", "No hay un paso guardado para repetir")
                return
            self._paso_play = paso
            self._play_t0 = time.time()
            self._arco = _arco(paso)
            hora = datetime.fromtimestamp(paso.inicio).strftime("%H:%M")
            self._log_add("sys", f"Repitiendo el paso de las {hora}, "
                                 f"máximo {paso.max_el:.0f}°")
        elif modo == "vivo":
            self._log_add("sys", "Seguimiento en vivo. Solo mueve si la elevación pasa de 10°")
        else:
            if not self._leer_rampa():
                return
            self._play_t0 = time.time()
            self._rampa_ini = self._vista()
            self._log_add("sys", "Rampa lenta, sin órbita")
        self._modo = modo
        self._ultimo_cmd = 0.0
        self._elev_sigue = False
        self._elev_frenado = False
        self._pintar_modos()

    def _ir_manual(self):
        az = self._leer_numero(self._manual_az_var.get())
        el = self._leer_numero(self._manual_el_var.get())
        if az is None or el is None:
            self._log_add("err", "La posición manual necesita azimut y NEMA")
            return
        if not (BASE_MIN <= az <= BASE_MAX and ELEV_MIN <= el <= ELEV_MAX):
            self._log_add("err", "La posición manual se sale del recorrido")
            return
        self._manual_az = az
        self._manual_el = el
        self._modo = "manual"
        self._ultimo_cmd = 0.0
        self._elev_sigue = False
        self._elev_frenado = False
        self._pintar_modos()
        self._log_add("sys", f"Manual · az {az:.1f}° · NEMA {el:.1f}° · primero la base")

    def _leer_rampa(self):
        az = self._leer_numero(self._rampa_az.get())
        el = self._leer_numero(self._rampa_el.get())
        dur = self._leer_numero(self._rampa_s.get())
        if None in (az, el, dur):
            self._log_add("err", "La rampa necesita azimut, elevación y segundos")
            return False
        if not (BASE_MIN <= az <= BASE_MAX and ELEV_MIN <= el <= ELEV_MAX and dur > 0):
            self._log_add("err", "La rampa se sale del recorrido")
            return False
        self._rampa_fin = (az, el, dur)
        return True

    def _pintar_modos(self):
        self._btn_vivo.set_color(ACCENT2 if self._modo == "vivo" else BORDER, TEXT)
        self._btn_repetir.set_color(ACCENT if self._modo == "repetir" else BORDER, TEXT)
        self._btn_rampa.set_color(WARN if self._modo == "rampa" else BORDER,
                                  BG if self._modo == "rampa" else TEXT)

    def _poll(self):
        self._vaciar_serial()
        self._vaciar_orbita()
        self._tick_seguimiento()
        self._acercar_simulacion()
        self._refrescar_vistas()
        for eje in ("B", "E"):
            if self._dibujar_escalon[eje]:
                self._pintar_escalon(eje)
                self._dibujar_escalon[eje] = False
        self.after(50, self._poll)

    def _vaciar_serial(self):
        try:
            while True:
                kind, data = self._rx_q.get_nowait()
                if kind == "CONNECTED":
                    self._lbl_status.config(text="●  CONECTADO", fg=ACCENT2)
                    self._btn_conn.configure_text("DESCONECTAR")
                    self._btn_conn.set_color(DANGER, TEXT)
                    self._log_add("sys", "Puerto abierto, 115200 8N1")
                elif kind == "MSG":
                    self._handle_msg(data)
                elif kind == "ERROR":
                    self._lbl_status.config(text="●  ERROR", fg=DANGER)
                    self._btn_conn.configure_text("CONECTAR")
                    self._btn_conn.set_color(ACCENT2, TEXT)
                    self._worker = None
                    self._log_add("err", data)
        except queue.Empty:
            pass

    def _vaciar_orbita(self):
        try:
            while True:
                kind, data = self._ui_q.get_nowait()
                if kind == "ORBITA":
                    n = len(self._orb.pasos)
                    self._log_add("ok", f"{self._orb.nombre}: {n} pasos sobre {UMBRAL_ELEV:.0f}°")
                    self._texto_cielo = self._resumen_pasos()
                    paso = (self._orb.paso_en_curso() or self._orb.paso_siguiente()
                            or self._orb.paso_anterior())
                    self._arco = _arco(paso)
                elif kind == "ORBITA_ERR":
                    self._texto_cielo = "No se pudo bajar la órbita"
                    self._log_add("err", data)
        except queue.Empty:
            pass

    def _resumen_pasos(self):
        curso = self._orb.paso_en_curso()
        if curso:
            return f"{self._orb.nombre} en curso · máximo {curso.max_el:.0f}°"
        sig = self._orb.paso_siguiente()
        if sig:
            hora = datetime.fromtimestamp(sig.inicio).strftime("%H:%M")
            return f"Próximo paso {hora} · máximo {sig.max_el:.0f}°"
        ant = self._orb.paso_anterior()
        if ant:
            return f"Paso guardado · máximo {ant.max_el:.0f}° · se puede repetir"
        return f"{self._orb.nombre} sin pasos sobre el horizonte"

    def _tick_seguimiento(self):
        ahora = time.time()
        if self._modo is None:
            if self._orb._sat is not None and ahora - self._ultimo_cielo > 1.0:
                self._ultimo_cielo = ahora
                try:
                    self._sat_az, self._sat_el = self._orb.ahora()
                except Exception:
                    return
                self._texto_cielo = self._resumen_pasos()
            return
        if ahora - self._ultimo_cmd < 0.2:
            return
        az, el, sigue, es_cielo = self._apunte_actual(ahora)
        if az is None:
            return
        if es_cielo:
            self._sat_az, self._sat_el = az, el
        self._ultimo_cmd = ahora
        if not sigue:
            return
        if self._modo == "rampa":
            self._cmd_az = az
            self._cmd_el = el
        else:
            self._cmd_az = consigna_base(
                az, self._pos_b if self._pos_b is not None else self._sim_az)
            self._cmd_el = min(ELEV_MAX, max(ELEV_MIN, el_a_nema(el)))
        self._actualizar_elev_sigue()
        if self._conectado():
            self._send(f"BP{self._cmd_az:.1f}", anotar=False)
            self._ref_b = self._cmd_az
            if self._elev_sigue:
                self._send(f"EP{self._cmd_el:.1f}", anotar=False)
                self._ref_e = self._cmd_el
                self._elev_frenado = False
            elif not self._elev_frenado:
                self._send("ES", anotar=False)
                self._elev_frenado = True

    def _apunte_actual(self, ahora):
        if self._modo == "manual":
            espera = "" if self._elev_sigue else " · base primero"
            self._texto_cielo = (f"Manual · az {self._manual_az:.1f}° · "
                                 f"NEMA {self._manual_el:.1f}°{espera}")
            return self._manual_az, self._manual_el, True, False
        if self._modo == "vivo":
            try:
                az, el = self._orb.ahora()
            except Exception as exc:
                self._modo = None
                self._pintar_modos()
                self._log_add("err", str(exc))
                return None, None, False, False
            self._texto_cielo = (f"En vivo · az {az:.1f}° · el {el:.1f}°"
                                 if el >= UMBRAL_ELEV else
                                 f"Bajo el horizonte · el {el:.1f}°")
            return az, el, el >= UMBRAL_ELEV, True
        if self._modo == "repetir":
            paso = self._paso_play
            t = paso.inicio + (ahora - self._play_t0)
            if t >= paso.fin:
                self._modo = None
                self._pintar_modos()
                self._log_add("ok", "Terminó la repetición del paso")
                self._texto_cielo = self._resumen_pasos()
                return paso.muestras[-1][1], paso.muestras[-1][2], False, True
            az, el = paso.en(t)
            falta = int(paso.fin - t)
            self._texto_cielo = f"Repitiendo · faltan {falta} s · el {el:.0f}°"
            return az, el, True, True
        if self._modo == "rampa":
            az1, el1, dur = self._rampa_fin
            az = rampa(ahora, self._play_t0, dur, self._rampa_ini[0], az1)
            el = rampa(ahora, self._play_t0, dur, self._rampa_ini[1], el1)
            if ahora - self._play_t0 >= dur:
                self._modo = None
                self._pintar_modos()
                self._texto_cielo = "Rampa terminada"
                self._log_add("ok", "Rampa terminada")
            else:
                self._texto_cielo = f"Rampa · az {az:.1f}° · NEMA {el:.1f}°"
            return az, el, True, False
        return None, None, False, False

    def _error_base(self):
        if self._conectado():
            if self._pos_b is None:
                return None
            return abs(self._pos_b - self._cmd_az)
        return abs(self._sim_az - self._cmd_az)

    def _actualizar_elev_sigue(self):
        """La base va primero. El NEMA sigue solo cuando el azimut ya está cerca."""
        error = self._error_base()
        if error is None:
            self._elev_sigue = False
            return
        if self._elev_sigue:
            self._elev_sigue = error <= SALIDA_BASE
        else:
            self._elev_sigue = error <= LLEGADA_BASE

    def _acercar_simulacion(self):
        if self._conectado():
            return
        self._sim_az, self._sim_vel["B"] = paso_rampa(
            self._sim_az, self._sim_vel["B"], self._cmd_az,
            self._vmax["B"], self._amax["B"], POLL_S)
        if self._elev_sigue:
            self._sim_el, self._sim_vel["E"] = paso_rampa(
                self._sim_el, self._sim_vel["E"], self._cmd_el,
                self._vmax["E"], self._amax["E"], POLL_S)

    def _vista(self):
        if self._conectado() and self._pos_b is not None:
            return self._pos_b, self._pos_e if self._pos_e is not None else 0.0
        return self._sim_az, self._sim_el

    def _refrescar_vistas(self):
        az, el = self._vista()
        self._gemelo.set_estado(az, el, self._sat_az, self._sat_el,
                                self._arco, self._texto_cielo)
        self._dial_b.set_valores(az, self._ref_b)
        self._dial_e.set_valores(nema_a_el(el), nema_a_el(self._ref_e))

    def _handle_msg(self, msg):
        m = TELEMETRIA_RE.match(msg)
        if m:
            self._pos_b = float(m.group(2))
            self._ref_b = float(m.group(1))
            self._pos_e = float(m.group(6))
            self._ref_e = float(m.group(5))
            if self._escalon["B"].agregar(self._pos_b):
                if self._escalon["B"].evaluar():
                    self._anotar_prueba("B", self._escalon["B"])
                self._dibujar_escalon["B"] = True
                self._poner_metricas("B")
            if self._escalon["E"].agregar(self._pos_e):
                if self._escalon["E"].evaluar():
                    self._anotar_prueba("E", self._escalon["E"])
                self._dibujar_escalon["E"] = True
                self._poner_metricas("E")
            return
        m = ENC_RE.match(msg)
        if m:
            nombre = "Base" if m.group(1) == "B" else "Elevación"
            self._log_add("plain", f"{nombre} ENC {m.group(2)}")
            return
        m = AB_RE.match(msg)
        if m:
            nombre = "Base" if m.group(1) == "B" else "Elevación"
            self._log_add("plain", f"{nombre} A={m.group(2)} B={m.group(3)}")
            return
        if msg == "RDY":
            self._log_add("sys", "PIC listo")
            return
        if msg == "OK":
            self._log_add("ok", "OK")
            return
        if msg == "ERR RANGO":
            self._log_add("err", "Fuera de rango")
            if self._modo is not None:
                self._modo = None
                self._pintar_modos()
            return
        if msg == "ERR VALOR":
            self._log_add("err", "El PIC no entendió el comando")
            return
        if msg.startswith("ERR"):
            self._log_add("err", msg)
            return
        self._log_add("plain", msg)

    def _poner_metricas(self, eje):
        esc = self._escalon[eje]
        metricas = self._metricas_b if eje == "B" else self._metricas_e
        metricas["ts"].config(text="—" if esc.ts_s is None else f"{esc.ts_s:.3f} s")
        metricas["te"].config(text="—" if esc.marca_te is None else f"{esc.marca_te:.3f} s")
        metricas["Mp"].config(text="—" if esc.mp_pct is None else f"{esc.mp_pct:.1f} %")

    def _estilo(self, ax, ylabel="Posición (°)"):
        ax.set_facecolor(BG)
        ax.tick_params(colors=TEXTDIM, labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(BORDER)
        ax.set_xlabel("Tiempo (s)", color=TEXTDIM, fontsize=8)
        ax.set_ylabel(ylabel, color=TEXTDIM, fontsize=8)
        ax.grid(True, color=BORDER, linewidth=0.6)

    def _pintar_escalon(self, eje):
        ax = self._ax_b if eje == "B" else self._ax_e
        fig = self._fig_b if eje == "B" else self._fig_e
        mpl = self._mpl_b if eje == "B" else self._mpl_e
        if ax is None:
            return
        esc = self._escalon[eje]
        ax.cla()
        self._estilo(ax, "Posición NEMA (°)" if eje == "E" else "Posición estimada (°)")
        if len(esc.t) < 2:
            ax.text(0.5, 0.5, "El escalón aparece al mandar la posición",
                    transform=ax.transAxes, ha="center", va="center",
                    color=TEXTDIM, fontsize=9)
            ax.set_xticks([])
            ax.set_yticks([])
            fig.tight_layout(pad=0.45)
            mpl.draw_idle()
            return
        y0, yf = esc.y0, esc.yf
        amp = yf - y0
        banda = BANDA_TE * abs(amp)
        t_fin = VENTANA_TE * esc.marca_te if esc.marca_te is not None else max(esc.t[-1], 0.4)
        t_pos = list(esc.t)
        y_pos = list(esc.y)
        if t_fin > t_pos[-1]:
            t_pos.append(t_fin)
            y_pos.append(y_pos[-1])
        ax.plot([0.0, 0.0, t_fin], [y0, yf, yf],
                color=ORANGE, linewidth=1.4, linestyle="--", label="Referencia")
        ax.plot(t_pos, y_pos, color=CYAN, linewidth=1.6, label="Posición")
        if abs(amp) >= PASO_MIN:
            ax.axhline(yf + banda, color=TEXTDIM, linewidth=0.7, linestyle=":")
            ax.axhline(yf - banda, color=TEXTDIM, linewidth=0.7, linestyle=":")
        if esc.marca_ts is not None:
            ax.axvline(esc.marca_ts, color=WARN, linewidth=1.1, linestyle="--")
        if esc.marca_te is not None:
            ax.axvline(esc.marca_te, color=TEXT, linewidth=1.1, linestyle=":")
        ys = esc.y + [y0, yf]
        bajo, alto = min(ys) - banda, max(ys) + banda
        if alto - bajo < 4.0:
            medio = 0.5 * (bajo + alto)
            bajo, alto = medio - 2.0, medio + 2.0
        ax.set_ylim(bajo, alto)
        ax.set_xlim(0.0, t_fin)
        leg = ax.legend(loc="upper right", fontsize=8, frameon=False)
        for txt in leg.get_texts():
            txt.set_color(TEXTDIM)
        fig.tight_layout(pad=0.45)
        mpl.draw_idle()

    def _anotar_prueba(self, eje, esc):
        self._pruebas.append({
            "eje": "Abajo" if eje == "B" else "Arriba",
            "kp": self._kp[eje], "ki": self._ki[eje], "kd": self._kd[eje],
            "pos_in": esc.y0, "ref_fin": esc.yf, "pos_fin": esc.y[-1],
            "error": esc.yf - esc.y[-1], "ts": esc.ts_s,
            "te": esc.marca_te, "mp": esc.mp_pct, "en_promedio": True,
        })
        self._log_add("ok", f"Prueba {len(self._pruebas)} anotada")
        self._refrescar_tabla(ir_al_final=True)

    def _abrir_pruebas(self):
        win = self._ventana_pruebas
        if win is not None and win.winfo_exists():
            win.lift()
            return
        win = tk.Toplevel(self)
        win.title("Pruebas")
        win.configure(bg=BG)
        win.geometry("1100x560")
        self._ventana_pruebas = win
        tk.Label(win, text="Tabla de pruebas", font=(FF, FSL, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w", padx=14, pady=(12, 0))
        tk.Label(win, text="Se anota sola cuando el escalón se queda quieto.",
                 font=(FF, FS - 1), bg=BG, fg=TEXTDIM).pack(anchor="w", padx=14, pady=(0, 8))
        columnas = (
            ("n", "N°", 48), ("eje", "Eje", 80),
            ("kp", "Kp", 70), ("ki", "Ki", 70), ("kd", "Kd", 70),
            ("pos_in", "Inicial (°)", 90), ("ref_fin", "Ref (°)", 80),
            ("pos_fin", "Final (°)", 90), ("error", "Error (°)", 80),
            ("ts", "ts (s)", 78), ("te", "te (s)", 78), ("mp", "Mp (%)", 76),
        )
        marco = tk.Frame(win, bg=BORDER)
        marco.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        arbol = ttk.Treeview(marco, columns=[c[0] for c in columnas],
                             show="headings", selectmode="browse")
        for clave, titulo, ancho in columnas:
            arbol.heading(clave, text=titulo)
            arbol.column(clave, width=ancho, anchor="center")
        sy = tk.Scrollbar(marco, orient="vertical", command=arbol.yview)
        arbol.configure(yscrollcommand=sy.set)
        sy.pack(side="right", fill="y")
        arbol.pack(side="left", fill="both", expand=True)
        self._arbol = arbol
        barra = tk.Frame(win, bg=BG)
        barra.pack(fill="x", padx=14, pady=(0, 12))
        FlatButton(barra, "Exportar CSV", command=self._exportar,
                   bg_color=ACCENT, fg_color=TEXT, width=140, height=32).pack(side="left")
        FlatButton(barra, "Borrar", command=self._borrar_pruebas,
                   bg_color=DANGER, fg_color=TEXT, width=100, height=32).pack(side="left", padx=8)
        self._refrescar_tabla()

    def _fila(self, i, p):
        def num(v, d):
            return "—" if v is None else f"{v:.{d}f}"

        def g(v):
            texto = f"{v:.4f}".rstrip("0").rstrip(".")
            return texto if texto else "0"

        return (str(i), p["eje"], g(p["kp"]), g(p["ki"]), g(p["kd"]),
                num(p["pos_in"], 1), num(p["ref_fin"], 1), num(p["pos_fin"], 1),
                num(p["error"], 1), num(p["ts"], 3), num(p["te"], 3), num(p["mp"], 1))

    def _refrescar_tabla(self, ir_al_final=False):
        arbol = self._arbol
        if arbol is None or not arbol.winfo_exists():
            return
        arbol.delete(*arbol.get_children())
        for i, p in enumerate(self._pruebas, start=1):
            arbol.insert("", "end", values=self._fila(i, p))
        if ir_al_final and arbol.get_children():
            ultimo = arbol.get_children()[-1]
            arbol.see(ultimo)

    def _borrar_pruebas(self):
        self._pruebas.clear()
        self._refrescar_tabla()

    def _exportar(self):
        if not self._pruebas:
            messagebox.showinfo("Sin pruebas", "Todavía no hay escalones anotados.",
                                parent=self._ventana_pruebas)
            return
        ruta = filedialog.asksaveasfilename(
            parent=self._ventana_pruebas, defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], title="Guardar pruebas")
        if not ruta:
            return
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            out = csv.writer(f, delimiter=";")
            out.writerow(["N", "Eje", "Kp", "Ki", "Kd", "Inicial", "Ref",
                          "Final", "Error", "ts", "te", "Mp"])
            for i, p in enumerate(self._pruebas, start=1):
                out.writerow(self._fila(i, p))
        self._log_add("ok", f"CSV guardado: {ruta}")

    def _log_add(self, tag, msg):
        ts = time.strftime("%H:%M:%S")
        self._log.config(state="normal")
        self._log.insert("end", f"[{ts}]", "ts")
        self._log.insert("end", f"  {msg}\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")


def _arco(paso):
    if paso is None:
        return []
    muestras = paso.muestras
    salto = max(1, len(muestras) // 80)
    return [(az, el) for _t, az, el in muestras[::salto]]


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Seguidor de satélites")
        self.configure(bg=BG)
        global UI_SCALE
        try:
            dpi = self.winfo_fpixels("1i")
            self.tk.call("tk", "scaling", dpi / 72.0)
            UI_SCALE = dpi / 96.0
        except Exception:
            pass
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = max(1180, int(sw * 0.88))
        h = max(760, int(sh * 0.86))
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.minsize(1100, 720)
        self._apply_style()
        self._show_splash()

    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("default")
        s.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE,
                    foreground=TEXT, arrowcolor=ACCENT, bordercolor=BORDER,
                    insertcolor=TEXT)
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE)],
              selectbackground=[("readonly", CARD2)],
              selectforeground=[("readonly", TEXT)])

    def _show_splash(self):
        self._splash = SplashFrame(self, self._show_main)
        self._splash.pack(fill="both", expand=True)

    def _show_main(self):
        self._splash.destroy()
        MainFrame(self).pack(fill="both", expand=True)


if __name__ == "__main__":
    App().mainloop()
