"""
Órbita de un satélite a partir del TLE de Celestrak.

La página no entrega el azimut ni la elevación. Entrega las dos líneas
de la órbita. Con la latitud del observador y la hora, Skyfield calcula
hacia dónde apuntar.
"""

import os
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np

os.environ.setdefault(
    "SKYFIELD_DATA",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".skyfield"),
)

ISS_NORAD = 25544
UMBRAL_ELEV = 10.0
URL_TLE = "https://celestrak.org/NORAD/elements/gp.php?CATNR={catnr}&FORMAT=tle"


class Paso:
    """Un tramo en el que el satélite está por encima del umbral."""

    def __init__(self, inicio, fin, max_el, muestras):
        self.inicio = inicio
        self.fin = fin
        self.max_el = max_el
        self.muestras = muestras

    @property
    def duracion_s(self):
        return self.fin - self.inicio

    def en(self, t):
        """Azimut y elevación interpolados. t es tiempo unix."""
        datos = self.muestras
        if t <= datos[0][0]:
            return datos[0][1], datos[0][2]
        if t >= datos[-1][0]:
            return datos[-1][1], datos[-1][2]
        lo = 0
        hi = len(datos) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if datos[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        t0, az0, el0 = datos[lo]
        t1, az1, el1 = datos[hi]
        u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
        daz = (az1 - az0 + 180.0) % 360.0 - 180.0
        return (az0 + daz * u) % 360.0, el0 + (el1 - el0) * u


class Orbita:
    def __init__(self):
        self.nombre = "ISS"
        self.catnr = ISS_NORAD
        self.linea1 = ""
        self.linea2 = ""
        self.pasos = []
        self.error = None
        self._ts = None
        self._sat = None
        self._obs = None
        self._lat = None
        self._lon = None
        self._alt = None

    def descargar(self, catnr):
        url = URL_TLE.format(catnr=int(catnr))
        req = urllib.request.Request(
            url, headers={"User-Agent": "SeguidorSatelite/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            texto = resp.read().decode("utf-8", errors="replace")
        nombre, l1, l2 = _partir_tle(texto)
        self.nombre = nombre or f"NORAD {int(catnr)}"
        self.catnr = int(catnr)
        self.linea1 = l1
        self.linea2 = l2
        self._sat = None
        self.pasos = []
        self.error = None

    def preparar(self, lat, lon, alt_m):
        """Arma el satélite y busca los pasos de las últimas 14 h y las próximas 18 h."""
        from skyfield.api import EarthSatellite, load, wgs84

        if not self.linea1:
            raise RuntimeError("Todavía no hay TLE")
        if self._ts is None:
            self._ts = load.timescale()
        self._sat = EarthSatellite(
            self.linea1, self.linea2, self.nombre, self._ts)
        self._obs = wgs84.latlon(float(lat), float(lon), elevation_m=float(alt_m))
        self._lat = float(lat)
        self._lon = float(lon)
        self._alt = float(alt_m)
        self.pasos = _buscar_pasos(self._ts, self._sat, self._obs)
        self.error = None

    def ahora(self):
        """Azimut 0-360 y elevación en grados, en este instante."""
        if self._sat is None:
            raise RuntimeError("Todavía no se calcula la órbita")
        t = self._ts.now()
        alt, az, _dist = (self._sat - self._obs).at(t).altaz()
        return float(az.degrees) % 360.0, float(alt.degrees)

    def paso_en_curso(self, t=None):
        t = time_now() if t is None else t
        for paso in self.pasos:
            if paso.inicio <= t <= paso.fin:
                return paso
        return None

    def paso_siguiente(self, t=None):
        t = time_now() if t is None else t
        futuros = [p for p in self.pasos if p.inicio > t]
        if not futuros:
            return None
        return min(futuros, key=lambda p: p.inicio)

    def paso_anterior(self, t=None):
        t = time_now() if t is None else t
        pasados = [p for p in self.pasos if p.fin < t]
        if not pasados:
            return None
        return max(pasados, key=lambda p: p.fin)


def time_now():
    return datetime.now(timezone.utc).timestamp()


def consigna_base(azimut, posicion):
    """Elige la vuelta de -360 a 360 más cercana a donde está la base."""
    if posicion is None:
        posicion = 0.0
    azimut = float(azimut) % 360.0
    candidatos = []
    for k in (-1, 0, 1):
        valor = azimut + 360.0 * k
        if -360.0 <= valor <= 360.0:
            candidatos.append(valor)
    if not candidatos:
        return max(-360.0, min(360.0, azimut if azimut <= 180.0 else azimut - 360.0))
    return min(candidatos, key=lambda valor: abs(valor - posicion))


def rampa(t, t0, duracion, inicio, fin):
    """Sube suave de inicio a fin. t y t0 en segundos."""
    if duracion <= 0.0:
        return fin
    u = (t - t0) / duracion
    if u <= 0.0:
        return inicio
    if u >= 1.0:
        return fin
    s = u * u * (3.0 - 2.0 * u)
    return inicio + (fin - inicio) * s


def _partir_tle(texto):
    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    if len(lineas) >= 3 and lineas[-2].startswith("1 ") and lineas[-1].startswith("2 "):
        return lineas[-3], lineas[-2], lineas[-1]
    if len(lineas) >= 2 and lineas[-2].startswith("1 ") and lineas[-1].startswith("2 "):
        return "", lineas[-2], lineas[-1]
    raise ValueError("Celestrak no devolvió un TLE")


def _buscar_pasos(ts, sat, obs):
    ahora = datetime.now(timezone.utc)
    inicio = ahora - timedelta(hours=14)
    segundos = np.arange(0.0, (14 + 18) * 3600.0, 20.0)
    tiempos = ts.utc(
        inicio.year, inicio.month, inicio.day,
        inicio.hour, inicio.minute, inicio.second + segundos)
    alt, az, _dist = (sat - obs).at(tiempos).altaz()
    elev = np.asarray(alt.degrees, dtype=float)
    azimut = np.asarray(az.degrees, dtype=float) % 360.0
    unix0 = inicio.timestamp()

    pasos = []
    i = 0
    n = len(elev)
    while i < n:
        if elev[i] < UMBRAL_ELEV:
            i += 1
            continue
        j = i
        while j < n and elev[j] >= UMBRAL_ELEV:
            j += 1
        t0 = unix0 + float(segundos[i])
        t1 = unix0 + float(segundos[min(j, n - 1)])
        if t1 - t0 >= 60.0:
            fino = np.arange(float(segundos[i]), float(segundos[min(j, n - 1)]) + 0.5, 0.5)
            tf = ts.utc(
                inicio.year, inicio.month, inicio.day,
                inicio.hour, inicio.minute, inicio.second + fino)
            alt_f, az_f, _d = (sat - obs).at(tf).altaz()
            el_f = np.asarray(alt_f.degrees, dtype=float)
            az_f = np.asarray(az_f.degrees, dtype=float) % 360.0
            muestras = [
                (unix0 + float(fino[k]), float(az_f[k]), float(el_f[k]))
                for k in range(len(fino))
            ]
            pasos.append(Paso(muestras[0][0], muestras[-1][0], float(np.max(el_f)), muestras))
        i = j
    return pasos
