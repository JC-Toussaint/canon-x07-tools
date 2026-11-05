/* Crible d'Ératosthène jusqu'à 2000 : tableau, boucles (303 nombres premiers).
   Comparaison C / Turbo Pascal : voir crible.pas et mesure.py. */
#include <stdio.h>
#include "x07.h"
#define N 2000
static char premier[N + 1];
int main(void)
{
    int i, j, n = 0;
    for (i = 2; i <= N; i++) premier[i] = 1;
    for (i = 2; i * i <= N; i++)
        if (premier[i])
            for (j = i * i; j <= N; j += i) premier[j] = 0;
    for (i = 2; i <= N; i++) if (premier[i]) n++;
    printf("%d\n", n);
    return 0;
}
