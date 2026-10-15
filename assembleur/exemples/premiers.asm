; PREMIERS - compilé par x07basic (BASIC entier pour Canon X-07)
; Chargement : CLEAR 50,&H3A3F  puis  EXEC &H3A40

STRCAP  EQU  80               ; capacité des chaînes

; Canon X-07 : routines de la ROM (« Les mystères du X-07 »)
LCDPUT   EQU  $C1BE  ; écrit A à l'écran (codes de contrôle admis)
LCDCLS   EQU  $CE9E  ; efface l'écran (CLS)

; Canon X-07 : variables système (« Les mystères du X-07 »)
BRKFLG   EQU  $002B  ; BREAKFLAG
CSRX     EQU  $00B8  ; colonne du curseur

        ORG  $3A40

START:  PUSH AF                  ; sauvegarde pour le retour au BASIC
        PUSH BC
        PUSH DE
        PUSH HL
        PUSH IX
        PUSH IY
        LD   (RT_SP),SP
        LD   HL,VARS
        LD   DE,VARS+1
        LD   BC,VARS_END-VARS-1
        LD   (HL),0
        LDIR                     ; variables à zéro

; 10 REM NOMBRES PREMIERS (CRIBLE D'ERATOSTHENE)

; 20 DIM P(500)

; 30 CLS:FOR I=2 TO 500
        CALL LCDCLS
        LD   HL,2
        LD   (V_I),HL
G_1:

; 40 IF P(I) THEN 70
        LD   HL,(V_I)
        LD   DE,501
        CALL RT_CHK
        ADD  HL,HL
        LD   DE,AV_P
        ADD  HL,DE
        LD   A,(HL)
        INC  HL
        LD   H,(HL)
        LD   L,A
        LD   A,H
        OR   L
        JP   Z,G_2
        JP   LN_70
G_2:

; 50 PRINT I;
        LD   HL,(V_I)
        CALL RT_PRN

; 60 IF I<23 THEN FOR J=I*I TO 500 STEP I:P(J)=1:NEXT J
        LD   HL,(V_I)
        EX   DE,HL
        LD   HL,23
        CALL RT_ICMP
        CALL RT_FLT
        LD   A,H
        OR   L
        JP   Z,G_4
        LD   HL,(V_I)
        EX   DE,HL
        LD   HL,(V_I)
        CALL RT_MUL
        LD   (V_J),HL
        LD   HL,(V_I)
        LD   (G_6_S),HL
G_6:
        LD   HL,1
        PUSH HL
        LD   HL,(V_J)
        LD   DE,501
        CALL RT_CHK
        ADD  HL,HL
        LD   DE,AV_P
        ADD  HL,DE
        POP  DE
        LD   (HL),E
        INC  HL
        LD   (HL),D
        CALL RT_BRK
        LD   HL,(V_J)
        LD   DE,(G_6_S)
        OR   A
        ADC  HL,DE
        JP   PE,G_6_X
        LD   (V_J),HL
        LD   A,(G_6_S+1)
        RLA
        JR   C,G_7
        LD   DE,500
        CALL RT_ICMP
        JP   NC,G_6
        JP   G_6_X
G_7:
        EX   DE,HL
        LD   HL,500
        CALL RT_ICMP
        JP   NC,G_6
G_6_X:
G_4:

; 70 NEXT I
LN_70:
        CALL RT_BRK
        LD   HL,(V_I)
        LD   DE,1
        OR   A
        ADC  HL,DE
        JP   PE,G_1_X
        LD   (V_I),HL
        LD   DE,500
        CALL RT_ICMP
        JP   NC,G_1
G_1_X:

        JP   RT_END

; ------------------------------------------------ bibliothèque

RT_END:
        LD   SP,(RT_SP)
        POP  IY
        POP  IX
        POP  HL
        POP  DE
        POP  BC
        POP  AF
        RET                     ; retour au BASIC (EXEC)

RT_ERR:                         ; HL = message ; affiche ?message et s'arrête
        PUSH HL
        LD   A,(CSRX)
        OR   A
        CALL NZ,RT_NL            ; à la ligne si le curseur n'y est pas
        LD   A,'?'
        CALL LCDPUT
        POP  HL
        CALL RT_PRS
        CALL RT_NL
        JP   RT_END

MSG_IDX:    DB 6,"INDICE"

MSG_BRK:    DB 5,"BREAK"

RT_BRK:                         ; touche BREAK -> arrêt (BREAKFLAG bit 0)
        LD   A,(BRKFLG)
        RRCA
        RET  NC
        LD   A,(BRKFLG)
        AND  $FE
        LD   (BRKFLG),A
        LD   HL,MSG_BRK
        JP   RT_ERR

RT_NEG:                         ; HL = -HL
        XOR  A
        SUB  L
        LD   L,A
        LD   A,0
        SBC  A,H
        LD   H,A
        RET

RT_MUL:                         ; HL = DE * HL (16 bits)
        LD   B,H
        LD   C,L
        LD   HL,0
        LD   A,16
.L:     ADD  HL,HL
        SLA  C
        RL   B
        JR   NC,.N
        ADD  HL,DE
.N:     DEC  A
        JR   NZ,.L
        RET

RT_ICMP:                        ; compare DE et HL (signés) -> C : DE<HL, Z : égaux
        LD   A,D
        XOR  $80
        LD   D,A
        LD   A,H
        XOR  $80
        LD   H,A
        LD   A,D
        CP   H
        RET  NZ
        LD   A,E
        CP   L
        RET

RT_FLT:
        LD   HL,0
        RET  NC
        DEC  HL
        RET

RT_STR:                         ; (DE) <- STR$(HL)
        PUSH DE
        INC  DE
        LD   A,' '
        BIT  7,H
        JR   Z,.P
        CALL RT_NEG
        LD   A,'-'
.P:     LD   (DE),A
        INC  DE
        XOR  A
        LD   (RT_NZ),A
        LD   BC,10000
        CALL .D
        LD   BC,1000
        CALL .D
        LD   BC,100
        CALL .D
        LD   BC,10
        CALL .D
        LD   A,L
        ADD  A,'0'
        LD   (DE),A
        INC  DE
        POP  HL
        LD   A,E
        SUB  L
        DEC  A
        LD   (HL),A
        RET
.D:     LD   A,'0'-1
.DL:    INC  A
        OR   A
        SBC  HL,BC
        JR   NC,.DL
        ADD  HL,BC
        CP   '0'
        JR   NZ,.W
        LD   A,(RT_NZ)
        OR   A
        RET  Z
        LD   A,'0'
.W:     LD   (DE),A
        INC  DE
        LD   A,1
        LD   (RT_NZ),A
        RET

RT_PRS:                         ; affiche la chaîne (HL)
        LD   B,(HL)
        INC  B
.L:     DEC  B
        RET  Z
        INC  HL
        LD   A,(HL)
        CALL LCDPUT
        JR   .L

RT_PRN:                         ; affiche HL comme PRINT (espace avant et après)
        LD   DE,RT_NBUF
        CALL RT_STR
        LD   HL,RT_NBUF
        CALL RT_PRS
        LD   A,' '
        JP   LCDPUT

RT_NL:                          ; retour à la ligne
        LD   A,13
        CALL LCDPUT
        LD   A,10
        JP   LCDPUT

RT_CHK:                         ; erreur si HL >= DE (non signés)
        PUSH HL
        OR   A
        SBC  HL,DE
        POP  HL
        RET  C
        LD   HL,MSG_IDX
        JP   RT_ERR

RT_SP:   DW   0

; ------------------------------------------------ variables (non chargées)
VARS:
AV_P:        DS   1002
G_6_S:       DS   2
V_I:         DS   2
V_J:         DS   2
RT_NZ:       DS   1
RT_NBUF:     DS   8
             DS   2
VARS_END:

        END  START
