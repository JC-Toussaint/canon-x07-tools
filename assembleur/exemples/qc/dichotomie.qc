/* Résoudre cos(x) = x par dichotomie, en Quick C : un exemple à suivre au
   débogueur (voir DEBOGUEUR.md, « Exemple : déboguer dichotomie.qc »).
   python3 x07asm.py run exemples/qc/dichotomie.qc --fenetre
   python3 x07asm.py debug exemples/qc/dichotomie.qc       (ou ide)
   On cherche x entre a = 0 et b = 1 tel que f(x) = cos(x) - x = 0 : f(a) et
   f(b) sont de signes contraires, et l'on garde la moitié de l'intervalle où
   le signe change, jusqu'à une largeur de 1E-10. */
#include <stdio.h>

#define PRECISION 1E-10

static int tours;                       /* nombre de moitiés prises */

static real f(real x)
{
    return cos(x) - x;
}

static real dichotomie(real a, real b)
{
    real milieu, fa;
    fa = f(a);
    while (b - a > PRECISION) {
        milieu = (a + b) / 2;
        if (fa * f(milieu) <= 0)        /* le signe change entre a et milieu */
            b = milieu;
        else {
            a = milieu;
            fa = f(a);
        }
        tours++;
    }
    return (a + b) / 2;
}

int main(void)
{
    real x;
    cls();
    printf("cos(x) = x\n");
    x = dichotomie(0, 1);
    printf("x =%s\n", str(x));
    printf("f(x) =%s\n", str(f(x)));
    printf("%d tours", tours);
    getkey();
    return 0;
}
