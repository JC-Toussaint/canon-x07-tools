/* Canon X-07 : bibliothèque d'appui des programmes C (SDCC), voir x07.h.
 *
 * Convention d'appel de SDCC 4 (sdcccall 1) : premier argument dans A (octet)
 * ou HL (mot), second dans L ou DE ; résultat dans A (octet) ou DE (mot).
 * IX (cadre de pile de SDCC) et IY sont sauvés autour des routines de la ROM.
 * Adresses : voir ROM.md.
 */
#include "x07.h"

unsigned char x07_gb[8];                 /* paramètres d'une commande T6834 */

void x07_putc(char c) __naked
{
    (void)c;
    __asm
        jp      0xC1BE                  ; LCDPUT : registres conservés
    __endasm;
}

/* BREAK, comme l'interpréteur ($C000) : extinction, pause, piles faibles */
void x07_break(void) __naked
{
    __asm
        ld      a, (0x002B)             ; BRKFLG
        or      a
        ret     z                       ; cas courant : rien à faire
        push    ix
        push    iy
        call    0xC5A6                  ; CHKBATT : bit 7, extinction demandée
        ld      a, (0x002B)
        bit     2, a                    ; bit 2 : pause, attendre une touche
        jr      z, 2$
        res     2, a
        ld      (0x002B), a
        call    0xC0BD                  ; T6FLUSH
1$:
        xor     a
        call    0xC90A                  ; INKEY
        jr      nz, 2$
        ld      a, (0x002B)
        or      a
        jr      z, 1$
2$:
        call    0xC06C                  ; BATTMSG : bits 1 et 3, piles faibles
        ld      a, (0x002B)
        rrca                            ; bit 0 : BREAK
        jr      c, 3$
        pop     iy
        pop     ix
        ret
3$:
        pop     iy
        pop     ix
    __endasm;
    __asm
_x07_stop::                             ; BREAK : « Break », retour au BASIC
        ld      a, (0x002B)
        and     a, #0xFA
        ld      (0x002B), a
        call    0xC0BD                  ; T6FLUSH
        ld      a, (0x00B9)             ; à la ligne si le curseur n est pas
        dec     a                       ; en colonne 1
        jr      z, 4$
        ld      a, #0x0D
        call    0xC1BE
        ld      a, #0x0A
        call    0xC1BE
4$:
        ld      hl, #x07_brk_msg
x07_msg_exit::                          ; affiche (HL), passe à la ligne, retour au BASIC
6$:
        ld      a, (hl)
        or      a
        jr      z, 7$
        call    0xC1BE
        inc     hl
        jr      6$
7$:
        ld      a, #0x0D
        call    0xC1BE
        ld      a, #0x0A
        call    0xC1BE
        jp      ___x07_exit
x07_brk_msg:
        .ascii  "Break"
        .db     0
    __endasm;
}

/* erreur de la ROM (crochet $00AB, installé par crt0.s) : E = numéro.
   « OV Error », comme le BASIC compilé, puis retour au BASIC. */
void x07_error(void) __naked
{
    __asm
        push    de
        call    0xE89E                  ; sortie vers l écran
        pop     de
        ld      a, (0x00B9)             ; à la ligne si le curseur n est pas
        dec     a                       ; en colonne 1
        jr      z, 1$
        ld      a, #0x0D
        call    0xC1BE
        ld      a, #0x0A
        call    0xC1BE
1$:
        ld      a, e                    ; code sur deux lettres (ERRTAB, $F123)
        dec     a
        add     a, a
        ld      l, a
        ld      h, #0
        ld      de, #0xF123
        add     hl, de
        ld      a, (hl)
        call    0xC1BE
        inc     hl
        ld      a, (hl)
        call    0xC1BE
        ld      hl, #2$
        jp      x07_msg_exit
2$:
        .ascii  " Error"
        .db     0
    __endasm;
}

void x07_raise(unsigned char code) __naked   /* erreur numéro code de la ROM */
{
    (void)code;
    __asm
        ld      e, a
        jp      _x07_error
    __endasm;
}

