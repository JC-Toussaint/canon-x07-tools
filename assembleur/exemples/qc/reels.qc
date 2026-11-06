/* Réels en double précision du X-07, en Quick C : comparer à exemples/c/reels.c.
   python3 x07asm.py run exemples/qc/reels.qc --fenetre
   1. racine de 2 par la méthode de Newton, comparée à sqrt ;
   2. e par la série 1 + 1/1! + 1/2! + ... ;
   3. table de sinus, mise en forme comme PRINT USING.
   Une touche entre les écrans. */
#include <stdio.h>

static void attendre(void)
{
    getkey();
    cls();
}

int main(void)
{
    real x, e, terme, degre;
    int i;

    cls();
    x = 1;
    for (i = 1; i <= 5; i++)
        x = (x + 2 / x) / 2;
    printf("Newton%s\n", str(x));
    printf("sqrt  %s\n", str(sqrt(2)));
    printf("egaux : %s\n", x == sqrt(2) ? "oui" : "non");
    attendre();

    e = 1;
    terme = 1;
    for (i = 1; i <= 17; i++) {
        terme = terme / i;
        e = e + terme;
    }
    printf("e =%s\n", str(e));
    printf("exp(1)=%s\n", str(exp(1)));
    attendre();

    degre = atan(1) / 45;                 /* pi/180 */
    for (i = 0; i <= 90; i += 30)
        printf("sin %2d =%s\n", i, fmt(sin(i * degre), 2, 6));
    attendre();
    return 0;
}
