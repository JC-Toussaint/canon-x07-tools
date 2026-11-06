/* Tir balistique en Quick C : réels du X-07 écrits comme des nombres.
   python3 x07asm.py run exemples/qc/tir.qc --fenetre
   On tape la vitesse de départ (m/s) et l'angle (degrés) ; le programme
   donne la durée du vol, la portée et la hauteur atteinte, puis trace la
   trajectoire.  Sans frottement de l'air : la portée est la plus grande à 45°.
   Une touche entre les écrans. */
#include <stdio.h>

#define G 9.81                          /* pesanteur, m/s² */

static real vx, vy;                     /* vitesse de départ, horizontale et verticale */

static real lire(const char *question)
{
    char s[12];
    printf("%s", question);
    input(s, sizeof s);
    return val(s);
}

static real hauteur(real t)             /* altitude à l'instant t */
{
    return vy * t - G * t * t / 2;
}

int main(void)
{
    real v, angle, duree, portee, haut, t;
    int k, x, y, x0, y0;

    for (;;) {
        cls();
        v = lire("Vitesse m/s ? ");
        angle = lire("Angle deg ? ");
        if (v > 0 && angle > 0 && angle < 90)
            break;
        printf("Vitesse > 0, angle\nde 1 a 89 degres");
        getkey();
    }
    angle = angle * atan(1) / 45;         /* en radians */
    vx = v * cos(angle);
    vy = v * sin(angle);
    duree = 2 * vy / G;
    portee = vx * duree;
    haut = hauteur(duree / 2);            /* au sommet, à mi-parcours */

    cls();
    printf("Duree  %s s\n", fmt(duree, 4, 2));
    printf("Portee %s m\n", fmt(portee, 5, 1));
    printf("Hauteur%s m\n", fmt(haut, 5, 1));
    printf("Touche : trajectoire");
    getkey();

    /* trajectoire : la portée sur 120 points, la hauteur sur les lignes 31 à 9 */
    cls();
    printf("%s m", fmt(portee, 4, 0));
    line(0, 31, 119, 31);
    x0 = 0;
    y0 = 31;
    for (k = 1; k <= 24; k++) {
        t = duree * k / 24;
        x = vx * t * 119 / portee;
        y = 31 - (int)(hauteur(t) * 22 / haut);
        if (y > 31)
            y = 31;
        line(x0, y0, x, y);
        x0 = x;
        y0 = y;
    }
    circle(60, 9, 2);                     /* le sommet */
    getkey();
    cls();
    return 0;
}
