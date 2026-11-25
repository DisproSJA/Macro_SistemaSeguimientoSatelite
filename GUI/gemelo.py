"""
Gemelo digital del seguidor de satélites (sin telescopio), basado en el CAD.

Cinemática (gimbal azimut-elevación):

  1. El plato del XD3420 gira sobre el eje VERTICAL y lleva encima toda la
     caja larga (y todo lo que va dentro de ella).  -> az
  2. Dentro de la caja, el NEMA 23 gira sobre un eje HORIZONTAL (el eje largo
     de la caja).  Dos brazos salen de ese eje y sostienen el panel, que da
     un cuarto de vuelta (0° a 90°), del horizonte al cenit.  -> el

     NEMA = 0°    panel arriba, telescopio horizontal, mira al horizonte
     NEMA = 90°   telescopio vertical, mira al cenit

  El telescopio va acostado sobre una base atornillada a los dos huecos del panel.
  Al encender, el tubo queda horizontal: ese punto es 0° en el PIC y en el NEMA.
  El XD3420 gira 360° (az sin tope en el gemelo).

Convenciones (las mismas que Dial y Skyfield):
  az = 0° es el norte (+Y), crece hacia el este (+X), o sea en sentido horario
  visto desde arriba.  z es hacia arriba.

Dimensiones en unidades relativas (1.0 = ancho del pedestal).  Ajusta el
bloque DIMENSIONES con las cotas reales del CAD y todo se reescala solo.
"""

import math
import tkinter as tk

BG = "#0D1117"
BORDER = "#30363D"
TEXT = "#E6EDF3"
TEXTDIM = "#8B949E"
ORANGE = "#F0883E"
CYAN = "#00D4FF"
FF = "Segoe UI"
FS = 10

# ───────────────────────── DIMENSIONES (ajustables) ─────────────────────────
PED_X, PED_Y, PED_Z = 1.00, 0.92, 1.25   # pedestal de abajo
PLATO_R, PLATO_H = 0.40, 0.05            # plato del XD3420 (el círculo rojo)
CAJA_L = 2.10                            # largo de la caja = largo del eje del NEMA
CAJA_P = 0.55                            # profundidad de la caja
CAJA_A = 0.85                            # alto de la caja
PARED = 0.035                            # espesor de las paredes
EJE_Z = 0.32                             # altura del eje del NEMA sobre el piso de la caja
RADIO = 0.62                             # distancia del eje al panel (largo del brazo)
PANEL_W, PANEL_E = 0.50, 0.06            # ancho y espesor del panel
BRAZO_W, BRAZO_E = 0.22, 0.07            # ancho y espesor de cada brazo
HUECOS_Y = 0.08                          # los dos huecos del panel están en y = ±HUECOS_Y
BASE_X, BASE_Y, BASE_E = 0.36, 0.40, 0.04  # placa de la base del telescopio (atornillada a los huecos)
BASE_ALTO = 0.10                         # altura de la base entre la placa y el tubo
TUBO_R = 0.28                            # radio del tubo del telescopio (3 kg)
TUBO_ATRAS = 0.50                        # cuánto tubo queda detrás de la base
TUBO_ADELANTE = 1.60                     # cuánto tubo sale hacia adelante (lado de la lente)

# 0° del NEMA = horizonte. 90° del NEMA = cenit. Es el mismo número que la
# elevación del cielo mientras el tubo va de horizontal a vertical.

# ─────────────────────────────── CÁMARA ─────────────────────────────────────
CAM_YAW = 0.62 + math.pi  # la cámara mira desde el norte: con az = 0 la lente queda hacia ti
CAM_PITCH = 0.36    # inclinación hacia abajo
CAM_Z = 1.30        # altura a la que mira la cámara
R_CIELO = 2.4       # desde la lente hasta el satélite, sobre el eje del tubo

Z_CAJA = PED_Z + PLATO_H
Z_EJE = Z_CAJA + EJE_Z

_IDX = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
        (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))


def _sombra(rgb, factor):
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))))


def _normal(pts):
    ax, ay, az = (pts[1][i] - pts[0][i] for i in range(3))
    bx, by, bz = (pts[2][i] - pts[0][i] for i in range(3))
    nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
    n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / n, ny / n, nz / n


