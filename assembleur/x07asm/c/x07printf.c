/* Canon X-07 : printf léger, à la place de celui de SDCC (z80.lib, 3 Ko environ).
 * L'éditeur de liens consulte x07.lib avant z80.lib : printf, vprintf, sprintf
 * et vsprintf sont pris ici, et la mise en forme de SDCC n'est plus emportée.
 *
 * Formats : %d %i %u %x %X %o %c %s %% ; « l » pour un long (%ld, %lu, %lx) ;
 * largeur (%5d, %*d), « - » à gauche (%-12s), « 0 » complète par des zéros
 * (%05d).  Pas de réels (%f) : str(x) ou r_str en Quick C et en C.
 */
#include <stdarg.h>
#include <stdio.h>
#include "x07.h"

static char *p_buf;                     /* sprintf : la chaîne ; printf : 0 (écran) */
static int p_count;

static void p_out(char c)
{
    if (p_buf)
        *p_buf++ = c;
    else
        putchar(c);
    p_count++;
}

static unsigned char p_base;

/* *v = *v / p_base ; rend le reste (division d'un long par un octet, bit à bit :
   bien plus court que __divulong et __modulong de z80.lib) */
static unsigned char p_div(unsigned long *v) __naked
{
    (void)v;
    __asm
        ld      a, (_p_base)
        ld      c, a
        ld      b, #32
        xor     a                       ; A : le reste
1$:
        push    hl
        sla     (hl)                    ; valeur << 1, le bit du haut dans CY
        inc     hl
        rl      (hl)
        inc     hl
        rl      (hl)
        inc     hl
        rl      (hl)
        pop     hl
        rla                             ; reste = 2 reste + ce bit
        cp      c
        jr      c, 2$
        sub     c
        inc     (hl)                    ; un bit du quotient
2$:
        djnz    1$
        ret
    __endasm;
}

static void p_pad(unsigned char width, unsigned char n, char c)
{
    while (n < width) {
        p_out(c);
        n++;
    }
}

static int p_format(const char *f, va_list ap)
{
    char digits[12];
    p_count = 0;
    for (; *f; f++) {
        char c = *f, left = 0, zero = 0, lng = 0;
        unsigned char width = 0, n = 0;
        if (c != '%') {
            p_out(c);
            continue;
        }
        c = *++f;
        for (; c == '-' || c == '0'; c = *++f)
            if (c == '-')
                left = 1;
            else
                zero = 1;
        if (c == '*') {
            width = va_arg(ap, int);
            c = *++f;
        }
        for (; c >= '0' && c <= '9'; c = *++f)
            width = width * 10 + c - '0';
        if (c == 'l') {
            lng = 1;
            c = *++f;
        } else if (c == 'h')
            c = *++f;
        if (c == 's' || c == 'c') {
            const char *s;
            if (c == 's') {
                s = va_arg(ap, const char *);
                if (!s)
                    s = "(null)";
            } else {
                digits[0] = (char)va_arg(ap, int);
                digits[1] = 0;
                s = digits;
            }
            while (s[n])
                n++;
            if (!left)
                p_pad(width, n, ' ');
            while (*s)
                p_out(*s++);
            if (left)
                p_pad(width, n, ' ');
        } else if (c == 'd' || c == 'i' || c == 'u' || c == 'x' || c == 'X' || c == 'o') {
            unsigned long v;
            unsigned char k = 0, neg = 0;
            p_base = c == 'x' || c == 'X' ? 16 : c == 'o' ? 8 : 10;
            if (lng)
                v = va_arg(ap, unsigned long);
            else
                v = va_arg(ap, unsigned int);
            if (c == 'd' || c == 'i') {          /* signé */
                if (lng ? (long)v < 0 : (int)v < 0) {
                    neg = 1;
                    v = lng ? -(long)v : (unsigned int)-(int)v;
                }
            }
            do {
                unsigned char d = p_div(&v);
                digits[k++] = d < 10 ? '0' + d : (c == 'x' ? 'a' : 'A') + d - 10;
            } while (v);
            n = k + neg;
            if (!left && !zero)
                p_pad(width, n, ' ');
            if (neg)
                p_out('-');
            if (!left && zero)
                p_pad(width, n, '0');
            while (k)
                p_out(digits[--k]);
            if (left)
                p_pad(width, n, ' ');
        } else if (c)
            p_out(c);                            /* %% et formats inconnus : le caractère */
        else
            break;                               /* « % » en fin de format */
    }
    if (p_buf)
        *p_buf = 0;
    return p_count;
}

int vprintf(const char *format, va_list ap)
{
    p_buf = 0;
    return p_format(format, ap);
}

int printf(const char *format, ...)
{
    va_list ap;
    int n;
    va_start(ap, format);
    p_buf = 0;
    n = p_format(format, ap);
    va_end(ap);
    return n;
}

int vsprintf(char *buf, const char *format, va_list ap)
{
    p_buf = buf;
    return p_format(format, ap);
}

int sprintf(char *buf, const char *format, ...)
{
    va_list ap;
    int n;
    va_start(ap, format);
    p_buf = buf;
    n = p_format(format, ap);
    va_end(ap);
    return n;
}
