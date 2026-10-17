# QuickBASIC vers le Canon X-07 : étude

**Question :** peut-on écrire un programme en QuickBASIC (blocs structurés, `SUB`, `FUNCTION`, noms longs, sans numéros de ligne), adapté au X-07 (écran de 20 × 4, 120 × 32 points), et en tirer automatiquement un programme en BASIC du X-07 et en assembleur ?

**Réponse : oui, pour l'essentiel du langage.** Un prototype fonctionne : la commande `qb`.

```
QuickBASIC  --qb-->  BASIC du X-07 (numéroté)  --basic-->  assembleur Z80
                         |                                    |
                     emu : vraie ROM                     run / --charger / send
```

La traduction produit du BASIC du X-07 ordinaire. On obtient donc les deux résultats demandés avec une seule traduction : le BASIC, que la ROM exécute (ou à taper sur la machine), et l'assembleur, produit par le compilateur existant.

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
DECLARE SUB Trier (t%(), n%)
CONST NB = 8
DIM notes%(1 TO NB)
...
Trier notes%(), NB
...
SUB Trier (t%(), n%)
    DO
        echange% = 0
        FOR i% = 1 TO n% - 1
            IF t%(i%) > t%(i% + 1) THEN
                SWAP t%(i%), t%(i% + 1)
                echange% = -1
            END IF
        NEXT i%
    LOOP WHILE echange%
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
| `DIM a(1 TO n)`, `DIM a(0 TO n)` | `DIM a(n)` : le X-07 n'a ni `TO` dans `DIM` ni `OPTION BASE`, ses indices vont toujours de 0 à n (la case 0 reste inutilisée pour `1 TO n`) |
| `DIM x AS INTEGER/SINGLE/DOUBLE/STRING`, suffixes, `DEFINT`… | suffixe explicite `%` `#` `$` |
| `SWAP a, b` | trois affectations |
| `LINE ...,B` / `,BF`, `PSET (x,y),0` | 4 lignes / boucle de lignes ; `PRESET` |
| `RANDOMIZE n`, `RND` | `RND(-n)`, `RND(1)` |
| `TIMER`, `RANDOMIZE TIMER` | calcul à partir de `TIME$` (interpréteur seulement, voir plus bas) |
| `SLEEP` | attente d'une touche |
| `SCREEN`, `COLOR`, `WIDTH`, `VIEW`, `KEY` | ignorés, avec un avertissement |
| `SOUND` | `BEEP` (avertissement) ; `LONG` → double précision (avertissement) |

## Ce qui n'est pas traduit

| Élément | Raison | Contournement |
|---|---|---|
| **récursivité** (`FUNCTION` qui s'appelle elle-même) | le BASIC du X-07 n'a pas de variables locales : un appel écraserait les variables de l'appel en cours | écrire une boucle ; ou la « voie directe » ci-dessous |
| `TYPE ... END TYPE` | pas d'enregistrements | tableaux parallèles |
| fichiers (`OPEN`, `PRINT #`…), `WRITE` | les périphériques du X-07 sont différents | — |
| `UCASE$`, `LCASE$`, `LTRIM$`, `RTRIM$`, `OCT$` | absents de la ROM | `MID$(STR$(x),2)` pour un nombre positif |
| `DIM t(2 TO 5)`, `OPTION BASE 1` | indices toujours de 0 à n sur le X-07 (`DIM A(1 TO 5)` et `OPTION BASE` y donnent `SN Error`) | décaler les indices |
| `REDIM`, chaînes de longueur fixe, `RETURN étiquette`, `LINE -(x,y)` | | |

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
- `Trier notes%()` appelle une copie de `Trier` qui travaille directement sur `NO%` ;
- `Trier notes2%()` appelle une autre copie, qui travaille sur `NT%`.

Le résultat est le même qu'avec une référence. On paie en taille de code (une copie par tableau), mais rien n'est recopié pendant l'exécution. C'est possible parce qu'en QuickBASIC le tableau passé est toujours **nommé dans le source** : on sait, dès la traduction, sur lequel la procédure travaillera.

**Pourquoi ne pas simuler des pointeurs.** La ROM connaît `VARPTR`, qui donne l'adresse d'une variable, et `PEEK`/`POKE` permettent d'atteindre les éléments par leur adresse (vérifié : `VARPTR(T%(0))` puis `PEEK` relisent bien `T%(2)`). Mais ce n'est pas une voie fiable :
- **les tableaux bougent en mémoire.** Le BASIC Microsoft range les tableaux après les variables simples et les déplace dès qu'une nouvelle variable apparaît. Dans l'émulateur, `VARPTR(T%(0))` vaut 1428, puis 1450 après la création de deux variables `B` et `Z`. Une adresse gardée comme « pointeur » deviendrait fausse sans prévenir ;
- **lourd et lent :** chaque `t(i)` deviendrait plusieurs `PEEK`/`POKE` avec un calcul d'adresse, pire encore pour les nombres décimaux (4 ou 8 octets BCD) et les chaînes ;
- **le compilateur ne gère pas `VARPTR`.**

**Où de vrais pointeurs seraient possibles :** dans la voie directe ci-dessous. Dans le code compilé, les tableaux ont une **adresse fixe**, que l'on pourrait passer dans un registre. Il n'y aurait plus de copies de procédures, et la récursivité deviendrait possible. Mais il n'y aurait plus de version en BASIC du X-07.

## Deux voies vers l'assembleur

**1. Par le BASIC du X-07 : la voie choisie pour le prototype.** Une seule traduction donne les deux résultats demandés. Le BASIC produit est vérifié par la vraie ROM, puis le compilateur existant (déjà testé contre la ROM) en fait de l'assembleur. Le prix à payer : l'assembleur hérite des limites du BASIC du X-07 (pas de récursivité, noms courts, pas d'entiers 32 bits).

**2. Directe** : l'arbre de QuickBASIC serait donné au générateur de code du compilateur, sans repasser par le texte BASIC. On gagnerait :
- la **récursivité**, grâce à une pile pour les variables locales et les paramètres ;
- de vrais **paramètres par référence** (passage d'adresses), y compris pour les tableaux, sans copie de procédure ;
- des **entiers 32 bits** (`LONG`), avec de nouvelles routines.

Mais cette voie ne produirait plus de BASIC du X-07, n'aurait plus la ROM pour référence, et demanderait de reprendre une bonne part du compilateur.

**Recommandation :** garder la voie 1, qui couvre les programmes écrits pour une machine de cette taille, et n'envisager la voie 2 que si la récursivité devient un vrai besoin.

## Pistes pour aller plus loin

1. Ajouter au compilateur ce que la ROM sait déjà faire et que la traduction produit : `INSTR`, `LINE INPUT`, `PRINT USING`, `TIME$`, `ON ERROR`.
2. Arrondi exact de QuickBASIC (demi au pair) dans une petite routine.
3. `TYPE` traduit en tableaux parallèles ; `REDIM` par `ERASE` puis `DIM`.
4. Garder les commentaires en `REM` (option), au prix de la mémoire.
5. Essayer des programmes QuickBASIC réels, écrits par d'autres, pour mesurer la part traduite sans retouche.

## Fichiers

```
x07asm/qbasic.py          traducteur : analyse, renommage, génération numérotée
tests/test_qbasic.py      tests (ROM + version compilée)
exemples/qbasic/          tri.qbas, tri2.qbas (même SUB pour deux tableaux), mystere.qbas
```
