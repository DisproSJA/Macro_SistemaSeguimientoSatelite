#ifndef TELEMETRIA_H
#define TELEMETRIA_H

#include <stdint.h>

/* Una linea por muestra, grados con un decimal y el mando con dos.
   B,consigna,posicion,error,mando,E,consigna,posicion,error,mando
   En la base el mando son voltios. En la elevacion, 24.00 es PASOS_MAX_HZ. */

void Telemetria_Enviar(int32_t cons_b, int32_t pos_b, int16_t mando_b,
                       int32_t cons_e, int32_t pos_e, int16_t mando_e);

#endif
