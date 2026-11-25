#ifndef ENCODER_H
#define ENCODER_H

#include <stdint.h>

/* Base, conector sensor 2: cuadratura x2 en hardware. A en RC7, B en RB7.
   Elevacion, conector sensor 1: los dos timers con compuerta ya estan usados,
   asi que A (RC3) interrumpe y B (RC6) da el signo. Misma resolucion, x2. */

void Encoder_Iniciar(void);
void Encoder_ISR(void);

void Encoder_FijarCero(uint8_t eje);
uint8_t Encoder_Ab(uint8_t eje);
int32_t Encoder_Cuentas(uint8_t eje);
int32_t Encoder_Posicion(uint8_t eje);

#endif
