/* Carnet de notes d'une classe, en Quick C, gardé dans un fichier en RAM du
   X-07 (NOTES) : il survit à l'extinction.
   python3 x07asm.py run exemples/qc/notes.qc --ram 16 --fenetre --memoire x07.mem
   Pour chaque élève : son nom et ses trois notes sur 20.  La liste donne la
   moyenne de chacun ; les statistiques, la moyenne de la classe, l'écart
   type, la meilleure et la plus faible moyenne.
   Une ligne par élève dans le fichier : « NOM note1 note2 note3 ». */
#include <stdio.h>
#include <string.h>

#define CHANNEL   1
#define FILE_SIZE 800                    /* une trentaine d'élèves */
#define NB_NOTES  3

static char nom[12];

static real lire_note(int k)
{
    char s[8];
    real n;
    do {
        printf("Note %d ? ", k);
        input(s, sizeof s);
        n = val(s);
    } while (n < 0 || n > 20);
    return n;
}

static void ajouter(void)
{
    real note[NB_NOTES];
    int k;
    cls();
    printf("Nom ? ");
    if (input(nom, sizeof nom) == 0)
        return;
    for (k = 0; k < NB_NOTES; k++)
        note[k] = lire_note(k + 1);
    f_open(CHANNEL, "notes", F_APPEND, FILE_SIZE);
    f_printf(CHANNEL, "%s", nom);
    for (k = 0; k < NB_NOTES; k++)
        f_printf(CHANNEL, " %s", str(note[k]));
    f_puts(CHANNEL, "\n");                       /* IO Error si le fichier est plein */
}

/* lit l'élève suivant : son nom dans nom[], sa moyenne en retour */
static real suivant(void)
{
    real somme = 0;
    int k;
    strcpy(nom, f_tok(CHANNEL));                 /* f_tok rend un tampon : on le copie */
    for (k = 0; k < NB_NOTES; k++)
        somme += f_val(CHANNEL);
    return somme / NB_NOTES;
}

static void liste(void)
{
    int lignes = 0;
    real m;
    cls();
    f_open(CHANNEL, "notes", F_READ, 0);
    if (f_eof(CHANNEL))
        printf("(aucun eleve)\n");
    while (!f_eof(CHANNEL)) {
        m = suivant();
        printf("%-12s%s\n", nom, fmt(m, 2, 2));
        if (++lignes == 4 && !f_eof(CHANNEL)) {
            getkey();
            cls();
            lignes = 0;
        }
    }
    getkey();
}

static void statistiques(void)
{
    real m, somme = 0, carres = 0, meilleure = -1, faible = 21, moyenne, ecart;
    char premier[12], dernier[12];
    int n = 0;
    cls();
    f_open(CHANNEL, "notes", F_READ, 0);
    while (!f_eof(CHANNEL)) {
        m = suivant();
        somme += m;
        carres += m * m;
        n++;
        if (m > meilleure) {
            meilleure = m;
            strcpy(premier, nom);
        }
        if (m < faible) {
            faible = m;
            strcpy(dernier, nom);
        }
    }
    if (n == 0) {
        printf("(aucun eleve)\n");
        getkey();
        return;
    }
    moyenne = somme / n;
    ecart = carres / n - moyenne * moyenne;      /* variance */
    ecart = ecart > 0 ? sqrt(ecart) : 0;
    printf("%d eleves  moy.%s\n", n, fmt(moyenne, 2, 2));
    printf("ecart type   %s\n", fmt(ecart, 2, 2));
    printf("+%-10s%s\n", premier, fmt(meilleure, 2, 2));
    printf("-%-10s%s", dernier, fmt(faible, 2, 2));
    getkey();
}

int main(void)
{
    char k;
    f_open(CHANNEL, "notes", F_APPEND, FILE_SIZE);    /* créé au premier lancement */
    for (;;) {
        cls();
        printf("1 Ajouter  2 Liste\n3 Statistiques\n4 Effacer  0 Fin\n");
        k = getkey();
        if (k == '1')
            ajouter();
        else if (k == '2')
            liste();
        else if (k == '3')
            statistiques();
        else if (k == '4') {
            cls();
            printf("Tout effacer (O/N) ?");
            if (getkey() == 'O')
                f_open(CHANNEL, "notes", F_WRITE, FILE_SIZE);
        } else if (k == '0')
            break;
    }
    cls();
    return 0;
}
