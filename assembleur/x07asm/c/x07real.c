/* Canon X-07 : réels en double précision de la ROM (BCD, 14 chiffres), voir x07.h.
 *
 * Chaque opération charge ses opérandes dans l'accumulateur de la ROM (FAC,
 * $044E, type 8 dans VALTYP $01D9), appelle la routine de la ROM, puis range
 * le résultat : ce sont les calculs du BASIC du X-07, au chiffre près.
 * Les opérations + - * / ^ passent par le répartiteur de la ROM ($F9E4),
 * comme l'interpréteur.  Une erreur (OV, /0...) arrête le programme (crt0.s).
 */
#include "x07.h"

static real *r_dst;
static const real *r_a, *r_b;
static char r_txt[40];

/* FAC <- (HL), double précision ; (HL) <- FAC */
static void r_ld(void) __naked
{
    __asm
x07r_ld:
        ld      de, #0x044E             ; FAC
        ld      bc, #8
        ldir
        ld      a, #8
        ld      (0x01D9), a             ; VALTYP : double
        ret
x07r_st:
        ex      de, hl
        ld      hl, #0x044E
        ld      bc, #8
        ldir
        ret
    __endasm;
}

/* *r_dst = *r_a op *r_b ; op : 0 + 1 - 2 * 3 / 4 ^ */
static void r_op(unsigned char op) __naked
{
    (void)op;
    __asm
        push    ix
        push    iy
        ld      (x07r_opc), a
        ld      hl, #1$                 ; retour du répartiteur
        push    hl
        ld      hl, (_r_a)
        call    x07r_ld
        ld      a, (x07r_opc)           ; opérande gauche empilé comme
        ld      c, a                    ; l évaluateur ($F976) : FACINT, FAC,
        ld      hl, (0x0450)            ; FAC+6, FAC+4, puis type et opération
        push    hl
        ld      hl, (0x044E)
        push    hl
        ld      hl, (0x0454)
        push    hl
        ld      hl, (0x0452)
        push    hl
        ld      b, #8
        push    bc
        ld      hl, (_r_b)
        call    x07r_ld
        jp      0xF9E4                  ; FOPDISP
1$:
        ld      hl, (_r_dst)
        call    x07r_st
        pop     iy
        pop     ix
        ret
x07r_opc:
        .db     0
    __endasm;
}

/* *r_dst = f(*r_a), f : routine de la ROM en HL */
static void r_fn(unsigned int rom) __naked
{
    (void)rom;
    __asm
        push    ix
        push    iy
        ld      de, #1$
        push    de                      ; retour de la routine
        push    hl                      ; la routine, lancée par RET
        ld      hl, (_r_a)
        call    x07r_ld
        ret
1$:
        ld      hl, (_r_dst)
        call    x07r_st
        pop     iy
        pop     ix
        ret
    __endasm;
}

void r_add(real *r, const real *a, const real *b) { r_dst = r; r_a = a; r_b = b; r_op(0); }
void r_sub(real *r, const real *a, const real *b) { r_dst = r; r_a = a; r_b = b; r_op(1); }
void r_mul(real *r, const real *a, const real *b) { r_dst = r; r_a = a; r_b = b; r_op(2); }
void r_div(real *r, const real *a, const real *b) { r_dst = r; r_a = a; r_b = b; r_op(3); }
void r_pow(real *r, const real *a, const real *b) { r_dst = r; r_a = a; r_b = b; r_op(4); }

void r_neg(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xC9E0); }   /* FNEG */
void r_abs(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xC9DC); }   /* FABS */
void r_sqrt(real *r, const real *a) { r_dst = r; r_a = a; r_fn(0xB694); }   /* FSQR */
void r_sin(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xB549); }   /* FSIN */
void r_cos(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xB530); }   /* FCOS */
void r_tan(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xB593); }   /* FTAN */
void r_atn(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xB5AC); }   /* FATN */
void r_exp(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xB6DD); }   /* FEXP */
void r_log(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xB609); }   /* FLOG */
void r_intp(real *r, const real *a) { r_dst = r; r_a = a; r_fn(0xCC23); }   /* FINT */
void r_fix(real *r, const real *a)  { r_dst = r; r_a = a; r_fn(0xCC14); }   /* FFIX */

