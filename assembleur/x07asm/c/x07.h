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
void beep(unsigned int note, unsigned int duration);

/* BREAK, piles faibles, extinction : comme l'interpréteur */
void x07_break(void);

/* réels : la double précision du X-07 (14 chiffres, calcul décimal BCD),
   calculée par la ROM comme en BASIC.  r = a + b s'écrit r_add(&r, &a, &b) ;
   le résultat peut être l'un des opérandes.  Une erreur (OV, /0...) arrête
   le programme avec son message, comme le BASIC. */
typedef struct { unsigned char b[8]; } real;
void r_set(real *r, const char *text);            /* "3.14159265358979", "1E-5" */
void r_int(real *r, int n);
int  r_toint(const real *a);                      /* partie entière tronquée (OV hors
                                                     de -32768..32767) */
void r_add(real *r, const real *a, const real *b);
void r_sub(real *r, const real *a, const real *b);
void r_mul(real *r, const real *a, const real *b);
void r_div(real *r, const real *a, const real *b);
void r_pow(real *r, const real *a, const real *b);   /* a ^ b */
void r_neg(real *r, const real *a);
void r_abs(real *r, const real *a);
void r_sqrt(real *r, const real *a);
void r_sin(real *r, const real *a);               /* radians */
void r_cos(real *r, const real *a);
void r_tan(real *r, const real *a);
void r_atn(real *r, const real *a);
void r_exp(real *r, const real *a);
void r_log(real *r, const real *a);               /* logarithme népérien */
void r_intp(real *r, const real *a);              /* INT : partie entière par défaut */
void r_fix(real *r, const real *a);               /* FIX : partie entière tronquée */
int  r_cmp(const real *a, const real *b);         /* -1 si a < b, 0 si égaux, 1 si a > b */
char *r_str(char *buf, const real *a);            /* comme STR$ (espace devant un
                                                     positif) ; buf : 26 octets */
char *r_fmt(char *buf, const real *a, unsigned char digits, unsigned char decimals);
                                                  /* comme PRINT USING "###.##" :
                                                     chiffres avant le point, décimales */
void r_print(const real *a);                      /* affiche r_str */
char *r_s(const real *a);                         /* r_str dans un tampon tournant */
char *r_f(const real *a, unsigned char digits, unsigned char decimals);
                                                  /* r_fmt, tampon tournant */

/* fichiers en RAM du X-07 : ils survivent à l'extinction.  Canal (channel) 1 à 5,
   nom (name) de 6 caractères au plus, taille (size) fixée à la création (256
   octets si 0).  La zone
   des fichiers (FSET) est de 1024 octets ; pour la changer, définir dans le
   programme : const unsigned int x07_fspace = 3000;
   Erreurs comme en BASIC : NE (fichier absent en lecture), IO (fichier plein). */
#define F_READ   0                               /* depuis le début */
#define F_WRITE  1                               /* vidé (créé s'il n'existe pas) */
#define F_APPEND 2                               /* écriture après les données */
void f_open(unsigned char channel, const char *name, unsigned char mode, unsigned int size);
#define f_close(channel) ((void)(channel))       /* rien à faire sur le X-07 */
void f_putc(unsigned char channel, char c);      /* '\n' : fin de ligne CR LF */
void f_puts(unsigned char channel, const char *s);
void f_printf(unsigned char channel, const char *format, ...);
int  f_getc(unsigned char channel);              /* -1 en fin de fichier */
int  f_gets(unsigned char channel, char *buf, int max);   /* une ligne, sans sa fin ;
                                                    rend sa longueur, -1 en fin */
int  f_eof(unsigned char channel);
void f_delete(const char *name);                 /* NE Error s'il n'existe pas */

void x07_raise(unsigned char code);               /* erreur de la ROM : 5 FC, 22 IO... */

/* mémoire et ports */
#define PEEK(a)    (*(volatile unsigned char *)(a))
#define POKE(a, v) (*(volatile unsigned char *)(a) = (v))
unsigned char inp(unsigned char port);
void outp(unsigned char port, unsigned char v);

#endif
