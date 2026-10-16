"""Bibliothèque d'exécution du compilateur BASIC (assembleur Z80).

Conventions :
  - entiers 16 bits signés ; résultat numérique dans HL ;
  - opérations binaires : opérande gauche dans DE, droit dans HL ;
  - chaîne = 1 octet de longueur + caractères, capacité STRCAP ;
  - comparaisons : RT_ICMP / RT_SCMP comparent DE (gauche) à HL (droite)
    et positionnent C (gauche < droite) et Z (égalité) ; RT_Fxx convertit
    ces indicateurs en -1 (vrai) ou 0 (faux).

Seules les routines réellement utilisées (et leurs dépendances, repérées
par les noms RT_xxx / MSG_xxx cités dans le texte) sont incluses.
Nombres non entiers : ils sont dans l'accumulateur de la ROM (FAC, $044E)
avec leur type réel en VALTYP ($01D9), exactement comme dans l'interpréteur ;
les calculs passent par les routines de la ROM (vérifiées dans ROM_x07).
Les erreurs ont le numéro et le message du X-07 (E = 6 OV, 9 BS, 11 /0...).
"""
import re

ROUTINES = {}
VARIABLES = {}       # variables internes -> taille (zone remise à zéro)


def _r(name, text):
    ROUTINES[name] = text.strip("\n")


# ------------------------------------------------------------- fin, erreurs
_r("RT_END", """
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
""")


_r("RT_FERR", """
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
        @ERRLINE@
        CALL CRLF
        JP   RT_END
""")

_r("RT_BREAK", """
RT_BREAK:                       ; arrêt par BREAK : « Break », comme le X-07
        LD   A,(CSRX)
        DEC  A
        CALL NZ,CRLF
        LD   HL,MSG_BRK
        CALL RT_PRS
        @ERRLINE@
        CALL CRLF
        JP   RT_END
""")

_r("RT_OV", """
RT_OV:                          ; dépassement de capacité
        LD   E,6
        JP   RT_FERR
""")



_r("MSG_ERR", 'MSG_ERR:    DB 6," Error"')
_r("MSG_BRK", 'MSG_BRK:    DB 5,"Break"')
_r("MSG_IN", 'MSG_IN:     DB 4," in "')

_r("RT_BRK", """
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
""")


# ------------------------------------------------------------- arithmétique
_r("RT_NEG", """
RT_NEG:                         ; HL = -HL
        XOR  A
        SUB  L
        LD   L,A
        LD   A,0
        SBC  A,H
        LD   H,A
        RET
""")

_r("RT_ABS", """
RT_ABS:
        BIT  7,H
        RET  Z
        JP   RT_NEG
""")

_r("RT_SGN", """
RT_SGN:
        LD   A,H
        OR   L
        RET  Z
        BIT  7,H
        LD   HL,1
        RET  Z
        DEC  HL
        DEC  HL
        RET
""")

_r("RT_MUL", """
RT_MUL:                         ; HL = DE * HL (signés), OV si dépassement
        LD   A,D
        XOR  H
        PUSH AF                 ; signe du résultat
        CALL RT_ABS
        EX   DE,HL
        CALL RT_ABS             ; HL, DE = valeurs absolues
        LD   A,H
        OR   A
        JR   Z,.S
        LD   A,D
        OR   A
        JP   NZ,RT_OV           ; les deux >= 256
        EX   DE,HL
.S:     LD   A,L                ; A = petit facteur, DE = grand
        LD   HL,0
        LD   B,8
.M:     ADD  HL,HL
        JP   C,RT_OV
        RLA
        JR   NC,.N
        ADD  HL,DE
        JP   C,RT_OV
.N:     DJNZ .M
        POP  AF
        JP   P,.P
        LD   A,H                ; négatif : au plus 32768
        CP   $80
        JP   C,RT_NEG
        JP   NZ,RT_OV
        LD   A,L
        OR   A
        JP   NZ,RT_OV
        RET
.P:     BIT  7,H
        RET  Z
        JP   RT_OV
""")

_r("RT_INEG", """
RT_INEG:                        ; HL = -HL, OV pour -32768
        LD   A,H
        CP   $80
        JP   NZ,RT_NEG
        LD   A,L
        OR   A
        JP   Z,RT_OV
        JP   RT_NEG
""")

