# QuickBASIC vers le Canon X-07 : étude

**Question :** peut-on écrire un programme en QuickBASIC (blocs structurés, `SUB`, `FUNCTION`, noms longs, sans numéros de ligne), adapté au X-07 (écran de 20 × 4, 120 × 32 points), et en tirer automatiquement un programme en BASIC du X-07 et en assembleur ?

**Réponse : oui, pour l'essentiel du langage.** Deux voies fonctionnent :

```
QuickBASIC  --qb-->  BASIC du X-07 (numéroté)  --basic-->  assembleur Z80
     |                   |                                    |
     |               emu : vraie ROM                     run / --charger / send
     |
     +--qb --direct-->  assembleur Z80  (récursivité, tableaux par adresse)
```

- **Traduction (`qb`)** : le résultat est du BASIC du X-07 ordinaire, que la ROM exécute ou que l'on tape sur la machine. Le compilateur existant en fait ensuite de l'assembleur : une seule traduction donne les deux résultats.
- **Compilation directe (`--direct`)** : le programme QuickBASIC devient directement de l'assembleur, sans BASIC du X-07. On gagne la récursivité et le passage des tableaux par adresse, mais on n'a plus de version en BASIC. Voir « Compilation directe » plus bas.

**Ce qui a été vérifié :**
- les tests (`tests/test_qbasic.py`) : chaque programme QuickBASIC est traduit, exécuté par la vraie ROM, et sa sortie est comparée à celle qu'aurait donnée QuickBASIC ;
- quand le compilateur accepte le résultat, la version compilée affiche exactement la même chose ;
- les deux exemples de `exemples/qbasic/` passent les deux chemins.

Aucun essai n'a été fait avec un vrai QuickBASIC : les sorties attendues ont été écrites à la main, d'après le comportement documenté de QuickBASIC 4.5.

## Utilisation

Les programmes QuickBASIC portent l'extension **`.qbas`**, pour les distinguer du BASIC du X-07 (`.bas`). La traduction de `NOM.qbas` s'écrit dans `NOM.bas`, à côté.

```sh
python3 x07asm.py qb exemples/qbasic/tri.qbas                # -> exemples/qbasic/tri.bas
python3 x07asm.py emu exemples/qbasic/tri.bas                # par la ROM du X-07
python3 x07asm.py qb exemples/qbasic/tri.qbas -f asm,bin --ram 16   # traduit puis compile
python3 x07asm.py qb exemples/qbasic/tri.qbas --noms         # correspondance des noms
```

**Les autres commandes acceptent aussi directement un `.qbas`** : elles le traduisent au passage, sans écrire de fichier.

```sh
python3 x07asm.py emu exemples/qbasic/tri.qbas --fenetre     # BASIC du X-07, dans la fenêtre
python3 x07asm.py run exemples/qbasic/tri.qbas               # compilé
python3 x07asm.py basic exemples/qbasic/tri.qbas --ram 16    # assembleur et binaire
python3 x07asm.py send exemples/qbasic/tri.qbas --ram 16 --port /dev/ttyUSB0
python3 x07asm.py emu --fenetre --charger exemples/qbasic/tri.qbas --ram 16
```

Ce n'est le cas que pour l'extension `.qbas`. Un programme QuickBASIC enregistré en `.bas` serait tapé tel quel sur le X-07, qui répondrait `SN Error` dès la première ligne qu'il ne connaît pas (`DECLARE`, `SUB`…).

| Option | Rôle |
|---|---|
| `-o FICHIER` | programme X-07 produit (défaut : `NOM.qbas` donne `NOM.bas`) |
| `-f FORMATS` | compile ensuite le résultat (`asm,bin,hex,lst,txt,bas`, comme `basic`) |
| `--ram`, `--org` | pour la compilation |
| `--largeur N` | longueur maximale d'une ligne produite (72 par défaut) |
| `--noms` | affiche le nom X-07 de chaque variable (`TRIER.ECHANGE -> E%`) |

