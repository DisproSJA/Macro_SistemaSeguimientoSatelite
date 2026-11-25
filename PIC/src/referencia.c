#include "referencia.h"
#include "configuracion.h"
#include "encoder.h"
#include "control_pid.h"

#define MODO_PARADO                     0U
#define MODO_PID                        1U
#define MODO_DIRECTO                    2U

/* La rampa lleva cuentas * 65536 para que una aceleracion chica no se pierda. */
#define UNO_Q                           65536L

static uint8_t modo[EJE_CANT];
static int32_t consigna[EJE_CANT];
static int32_t lim_min[EJE_CANT];
static int32_t lim_max[EJE_CANT];

static int32_t perfil[EJE_CANT];        /* punto que sigue el PID */
static int32_t vel[EJE_CANT];           /* por muestra */
static int32_t vel_max[EJE_CANT];
static int32_t acel_max[EJE_CANT];

static int32_t base_v0_mv;
static int32_t base_kv;                 /* mV por grado/s */
static int16_t base_directa_mv;

/* Decimas de grado a cuentas del encoder, redondeando. */
static int32_t a_cuentas(int16_t decimas)
{
    int32_t mag;
    int32_t cuentas;

    if (decimas >= 0) {
        mag = decimas;
    } else {
        mag = -(int32_t)decimas;
    }
    cuentas = (mag * CUENTAS_POR_VUELTA + (DECIMAS_POR_VUELTA / 2L)) / DECIMAS_POR_VUELTA;
    if (decimas < 0) {
        cuentas = -cuentas;
    }
    return cuentas;
}

/* Milesimas de grado/s a cuentas*65536 por muestra. */
static int32_t vel_a_q(int32_t milesimas)
{
    long long v;

    v = (long long)milesimas * (long long)CUENTAS_POR_VUELTA * (long long)UNO_Q;
    v /= 360000LL * (long long)FS_HZ;
    return (int32_t)v;
}

/* Milesimas de grado/s^2 a cuentas*65536 por muestra al cuadrado. Nunca 0. */
static int32_t acel_a_q(int32_t milesimas)
{
    long long a;

    a = (long long)milesimas * (long long)CUENTAS_POR_VUELTA * (long long)UNO_Q;
    a /= 360000LL * (long long)FS_HZ * (long long)FS_HZ;
    if (a < 1LL) {
        a = 1LL;
    }
    return (int32_t)a;
}

static int32_t q_a_cuentas(int32_t q)
{
    if (q >= 0) {
        return (q + (UNO_Q / 2L)) / UNO_Q;
    }
    return -(((-q) + (UNO_Q / 2L)) / UNO_Q);
}

/* La rampa arranca quieta en donde esta el eje, no donde quedo la consigna.
   La base no tiene encoder: arranca donde la dejo la rampa. */
static void perfil_desde_aqui(uint8_t eje)
{
    if (eje != EJE_BASE) {
        perfil[eje] = Encoder_Posicion(eje) * UNO_Q;
    }
    vel[eje] = 0;
}

/* Una muestra de rampa trapezoidal: acelera, va a vel_max y frena a tiempo. */
static void avanzar_perfil(uint8_t eje)
{
    int32_t meta;
    int32_t falta;
    int32_t dist;
    int32_t v;
    int32_t a;
    int8_t dir;

    meta = consigna[eje] * UNO_Q;
    if (vel_max[eje] == 0) {
        perfil[eje] = meta;
        vel[eje] = 0;
        return;
    }

    a = acel_max[eje];
    falta = meta - perfil[eje];

    if (falta == 0) {
        /* Llego con velocidad: frena sobre la meta y vuelve. */
        v = vel[eje];
        if ((v <= 2L * a) && (v >= -2L * a)) {
            vel[eje] = 0;
            return;
        }
        vel[eje] = (v > 0) ? (v - a) : (v + a);
        perfil[eje] += vel[eje];
        return;
    }

    if (falta > 0) {
        dir = 1;
        dist = falta;
        v = vel[eje];
    } else {
        dir = -1;
        dist = -falta;
        v = -vel[eje];
    }

    /* v es ahora la velocidad hacia la meta. */
    if (v < 0) {
        v += a;
    } else if ((long long)v * (long long)v >= 2LL * (long long)a * (long long)dist) {
        v -= a;
        if (v < 0) {
            v = 0;
        }
    } else {
        v += a;
    }
    if (v > vel_max[eje]) {
        v = vel_max[eje];
    }

    /* El ultimo tramo, ya despacio, cae justo en la meta. */
    if ((v >= dist) && (v <= 4L * a)) {
        perfil[eje] = meta;
        vel[eje] = 0;
        return;
    }

    vel[eje] = (dir > 0) ? v : -v;
    perfil[eje] += vel[eje];
}

