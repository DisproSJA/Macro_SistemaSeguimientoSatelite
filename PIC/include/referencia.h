#ifndef REFERENCIA_H
#define REFERENCIA_H

#include <stdint.h>

/* Que tiene que hacer el main con ese eje en esta muestra. */
#define REF_COAST                       0U
#define REF_PID                         1U
#define REF_DIRECTO                     2U      /* base con tension fija (BU) */

void Referencia_Iniciar(void);
void Referencia_Parar(uint8_t eje);

/* Grados en decimas. 0 si el numero se sale del eje. */
uint8_t Referencia_FijarDecimas(uint8_t eje, int16_t decimas);

/* Lleva la consigna al cero que se marco. No mueve el cero. */
void Referencia_IrAlCero(uint8_t eje);

/* El angulo de este instante pasa a ser 0. */
void Referencia_FijarCeroAqui(uint8_t eje);

/* Velocidad maxima en milesimas de grado/s, de 0 a 360000. 0 apaga la rampa. */
uint8_t Referencia_FijarVelMax(uint8_t eje, int32_t milesimas);

/* Aceleracion maxima en milesimas de grado/s^2, de 1 a 360000. */
uint8_t Referencia_FijarAcelMax(uint8_t eje, int32_t milesimas);

/* Lazo abierto de la base. V0 en mV (0 a 24000). Kv en mV por grado/s. */
uint8_t Referencia_FijarV0(int32_t milivoltios);
uint8_t Referencia_FijarKv(int32_t mv_por_grado_s);

/* BU: tension fija en la base para medir V0 y Kv. No mueve la posicion estimada. */
uint8_t Referencia_TensionDirecta(int32_t milivoltios);
int16_t Referencia_Tension(void);

/* Tension de la base para la velocidad de la rampa en esta muestra. */
int16_t Referencia_MandoAbierto(void);

/* Donde cree el PIC que esta el eje, en cuentas. Para la base es la rampa. */
int32_t Referencia_Estimada(uint8_t eje);

/* 0 V si en el tope el PID empujaria mas hacia afuera. */
int16_t Referencia_AplicarFin(uint8_t eje, int32_t posicion, int16_t mando);

/* Avanza la rampa una muestra y entrega el punto que debe seguir el PID. */
uint8_t Referencia_Actualizar(uint8_t eje, int32_t *consigna);
int16_t Referencia_Tope(void);

#endif