class Gemelo(tk.Canvas):

    def __init__(self, parent):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0)
        self._az = 0.0
        self._el = 0.0
        self._sat_az = None
        self._sat_el = None
        self._arco = []
        self._texto = "Buscando la ISS..."
        self.bind("<Configure>", lambda _e: self._dibujar())

    def set_estado(self, az, el, sat_az, sat_el, arco, texto):
        self._az = float(az)
        self._el = max(0.0, min(90.0, float(el)))
        self._sat_az = sat_az
        self._sat_el = sat_el
        self._arco = arco or []
        self._texto = texto
        self._dibujar()

    # ───────────────────────── transformaciones ─────────────────────────────
    def _yaw(self, x, y, z):
        """Giro del XD3420: azimut en sentido horario visto desde arriba."""
        a = math.radians(self._az)
        c, s = math.cos(a), math.sin(a)
        return x * c + y * s, -x * s + y * c, z

    def _elev(self, x, y, z):
        """Giro del NEMA 23 sobre el eje X (el eje largo de la caja).

        Las piezas se definen con el panel ARRIBA (el = 0°, tubo horizontal).
        Subir el ángulo lleva la lente hacia el cenit. Después se aplica el yaw.
        """
        b = math.radians(self._el)
        c, s = math.cos(b), math.sin(b)
        y, z = y * c - z * s, y * s + z * c
        return self._yaw(x, y, z + Z_EJE)

    def _el_cielo(self):
        """Elevación real a la que mira el telescopio (negativa = hacia el suelo)."""
        return self._el

    # ───────────────────────────── primitivas ───────────────────────────────
    @staticmethod
    def _caja(x0, x1, y0, y1, z0, z1, rgb, tf=None):
        esq = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        if tf:
            esq = [tf(*p) for p in esq]
        return [([esq[i] for i in inds], rgb) for inds in _IDX]

    @staticmethod
    def _cilindro(inicio, fin, radio, n, rgb, tf=None):
        """Cilindro entre dos puntos cualquiera (sirve para ejes y platos)."""
        d = tuple(fin[i] - inicio[i] for i in range(3))
        largo = math.sqrt(sum(t * t for t in d))
        if largo < 1e-9:
            return []
        u = tuple(t / largo for t in d)
        aux = (0.0, 0.0, 1.0) if abs(u[2]) < 0.9 else (0.0, 1.0, 0.0)
        v = (u[1] * aux[2] - u[2] * aux[1],
             u[2] * aux[0] - u[0] * aux[2],
             u[0] * aux[1] - u[1] * aux[0])
        nv = math.sqrt(sum(t * t for t in v))
        v = tuple(t / nv for t in v)
        q = (u[1] * v[2] - u[2] * v[1],
             u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])

        def aro(c):
            pts = []
            for i in range(n):
                ang = 2.0 * math.pi * i / n
                p = tuple(c[j] + radio * (math.cos(ang) * v[j] + math.sin(ang) * q[j])
                          for j in range(3))
                pts.append(tf(*p) if tf else p)
            return pts

        a, b = aro(inicio), aro(fin)
        caras = [([a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]], rgb) for i in range(n)]
        caras += [(list(reversed(a)), rgb), (b, rgb)]
        return caras

    # ─────────────────────────── piezas del CAD ─────────────────────────────
    def _pedestal(self):
        """Caja fija de abajo. No gira."""
        cuerpo = (96, 108, 124)
        caras = self._caja(-PED_X / 2, PED_X / 2, -PED_Y / 2, PED_Y / 2,
                           0.0, PED_Z, cuerpo)
        caras += self._caja(-PED_X / 2 - 0.04, PED_X / 2 + 0.04,
                            -PED_Y / 2 - 0.04, PED_Y / 2 + 0.04,
                            0.0, 0.06, (62, 71, 84))
        return caras

    def _plato_xd(self):
        """El círculo rojo del CAD: salida del XD3420. Gira con el azimut."""
        return self._cilindro((0, 0, PED_Z), (0, 0, Z_CAJA),
                              PLATO_R, 28, (178, 72, 72), self._yaw)

    def _caja_larga(self):
        """Caja larga sobre el plato. Gira con el azimut. El extremo +X va abierto."""
        g = self._yaw
        c = (112, 124, 142)
        hx, hy = CAJA_L / 2, CAJA_P / 2
        t = PARED
        caras = self._caja(-hx, hx, -hy, hy, Z_CAJA, Z_CAJA + t, c, g)                 # piso
        caras += self._caja(-hx, hx, -hy, hy, Z_CAJA + CAJA_A - t, Z_CAJA + CAJA_A, c, g)  # tapa
        caras += self._caja(-hx, hx, -hy, -hy + t, Z_CAJA, Z_CAJA + CAJA_A, c, g)      # frente
        caras += self._caja(-hx, hx, hy - t, hy, Z_CAJA, Z_CAJA + CAJA_A, c, g)        # fondo
        caras += self._caja(-hx, -hx + t, -hy, hy, Z_CAJA, Z_CAJA + CAJA_A, c, g)      # extremo -X
        # tornillos de la tapa, como en el CAD
        for x in (-hx + 0.08, hx - 0.08):
            for y in (-hy + 0.07, hy - 0.07):
                caras += self._caja(x - 0.025, x + 0.025, y - 0.025, y + 0.025,
                                    Z_CAJA + CAJA_A, Z_CAJA + CAJA_A + 0.02,
                                    (45, 53, 66), g)
        return caras

    def _brazos_y_panel(self):
        """Lo que mueve el NEMA: dos brazos con el eje en un extremo y el panel
        en el otro. Se rotan juntos alrededor del eje X."""
        f = self._elev
        hx = CAJA_L / 2
        brazo = (150, 160, 176)
        panel = (170, 180, 194)
        caras = []
        for lado in (-1, 1):
            xa = lado * (hx + 0.01)
            xb = lado * (hx + 0.01 + BRAZO_E)
            x0, x1 = min(xa, xb), max(xa, xb)
            caras += self._caja(x0, x1, -BRAZO_W / 2, BRAZO_W / 2, 0.0, RADIO, brazo, f)
            caras += self._cilindro((x0, 0, 0), (x1, 0, 0), BRAZO_W / 2, 16, brazo, f)
            caras += self._cilindro((x0, 0, RADIO), (x1, 0, RADIO), BRAZO_W / 2, 16, brazo, f)
            # eje del NEMA que atraviesa la pared
            xi = lado * (hx - 0.12)
            caras += self._cilindro((xi, 0, 0), (xa, 0, 0), 0.07, 12, (200, 208, 218), f)
        caras += self._caja(-hx, hx, -PANEL_W / 2, PANEL_W / 2,
                            RADIO - PANEL_E / 2, RADIO + PANEL_E / 2, panel, f)
        for y in (-HUECOS_Y, HUECOS_Y):  # huecos de montaje del telescopio
            caras += self._caja(-0.04, 0.04, y - 0.035, y + 0.035,
                                RADIO + PANEL_E / 2, RADIO + PANEL_E / 2 + 0.02,
                                (40, 48, 60), f)
        return caras

    def _eje_tubo(self):
        """Altura (en el marco del NEMA) del eje del tubo sobre el eje de giro."""
        return RADIO + PANEL_E / 2 + BASE_E + BASE_ALTO + TUBO_R

    def _telescopio(self):
        """Telescopio de 3 kg, acostado sobre una base atornillada a los dos huecos.

        El tubo corre a lo largo de Y (paralelo al panel). Con el NEMA a 0°
        queda horizontal y la lente mira al horizonte. A 90° mira al cenit.
        """
        f = self._elev
        z_panel = RADIO + PANEL_E / 2
        z_placa = z_panel + BASE_E
        z_tubo = self._eje_tubo()
        blanco = (226, 229, 236)
        caras = self._caja(-BASE_X / 2, BASE_X / 2, -BASE_Y / 2, BASE_Y / 2,
                           z_panel, z_placa, (150, 110, 190), f)
        for y in (-HUECOS_Y, HUECOS_Y):  # tornillos en los huecos
            caras += self._cilindro((0, y, z_placa), (0, y, z_placa + 0.025),
                                    0.025, 10, (40, 48, 60), f)
        caras += self._caja(-0.09, 0.09, -0.14, 0.14, z_placa,
                            z_placa + BASE_ALTO, (150, 110, 190), f)           # pedestal
        caras += self._caja(-0.14, 0.14, -0.22, 0.22, z_placa + BASE_ALTO - 0.04,
                            z_placa + BASE_ALTO, (120, 90, 160), f)            # cuna
        caras += self._cilindro((0, -TUBO_ATRAS, z_tubo), (0, TUBO_ADELANTE, z_tubo),
                                TUBO_R, 32, blanco, f)
        caras += self._cilindro((0, -TUBO_ATRAS - 0.05, z_tubo), (0, -TUBO_ATRAS, z_tubo),
                                TUBO_R + 0.015, 32, (60, 68, 82), f)           # tapa trasera
        caras += self._cilindro((0, TUBO_ADELANTE - 0.20, z_tubo), (0, TUBO_ADELANTE, z_tubo),
                                TUBO_R + 0.03, 32, (170, 176, 190), f)         # parasol
        caras += self._cilindro((0, TUBO_ADELANTE, z_tubo), (0, TUBO_ADELANTE + 0.012, z_tubo),
                                TUBO_R - 0.035, 32, (110, 190, 235), f)        # lente
        return caras

    # ───────────────────────────── proyección ───────────────────────────────
    def _proy(self, x, y, z, ox, oy, escala):
        ca, sa = math.cos(CAM_YAW), math.sin(CAM_YAW)
        xr = ca * x - sa * y
        yr = sa * x + ca * y
        ce, se = math.cos(CAM_PITCH), math.sin(CAM_PITCH)
        zc = z - CAM_Z
        y2 = ce * yr - se * zc
        z2 = se * yr + ce * zc
        persp = 5.0 / (5.0 + y2 + 3.2)
        return ox + xr * escala * persp, oy - z2 * escala * persp, y2

    @staticmethod
    def _direccion(az, el):
        a, e = math.radians(az), math.radians(el)
        return (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))

    def _origen_mira(self):
        """La lente. El cielo se mide desde aquí, no desde el eje de la caja."""
        return self._elev(0.0, TUBO_ADELANTE, self._eje_tubo())

    def _punto_cielo(self, az, el, ox, oy, escala):
        d = self._direccion(az, el)
        o = self._origen_mira()
        x, y, prof = self._proy(o[0] + d[0] * R_CIELO,
                                o[1] + d[1] * R_CIELO,
                                o[2] + d[2] * R_CIELO, ox, oy, escala)
        return None if prof < -2.4 else (x, y)

    # ────────────────────────────── dibujo ──────────────────────────────────
    def _dibujar(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 30 or h < 30:
            return
        self.create_rectangle(0, 0, w, h, fill="#0a1020", outline="")
        self.create_text(12, 14, text=self._texto, anchor="w",
                         fill=TEXT, font=(FF, FS - 1))
        self.create_text(12, h - 12,
                         text=(f"Base {self._az:.1f}°   ·   NEMA {self._el:.1f}°   ·   "
                               f"el. telescopio {self._el_cielo():.1f}°"),
                         anchor="w", fill=TEXTDIM, font=(FF, FS - 1))

        ox, oy = 0.50 * w, 0.60 * h
        escala = min(w / 4.0, h / 4.4)

        caras = (self._pedestal() + self._plato_xd()
                 + self._caja_larga() + self._brazos_y_panel()
                 + self._telescopio())
        lista = []
        for pts, rgb in caras:
            proy = [self._proy(*p, ox, oy, escala) for p in pts]
            if any(p[2] < -2.6 for p in proy):
                continue
            nx, ny, nz = _normal(pts)
            luz = abs(0.25 * nx - 0.55 * ny + 0.79 * nz)
            lista.append((sum(p[2] for p in proy) / len(proy), proy, rgb, luz))
        lista.sort(key=lambda v: -v[0])
        for _, proy, rgb, luz in lista:
            self.create_polygon([(p[0], p[1]) for p in proy],
                                fill=_sombra(rgb, 0.32 + 0.72 * luz),
                                outline=_sombra(rgb, 0.27 + 0.38 * luz), width=1)
        self._rayo(ox, oy, escala)
        self._cielo(ox, oy, escala, w, h)

    def _rayo(self, ox, oy, escala):
        """Línea desde la lente hasta donde quedaría la ISS si el tubo la apunta."""
        p0 = self._origen_mira()
        d = self._direccion(self._az, self._el_cielo())
        p1 = tuple(p0[i] + d[i] * R_CIELO for i in range(3))
        a = self._proy(*p0, ox, oy, escala)
        b = self._proy(*p1, ox, oy, escala)
        self.create_line(a[0], a[1], b[0], b[1], fill=CYAN, width=2, dash=(5, 3))
        self.create_oval(b[0] - 3, b[1] - 3, b[0] + 3, b[1] + 3, fill=CYAN, outline="")

    def _cielo(self, ox, oy, escala, w, h):
        previo = None
        for az, el in self._arco:
            p = self._punto_cielo(az, el, ox, oy, escala)
            if p is not None and not (0 < p[0] < w and 0 < p[1] < h):
                p = None
            if p is not None and previo is not None:
                self.create_line(*previo, *p, fill=ORANGE, width=2, dash=(3, 3))
            previo = p
        if self._sat_az is None or self._sat_el is None:
            return
        visible = self._sat_el >= 0.0
        sat = self._punto_cielo(self._sat_az, max(0.0, self._sat_el), ox, oy, escala)
        if sat is None:
            return
        x = min(w - 16, max(16, sat[0]))
        y = min(h - 24, max(28, sat[1]))
        col = CYAN if visible else TEXTDIM
        self.create_oval(x - 7, y - 7, x + 7, y + 7, fill=col, outline=TEXT)
        self.create_line(x - 11, y, x + 11, y, fill=col, width=1)
        self.create_line(x, y - 11, x, y + 11, fill=col, width=1)
        self.create_text(x + 14, y - 12, text="ISS", anchor="w",
                         fill=col, font=(FF, 8, "bold"))
