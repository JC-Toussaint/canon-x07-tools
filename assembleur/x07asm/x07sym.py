"""Symboles du Canon X-07, d'après « Les mystères du X-07 » et
« Applications en assembleur » (voir X07_mysteres_reference.tex).

Trois familles :
  ROUTINES  : points d'entrée en ROM (cibles de CALL/JP)
  VARIABLES : zone de travail du système en RAM (références (nn))
  PORTS     : ports d'E/S du HD61L202F (IN/OUT)
  T6834     : codes de commande du sous-processeur (constantes)
Chaque entrée : nom -> (valeur, commentaire).
Les entrées marquées « vérifié ROM » ont été contrôlées dans le vidage de
la ROM (ROM_x07/x07.bin) ; le livre inverse notamment $B8 (ligne) et $B9
(colonne), qui comptent à partir de 1.
"""

ROUTINES = {
    # RST
    "SYNCHR":      (0xF52F, "RST 08 : compare (HL) à l'octet suivant le RST, sinon SN ERROR (vérifié ROM)"),
    "CHRGET":      (0xF537, "RST 10 : A=(HL), HL+1 ; CY si chiffre/lettre (vérifié ROM)"),
    "CPHLDE":      (0xEE45, "RST 20 : compare HL et DE (vérifié ROM)"),
    "GETYPE":      (0xFC2F, "RST 30 : teste le type (01D9) (vérifié ROM)"),
    # calcul flottant BCD (vérifié ROM ; FAC = $044E, ARG = $049F, type en $01D9)
    "FOPDISP":     (0xF9E4, "répartiteur des opérateurs + - * / ^ (pile : opérande gauche, BC = type/op) (vérifié ROM)"),
    "FIN":         (0xBA21, "texte (HL) -> FAC, type selon l'écriture (vérifié ROM)"),
    "FOUT":        (0xBBAB, "FAC -> texte libre, HL = début, fin 00 (vérifié ROM)"),
    "FNEG":        (0xC9E0, "FAC = -FAC, tous types (vérifié ROM)"),
    "FSGN":        (0xC9F1, "SGN : HL = -1, 0 ou 1, tous types (vérifié ROM)"),
    "FFIX":        (0xCC14, "FIX (vérifié ROM)"),
    "FSQR":        (0xB694, "SQR (vérifié ROM)"),
    "FLOG":        (0xB609, "LOG (vérifié ROM)"),
    "FEXP":        (0xB6DD, "EXP (vérifié ROM)"),
    "FCOS":        (0xB530, "COS (vérifié ROM)"),
    "FSIN":        (0xB549, "SIN (vérifié ROM)"),
    "FTAN":        (0xB593, "TAN (vérifié ROM)"),
    "FATN":        (0xB5AC, "ATN (vérifié ROM)"),
    "FRND":        (0xB771, "RND (vérifié ROM)"),
    "RNDINIT":     (0xB7B5, "réinitialise RND comme RUN (vérifié ROM)"),
    "DEVPOS":      (0xE8EE, "position (A) et largeur (B) du périphérique courant (vérifié ROM)"),
    "CRLF":        (0xE929, "envoie CR LF au périphérique courant (vérifié ROM)"),
    "ERRTAB":      (0xF123, "codes d'erreur sur 2 lettres : NF SN RG OD FC OV... (vérifié ROM)"),
    "FSIGN":       (0xC9C7, "RST 18 : signe de l'accumulateur -> A = 0, 1 ou FF ; Z si nul (vérifié ROM)"),
    "ARRADR":      (0xE906, "RST 38 + octet n : n < $80 -> DE = mot en HL+n ; n >= $80 -> fonction n du pilote courant (vérifié ROM)"),
    # buzzer
    "BEEPR":       (0xC2DF, "bip : IY=tonalité, H=durée, L=0 (vérifié ROM)"),
    "SPEAKER":     (0xC331, "haut-parleur : IY=tonalité, HL=durée, C=FF/00"),
    # clavier
    "KBWAIT":      (0xC8C5, "lit le clavier avec curseur -> A (vérifié ROM)"),
    "INKEY":       (0xC90A, "lit une touche (INKEY$) -> A ; Z=1 si aucune (vérifié ROM)"),
    # écran LCD
    "LCDPUT":      (0xC1BE, "écrit A à l'écran, codes de contrôle admis, registres conservés (vérifié ROM)"),
    "LCDPUTXY":    (0xC231, "écrit C en X=H, Y=L, curseur immobile"),
    "LCDCLS":      (0xCE9E, "efface l'écran (CLS) (vérifié ROM)"),
    "LCDCHR":      (0xC18A, "affiche A au curseur, le curseur avance"),
    "CURSOR":      (0xC0A1, "A=0 affiche le curseur, A=1 le cache"),
    # imprimante
    "PRTINIT":     (0xCFB7, "initialise l'imprimante parallèle"),
    "PRTCRLF":     (0xCFB0, "envoie LF+CR à l'imprimante"),
    "PRTPUT":      (0xCEF7, "envoie A à l'imprimante (teste BUSY/BREAK)"),
    "PARPUT":      (0xCF11, "envoie A sur le port parallèle"),
    "PARWAIT":     (0xCF2A, "attend BUSY=0 sur le port parallèle"),
    # T6834
    "T6CMD":       (0xE428, "commande T6834 sans paramètre (A) (vérifié ROM)"),
    "T6CMDP":      (0xC92F, "commande T6834 : A=cmd, HL=param, B=nb, C=nb rép., DE=tampon (vérifié ROM)"),
    "T6FLUSH":     (0xC0BD, "vide les tampons clavier et T6834 (vérifié ROM)"),
    "T6PEEK":      (0xE348, "lit la RAM du T6834 : HL=adresse -> A (vérifié ROM)"),
    "T6POKE":      (0xE334, "écrit la RAM du T6834 : HL=adresse, A=donnée"),
    # général
    "IOINIT":      (0xC39D, "initialise les ports"),
    # conversions
    "FCINT":       (0xCAE0, "accumulateur -> entier ; TRONQUE (CINT(2.6)=2), OV au-delà de 16 bits (vérifié ROM)"),
    "FCSNG":       (0xCB08, "accumulateur -> simple précision (CSNG) (vérifié ROM)"),
    "INT2SNG":     (0xCB1E, "entier -> simple précision (vérifié ROM)"),
    "FCDBL":       (0xCB90, "accumulateur -> double précision (CDBL) (vérifié ROM)"),
    "ASC2INT":     (0xF595, "lit un NUMÉRO DE LIGNE en (HL) -> DE : entier non signé 0-65535 seulement (vérifié ROM)"),
    "PRTHL":       (0xBB98, "affiche HL en décimal (vérifié ROM)"),
    "INT2ASC":     (0xBE5F, "entier -> ASCII dans (HL)"),
    # arithmétique
    "IADD":        (0xCCC6, "HL+DE (entier) (vérifié ROM)"),
    "ISUB":        (0xCCBB, "HL-DE (entier) (vérifié ROM)"),
    "IMUL":        (0xCCE7, "HL*DE (entier) (vérifié ROM)"),
    "IDIV":        (0xFA79, "division entière DE / HL du répartiteur : le résultat est un double (comme 1/3) (vérifié ROM)"),
    "SADD":        (0xCDA9, "« simple » : BC:DE + FAC, calculé en double (type 8) (vérifié ROM)"),
    "SSUB":        (0xCDB2, "« simple » : BC:DE - FAC, calculé en double (type 8) (vérifié ROM)"),
    "SMUL":        (0xCDB7, "« simple » : BC:DE * FAC, calculé en double (type 8) (vérifié ROM)"),
    "SDIV":        (0xCDC2, "« simple » : BC:DE / FAC, calculé en double (type 8) (vérifié ROM)"),
    "DADD":        (0xB20E, "acc + acc2 (double) (vérifié ROM)"),
    "DSUB":        (0xB200, "acc - acc2 (double) (vérifié ROM)"),
    "DMUL":        (0xB376, "acc * acc2 (double) (vérifié ROM)"),
    "DDIV":        (0xB42F, "acc / acc2 (double) (vérifié ROM)"),
    "SCMP":        (0xCA7B, "compare BC:DE et acc (simple) (vérifié ROM)"),
    "ICMP":        (0xCAA5, "compare HL et DE (entier) (vérifié ROM)"),
    "DCMP":        (0xCAD9, "compare FAC et ARG (double) : A = 1 si FAC < ARG, -1 si FAC > ARG, 0 si égaux (vérifié ROM)"),
    "DSIGN":       (0xC9FB, "signe de l'accumulateur double"),
    "FABS":        (0xC9DC, "valeur absolue (ABS) (vérifié ROM)"),
    "FINT":        (0xCC23, "partie entière (INT) (vérifié ROM)"),
    # transferts
    "PUSHFAC":     (0xCA0B, "empile l'accumulateur"),
    "BCDE2FAC":    (0xCA1B, "BC:DE -> accumulateur"),
    "FAC2BCDE":    (0xCA26, "accumulateur -> BC:DE"),
    "FAC2MEM":     (0xCA42, "accumulateur -> (HL)"),
    "MOVUP":       (0xCA51, "copie B octets (DE)->(HL), croissant"),
    "MOVDN":       (0xCA58, "copie B octets (DE)->(HL), décroissant"),
    "HL2FAC":      (0xCAEF, "HL -> accumulateur (entier) (vérifié ROM)"),
    "ARG2FAC":     (0xCA5F, "acc2 -> accumulateur"),
    "FAC2ARG":     (0xCA67, "accumulateur -> acc2"),
    # système
    "ISCNTC":      (0xC000, "test OFF/pause/piles/BREAK de l'interpréteur (vérifié ROM)"),
    "BATTMSG":     (0xC06C, "messages piles faibles (BREAKFLAG bits 1 et 3) (vérifié ROM)"),
    "CURSET":      (0xC164, "place le curseur : H=colonne, L=ligne, à partir de 1 (vérifié ROM)"),
    "CHKTIMER":    (0xC02D, "si BREAKFLAG bit 0 : efface les bits 0 et 2, vide le clavier (vérifié ROM)"),
    "CHKBATT":     (0xC5A6, "si BREAKFLAG bit 7 (OFF) : éteint la machine (vérifié ROM)"),
    "JMPTAB":      (0xEE13, "saut dans une table : HL=table, C=décalage"),
    "EXTSW":       (0xC557, "commutateur d'extension -> HL=4000/2000"),
    "POWEROFF":    (0xC5C3, "coupe l'alimentation"),
    "STARTPRG":    (0xC5CD, "programme de lancement (A=1/2)"),
    "RSTTIMER":    (0xE327, "réarme la minuterie d'extinction"),
    "ISRAM":       (0xC62E, "Z=1 si HL est en RAM"),
    "SLEEPR":      (0xC59B, "SLEEP"),
    "GETBRK":      (0xE8E8, "A = BREAKFLAG AND $83 ; NZ si BREAK, piles ou OFF (vérifié ROM)"),
    "PRTSTR":      (0xD5B0, "affiche la chaîne (HL) terminée par 00/0D"),
    "PRTMSG":      (0xFEF7, "affiche le message (HL) terminé par 00 (vérifié ROM)"),
    "INPUTQ":      (0xEBF2, "saisie avec « ? » -> HL=$00D4, fin 00 ; CY=1 si BREAK (vérifié ROM)"),
    "INPUTL":      (0xEBFF, "saisie sans « ? » -> HL=$00D4, fin 00 ; CY=1 si BREAK (vérifié ROM)"),
    "FNDLIN":      (0xF30D, "cherche la ligne BASIC DE (vérifié ROM)"),
    "GETBYT":      (0xFE5E, "évalue une expression < 256"),
    "GETINT":      (0xFFCC, "évalue une expression entière"),
    "CONTSYS":     (0xF680, "CONT général du système"),
    "COPYRGT":     (0xC528, "message de copyright"),
    "COLDST":      (0xC3C3, "démarrage à froid (vérifié ROM)"),
    "HEXENTRY":    (0xFB4F, "entrée d'une routine en hexadécimal"),
    "CREATSYS":    (0xC4D1, "« CREATE SYSTEM ? » (vérifié ROM)"),
    "READY":       (0xF23D, "mode d'attente avec curseur (vérifié ROM)"),
    "SNERR":       (0xF1AA, "SN ERROR (vérifié ROM)"),
    "ERROR":       (0xF1C7, "erreur numéro E (vérifié ROM)"),
    # fichiers / périphériques
    "DEVOPEN":     (0xE6A8, "INIT# : DE=table, IY=fichier, A=0 (vérifié ROM)"),
    "DEVSEL":      (0xE827, "choisit le fichier courant (DE) (vérifié ROM)"),
    "DEVPUT":      (0xE88F, "RST 28 : envoie A au fichier courant (vérifié ROM)"),
    "DEVGET":      (0xE8D4, "lit un octet du fichier courant -> A (vérifié ROM)"),
    "DEV_KBD":     (0xE778, "table du dispositif KBD: (vérifié ROM)"),
    "DEV_CASI":    (0xE787, "table du dispositif CASI: (vérifié ROM)"),
    "DEV_CASO":    (0xE796, "table du dispositif CASO: (vérifié ROM)"),
    "DEV_COM":     (0xE7A4, "table du dispositif COM: (vérifié ROM)"),
    "DEV_GPR":     (0xE7B2, "table du dispositif GPR: (vérifié ROM)"),
    "DEV_PRT":     (0xE7C0, "table du dispositif PRT:"),
    "DEV_RAM":     (0xE7CE, "table du dispositif RAM:"),
    "DEV_OPT":     (0xE7DC, "table du dispositif OPT:"),
    "DEV_CON":     (0xE7EA, "table du dispositif CON:"),
    "DEV_LPT":     (0xE7F8, "table du dispositif LPT:"),
}