int putchar(int c)
{
    x07_break();
    if (c == '\n') {
        x07_putc('\r');
        x07_putc('\n');
    } else
        x07_putc((char)c);
    return c;
}

void x07_puts(const char *s)
{
    while (*s)
        putchar(*s++);
}

void cls(void) __naked
{
    __asm
        push    ix
        push    iy
        call    0xCE9E                  ; LCDCLS
        pop     iy
        pop     ix
        ret
    __endasm;
}

void locate(unsigned char col, unsigned char row) __naked
{
    (void)col; (void)row;
    __asm
        push    ix
        push    iy
        inc     a                       ; CURSET : H = colonne, L = ligne, depuis 1
        ld      h, a
        inc     l
        call    0xC164
        pop     iy
        pop     ix
        ret
    __endasm;
}

/* commande cmd du T6834, n paramètres dans x07_gb */
void x07_t6(unsigned char cmd, unsigned char n) __naked
{
    (void)cmd; (void)n;
    __asm
        push    ix
        push    iy
        ld      b, l                    ; B = nombre de paramètres
        ld      c, #0
        ld      hl, #_x07_gb
        ld      de, #0x026E             ; T6BUF
        call    0xC92F                  ; T6CMDP
        pop     iy
        pop     ix
        ret
    __endasm;
}

void pset(unsigned char x, unsigned char y)
{
    x07_gb[0] = x; x07_gb[1] = y;
    x07_t6(0x11, 2);
}

void preset(unsigned char x, unsigned char y)
{
    x07_gb[0] = x; x07_gb[1] = y;
    x07_t6(0x12, 2);
}

void line(unsigned char x1, unsigned char y1, unsigned char x2, unsigned char y2)
{
    x07_gb[0] = x1; x07_gb[1] = y1; x07_gb[2] = x2; x07_gb[3] = y2;
    x07_t6(0x14, 4);
}

void circle(unsigned char x, unsigned char y, unsigned char r)
{
    x07_gb[0] = x; x07_gb[1] = y; x07_gb[2] = r;
    x07_t6(0x15, 3);
}

static char inkey_rom(void) __naked
{
    __asm
        push    ix
        push    iy
        xor     a
        call    0xC90A                  ; INKEY : Z = 1 si aucune touche
        jr      nz, 1$
        xor     a
1$:
        pop     iy
        pop     ix
        ret
    __endasm;
}

char inkey(void)
{
    x07_break();
    return inkey_rom();
}

char getkey(void)
{
    char k;
    while (!(k = inkey()))
        ;
    return k;
}

/* saisie d'une ligne par la ROM ; rend l'adresse du texte (fin 00) */
static const char *input_rom(void) __naked
{
    __asm
        push    ix
        push    iy
        call    0xEBFF                  ; INPUTL : HL = $00D4 ; CY = 1 si BREAK
        pop     iy
        pop     ix
        jp      c, _x07_stop
        inc     hl
        ex      de, hl
        ret
    __endasm;
}

int input(char *buf, int max)
{
    const char *p = input_rom();
    int n = 0;
    while (*p && n < max - 1)
        buf[n++] = *p++;
    buf[n] = 0;
    return n;
}

void beep(unsigned int note, unsigned int duration) __naked
{
    (void)note; (void)duration;
    __asm
        push    ix
        push    iy
        push    hl
        pop     iy                      ; IY = note
        ld      h, e                    ; H = durée
        ld      l, #0
        ld      bc, #1$                 ; BEEPR ($C2DF) dépile une adresse
        push    bc                      ; de trop : on la fournit
        call    0xC2DF
1$:
        pop     iy
        pop     ix
        ret
    __endasm;
}

unsigned char inp(unsigned char port) __naked
{
    (void)port;
    __asm
        ld      c, a
        in      a, (c)
        ret
    __endasm;
}

void outp(unsigned char port, unsigned char v) __naked
{
    (void)port; (void)v;
    __asm
        ld      c, a
        out     (c), l
        ret
    __endasm;
}
