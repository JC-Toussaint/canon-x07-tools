# x07asm : assembleur et désassembleur pour le Canon X-07

Assembleur et désassembleur Z80 pour le **Canon X-07**, dont le processeur NSC800 exécute le jeu d'instructions du Z80.
Écrit en Python 3, sans dépendance.

- Les **698 instructions documentées** du Z80, y compris les préfixes CB, ED, DD, FD, DDCB et FDCB.
- **Symboles du X-07 prédéfinis** : routines de la ROM, variables système, ports F0–F7 et commandes du T6834. Ils sont tirés des *Mystères du X-07* et des *Applications en assembleur*.
- **Chargeur BASIC** généré automatiquement, avec une somme de contrôle par ligne de DATA.
- Le désassembleur produit un **source réassemblable à l'identique**. Il gère l'octet en ligne qui suit `RST 08`.

L'outil comprend aussi :
- un **compilateur BASIC** (entiers, simple et double précision, chaînes) : [COMPILATEUR.md](COMPILATEUR.md) ;
- un **émulateur** qui exécute la vraie ROM : [EMULATEUR.md](EMULATEUR.md) ;
- un **débogueur** : points d'arrêt, pas à pas, registres, dans l'émulateur : [DEBOGUEUR.md](DEBOGUEUR.md) ;
- un **traducteur QuickBASIC** vers le BASIC du X-07 (étude, prototype) : [QBASIC.md](QBASIC.md) ;
- le **transfert par le câble série** : [TRANSFERT.md](TRANSFERT.md).

La carte des routines de la ROM est dans [ROM.md](ROM.md). Pour un premier parcours complet, voir le [guide de démarrage](../DEMARRAGE.md).

## Utilisation rapide

```sh
python3 x07asm.py asm exemples/caso.asm -f bin,lst,bas   # assembler
python3 x07asm.py dis exemples/caso.bin --org 1C00 -t    # désassembler
python3 x07asm.py sym T6834                              # chercher un symbole
python3 x07asm.py basic exemples/premiers.bas            # compiler du BASIC
python3 x07asm.py run exemples/devine.bas                # l'essayer sur PC
python3 x07asm.py emu exemples/devine.bas                # le BASIC du X-07 (vraie ROM)
python3 x07asm.py emu exemples/graphisme.bas --fenetre   # l'écran de 120 x 32 points
python3 x07asm.py qb exemples/qbasic/tri.qbas            # QuickBASIC -> BASIC du X-07
python3 x07asm.py run exemples/qbasic/rapide.qbas --direct   # QuickBASIC compilé directement
python3 x07asm.py debug exemples/bonjour.asm              # débogueur pas à pas
python3 x07asm.py send exemples/devine.bas -p /dev/ttyUSB0   # envoi par le câble FT232RL
python3 -m unittest discover -s tests                    # tests
```

## Assembleur : `asm`

```
python3 x07asm.py asm SOURCE [-o BASE] [-f FORMATS] [-D NOM=VAL] [--no-x07]
```

| Format (`-f`) | Fichier | Contenu |
|---|---|---|
| `bin` | `.bin` | binaire brut, de l'adresse la plus basse à la plus haute |
| `lst` | `.lst` | listing : adresses, octets, source, table des symboles |
| `hex` | `.hex` | Intel HEX, avec l'adresse de lancement |
| `bas` | `.bas` | **chargeur BASIC** à taper ou à transférer sur le X-07 |
| `txt` | `.txt` | vidage hexadécimal pour l'« entreur de codes » du livre |

Par défaut : `bin,lst`.

### Syntaxe

```asm
; commentaire
        ORG  $1C00           ; adresse d'implantation
NOM     EQU  $20             ; constante (ou NOM = $20)
DEBUT:  LD   HL,MSG          ; étiquette avec ou sans « : »
.BCL    DJNZ .BCL            ; étiquette locale (rattachée à DEBUT)
        CALL INKEY           ; symbole X-07 prédéfini ($C90A)
        IN   A,(P_MODE)      ; port $F4
        LD   A,(IX+2)
        EX   AF,AF'
MSG:    DZ   "BONJOUR"       ; chaîne terminée par 00
```

- **Nombres** : `123`, `$1C00`, `&H1C00`, `0x1C00`, `1C00H`, `%1010`, `&B1010`, `'A'`. Le `$` seul vaut l'adresse courante.
- **Opérateurs** : `+ - * / MOD % << >> & | ^ ~`, `AND OR XOR NOT`, `HIGH()` et `LOW()`.
- **Directives** : `ORG`, `EQU`/`=`, `DB`/`DEFB`, `DW`/`DEFW`, `DM`/`DEFM`, `DZ`, `DS`/`DEFS n[,val]`, `ALIGN`, `ENTRY` (adresse de lancement), `INCLUDE`, `INCBIN`, `IF`/`ELSE`/`ENDIF`, `ASSERT`, `END`.
- Les étiquettes ne tiennent pas compte de la casse.
- Une étiquette du programme **remplace** un symbole X-07 de même nom.
- Les formes `ADD B` et `SUB A,B` sont acceptées.

### Implantation sur le X-07

