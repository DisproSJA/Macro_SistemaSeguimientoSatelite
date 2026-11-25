#ifndef CONFIGURACION_H
#define CONFIGURACION_H

/* Dos ejes. B es la base (XD-3420, una vuelta, lazo abierto).
   E es la elevacion (NEMA 23, 0 a 90, PID con encoder).
   El Ts es el del Micro 3. La unidad de afuera ahora es el grado. */

#define FOSC_HZ                         32000000UL
#define _XTAL_FREQ                      FOSC_HZ

#define FS_HZ                           150UL
#define BAUDIOS_UART                    115200UL

#define EJE_BASE                        0U
#define EJE_ELEV                        1U
#define EJE_CANT                        2U

/* 600 PPR y cuadratura x2: 1200 cuentas por vuelta del encoder.
   Si el encoder no va 1:1 con el eje que se ve, aqui van las cuentas
   de una vuelta de ese eje. 1 cuenta = 0.3 grados con 1200. */
#define CUENTAS_POR_VUELTA              1200L
#define DECIMAS_POR_VUELTA              3600L

/* El PID pasa de cuentas a grados con 360/cuentas_por_vuelta. */
#define ESCALA_NUM                      360L
#define ESCALA_DEN                      CUENTAS_POR_VUELTA

/* Desde el cero del encendido. La salida del XD da una vuelta para cada lado.
   El NEMA arranca horizontal: 0 es el horizonte y 90 es el cenit. */
#define BASE_DECIMAS_MIN                (-3600)
#define BASE_DECIMAS_MAX                3600
#define ELEV_DECIMAS_MIN                0
#define ELEV_DECIMAS_MAX                900

/* Si al probar el eje se aleja de la consigna, se cambia el que corresponda. */
#define INVERTIR_GIRO_BASE              0
#define INVERTIR_ENCODER_BASE           0
#define INVERTIR_GIRO_ELEV              0
#define INVERTIR_ENCODER_ELEV           0

/* Mismas ganancias de arranque que el Micro 3. En la base, 1.5 es V/grado.
   En el NEMA el numero es el mismo, pero 24.00 de salida es PASOS_MAX_HZ,
   no 24 V. Se sintonizan las dos en la mesa. */
#define KP_MILLI_INICIAL                1500
#define KI_MILLI_INICIAL                0
#define KD_MILLI_INICIAL                70

/* Rampa de la consigna, en milesimas: grados/s y grados/s^2.
   Velocidad 0 apaga la rampa y la consigna salta de una vez. */
#define VEL_MAX_MILLI_INICIAL           20000L
#define ACEL_MAX_MILLI_INICIAL          20000L

/* La base va en lazo abierto: sin encoder, la posicion es la de la rampa.
   Tension = V0 + Kv * velocidad. V0 vence la friccion; Kv en V por grado/s
   del plato rojo (ya incluye la polea 1:3). Se miden en la mesa. */
#define BASE_V0_MV_INICIAL              1500L
#define BASE_KV_MILLI_INICIAL           4L

/* Tope del PID, igual en los dos ejes. En el XD son mV de los 24 V.
   En el NEMA, ±24000 es ±PASOS_MAX_HZ en el pin STEP. */
#define VM_MV                           24000
#define VLIM_MV                         24000

/* Pulsos por segundo con la salida del PID en el tope.
   El DIP fija el micropaso; este numero es la velocidad del pin STEP.
   Si el motor se dispara, se baja. */
#define PASOS_MAX_HZ                    2000L

/* Timer4 reparte los pasos. 8 MHz / 4 / 100 = 20 kHz. */
#define TICK_PASO_HZ                    20000L

/* 65536 - 8000000/150. El timer cuenta Fosc/4. */
#define TMR0_RECARGA                    12203U

#define TAM_RX                          48U
#define TAM_TX                          128U
#define LARGO_LINEA                     28U

#endif