## Exemple

`exemples/qbasic/tri.qbas` (extrait) :

```basic
DEFINT A-Z                      ' variables entières sur 2 octets par défaut
DECLARE SUB Trier (t(), n)
CONST NB = 8
DIM notes(1 TO NB)
...
Trier notes(), NB
...
SUB Trier (t(), n)
    DO
        echange = 0
        FOR i = 1 TO n - 1
            IF t(i) > t(i + 1) THEN
                SWAP t(i), t(i + 1)
                echange = -1
            END IF
        NEXT i
    LOOP WHILE echange
END SUB
```

devient :

```basic
40 N%=8:GOSUB 60:CLS:FOR I%=1 TO 8:PRINT NO%(I%);:NEXT I%
...
60 E%=0:I0%=0
70 E%=0:B%=N%-1:IF 1>B% THEN 110
80 FOR I0%=1 TO B%:IF NO%(I0%)<=NO%(I0%+1) THEN 100
90 C%=NO%(I0%):NO%(I0%)=NO%(I0%+1):NO%(I0%+1)=C%:E%=-1
100 NEXT I0%
110 IF E% THEN 70
120 RETURN
```

Ici, 37 lignes de QuickBASIC donnent 16 lignes de BASIC du X-07 (505 caractères) et 1 163 octets de code machine.

## Types des variables : éviter les `%`

Comme sur le X-07, un nom terminé par `%` désigne un **entier sur 2 octets** (de -32 768 à 32 767), `!` la simple précision, `#` la double, `$` une chaîne. Sans suffixe, une variable est en simple précision. Pour ne pas écrire `%` partout, QuickBASIC offre deux moyens, acceptés par la traduction comme par la compilation directe.

**1. `DEFINT` pour une plage de lettres**, en tête du programme :

```basic
DEFINT A-Z                       ' toutes les variables sont entières par défaut
DECLARE SUB Tri (t(), g, d)
DIM a(9), b(5)
...
SUB Tri (t(), g, d)
    pivot = t((g + d) \ 2)
```

`DEFINT I-N` limite la règle aux noms qui commencent par I à N. `DEFSNG`, `DEFDBL` et `DEFSTR` font de même pour les autres types. Un suffixe explicite reste prioritaire : avec `DEFINT A-Z`, `moyenne!` est toujours en simple précision.

**2. `AS INTEGER` dans les déclarations**, variable par variable, paramètres et variables locales compris :

```basic
DECLARE FUNCTION Somme (n AS INTEGER)
DIM total AS INTEGER, k AS INTEGER, x AS SINGLE
...
FUNCTION Somme (n AS INTEGER)
    DIM s AS INTEGER, i AS INTEGER
```

Une fois déclarée, la variable s'écrit sans suffixe partout.

**Le résultat d'une `FUNCTION`** ne peut pas s'écrire `AS INTEGER` en QuickBASIC 4.5 : son type vient du suffixe du nom (`Fact#`) ou de `DEFINT`. Avec `DEFINT A-Z`, `FUNCTION Somme` rend un entier.

Tous les exemples de `exemples/qbasic/` sont écrits avec `DEFINT A-Z`. Leur traduction est identique, octet pour octet, à celle des versions avec `%`. Un suffixe n'y reste que pour un autre type : `Moyenne!` et `s!` (simple précision), `Fact#` (double), et `graine!` dans `mystere.qbas`, qui compte les tours d'attente et déborderait en entier au-delà de 32 767. Vérifié aussi : `total = x`, avec `x AS SINGLE` valant 2,7, donne bien 3, arrondi comme en QuickBASIC.

**Attention aux types des arguments.** Un tableau, ou une variable passée par référence, doit avoir **exactement** le type du paramètre. Avec `DEFINT A-Z`, `SUB Tri (t())` attend un tableau d'entiers : lui passer `b()` déclaré `AS DOUBLE` est une erreur. QuickBASIC la signale à la compilation (« Parameter type mismatch »), et nos deux voies aussi :

