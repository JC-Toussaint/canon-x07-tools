/* Réels en double précision du X-07 (14 chiffres, calcul décimal), en C.
   python3 x07asm.py run exemples/c/reels.c --fenetre
   1. racine de 2 par la méthode de Newton, comparée à r_sqrt ;
   2. e par la série 1 + 1/1! + 1/2! + ... ;
   3. table de sinus, mise en forme comme PRINT USING.
   Une touche entre les écrans. */
#include <stdio.h>
#include "x07.h"

static void attendre(void)
{
    getkey();
    cls();
}

int main(void)
{
    real x, deux, un_demi, t, e, terme, k, quart, deg;
    char buf[26];
    unsigned char i;

    cls();
    r_int(&deux, 2);
    r_set(&un_demi, "0.5");
    r_int(&x, 1);
    for (i = 1; i <= 5; i++) {            /* x <- (x + 2/x) / 2 */
        r_div(&t, &deux, &x);
        r_add(&t, &t, &x);
        r_mul(&x, &t, &un_demi);
    }
    printf("Newton%s\n", r_str(buf, &x));
    r_sqrt(&t, &deux);
    printf("sqrt  %s\n", r_str(buf, &t));
    printf("egaux : %s\n", r_cmp(&x, &t) == 0 ? "oui" : "non");
    attendre();

    r_int(&e, 1);
    r_int(&terme, 1);
    for (i = 1; i <= 17; i++) {           /* terme <- terme / i */
        r_int(&k, i);
        r_div(&terme, &terme, &k);
        r_add(&e, &e, &terme);
    }
    printf("e =%s\n", r_str(buf, &e));
    r_int(&t, 1);
    r_exp(&t, &t);
    printf("exp(1)=%s\n", r_str(buf, &t));
    attendre();

    r_int(&t, 1);
    r_atn(&quart, &t);                    /* pi/4 */
    r_int(&t, 45);
    r_div(&deg, &quart, &t);              /* un degré : pi/180 = (pi/4)/45 */
    for (i = 0; i <= 90; i += 30) {
        r_int(&t, i);
        r_mul(&t, &t, &deg);
        r_sin(&t, &t);
        printf("sin %2u =%s\n", i, r_fmt(buf, &t, 2, 6));
    }
    attendre();
    return 0;
}
