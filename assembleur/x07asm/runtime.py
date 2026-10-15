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
Routines du X-07 employées (voir x07sym) : LCDPUT, LCDCLS, INKEY, INPUTQ,
INPUTL, T6CMDP, BEEPR ; variables CSRX, CSRY, BRKFLG, T6BUF.
"""
import re

ROUTINES = {}
VARIABLES = {}       # variables internes -> taille (zone remise à zéro)


def _r(name, text):
    ROUTINES[name] = text.strip("\n")


# ------------------------------------------------------------- fin, erreurs
_r("RT_END", """
RT_END:
        LD   SP,(RT_SP)
        POP  IY
        POP  IX
        POP  HL
        POP  DE
        POP  BC
        POP  AF
        RET                     ; retour au BASIC (EXEC)
""")

_r("RT_ERR", """
RT_ERR:                         ; HL = message ; affiche ?message et s'arrête
        PUSH HL
        LD   A,(CSRX)
        DEC  A
        CALL NZ,RT_NL            ; à la ligne si le curseur n'est pas en colonne 1
        LD   A,'?'
        CALL LCDPUT
        POP  HL
        CALL RT_PRS
        @ERRLINE@
        CALL RT_NL
        JP   RT_END
""")

_r("MSG_DIV0", 'MSG_DIV0:   DB 4,"DIV0"')
_r("MSG_IDX", 'MSG_IDX:    DB 6,"INDICE"')
_r("MSG_DATA", 'MSG_DATA:   DB 4,"DATA"')
_r("MSG_BRK", 'MSG_BRK:    DB 5,"BREAK"')
_r("MSG_LN", 'MSG_LN:     DB 6," LIGNE"')

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
        LD   HL,MSG_BRK
        JP   RT_ERR
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
        LD   HL,MSG_DIV0
        JP   RT_ERR
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
RT_DIV:                         ; HL = DE / HL (troncature)
        JP   RT_DIVMOD
""")

_r("RT_MOD", """
RT_MOD:                         ; HL = DE MOD HL (signe du dividende)
        CALL RT_DIVMOD
        EX   DE,HL
        RET
""")

_r("RT_POW", """
RT_POW:                         ; HL = DE ^ HL
        BIT  7,H
        JR   Z,.P
        LD   HL,0
        RET
.P:     LD   B,H
        LD   C,L
        LD   HL,1
.L:     LD   A,B
        OR   C
        RET  Z
        PUSH BC
        PUSH DE
        CALL RT_MUL
        POP  DE
        POP  BC
        DEC  BC
        JR   .L
""")

