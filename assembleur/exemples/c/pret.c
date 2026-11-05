/* Prêt à mensualités constantes, en réels décimaux du X-07 (14 chiffres).
   python3 x07asm.py run exemples/c/pret.c --fenetre
   On tape le capital, le taux annuel en %, la durée en années ; le programme
   donne la mensualité, le total payé et les intérêts, puis trace la courbe du
   capital restant dû, année par année.  Une touche entre les écrans.

   Mensualité : M = C r / (1 - (1 + r)^-n), r = taux / 1200, n = mois.
   Capital restant après un an : K' = K q - M (q - 1) / r, avec q = (1 + r)^12
   (une multiplication et une soustraction par année, au lieu de douze). */
#include <stdio.h>
#include "x07.h"

static real capital, taux, r, mens, q, annuite, k, t, u, un;
static char buf[26];

static void lire(const char *question, real *x)
{
    char s[16];
    printf("%s", question);
    input(s, sizeof s);
    r_set(x, s);
}

static void ligne(const char *texte, const real *x, unsigned char chiffres,
                  unsigned char decimales)
{
    printf("%s%s\n", texte, r_fmt(buf, x, chiffres, decimales));
}

int main(void)
{
    int annees, mois, an, x, y, x0, y0;
    real zero;

    r_int(&un, 1);
    r_int(&zero, 0);
    for (;;) {
        cls();
        lire("Capital ? ", &capital);
        lire("Taux % ? ", &taux);
        lire("Annees ? ", &t);
        annees = r_toint(&t);
        if (r_cmp(&capital, &zero) > 0 && annees >= 1 && annees <= 40 &&
            r_cmp(&taux, &zero) >= 0)
            break;
        printf("Valeurs incorrectes");
        getkey();
    }
    mois = annees * 12;

    /* mensualité */
    r_int(&t, 1200);
    r_div(&r, &taux, &t);                         /* taux mensuel */
    r_int(&t, mois);
    if (r_cmp(&r, &zero) == 0)
        r_div(&mens, &capital, &t);               /* sans intérêts */
    else {
        r_neg(&t, &t);
        r_add(&u, &un, &r);
        r_pow(&u, &u, &t);                        /* (1 + r)^-n */
        r_sub(&u, &un, &u);
        r_mul(&mens, &capital, &r);
        r_div(&mens, &mens, &u);
    }
    cls();
    ligne("Mensualite", &mens, 6, 2);
    r_int(&t, mois);
    r_mul(&t, &mens, &t);
    ligne("Total paye", &t, 9, 0);
    r_sub(&t, &t, &capital);
    ligne("Interets  ", &t, 9, 0);
    printf("Touche : courbe");
    getkey();

    /* capital restant dû, de 1 (en haut) à 0 (en bas), sur les lignes 9 à 31 */
    cls();
    printf("Restant du, %d ans", annees);
    r_int(&t, 12);
    r_add(&q, &un, &r);
    r_pow(&q, &q, &t);                            /* (1 + r)^12 */
    if (r_cmp(&r, &zero) == 0)
        r_mul(&annuite, &mens, &t);
    else {
        r_sub(&annuite, &q, &un);
        r_div(&annuite, &annuite, &r);
        r_mul(&annuite, &annuite, &mens);         /* M (q - 1) / r */
    }
    k = capital;
    r_int(&u, 22);
    x0 = 0;
    y0 = 9;
    line(0, 31, 119, 31);                         /* axe des années */
    for (an = 1; an <= annees; an++) {
        r_mul(&k, &k, &q);
        r_sub(&k, &k, &annuite);
        r_mul(&t, &k, &u);
        r_div(&t, &t, &capital);
        y = 31 - r_toint(&t);                     /* 22 points pour tout le capital */
        if (y > 31)
            y = 31;
        x = an * 119 / annees;
        line(x0, y0, x, y);
        pset(x, 30);                              /* graduation */
        x0 = x;
        y0 = y;
    }
    getkey();
    cls();
    return 0;
}
