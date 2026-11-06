/* Carnet de consommation d'une voiture, en Quick C, gardé dans un fichier en
   RAM du X-07 (CONSO) : il survit à l'extinction.
   python3 x07asm.py run exemples/qc/conso.qc --ram 16 --fenetre --memoire x07.mem
   À chaque plein, on tape le kilométrage du compteur et les litres versés.
   Le bilan donne la consommation de chaque plein et la moyenne, en litres
   aux 100 km : les litres d'un plein ont servi aux kilomètres depuis le
   plein précédent.  Une ligne par plein dans le fichier : « km litres ». */
#include <stdio.h>

#define CHANNEL   1
#define FILE_SIZE 600                    /* environ 40 pleins */

static real lire(const char *question)
{
    char s[12];
    printf("%s", question);
    input(s, sizeof s);
    return val(s);
}

static void plein(void)
{
    real km, litres;
    cls();
    printf("-- Plein --\n");
    km = lire("Compteur km ? ");
    litres = lire("Litres ? ");
    if (km <= 0 || litres <= 0)
        return;
    f_open(CHANNEL, "conso", F_APPEND, FILE_SIZE);
    f_printf(CHANNEL, "%s %s\n", str(km), str(litres));   /* IO Error si plein */
}

static void bilan(void)
{
    real km, litres, km0, depart, total = 0, l100;
    int n = 0, lignes = 0;
    cls();
    f_open(CHANNEL, "conso", F_READ, 0);
    while (!f_eof(CHANNEL)) {
        km = f_val(CHANNEL);
        litres = f_val(CHANNEL);
        if (n == 0)
            depart = km;                 /* premier plein : point de départ */
        else {
            l100 = litres * 100 / (km - km0);
            printf("%s km%s l\n", fmt(km, 6, 0), fmt(l100, 3, 1));
            total += litres;
            if (++lignes == 3) {
                getkey();
                cls();
                lignes = 0;
            }
        }
        km0 = km;
        n++;
    }
    if (n < 2)
        printf("Il faut deux pleins\n");
    else
        printf("Moyenne%s l/100\n", fmt(total * 100 / (km0 - depart), 3, 2));
    getkey();
}

int main(void)
{
    char k;
    f_open(CHANNEL, "conso", F_APPEND, FILE_SIZE);    /* créé au premier lancement */
    for (;;) {
        cls();
        printf("1 Plein  2 Bilan\n3 Tout effacer\n0 Fin\n");
        k = getkey();
        if (k == '1')
            plein();
        else if (k == '2')
            bilan();
        else if (k == '3') {
            cls();
            printf("Effacer (O/N) ?");
            if (getkey() == 'O')
                f_open(CHANNEL, "conso", F_WRITE, FILE_SIZE);
        } else if (k == '0')
            break;
    }
    cls();
    return 0;
}
