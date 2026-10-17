# Débogueur

Le débogueur exécute un programme machine **dans l'émulateur**, sur la vraie ROM du X-07. On peut le suivre instruction par instruction, l'arrêter où l'on veut, et regarder ou modifier les registres, la mémoire et les variables.

```sh
python3 x07asm.py debug exemples/bonjour.asm                 # programme assembleur
python3 x07asm.py debug exemples/premiers.bas                # BASIC, compilé au passage
python3 x07asm.py debug exemples/qbasic/tri.qbas             # QuickBASIC, traduit puis compilé
python3 x07asm.py debug prog.bin --org 3000                  # binaire seul (sans étiquettes)
python3 x07asm.py debug exemples/graphisme.bas --fenetre     # avec l'écran du X-07 en direct
```

Le programme est préparé comme sur la machine, par `CLEAR 50,&H…` puis `EXEC`. Le débogueur s'arrête sur la première instruction et attend une commande :

```
Débogueur X-07 : h pour l'aide, q pour quitter.
[départ]
A=00 F=44 -Z-P--  BC=F16B DE=0068 HL=001B  IX=0000 IY=0000 SP=1BCB PC=1C00
> 1C00  DEBUT          CALL  LCDCLS            ; CLS ($CE9E)
(x07) n
A=00 F=44 -Z-P--  BC=F16B DE=0068 HL=001B  IX=0000 IY=0000 SP=1BCB PC=1C03
> 1C03  DEBUT+3        LD    HL,MSG
```

