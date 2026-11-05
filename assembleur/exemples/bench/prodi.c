/* Double boucle 100 x 100 avec multiplication entière (27292).
   Comparaison C / Turbo Pascal : voir prodi.pas et mesure.py. */
#include <stdio.h>
#include "x07.h"
int main(void)
{
    int i, j, s = 0;
    for (i = 0; i < 100; i++)
        for (j = 0; j < 100; j++)
            s += (i * j) & 7;
    printf("%d\n", s);
    return 0;
}
