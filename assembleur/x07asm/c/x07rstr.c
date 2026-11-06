/* Canon X-07 : texte d'un réel dans des tampons tournants, pour printf
   (str(x) et fmt(x, chiffres, décimales) de Quick C) : quatre textes au plus
   dans un même printf. */
#include "x07.h"

static char r_bufs[4][26];
static unsigned char r_next;

char *r_s(const real *a)
{
    r_next = (r_next + 1) & 3;
    return r_str(r_bufs[r_next], a);
}

char *r_f(const real *a, unsigned char digits, unsigned char decimals)
{
    r_next = (r_next + 1) & 3;
    return r_fmt(r_bufs[r_next], a, digits, decimals);
}
