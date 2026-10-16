# x07basic : compilateur BASIC pour le Canon X-07

Le compilateur traduit un programme BASIC du X-07 en **assembleur Z80**, puis l'outil assemble ce source en **binaire**. Le programme compilé se lance sur la machine par `EXEC`.

Il reproduit le BASIC du X-07 **à l'identique**, nombres décimaux compris. Les calculs flottants passent par les routines de la ROM elle-même, si bien que les arrondis, les messages d'erreur et la mise en page de `PRINT` sont ceux de la machine. Chaque comportement a été comparé à l'interpréteur de la vraie ROM (voir [Vérification](#vérification)).

```sh
python3 x07asm.py basic exemples/premiers.bas        # -> .asm et .bin
```

## Commandes

### `basic` : compiler

| Option | Rôle |
|---|---|
| `-f asm,bin,hex,lst,txt,bas` | fichiers produits (défaut : `asm,bin`). `bas` crée `NOM_chargeur.bas`, sans écraser votre source |
| `--ram 8\|16\|24` | mémoire du X-07 en Ko (défaut : 8) |
| `--org auto\|ADR` | implantation. `auto` place le programme **en haut de la RAM**, ce qui laisse le maximum de place au BASIC. Les 14 derniers octets (`$3FF2`-`$3FFF` avec 16 Ko) restent à la ROM, qui y garde une signature : le programme et ses variables finissent au plus en `$3FF1` |
| `--default d\|f\|i` | type des variables sans suffixe : `d` double (défaut, comme le X-07), `f` simple, `i` entier |
| `--strlen N` | longueur maximale des chaînes (défaut : 80, au plus 254) |
| `--debug` | les erreurs indiquent la ligne, comme le X-07 (`/0 Error in 20`) |
| `--no-break` | supprime le test de BREAK et OFF dans les boucles (un peu plus rapide) |
| `--no-bounds` | supprime le contrôle des indices de tableaux |

L'outil affiche ensuite les deux commandes à taper sur le X-07, par exemple `CLEAR 50,&H1A3F` puis `EXEC &H1A40`.

### Essayer, puis envoyer au X-07

- **Essayer sur le PC :** `run` lance le programme compilé sur le X-07 émulé. `emu` fait exécuter le même programme par l'interpréteur de la ROM, pour comparer. Voir [EMULATEUR.md](EMULATEUR.md).
- **Envoyer à la machine :** `send` passe par le câble série FT232RL. Voir [TRANSFERT.md](TRANSFERT.md).

Le parcours complet, de l'écriture au lancement sur la machine, est décrit dans le [guide de démarrage](../DEMARRAGE.md).

## Types et calcul

Les types sont **ceux du X-07**, ce qui a été vérifié dans la ROM :

| Suffixe | Type | Taille | Calcul dans le programme compilé |
|---|---|---|---|
| `%` | entier, −32768 à 32767 | 2 octets | dans les registres : **très rapide** |
| `!` | simple précision, 6 chiffres | 4 octets | routines BCD de la ROM |
| `#` | double précision, 14 chiffres | 8 octets | routines BCD de la ROM |
| `$` | chaîne | `--strlen`+1 octets | bibliothèque du compilateur |

- **Sans suffixe, une variable est en double précision** : la ROM le fixe à chaque `RUN`. `DEFINT`, `DEFSNG`, `DEFDBL` et `DEFSTR` changent ce type pour une plage de lettres.
- **Pour la vitesse, utilisez des entiers.** `DEFINT A-Z` en tête de programme, ou des variables `%` pour les compteurs de boucle et les indices.

| Programme d'essai | Gain du compilé sur l'interprété |
|---|---|
| boucle en entiers (`DEFINT`) | **× 30** |
| crible d'Ératosthène (`DEFINT`) | **× 27** |
| traitement de chaînes | × 7 |
| entiers et doubles mêlés (`S#=S#+I%*I%`) | × 5 |
| boucle en double précision (défaut) | × 1,5 |
| `SIN`, `SQR`… | × 1 (le temps est passé dans la ROM) |

