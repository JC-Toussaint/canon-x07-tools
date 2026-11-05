/* Canon X-07 : bibliothèque d'appui des programmes C (SDCC).
 *
 * Écran de 20 x 4 caractères, 120 x 32 points ; les routines passent par la
 * ROM du X-07, comme le BASIC.  printf, puts et putchar écrivent à l'écran
 * ('\n' passe à la ligne).  La touche BREAK arrête le programme pendant un
 * affichage ou une attente de touche ; dans une longue boucle de calcul,
 * appelez x07_break() de temps en temps.
 */
#ifndef X07_H
#define X07_H

/* écran */
void cls(void);                                   /* efface l'écran */
void locate(unsigned char col, unsigned char row);/* colonne 0-19, ligne 0-3 */
void x07_putc(char c);                            /* un caractère, codes de contrôle admis */
void x07_puts(const char *s);                     /* une chaîne, sans passer à la ligne */

/* graphismes (x 0-119, y 0-31) */
void pset(unsigned char x, unsigned char y);
void preset(unsigned char x, unsigned char y);
void line(unsigned char x1, unsigned char y1, unsigned char x2, unsigned char y2);
void circle(unsigned char x, unsigned char y, unsigned char r);

/* clavier */
char inkey(void);                                 /* touche, ou 0 si aucune */
char getkey(void);                                /* attend une touche */
int  input(char *buf, int max);                   /* saisit une ligne (avec écho) ;
                                                     rend sa longueur */
/* son : note 1-4095 comme BEEP (192000/note Hz), durée en 1/20 s */
void beep(unsigned int note, unsigned int duree);

/* BREAK, piles faibles, extinction : comme l'interpréteur */
void x07_break(void);

/* mémoire et ports */
#define PEEK(a)    (*(volatile unsigned char *)(a))
#define POKE(a, v) (*(volatile unsigned char *)(a) = (v))
unsigned char inp(unsigned char port);
void outp(unsigned char port, unsigned char v);

#endif
