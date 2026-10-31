# Turbo Pascal simplifié pour le Canon X-07

Un sous-ensemble de **Turbo Pascal 3.0**, compilé en code machine pour le X-07. Le réel (`real`) est en **double précision** (14 chiffres), et les `record` sont pris en charge.

```sh
python3 x07asm.py run exemples/pascal/fiches.pas --fenetre    # compilé, dans la fenêtre
python3 x07asm.py run exemples/pascal/hanoi.pas               # sortie dans le terminal
python3 x07asm.py ide exemples/pascal/fiches.pas              # éditeur-débogueur
python3 x07asm.py pas exemples/pascal/fiches.pas              # QuickBASIC produit, à examiner
python3 x07asm.py send exemples/pascal/fiches.pas --port /dev/ttyUSB0   # vers la machine
python3 x07asm.py emu --fenetre --charger exemples/pascal/fiches.pas    # puis EXEC &H...
```

Les programmes Pascal portent l'extension **`.pas`**. Les commandes `run`, `basic`, `send`, `debug`, `ide` et `emu --charger` les acceptent. `emu` sans `--charger` les refuse : il tape un programme BASIC dans la ROM, et un programme Pascal n'en est pas un.

## Principe

```
Pascal (.pas)  --pascal.py-->  QuickBASIC  --qbcomp-->  assembleur Z80  -->  X-07
```

Le programme Pascal est **traduit en QuickBASIC**, puis compilé directement par la compilation directe du QuickBASIC (`qbcomp`, voir [QBASIC.md](QBASIC.md)). Le générateur de code, vérifié contre la ROM, sert donc tel quel : calculs en virgule flottante, chaînes, récursivité, tableaux passés par adresse.

La commande `pas` écrit le QuickBASIC produit (`NOM_pas.qbas`), pour voir ce que devient chaque instruction. Les messages d'erreur, le débogueur et l'éditeur parlent en **lignes du programme Pascal**.

Dans l'éditeur-débogueur (`ide`), l'onglet *Variables* montre les **noms Pascal** : `Trier.i` pour une variable locale, `l.age(1..4)` pour un champ de tableau de records, avec les indices du programme, et `Trier.l.age() -> l.age()` pour un tableau reçu en paramètre. Les variables de la bibliothèque d'appui y sont cachées.

## Le langage

| Élément | Remarques |
|---|---|
| `program`, `uses` | `uses` est ignoré |
| `const` | constantes, et constantes typées (`Bonus: integer = 7`), qui sont des variables initialisées ; aussi pour un tableau : `Notes: array[1..4] of integer = (262, 294, 330, 349)`, imbriqué pour plusieurs dimensions |
| `type`, `var` | |
| `integer`, `byte` | entier de 16 bits (-32 768 à 32 767). `longint` et `word` aussi, avec un avertissement |
| `real` | **double précision du X-07** (14 chiffres, calcul décimal). `single` et `double` aussi |
| `boolean`, `char`, `string[n]` | `true` vaut -1 en interne, et `ord(true)` vaut bien 1 |
| types énumérés `(rouge, vert, bleu)`, intervalles `1..10` | |
| `array[a..b, c..d] of ...` | bornes quelconques, y compris négatives ou des caractères (`array['a'..'z']`) |
| `record ... end` | imbriqués, tableaux de records, records contenant des tableaux ; `with` |
| `if`, `while`, `repeat`, `for ... to / downto`, `case ... of ... else` | |
| `procedure`, `function`, `forward` | paramètres par valeur et `var` (traduits par un argument QuickBASIC entre parenthèses, ou par la variable seule), récursivité, `exit` |
| `x in [constantes]` | pour tester une valeur : `c in ['a'..'z', '_']` |

### Entrées, sorties, chaînes, calculs

| Turbo Pascal | Sur le X-07 |
|---|---|
| `write`, `writeln` | comme Turbo Pascal : entiers sans espace, `x:n` à droite sur n colonnes, réels en notation scientifique ` 1.2345678900E+03`, `x:n:d` en virgule fixe, booléens `TRUE` / `FALSE` |
| `read`, `readln` | une valeur par ligne tapée ; `read(kbd, c)` lit une touche sans l'afficher |
| `KeyPressed`, `ReadKey` | `KeyPressed` ne consomme pas la touche, que `ReadKey` lit ensuite |
| `ClrScr`, `GotoXY(colonne, ligne)`, `WhereX`, `WhereY` | à partir de 1, comme Turbo Pascal |
| `Delay(ms)`, `Sound(f)`, `NoSound` | `Sound(440); Delay(500); NoSound` joue une note (BEEP du X-07, par pas de 50 ms). Sans son, `Delay` est une boucle d'attente approximative |
| `length`, `copy`, `concat`, `pos`, `upcase`, `insert`, `delete`, `str`, `val`, `s[i]` | |
| `abs`, `sqr`, `sqrt`, `sin`, `cos`, `arctan`, `exp`, `ln`, `trunc`, `round`, `frac`, `int`, `odd`, `pi` | |
| `ord`, `chr`, `succ`, `pred`, `inc`, `dec`, `lo`, `hi` | |
| `random`, `random(n)`, `randomize` | |
| `div`, `mod`, `and`, `or`, `xor`, `not`, `shl`, `shr` | `shl` et `shr` avec un décalage constant |
| `mem[adresse]`, `port[n]` | `PEEK` / `POKE`, `INP` / `OUT` |
| `halt` | |

