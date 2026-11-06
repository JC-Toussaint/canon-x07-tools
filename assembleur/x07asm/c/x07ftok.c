/* Canon X-07 : lecture d'un fichier en RAM valeur par valeur (comme INPUT #),
   pour f_tok(canal) en C et f_val(canal) en Quick C.  Les valeurs sont
   séparées par des espaces, des virgules, des points-virgules ou des fins de
   ligne. */
#include "x07.h"

#define RPTR(e) (*(unsigned char **)((e) + 4))
#define FEND(e) (*(unsigned char **)((e) + 6))

static char f_word[24];

static unsigned char f_sep(unsigned char c)
{
    return c == ' ' || c == ',' || c == ';' || c == '\r' || c == '\n' || c == '\t';
}

char *f_tok(unsigned char channel)
{
    unsigned char *e, *p;
    unsigned char n = 0;
    if (channel < 1 || channel > 5)
        x07_raise(5);                       /* FC Error */
    e = (unsigned char *)(0x02C5 + 8 * (channel - 1));
    p = RPTR(e);
    while (p <= FEND(e) && *p && f_sep(*p))
        p++;
    if (p > FEND(e) || !*p)
        x07_raise(22);                      /* IO Error : lecture au-delà de la fin */
    while (p <= FEND(e) && *p && !f_sep(*p)) {
        if (n < sizeof f_word - 1)
            f_word[n++] = *p;
        p++;
    }
    while (p <= FEND(e) && *p && f_sep(*p)) /* séparateurs suivants : f_eof juste */
        p++;
    RPTR(e) = p;
    f_word[n] = 0;
    return f_word;
}
