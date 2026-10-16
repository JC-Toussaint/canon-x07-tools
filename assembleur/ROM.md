# Carte de la ROM et de la zone système du Canon X-07

Les symboles que l'assembleur connaît d'avance (`CALL INKEY`, `LD HL,(TXTTAB)`...) et que le compilateur et le désassembleur utilisent. Ils viennent des *Mystères du X-07* et ont été corrigés d'après la ROM (voir [l'errata](../ref_docs/ERRATA.md)).

La colonne « Vérifié » signale une entrée contrôlée dans le vidage de la ROM ou par l'émulateur : 109 sur 161. Les autres viennent du livre.

> Fichier produit par `python3 x07asm.py sym --md > ROM.md` à partir de `x07asm/x07sym.py` : ne pas le modifier à la main.

## Routines de la ROM ($B000-$FFFF)

| Adresse | Nom | Rôle | Vérifié |
|---|---|---|---|
| `$B200` | `DSUB` | acc - acc2 (double) | ✓ |
| `$B20E` | `DADD` | acc + acc2 (double) | ✓ |
| `$B376` | `DMUL` | acc * acc2 (double) | ✓ |
| `$B42F` | `DDIV` | acc / acc2 (double) | ✓ |
| `$B530` | `FCOS` | COS | ✓ |
| `$B549` | `FSIN` | SIN | ✓ |
| `$B593` | `FTAN` | TAN | ✓ |
| `$B5AC` | `FATN` | ATN | ✓ |
| `$B609` | `FLOG` | LOG | ✓ |
| `$B694` | `FSQR` | SQR | ✓ |
| `$B6DD` | `FEXP` | EXP | ✓ |
| `$B771` | `FRND` | RND | ✓ |
| `$B7B5` | `RNDINIT` | réinitialise RND comme RUN | ✓ |
| `$BA21` | `FIN` | texte (HL) -> FAC, type selon l'écriture | ✓ |
| `$BB98` | `PRTHL` | affiche HL en décimal | ✓ |
| `$BBAB` | `FOUT` | FAC -> texte libre, HL = début, fin 00 | ✓ |
| `$BE5F` | `INT2ASC` | entier -> ASCII dans (HL) |  |
| `$C000` | `ISCNTC` | test OFF/pause/piles/BREAK de l'interpréteur | ✓ |
| `$C02D` | `CHKTIMER` | si BREAKFLAG bit 0 : efface les bits 0 et 2, vide le clavier | ✓ |
| `$C06C` | `BATTMSG` | messages piles faibles (BREAKFLAG bits 1 et 3) | ✓ |
| `$C0A1` | `CURSOR` | A=0 affiche le curseur, A=1 le cache |  |
| `$C0BD` | `T6FLUSH` | vide les tampons clavier et T6834 | ✓ |
| `$C164` | `CURSET` | place le curseur : H=colonne, L=ligne, à partir de 1 | ✓ |
| `$C18A` | `LCDCHR` | affiche A au curseur, le curseur avance |  |
| `$C1BE` | `LCDPUT` | écrit A à l'écran, codes de contrôle admis, registres conservés | ✓ |
| `$C231` | `LCDPUTXY` | écrit C en X=H, Y=L, curseur immobile |  |
| `$C2DF` | `BEEPR` | bip : IY=tonalité, H=durée, L=0 | ✓ |
| `$C331` | `SPEAKER` | haut-parleur : IY=tonalité, HL=durée, C=FF/00 |  |
| `$C39D` | `IOINIT` | initialise les ports |  |
| `$C3C3` | `COLDST` | démarrage à froid | ✓ |
| `$C4D1` | `CREATSYS` | « CREATE SYSTEM ? » | ✓ |
| `$C528` | `COPYRGT` | message de copyright |  |
| `$C557` | `EXTSW` | commutateur d'extension -> HL=4000/2000 |  |
| `$C59B` | `SLEEPR` | SLEEP |  |
| `$C5A6` | `CHKBATT` | si BREAKFLAG bit 7 (OFF) : éteint la machine | ✓ |
| `$C5C3` | `POWEROFF` | coupe l'alimentation |  |
| `$C5CD` | `STARTPRG` | programme de lancement (A=1/2) |  |
| `$C62E` | `ISRAM` | Z=1 si HL est en RAM |  |
| `$C8C5` | `KBWAIT` | lit le clavier avec curseur -> A | ✓ |
| `$C90A` | `INKEY` | lit une touche (INKEY$) -> A ; Z=1 si aucune | ✓ |
| `$C92F` | `T6CMDP` | commande T6834 : A=cmd, HL=param, B=nb, C=nb rép., DE=tampon | ✓ |
| `$C9C7` | `FSIGN` | RST 18 : signe de l'accumulateur -> A = 0, 1 ou FF ; Z si nul | ✓ |
| `$C9DC` | `FABS` | valeur absolue (ABS) | ✓ |
| `$C9E0` | `FNEG` | FAC = -FAC, tous types | ✓ |
| `$C9F1` | `FSGN` | SGN : HL = -1, 0 ou 1, tous types | ✓ |
| `$C9FB` | `DSIGN` | signe de l'accumulateur double |  |
| `$CA0B` | `PUSHFAC` | empile l'accumulateur |  |
| `$CA1B` | `BCDE2FAC` | BC:DE -> accumulateur |  |
| `$CA26` | `FAC2BCDE` | accumulateur -> BC:DE |  |
| `$CA42` | `FAC2MEM` | accumulateur -> (HL) |  |
| `$CA51` | `MOVUP` | copie B octets (DE)->(HL), croissant |  |
| `$CA58` | `MOVDN` | copie B octets (DE)->(HL), décroissant |  |
| `$CA5F` | `ARG2FAC` | acc2 -> accumulateur |  |
| `$CA67` | `FAC2ARG` | accumulateur -> acc2 |  |
| `$CA7B` | `SCMP` | compare BC:DE et acc (simple) | ✓ |
| `$CAA5` | `ICMP` | compare HL et DE (entier) | ✓ |
| `$CAD9` | `DCMP` | compare FAC et ARG (double) : A = 1 si FAC < ARG, -1 si FAC > ARG, 0 si égaux | ✓ |
| `$CAE0` | `FCINT` | accumulateur -> entier ; TRONQUE (CINT(2.6)=2), OV au-delà de 16 bits | ✓ |
| `$CAEF` | `HL2FAC` | HL -> accumulateur (entier) | ✓ |
| `$CB08` | `FCSNG` | accumulateur -> simple précision (CSNG) | ✓ |
| `$CB1E` | `INT2SNG` | entier -> simple précision | ✓ |
| `$CB90` | `FCDBL` | accumulateur -> double précision (CDBL) | ✓ |
| `$CC14` | `FFIX` | FIX | ✓ |
| `$CC23` | `FINT` | partie entière (INT) | ✓ |
| `$CCBB` | `ISUB` | HL-DE (entier) | ✓ |
| `$CCC6` | `IADD` | HL+DE (entier) | ✓ |
| `$CCE7` | `IMUL` | HL*DE (entier) | ✓ |
| `$CDA9` | `SADD` | « simple » : BC:DE + FAC, calculé en double (type 8) | ✓ |
| `$CDB2` | `SSUB` | « simple » : BC:DE - FAC, calculé en double (type 8) | ✓ |
| `$CDB7` | `SMUL` | « simple » : BC:DE * FAC, calculé en double (type 8) | ✓ |
| `$CDC2` | `SDIV` | « simple » : BC:DE / FAC, calculé en double (type 8) | ✓ |
| `$CE9E` | `LCDCLS` | efface l'écran (CLS) | ✓ |
| `$CEF7` | `PRTPUT` | envoie A à l'imprimante (teste BUSY/BREAK) |  |
| `$CF11` | `PARPUT` | envoie A sur le port parallèle |  |
| `$CF2A` | `PARWAIT` | attend BUSY=0 sur le port parallèle |  |
| `$CFB0` | `PRTCRLF` | envoie LF+CR à l'imprimante |  |
| `$CFB7` | `PRTINIT` | initialise l'imprimante parallèle |  |
| `$D5B0` | `PRTSTR` | affiche la chaîne (HL) terminée par 00/0D |  |
| `$E327` | `RSTTIMER` | réarme la minuterie d'extinction |  |
| `$E334` | `T6POKE` | écrit la RAM du T6834 : HL=adresse, A=donnée |  |
| `$E348` | `T6PEEK` | lit la RAM du T6834 : HL=adresse -> A | ✓ |
| `$E428` | `T6CMD` | commande T6834 sans paramètre (A) | ✓ |
| `$E6A8` | `DEVOPEN` | INIT# : DE=table, IY=fichier, A=0 | ✓ |
| `$E778` | `DEV_KBD` | table du dispositif KBD: | ✓ |
| `$E787` | `DEV_CASI` | table du dispositif CASI: | ✓ |
| `$E796` | `DEV_CASO` | table du dispositif CASO: | ✓ |
| `$E7A4` | `DEV_COM` | table du dispositif COM: | ✓ |
| `$E7B2` | `DEV_GPR` | table du dispositif GPR: | ✓ |
| `$E7C0` | `DEV_PRT` | table du dispositif PRT: |  |
| `$E7CE` | `DEV_RAM` | table du dispositif RAM: |  |
| `$E7DC` | `DEV_OPT` | table du dispositif OPT: |  |
| `$E7EA` | `DEV_CON` | table du dispositif CON: |  |
| `$E7F8` | `DEV_LPT` | table du dispositif LPT: |  |
| `$E827` | `DEVSEL` | choisit le fichier courant (DE) | ✓ |
| `$E88F` | `DEVPUT` | RST 28 : envoie A au fichier courant | ✓ |
| `$E8D4` | `DEVGET` | lit un octet du fichier courant -> A | ✓ |
| `$E8E8` | `GETBRK` | A = BREAKFLAG AND $83 ; NZ si BREAK, piles ou OFF | ✓ |
| `$E8EE` | `DEVPOS` | position (A) et largeur (B) du périphérique courant | ✓ |
| `$E906` | `ARRADR` | RST 38 + octet n : n < $80 -> DE = mot en HL+n ; n >= $80 -> fonction n du pilote courant | ✓ |
| `$E929` | `CRLF` | envoie CR LF au périphérique courant | ✓ |
| `$EBF2` | `INPUTQ` | saisie avec « ? » -> HL=$00D4, fin 00 ; CY=1 si BREAK | ✓ |
| `$EBFF` | `INPUTL` | saisie sans « ? » -> HL=$00D4, fin 00 ; CY=1 si BREAK | ✓ |
| `$EE13` | `JMPTAB` | saut dans une table : HL=table, C=décalage |  |
| `$EE45` | `CPHLDE` | RST 20 : compare HL et DE | ✓ |
| `$F123` | `ERRTAB` | codes d'erreur sur 2 lettres : NF SN RG OD FC OV... | ✓ |
| `$F1AA` | `SNERR` | SN ERROR | ✓ |
| `$F1C7` | `ERROR` | erreur numéro E | ✓ |
| `$F23D` | `READY` | mode d'attente avec curseur | ✓ |
| `$F30D` | `FNDLIN` | cherche la ligne BASIC DE | ✓ |
| `$F52F` | `SYNCHR` | RST 08 : compare (HL) à l'octet suivant le RST, sinon SN ERROR | ✓ |
| `$F537` | `CHRGET` | RST 10 : A=(HL), HL+1 ; CY si chiffre/lettre | ✓ |
| `$F595` | `ASC2INT` | lit un NUMÉRO DE LIGNE en (HL) -> DE : entier non signé 0-65535 seulement | ✓ |
| `$F680` | `CONTSYS` | CONT général du système |  |
| `$F9E4` | `FOPDISP` | répartiteur des opérateurs + - * / ^ (pile : opérande gauche, BC = type/op) | ✓ |
| `$FA79` | `IDIV` | division entière DE / HL du répartiteur : le résultat est un double (comme 1/3) | ✓ |
| `$FB4F` | `HEXENTRY` | entrée d'une routine en hexadécimal |  |
| `$FC2F` | `GETYPE` | RST 30 : teste le type (01D9) | ✓ |
| `$FE5E` | `GETBYT` | évalue une expression < 256 |  |
| `$FEF7` | `PRTMSG` | affiche le message (HL) terminé par 00 | ✓ |
| `$FFCC` | `GETINT` | évalue une expression entière |  |

