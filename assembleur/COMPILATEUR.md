# x07basic : compilateur BASIC pour le Canon X-07

Le compilateur traduit un programme BASIC du X-07 en **assembleur Z80**, puis l'outil assemble ce source en **binaire**. Le programme compilé se lance sur la machine par `EXEC`.

Il s'adresse surtout aux programmes qui doivent aller vite (jeux, calculs, graphismes). Il travaille sur des **nombres entiers**.

```sh
python3 x07asm.py basic exemples/premiers.bas                   # -> .asm et .bin
python3 x07asm.py basic jeu.bas -f asm,bin,lst,bas --ram 16     # tous les formats
python3 x07asm.py run exemples/devine.bas                       # essai sur PC (simulateur)
```

## Commande `basic`

| Option | Rôle |
|---|---|
| `-f asm,bin,hex,lst,txt,bas` | fichiers produits (défaut : `asm,bin`). `bas` crée `NOM_chargeur.bas`, sans écraser votre source |
| `--ram 8\|16\|24` | mémoire du X-07 en Ko (défaut : 8) |
| `--org auto\|ADR` | implantation. `auto` place le programme **en haut de la RAM**, ce qui laisse le maximum de place au BASIC |
| `--strlen N` | longueur maximale des chaînes (défaut : 80, au plus 254) |
| `--debug` | les messages d'erreur indiquent la ligne (`?DIV0 LIGNE 20`) |
| `--no-break` | supprime le test de la touche BREAK dans les boucles (un peu plus rapide) |
| `--no-bounds` | supprime le contrôle des indices de tableaux |

L'outil affiche ensuite les deux commandes à taper sur le X-07, par exemple `CLEAR 50,&H1A3F` puis `EXEC &H1A40`.

## Commande `run` (simulateur)

`run` exécute le programme compilé sur un **processeur Z80 simulé**. Les routines de la ROM du X-07 sont imitées en Python : écran de 20×4, INKEY$, INPUT et commandes graphiques du T6834. L'écran final est affiché à la fin.

```sh
python3 x07asm.py run devine.bas -i 50 -i 25     # lignes pour INPUT
python3 x07asm.py run jeu.bas -k "ZZQ\r"         # touches pour INKEY$
```

Sans `-i`, les INPUT sont demandés au clavier du PC. Le simulateur ne remplace pas un essai sur la machine (voir « À vérifier » plus bas).

## Langage reconnu

**Instructions :**

- `LET` (facultatif), `PRINT` / `?` (avec `;`, `,`, `TAB()`, `SPC()`)
- `INPUT ["texte";] v,...` (avec `,` au lieu de `;` après le texte, pas de « ? »)
- `IF … THEN … ELSE …`, `IF … GOTO n`
- `GOTO`, `GOSUB`, `RETURN`, `ON x GOTO/GOSUB`
- `FOR … TO … STEP`, `NEXT [v,…]`, `WHILE` / `WEND` (extension)
- `DIM` (dimensions constantes, plusieurs indices), `DATA`, `READ`, `RESTORE [n]`
- `DEF FNx(a,b)=expr` (numérique), `END`, `STOP`, `REM`, `'`
- `CLS`, `LOCATE x,y`, `BEEP [ton,durée]`
- `PSET(x,y)`, `PRESET(x,y)`, `LINE(x1,y1)-(x2,y2)`, `CIRCLE(x,y),r`
- `POKE`, `OUT`, `EXEC adr`

`CLEAR`, `DEFINT`, `DEFSNG` et `DEFDBL` sont ignorés.

**Fonctions :**

- numériques : `ABS SGN INT FIX CINT RND PEEK INP LEN ASC VAL POINT STICK STRIG CSRLIN POS`
- chaînes : `LEFT$ RIGHT$ MID$ CHR$ STR$ HEX$ STRING$ INKEY$`

**Opérateurs :** `+ - * / \ MOD ^`, comparaisons, `NOT AND OR XOR`, concaténation `+`.

Le source peut être écrit « tassé » comme sur le X-07 : `FORI=1TO10:PRINTI;:NEXT`.

## Différences avec le BASIC du X-07

