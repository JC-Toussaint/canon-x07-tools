/* Bonjour en C pour le Canon X-07 (SDCC)
   python3 x07asm.py run exemples/c/bonjour.c --fenetre
   Saisie d'un nom, printf, tableau, fonction récursive. */
#include <stdio.h>
#include "x07.h"

static int carres[6];

static unsigned long factorielle(unsigned char n)
{
    return n <= 1 ? 1 : n * factorielle(n - 1);
}

int main(void)
{
    char nom[13];
    int i;

    cls();
    printf("Nom ? ");
    input(nom, sizeof nom);
    printf("Bonjour %s !\n", nom);
    for (i = 0; i < 6; i++)
        carres[i] = i * i;
    printf("5*5=%d  10!=%lu\n", carres[5], factorielle(10));
    printf("Une touche...");
    getkey();
    return 0;
}