_r("RT_IABS", """
RT_IABS:                        ; ABS entier, OV pour -32768
        BIT  7,H
        RET  Z
        JP   RT_INEG
""")


_r("RT_UDIV", """
RT_UDIV:                        ; HL / DE non signés -> HL quotient, DE reste
        LD   B,H
        LD   C,L
        LD   HL,0
        LD   A,16
.L:     SLA  C
        RL   B
        ADC  HL,HL
        OR   A
        SBC  HL,DE
        JR   NC,.K
        ADD  HL,DE
        JR   .N
.K:     INC  C
.N:     DEC  A
        JR   NZ,.L
        EX   DE,HL
        LD   H,B
        LD   L,C
        RET
""")

_r("RT_DIVMOD", """
RT_DIVMOD:                      ; DE / HL signés -> HL quotient, DE reste
        LD   A,H
        OR   L
        JR   NZ,.OK
        LD   E,11               ; /0
        JP   RT_FERR
.OK:    LD   A,D
        XOR  H
        LD   B,A                ; bit 7 : signe du quotient
        LD   C,D                ; bit 7 : signe du reste
        PUSH BC
        CALL RT_ABS
        EX   DE,HL
        CALL RT_ABS
        CALL RT_UDIV
        POP  BC
        BIT  7,C
        JR   Z,.R
        EX   DE,HL
        CALL RT_NEG
        EX   DE,HL
.R:     BIT  7,B
        RET  Z
        JP   RT_NEG
""")

_r("RT_DIV", """
RT_DIV:                         ; HL = DE \\ HL (troncature)
        JP   RT_DIVMOD
""")

_r("RT_MOD", """
RT_MOD:                         ; HL = DE MOD HL (signe du dividende)
        CALL RT_DIVMOD
        EX   DE,HL
        RET
""")

# ------------------------------------------------------------- comparaisons
_r("RT_ICMP", """
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
""")

_r("RT_FEQ", """
RT_FEQ:
        LD   HL,0
        RET  NZ
        DEC  HL
        RET
""")
_r("RT_FNE", """
RT_FNE:
        LD   HL,0
        RET  Z
        DEC  HL
        RET
""")
_r("RT_FLT", """
RT_FLT:
        LD   HL,0
        RET  NC
        DEC  HL
        RET
""")
_r("RT_FGE", """
RT_FGE:
        LD   HL,0
        RET  C
        DEC  HL
        RET
""")

# ------------------------------------------------------------- chaînes
_r("RT_SCOPY", """
RT_SCOPY:                       ; (HL) <- (DE), tronquée à STRCAP
        LD   A,(DE)
        CP   STRCAP+1
        JR   C,.K
        LD   A,STRCAP
.K:     LD   (HL),A
        OR   A
        RET  Z
        LD   C,A
        LD   B,0
        INC  HL
        INC  DE
        EX   DE,HL
        LDIR
        RET
""")

_r("RT_SCAT", """
RT_SCAT:                        ; (HL) <- (HL) + (DE), tronquée à STRCAP
        LD   A,(DE)
        OR   A
        RET  Z
        LD   B,A
        LD   A,(HL)
        LD   C,A
        ADD  A,B
        JR   C,.T
        CP   STRCAP+1
        JR   C,.K
.T:     LD   A,STRCAP
.K:     LD   (HL),A
        SUB  C
        RET  Z
        LD   B,0
        INC  HL
        ADD  HL,BC
        EX   DE,HL
        INC  HL
        LD   C,A
        LD   B,0
        LDIR
        RET
""")

_r("RT_SCMP", """
RT_SCMP:                        ; compare les chaînes (DE) et (HL)
        LD   A,(DE)
        LD   B,A
        LD   C,(HL)
.L:     LD   A,B
        OR   A
        JR   Z,.E
        LD   A,C
        OR   A
        JR   Z,.G
        INC  DE
        INC  HL
        LD   A,(DE)
        CP   (HL)
        RET  NZ
        DEC  B
        DEC  C
        JR   .L
.E:     LD   A,C
        OR   A
        RET  Z
        SCF
        RET
.G:     LD   A,1
        OR   A
        RET
""")