VARIABLES = {
    "BRKFLG":   (0x002B, "BREAKFLAG (vérifié ROM)"),
    "HKCONOUT": (0x009F, "hook sortie CONSOLE"),
    "HKCONIN":  (0x00A2, "hook entrée CONSOLE"),
    "HKABORT":  (0x00A8, "hook ABORT"),
    "HKERROR":  (0x00AB, "hook ERREUR (vérifié ROM)"),
    "TXTTAB":   (0x00B2, "début du programme BASIC (vérifié ROM)"),
    "CSRY":     (0x00B8, "ligne du curseur, à partir de 1 (vérifié ROM)"),
    "CSRX":     (0x00B9, "colonne du curseur, à partir de 1 (vérifié ROM)"),
    "INPBUF":   (0x00D5, "tampon d'entrée (vérifié ROM)"),
    "VALTYP":   (0x01D9, "type de donnée (2,3,4,8) (vérifié ROM)"),
    "STKTOP":   (0x01DD, "fin de la pile (vérifié ROM)"),
    "MEMSIZ":   (0x01DF, "fin de la zone BASIC (vérifié ROM)"),
    "FRETOP":   (0x0204, "zone des chaînes libre (vérifié ROM)"),
    "RAMSTR":   (0x0210, "début des fichiers RAM"),
    "RAMEND":   (0x0212, "fin des fichiers RAM"),
    "LCDIMG":   (0x0214, "image de l'écran LCD (80 octets)"),
    "INTIMAG":  (0x026C, "image du port F0 (vérifié ROM)"),
    "T6BUF":    (0x026E, "tampon T6834 (vérifié ROM)"),
    "FILE1":    (0x02C5, "fichier #1 (table INIT#) (vérifié ROM)"),
    "FILE2":    (0x02CD, "fichier #2 (table INIT#)"),
    "CURDEV":   (0x02F5, "périphérique ouvert (vérifié ROM)"),
    "CURLIN":   (0x0311, "ligne en cours"),
    "ERRLIN":   (0x0317, "ligne de l'erreur"),
    "ONERR":    (0x0319, "adresse ON ERROR"),
    "VARTAB":   (0x0322, "table des variables (vérifié ROM)"),
    "ARYTAB":   (0x0324, "table des tableaux"),
    "STREND":   (0x0326, "début de la zone libre"),
    "DATPTR":   (0x0328, "pointeur des DATA (vérifié ROM)"),
    "FAC":      (0x044E, "accumulateur flottant (vérifié ROM)"),
    "FACINT":   (0x0450, "entier dans l'accumulateur (vérifié ROM)"),
    "ARG":      (0x049F, "accumulateur 2 (vérifié ROM)"),
    "T6BUF2":   (0x0507, "2e tampon T6834"),
    "BASTXT":   (0x0553, "début des programmes BASIC (vérifié ROM)"),
}

