#include <xc.h>
#include "encoder.h"
#include "configuracion.h"

/* La base la cuentan los timers, sin interrupciones.
   Timer1 cuenta subidas de A con B en bajo.
   Timer5 cuenta bajadas de A con B en bajo. La CLC1 le da A negada.
   El signo es el del Micro 3: con B en bajo, la subida resta y la bajada suma.
   El nivel de A completa la cuenta que cae con B en alto. Queda x2. */

static int32_t cero_base;
static uint8_t a_inicial;

static volatile int32_t cuentas_elev;
static int32_t cero_elev;
static uint8_t a_elev;

/* A de la base es RC7, B es RB7. A del NEMA es RC3, B es RC6. */
void Encoder_Iniciar(void)
{
    TRISCbits.TRISC7 = 1;
    TRISBbits.TRISB7 = 1;
    TRISCbits.TRISC3 = 1;
    TRISCbits.TRISC6 = 1;
    ANSELCbits.ANSELC7 = 0;
    ANSELBbits.ANSELB7 = 0;
    ANSELCbits.ANSELC3 = 0;
    ANSELCbits.ANSELC6 = 0;

    /* TTL y pull-up: el encoder en colector abierto igual se ve. */
    INLVLCbits.INLVLC7 = 0;
    INLVLBbits.INLVLB7 = 0;
    INLVLCbits.INLVLC3 = 0;
    INLVLCbits.INLVLC6 = 0;
    WPUCbits.WPUC7 = 1;
    WPUBbits.WPUB7 = 1;
    WPUCbits.WPUC3 = 1;
    WPUCbits.WPUC6 = 1;

    /* CLC1 = A negada. AND de 4 compuertas: la 1 es A, las otras
       no tienen entrada (dan 0) y se invierten a 1. La salida se niega. */
    CLC1CON = 0x00;
    CLC1SEL0 = 0x00;              /* D1 = CLCIN0PPS = RC7 */
    CLC1SEL1 = 0x00;
    CLC1SEL2 = 0x00;
    CLC1SEL3 = 0x00;
    CLC1GLS0 = 0x02;              /* compuerta 1 = D1 sin negar */
    CLC1GLS1 = 0x00;
    CLC1GLS2 = 0x00;
    CLC1GLS3 = 0x00;
    CLC1POL = 0x8E;               /* salida negada, compuertas 2..4 en 1 */
    CLC1CON = 0x82;               /* encendida, AND de 4 */

    /* Reloj sincronizado con Fosc, lectura de 16 bits de una vez.
       Compuerta activa en bajo: solo cuenta con B = 0. */
    T1CON = 0x02;
    T1CLK = 0x00;                 /* T1CKIPPS = RC7 */
    T1GATE = 0x00;                /* T1GPPS = RB7 */
    T1GCON = 0x80;
    TMR1H = 0;
    TMR1L = 0;

    T5CON = 0x02;
    T5CLK = 0x0D;                 /* CLC1_out = A negada */
    T5GATE = 0x00;                /* T5GPPS = RB7 */
    T5GCON = 0x80;
    TMR5H = 0;
    TMR5L = 0;

    /* El timer pierde la primera subida si arranca con el reloj en bajo.
       Son 2 cuentas como mucho y solo al encender. */
    a_inicial = PORTCbits.RC7;
    T1CONbits.ON = 1;
    T5CONbits.ON = 1;

    cero_base = 0;

    /* Cada flanco de A del NEMA. B solo se lee, no interrumpe. */
    a_elev = PORTCbits.RC3;
    cuentas_elev = 0;
    cero_elev = 0;
    IOCCF = 0;
    IOCCP = 0;
    IOCCN = 0;
    IOCCPbits.IOCCP3 = 1;
    IOCCNbits.IOCCN3 = 1;
    IOCCFbits.IOCCF3 = 0;
    PIR0bits.IOCIF = 0;
}

/* Un flanco de A ya ocurrio. Si A quedo igual a B, la cuenta sube. */
void Encoder_ISR(void)
{
    uint8_t vueltas;
    uint8_t a;
    uint8_t b;
    int8_t delta;

    if (!IOCCFbits.IOCCF3) {
        return;
    }

    for (vueltas = 0; vueltas < 2U; vueltas++) {
        IOCCFbits.IOCCF3 = 0;
        a = PORTCbits.RC3;
        b = PORTCbits.RC6;
        if (a != a_elev) {
            a_elev = a;
            if (a == b) {
                delta = 1;
            } else {
                delta = -1;
            }
#if INVERTIR_ENCODER_ELEV
            delta = (int8_t)(-delta);
#endif
            cuentas_elev += delta;
        }
        if (!IOCCFbits.IOCCF3) {
            break;
        }
    }
}

/* Conteo x2 de la base desde el encendido. Si A cambia en medio de la lectura,
   se lee otra vez para que timers y pin sean del mismo instante. */
static int32_t cuentas_base(void)
{
    uint8_t a_antes;
    uint8_t a_despues;
    uint8_t bajo;
    uint16_t sube;
    uint16_t baja;
    int32_t cuentas;

    do {
        a_antes = PORTCbits.RC7;
        bajo = TMR1L;             /* con RD16, leer L congela H */
        sube = (uint16_t)(((uint16_t)TMR1H << 8) | bajo);
        bajo = TMR5L;
        baja = (uint16_t)(((uint16_t)TMR5H << 8) | bajo);
        a_despues = PORTCbits.RC7;
    } while (a_antes != a_despues);

    /* La resta en 16 bits aguanta que los timers den la vuelta. */
    cuentas = 2L * (int32_t)(int16_t)(uint16_t)(baja - sube);
    cuentas += (int32_t)a_despues - (int32_t)a_inicial;

#if INVERTIR_ENCODER_BASE
    cuentas = -cuentas;
#endif
    return cuentas;
}

static int32_t cuentas_elevacion(void)
{
    int32_t cuentas;
    uint8_t gie;

    gie = INTCONbits.GIE;
    INTCONbits.GIE = 0;
    cuentas = cuentas_elev;
    INTCONbits.GIE = gie;
    return cuentas;
}

/* bit0 = A, bit1 = B, como los ve el PIC ahora. */
uint8_t Encoder_Ab(uint8_t eje)
{
    uint8_t a;
    uint8_t b;

    if (eje == EJE_ELEV) {
        a = PORTCbits.RC3;
        b = PORTCbits.RC6;
    } else {
        a = PORTCbits.RC7;
        b = PORTBbits.RB7;
    }
    return (uint8_t)(a | (uint8_t)(b << 1));
}

int32_t Encoder_Cuentas(uint8_t eje)
{
    if (eje == EJE_ELEV) {
        return cuentas_elevacion();
    }
    return cuentas_base();
}

/* Guarda el conteo de este instante. Ahi queda 0 grados. */
void Encoder_FijarCero(uint8_t eje)
{
    if (eje == EJE_ELEV) {
        cero_elev = cuentas_elevacion();
    } else {
        cero_base = cuentas_base();
    }
}

int32_t Encoder_Posicion(uint8_t eje)
{
    if (eje == EJE_ELEV) {
        return cuentas_elevacion() - cero_elev;
    }
    return cuentas_base() - cero_base;
}
