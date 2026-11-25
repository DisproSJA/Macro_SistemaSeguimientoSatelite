#include "pines.h"

/* HFINTOSC a 32 MHz. RSTOSC ya lo pide; se vuelve a escribir. */
static void iniciar_oscilador(void)
{
    OSCFRQbits.HFFRQ = 0b110;
    OSCCON1 = 0x60;

    while (!OSCSTATbits.HFOR) {
        ;
    }
    while (OSCCON2bits.COSC != 0b110) {
        ;
    }
}

/* Latch primero. Si TRIS va antes, el pin sale un momento al aire. */
static void iniciar_gpio(void)
{
    /* RA4 en alto: EN del DRV8825 es activo en bajo, el NEMA arranca suelto.
       XD en RC0 y RA5, STEP y DIR en RC1 y RC2, todos en bajo. */
    LATA = 0x10;
    LATB = 0;
    LATC = 0;

    /* RA0/RA1 ICSP, RA2 ADC sin usar, RA3 MCLR. RA4 enable, RA5 IN2 del XD. */
    TRISA = 0x0F;
    /* RB7 encoder B de la base. RB4..RB6 sensores, sin usar. */
    TRISB = 0xFF;
    /* Salidas: RC0 IN1 del XD, RC1 STEP, RC2 DIR, RC4 TX.
       Entradas: RC3 A y RC6 B del NEMA, RC5 RX, RC7 A de la base. */
    TRISC = 0xE8;

    ANSELA = 0x04;
    ANSELB = 0;
    ANSELC = 0;

    WPUB = 0x40;
}

/* Destraba PPSLOCK. La secuencia 0x55, 0xAA tiene que ir seguida. */
static void abrir_pps(void)
{
    asm("BANKSEL PPSLOCK");
    asm("MOVLW 0x55");
    asm("MOVWF PPSLOCK");
    asm("MOVLW 0xAA");
    asm("MOVWF PPSLOCK");
    asm("BCF PPSLOCK, 0");
}

/* Vuelve a trabar PPSLOCK. */
static void cerrar_pps(void)
{
    asm("BANKSEL PPSLOCK");
    asm("MOVLW 0x55");
    asm("MOVWF PPSLOCK");
    asm("MOVLW 0xAA");
    asm("MOVWF PPSLOCK");
    asm("BSF PPSLOCK, 0");
}

/* TX en RC4, PWM6 en RC0 (IN1), PWM7 en RA5 (IN2). RX entra por RC5.
   STEP y DIR se manejan por el latch, sin periferico.
   T1CKI y CLCIN0 solo aceptan puertos A y C; T1G y T5G, B y C. */
static void iniciar_pps(void)
{
    uint8_t gie;

    gie = INTCONbits.GIE;
    INTCONbits.GIE = 0;

    abrir_pps();

    RX1PPS = 0x15;

    /* Encoder de la base: A (RC7) a Timer1 y a la CLC1, B (RB7) a las compuertas. */
    T1CKIPPS = 0x17;
    CLCIN0PPS = 0x17;
    T1GPPS = 0x0F;
    T5GPPS = 0x0F;
    RC4PPS = 0x0F;
    RC0PPS = 0x0D;
    RA5PPS = 0x0E;
    RC1PPS = 0x00;
    RC2PPS = 0x00;

    cerrar_pps();
    INTCONbits.GIE = gie;
}

/* Oscilador, GPIO y PPS. */
void Pines_Iniciar(void)
{
    iniciar_oscilador();
    iniciar_gpio();
    iniciar_pps();
}