Chaque arrêt affiche :
- les **registres**, et les indicateurs en clair (`S Z H P N C`, `-` quand l'indicateur est à 0) ;
- la **prochaine instruction**, avec son étiquette, les noms des routines et des variables de la ROM, et le commentaire du source.

## Commandes

| Commande | Rôle |
|---|---|
| `c` | continuer jusqu'au prochain point d'arrêt (ou la fin) |
| `s [n]` | pas à pas : n instructions, **en entrant** dans les `CALL` |
| `n [n]` | pas à pas **par-dessus** les `CALL` et `RST` (la routine s'exécute d'un coup) |
| `f` | finir la routine en cours, jusqu'à son `RET` |
| `j ADR` | continuer jusqu'à une adresse |
| `b [ADR]` | poser un point d'arrêt ; sans adresse, la liste |
| `w ADR` | surveiller un octet : arrêt dès qu'il change, en indiquant l'instruction responsable |
| `d ADR`, `d tout` | enlever un point d'arrêt ou une surveillance |
| `r` | tous les registres, y compris `AF'`… `HL'`, `I`, `R`, l'état des interruptions et le nombre d'instructions exécutées |
| `r HL=1234 A=#65 PC=START` | modifier des registres |
| `x ADR [n]` | mémoire en hexadécimal et en texte (n octets, 64 par défaut) |
| `m ADR v [v…]` | écrire des octets |
| `l [ADR] [n]` | désassembler (au PC par défaut, 8 instructions) |
| `p [n]` | pile, avec le nom des adresses de retour |
| `v [NOM]` | variables BASIC du programme compilé : `v` (toutes), `v N`, `v A$`, `v T%(3)` |
| `k TEXTE` | donner des touches au programme (`INKEY$`) ; `\r` pour Entrée |
| `e`, `e points` | écran du X-07 : texte, ou tous les points (graphismes compris) |
| `sym TEXTE` | chercher un symbole (programme ou ROM) |
| `h`, `q` | aide, quitter |

**Entrée seule** répète la dernière commande : on avance ainsi avec `n`, puis Entrée, Entrée…

**Ctrl+C** (ou **F9** dans la fenêtre) interrompt le programme en cours, par exemple une boucle sans fin.

## Adresses et nombres

Une adresse s'écrit :
- en hexadécimal : `3C40`, `$3C40`, `&H3C40`, `0x3C40` ;
- par un **nom** : une étiquette du programme (`BOUCLE`, `DEBUT.ATT`) ou un symbole de la ROM (`INKEY`, `FOUT`, `CSRX`), éventuellement avec un décalage : `BOUCLE+3` ;
- pour un programme BASIC, par sa **ligne** : `ligne 40` (ou `LN_40`).

Les valeurs sont aussi en hexadécimal ; `#` indique le décimal : `r A=#65`. Le nombre d'octets ou d'instructions de `x`, `l`, `s`, `n` et `p` est en décimal.

## Programmes BASIC et QuickBASIC

Un `.bas` (ou `.qbas`) est compilé au passage, avec les numéros de ligne dans les erreurs (option `--debug` du compilateur). Le débogueur connaît alors :
- **les lignes BASIC** : `b ligne 50` s'arrête au début de la ligne 50, et chaque arrêt indique la ligne en cours (`ligne BASIC 50`) ;
- **les variables**, par leur nom BASIC. Les nombres en simple et en double précision sont convertis par la routine `FOUT` de la ROM, comme le ferait `PRINT` :

```
(x07) b ligne 40
point d'arrêt en 3D8F LN_40
(x07) c
[point d'arrêt]  ligne BASIC 40
(x07) v
  N$ = "BONJOUR" (longueur 7)   ($3F81)
  A# = .33333333333333   ($3FD2)
  B! = 2.5   ($3FDA)
  C% = -7   ($3FDE)
  I% = 6   ($3FE0)
(x07) v T%(3)
  T%(3) = 9   ($3F7B)
```

Une ligne QuickBASIC n'a pas de numéro : on s'arrête sur la ligne du programme traduit, que donne `python3 x07asm.py qb FICHIER.qbas`. Voir l'exemple ci-dessous.

## Exemple : déboguer `tri.qbas`

**1. Repérer les lignes à surveiller.** On regarde la traduction, avec `--noms` pour savoir ce que deviennent les variables :

```sh
python3 x07asm.py qb exemples/qbasic/tri.qbas --noms
```

```
  NOTES()                  NO%
  TRIER.I                  I0%
  MOYENNE.S                S
  MOYENNE! (résultat)      M
...
80 FOR I0%=1 TO B%:IF NO%(I0%)<=NO%(I0%+1) THEN 100
90 C%=NO%(I0%):NO%(I0%)=NO%(I0%+1):NO%(I0%+1)=C%:E%=-1     ← le SWAP de Trier
...
150 M=S/N0%                                                  ← le calcul de la moyenne
```

**2. Lancer le débogueur.** Le `.qbas` est traduit et compilé au passage :

```sh
python3 x07asm.py debug exemples/qbasic/tri.qbas
```

**3. S'arrêter à chaque échange du tri :**

```
(x07) b ligne 90
point d'arrêt en 3C0D LN_90
(x07) c
[point d'arrêt]  ligne BASIC 90
(x07) v I0%
  I0% = 1   ($3F98)
(x07) v NO%(1)
  NO%(1) = 12   ($3F7A)
(x07) v NO%(2)
  NO%(2) = 7   ($3F7C)          ← 12 > 7 : c'est bien un échange
(x07) c
[point d'arrêt]  ligne BASIC 90
(x07) v NO%(2)
  NO%(2) = 12   ($3F7C)         ← le premier échange a eu lieu
```

**4. Aller au calcul de la moyenne :**

```
(x07) d tout
(x07) b ligne 150
(x07) c
[point d'arrêt]  ligne BASIC 150
(x07) v S
  S! = 92   ($3FA6)             ← somme des 8 notes
(x07) v N0%
  N0% = 8   ($3FA2)
(x07) f                         ← finir la FUNCTION Moyenne!
[retour de la routine]  ligne BASIC 50
(x07) v M
  M! = 11.5   ($3F9E)           ← son résultat
(x07) c
[fin]
(x07) e
+--------------------+
| 6  7  9  11  12    |
| 14  15  18         |
|Moyenne : 11.5      |
+--------------------+
```

Pour rejouer une suite de commandes sans les taper, on les passe avec `-x` :

```sh
python3 x07asm.py debug exemples/qbasic/tri.qbas -x "b ligne 150;c;v S;v N0%"
```

Le pas à pas avance par **instructions machine**, pas par instructions BASIC : une ligne BASIC en compte souvent une dizaine. D'où l'intérêt des points d'arrêt sur les lignes, et de `c` plutôt que de `n`.

## Avec la fenêtre

Avec `--fenetre`, l'écran du X-07 s'affiche en direct dans une fenêtre. Les commandes du débogueur, elles, se tapent dans le terminal. Le clavier de la fenêtre sert au programme (`INKEY$`, `INPUT`) ; F9 l'interrompt.

Sans fenêtre, les réponses aux `INPUT` sont demandées dans le terminal, et les touches viennent de `-k` ou de la commande `k`. Si le programme attend une touche que personne ne fournit, le débogueur s'arrête et le dit.

## Options

| Option | Rôle |
|---|---|
| `-b ADR` | point d'arrêt dès le départ (répétable) |
| `-x "cmd;cmd;…"` | commandes exécutées d'abord, par exemple `-x "b ligne 40;c;v"`. Si l'entrée n'est pas un terminal, le débogueur s'arrête ensuite : pratique dans un script |
| `-k TOUCHES`, `-i LIGNE` | touches et réponses aux `INPUT`, comme pour `run` |
| `--ram 8\|16\|24` | mémoire de la machine (16 Ko par défaut) |
| `--org`, `--entry` | adresse de chargement d'un `.bin`, adresse de départ |
| `--fenetre`, `--zoom N` | écran dans une fenêtre |

## Limites

- **Interruptions :** une interruption (réception série) s'exécute pendant les pas, comme sur la machine.
- **Routines imitées :** certaines routines de la ROM sont remplacées par du Python (affichage, clavier, T6834 : voir [EMULATEUR.md](EMULATEUR.md)). Entrer dedans avec `s` exécute l'imitation d'un coup.
- **Surveillances :** elles portent sur des octets de la mémoire, pas sur les registres.
- **Pas de retour arrière :** on ne peut pas revenir à une instruction déjà exécutée.