## Variables de la zone système

| Adresse | Nom | Rôle | Vérifié |
|---|---|---|---|
| `$002B` | `BRKFLG` | BREAKFLAG | ✓ |
| `$009F` | `HKCONOUT` | hook sortie CONSOLE |  |
| `$00A2` | `HKCONIN` | hook entrée CONSOLE |  |
| `$00A8` | `HKABORT` | hook ABORT |  |
| `$00AB` | `HKERROR` | hook ERREUR | ✓ |
| `$00B2` | `TXTTAB` | début du programme BASIC | ✓ |
| `$00B8` | `CSRY` | ligne du curseur, à partir de 1 | ✓ |
| `$00B9` | `CSRX` | colonne du curseur, à partir de 1 | ✓ |
| `$00D5` | `INPBUF` | tampon d'entrée | ✓ |
| `$01D9` | `VALTYP` | type de donnée (2,3,4,8) | ✓ |
| `$01DD` | `STKTOP` | fin de la pile | ✓ |
| `$01DF` | `MEMSIZ` | fin de la zone BASIC | ✓ |
| `$0204` | `FRETOP` | zone des chaînes libre | ✓ |
| `$0210` | `RAMSTR` | début des fichiers RAM |  |
| `$0212` | `RAMEND` | fin des fichiers RAM |  |
| `$0214` | `LCDIMG` | image de l'écran LCD (80 octets) |  |
| `$026C` | `INTIMAG` | image du port F0 | ✓ |
| `$026E` | `T6BUF` | tampon T6834 | ✓ |
| `$02C5` | `FILE1` | fichier #1 (table INIT#) | ✓ |
| `$02CD` | `FILE2` | fichier #2 (table INIT#) |  |
| `$02F5` | `CURDEV` | périphérique ouvert | ✓ |
| `$0311` | `CURLIN` | ligne en cours |  |
| `$0317` | `ERRLIN` | ligne de l'erreur |  |
| `$0319` | `ONERR` | adresse ON ERROR |  |
| `$0322` | `VARTAB` | table des variables | ✓ |
| `$0324` | `ARYTAB` | table des tableaux |  |
| `$0326` | `STREND` | début de la zone libre |  |
| `$0328` | `DATPTR` | pointeur des DATA | ✓ |
| `$044E` | `FAC` | accumulateur flottant | ✓ |
| `$0450` | `FACINT` | entier dans l'accumulateur | ✓ |
| `$049F` | `ARG` | accumulateur 2 | ✓ |
| `$0507` | `T6BUF2` | 2e tampon T6834 |  |
| `$0553` | `BASTXT` | début des programmes BASIC | ✓ |

