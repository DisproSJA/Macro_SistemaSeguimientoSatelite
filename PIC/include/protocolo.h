#ifndef PROTOCOLO_H
#define PROTOCOLO_H

#include <stdint.h>

/* Una linea, cerrada con enter.
   B es la base y E la elevacion.
   BP45.0 consigna en grados. BZ va a 0. B0 marca el cero aqui.
   BKp:1.5  BKi:0  BKd:0.07
   BV:20 velocidad maxima (grados/s, 0 sin rampa). BA:20 aceleracion (grados/s^2).
   Base en lazo abierto: BV0:1.5 tension de arranque (V), BKv:0.004 V por grado/s,
   BU12 tension fija para calibrar hasta BS (la posicion estimada no cambia).
   BS frena ese eje. S frena los dos. BC lee el encoder.
   EF corta las bobinas del NEMA para poder girarlo a mano. */

void Protocolo_Iniciar(void);
void Protocolo_Procesar(void);

#endif
