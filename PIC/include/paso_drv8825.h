#ifndef PASO_DRV8825_H
#define PASO_DRV8825_H

#include <stdint.h>

/* STEP en RC1, DIR en RC2, EN en RA4 (activo en bajo).
   El mando del PID se vuelve frecuencia de pulsos. Cero Hz deja el eje frenado
   mientras el driver siga habilitado. */

void Paso_Iniciar(void);
void Paso_ISR(void);
void Paso_AplicarMv(int16_t milivoltios);
void Paso_Detener(void);
void Paso_Soltar(void);

#endif