### Propre au X-07

| Procédure | Rôle |
|---|---|
| `Plot(x, y)`, `Plot(x, y, 0)` | allume ou éteint un point (écran de 120 × 32 points) |
| `Draw(x1, y1, x2, y2)`, `Draw(..., 0)` | trace ou efface une ligne |
| `Circle(x, y, r)` | trace un cercle |
| `Beep(note, durée)` | le `BEEP` du X-07 |

## Les records

Le X-07 n'a pas de structures : chaque **champ** devient une variable à part entière.

| Pascal | Devient |
|---|---|
| `p: Point` (champs `x`, `y`) | deux variables `P.X#` et `P.Y#` |
| `t: array[1..5] of Point` | deux tableaux `T.X#` et `T.Y#` |
| `p.pos.x` (record imbriqué) | `P.POS.X#` |
| `q := p` | une copie champ par champ (avec des boucles pour un tableau contenu) |
| `procedure P(var r: Point)` | un paramètre par champ, par adresse |

Les records gardent ainsi leur sens exact, y compris dans une procédure récursive.

## Ce qui n'est pas pris en charge

- **`set`**, sauf dans un test `x in [...]` avec des constantes.
- **Pointeurs**, `new`, `dispose`, `nil`.
- **Fichiers** (`text`, `file of`, `assign`…).
- **Procédures imbriquées** dans une autre procédure : il faut les déclarer au niveau du programme.
- `goto`, `label` ; records à partie variable (`case` dans un record).
- **Fonction qui rend un tableau ou un record** (Turbo Pascal 3.0 ne le permet pas non plus).
- **Partie de tableau** passée en paramètre (une ligne d'un tableau à deux dimensions).

Le compilateur le signale par un message clair, avec la ligne du programme.

## Différences avec Turbo Pascal

- **Tableau passé par valeur :** il est passé par adresse, et une modification faite dans la procédure se voit chez l'appelant. Un avertissement le signale. Les tableaux sont en général passés en `var` en Turbo Pascal, ce qui revient au même.
- **Dépassement d'entier :** il donne `OV Error`, au lieu de repartir en arrière (32 767 + 1 = -32 768 en Turbo Pascal).
- **Réels :** le X-07 calcule **en décimal**, sur 14 chiffres. `0.1` y est exact, mais `1/3*3` vaut 0,99999999999999 : la comparaison `= 1` est fausse.
- **Écran de 20 colonnes :** un `write` trop long passe à la ligne suivante.
- **Largeur constante dépassée :** `write(x:4)` ou `write(x:9:5)` passent par le `PRINT USING` de la ROM, plus compact. Si la valeur ne tient pas dans la largeur, la ROM l'écrit précédée de `%` (`%12345`), alors que Turbo Pascal élargit le champ. `x:0:d`, la façon habituelle de demander la largeur minimale, n'est pas concerné.
- **`Val`** rend toujours 0 dans son code d'erreur.
- **`Delay` sans son** est une boucle d'attente : environ 500 instructions par milliseconde, soit environ 1 ms sur la machine.
- **Identifiants :** un nom qui est un mot réservé du QuickBASIC (`len`, `line`, `data`…) est renommé en interne (`LENV`). Le préfixe `TP` est réservé à la bibliothèque d'appui. Cela ne se voit que dans le QuickBASIC produit.

## Exemples

```
exemples/pascal/bonjour.pas   lecture au clavier, affichage
exemples/pascal/fiches.pas    tableau de records trié, with, write avec largeurs
exemples/pascal/hanoi.pas     récursivité : les tours de Hanoï
exemples/pascal/dessin.pas    graphismes (Plot, Draw, Circle), Sound, KeyPressed
exemples/pascal/valeur.pas    paramètres par valeur ou var (entier, record, chaîne)
exemples/pascal/gauss_rand.pas  système aléatoire résolu par Gauss-Jordan (tableau à deux dimensions)
exemples/pascal/limites.pas   le X-07 dans ses retranchements : 14 chiffres en décimal, écran de
                              120 x 32 points, Mandelbrot en entiers, buzzer de 47 à 3918 Hz (16 Ko)
```

## Fichiers

```
x07asm/pascal.py        analyse du Pascal et traduction en QuickBASIC
tests/test_pascal.py    programmes exécutés par la ROM, affichage comparé à Turbo Pascal
```