PORTS = {
    "P_INT":    (0xF0, "interruptions (vérifié ROM)"),
    "P_T6":     (0xF1, "donnée T6834 (vérifié ROM)"),
    "P_STAT":   (0xF2, "bauds bas / indicateurs (vérifié ROM)"),
    "P_BAUDH":  (0xF3, "bauds haut (vérifié ROM)"),
    "P_MODE":   (0xF4, "modes (REM, BZON, MD0/1...) (vérifié ROM)"),
    "P_INTRST": (0xF5, "RAZ des interruptions (vérifié ROM)"),
    "P_UART":   (0xF6, "contrôle/état UART (vérifié ROM)"),
    "P_SER":    (0xF7, "donnée série (vérifié ROM)"),
}

T6834 = {
    "T_TIMECALL": 0x01, "T_STICK": 0x02, "T_STRIG": 0x03, "T_STRIG1": 0x04,
    "T_RAMREAD": 0x05, "T_RAMWRITE": 0x06, "T_SCROLLSET": 0x07,
    "T_SCROLLEXEC": 0x08, "T_LINECLEAR": 0x09, "T_TIMESET": 0x0A,
    "T_CALCDAY": 0x0B, "T_ALARMSET": 0x0C, "T_BUZZOFF": 0x0D, "T_BUZZON": 0x0E,
    "T_BITIMAGE": 0x0F, "T_POINT": 0x10, "T_PSET": 0x11, "T_PRESET": 0x12,
    "T_PEOR": 0x13, "T_LINE": 0x14, "T_CIRCLE": 0x15, "T_UDKWRITE": 0x16,
    "T_UDKREAD": 0x17, "T_UDKON": 0x18, "T_UDKOFF": 0x19, "T_UDCWRITE": 0x1A,
    "T_UDCREAD": 0x1B, "T_UDCINIT": 0x1C, "T_SPWRITE": 0x1D, "T_SPWRCONT": 0x1E,
    "T_SPON": 0x1F, "T_SPOFF": 0x20, "T_SPREAD": 0x21, "T_ONSTATE": 0x22,
    "T_OFFREQ": 0x23, "T_LOCATE": 0x24, "T_CURSON": 0x25, "T_CURSOFF": 0x26,
    "T_TESTKEY": 0x27, "T_TESTCHR": 0x28, "T_SECCLR": 0x29, "T_DATESET": 0x2A,
    "T_DISPOFF": 0x2B, "T_DISPON": 0x2C, "T_KBCLR": 0x2D, "T_CLS": 0x2E,
    "T_HOME": 0x2F, "T_UDKDISPON": 0x30, "T_UDKDISPOFF": 0x31,
    "T_REPEATON": 0x32, "T_REPEATOFF": 0x33, "T_KANASET": 0x34,
    "T_UDKCONT": 0x35, "T_ALARMREAD": 0x36, "T_BUZZZERO": 0x37,
    "T_CLICKOFF": 0x38, "T_CLICKON": 0x39, "T_LOCCLOSE": 0x3A,
    "T_KEYOUTON": 0x3B, "T_KEYOUTOFF": 0x3C, "T_SPAUTOON": 0x3D,
    "T_SPAUTOOFF": 0x3E, "T_SLEEP": 0x3F, "T_UDKINIT": 0x40,
    "T_CHARWRITE": 0x41, "T_CHARREAD": 0x42, "T_SCANR": 0x43, "T_SCANL": 0x44,
    "T_TIMECHK": 0x45, "T_ALMCHK": 0x46,
}