- **Entiers seulement**, de −32768 à 32767. `/` est une division entière tronquée, comme `\`. Pas de `SIN`, `SQR`, etc. Un dépassement fait reboucler la valeur, sans erreur `OV`. Les nombres de 32768 à 65535 sont acceptés pour les adresses (`PEEK(&HC000)`).
- `RND(n)` donne un entier de 0 à n−1.
- Les comparaisons valent −1 (vrai) ou 0 (faux), comme sur le X-07. `POINT(x,y)` vaut −1 si le point est allumé, sinon 0.
- **FOR / NEXT** sont appariés à la compilation, dans l'ordre du texte. La boucle s'exécute au moins une fois.
- Les chaînes sont limitées à `--strlen` caractères ; au-delà, elles sont tronquées.
- `INPUT` d'une chaîne s'arrête à la virgule.
- S'il manque des valeurs à un `INPUT`, les variables restantes valent 0 ou "". Il n'y a pas de `?Redo`.
- Les noms de variables sont distingués sur **toute leur longueur**. `A` et `A%` sont deux variables différentes.
- Comme sur le X-07, un nom **ne doit pas contenir de mot-clé**. `TOTAL` se lit `TO TAL`, `SCORE` se lit `SC OR E`.
- Un tableau non déclaré est créé avec 11 éléments par dimension (indices de 0 à 10) ; le compilateur vous prévient.
- **Erreurs à l'exécution :** `?DIV0`, `?INDICE` (indice hors du tableau), `?DATA` (plus de DATA) et `?BREAK`. Le programme s'arrête et rend la main au BASIC.

**Non géré :** nombres décimaux, `ON ERROR`, `RESUME`, `PRINT USING`, `INSTR`, `LINE INPUT`, fichiers (`INIT#`, `OPEN`), `DEF FN` sur des chaînes, `CALL`.

## Organisation en mémoire

```
ORG   code du programme + bibliothèque (seules les routines utilisées)
      chaînes constantes, DATA
VARS  variables, tableaux, tampons (non chargés, remis à zéro au lancement)
```

Le programme sauvegarde tous les registres et le pointeur de pile. `END`, une erreur ou BREAK restaurent tout et reviennent au BASIC.

Le fichier `.bin` ne contient que le code. Les variables sont réservées au-dessus du code et ne sont pas transférées.

## Vérifié dans la ROM

Toutes les routines de la ROM que le compilateur appelle ont été contrôlées dans le vidage `ROM_x07/x07.bin` (BASIC en `$B000-$FFFF`). Il s'agit d'une lecture du code de la ROM, pas encore d'un essai sur la machine.

| Point | Ce que fait la ROM (et donc le compilateur) |
|---|---|
| Affichage | `$C1BE` conserve tous les registres. CR (13) ramène en colonne 1, LF (10) descend d'une ligne |
| Curseur | **`$B8` = ligne, `$B9` = colonne, comptées à partir de 1** (le livre inverse X et Y). `LOCATE x,y` appelle `$C164` avec H = x+1 et L = y+1, comme le `LOCATE` de la ROM (`$E212`). `CSRLIN` = `($B8)−1`, `POS` = `($B9)−1` |
| INPUT | `$EBF2`/`$EBFF` rendent HL = `$00D4` et un tampon terminé par 00. **C=1 signale BREAK** : le programme s'arrête alors sur `?BREAK` |
| BREAK, OFF | les boucles reproduisent `$C000` de l'interpréteur : bit 7 de `$2B` → extinction (`$C5A6`), bit 2 → pause jusqu'à une touche, bits 1 et 3 → message de piles faibles (`$C06C`), bit 0 → arrêt et `AND $FA` |
| INKEY | `$C90A` : Z=1 sans touche, registres conservés |
| BEEP t,d | `$C2DF` avec IY = ton et H = durée, exactement comme `BEEP` de la ROM |
| STICK, STRIG | commande `$82` puis `AND $0F` ; `STRIG(0)` = `$84` (espace), `STRIG(1)` = `$83` (F6), réponse inversée par `CPL` (−1 = enfoncée). Le tampon du T6834 est vidé ensuite (`$C0BD`) |
| Graphiques | PSET `$11`, PRESET `$12`, POINT `$10` (`CPL` de la réponse), LINE `$14`, CIRCLE `$15` |

`exemples/test_x07.bas` reste utile pour un premier essai sur la vraie machine.

Pour relire la ROM avec le désassembleur (le fichier a un octet `00` en trop à la fin, ignoré tant que `--end` reste sous `$10000`) :

```sh
python3 x07asm.py dis ../ROM_x07/x07.bin --org B000 --start E212 --end E242 -l
```

## Fichiers

```
x07asm/basic.py     analyse lexicale, analyse syntaxique, génération de code
x07asm/runtime.py   bibliothèque d'exécution (assembleur Z80)
x07asm/sim.py       simulateur Z80 + imitation de l'écran, du clavier et du T6834
tests/test_basic.py tests (dont 300 expressions aléatoires comparées à un calcul de référence)
exemples/           devine.bas, premiers.bas, test_x07.bas
```
