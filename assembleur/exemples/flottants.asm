; FLOTTANTS - compilé par x07basic (BASIC du Canon X-07)
; Chargement : CLEAR 50,&H1CEF  puis  EXEC &H1CF0

STRCAP  EQU  80               ; capacité des chaînes

; Canon X-07 : routines de la ROM
FATN     EQU  $B5AC  ; ATN (vérifié ROM)
FSQR     EQU  $B694  ; SQR (vérifié ROM)
FOUT     EQU  $BBAB  ; FAC -> texte libre, HL = début, fin 00 (vérifié ROM)
BATTMSG  EQU  $C06C  ; messages piles faibles (BREAKFLAG bits 1 et 3) (vérifié ROM)
T6FLUSH  EQU  $C0BD  ; vide les tampons clavier et T6834
CHKBATT  EQU  $C5A6  ; si BREAKFLAG bit 7 (OFF) : éteint la machine (vérifié ROM)
INKEY    EQU  $C90A  ; lit une touche (INKEY$) -> A ; Z=1 si aucune (vérifié ROM)
DCMP     EQU  $CAD9  ; compare acc et acc2 (double)
HL2FAC   EQU  $CAEF  ; HL -> accumulateur (entier)
FCSNG    EQU  $CB08  ; accumulateur -> simple précision (CSNG)
FCDBL    EQU  $CB90  ; accumulateur -> double précision (CDBL)
LCDCLS   EQU  $CE9E  ; efface l'écran (CLS)
DEVPOS   EQU  $E8EE  ; position (A) et largeur (B) du périphérique courant (vérifié ROM)
CRLF     EQU  $E929  ; envoie CR LF au périphérique courant (vérifié ROM)
ERRTAB   EQU  $F123  ; codes d'erreur sur 2 lettres : NF SN RG OD FC OV... (vérifié ROM)
FOPDISP  EQU  $F9E4  ; répartiteur des opérateurs + - * / ^ (pile : opérande gauche, BC = type/op) (vérifié ROM)

; Canon X-07 : variables système
BRKFLG   EQU  $002B  ; BREAKFLAG
HKERROR  EQU  $00AB  ; hook ERREUR
CSRX     EQU  $00B9  ; colonne du curseur, à partir de 1 (vérifié ROM)
VALTYP   EQU  $01D9  ; type de donnée (2,3,4,8)
FAC      EQU  $044E  ; accumulateur flottant
FACINT   EQU  $0450  ; entier dans l'accumulateur
ARG      EQU  $049F  ; accumulateur 2

        ORG  $1CF0

START:  PUSH AF                  ; sauvegarde pour le retour au BASIC
        PUSH BC
        PUSH DE
        PUSH HL
        PUSH IX
        PUSH IY
        LD   (RT_SP),SP
        LD   HL,(HKERROR)        ; détourne le crochet d'erreur de la ROM
        LD   (RT_HSAV),HL
        LD   A,(HKERROR+2)
        LD   (RT_HSAV+2),A
        LD   A,$C3               ; JP RT_FERR
        LD   (HKERROR),A
        LD   HL,RT_FERR
        LD   (HKERROR+1),HL
        LD   HL,VARS
        LD   DE,VARS+1
        LD   BC,VARS_END-VARS-1
        LD   (HL),0
        LDIR                     ; variables à zéro

; 10 REM CALCULS EN VIRGULE FLOTTANTE (DOUBLE PRECISION PAR DEFAUT, COMME LE X-07)

; 20 CLS:PRINT "PI=";4*ATN(1)
        CALL LCDCLS
        LD   HL,LIT_1
        CALL RT_PRS
        LD   HL,G_1
        PUSH HL
        LD   HL,4
        CALL HL2FAC
        LD   C,2
        CALL RT_FPUSHL
        LD   HL,1
        CALL HL2FAC
        CALL FCDBL
        CALL FATN
        JP   FOPDISP
G_1:
        CALL RT_PRNUM
        CALL CRLF

; 30 PRINT "RACINE 2=";SQR(2)
        LD   HL,LIT_2
        CALL RT_PRS
        LD   HL,2
        CALL HL2FAC
        CALL FCDBL
        CALL FSQR
        CALL RT_PRNUM
        CALL CRLF

; 40 A!=1/3:PRINT "1/3 SIMPLE=";A!
        LD   HL,G_2
        PUSH HL
        LD   HL,1
        CALL HL2FAC
        LD   C,3
        CALL RT_FPUSHL
        LD   HL,3
        CALL HL2FAC
        JP   FOPDISP