def all_symbols():
    """Tous les symboles prédéfinis pour l'assembleur : nom -> valeur."""
    out = {}
    for table in (ROUTINES, VARIABLES, PORTS):
        out.update({k: v for k, (v, _) in table.items()})
    out.update(T6834)
    return out


def by_value(table):
    return {v: (k, c) for k, (v, c) in table.items()}


ROUTINE_AT = by_value(ROUTINES)
VARIABLE_AT = by_value(VARIABLES)
PORT_AT = by_value(PORTS)

RST_COMMENT = {
    0x00: "point d'arrêt (XP-140F)",
    0x08: "SYNCHR : compare (HL) à l'octet suivant",
    0x10: "CHRGET : A=(HL), HL+1",
    0x18: "FSIGN : signe de l'accumulateur flottant -> A (vérifié ROM)",
    0x20: "CPHLDE : compare HL et DE",
    0x28: "DEVPUT : A vers le fichier courant",
    0x30: "GETYPE : type de donnée",
    0x38: "lecture dans une table ou fonction du pilote courant (octet en ligne)",
}

# Plages de la carte mémoire (pour la vérification d'implantation)
RAM_TOP = {8: 0x1FFF, 16: 0x3FFF, 24: 0x5FFF}


def markdown():
    """Carte des symboles au format Markdown (assembleur/ROM.md)."""
    def rows(table, fmt):
        out = ["| Adresse | Nom | Rôle | Vérifié |", "|---|---|---|---|"]
        for name, (v, c) in sorted(table.items(), key=lambda x: x[1][0]):
            checked = "vérifié ROM" in c
            role = c.replace(" (vérifié ROM)", "").replace("|", "\\|")
            out.append("| `%s` | `%s` | %s | %s |" % (fmt % v, name, role, "✓" if checked else ""))
        return out

    n_ok = sum("vérifié ROM" in c for t in (ROUTINES, VARIABLES, PORTS) for _, c in t.values())
    n = sum(len(t) for t in (ROUTINES, VARIABLES, PORTS))
    lines = [
        "# Carte de la ROM et de la zone système du Canon X-07",
        "",
        "Les symboles que l'assembleur connaît d'avance (`CALL INKEY`, `LD HL,(TXTTAB)`...) "
        "et que le compilateur et le désassembleur utilisent. Ils viennent des *Mystères du X-07* "
        "et ont été corrigés d'après la ROM (voir [l'errata](../ref_docs/ERRATA.md)).",
        "",
        "La colonne « Vérifié » signale une entrée contrôlée dans le vidage de la ROM ou par "
        "l'émulateur : %d sur %d. Les autres viennent du livre." % (n_ok, n),
        "",
        "> Fichier produit par `python3 x07asm.py sym --md > ROM.md` à partir de "
        "`x07asm/x07sym.py` : ne pas le modifier à la main.",
        "",
        "## Routines de la ROM ($B000-$FFFF)",
        "",
    ] + rows(ROUTINES, "$%04X") + [
        "",
        "## Variables de la zone système",
        "",
    ] + rows(VARIABLES, "$%04X") + [
        "",
        "## Ports d'entrée/sortie (HD61L202F)",
        "",
    ] + rows(PORTS, "$%02X") + [
        "",
        "## Commandes du sous-processeur T6834",
        "",
        "Codes envoyés par `T6CMD` ou `T6CMDP` (les valeurs viennent du livre ; ajouter $80 "
        "pour une commande sans paramètre).",
        "",
        "| Code | Nom |",
        "|---|---|",
    ] + ["| `$%02X` | `%s` |" % (v, n) for n, v in sorted(T6834.items(), key=lambda x: x[1])] + [
        "",
        "## Vecteurs RST",
        "",
        "| RST | Rôle |",
        "|---|---|",
    ] + ["| `$%02X` | %s |" % (v, c) for v, c in sorted(RST_COMMENT.items())]
    return "\n".join(lines) + "\n"