```
erreur : QuickBASIC : ligne 15 : TRI : le paramètre T() attend un tableau de type entier (%),
mais B() est de type double précision (#) (QuickBASIC refuse aussi : « Parameter type mismatch »)
```

Sans cette vérification, la procédure parcourrait le tableau avec la mauvaise taille d'élément (2 octets au lieu de 8). Elle trierait des morceaux de nombres, et le programme afficherait des valeurs abîmées sans aucune alerte. Une expression, elle, est convertie, comme en QuickBASIC : pour passer `x!` à un paramètre entier, écrivez `(x!)`. Une chaîne ne va jamais dans un nombre, ni l'inverse.

## Ce que le X-07 impose (vérifié dans la ROM)

Ces différences ont été mesurées dans l'émulateur, qui exécute la vraie ROM. Ce sont elles qui rendent une traduction automatique nécessaire : un programme QuickBASIC ne peut pas être simplement recopié.

| Sur le X-07 | Conséquence | Traduction |
|---|---|---|
| **2 caractères** significatifs dans un nom : `ALPHA` et `ALBUM` sont la même variable | collisions silencieuses | toutes les variables sont renommées (1 ou 2 caractères + suffixe de type) |
| un mot-clé dans un nom est refusé : `TOTAL` (contient `TO`), `FORME` donnent `SN Error` | | les noms produits ne contiennent aucun mot-clé |
| pas de `WHILE`/`WEND`, de `SWAP`, de bloc `IF`, de `DO`/`LOOP`, de `SELECT CASE`, de `SUB`/`FUNCTION`, d'étiquettes | | `IF ... THEN n`, `GOTO`, `GOSUB`, numéros de ligne |
| `FOR I=1 TO 0` **exécute le corps une fois** | QuickBASIC ne l'exécute pas | garde `IF 1>N THEN ...` avant la boucle, sauf si les bornes sont des constantes |
| `CINT(3.7)` = 3, `A%=3.7` donne 3 : **troncature** | QuickBASIC arrondit (4) | `INT(x+.5)` quand une valeur non entière va dans un entier |
| `LOCATE x,y`, `POS`, `CSRLIN`, `TAB` comptent **depuis 0**, `LOCATE` prend la colonne en premier | | `LOCATE r,c` devient `LOCATE c-1,r-1` ; `POS(0)+1`, `CSRLIN+1`, `TAB(n-1)` |
| pas de `SPC()` : `SPC(2)` est lu comme un tableau | | `STRING$(n," ")` (comme `SPACE$`) |
| `INPUT "texte",v` donne `SN Error` | le X-07 affiche toujours « ? » | `INPUT "texte";v` (avertissement) |
| type par défaut : double précision | QuickBASIC : simple | `DEFSNG A-Z` en tête |
| `DIM` refait donne `DD Error`, `ERASE` d'un tableau absent donne `FC Error` | tableaux locaux des procédures | `DIM` une seule fois en tête du programme, tableau remis à zéro à chaque appel |
| **50 octets seulement pour les chaînes** au départ : construire une chaîne (`r$ = r$ + MID$(...)`) donne vite `OS Error` | QuickBASIC n'a pas cette limite | `CLEAR 500` en tête du programme traduit, s'il emploie des chaînes (le compilateur, lui, réserve la place de chaque chaîne) |
| pas de pointeurs : un tableau ne peut pas être passé en paramètre | `SUB Trier (t())` | une copie de la procédure par tableau reçu |