_r("RT_RND", """
RT_RND:                         ; HL = n -> 0..n-1 (n <= 0 : 0..32767)
        PUSH HL
        LD   HL,(RT_SEED)       ; xorshift 16 bits
        LD   A,H
        RRA
        LD   A,L
        RRA
        XOR  H
        LD   H,A
        LD   A,L
        RRA
        LD   A,H
        RRA
        XOR  L
        LD   L,A
        XOR  H
        LD   H,A
        LD   (RT_SEED),HL
        RES  7,H
        EX   DE,HL
        POP  HL
        BIT  7,H
        JR   NZ,.R
        LD   A,H
        OR   L
        JR   Z,.R
        JP   RT_MOD
.R:     EX   DE,HL
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

_r("RT_STR", """
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

_r("RT_ATOI", """
RT_ATOI:                        ; HL = texte, C = longueur -> DE = valeur
        LD   DE,0
.S:     CALL .CH
        CP   ' '
        JR   NZ,.S1
        CALL .AV
        JR   .S
.S1:    LD   B,0
        CP   '+'
        JR   Z,.SG
        CP   '-'
        JR   NZ,.S2
        INC  B
.SG:    CALL .AV
        CALL .CH
.S2:    CP   '&'
        JR   Z,.HX
.DL:    CALL .CH
        SUB  '0'
        CP   10
        JR   NC,.F
        PUSH HL
        LD   H,D
        LD   L,E
        ADD  HL,HL
        ADD  HL,HL
        ADD  HL,DE
        ADD  HL,HL
        LD   E,A
        LD   D,0
        ADD  HL,DE
        EX   DE,HL
        POP  HL
        CALL .AV
        JR   .DL
.HX:    CALL .AV
        CALL .CH
        AND  $DF
        CP   'H'
        JR   NZ,.F
        CALL .AV
.HE:    CALL .CH
        CP   'a'
        JR   C,.HU
        AND  $DF
.HU:    SUB  '0'
        CP   10
        JR   C,.HD
        SUB  7
        CP   10
        JR   C,.F
        CP   16
        JR   NC,.F
.HD:    PUSH HL
        EX   DE,HL
        ADD  HL,HL
        ADD  HL,HL
        ADD  HL,HL
        ADD  HL,HL
        LD   E,A
        LD   D,0
        ADD  HL,DE
        EX   DE,HL
        POP  HL
        CALL .AV
        JR   .HE
.F:     LD   A,B
        OR   A
        RET  Z
        EX   DE,HL
        CALL RT_NEG
        EX   DE,HL
        RET
.CH:    LD   A,C
        OR   A
        RET  Z
        LD   A,(HL)
        RET
.AV:    LD   A,C
        OR   A
        RET  Z
        INC  HL
        DEC  C
        RET
""")

_r("RT_VAL", """
RT_VAL:                         ; HL = VAL((HL))
        LD   C,(HL)
        INC  HL
        CALL RT_ATOI
        EX   DE,HL
        RET
""")

# ------------------------------------------------------------- affichage
_r("RT_PRS", """
RT_PRS:                         ; affiche la chaîne (HL)
        LD   B,(HL)
        INC  B
.L:     DEC  B
        RET  Z
        INC  HL
        LD   A,(HL)
        CALL LCDPUT
        JR   .L
""")

_r("RT_PRN", """
RT_PRN:                         ; affiche HL comme PRINT (espace avant et après)
        LD   DE,RT_NBUF
        CALL RT_STR
        LD   HL,RT_NBUF
        CALL RT_PRS
        LD   A,' '
        JP   LCDPUT
""")

_r("RT_NL", """
RT_NL:                          ; retour à la ligne
        LD   A,13
        CALL LCDPUT
        LD   A,10
        JP   LCDPUT
""")

_r("RT_COMMA", """
RT_COMMA:                       ; virgule de PRINT : zone suivante (10 colonnes)
        LD   A,' '
        CALL LCDPUT
        LD   A,(CSRX)           ; colonne, à partir de 1
        DEC  A
.M:     SUB  10
        JR   NC,.M
        ADD  A,10
        JR   NZ,RT_COMMA
        RET
""")


_r("RT_TAB", """
RT_TAB:                         ; TAB(HL) : colonnes comptées à partir de 0
        LD   A,H
        OR   A
        JR   NZ,.C
        LD   A,L
        CP   20
        JR   C,.K
.C:     LD   L,19
.K:     INC  L                  ; CSRX compte à partir de 1
.L:     LD   A,(CSRX)
        CP   L
        RET  NC
        LD   A,' '
        CALL LCDPUT
        JR   .L
""")


_r("RT_SPC", """
RT_SPC:                         ; SPC(HL)
        LD   A,H
        OR   A
        RET  NZ
        LD   B,L
        INC  B
.L:     DEC  B
        RET  Z
        LD   A,' '
        CALL LCDPUT
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
        LD   HL,MSG_IDX
        JP   RT_ERR
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

# ------------------------------------------------------------- INPUT
_r("RT_INPUT", """
RT_INPUT:                       ; saisie d'une ligne (A=1 : avec « ? »)
        OR   A
        JR   Z,.N
        CALL INPUTQ
        JR   .G
.N:     CALL INPUTL
.G:     JR   NC,.K              ; CY=1 : BREAK pendant la saisie
        LD   HL,MSG_BRK
        JP   RT_ERR
.K:     INC  HL
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

_r("RT_INN", """
RT_INN:                         ; lit un entier saisi -> (HL)
        PUSH HL
        LD   HL,(RT_IP)
        LD   A,(RT_IC)
        LD   C,A
        CALL RT_ATOI
        CALL RT_SKIPC
        LD   (RT_IP),HL
        LD   A,C
        LD   (RT_IC),A
        POP  HL
        LD   (HL),E
        INC  HL
        LD   (HL),D
        RET
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
RT_DNEXT:                       ; HL = élément DATA suivant
        LD   HL,(RT_DPTR)
        LD   A,(HL)
        CP   $FF
        JR   NZ,.K
        LD   HL,MSG_DATA
        JP   RT_ERR
.K:     PUSH HL
        LD   E,A
        LD   D,0
        INC  DE
        ADD  HL,DE
        LD   (RT_DPTR),HL
        POP  HL
        RET
""")

_r("RT_RDN", """
RT_RDN:                         ; READ entier -> (HL)
        PUSH HL
        CALL RT_DNEXT
        LD   C,(HL)
        INC  HL
        CALL RT_ATOI
        POP  HL
        LD   (HL),E
        INC  HL
        LD   (HL),D
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
    "RT_NZ": 1, "RT_SEED": 2, "RT_DPTR": 2, "RT_IP": 2, "RT_IC": 1,
    "RT_NBUF": 8, "RT_GB": 5, "RT_LINE": 2,
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
            "LD   HL,MSG_LN\n        CALL RT_PRS\n        LD   HL,(RT_LINE)\n"
            "        CALL RT_PRN" if debug else "")
        text = "\n".join(l for l in text.split("\n") if l.strip())
    return text
