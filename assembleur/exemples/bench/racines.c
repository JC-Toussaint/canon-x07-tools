/* Somme des racines carrées de 1 à 30, en réels de la ROM (112.08284521569).
   Comparaison C / Turbo Pascal : voir racines.pas et mesure.py. */
#include <stdio.h>
#include "x07.h"
int main(void)
{
    real s, x;
    int i;
    char buf[26];
    r_int(&s, 0);
    for (i = 1; i <= 30; i++) { r_int(&x, i); r_sqrt(&x, &x); r_add(&s, &s, &x); }
    printf("%s\n", r_str(buf, &s));
    return 0;
}
