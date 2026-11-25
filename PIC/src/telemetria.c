#include "telemetria.h"
#include "configuracion.h"
#include "uart.h"

static uint8_t poner_char(char *buf, uint8_t n, char c)
{
    if (n < 79U) {
        buf[n] = c;
    }
    return (uint8_t)(n + 1U);
}

/* Grados con un decimal, a partir de las cuentas del encoder. */
static uint8_t poner_grados(char *buf, uint8_t n, int32_t cuentas)
{
    int32_t decimas;
    int32_t mag;
    uint16_t entero;
    uint8_t frac;

    if (cuentas >= 0) {
        decimas = (cuentas * DECIMAS_POR_VUELTA + (CUENTAS_POR_VUELTA / 2L)) /
                  CUENTAS_POR_VUELTA;
    } else {
        mag = -cuentas;
        decimas = -((mag * DECIMAS_POR_VUELTA + (CUENTAS_POR_VUELTA / 2L)) /
                    CUENTAS_POR_VUELTA);
    }

    if (decimas < 0) {
        n = poner_char(buf, n, '-');
        decimas = -decimas;
    }
    if (decimas > 99999L) {
        decimas = 99999L;
    }
    entero = (uint16_t)(decimas / 10L);
    frac = (uint8_t)(decimas % 10L);
    if (entero >= 10000U) {
        n = poner_char(buf, n, (char)('0' + (entero / 10000U)));
        entero = (uint16_t)(entero % 10000U);
    }
    if (entero >= 1000U) {
        n = poner_char(buf, n, (char)('0' + (entero / 1000U)));
        entero = (uint16_t)(entero % 1000U);
    }
    if (entero >= 100U) {
        n = poner_char(buf, n, (char)('0' + (entero / 100U)));
        entero = (uint16_t)(entero % 100U);
    }
    if (entero >= 10U) {
        n = poner_char(buf, n, (char)('0' + (entero / 10U)));
        entero = (uint16_t)(entero % 10U);
    }
    n = poner_char(buf, n, (char)('0' + entero));
    n = poner_char(buf, n, '.');
    n = poner_char(buf, n, (char)('0' + frac));
    return n;
}

/* Mando con dos decimales. 12.00 en la base son 12 V. */
static uint8_t poner_mando(char *buf, uint8_t n, int16_t milivoltios)
{
    int16_t centi;
    uint16_t entero;
    uint8_t frac;

    centi = (int16_t)(milivoltios / 10);
    if (centi < 0) {
        n = poner_char(buf, n, '-');
        centi = (int16_t)(-centi);
    }
    entero = (uint16_t)(centi / 100);
    frac = (uint8_t)(centi % 100);
    if (entero >= 10U) {
        n = poner_char(buf, n, (char)('0' + (entero / 10U)));
        entero = (uint16_t)(entero % 10U);
    }
    n = poner_char(buf, n, (char)('0' + entero));
    n = poner_char(buf, n, '.');
    n = poner_char(buf, n, (char)('0' + (frac / 10U)));
    n = poner_char(buf, n, (char)('0' + (frac % 10U)));
    return n;
}

static uint8_t poner_eje(char *buf, uint8_t n, char nombre,
                         int32_t consigna, int32_t posicion, int16_t mando)
{
    n = poner_char(buf, n, nombre);
    n = poner_char(buf, n, ',');
    n = poner_grados(buf, n, consigna);
    n = poner_char(buf, n, ',');
    n = poner_grados(buf, n, posicion);
    n = poner_char(buf, n, ',');
    n = poner_grados(buf, n, consigna - posicion);
    n = poner_char(buf, n, ',');
    n = poner_mando(buf, n, mando);
    return n;
}

/* Si no cabe en la UART, se salta esta muestra. */
void Telemetria_Enviar(int32_t cons_b, int32_t pos_b, int16_t mando_b,
                       int32_t cons_e, int32_t pos_e, int16_t mando_e)
{
    static char buf[80];
    uint8_t n;
    uint8_t i;

    n = 0;
    n = poner_eje(buf, n, 'B', cons_b, pos_b, mando_b);
    n = poner_char(buf, n, ',');
    n = poner_eje(buf, n, 'E', cons_e, pos_e, mando_e);
    n = poner_char(buf, n, '\r');
    n = poner_char(buf, n, '\n');
    if (n > 79U) {
        return;
    }
    buf[n] = '\0';

    if (Uart_Espacio() < n) {
        return;
    }
    for (i = 0; i < n; i++) {
        Uart_EscribirByte((uint8_t)buf[i]);
    }
}
