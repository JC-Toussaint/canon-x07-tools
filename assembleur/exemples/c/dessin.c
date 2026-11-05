/* Graphismes et son en C pour le Canon X-07 (SDCC)
   python3 x07asm.py run exemples/c/dessin.c --fenetre
   Cadre, cercles, rayons, puis une gamme ; une touche pour finir. */
#include "x07.h"

static const unsigned int gamme[8] = { 1, 3, 5, 6, 8, 10, 12, 13 };  /* do ré mi... (BEEP) */

int main(void)
{
    unsigned char i;

    cls();
    line(0, 0, 119, 0);                   /* cadre de l'écran : 120 x 32 points */
    line(119, 0, 119, 31);
    line(119, 31, 0, 31);
    line(0, 31, 0, 0);
    for (i = 4; i <= 14; i += 5)
        circle(30, 15, i);
    for (i = 62; i <= 118; i += 8)        /* éventail */
        line(90, 30, i, 1);
    locate(8, 1);                         /* entre les deux : colonnes 8 et 9 */
    x07_puts("C!");
    for (i = 0; i < 8; i++)
        beep(gamme[i], 3);
    getkey();
    cls();
    return 0;
}
