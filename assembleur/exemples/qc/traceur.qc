/* Traceur de courbes en Quick C : réels du X-07 et graphismes (120 x 32 points).
   python3 x07asm.py run exemples/qc/traceur.qc --fenetre
   On choisit une fonction et l'intervalle des x ; le programme calcule 61
   points, cherche le plus petit et le plus grand y pour remplir l'écran, trace
   les axes s'ils sont dans le cadre, puis la courbe.  Une touche donne les
   bornes des y, une autre revient au menu. */
#include <stdio.h>

#define POINTS 60                       /* intervalles : 61 points calculés */

static real y[POINTS + 1];

static real f(int choix, real x)
{
    if (choix == 1)
        return sin(x);
    if (choix == 2)
        return x * sin(x);
    if (choix == 3)
        return exp(-x / 4) * cos(2 * x);   /* oscillation amortie */
    return x * x * x - 3 * x;              /* cubique */
}

static real lire(const char *question)
{
    char s[12];
    printf("%s", question);
    input(s, sizeof s);
    return val(s);
}

/* colonne de l'écran (0 à 119) pour x, ligne (31 en bas, 0 en haut) pour v */
static int colonne(real x, real xmin, real xmax)
{
    return (x - xmin) * 119 / (xmax - xmin);
}

static int ligne_ecran(real v, real ymin, real ymax)
{
    return 31 - (int)((v - ymin) * 31 / (ymax - ymin));
}

int main(void)
{
    real xmin, xmax, x, ymin, ymax;
    int choix, k, px, py, px0, py0;

    for (;;) {
        cls();
        printf("1 sin x  2 x sin x\n3 amortie 4 cubique\n0 fin ? ");
        choix = getkey() - '0';
        if (choix == 0)
            break;
        if (choix < 1 || choix > 4)
            continue;
        cls();
        xmin = lire("x de ? ");
        xmax = lire("a ? ");
        if (xmax <= xmin) {
            printf("il faut x de < a");
            getkey();
            continue;
        }
        printf("calcul...");

        for (k = 0; k <= POINTS; k++) {     /* les points, et leurs bornes */
            x = xmin + (xmax - xmin) * k / POINTS;
            y[k] = f(choix, x);
            if (k == 0 || y[k] < ymin)
                ymin = y[k];
            if (k == 0 || y[k] > ymax)
                ymax = y[k];
        }
        if (ymax == ymin) {                 /* courbe plate : une marge */
            ymin = ymin - 1;
            ymax = ymax + 1;
        }

        cls();
        if (ymin <= 0 && ymax >= 0) {       /* axe des x, bords compris */
            py = ligne_ecran(0, ymin, ymax);
            line(0, py, 119, py);
        }
        if (xmin <= 0 && xmax >= 0) {       /* axe des y */
            px = colonne(0, xmin, xmax);
            line(px, 0, px, 31);
        }
        for (k = 0; k <= POINTS; k++) {
            px = k * 119 / POINTS;
            py = ligne_ecran(y[k], ymin, ymax);
            if (k > 0)
                line(px0, py0, px, py);
            px0 = px;
            py0 = py;
        }
        getkey();
        cls();
        printf("x de%s a%s\n", fmt(xmin, 3, 2), fmt(xmax, 3, 2));
        printf("y de%s\n", fmt(ymin, 5, 4));   /* 20 colonnes : forme fixe */
        printf("   a%s\n", fmt(ymax, 5, 4));
        getkey();
    }
    cls();
    return 0;
}
