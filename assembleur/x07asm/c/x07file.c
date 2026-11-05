/* Canon X-07 : fichiers en RAM pour les programmes C, voir x07.h et FICHIERS.md.
 *
 * Ouverture, effacement et réservation de la zone des fichiers passent par les
 * commandes de la ROM (INIT#, DELETE, FSET), comme le BASIC compilé.  La
 * lecture et l'écriture suivent les pointeurs du canal (table KBNTAB, $02C5 :
 * +2 écriture, +4 lecture, +6 dernier octet des données) ; un octet 0 marque
 * la fin des données.  Les lignes finissent par CR LF, comme PRINT # : un
 * programme BASIC relit les fichiers écrits en C, et inversement.
 */
#include <stdarg.h>
#include <stdio.h>
#include "x07.h"

extern const unsigned int x07_fspace;   /* zone des fichiers (x07fsp.c, ou le programme) */

#define RAMSTR (*(unsigned char **)0x0210)
#define RAMEND (*(unsigned char **)0x0212)

static char f_cmd[48];
static unsigned char f_len;

/* commande de la ROM : gestionnaire en DE, texte (fin 00) en HL, comme l'interpréteur */
static void f_rom(const char *text, unsigned int handler) __naked
{
    (void)text; (void)handler;
    __asm
        push    ix
        push    iy
        call    1$
        pop     iy
        pop     ix
        ret
1$:
        dec     hl
        push    de
        rst     0x10                    ; CHRGET : A = premier caractère
        ret                             ; vers le handler
    __endasm;
}

/* FSET (texte en HL) : la ROM refait le haut de la zone BASIC comme CLEAR, pile
   comprise ; le programme garde sa pile et ses réglages (STKTOP, MEMSIZ, FRETOP) */
static void f_fset_rom(const char *text) __naked
{
    (void)text;
    __asm
        push    ix
        push    iy
        ld      (x07f_sp), sp
        ld      de, (0x01DD)
        ld      (x07f_mem), de
        ld      de, (0x01DF)
        ld      (x07f_mem+2), de
        ld      de, (0x0204)
        ld      (x07f_mem+4), de
        ld      de, #0xBF56             ; FSET
        call    2$
        ld      sp, (x07f_sp)
        ld      hl, (x07f_mem)
        ld      (0x01DD), hl
        ld      hl, (x07f_mem+2)
        ld      (0x01DF), hl
        ld      hl, (x07f_mem+4)
        ld      (0x0204), hl
        pop     iy
        pop     ix
        ret
2$:
        dec     hl
        push    de
        rst     0x10
        ret
x07f_sp:
        .dw     0
x07f_mem:
        .dw     0, 0, 0
    __endasm;
}

static void f_add(char c)
{
    if (f_len < sizeof f_cmd - 1)
        f_cmd[f_len++] = c;
}

static void f_num(unsigned int n)
{
    char d[6];
    unsigned char k = 0;
    do {
        d[k++] = '0' + n % 10;
        n /= 10;
    } while (n);
    while (k)
        f_add(d[--k]);
}

static void f_name(const char *prefix, const char *name)   /* "RAM:NOM" : nom de 6
                                                            caractères, en majuscules */
{
    unsigned char k = 0;
    f_add('"');
    while (*prefix)
        f_add(*prefix++);
    for (; *name && k < 6; name++, k++)
        f_add(*name >= 'a' && *name <= 'z' ? *name - 32 : *name);
    f_add('"');
}

static void f_zone(void)               /* zone des fichiers assez grande, sinon FSET */
{
    if ((unsigned int)(RAMEND - RAMSTR) < x07_fspace - 13) {
        f_len = 0;
        f_num(x07_fspace);
        f_cmd[f_len] = 0;
        f_fset_rom(f_cmd);
    }
}

static unsigned char *f_ent(unsigned char channel)
{
    if (channel < 1 || channel > 5)
        x07_raise(5);                   /* FC Error */
    return (unsigned char *)(0x02C5 + 8 * (channel - 1));
}

#define WPTR(e) (*(unsigned char **)((e) + 2))
#define RPTR(e) (*(unsigned char **)((e) + 4))
#define FEND(e) (*(unsigned char **)((e) + 6))

void f_open(unsigned char channel, const char *name, unsigned char mode, unsigned int size)
{
    unsigned char *e = f_ent(channel), *p;
    f_zone();
    f_len = 0;
    f_add('#');
    f_add('0' + channel);
    f_add(',');
    f_name("RAM:", name);
    if (mode != F_READ) {               /* créé s'il n'existe pas */
        f_add(',');
        f_num(size ? size : 256);
    }
    f_cmd[f_len] = 0;
    f_rom(f_cmd, 0xE699);               /* INIT# ; fichier absent en lecture : NE Error */
    if (mode == F_WRITE)               /* vidé : données à zéro */
        for (p = RPTR(e); p <= FEND(e); p++)
            *p = 0;
    else if (mode == F_APPEND) {       /* écriture après les données */
        p = RPTR(e);
        while (p <= FEND(e) && *p)
            p++;
        WPTR(e) = p;
    }
}

void f_delete(const char *name)
{
    f_zone();
    f_len = 0;
    f_name("", name);
    f_cmd[f_len] = 0;
    f_rom(f_cmd, 0xE682);               /* DELETE ; absent : NE Error */
}

void f_putc(unsigned char channel, char c)
{
    unsigned char *e = f_ent(channel), *p;
    if (c == '\n') {                    /* fin de ligne CR LF, comme PRINT # */
        f_putc(channel, '\r');
        c = '\n';
    }
    p = WPTR(e);
    if (p > FEND(e))
        x07_raise(22);                  /* IO Error : fichier plein */
    *p = c;
    WPTR(e) = p + 1;
}

void f_puts(unsigned char channel, const char *s)
{
    while (*s)
        f_putc(channel, *s++);
}

void f_printf(unsigned char channel, const char *format, ...)
{
    static char buf[82];
    va_list ap;
    va_start(ap, format);
    vsprintf(buf, format, ap);
    va_end(ap);
    f_puts(channel, buf);
}

int f_eof(unsigned char channel)
{
    unsigned char *e = f_ent(channel), *p = RPTR(e);
    if (p <= FEND(e) && *p == '\n')     /* saut de ligne laissé par la ligne lue */
        p++;
    return p > FEND(e) || *p == 0;
}

int f_getc(unsigned char channel)
{
    unsigned char *e = f_ent(channel), *p = RPTR(e);
    if (p > FEND(e) || *p == 0)
        return -1;
    RPTR(e) = p + 1;
    return *p;
}

int f_gets(unsigned char channel, char *buf, int max)
{
    unsigned char *e = f_ent(channel), *p;
    int n = 0;
    if (f_eof(channel)) {
        buf[0] = 0;
        return -1;
    }
    p = RPTR(e);
    if (*p == '\n')
        p++;
    while (p <= FEND(e) && *p && *p != '\r') {
        if (n < max - 1)
            buf[n++] = *p;
        p++;
    }
    if (p <= FEND(e) && *p == '\r')
        p++;
    RPTR(e) = p;
    buf[n] = 0;
    return n;
}
