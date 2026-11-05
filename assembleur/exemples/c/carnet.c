/* Carnet d'adresses en C, gardé dans un fichier en RAM du X-07 (CARNET).
   python3 x07asm.py run exemples/c/carnet.c --ram 16 --fenetre --memoire x07.mem
   Le fichier survit à l'extinction : avec --memoire, l'émulateur le retrouve
   d'une séance à l'autre, comme la machine.  Une ligne par personne :
   NOM;TELEPHONE, que relirait aussi un programme BASIC (LINE INPUT #). */
#include <stdio.h>
#include <string.h>
#include "x07.h"

#define CHANNEL  1
#define FILE_SIZE 1000                      /* octets du fichier, fixés à sa création */

/* zone des fichiers (FSET) : le fichier et son en-tête de 14 octets doivent y
   tenir (1024 octets par défaut) ; sinon OM Error, comme en BASIC */
const unsigned int x07_fspace = 1200;

static char ligne[40];

static void titre(const char *t)
{
    cls();
    printf("%s\n", t);
}

static void attendre(void)
{
    printf("(touche)");
    getkey();
}

static void ajouter(void)
{
    char nom[16], tel[16];
    titre("-- Ajouter --");
    printf("Nom ? ");
    if (input(nom, sizeof nom) == 0)
        return;
    printf("Tel ? ");
    input(tel, sizeof tel);
    f_open(CHANNEL, "carnet", F_APPEND, FILE_SIZE);
    f_printf(CHANNEL, "%s;%s\n", nom, tel);  /* IO Error si le fichier est plein */
}

/* affiche les fiches contenant motif (toutes si motif est vide), 3 par écran */
static void lister(const char *motif)
{
    unsigned char n = 0, vues = 0;
    char *sep;
    titre(*motif ? "-- Recherche --" : "-- Liste --");
    f_open(CHANNEL, "carnet", F_READ, 0);
    while (f_gets(CHANNEL, ligne, sizeof ligne) >= 0) {
        if (*motif && !strstr(ligne, motif))
            continue;
        sep = strchr(ligne, ';');
        if (sep)
            *sep = ' ';
        printf("%s\n", ligne);
        vues++;
        if (++n == 3) {
            attendre();
            cls();
            n = 0;
        }
    }
    if (!vues)
        printf("(aucune fiche)\n");
    attendre();
}

int main(void)
{
    char motif[16], k;
    f_open(CHANNEL, "carnet", F_APPEND, FILE_SIZE);   /* créé au premier lancement */
    for (;;) {
        titre("1 Ajouter 2 Liste");
        printf("3 Chercher 4 Vider\n0 Fin\n");
        k = getkey();
        if (k == '1')
            ajouter();
        else if (k == '2')
            lister("");
        else if (k == '3') {
            titre("-- Recherche --");
            printf("Texte ? ");
            input(motif, sizeof motif);
            lister(motif);
        } else if (k == '4') {
            titre("Tout effacer (O/N) ?");
            if (getkey() == 'O')
                f_open(CHANNEL, "carnet", F_WRITE, FILE_SIZE);
        } else if (k == '0')
            break;
    }
    cls();
    return 0;
}