/* El punto donde esta cada eje al encender queda en 0 grados. */
void Referencia_Iniciar(void)
{
    uint8_t eje;

    Encoder_FijarCero(EJE_BASE);
    Encoder_FijarCero(EJE_ELEV);

    for (eje = 0; eje < EJE_CANT; eje++) {
        modo[eje] = MODO_PARADO;
        consigna[eje] = 0;
        perfil[eje] = 0;
        vel[eje] = 0;
        vel_max[eje] = vel_a_q(VEL_MAX_MILLI_INICIAL);
        acel_max[eje] = acel_a_q(ACEL_MAX_MILLI_INICIAL);
    }
    base_v0_mv = BASE_V0_MV_INICIAL;
    base_kv = BASE_KV_MILLI_INICIAL;
    base_directa_mv = 0;
    lim_min[EJE_BASE] = a_cuentas(BASE_DECIMAS_MIN);
    lim_max[EJE_BASE] = a_cuentas(BASE_DECIMAS_MAX);
    lim_min[EJE_ELEV] = a_cuentas(ELEV_DECIMAS_MIN);
    lim_max[EJE_ELEV] = a_cuentas(ELEV_DECIMAS_MAX);
}

/* Suelta el lazo y olvida I y D. El driver lo suelta el main. */
void Referencia_Parar(uint8_t eje)
{
    if (eje >= EJE_CANT) {
        return;
    }
    modo[eje] = MODO_PARADO;
    vel[eje] = 0;
    Control_Reiniciar(eje);
}

/* P en decimas de grado. 0 si se sale del recorrido de ese eje. */
uint8_t Referencia_FijarDecimas(uint8_t eje, int16_t decimas)
{
    int16_t minimo;
    int16_t maximo;

    if (eje == EJE_ELEV) {
        minimo = ELEV_DECIMAS_MIN;
        maximo = ELEV_DECIMAS_MAX;
    } else if (eje == EJE_BASE) {
        minimo = BASE_DECIMAS_MIN;
        maximo = BASE_DECIMAS_MAX;
    } else {
        return 0;
    }
    if ((decimas < minimo) || (decimas > maximo)) {
        return 0;
    }

    if (modo[eje] != MODO_PID) {
        perfil_desde_aqui(eje);
    }
    consigna[eje] = a_cuentas(decimas);
    modo[eje] = MODO_PID;
    return 1;
}

/* Z lleva el eje a 0 grados, el punto que se guardo al marcar el cero. */
void Referencia_IrAlCero(uint8_t eje)
{
    if (eje >= EJE_CANT) {
        return;
    }
    if (modo[eje] != MODO_PID) {
        perfil_desde_aqui(eje);
    }
    consigna[eje] = 0;
    modo[eje] = MODO_PID;
}

/* El angulo actual queda en 0 y la consigna tambien, para no salir disparado. */
void Referencia_FijarCeroAqui(uint8_t eje)
{
    if (eje >= EJE_CANT) {
        return;
    }
    Encoder_FijarCero(eje);
    consigna[eje] = 0;
    perfil[eje] = 0;
    vel[eje] = 0;
    Control_Reiniciar(eje);
}