_r("RT_LEFT", """
RT_LEFT:                        ; (DE) <- LEFT$((DE),HL)
        BIT  7,H
        JR   Z,.P
        LD   HL,0
.P:     LD   A,H
        OR   A
        RET  NZ
        LD   A,(DE)
        CP   L
        RET  C
        LD   A,L
        LD   (DE),A
        RET
""")

_r("RT_RIGHT", """
RT_RIGHT:                       ; (DE) <- RIGHT$((DE),HL)
        BIT  7,H
        JR   Z,.P
        LD   HL,0
.P:     LD   A,H
        OR   A
        RET  NZ
        LD   A,(DE)
        CP   L
        RET  C
        RET  Z
        SUB  L
        EX   DE,HL
        LD   (HL),E
        INC  HL
        PUSH HL
        LD   C,A
        LD   B,0
        ADD  HL,BC
        LD   C,E
        POP  DE
        LD   A,C
        OR   A
        RET  Z
        LDIR
        RET
""")

_r("RT_MID", """
RT_MID:                         ; (DE) <- MID$((DE),BC,HL)
        BIT  7,H
        JR   Z,.N1
        LD   HL,0
.N1:    LD   A,H
        OR   A
        JR   Z,.N2
        LD   L,255
.N2:    BIT  7,B
        JR   Z,.P1
        LD   BC,1
.P1:    LD   A,B
        OR   A
        JR   NZ,.V
        LD   A,C
        OR   A
        JR   NZ,.P2
        INC  C
.P2:    LD   A,(DE)
        CP   C
        JR   C,.V
        SUB  C
        INC  A
        CP   L
        JR   NC,.P3
        LD   L,A
.P3:    LD   A,L
        LD   (DE),A
        OR   A
        RET  Z
        PUSH AF
        LD   H,D
        LD   L,E
        LD   B,0
        ADD  HL,BC
        INC  DE
        POP  AF
        LD   C,A
        LD   B,0
        LDIR
        RET
.V:     XOR  A
        LD   (DE),A
        RET
""")

_r("RT_HEX", """
RT_HEX:                         ; (DE) <- HEX$(HL)
        PUSH DE
        INC  DE
        LD   B,4
        LD   C,0
.L:     XOR  A
        ADD  HL,HL
        RLA
        ADD  HL,HL
        RLA
        ADD  HL,HL
        RLA
        ADD  HL,HL
        RLA
        OR   A
        JR   NZ,.D
        BIT  0,C
        JR   NZ,.D
        LD   A,B
        CP   1
        JR   NZ,.X
        XOR  A
.D:     LD   C,1
        ADD  A,'0'
        CP   '9'+1
        JR   C,.W
        ADD  A,7
.W:     LD   (DE),A
        INC  DE
.X:     DJNZ .L
        POP  HL
        LD   A,E
        SUB  L
        DEC  A
        LD   (HL),A
        RET
""")

_r("RT_STRING", """
RT_STRING:                      ; (DE) <- STRING$(HL,A)
        BIT  7,H
        JR   Z,.P
        LD   HL,0
.P:     LD   B,A
        LD   A,H
        OR   A
        JR   NZ,.C
        LD   A,L
        CP   STRCAP+1
        JR   C,.K
.C:     LD   A,STRCAP
.K:     LD   (DE),A
        OR   A
        RET  Z
        LD   C,A
        LD   A,B
.L:     INC  DE
        LD   (DE),A
        DEC  C
        JR   NZ,.L
        RET
""")

_r("RT_INKEY", """
RT_INKEY:                       ; (HL) <- INKEY$
        PUSH HL
        XOR  A
        CALL INKEY
        POP  HL
        JR   Z,.N
        LD   (HL),1
        INC  HL
        LD   (HL),A
        RET
.N:     LD   (HL),0
        RET
""")

# ------------------------------------------------------------- affichage
_r("RT_PRS", """
RT_PRS:                         ; affiche la chaîne (HL) sur le périphérique courant
        LD   B,(HL)
        INC  B
.L:     DEC  B
        RET  Z
        INC  HL
        LD   A,(HL)
        RST  $28
        JR   .L
""")


_r("RT_NL", """
RT_NL:                          ; retour à la ligne (CR LF de la ROM)
        JP   CRLF
""")