Les règles de calcul sont celles de la ROM, puisque c'est elle qui calcule :

- `1/3` donne un double, même entre entiers. `\` et `MOD` donnent des entiers.
- Tout calcul avec un flottant est fait en double, puis **arrondi à 6 chiffres au rangement** dans une variable `!`.
- **`CINT` tronque**, comme le X-07 (`CINT(2.6)` = 2), et l'affectation à une variable `%` aussi.
- Un **dépassement entier passe en double** quand le résultat va dans un nombre : `PRINT 30000+30000` affiche 60000. Rangé dans une variable `%`, il donne `OV Error`, comme sur le X-07.
- Les constantes sont converties à la compilation **par la routine de la ROM**. Leurs particularités sont donc conservées : `999999.5!` vaut 100000 sur le X-07, la retenue n'ajustant pas l'exposant.

## Langage reconnu

**Instructions :**

- `LET` (facultatif), `PRINT` / `?` (avec `;`, `,`, `TAB()`, et `SPC()` en extension)
- `INPUT ["texte";] v,...` (le X-07 exige `;` après le texte)
- `IF … THEN … ELSE …`, `IF … GOTO n`
- `GOTO`, `GOSUB`, `RETURN`, `ON x GOTO/GOSUB`
- `FOR … TO … STEP` (variables entières ou flottantes), `NEXT [v,…]`, `WHILE`/`WEND` (extension)
- `DIM` (dimensions constantes, plusieurs indices, tous types), `DATA`, `READ`, `RESTORE [n]`
- `DEFFN`, en un mot comme sur le X-07 : numérique, avec ou sans paramètres
- `DEFINT`, `DEFSNG`, `DEFDBL`, `DEFSTR`, `END`, `STOP`, `REM`, `'`
- `CLS`, `LOCATE x,y`, `BEEP [ton,durée]`
- `PSET(x,y)`, `PRESET(x,y)`, `LINE(x1,y1)-(x2,y2)`, `CIRCLE(x,y),r`
- `FONT$(code)=chaîne` : caractère redéfini (codes `&H80`-`&H9F` et `&HE0`-`&HFF`). La chaîne contient **8 nombres** séparés par des virgules, un par ligne de 6 points (bit 7 à gauche), lus par la ROM comme sur la machine. Écrivez-les en décimal ou avec `&H` : `"F8"` serait lu comme la variable F8.
- `POKE`, `OUT`, `EXEC adr`

`CLEAR` est ignoré.

**Fonctions :**

- numériques : `ABS SGN INT FIX CINT CSNG CDBL SQR LOG EXP SIN COS TAN ATN RND PEEK INP LEN ASC VAL POINT STICK STRIG CSRLIN POS`
- chaînes : `LEFT$ RIGHT$ MID$ CHR$ STR$ HEX$ STRING$ INKEY$ FONT$`

`FONT$(code)` rend le motif d'un caractère (code `&H20` à `&HFF`) sous la forme `[xx,xx,xx,xx,xx,xx,xx,xx]` : 25 caractères, en hexadécimal **sans** `&H`. On ne peut donc pas le réutiliser tel quel dans `FONT$(code)=`. Comme la ROM, si le premier octet est inférieur à `&H10`, son zéro de tête est `CHR$(0)` et non `"0"` : `PRINT` montre alors `[5,10,…]`.

**Opérateurs :** `+ - * / \ MOD ^`, comparaisons, `NOT AND OR XOR EQV IMP`, concaténation `+`.

Le source peut être écrit « tassé » comme sur le X-07 : `FORI=1TO10:PRINTI;:NEXT`.

## Comportements du X-07 reproduits

Ces comportements, parfois surprenants, ont été observés sur l'interpréteur de la ROM. Le compilateur les reproduit :

