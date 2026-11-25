#include <xc.h>
#include "paso_drv8825.h"
#include "configuracion.h"

/* Se suma en cada tick de 20 kHz. Al dar la vuelta el acumulador, sale un flanco.
   6553 * 20 kHz / 65536 ≈ 2000 pasos/s cuando el PID esta en el tope. */
#define INCR_A_TOPE                     ((PASOS_MAX_HZ * 65536L) / TICK_PASO_HZ)

static volatile uint16_t acumulado;
static volatile uint16_t incremento;
static volatile int8_t sentido;

/* Sube STEP el tiempo minimo del DRV8825 y lo baja. */
static void pulso(void)
{
    LATCbits.LATC1 = 1;
    __delay_us(2);
    LATCbits.LATC1 = 0;
}

/* Timer4 a 20 kHz. El driver sigue suelto y no hay pulsos. */
void Paso_Iniciar(void)
{
    acumulado = 0;
    incremento = 0;
    sentido = 0;
    LATCbits.LATC1 = 0;
    LATCbits.LATC2 = 0;
    LATAbits.LATA4 = 1;

    T4CLKCONbits.CS = 0b0001;
    T4CONbits.CKPS = 0b010;       /* 1:4. 8 MHz / 4 / 100 = 20 kHz */
    T4CONbits.OUTPS = 0;
    T4HLTbits.MODE = 0;
    T4HLTbits.PSYNC = 1;
    T4PR = 99;
    T4TMR = 0;

    PIR4bits.TMR4IF = 0;
    T4CONbits.ON = 1;
}

/* Un tick. Como mucho un paso, para no alargar la interrupcion. */
void Paso_ISR(void)
{
    uint16_t antes;
    uint16_t paso;
    uint8_t dir;

    paso = incremento;
    if (paso == 0U) {
        return;
    }

    if (sentido < 0) {
        dir = 1U;
    } else {
        dir = 0U;
    }
#if INVERTIR_GIRO_ELEV
    dir = (uint8_t)(dir ^ 1U);
#endif
    LATCbits.LATC2 = dir;

    antes = acumulado;
    acumulado = (uint16_t)(acumulado + paso);
    if (acumulado < antes) {
        pulso();
    }
}

/* Mando del PID. El signo es DIR y la magnitud es la frecuencia. */
void Paso_AplicarMv(int16_t milivoltios)
{
    int32_t mag;
    uint16_t nuevo_incr;
    int8_t nuevo_sentido;
    uint8_t gie;

    if (milivoltios > VLIM_MV) {
        milivoltios = VLIM_MV;
    } else if (milivoltios < -VLIM_MV) {
        milivoltios = -VLIM_MV;
    }

    if (milivoltios > 0) {
        mag = milivoltios;
        nuevo_sentido = 1;
    } else if (milivoltios < 0) {
        mag = -milivoltios;
        nuevo_sentido = -1;
    } else {
        mag = 0;
        nuevo_sentido = 0;
    }

    nuevo_incr = (uint16_t)((mag * INCR_A_TOPE) / VLIM_MV);
    LATAbits.LATA4 = 0;

    gie = INTCONbits.GIE;
    INTCONbits.GIE = 0;
    sentido = nuevo_sentido;
    incremento = nuevo_incr;
    INTCONbits.GIE = gie;
}

/* Deja de avanzar y mantiene las bobinas, para que la elevacion no caiga. */
void Paso_Detener(void)
{
    uint8_t gie;

    gie = INTCONbits.GIE;
    INTCONbits.GIE = 0;
    incremento = 0;
    sentido = 0;
    INTCONbits.GIE = gie;
    LATCbits.LATC1 = 0;
}

/* Corta el driver. El eje queda libre. */
void Paso_Soltar(void)
{
    Paso_Detener();
    LATCbits.LATC1 = 0;
    LATAbits.LATA4 = 1;
}
