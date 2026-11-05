;; Démarrage d'un programme C (SDCC) pour le Canon X-07.
;; Chargement : CLEAR 50,&H(org-1)  puis  EXEC &H(org) : le programme commence
;; au premier octet ; il garde la pile du BASIC (sous le programme) et revient
;; au BASIC à la fin de main, ou par exit().
        .module crt0
        .globl  _main
        .globl  ___x07_exit

        .area   _CODE
init:
        push    af
        push    bc
        push    de
        push    hl
        push    ix
        push    iy
        ld      (x07_sp), sp
        call    gsinit                  ; variables globales
        call    _main
_exit::                                 ; exit(n) : retour au BASIC
___x07_exit::
        ld      sp, (x07_sp)
        pop     iy
        pop     ix
        pop     hl
        pop     de
        pop     bc
        pop     af
        ret
x07_sp:
        .dw     0                       ; dans le code : la remise à zéro l'épargne

        ;; ordre des zones : le code, puis les données, puis le tas
        .area   _HOME
        .area   _CODE
        .area   _INITIALIZER
        .area   _GSINIT
        .area   _GSFINAL
        .area   _DATA
        .area   _INITIALIZED
        .area   _BSEG
        .area   _BSS
        .area   _HEAP
        .area   _HEAP_END

        .area   _GSINIT
gsinit::
        ld      bc, #l__DATA            ; variables sans valeur initiale : 0
        ld      a, b
        or      a, c
        jr      Z, zeroed
        ld      hl, #s__DATA
        ld      (hl), #0x00
        dec     bc
        ld      a, b
        or      a, c
        jr      Z, zeroed
        ld      e, l
        ld      d, h
        inc     de
        ldir
zeroed:
        ld      bc, #l__INITIALIZER     ; variables initialisées : leur valeur
        ld      a, b
        or      a, c
        jr      Z, gsinit_next
        ld      de, #s__INITIALIZED
        ld      hl, #s__INITIALIZER
        ldir
gsinit_next:

        .area   _GSFINAL
        ret