_r("RT_COMMA", """
RT_COMMA:                       ; virgule de PRINT, copie de la ROM ($EA4D) : zones de 14
        LD   BC,0
        CALL DEVPOS             ; A = position, B = largeur
        PUSH AF
        LD   A,B
        AND  A
        JR   Z,.T
.M:     SUB  14
        JR   NC,.M
        ADD  A,28
        NEG
        ADD  A,B
        LD   C,A                ; début de la dernière zone complète
        POP  AF
        CP   C
        JP   NC,CRLF
.S:     SUB  14
        JR   NC,.S
        CPL
        INC  A
        RET  Z
        LD   B,A
        LD   A,' '
.L:     RST  $28
        DJNZ .L
        RET
.T:     LD   A,9
        RST  $28
        POP  AF
        RET
""")



_r("RT_TAB", """
RT_TAB:                         ; TAB(HL), copie de la ROM ($EA81)
        LD   A,H
        OR   A
        JR   Z,.K
        LD   L,255
.K:     LD   E,L
        LD   BC,$FFFF
        CALL DEVPOS             ; C = position, B = largeur
        DEC  B
        LD   A,B
        CP   E
        JR   NC,.D
        LD   E,B                ; au plus largeur-1
.D:     LD   L,0
        RST  $38                ; fonction $8F du périphérique : se placer en colonne E
        DB   $8F                ; (l'écran déplace le curseur et rend L<>0)
        LD   A,L
        AND  A
        RET  NZ
        LD   A,C                ; sinon : espaces jusqu'à la colonne E
        CPL
        ADD  A,E
        JR   C,.S
        LD   A,13
        RST  $28
        LD   A,E
        DEC  A
.S:     INC  A
        RET  Z
        LD   B,A
        LD   A,' '
.L:     RST  $28
        DJNZ .L
        RET
""")



_r("RT_SPC", """
RT_SPC:                         ; SPC(HL) (extension : absent du BASIC du X-07)
        LD   A,H
        OR   A
        RET  NZ
        LD   B,L
        INC  B
.L:     DEC  B
        RET  Z
        LD   A,' '
        RST  $28
        JR   .L
""")


# ------------------------------------------------------------- tableaux, ON
_r("RT_CHK", """
RT_CHK:                         ; erreur si HL >= DE (non signés)
        PUSH HL
        OR   A
        SBC  HL,DE
        POP  HL
        RET  C
        LD   E,9                ; BS : indice hors du tableau
        JP   RT_FERR
""")

_r("RT_ONSEL", """
RT_ONSEL:                       ; HL = rang, DE = table (n, adresses) -> HL = cible ou 0
        LD   A,H
        OR   A
        JR   NZ,.N
        LD   A,L
        OR   A
        JR   Z,.N
        EX   DE,HL
        LD   A,(HL)
        CP   E
        JR   C,.N
        INC  HL
        LD   D,0
        DEC  E
        ADD  HL,DE
        ADD  HL,DE
        LD   A,(HL)
        INC  HL
        LD   H,(HL)
        LD   L,A
        RET
.N:     LD   HL,0
        RET
""")

_r("RT_JPHL", """
RT_JPHL:                        ; EXEC adresse
        JP   (HL)
""")

# ------------------------------------------------------------- nombres (ROM)
_r("RT_PRNUM", """
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
""")

_r("RT_STRX", """
RT_STRX:                        ; (DE) <- STR$(FAC)
        PUSH DE
        CALL FOUT
        POP  DE
        PUSH DE
        INC  DE
        LD   B,0
.L:     LD   A,(HL)
        OR   A
        JR   Z,.E
        LD   (DE),A
        INC  HL
        INC  DE
        INC  B
        JR   .L
.E:     POP  HL
        LD   (HL),B
        RET
""")

_r("RT_ZSTR", """
RT_ZSTR:                        ; RT_FBUF <- chaîne (HL), terminée par 00 ; HL = RT_FBUF
        LD   A,(HL)
        CP   63
        JR   C,.K
        LD   A,63
.K:     LD   C,A
        LD   B,0
        INC  HL
        LD   DE,RT_FBUF
        OR   A
        JR   Z,.Z
        LDIR
.Z:     XOR  A
        LD   (DE),A
        LD   HL,RT_FBUF
.S:     LD   A,(HL)             ; espaces de tête
        CP   ' '
        RET  NZ
        INC  HL
        JR   .S
""")

