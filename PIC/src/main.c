#include <xc.h>
#include "configuracion.h"
#include "pines.h"
#include "uart.h"
#include "temporizador.h"
#include "encoder.h"
#include "control_pid.h"
#include "drv8871_pwm.h"
#include "paso_drv8825.h"
#include "referencia.h"
#include "protocolo.h"
#include "telemetria.h"
#include "interrupciones.h"

/* Lazo abierto: la tension sale de la velocidad de la rampa y la posicion
   es la que la rampa ya recorrio. No se lee el encoder. */
static void eje_base(int32_t *consigna, int32_t *posicion, int16_t *mando)
{
    uint8_t salida;

    salida = Referencia_Actualizar(EJE_BASE, consigna);
    *posicion = Referencia_Estimada(EJE_BASE);
    if (salida == REF_PID) {
        *mando = Referencia_MandoAbierto();
        Pwm_AplicarMv(*mando);
    } else if (salida == REF_DIRECTO) {
        *mando = Referencia_Tension();
        Pwm_AplicarMv(*mando);
    } else {
        Pwm_Soltar();
        *mando = 0;
    }
}

static void eje_elevacion(int32_t *consigna, int32_t *posicion, int16_t *mando)
{
    uint8_t salida;

    salida = Referencia_Actualizar(EJE_ELEV, consigna);
    *posicion = Encoder_Posicion(EJE_ELEV);
    if (salida == REF_PID) {
        *mando = Control_Calcular(EJE_ELEV, *consigna, *posicion, Referencia_Tope());
        *mando = Referencia_AplicarFin(EJE_ELEV, *posicion, *mando);
        Paso_AplicarMv(*mando);
    } else {
        Paso_Detener();
        *mando = 0;
    }
}

void main(void)
{
    int32_t cons_b;
    int32_t pos_b;
    int16_t mando_b;
    int32_t cons_e;
    int32_t pos_e;
    int16_t mando_e;

    Pines_Iniciar();              /* 32 MHz, pines y PPS */
    Uart_Iniciar();               /* 115200 8N1 */
    Pwm_Iniciar();                /* 31.25 kHz, XD suelto */
    Paso_Iniciar();               /* 20 kHz, NEMA suelto */
    Encoder_Iniciar();            /* base en hardware, elevacion por flanco */
    Temporizador_Iniciar();       /* muestra de 150 Hz */
    Control_Iniciar();            /* Kp 1.5, Ki 0, Kd 0.07 en los dos */
    Referencia_Iniciar();         /* el angulo de encendido queda en 0 */
    Protocolo_Iniciar();
    Interrupciones_Habilitar();

    Uart_EnviarTexto("RDY\r\n");

    while (1) {
        Protocolo_Procesar();

        if (Temporizador_TomarMuestra()) {
            eje_base(&cons_b, &pos_b, &mando_b);
            eje_elevacion(&cons_e, &pos_e, &mando_e);
            Telemetria_Enviar(cons_b, pos_b, mando_b, cons_e, pos_e, mando_e);
        }
    }
}