- **Virgule de `PRINT` :** les zones font 14 colonnes. Sur l'écran de 20 colonnes, `PRINT A,B` affiche donc B à la ligne suivante.
- **Nombres en fin de ligne :** un nombre qui ne tient pas dans la place restante passe à la ligne suivante.
- **`TAB(n)` sur l'écran** déplace le curseur, éventuellement **en arrière**, sans écrire d'espaces.
- **`FOR I=5 TO 1`** exécute la boucle une fois ; I vaut ensuite 6.
- **`READ` d'un texte non numérique** dans une variable numérique donne `SN Error`, à la ligne du `DATA`.
- **`RND`** repart de la même suite à chaque lancement, comme après `RUN`.
- **Messages d'erreur :** ceux du X-07 (`OV Error`, `/0 Error`, `FC Error`, `BS Error`, `OD Error`, `SN Error`, `Break`), suivis de ` in n` avec `--debug`.

## Différences avec l'interpréteur

- **Un dépassement entier dans une comparaison ou un indice** donne `OV Error`, là où l'interpréteur calculerait en double. C'est le prix des entiers rapides.
- **`FOR` / `NEXT`** sont appariés à la compilation, dans l'ordre du texte.
- **Chaînes** limitées à `--strlen` caractères.
- **`INPUT` d'une chaîne** s'arrête à la virgule. Une saisie numérique incorrecte donne 0 au lieu de `?Redo from start`.
- **Noms de variables** distingués sur toute leur longueur. Comme sur le X-07, un nom **ne doit pas contenir de mot-clé** (`TOTAL` se lit `TO TAL`).
- **Tableau non déclaré :** il est créé avec 11 éléments par dimension ; le compilateur vous prévient.

**Non géré :** `ON ERROR`, `RESUME`, `PRINT USING`, `INSTR`, `LINE INPUT`, fichiers (`INIT#`), `DEFFN` sur des chaînes, `MID$` à gauche du signe `=`.

## Vérification

Le simulateur exécute la vraie ROM : démarrage à froid, puis l'interpréteur BASIC. Il sert de **référence**. Les tests (`tests/test_basic.py`) font exécuter chaque programme par l'interpréteur de la ROM, puis le compilent et le lancent par `EXEC`. Ils exigent que l'affichage et l'écran soient **identiques au caractère près**.

Les tests couvrent :

- des programmes ciblés : types, fonctions, boucles, mise en page, chaînes, tableaux, `DATA`, `INPUT`, `DEFFN`, erreurs ;
- 150 expressions flottantes et 144 expressions entières tirées au hasard ;
- le comportement de la machine : BREAK, OFF, registres et crochet d'erreur rétablis.

Les routines de la ROM utilisées, et leur façon d'être appelées, ont été établies en désassemblant la ROM, puis confirmées par ces essais. Elles sont marquées « vérifié ROM » dans `x07asm/x07sym.py` et listées dans [ROM.md](ROM.md). Les erreurs des livres découvertes en chemin sont rassemblées dans [l'errata](../ref_docs/ERRATA.md).

Il reste à confirmer le tout sur la machine ; `exemples/test_x07.bas` est fait pour cela.

## Organisation en mémoire

```
ORG   code du programme + bibliothèque (seules les routines utilisées)
      chaînes et nombres constants, DATA
VARS  variables, tableaux, tampons (non chargés, remis à zéro au lancement)
```

- **Au lancement,** le programme sauvegarde tous les registres et le pointeur de pile. Il détourne aussi le crochet d'erreur de la ROM (`$00AB`), pour afficher lui-même les erreurs de calcul.
- **À la sortie,** par `END`, une erreur ou BREAK, il rétablit tout et revient au BASIC.

## Fichiers

```
x07asm/basic.py     analyse lexicale, analyse syntaxique, génération de code
x07asm/runtime.py   bibliothèque d'exécution (assembleur Z80)
tests/test_basic.py comparaisons avec l'interpréteur de la ROM
exemples/           devine.bas, premiers.bas, flottants.bas, table.bas, test_x07.bas
```
