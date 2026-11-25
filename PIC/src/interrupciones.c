#include <xc.h>
#include "interrupciones.h"
#include "temporizador.h"
#include "uart.h"
#include "encoder.h"
#include "paso_drv8825.h"

/* Una sola entrada. El encoder de la base no interrumpe: lo cuentan los timers. */
void __interrupt() ISR(void)
{
    if (PIE0bits.IOCIE && PIR0bits.IOCIF) {
        Encoder_ISR();
        if (!IOCCFbits.IOCCF3) {
            PIR0bits.IOCIF = 0;
        }
    }
    if (PIE4bits.TMR4IE && PIR4bits.TMR4IF) {
        Paso_ISR();
        PIR4bits.TMR4IF = 0;
    }
    if (PIE0bits.TMR0IE && PIR0bits.TMR0IF) {
        Temporizador_ISR();
    }
    if (PIE3bits.RC1IE && PIR3bits.RC1IF) {
        Uart_ISR_Recepcion();
    }
    if (PIE3bits.TX1IE && PIR3bits.TX1IF) {
        Uart_ISR_Transmision();
    }
}

/* Prende el flanco del NEMA, el generador de pasos, la muestra y RX.
   TX se prende solo al enviar. */
void Interrupciones_Habilitar(void)
{
    IOCCFbits.IOCCF3 = 0;
    PIR0bits.IOCIF = 0;
    PIR0bits.TMR0IF = 0;
    PIR3bits.RC1IF = 0;
    PIR3bits.TX1IF = 0;
    PIR4bits.TMR4IF = 0;

    PIE0bits.IOCIE = 1;
    PIE0bits.TMR0IE = 1;
    PIE3bits.RC1IE = 1;
    PIE3bits.TX1IE = 0;
    PIE4bits.TMR4IE = 1;

    INTCONbits.PEIE = 1;
    INTCONbits.GIE = 1;
}