_r("RT_VALX", """
RT_VALX:                        ; FAC = VAL((HL))
        CALL RT_ZSTR
        JP   FIN
""")

_r("RT_LDF4", """
RT_LDF4:                        ; FAC <- simple précision en (HL)
        LD   DE,FAC
        LD   BC,4
        LDIR
        LD   A,4
        LD   (VALTYP),A
        RET
""")

_r("RT_LDF8", """
RT_LDF8:                        ; FAC <- double précision en (HL)
        LD   DE,FAC
        LD   BC,8
        LDIR
        LD   A,8
        LD   (VALTYP),A
        RET
""")

_r("RT_STF4", """
RT_STF4:                        ; (HL) <- FAC simple précision
        EX   DE,HL
        LD   HL,FAC
        LD   BC,4
        LDIR
        RET
""")

_r("RT_STF8", """
RT_STF8:                        ; (HL) <- FAC double précision
        EX   DE,HL
        LD   HL,FAC
        LD   BC,8
        LDIR
        RET
""")

_r("RT_FPUSHL", """
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
""")

_r("RT_FPUSH8", """
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
""")

_r("RT_FPOPARG", """
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
""")

_r("RT_INFLD", """
RT_INFLD:                       ; champ suivant de la saisie -> RT_FBUF (00) ; HL = RT_FBUF
        LD   HL,(RT_IP)
        LD   A,(RT_IC)
        LD   C,A
        LD   DE,RT_FBUF
        LD   B,63
.S:     LD   A,C
        OR   A
        JR   Z,.E
        LD   A,(HL)
        CP   ' '
        JR   NZ,.L
        INC  HL
        DEC  C
        JR   .S
.L:     LD   A,C
        OR   A
        JR   Z,.E
        LD   A,(HL)
        INC  HL
        DEC  C
        CP   ','
        JR   Z,.E
        LD   (DE),A
        INC  DE
        DJNZ .L
.E:     XOR  A
        LD   (DE),A
        LD   (RT_IP),HL
        LD   A,C
        LD   (RT_IC),A
        LD   HL,RT_FBUF
        RET
""")

_r("RT_RDX", """
RT_RDX:                         ; FAC <- élément DATA suivant (texte lu par FIN)
        CALL RT_DNEXT
        CALL RT_ZSTR
        CALL FIN
.S:     LD   A,(HL)             ; le nombre doit occuper tout l'élément
        CP   ' '
        JR   NZ,.F
        INC  HL
        JR   .S
.F:     OR   A
        RET  Z
        LD   HL,(RT_DLINE)      ; sinon SN Error, à la ligne du DATA (comme le X-07)
        LD   (RT_LINE),HL
        LD   E,2
        JP   RT_FERR
""")

# ------------------------------------------------------------- INPUT
_r("RT_INPUT", """
RT_INPUT:                       ; saisie d'une ligne (A=1 : avec « ? »)
        OR   A
        JR   Z,.N
        CALL INPUTQ
        JR   .G
.N:     CALL INPUTL
.G:     JP   C,RT_BREAK         ; CY=1 : BREAK pendant la saisie
        INC  HL
        LD   (RT_IP),HL
        LD   B,0
.L:     LD   A,(HL)
        OR   A
        JR   Z,.E
        INC  HL
        INC  B
        JR   NZ,.L
        DEC  B
.E:     LD   A,B
        LD   (RT_IC),A
        RET
""")

_r("RT_CSAV", """
RT_CSAV:                        ; garde la fin de la ligne directe « EXEC &H... »,
        LD   HL,(RT_SP)         ; que la saisie d'un INPUT écrase dans le tampon
        LD   DE,24              ; $00D5 : le BASIC la relit au retour (sinon SN Error)
        ADD  HL,DE
        LD   E,(HL)
        INC  HL
        LD   D,(HL)             ; DE = pointeur texte empilé par EXEC ($CEB8)
        LD   HL,-$00D4
        ADD  HL,DE
        RET  NC                 ; avant le tampon
        LD   A,H
        OR   A
        RET  NZ                 ; après le tampon : programme en mémoire
        EX   DE,HL
        LD   (RT_CMDP),HL
        LD   DE,RT_CMD          ; 64 octets : la fin de ligne et les 00 qui suivent
        LD   BC,64
        LDIR
        RET
""")