G_2:
        CALL FCSNG
        LD   HL,V_A_F
        CALL RT_STF4
        LD   HL,LIT_3
        CALL RT_PRS
        LD   HL,V_A_F
        CALL RT_LDF4
        CALL RT_PRNUM
        CALL CRLF

; 50 S=0:FOR I=1 TO 10:S=S+1/I:NEXT
        LD   HL,0
        CALL HL2FAC
        CALL FCDBL
        LD   HL,V_S_D
        CALL RT_STF8
        LD   HL,1
        CALL HL2FAC
        CALL FCDBL
        LD   HL,V_I_D
        CALL RT_STF8
        LD   HL,10
        CALL HL2FAC
        CALL FCDBL
        LD   HL,G_3_L
        CALL RT_STF8
        LD   HL,1
        CALL HL2FAC
        CALL FCDBL
        LD   HL,G_3_S
        CALL RT_STF8
G_3:
        LD   HL,G_4
        PUSH HL
        LD   HL,V_S_D
        CALL RT_LDF8
        LD   C,0
        CALL RT_FPUSHL
        LD   HL,G_5
        PUSH HL
        LD   HL,1
        CALL HL2FAC
        LD   C,3
        CALL RT_FPUSHL
        LD   HL,V_I_D
        CALL RT_LDF8
        JP   FOPDISP
G_5:
        JP   FOPDISP
G_4:
        CALL FCDBL
        LD   HL,V_S_D
        CALL RT_STF8
        CALL RT_BRK
        LD   HL,G_6
        PUSH HL
        LD   HL,V_I_D
        CALL RT_LDF8
        LD   C,0
        CALL RT_FPUSHL
        LD   HL,G_3_S
        CALL RT_LDF8
        JP   FOPDISP
G_6:
        CALL FCDBL
        LD   HL,V_I_D
        CALL RT_STF8
        LD   HL,V_I_D
        CALL RT_LDF8
        CALL FCDBL
        CALL RT_FPUSH8
        LD   HL,G_3_L
        CALL RT_LDF8
        CALL FCDBL
        CALL RT_FPOPARG
        CALL DCMP
        CP   $FF
        JP   NZ,G_3
G_3_X:

; 60 PRINT "H10=";S
        LD   HL,LIT_4
        CALL RT_PRS
        LD   HL,V_S_D
        CALL RT_LDF8
        CALL RT_PRNUM
        CALL CRLF

        JP   RT_END

; ------------------------------------------------ bibliothèque

RT_END:
        LD   HL,(RT_HSAV)       ; rétablit le crochet d'erreur ($00AB)
        LD   (HKERROR),HL
        LD   A,(RT_HSAV+2)
        LD   (HKERROR+2),A
        LD   SP,(RT_SP)
        POP  IY
        POP  IX
        POP  HL
        POP  DE
        POP  BC
        POP  AF
        RET                     ; retour au BASIC (EXEC)

RT_FERR:                        ; erreur numéro E (crochet $00AB de la ROM ou bibliothèque)
        LD   A,(CSRX)
        DEC  A
        CALL NZ,CRLF            ; à la ligne si le curseur n'est pas en colonne 1
        LD   A,E
        DEC  A
        ADD  A,A
        LD   L,A
        LD   H,0
        LD   DE,ERRTAB          ; codes sur deux lettres, comme le X-07
        ADD  HL,DE
        LD   A,(HL)
        RST  $28
        INC  HL
        LD   A,(HL)
        RST  $28
        LD   HL,MSG_ERR
        CALL RT_PRS
        CALL CRLF
        JP   RT_END

RT_BREAK:                       ; arrêt par BREAK : « Break », comme le X-07
        LD   A,(CSRX)
        DEC  A
        CALL NZ,CRLF
        LD   HL,MSG_BRK
        CALL RT_PRS
        CALL CRLF
        JP   RT_END

MSG_ERR:    DB 6," Error"

MSG_BRK:    DB 5,"Break"

RT_BRK:                         ; comme l'interpréteur ($C000) : OFF, pause, piles, BREAK
        LD   A,(BRKFLG)
        OR   A
        RET  Z                  ; cas courant : rien à faire
        PUSH HL
        PUSH DE
        PUSH BC
        CALL CHKBATT            ; bit 7 : extinction demandée
        BIT  2,A                ; bit 2 : pause jusqu'à une touche
        JR   Z,.P
        RES  2,A
        LD   (BRKFLG),A
        CALL T6FLUSH
