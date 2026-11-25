#include "control_pid.h"
#include "configuracion.h"

/* N = 1/6.8983e-5 y Ts = 1/150. El polo queda en 1/(1+N*Ts) ≈ 8/781.
   14496 es N en rad/s, para armar el termino Kd*N*dq. */
#define DEN_NUM                         8L
#define DEN_DEN                         781L
#define N_RAD_S                         14496L
#define DOS_SOBRE_TS                    (2L * (int32_t)FS_HZ)
#define TOPE_SUMA                       200000000L

static int16_t kp_milli[EJE_CANT];
static int16_t ki_milli[EJE_CANT];
static int16_t kd_milli[EJE_CANT];
static int32_t i_mv[EJE_CANT];
static int32_t d_mv[EJE_CANT];
static int32_t e_prev[EJE_CANT];
static int32_t y_prev[EJE_CANT];
static uint8_t primera[EJE_CANT];

/* ganancia * magnitud * 360 / cuentas_por_vuelta, sin salirse del entero. */
static int32_t escalar(int32_t ganancia, int32_t magnitud)
{
    long long v;

    v = (long long)ganancia * (long long)magnitud * (long long)ESCALA_NUM;
    v /= (long long)ESCALA_DEN;
    if (v > 2000000000LL) {
        return 2000000000L;
    }
    if (v < -2000000000LL) {
        return -2000000000L;
    }
    return (int32_t)v;
}

/* Deja los dos estados en cero y carga las ganancias del Micro 3. */
void Control_Iniciar(void)
{
    uint8_t eje;

    for (eje = 0; eje < EJE_CANT; eje++) {
        kp_milli[eje] = KP_MILLI_INICIAL;
        ki_milli[eje] = KI_MILLI_INICIAL;
        kd_milli[eje] = KD_MILLI_INICIAL;
        Control_Reiniciar(eje);
    }
}

/* Borra I, D y el sample anterior. Se llama al frenar y al marcar el cero. */
void Control_Reiniciar(uint8_t eje)
{
    i_mv[eje] = 0;
    d_mv[eje] = 0;
    e_prev[eje] = 0;
    y_prev[eje] = 0;
    primera[eje] = 1;
}

/* 0 si se sale de 0 a 20. */
uint8_t Control_FijarKp(uint8_t eje, int16_t valor)
{
    if ((eje >= EJE_CANT) || (valor < 0) || (valor > 20000)) {
        return 0;
    }
    kp_milli[eje] = valor;
    return 1;
}

/* 0 si se sale de 0 a 20. Al pasar a cero se tira el integrador. */
uint8_t Control_FijarKi(uint8_t eje, int16_t valor)
{
    if ((eje >= EJE_CANT) || (valor < 0) || (valor > 20000)) {
        return 0;
    }
    ki_milli[eje] = valor;
    if (valor == 0) {
        i_mv[eje] = 0;
    }
    return 1;
}

/* 0 si se sale de 0 a 2. Mas alto y el entero del filtro no da. */
uint8_t Control_FijarKd(uint8_t eje, int16_t valor)
{
    if ((eje >= EJE_CANT) || (valor < 0) || (valor > 2000)) {
        return 0;
    }
    kd_milli[eje] = valor;
    return 1;
}

/* Una muestra. Devuelve el mando ya recortado a ±tope. */
int16_t Control_Calcular(uint8_t eje, int32_t consigna, int32_t posicion,
                         int16_t tope)
{
    int32_t error;
    int32_t p_mv;
    int32_t dq;
    int32_t deriv;
    int32_t suma;
    int32_t u;
    int32_t i_antes;
    uint8_t congelar;
    int32_t tope_error;

    error = consigna - posicion;
    tope_error = 2L * CUENTAS_POR_VUELTA;
    if (error > tope_error) {
        error = tope_error;
    } else if (error < -tope_error) {
        error = -tope_error;
    }
    p_mv = escalar((int32_t)kp_milli[eje], error);

    /* Si se acaba de bajar el tope, el integrador no se queda por encima. */
    if (i_mv[eje] > tope) {
        i_mv[eje] = tope;
    } else if (i_mv[eje] < -tope) {
        i_mv[eje] = -tope;
    }

    i_antes = i_mv[eje];
    if (ki_milli[eje] == 0) {
        i_mv[eje] = 0;
    } else {
        i_mv[eje] += escalar((int32_t)ki_milli[eje], error + e_prev[eje]) / DOS_SOBRE_TS;
        if (i_mv[eje] > tope) {
            i_mv[eje] = tope;
        } else if (i_mv[eje] < -tope) {
            i_mv[eje] = -tope;
        }
    }

    if (primera[eje]) {
        dq = 0;
        primera[eje] = 0;
    } else {
        /* q = -y, asi que el incremento es la posicion al reves. */
        dq = y_prev[eje] - posicion;
        if (dq > 600) {
            dq = 600;
        } else if (dq < -600) {
            dq = -600;
        }
    }

    deriv = escalar((int32_t)kd_milli[eje] * N_RAD_S, dq);
    if (deriv > TOPE_SUMA) {
        deriv = TOPE_SUMA;
    } else if (deriv < -TOPE_SUMA) {
        deriv = -TOPE_SUMA;
    }
    suma = d_mv[eje] + deriv;
    if (suma > TOPE_SUMA) {
        suma = TOPE_SUMA;
    } else if (suma < -TOPE_SUMA) {
        suma = -TOPE_SUMA;
    }
    d_mv[eje] = (suma * DEN_NUM) / DEN_DEN;

    u = p_mv + i_mv[eje] + d_mv[eje];
    congelar = 0;
    if (u > tope) {
        u = tope;
        if (error > 0) {
            congelar = 1;
        }
    } else if (u < -tope) {
        u = -tope;
        if (error < 0) {
            congelar = 1;
        }
    }

    /* Si el integrador empujaba mas contra el tope, se devuelve. */
    if (congelar) {
        i_mv[eje] = i_antes;
        u = p_mv + i_mv[eje] + d_mv[eje];
        if (u > tope) {
            u = tope;
        } else if (u < -tope) {
            u = -tope;
        }
    }

    e_prev[eje] = error;
    y_prev[eje] = posicion;
    return (int16_t)u;
}