uint8_t Referencia_FijarVelMax(uint8_t eje, int32_t milesimas)
{
    if ((eje >= EJE_CANT) || (milesimas < 0) || (milesimas > 360000L)) {
        return 0;
    }
    /* Sin rampa la base no sabria cuanto tiempo girar. */
    if ((eje == EJE_BASE) && (milesimas == 0)) {
        return 0;
    }
    vel_max[eje] = vel_a_q(milesimas);
    if ((milesimas > 0) && (vel_max[eje] == 0)) {
        vel_max[eje] = 1;
    }
    return 1;
}

uint8_t Referencia_FijarAcelMax(uint8_t eje, int32_t milesimas)
{
    if ((eje >= EJE_CANT) || (milesimas <= 0) || (milesimas > 360000L)) {
        return 0;
    }
    acel_max[eje] = acel_a_q(milesimas);
    return 1;
}

uint8_t Referencia_FijarV0(int32_t milivoltios)
{
    if ((milivoltios < 0) || (milivoltios > (int32_t)VM_MV)) {
        return 0;
    }
    base_v0_mv = milivoltios;
    return 1;
}

uint8_t Referencia_FijarKv(int32_t mv_por_grado_s)
{
    if ((mv_por_grado_s < 0) || (mv_por_grado_s > (int32_t)VM_MV)) {
        return 0;
    }
    base_kv = mv_por_grado_s;
    return 1;
}

/* La base gira a tension fija hasta un S o BS. La posicion estimada no cambia. */
uint8_t Referencia_TensionDirecta(int32_t milivoltios)
{
    if ((milivoltios > (int32_t)VM_MV) || (milivoltios < -(int32_t)VM_MV)) {
        return 0;
    }
    base_directa_mv = (int16_t)milivoltios;
    vel[EJE_BASE] = 0;
    consigna[EJE_BASE] = q_a_cuentas(perfil[EJE_BASE]);
    modo[EJE_BASE] = MODO_DIRECTO;
    return 1;
}

int16_t Referencia_Tension(void)
{
    return base_directa_mv;
}

/* V0 + Kv * |velocidad de la rampa|, con el signo del giro. Quieta: 0 V. */
int16_t Referencia_MandoAbierto(void)
{
    int32_t v;
    long long mv;

    v = vel[EJE_BASE];
    if (v == 0) {
        return 0;
    }
    if (v < 0) {
        v = -v;
    }
    /* cuentas*65536/muestra a grados/s, multiplicado por Kv en mV. */
    mv = (long long)v * (long long)FS_HZ * 360LL * (long long)base_kv;
    mv /= (long long)CUENTAS_POR_VUELTA * (long long)UNO_Q;
    mv += (long long)base_v0_mv;
    if (mv > (long long)VM_MV) {
        mv = (long long)VM_MV;
    }
    if (vel[EJE_BASE] < 0) {
        mv = -mv;
    }
    return (int16_t)mv;
}

int32_t Referencia_Estimada(uint8_t eje)
{
    if (eje >= EJE_CANT) {
        return 0;
    }
    return q_a_cuentas(perfil[eje]);
}

/* En el tope no se empuja mas hacia afuera. Hacia adentro si se puede. */
int16_t Referencia_AplicarFin(uint8_t eje, int32_t posicion, int16_t mando)
{
    if (eje >= EJE_CANT) {
        return 0;
    }
    if ((posicion >= lim_max[eje]) && (mando > 0)) {
        return 0;
    }
    if ((posicion <= lim_min[eje]) && (mando < 0)) {
        return 0;
    }
    return mando;
}

/* Cada Ts. Parado no calcula el PID ni mueve la rampa. */
uint8_t Referencia_Actualizar(uint8_t eje, int32_t *consigna_out)
{
    if (eje >= EJE_CANT) {
        *consigna_out = 0;
        return REF_COAST;
    }
    if (modo[eje] == MODO_DIRECTO) {
        *consigna_out = consigna[eje];
        return REF_DIRECTO;
    }
    if (modo[eje] != MODO_PID) {
        *consigna_out = consigna[eje];
        return REF_COAST;
    }
    avanzar_perfil(eje);
    *consigna_out = q_a_cuentas(perfil[eje]);
    return REF_PID;
}

/* Los dos ejes saturan en el mismo numero. */
int16_t Referencia_Tope(void)
{
    return VLIM_MV;
}