Ce qui est **identique** et passe tel quel : `PRINT` (`;` `,` zones de 14 colonnes), opérateurs et priorités, vrai = -1, `MOD`, `\`, `&H`, `&O`, fonctions de chaînes, `DATA`/`READ`/`RESTORE`, `ON ... GOTO/GOSUB`, `DEF FN`, et sortie d'une boucle `FOR` par `GOTO` (tolérée par la ROM).

`INSTR`, `LINE INPUT`, `PRINT USING`, `ON ERROR`/`RESUME` existent dans la ROM. Ils sont donc traduits, mais le compilateur ne les accepte pas encore : avec eux, seul le chemin « BASIC du X-07 » fonctionne. Un avertissement le signale.

## Ce que fait la traduction

| QuickBASIC | BASIC du X-07 |
|---|---|
| étiquettes `Nom:`, numéros de ligne | numéros de ligne (10, 20…) ; instructions regroupées par `:` sur 72 caractères au plus |
| `IF` en bloc, `ELSEIF`, `ELSE` | `IF` inversé + `GOTO` ; un `IF` simple reste sur une ligne |
| `DO [WHILE\|UNTIL] ... LOOP [WHILE\|UNTIL]`, `WHILE ... WEND` | tests et `GOTO` ; `EXIT DO` |
| `FOR ... NEXT`, `EXIT FOR` | `FOR` du X-07 + garde de boucle vide ; `GOTO` après le `NEXT` |
| `SELECT CASE` (`CASE a`, `a TO b`, `IS > a`, listes, `CASE ELSE`) | valeur dans une variable, puis suite de `IF` |
| `SUB` / `FUNCTION`, `CALL`, appel sans `CALL` | `GOSUB` ; paramètres copiés à l'entrée **et recopiés à la sortie** (passage par référence de QuickBASIC) ; `(x)` passe par valeur |
| appel de `FUNCTION` dans une expression, un test, une condition de boucle | appel fait juste avant, résultat dans une variable |
| variables locales | variables propres à chaque procédure, **remises à zéro à chaque appel** ; `STATIC` les garde |
| `DIM SHARED`, `SHARED` | variables du module |
| paramètre tableau `t()` | une **copie de la procédure pour chaque tableau reçu** (avertissement) ; ses variables simples restent communes. Un tableau peut aussi être transmis d'une procédure à une autre |
| tableau local (`DIM` dans une procédure) | `DIM` une seule fois en tête du programme ; remis à zéro à chaque appel par une boucle, sauf `STATIC` (tailles constantes, 1 ou 2 dimensions) |
| `CONST` | valeur recopiée dans les expressions |
| `REDIM a(n)` | `IF témoin THEN ERASE A`, puis `DIM A(n)` : une variable témoin dit si le tableau existe déjà (le X-07 répond `FC Error` à l'`ERASE` d'un tableau absent). Le contenu est remis à zéro, comme en QuickBASIC ; `REDIM PRESERVE` n'existe pas en QuickBASIC 4.5 |
| `DIM a(1 TO n)`, `DIM a(0 TO n)` | `DIM a(n)` : le X-07 n'a ni `TO` dans `DIM` ni `OPTION BASE`, ses indices vont toujours de 0 à n (la case 0 reste inutilisée pour `1 TO n`) |
| `DIM x AS INTEGER/SINGLE/DOUBLE/STRING`, suffixes, `DEFINT`… | suffixe explicite `%` `#` `$` |
| `SWAP a, b` | trois affectations |
| `LINE ...,B` / `,BF`, `PSET (x,y),0` | 4 lignes / boucle de lignes ; `PRESET` |
| `RANDOMIZE n`, `RND` | `RND(-n)`, `RND(1)` |
| `TIMER`, `RANDOMIZE TIMER` | calcul à partir de `TIME$` (interpréteur seulement, voir plus bas) |
| `SLEEP` | attente d'une touche |
| `SCREEN`, `COLOR`, `WIDTH`, `VIEW`, `KEY` | ignorés, avec un avertissement |
| `BEEP` | `BEEP 240,5` : 800 Hz pendant 1/4 s, comme sur PC |
| `BEEP note, durée` | gardé tel quel : c'est le `BEEP` du X-07 (note 1 à 48 par demi-tons depuis le do, 49 à 4095 : 192 000/note Hz ; durée × 50 ms) |
| `SOUND f, durée` | `BEEP 192000/f, durée × 1,1` (durée en tops de 1/18,2 s) ; le X-07 joue de 47 à 3918 Hz, 12,75 s au plus (avertissement si une constante en sort, ou si l'expression est variable) |
| `LONG` | double précision (avertissement) |

## Ce qui n'est pas traduit

| Élément | Raison | Contournement |
|---|---|---|
| **récursivité** (`FUNCTION` qui s'appelle elle-même) | le BASIC du X-07 n'a pas de variables locales : un appel écraserait les variables de l'appel en cours | écrire une boucle ; ou la « voie directe » ci-dessous |
| `TYPE ... END TYPE` | pas d'enregistrements | tableaux parallèles |
| fichiers autres que séquentiels (`RANDOM`, `BINARY`, `GET`, `PUT`) | — | fichiers séquentiels en RAM : `OPEN ... FOR INPUT/OUTPUT/APPEND`, voir [FICHIERS.md](FICHIERS.md) |
| `UCASE$`, `LCASE$`, `LTRIM$`, `RTRIM$`, `OCT$` | absents de la ROM | `MID$(STR$(x),2)` pour un nombre positif |
| `DIM t(2 TO 5)`, `OPTION BASE 1` | indices toujours de 0 à n sur le X-07 (`DIM A(1 TO 5)` et `OPTION BASE` y donnent `SN Error`) | décaler les indices |
| chaînes de longueur fixe, `RETURN étiquette`, `LINE -(x,y)` | | |

**Différences qui restent**, à connaître :
- **Arrondi :** QuickBASIC arrondit les demis au pair (`CINT(2.5)` = 2). La traduction donne 3.
- **Largeur d'écran :** sur 20 colonnes, `PRINT` passe à la ligne plus souvent. C'est la raison pour laquelle le programme doit être « adapté au X-07 ».
- **Paramètres :** une procédure qui modifie à la fois un paramètre et la variable passée (par `SHARED`) ne voit pas la même chose qu'en QuickBASIC. La recopie se fait au retour.
- **Tableaux locaux de taille variable** (`DIM w(n)` dans une procédure) : créés au premier appel et jamais remis à zéro, comme s'ils étaient `STATIC`. Le compilateur les refuse si la procédure est recopiée.
- **Taille :** chaque tableau différent passé à une procédure ajoute une copie de son code (voir « Tableaux en paramètre » ci-dessous). Avec beaucoup de tableaux et une grosse procédure, la mémoire du X-07 peut manquer.
- **Messages d'erreur :** ils donnent les numéros de ligne du programme traduit.

## Tableaux en paramètre : sans pointeurs

Le BASIC du X-07 n'a pas de pointeurs : la traduction ne passe donc jamais l'adresse d'un tableau. Le **passage par référence** fonctionne pourtant : une procédure qui modifie le tableau reçu modifie bien celui de l'appelant, comme en QuickBASIC.

**Comment.** Le traducteur produit une **copie de la procédure pour chaque tableau réel** qu'elle reçoit. Dans `tri2.qbas` :
- `Trier notes()` appelle une copie de `Trier` qui travaille directement sur `NO%` ;
- `Trier notes2()` appelle une autre copie, qui travaille sur `NT%`.

Le résultat est le même qu'avec une référence. On paie en taille de code (une copie par tableau), mais rien n'est recopié pendant l'exécution. C'est possible parce qu'en QuickBASIC le tableau passé est toujours **nommé dans le source** : on sait, dès la traduction, sur lequel la procédure travaillera.

**Pourquoi ne pas simuler des pointeurs.** La ROM connaît `VARPTR`, qui donne l'adresse d'une variable, et `PEEK`/`POKE` permettent d'atteindre les éléments par leur adresse (vérifié : `VARPTR(T%(0))` puis `PEEK` relisent bien `T%(2)`). Mais ce n'est pas une voie fiable :
- **les tableaux bougent en mémoire.** Le BASIC Microsoft range les tableaux après les variables simples et les déplace dès qu'une nouvelle variable apparaît. Dans l'émulateur, `VARPTR(T%(0))` vaut 1428, puis 1450 après la création de deux variables `B` et `Z`. Une adresse gardée comme « pointeur » deviendrait fausse sans prévenir ;
- **lourd et lent :** chaque `t(i)` deviendrait plusieurs `PEEK`/`POKE` avec un calcul d'adresse, pire encore pour les nombres décimaux (4 ou 8 octets BCD) et les chaînes ;
- **le compilateur ne gère pas `VARPTR`.**

**Où de vrais pointeurs sont possibles :** dans le code compilé, les tableaux ont une **adresse fixe**. C'est ce que fait la compilation directe (`--direct`, ci-dessous) : une seule copie de chaque procédure, et la récursivité en plus, mais plus de version en BASIC du X-07.

## Compilation directe (`--direct`)

```sh
python3 x07asm.py run exemples/qbasic/rapide.qbas --direct       # dans l'émulateur
python3 x07asm.py qb exemples/qbasic/rapide.qbas --direct        # -> rapide.asm, rapide.bin
python3 x07asm.py debug exemples/qbasic/rapide.qbas --direct     # débogueur, voir ci-dessous
```

`--direct` existe aussi pour `basic`, `send` et `emu --charger`. Sans cette option, un `.qbas` passe par la traduction en BASIC.

Avec le débogueur, `ligne N` désigne la ligne N du **source QuickBASIC**, et `v PROC.VAR` une variable locale. On voit ainsi chaque appel récursif :

```
(x07) b ligne 27                  ← i = g: j = d, dans SUB Tri
(x07) c
(x07) v TRI.G
  TRI.G% = 0
(x07) v TRI.D
  TRI.D% = 9
(x07) v TRI.PIVOT
  TRI.PIVOT% = 7
(x07) c                           ← l'appel récursif suivant
(x07) v TRI.D
  TRI.D% = 6
```

**Principe.** Le programme QuickBASIC, analysé comme pour la traduction, est transformé directement en instructions internes du compilateur, sans texte BASIC (`x07asm/qbcomp.py`). Le générateur de code existant, vérifié contre la ROM, sert tel quel pour les expressions, `PRINT`, les chaînes et les nombres BCD. Les adaptations au X-07 restent les mêmes que pour la traduction : arrondi vers les entiers, `LOCATE`, garde des `FOR`.

**Ce qui change par rapport à la traduction :**

| | Traduction (`qb`) | Compilation directe (`--direct`) |
|---|---|---|
| noms des variables | renommés en 1 ou 2 caractères | gardés (`V_ALPHABET_F`) |
| `SUB`, `FUNCTION` | `GOSUB` | `CALL` / `RET` |
| récursivité | refusée | **permise** |
| tableau en paramètre | une copie de la procédure par tableau | **une seule copie** : le tableau est passé par adresse |
| `INSTR`, `LINE INPUT`, `PRINT USING`, `ON ERROR`, `TIME$` | traduits (ROM seulement) | refusés (absents du compilateur) |
| `DIM t(n)` avec n variable | accepté par la ROM | refusé : dimensions constantes |
| `REDIM` | `ERASE` puis `DIM` | refusé : tableaux de taille fixe |
| résultat | BASIC du X-07 + assembleur | assembleur seulement |

**Procédures.** L'appelant range les arguments dans des cases propres à la procédure ; la procédure les recopie dans ses paramètres à l'entrée. À la sortie, elle range ses paramètres dans d'autres cases, que l'appelant recopie dans les variables passées : c'est le passage par référence de QuickBASIC, et `(x)` passe par valeur. Ces cases ne sont jamais empilées : le passage reste exact pendant la récursivité, y compris quand une procédure se transmet sa propre variable par référence.

**Récursivité.** Les variables gardent une adresse fixe. Une procédure **récursive** (repérée par le graphe des appels) empile, à l'entrée, ses variables locales, ses paramètres, son résultat, ses variables temporaires et les variables cachées de ses boucles `FOR` (limite, pas). Elle les dépile à la sortie (`RT_SAVE`, `RT_REST`). Les procédures non récursives n'ont pas ce coût. Une récursivité trop profonde donne `OM Error` avant que la pile n'atteigne la mémoire du BASIC.

**Tableaux par adresse.** Chaque tableau passé en paramètre reçoit un petit descripteur (adresse, nombre d'éléments par dimension). L'appelant transmet l'adresse du descripteur ; la procédure la charge dans un registre à chaque accès, et une routine calcule l'adresse de l'élément, avec le contrôle des indices (`BS Error`). Une procédure peut transmettre à son tour le tableau reçu. Le passage par adresse est limité à 1 ou 2 dimensions.

**Coût, mesuré dans l'émulateur :**

| Programme | Traduction | Compilation directe |
|---|---|---|
| `tri.qbas` | 1 163 octets, 22 632 instructions | 1 374 octets, 26 458 instructions |
| `tri2.qbas` (deux tableaux) | 1 560 octets, 31 030 instructions | 1 502 octets, 38 417 instructions |
| `rapide.qbas` (récursif) | refusé | 1 926 octets, 56 250 instructions |

L'accès indirect aux tableaux et les recopies de paramètres coûtent environ 20 % de temps. En échange, le code ne grossit plus avec le nombre de tableaux passés à une procédure.

**Limites propres à la compilation directe :**
- **Tableau local d'une procédure récursive :** il n'est pas empilé, et il est donc partagé par tous les appels en cours (avertissement).
- **`LOCATE` :** il faut donner la ligne et la colonne.
- **`PSET` :** la couleur doit être une constante.
- **`DEF FN` :** numériques seulement.
- **Messages d'erreur :** les erreurs d'exécution donnent la ligne du source QuickBASIC, avec l'option du compilateur `--debug` (`debug` l'active toujours).

**Quand choisir quoi :**
- **Traduction :** si l'on veut un programme en BASIC du X-07, à taper ou à lire sur la machine, ou si le programme emploie `INSTR`, `PRINT USING`, `ON ERROR`.
- **Compilation directe :** dès qu'il y a de la récursivité, ou une procédure qui travaille sur plusieurs tableaux.

## Pistes pour aller plus loin

1. Ajouter au compilateur ce que la ROM sait déjà faire et que la traduction produit : `INSTR`, `LINE INPUT`, `PRINT USING`, `TIME$`, `ON ERROR`. Les deux voies en profiteraient.
2. Compilation directe : entiers 32 bits (`LONG`), dimensions variables (`DIM t(n)`), tableaux par adresse à plus de 2 dimensions.
3. Arrondi exact de QuickBASIC (demi au pair) dans une petite routine.
4. `TYPE` traduit en tableaux parallèles.
5. Garder les commentaires en `REM` (option), au prix de la mémoire.
6. Essayer des programmes QuickBASIC réels, écrits par d'autres, pour mesurer la part traduite sans retouche.

## Fichiers

```
x07asm/qbasic.py          traducteur : analyse, renommage, génération numérotée
x07asm/qbcomp.py          compilation directe en assembleur (--direct)
tests/test_qbasic.py      tests de la traduction (ROM + version compilée)
tests/test_qbcomp.py      tests de la compilation directe
exemples/qbasic/          tri.qbas, tri2.qbas (même SUB pour deux tableaux), mystere.qbas,
                          mots.qbas (chaînes : envers, César, voyelles, palindrome),
                          rapide.qbas (tri rapide récursif : compilation directe seulement)
```
