; Compte les interruptions INT A (T6834 : clavier) pendant qu'une boucle tourne.
; Chargement : CLEAR 50,&H1BFF  puis  EXEC &H1C00
; Chaque touche affiche le nombre d'interruptions et le compteur de la boucle
; (32 bits, en hexadécimal) ; RETURN rend la main au BASIC.
;
; Adapté d'un programme Z80 en IM 2 ; sur le X-07 :
; - la RAM va de $0000 à $3FFF (16 Ko) : pas de code en $8000, pas de pile
;   en $BFFF (c'est la ROM) ; on garde la pile du BASIC ;
; - le NSC800 reçoit les interruptions sur RST A, B et C, aux vecteurs fixes
;   $003C (INT A, T6834), $0034 (INT B, série et BEEP) et $002C (INT C) :
;   pas d'IM 2 ni de registre I. Les vecteurs sont des JP en RAM ; on détourne
;   celui de INT A, puis on enchaîne sur la routine de la ROM, qui lit la
;   touche et acquitte le T6834 ;
; - cette routine ($C799) commence par EXX / EX AF,AF' : les registres
;   alternatifs sont à elle. Le gestionnaire sauve donc AF et HL par la pile.

        ORG  $1C00

START:  DI
        LD   HL,(INTA+1)        ; adresse du JP de INT A (JP $C799)
        LD   (CHAIN+1),HL       ; notre gestionnaire y enchaînera
        LD   HL,IRQ_HANDLER
        LD   (INTA+1),HL
        LD   HL,0
        LD   (IRQ_COUNTER),HL
        EI

        CALL LCDCLS
        LD   HL,TITRE
        CALL PRTMSG

        LD   DE,0               ; compteur principal DE:HL, sur 32 bits
        LD   HL,0               ; (7 instructions par tour : sur 16 bits,
                                ; il ferait le tour en moins d'une seconde)
        LD   B,0                ; poids faible du nombre d'interruptions vu

MAIN_LOOP:
        INC  HL                 ; compteur principal
        LD   A,H
        OR   L
        JR   NZ,.VU
        INC  DE
.VU:    LD   A,(IRQ_COUNTER)    ; une interruption depuis le dernier tour ?
        CP   B
        JR   Z,MAIN_LOOP
        LD   B,A
        LD   (TOURS),HL
        LD   (TOURS+2),DE
        PUSH BC
        PUSH DE
        PUSH HL
        XOR  A
        CALL INKEY              ; la touche, rangée par la ROM ; Z=1 si aucune
        JR   Z,.SUITE           ; (interruption sans touche)
        CP   $0D
        JR   Z,FIN              ; RETURN : terminé
        CALL AFFICHE
.SUITE: POP  HL
        POP  DE
        POP  BC
        JR   MAIN_LOOP

FIN:    POP  HL
        POP  DE
        POP  BC
        CALL AFFICHE
        DI                      ; vecteur d'origine remis
        LD   HL,(CHAIN+1)
        LD   (INTA+1),HL
        EI
        RET                     ; retour au BASIC


; ======================================
; ROUTINE D'INTERRUPTION (INT A)
; ======================================

IRQ_HANDLER:
        PUSH AF
        PUSH HL
        LD   HL,(IRQ_COUNTER)
        INC  HL
        LD   (IRQ_COUNTER),HL
        POP  HL
        POP  AF
CHAIN:  JP   $C799              ; routine de la ROM (adresse recopiée au départ) :
                                ; elle se termine par EI / RET


; ======================================
; AFFICHAGE
; ======================================

AFFICHE:
        LD   HL,$0102           ; colonne 1 ($00B9), ligne 2 ($00B8)
        LD   (CSRY),HL
        LD   HL,MSG_IRQ
        CALL PRTMSG
        LD   HL,(IRQ_COUNTER)
        CALL PRTHL              ; en décimal
        LD   HL,$0103
        LD   (CSRY),HL
        LD   HL,MSG_TOURS
        CALL PRTMSG
        LD   A,(TOURS+3)
        CALL HEXA
        LD   A,(TOURS+2)
        CALL HEXA
        LD   A,(TOURS+1)
        CALL HEXA
        LD   A,(TOURS)
HEXA:   PUSH AF                 ; A en deux chiffres hexadécimaux
        RRCA
        RRCA
        RRCA
        RRCA
        CALL .CHIFFRE
        POP  AF
.CHIFFRE:
        AND  $0F
        ADD  A,$90
        DAA
        ADC  A,$40
        DAA
        JP   LCDPUT


; ======================================
; DONNÉES
; ======================================

INTA        EQU  $003C          ; vecteur de INT A : C3 99 C7 (JP $C799)
CSRY        EQU  $00B8          ; ligne du curseur, puis colonne en $00B9

TITRE:      DZ   "INT A : touches"
MSG_IRQ:    DZ   "INT A  "
MSG_TOURS:  DZ   "TOURS $"
IRQ_COUNTER: DW  0
TOURS:      DS   4              ; compteur principal à la dernière touche