_r("RT_CRST", """
RT_CRST:                        ; rétablit la fin de la ligne directe
        LD   DE,(RT_CMDP)
        LD   A,D
        OR   E
        RET  Z
        LD   HL,RT_CMD
        LD   BC,64
        LDIR
        RET
""")

_r("RT_SKIPC", """
RT_SKIPC:                       ; avance après la prochaine virgule
        LD   A,C
        OR   A
        RET  Z
        LD   A,(HL)
        INC  HL
        DEC  C
        CP   ','
        RET  Z
        JR   RT_SKIPC
""")

_r("RT_INS", """
RT_INS:                         ; lit une chaîne saisie (jusqu'à la virgule) -> (HL)
        EX   DE,HL
        LD   HL,(RT_IP)
        LD   A,(RT_IC)
        LD   C,A
        PUSH DE
        INC  DE
        LD   B,0
.L:     LD   A,C
        OR   A
        JR   Z,.E
        LD   A,(HL)
        INC  HL
        DEC  C
        CP   ','
        JR   Z,.E
        PUSH AF
        LD   A,B
        CP   STRCAP
        JR   NC,.S
        POP  AF
        LD   (DE),A
        INC  DE
        INC  B
        JR   .L
.S:     POP  AF
        JR   .L
.E:     LD   (RT_IP),HL
        LD   A,C
        LD   (RT_IC),A
        POP  HL
        LD   (HL),B
        RET
""")

# ------------------------------------------------------------- DATA / READ
_r("RT_DNEXT", """
RT_DNEXT:                       ; HL = élément DATA suivant (ligne dans RT_DLINE)
        LD   HL,(RT_DPTR)
        LD   E,(HL)
        INC  HL
        LD   D,(HL)
        INC  HL
        LD   A,D
        AND  E
        INC  A
        JR   NZ,.K
        LD   E,4                ; OD : plus de DATA
        JP   RT_FERR
.K:     LD   (RT_DLINE),DE
        PUSH HL
        LD   E,(HL)
        LD   D,0
        INC  DE
        ADD  HL,DE
        LD   (RT_DPTR),HL
        POP  HL
        RET
""")

_r("RT_RDS", """
RT_RDS:                         ; READ chaîne -> (HL)
        PUSH HL
        CALL RT_DNEXT
        EX   DE,HL
        POP  HL
        JP   RT_SCOPY
""")

# ------------------------------------------------------------- T6834
_r("RT_T6", """
RT_T6:                          ; commande A au T6834, paramètres dans RT_GB
        LD   HL,RT_GB
        LD   DE,T6BUF
        JP   T6CMDP
""")

VARIABLES.update({
    "RT_DPTR": 2, "RT_IP": 2, "RT_IC": 1, "RT_GB": 5, "RT_LINE": 2, "RT_FBUF": 64, "RT_DLINE": 2,
    "RT_CMD": 64, "RT_CMDP": 2,
})

_NAME = re.compile(r"\b((?:RT|MSG)_[A-Z0-9_]+)\b")


def refs(text):
    return set(_NAME.findall(text))


def closure(used, debug=False):
    """Routines et variables nécessaires, dans un ordre stable."""
    need, todo = set(), list(used)
    while todo:
        n = todo.pop()
        if n in need:
            continue
        need.add(n)
        if n in ROUTINES:
            todo += refs(routine(n, debug))
    routines = [n for n in ROUTINES if n in need]
    variables = [n for n in VARIABLES if n in need]
    return routines, variables


def routine(name, debug=False):
    text = ROUTINES[name]
    if "@ERRLINE@" in text:
        text = text.replace(
            "@ERRLINE@",
            "LD   HL,MSG_IN\n        CALL RT_PRS\n        LD   HL,(RT_LINE)\n"
            "        CALL PRTHL" if debug else "")
        text = "\n".join(l for l in text.split("\n") if l.strip())
    return text