Les programmes BASIC commencent en `$0553`. Pour réserver la place du code, il faut placer le haut de la zone BASIC juste en dessous avec `CLEAR 50,&H<ORG-1>`. Le chargeur `.bas` contient ce `CLEAR`.

Exemples :

- `ORG $1C00` avec `CLEAR 50,&H1BFF` ;
- en haut de 16 Ko, `ORG $3C10` comme REFBAS.

Le chargeur lit des lignes `DATA adresse,nombre,octets…,somme` et s'arrête sur `ERREUR LIGNE n` si une ligne a été mal tapée. Il annonce enfin la commande `EXEC &H…`.

> ⚠️ Le chargeur BASIC occupe lui-même de la mémoire à partir de `$0553` (environ 40 octets par ligne de DATA). Pour un gros programme implanté bas (`$0800`), l'outil vous avertit : implantez le code plus haut, ou utilisez le vidage `-f txt` avec l'entreur de codes.

## Désassembleur : `dis`

```
python3 x07asm.py dis ENTRÉE [--org ADR] [-t] [-e ADR]... [--data DEB-FIN[:b|w|t]]...
                             [-l] [-o SORTIE.asm] [--labels FICHIER] [--start ADR] [--end ADR]
```

**Entrées acceptées** (le format est détecté automatiquement) :

- binaire `.bin` ou `.rom`, avec `--org` ;
- Intel HEX ;
- chargeur `.bas` produit par x07asm ;
- lignes BASIC `DATA 11,96,E7,...`, en hexadécimal, ou en décimal avec `--decimal` (format de LMDATA) ;
- vidage `1C00 : 11 96 E7 ...`.

**Options :**

- **Balayage linéaire** (par défaut) : tout est décodé comme du code, sauf les zones `--data`.
- **`-t` / `-e ADR`** : suit le flot d'exécution depuis les points d'entrée. Ce qui n'est jamais atteint devient `DB`/`DM`, et les chaînes de 4 caractères ou plus sont détectées.
- **`--data 1C61-1C67:b`** déclare une zone de données. Les types sont `b` (octets), `w` (mots, étiquetés s'ils pointent dans le programme) et `t` (texte).
- **`-l`** : listage avec adresses et octets, pour la lecture (non réassemblable).
- **`--labels`** : vos propres noms, sous la forme `NOM EQU $1C54` (une par ligne).
- **`--no-rst8`** : ne traite pas l'octet qui suit `RST 08` et `RST 38` comme une donnée. Dans la ROM du X-07, `RST 08` (SYNCHR) est suivi de l'octet à comparer, et `RST 38` du numéro d'une entrée de table ou d'une fonction du pilote courant.

Le désassembleur nomme les cibles internes `Lxxxx` (code) et `Dxxxx` (données). Les appels à la ROM prennent leur nom symbolique (`CALL DEVOPEN`), avec une ligne `EQU` en tête et le rôle de la routine en commentaire.

## Organisation

```
x07asm.py           point d'entrée
x07asm/z80.py       table unique des instructions (utilisée dans les deux sens)
x07asm/asm.py       assembleur deux passes
x07asm/dis.py       désassembleur (linéaire ou suivi du flot)
x07asm/expr.py      évaluateur d'expressions
x07asm/x07sym.py    symboles du X-07
x07asm/formats.py   bin, Intel HEX, chargeur BASIC, vidage, DATA
x07asm/basic.py     compilateur BASIC (voir COMPILATEUR.md)
x07asm/debug.py     débogueur (voir DEBOGUEUR.md)
x07asm/qbasic.py    traducteur QuickBASIC -> BASIC du X-07 (voir QBASIC.md)
x07asm/qbcomp.py    compilation directe QuickBASIC -> assembleur (voir QBASIC.md)
x07asm/runtime.py   bibliothèque d'exécution du compilateur
x07asm/sim.py       simulateur Z80 pour essayer les programmes sur PC
x07asm/emu.py       démarrage de la vraie ROM : le BASIC du X-07 sur PC
exemples/           caso.asm (livre, p. 60), bonjour.asm, *.bas
tests/              tests unitaires
```

## Vérifications effectuées

- `exemples/caso.asm` (sortie cassette, *Applications en assembleur* p. 60) s'assemble **octet pour octet** comme les DATA publiés dans le livre.
- Aller-retour exhaustif : chaque instruction est encodée, décodée, remise en texte puis réassemblée.
- 5 000 mémoires aléatoires ont été désassemblées puis réassemblées à l'identique, en mode linéaire et en mode trace, avec des zones de données.
- Des encodages ont été comparés aux tables de référence du Z80.

## Limites

- Les instructions **non documentées** du Z80 (`SLL`, `IXH`, `IXL`…) ne sont pas assemblées. Le désassembleur les rend en `DB`. Le NSC800 ne les garantit d'ailleurs pas.
- Pas de macros.
- Les adresses des routines viennent des livres, qui contiennent quelques incohérences (signalées dans `X07_mysteres_reference.tex`, par exemple RST 18 : `$C9C7` ou `$C937`). Vérifiez-les sur la machine pour les cas critiques.
