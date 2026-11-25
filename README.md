# Sistema de seguimiento de satélites

Proyecto final de Proyecto de diseño Mecatrónica

**Integrantes:** Juan Andrés Sánchez, Sofía Vega y Andrés Felipe Trujillo.

## ¿De qué trata?

Construimos un seguidor de satélites de dos grados de libertad que apunta un telescopio hacia la Estación Espacial Internacional (ISS, NORAD 25544) mientras pasa sobre Bogotá.

- **Base (azimut):** motor DC XD-3420 con driver DRV8871 y una polea 1:3. Gira 360° y trabaja en lazo abierto: la posición se estima con una rampa de velocidad y una calibración de tensión contra velocidad.
- **Elevación:** motor paso a paso NEMA 23 con driver DRV8825 a 1/8 de paso y un encoder de 600 PPR. Se controla con un PID y va de 0° (horizonte) a 90° (cenit).

El computador hace los cálculos de la órbita y el PIC16F18446 solo mueve los motores:

1. La interfaz descarga el TLE de la ISS desde Celestrak.
2. Con Skyfield (modelo SGP4) y nuestra ubicación calcula el azimut y la elevación en cada instante.
3. Manda esos ángulos por UART al PIC, que los sigue con una rampa trapezoidal de velocidad.



## Estructura

```
Codigo/
├── PIC/                    Firmware del PIC16F18446 (MPLAB, XC8)
│   ├── include/
│   │   └── configuracion.h Constantes: muestreo, límites, ganancias, rampas
│   └── src/
│       ├── main.c          Lazo principal a 150 Hz
│       ├── referencia.c    Rampa de velocidad y lazo abierto de la base
│       ├── control_pid.c   PID discreto del NEMA
│       ├── drv8871_pwm.c   PWM del motor DC (base)
│       ├── paso_drv8825.c  Pulsos STEP/DIR del NEMA
│       ├── encoder.c       Lectura de encoders en cuadratura
│       ├── protocolo.c     Comandos por UART (BP, EP, BV, EKp...)
│       ├── telemetria.c    Envío de consigna, posición, error y mando
│       └── ...             Pines, UART, temporizador e interrupciones
├── GUI/                    Interfaz en Python
│   ├── interfaz_seguidor.py  Ventana principal: conexión, parámetros, modos y gráficas
│   ├── orbita.py             Descarga del TLE y cálculo de los pasos de la ISS
│   └── gemelo.py             Gemelo digital 3D del mecanismo
└── Insumos/
    └── Esquematico Final.pdf Esquemático de la tarjeta
```



## Modos de la interfaz

- **En vivo:** sigue a la ISS en tiempo real cuando está a más de 10° sobre el horizonte.
- **Repetir paso:** reproduce un paso real ya calculado. Es la prueba principal en el laboratorio.
- **Rampa:** lleva los ejes a un ángulo de forma suave, sin usar la órbita.
- **Manual:** mueve la base y el NEMA a un azimut y una elevación escritos a mano.

Desde la interfaz también se ajustan las ganancias del PID, la rampa de cada motor y la calibración de la base (V0 y Kv). Además se ven la respuesta al escalón (ts, te y Mp) y el gemelo digital.

## Cómo usarlo

1. Abrir la carpeta `PIC` en MPLAB, compilar y programar el PIC16F18446.
2. Instalar las dependencias de Python:
  ```
   py -3 -m pip install pyserial matplotlib numpy pillow skyfield
  ```
3. Desde la carpeta `Codigo`, abrir la interfaz:
  ```
   py -3 GUI\interfaz_seguidor.py
  ```
4. Antes de encender, dejar el telescopio horizontal y mirando al norte geográfico. Ese punto queda como cero de los dos ejes.