.W:     CALL INKEY
        JR   NZ,.P
        LD   A,(BRKFLG)
        OR   A
        JR   Z,.W
.P:     CALL BATTMSG            ; bits 1 et 3 : piles faibles
        LD   A,(BRKFLG)
        RRCA                    ; bit 0 : BREAK
        JR   C,.B
        POP  BC
        POP  DE
        POP  HL
        RET
.B:     LD   A,(BRKFLG)
        AND  $FA
        LD   (BRKFLG),A
        CALL T6FLUSH
        JP   RT_BREAK

RT_PRS:                         ; affiche la chaîne (HL) sur le périphérique courant
        LD   B,(HL)
        INC  B
.L:     DEC  B
        RET  Z
        INC  HL
        LD   A,(HL)
        RST  $28
        JR   .L

RT_PRNUM:                       ; PRINT d'un nombre (FAC), copie de la ROM ($EA2C)
        CALL FOUT               ; HL = texte terminé par 00
        PUSH HL
        LD   B,1                ; longueur + espace final
.C:     LD   A,(HL)
        OR   A
        JR   Z,.D
        INC  HL
        INC  B
        JR   .C
.D:     PUSH BC
        LD   BC,$FF00
        CALL DEVPOS             ; A = position, B = largeur
        POP  DE                 ; D = longueur
        AND  A
        JR   Z,.P
        ADD  A,D
        DEC  A
        CP   B
        CALL NC,CRLF            ; ne tient pas sur la ligne
.P:     POP  HL
.O:     LD   A,(HL)
        OR   A
        JR   Z,.S
        RST  $28
        INC  HL
        JR   .O
.S:     LD   A,' '
        RST  $28
        RET

RT_LDF4:                        ; FAC <- simple précision en (HL)
        LD   DE,FAC
        LD   BC,4
        LDIR
        LD   A,4
        LD   (VALTYP),A
        RET

RT_LDF8:                        ; FAC <- double précision en (HL)
        LD   DE,FAC
        LD   BC,8
        LDIR
        LD   A,8
        LD   (VALTYP),A
        RET

RT_STF4:                        ; (HL) <- FAC simple précision
        EX   DE,HL
        LD   HL,FAC
        LD   BC,4
        LDIR
        RET

RT_STF8:                        ; (HL) <- FAC double précision
        EX   DE,HL
        LD   HL,FAC
        LD   BC,8
        LDIR
        RET

RT_FPUSHL:                      ; empile l'opérande gauche comme l'évaluateur ($F976)
        POP  IX                 ; C = opération (0 + 1 - 2 * 3 / 4 ^)
        LD   HL,(FACINT)
        PUSH HL
        LD   A,(VALTYP)
        CP   4
        JR   C,.T
        LD   HL,(FAC)
        PUSH HL
        CP   8
        JR   NZ,.T
        LD   HL,(FAC+6)
        PUSH HL
        LD   HL,(FAC+4)
        PUSH HL
.T:     LD   B,A                ; B = type
        PUSH BC
        JP   (IX)

RT_FPUSH8:                      ; empile les 8 octets de FAC
        POP  IX
        LD   HL,(FAC+6)
        PUSH HL
        LD   HL,(FAC+4)
        PUSH HL
        LD   HL,(FAC+2)
        PUSH HL
        LD   HL,(FAC)
        PUSH HL
        JP   (IX)

RT_FPOPARG:                     ; ARG <- FAC ; FAC <- valeur dépilée (double)
        POP  IX
        LD   HL,FAC
        LD   DE,ARG
        LD   BC,8
        LDIR
        POP  HL
        LD   (FAC),HL
        POP  HL
        LD   (FAC+2),HL
        POP  HL
        LD   (FAC+4),HL
        POP  HL
        LD   (FAC+6),HL
        LD   A,8
        LD   (VALTYP),A
        JP   (IX)

; ------------------------------------------------ chaînes
LIT_1:   DB   3,"PI="
LIT_2:   DB   9,"RACINE 2="
LIT_3:   DB   11,"1/3 SIMPLE="
LIT_4:   DB   4,"H10="

RT_SP:   DW   0
RT_HSAV: DB   0,0,0

; ------------------------------------------------ variables (non chargées)
VARS:
G_3_L:         DS   8
G_3_S:         DS   8
V_A_F:         DS   4
V_I_D:         DS   8
V_S_D:         DS   8
               DS   2
VARS_END:

        END
