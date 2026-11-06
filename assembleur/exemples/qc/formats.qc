/* printf en Quick C : des tableaux alignés sur l'écran de 20 colonnes.
   python3 x07asm.py run exemples/qc/formats.qc --fenetre
   1. des caractères : code décimal, hexadécimal, octal (%3d %02X %03o %c) ;
   2. les puissances de 2, en entiers longs (%2d %9lu %7lX) ;
   3. un ticket de caisse : articles, quantités, prix en réels du X-07
      (%-8s %2d, fmt(x, ...) pour les réels, %05d, %%).
   Les lignes sont préparées par sprintf, puis affichées par écrans de 4 lignes ;
   une touche pour passer à l'écran suivant.  Une ligne de 20 caractères pile
   ferait passer le curseur à la ligne suivante, puis « \n » sauterait une
   ligne vide : les lignes ont 19 caractères au plus. */
#include <stdio.h>

static char ligne[24];
static int rang;                         /* ligne de l'écran, de 0 à 3 */

static void afficher(void)               /* la ligne préparée, 4 par écran */
{
    if (rang == 0)
        cls();
    printf("%s", ligne);
    if (++rang == 4) {
        getkey();
        rang = 0;
    } else
        printf("\n");
}

static void fin_de_page(void)            /* écran incomplet : on attend aussi */
{
    if (rang) {
        getkey();
        rang = 0;
    }
}

static const char *article[4] = {"Pain", "Lait", "Fromage", "Pommes"};
static const int quantite[4] = {2, 3, 1, 2};
static const real prix[4] = {1.35, 0.98, 7.5, 2.49};

int main(void)
{
    static const char codes[] = "Aaz0~";
    real total, montant, tva;
    unsigned long p;
    int k;

    sprintf(ligne, "Car Dec Hex Oct");
    afficher();
    for (k = 0; codes[k]; k++) {
        sprintf(ligne, " %c  %3d  %02X %03o", codes[k], codes[k], codes[k], codes[k]);
        afficher();
    }
    fin_de_page();

    sprintf(ligne, " n      2^n    hexa");
    afficher();
    p = 1;
    for (k = 0; k <= 31; k++) {
        if (k % 4 == 0 && k <= 24) {     /* 2^0, 2^4... 2^24 : 19 colonnes au plus */
            sprintf(ligne, "%2d%9lu %7lX", k, p, p);
            afficher();
        }
        if (k < 31)
            p = p * 2;
    }
    sprintf(ligne, "2^31 = %lu", p);     /* un long signé s'arrête juste avant */
    afficher();
    fin_de_page();

    total = 0;
    sprintf(ligne, "Ticket n. %05d", 42);
    afficher();
    for (k = 0; k < 4; k++) {
        montant = prix[k] * quantite[k];
        total += montant;
        sprintf(ligne, "%-8s%2d x%s", article[k], quantite[k], fmt(prix[k], 2, 2));
        afficher();
        sprintf(ligne, "%14s", fmt(montant, 3, 2));
        afficher();
    }
    tva = total * 5.5 / 105.5;           /* TVA à 5,5 % comprise dans les prix */
    sprintf(ligne, "TOTAL   %s", fmt(total, 3, 2));
    afficher();
    sprintf(ligne, "dont TVA 5.5%%%s", fmt(tva, 2, 2));
    afficher();
    fin_de_page();
    cls();
    return 0;
}