/* A = 1 si *r_a < *r_b, $FF si *r_a > *r_b, 0 si égaux (DCMP) */
static signed char r_cmp0(void) __naked
{
    __asm
        push    ix
        push    iy
        ld      hl, (_r_b)
        call    x07r_ld
        ld      hl, #0x044E             ; ARG <- FAC
        ld      de, #0x049F
        ld      bc, #8
        ldir
        ld      hl, (_r_a)
        call    x07r_ld
        call    0xCAD9                  ; DCMP
        pop     iy
        pop     ix
        ret
    __endasm;
}

int r_cmp(const real *a, const real *b)
{
    r_a = a; r_b = b;
    return -r_cmp0();
}

/* (HL) texte terminé par 00 -> FAC (FIN), puis double précision -> *r_dst */
static void r_fin(const char *s) __naked
{
    (void)s;
    __asm
        push    ix
        push    iy
        call    0xBA21                  ; FIN
        call    0xCB90                  ; FCDBL
        ld      hl, (_r_dst)
        call    x07r_st
        pop     iy
        pop     ix
        ret
    __endasm;
}

void r_set(real *r, const char *text)
{
    unsigned char n = 0;
    while (*text == ' ')
        text++;
    while (text[n] && n < sizeof r_txt - 2) {
        r_txt[n] = text[n];
        n++;
    }
    r_txt[n++] = '#';                   /* lu en double précision, comme 1.5# */
    r_txt[n] = 0;
    r_dst = r;
    r_fin(r_txt);
}

static void r_hl(int n) __naked        /* *r_dst = n */
{
    (void)n;
    __asm
        push    ix
        push    iy
        call    0xCAEF                  ; HL2FAC
        call    0xCB90                  ; FCDBL
        ld      hl, (_r_dst)
        call    x07r_st
        pop     iy
        pop     ix
        ret
    __endasm;
}

void r_int(real *r, int n)
{
    r_dst = r;
    r_hl(n);
}

static int r_cint(void) __naked        /* partie entière de *r_a, tronquée (FCINT) */
{
    __asm
        push    ix
        push    iy
        ld      hl, (_r_a)
        call    x07r_ld
        call    0xCAE0                  ; FCINT : OV au-delà de 16 bits
        ld      de, (0x0450)            ; FACINT
        pop     iy
        pop     ix
        ret
    __endasm;
}

int r_toint(const real *a)
{
    r_a = a;
    return r_cint();
}

/* texte de *r_a : flags = 0 pour FOUT (comme STR$), sinon PRINT USING */
static const char *r_out(unsigned char flags, unsigned int bc) __naked
{
    (void)flags; (void)bc;
    __asm
        push    ix
        push    iy
        push    af
        push    de
        ld      hl, (_r_a)
        call    x07r_ld
        pop     bc                      ; B = digits prefix le point, C = après
        pop     af
        or      a
        jr      nz, 1$
        call    0xBBAB                  ; FOUT : HL = text, fin 00
        jr      2$
1$:
        call    0xBBAC                  ; comme PRINT USING ($D0EA)
2$:
        ex      de, hl
        pop     iy
        pop     ix
        ret
    __endasm;
}

static char *r_copy(char *buf, const char *s)
{
    char *p = buf;
    while ((*p++ = *s++))
        ;
    return buf;
}

char *r_str(char *buf, const real *a)
{
    r_a = a;
    return r_copy(buf, r_out(0, 0));
}

char *r_fmt(char *buf, const real *a, unsigned char digits, unsigned char decimals)
{
    r_a = a;
    return r_copy(buf, r_out(0x80, (unsigned int)digits << 8
                                   | (decimals ? decimals + 1 : 0)));
}

void r_print(const real *a)
{
    char buf[26];
    x07_puts(r_str(buf, a));
}
