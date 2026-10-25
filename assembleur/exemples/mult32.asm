        ORG     $19D0

; Multiplication non signee 16 x 16 -> 32 bits
; Convention des octets : poids faible en premier
;
; ENTREE :
;   MULT1  = 2 octets
;   MULT2  = 2 octets
;
; SORTIE :
;   PROD   = 4 octets
;
; Variables a placer dans une zone RAM libre.

        LD      HL,(MULT1)
        LD      (M0),HL
        LD      HL,0
        LD      (M2),HL

        LD      HL,0
        LD      (P0),HL
        LD      (P2),HL

        LD      BC,(MULT2)
        LD      A,B
        OR      C
        JR      Z,FIN

        LD      A,16
        LD      (COMPTE),A

BOUCLE:
        ; Tester le bit de poids faible du multiplicateur
        BIT     0,C
        JR      Z,DECALER

        ; PROD = PROD + M (32 bits)
        LD      HL,(P0)
        LD      DE,(M0)
        ADD     HL,DE
        LD      (P0),HL

        LD      HL,(P2)
        LD      DE,(M2)
        ADC     HL,DE
        LD      (P2),HL

DECALER:
        ; Multiplicateur 16 bits : decalage a droite
        SRL     B
        RR      C

        ; Multiplicande 32 bits : decalage a gauche
        LD      HL,M0
        SLA     (HL)
        INC     HL
        RL      (HL)
        INC     HL
        RL      (HL)
        INC     HL
        RL      (HL)

        LD      A,(COMPTE)
        DEC     A
        LD      (COMPTE),A
        JR      NZ,BOUCLE

FIN:
        RET

; Variables
MULT1:  DEFW    1234
MULT2:  DEFW    5678

M0:     DEFW    0
M2:     DEFW    0
P0:     DEFW    0
P2:     DEFW    0
COMPTE: DEFB    0