## Ports d'entrée/sortie (HD61L202F)

| Adresse | Nom | Rôle | Vérifié |
|---|---|---|---|
| `$F0` | `P_INT` | interruptions | ✓ |
| `$F1` | `P_T6` | donnée T6834 | ✓ |
| `$F2` | `P_STAT` | bauds bas / indicateurs | ✓ |
| `$F3` | `P_BAUDH` | bauds haut | ✓ |
| `$F4` | `P_MODE` | modes (REM, BZON, MD0/1...) | ✓ |
| `$F5` | `P_INTRST` | RAZ des interruptions | ✓ |
| `$F6` | `P_UART` | contrôle/état UART | ✓ |
| `$F7` | `P_SER` | donnée série | ✓ |

## Commandes du sous-processeur T6834

Codes envoyés par `T6CMD` ou `T6CMDP` (les valeurs viennent du livre ; ajouter $80 pour une commande sans paramètre).

| Code | Nom |
|---|---|
| `$01` | `T_TIMECALL` |
| `$02` | `T_STICK` |
| `$03` | `T_STRIG` |
| `$04` | `T_STRIG1` |
| `$05` | `T_RAMREAD` |
| `$06` | `T_RAMWRITE` |
| `$07` | `T_SCROLLSET` |
| `$08` | `T_SCROLLEXEC` |
| `$09` | `T_LINECLEAR` |
| `$0A` | `T_TIMESET` |
| `$0B` | `T_CALCDAY` |
| `$0C` | `T_ALARMSET` |
| `$0D` | `T_BUZZOFF` |
| `$0E` | `T_BUZZON` |
| `$0F` | `T_BITIMAGE` |
| `$10` | `T_POINT` |
| `$11` | `T_PSET` |
| `$12` | `T_PRESET` |
| `$13` | `T_PEOR` |
| `$14` | `T_LINE` |
| `$15` | `T_CIRCLE` |
| `$16` | `T_UDKWRITE` |
| `$17` | `T_UDKREAD` |
| `$18` | `T_UDKON` |
| `$19` | `T_UDKOFF` |
| `$1A` | `T_UDCWRITE` |
| `$1B` | `T_UDCREAD` |
| `$1C` | `T_UDCINIT` |
| `$1D` | `T_SPWRITE` |
| `$1E` | `T_SPWRCONT` |
| `$1F` | `T_SPON` |
| `$20` | `T_SPOFF` |
| `$21` | `T_SPREAD` |
| `$22` | `T_ONSTATE` |
| `$23` | `T_OFFREQ` |
| `$24` | `T_LOCATE` |
| `$25` | `T_CURSON` |
| `$26` | `T_CURSOFF` |
| `$27` | `T_TESTKEY` |
| `$28` | `T_TESTCHR` |
| `$29` | `T_SECCLR` |
| `$2A` | `T_DATESET` |
| `$2B` | `T_DISPOFF` |
| `$2C` | `T_DISPON` |
| `$2D` | `T_KBCLR` |
| `$2E` | `T_CLS` |
| `$2F` | `T_HOME` |
| `$30` | `T_UDKDISPON` |
| `$31` | `T_UDKDISPOFF` |
| `$32` | `T_REPEATON` |
| `$33` | `T_REPEATOFF` |
| `$34` | `T_KANASET` |
| `$35` | `T_UDKCONT` |
| `$36` | `T_ALARMREAD` |
| `$37` | `T_BUZZZERO` |
| `$38` | `T_CLICKOFF` |
| `$39` | `T_CLICKON` |
| `$3A` | `T_LOCCLOSE` |
| `$3B` | `T_KEYOUTON` |
| `$3C` | `T_KEYOUTOFF` |
| `$3D` | `T_SPAUTOON` |
| `$3E` | `T_SPAUTOOFF` |
| `$3F` | `T_SLEEP` |
| `$40` | `T_UDKINIT` |
| `$41` | `T_CHARWRITE` |
| `$42` | `T_CHARREAD` |
| `$43` | `T_SCANR` |
| `$44` | `T_SCANL` |
| `$45` | `T_TIMECHK` |
| `$46` | `T_ALMCHK` |

## Vecteurs RST

| RST | Rôle |
|---|---|
| `$00` | point d'arrêt (XP-140F) |
| `$08` | SYNCHR : compare (HL) à l'octet suivant |
| `$10` | CHRGET : A=(HL), HL+1 |
| `$18` | FSIGN : signe de l'accumulateur flottant -> A (vérifié ROM) |
| `$20` | CPHLDE : compare HL et DE |
| `$28` | DEVPUT : A vers le fichier courant |
| `$30` | GETYPE : type de donnée |
| `$38` | lecture dans une table ou fonction du pilote courant (octet en ligne) |
