# Programmes C pour le Canon X-07 (SDCC)

Les programmes C sont compilés par [SDCC](https://sdcc.sourceforge.net/), un compilateur C pour le Z80. Ils deviennent des programmes machine, chargés et lancés comme les autres : `CLEAR 50,&H…`, puis `EXEC &H…`.

```sh
sudo apt install sdcc                                         # une fois (Debian, Ubuntu, WSL)
python3 x07asm.py run exemples/c/bonjour.c --fenetre          # dans la fenêtre
python3 x07asm.py ide exemples/c/bonjour.c                    # éditeur-débogueur
python3 x07asm.py c exemples/c/bonjour.c -f bin,lst           # binaire, listing
python3 x07asm.py send exemples/c/bonjour.c --port /dev/ttyUSB0   # vers la machine
```

Les commandes `run`, `send`, `debug`, `ide` et `emu --charger` acceptent les `.c`. Dans l'IDE, on peut poser des points d'arrêt sur les lignes C, avancer ligne par ligne, et voir les variables globales et `static`.

## Un premier programme

```c
#include <stdio.h>
#include "x07.h"

int main(void)
{
    char nom[13];
    cls();
    printf("Nom ? ");
    input(nom, sizeof nom);
    printf("Bonjour %s !\n", nom);
    return 0;               /* retour au BASIC */
}
```

## La bibliothèque `x07.h`

Elle est compilée avec chaque programme et passe par les routines de la ROM, comme le BASIC.

| Fonction | Rôle |
|---|---|
| `printf`, `puts`, `putchar` | écriture à l'écran (bibliothèque de SDCC). `'\n'` passe à la ligne |
| `cls()`, `locate(col, ligne)` | efface l'écran ; place le curseur (colonne 0-19, ligne 0-3, comme `LOCATE`) |
| `x07_putc(c)`, `x07_puts(s)` | un caractère (codes de contrôle admis), une chaîne |
| `pset(x, y)`, `preset(x, y)`, `line(x1, y1, x2, y2)`, `circle(x, y, r)` | graphismes : x de 0 à 119, y de 0 à 31 |
| `inkey()` | touche tapée, ou 0 si aucune (comme `INKEY$`) |
| `getkey()` | attend une touche |
| `input(buf, max)` | saisit une ligne, avec écho ; rend sa longueur |
| `beep(note, duree)` | comme `BEEP note, durée` : note de 1 à 4095 (192 000/note Hz), durée en 1/20 s |
| `x07_break()` | traite BREAK, la pause, les piles faibles et l'extinction, comme l'interpréteur |
| `PEEK(a)`, `POKE(a, v)`, `inp(port)`, `outp(port, v)` | mémoire et ports |

**BREAK** arrête le programme, qui affiche alors « Break » et revient au BASIC. La touche est vue pendant un affichage et pendant l'attente d'une touche. Dans une longue boucle de calcul sans affichage, appelez `x07_break()` de temps en temps.

## Mémoire

- **Placement :** par défaut, le programme et ses données sont placés **en haut de la RAM**, comme le BASIC compilé. La commande affiche le `CLEAR` à taper. `--org 2000` impose l'adresse.
- **Pile :** le programme garde celle du BASIC, sous lui.
- **Variables globales :** remises à leur valeur de départ (ou à 0) à chaque `EXEC`.
- **Allocation dynamique :** `malloc` réserve 1 Ko de tas (bibliothèque de SDCC).
- **Taille :** `printf` coûte environ 3 Ko. Pour un petit programme, `x07_puts` et `x07_putc` suffisent.

## Ce que le C du X-07 ne fait pas

- **Réels :** `float` est l'IEEE 754 simulé par la bibliothèque de SDCC. C'est lent et encombrant, et ce n'est pas le calcul décimal (BCD) de la ROM. `printf` n'affiche pas les `float`.
- **Un seul fichier source** par programme (plus la bibliothèque `x07.h`).
- **Fichiers en RAM, liaison série :** pas encore dans la bibliothèque.

## Fonctionnement

```
programme.c --sdcc -mz80--> .rel --+
x07asm/c/crt0.s  (démarrage) ------+--sdldz80 (+ z80.lib)--> .ihx --> mémoire du X-07
x07asm/c/x07.c   (bibliothèque) ---+
```

- **`crt0.s`** sauve les registres et la pile du BASIC, initialise les variables, appelle `main`, puis rend la main au BASIC (fin de `main` ou `exit()`). Les zones suivent le code dans cet ordre : `_CODE`, `_INITIALIZER`, `_GSINIT`, `_DATA`, `_INITIALIZED`, puis le tas.
- **Placement automatique :** un premier lien en `$1000` donne la taille, un second place le programme en haut de la RAM.
- **Convention d'appel de SDCC 4 :** premier argument dans A (octet) ou HL (mot), second dans L ou DE, résultat dans A ou DE. Les enveloppes de la ROM, dans `x07.c`, sauvent IX et IY.
- **Lignes C :** elles sont lues dans le listing `.rst` du lien. `LN_n` est l'adresse de la première instruction de la ligne n, pour le débogueur et l'IDE.

## Fichiers

```
x07asm/ccomp.py      appel de SDCC, placement, symboles et lignes
x07asm/c/crt0.s      démarrage
x07asm/c/x07.h, x07.c  bibliothèque d'appui (ROM du X-07)
exemples/c/          bonjour.c (saisie, printf, récursivité), dessin.c (graphismes, son)
tests/test_c.py      compilation et exécution par la ROM (passés sans SDCC)
```
