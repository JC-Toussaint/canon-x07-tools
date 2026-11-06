/* Prêt à mensualités constantes, en Quick C : comparer à exemples/c/pret.c.
   python3 x07asm.py run exemples/qc/pret.qc --fenetre
   On tape le capital, le taux annuel en %, la durée en années ; le programme
   donne la mensualité, le total payé et les intérêts, puis trace la courbe du
   capital restant dû, année par année.  Une touche entre les écrans.

   Mensualité : M = C r / (1 - (1 + r)^-n), r = taux / 1200, n = mois.
   Capital restant après un an : K' = K q - M (q - 1) / r, avec q = (1 + r)^12. */
#include <stdio.h>

static real lire(const char *question)
{
    char s[16];
    printf("%s", question);
    input(s, sizeof s);
    return val(s);
}

int main(void)
{
    real capital, taux, r, mens, total, q, annuite, k;
    int annees, mois, an, x, y, x0, y0;

    for (;;) {
        cls();
        capital = lire("Capital ? ");
        taux = lire("Taux % ? ");
        annees = lire("Annees ? ");
        if (capital > 0 && annees >= 1 && annees <= 40 && taux >= 0)
            break;
        printf("Valeurs incorrectes");
        getkey();
    }
    mois = annees * 12;
    r = taux / 1200;                              /* taux mensuel */
    if (r == 0)
        mens = capital / mois;                    /* sans intérêts */
    else
        mens = capital * r / (1 - pow(1 + r, -mois));
    total = mens * mois;
    cls();
    printf("Mensualite%s\n", fmt(mens, 6, 2));
    printf("Total paye%s\n", fmt(total, 9, 0));
    printf("Interets  %s\n", fmt(total - capital, 9, 0));
    printf("Touche : courbe");
    getkey();

    /* capital restant dû, de 1 (en haut) à 0 (en bas), sur les lignes 9 à 31 */
    cls();
    printf("Restant du, %d ans", annees);
    q = pow(1 + r, 12);
    annuite = r == 0 ? mens * 12 : mens * (q - 1) / r;
    k = capital;
    x0 = 0;
    y0 = 9;
    line(0, 31, 119, 31);                         /* axe des années */
    for (an = 1; an <= annees; an++) {
        k = k * q - annuite;
        y = 31 - (int)(k * 22 / capital);         /* 22 points pour tout le capital */
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
