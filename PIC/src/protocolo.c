#include "protocolo.h"
#include "configuracion.h"
#include "uart.h"
#include "referencia.h"
#include "control_pid.h"
#include "encoder.h"
#include "paso_drv8825.h"

static char linea[LARGO_LINEA];
static uint8_t largo;

/* Mayuscula, para no depender de como llegue el comando. */
static char mayus(char c)
{
    if ((c >= 'a') && (c <= 'z')) {
        return (char)(c - ('a' - 'A'));
    }
    return c;
}

static void responder(const char *texto)
{
    Uart_EnviarTexto(texto);
}

/* Lee un numero con hasta 3 decimales y lo deja en milesimas. */
static uint8_t leer_milesimas(const char *s, int32_t *milesimas)
{
    uint32_t entero;
    uint32_t frac;
    uint8_t digitos;
    uint8_t alguno;
    uint8_t negativo;

    entero = 0;
    frac = 0;
    digitos = 0;
    alguno = 0;
    negativo = 0;

    while (*s == ' ') {
        s++;
    }
    if (*s == '+') {
        s++;
    } else if (*s == '-') {
        negativo = 1;
        s++;
    }

    while ((*s >= '0') && (*s <= '9')) {
        alguno = 1;
        entero = (entero * 10UL) + (uint32_t)(*s - '0');
        if (entero > 360UL) {
            return 0;
        }
        s++;
    }

    if (*s == '.') {
        s++;
        while ((*s >= '0') && (*s <= '9') && (digitos < 3U)) {
            alguno = 1;
            frac = (frac * 10UL) + (uint32_t)(*s - '0');
            digitos++;
            s++;
        }
        while (digitos < 3U) {
            frac = frac * 10UL;
            digitos++;
        }
        /* Si mandan mas de 3 decimales, se ignoran. */
        while ((*s >= '0') && (*s <= '9')) {
            s++;
        }
    }

    while (*s == ' ') {
        s++;
    }
    if (!alguno || (*s != '\0')) {
        return 0;
    }

    *milesimas = (int32_t)((entero * 1000UL) + frac);
    if (negativo) {
        *milesimas = -(*milesimas);
    }
    return 1;
}

/* BP10.5 -> 105 decimas. Se redondea si vienen mas decimales. */
static void comando_p(uint8_t eje, const char *s)
{
    int32_t milesimas;
    int16_t decimas;

    if (!leer_milesimas(s, &milesimas)) {
        responder("ERR VALOR\r\n");
        return;
    }

    if (milesimas >= 0) {
        decimas = (int16_t)((milesimas + 50L) / 100L);
    } else {
        decimas = (int16_t)(-(((-milesimas) + 50L) / 100L));
    }

    if (!Referencia_FijarDecimas(eje, decimas)) {
        responder("ERR RANGO\r\n");
        return;
    }
    responder("OK\r\n");
}

/* Kp:1.5 guarda 1500. Kd no pasa de 2. */
static void comando_ganancia(uint8_t eje, char cual, const char *s)
{
    int32_t milesimas;
    int16_t milli;
    uint8_t bien;

    if (!leer_milesimas(s, &milesimas) || (milesimas < 0)) {
        responder("ERR VALOR\r\n");
        return;
    }
    if (milesimas > 20000L) {
        responder("ERR RANGO\r\n");
        return;
    }

    milli = (int16_t)milesimas;
    if (cual == 'P') {
        bien = Control_FijarKp(eje, milli);
    } else if (cual == 'I') {
        bien = Control_FijarKi(eje, milli);
    } else {
        bien = Control_FijarKd(eje, milli);
    }

    if (!bien) {
        responder("ERR RANGO\r\n");
        return;
    }
    responder("OK\r\n");
}

/* BV:20 velocidad maxima en grados/s. BA:40 aceleracion en grados/s^2. */
static void comando_rampa(uint8_t eje, char cual, const char *s)
{
    int32_t milesimas;
    uint8_t bien;

    if (!leer_milesimas(s, &milesimas)) {
        responder("ERR VALOR\r\n");
        return;
    }
    if (cual == 'V') {
        bien = Referencia_FijarVelMax(eje, milesimas);
    } else {
        bien = Referencia_FijarAcelMax(eje, milesimas);
    }
    if (!bien) {
        responder("ERR RANGO\r\n");
        return;
    }
    responder("OK\r\n");
}

/* Solo base. BU12 gira a 12 V (negativo al otro lado). BV0:1.5 y BKv:0.004. */
static void comando_abierto(char cual, const char *s)
{
    int32_t milesimas;
    uint8_t bien;

    if (!leer_milesimas(s, &milesimas)) {
        responder("ERR VALOR\r\n");
        return;
    }
    if (cual == 'U') {
        bien = Referencia_TensionDirecta(milesimas);
    } else if (cual == '0') {
        bien = Referencia_FijarV0(milesimas);
    } else {
        bien = Referencia_FijarKv(milesimas);
    }
    if (!bien) {
        responder("ERR RANGO\r\n");
        return;
    }
    responder("OK\r\n");
}

