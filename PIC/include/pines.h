#ifndef PINES_H
#define PINES_H

#include <xc.h>
#include <stdint.h>

/* Oscilador, GPIO y PPS.
   XD: IN1 RC0 (PWM6), IN2 RA5 (PWM7).
   NEMA: STEP RC1, DIR RC2, EN RA4 en alto para dejar el DRV8825 suelto.
   El DIP de M0 M1 M2 no pasa por el PIC. */

void Pines_Iniciar(void);

#endif
