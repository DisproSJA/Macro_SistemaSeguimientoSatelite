#ifndef CONTROL_PID_H
#define CONTROL_PID_H

#include <stdint.h>

/* La misma ley en los dos ejes. Integral en trapezio, derivada con Euler
   hacia atras sobre la posicion, para no patear en el escalon.
   La salida es el mando en las mismas unidades que el tope (mV o su equivalente). */

void Control_Iniciar(void);
void Control_Reiniciar(uint8_t eje);
uint8_t Control_FijarKp(uint8_t eje, int16_t kp_milli);
uint8_t Control_FijarKi(uint8_t eje, int16_t ki_milli);
uint8_t Control_FijarKd(uint8_t eje, int16_t kd_milli);
int16_t Control_Calcular(uint8_t eje, int32_t consigna, int32_t posicion,
                         int16_t tope);

#endif