/* BENC: y el conteo crudo, sin restar el cero. */
static void responder_conteo(uint8_t eje, int32_t valor)
{
    char buf[24];
    char digitos[11];
    uint8_t n;
    uint8_t k;
    uint32_t mag;

    n = 0;
    buf[n++] = (eje == EJE_ELEV) ? 'E' : 'B';
    buf[n++] = 'E';
    buf[n++] = 'N';
    buf[n++] = 'C';
    buf[n++] = ':';

    if (valor < 0) {
        buf[n++] = '-';
        mag = (uint32_t)(-valor);
    } else {
        mag = (uint32_t)valor;
    }

    k = 0;
    do {
        digitos[k++] = (char)('0' + (mag % 10UL));
        mag = mag / 10UL;
    } while ((mag > 0UL) && (k < 11U));

    while (k > 0U) {
        k--;
        buf[n++] = digitos[k];
    }

    buf[n++] = '\r';
    buf[n++] = '\n';
    buf[n] = '\0';
    responder(buf);
}

/* A y B como los lee el PIC. Sirve para ver si el pin si cambia. */
static void responder_ab(uint8_t eje, uint8_t nivel)
{
    char buf[10];

    buf[0] = (eje == EJE_ELEV) ? 'E' : 'B';
    buf[1] = 'A';
    buf[2] = 'B';
    buf[3] = ':';
    buf[4] = (char)('0' + (nivel & 1U));
    buf[5] = (char)('0' + ((nivel >> 1) & 1U));
    buf[6] = '\r';
    buf[7] = '\n';
    buf[8] = '\0';
    responder(buf);
}

/* El resto de la linea, ya sin la B o la E. */
static void ejecutar_eje(uint8_t eje, char *cmd)
{
    char c0;
    char c1;

    while (*cmd == ' ') {
        cmd++;
    }
    if (*cmd == '\0') {
        responder("ERR VALOR\r\n");
        return;
    }

    c0 = mayus(cmd[0]);
    c1 = mayus(cmd[1]);

    if (c0 == 'P') {
        comando_p(eje, &cmd[1]);
    } else if ((c0 == 'S') && (cmd[1] == '\0')) {
        Referencia_Parar(eje);
        responder("OK\r\n");
    } else if ((c0 == 'Z') && (cmd[1] == '\0')) {
        Referencia_IrAlCero(eje);
        responder("OK\r\n");
    } else if ((c0 == '0') && (cmd[1] == '\0')) {
        Referencia_FijarCeroAqui(eje);
        responder("OK\r\n");
    } else if ((c0 == 'C') && (cmd[1] == '\0')) {
        responder_conteo(eje, Encoder_Cuentas(eje));
        responder_ab(eje, Encoder_Ab(eje));
    } else if ((eje == EJE_ELEV) && (c0 == 'F') && (cmd[1] == '\0')) {
        Referencia_Parar(eje);
        Paso_Soltar();
        responder("OK\r\n");
    } else if ((eje == EJE_BASE) && (c0 == 'U')) {
        comando_abierto('U', &cmd[1]);
    } else if ((eje == EJE_BASE) && (c0 == 'V') && (cmd[1] == '0') && (cmd[2] == ':')) {
        comando_abierto('0', &cmd[3]);
    } else if ((eje == EJE_BASE) && (c0 == 'K') && (c1 == 'V') && (cmd[2] == ':')) {
        comando_abierto('K', &cmd[3]);
    } else if (((c0 == 'V') || (c0 == 'A')) && (cmd[1] == ':')) {
        comando_rampa(eje, c0, &cmd[2]);
    } else if ((c0 == 'K') && (cmd[1] != '\0') && (cmd[2] == ':') &&
               ((c1 == 'P') || (c1 == 'I') || (c1 == 'D'))) {
        comando_ganancia(eje, c1, &cmd[3]);
    } else {
        responder("ERR VALOR\r\n");
    }
}

/* Una linea ya cerrada con enter. */
static void ejecutar(void)
{
    char c0;

    if (largo == 0U) {
        return;
    }
    linea[largo] = '\0';
    largo = 0;

    c0 = mayus(linea[0]);
    if ((c0 == 'S') && (linea[1] == '\0')) {
        Referencia_Parar(EJE_BASE);
        Referencia_Parar(EJE_ELEV);
        responder("OK\r\n");
        return;
    }
    if (c0 == 'B') {
        ejecutar_eje(EJE_BASE, &linea[1]);
    } else if (c0 == 'E') {
        ejecutar_eje(EJE_ELEV, &linea[1]);
    } else {
        responder("ERR VALOR\r\n");
    }
}

/* Nada que armar todavia. */
void Protocolo_Iniciar(void)
{
    largo = 0;
}

/* Saca bytes hasta armar una linea. \r se bota. */
void Protocolo_Procesar(void)
{
    uint8_t dato;

    while (Uart_LeerByte(&dato)) {
        if (dato == '\n') {
            ejecutar();
        } else if (dato == '\r') {
            ;
        } else if (largo < (LARGO_LINEA - 1U)) {
            linea[largo++] = (char)dato;
        } else {
            largo = 0;
            responder("ERR VALOR\r\n");
        }
    }
}
