# Quick C : les réels du X-07 écrits comme des nombres

En C, les réels en double précision de la ROM ([C.md](C.md#réels--la-double-précision-du-x-07)) s'écrivent par appels de fonctions : `r_mul(&t, &a, &b); r_add(&x, &t, &c);`. **Quick C** (fichiers `.qc`) est le même C, où l'on écrit simplement :

```c
real x, a = 2.5;
x = a * sqrt(a) + 1;
if (x > a)
    printf("%s\n", str(x));
```

Le traducteur (`x07asm/qc.py`) récrit en appels de la bibliothèque les seules expressions où paraît un réel. Le reste du programme est recopié tel quel, puis compilé par SDCC comme un `.c`.

```sh
python3 x07asm.py run exemples/qc/pret.qc --fenetre       # dans la fenêtre
python3 x07asm.py ide exemples/qc/pret.qc                 # éditeur-débogueur
python3 x07asm.py qc exemples/qc/pret.qc -f bin,lst       # C produit (pret_qc.c), binaire, listing
python3 x07asm.py send exemples/qc/pret.qc --ram 16 --port /dev/ttyUSB0
```

Les commandes `run`, `send`, `debug`, `ide`, `emu --charger` et `c` acceptent les `.qc`. Les messages de SDCC, les points d'arrêt et le pas à pas de l'IDE portent sur les lignes du `.qc`, et le débogueur montre les variables, locales comprises, les réels en nombres ([DEBOGUEUR.md](DEBOGUEUR.md#programmes-c-et-quick-c)).

## Comparaison

`exemples/qc/pret.qc` et `exemples/c/pret.c` font la même chose et tracent la même courbe, point pour point :

```c
/* C */                                          /* Quick C */
r_int(&t, 1200);                                 r = taux / 1200;
r_div(&r, &taux, &t);                            mens = capital * r / (1 - pow(1 + r, -mois));
r_int(&t, mois);
r_neg(&t, &t);
r_add(&u, &un, &r);
r_pow(&u, &u, &t);
r_sub(&u, &un, &u);
r_mul(&mens, &capital, &r);
r_div(&mens, &mens, &u);
```

Le programme produit est le même : Quick C n'est ni plus lent ni beaucoup plus gros (pour `pret` : 687 000 instructions au lieu de 681 000, 5 783 octets au lieu de 5 615).

## Le langage

C'est le C de SDCC, plus le type `real` et quelques fonctions. `x07.h` est inclus d'office, avec toute la bibliothèque : écran, clavier, graphismes, fichiers.

| Écriture | Sens |
|---|---|
| `real x, y = 2.5, t[3] = {1, 2, 0.5};` | réels en double précision du X-07 (14 chiffres, calcul décimal), tableaux |
| `+ - * /`, `+= -= *= /=`, `++ --`, `-x` | calcul par la ROM, comme en BASIC |
| `< > <= >= == !=` | comparaisons |
| `if (x)`, `!x`, `x && y` | un réel est vrai s'il n'est pas nul |
| `sqrt sin cos tan atan exp log fabs` | comme `SQR SIN COS TAN ATN EXP LOG ABS` (radians, logarithme népérien) |
| `floor(x)`, `trunc(x)` | comme `INT` (partie entière par défaut) et `FIX` (tronquée) |
| `pow(a, b)` | `a ^ b` |
| `val(texte)` | réel lu dans un texte, comme `VAL` |
| `f_val(canal)` | nombre suivant d'un fichier en RAM (voir plus bas) |
| `str(x)`, `fmt(x, chiffres, décimales)` | texte, comme `STR$` et `PRINT USING "###.##"`, pour `printf("%s", …)`. Quatre au plus dans un même `printf` |
| `real f(real a, int n)` | fonctions qui prennent ou rendent des réels, passés par valeur, comme en C |
| `#define PI 3.14159265358979` | une macro qui vaut un nombre à virgule est un réel (un commentaire peut suivre). Un nom inconnu du traducteur, mêlé à un réel (macro calculée comme `#define G (9.81 * 2)`, `enum`), est refusé : le C le tronquerait en entier sans rien dire |

**Conversions, comme en C :**
- Un entier mêlé à un réel est converti en réel (`x * 2`, `x = n`).
- Un réel rangé dans un entier est **tronqué** (`n = x`, `(int)x`) ; `OV Error` au-delà de -32 768 à 32 767.
- `1 / 3` reste une division entière, qui vaut 0 ; il faut écrire `1 / 3.0` ou `1.0 / 3`.

**Constantes :** `2.5`, `1E-3`, et les entiers mêlés aux réels sont convertis **à la compilation**, par la routine `FIN` de la ROM, comme les constantes du BASIC compilé. Elles ne coûtent rien à l'exécution.

## Fichiers en RAM

Les fichiers en RAM du C ([C.md](C.md#fichiers-en-ram) : `f_open`, `f_gets`, `f_printf`…) servent tels quels. Pour les réels, on écrit leur texte, et on relit les nombres un par un avec `f_val` :

```c
real t;
int jour;
f_open(1, "releve", F_APPEND, 500);
f_printf(1, "%d %s\n", 12, str(18.5));    /* une ligne : « 12 18.5 » */
f_open(2, "releve", F_READ, 0);
while (!f_eof(2)) {
    jour = f_val(2);                      /* nombre suivant, comme INPUT # */
    t = f_val(2);
}
```

`f_val(canal)` lit le nombre suivant du fichier. Les nombres peuvent être séparés par des espaces, des virgules, des points-virgules ou des fins de ligne, si bien qu'un fichier écrit par `PRINT #` en BASIC se relit aussi. Lire au-delà de la fin donne `IO Error`, comme sur le X-07 ; `f_eof` le prévient.

Exemples complets : `exemples/qc/conso.qc`, un carnet de consommation d'une voiture (pleins, litres aux 100 km), et `exemples/qc/notes.qc`, un carnet de notes (noms lus par `f_tok`, notes par `f_val`).

## Ce que fait le traducteur

```c
x = sqrt(y) * 3 + n;
```
devient (voir `python3 x07asm.py qc`)
```c
(r_add(&(x), (r_mul(&_qc_t2, (r_sqrt(&_qc_t1, &y), &_qc_t1), &_qc_k1), &_qc_t2),
       (r_int(&_qc_t3, n), &_qc_t3)), &(x));
```

- **Une expression réelle** devient une suite d'appels reliés par l'opérateur virgule, qui vaut l'adresse du résultat. Elle reste donc une expression : elle va partout, dans une condition de `while`, un argument, un `?:`.
- **Les résultats intermédiaires** vont dans des temporaires (`_qc_t1`…), déclarés en tête de chaque fonction : la récursivité reste possible.
- **Les constantes** (`_qc_k1`…) sont déclarées en tête du fichier.
- **Fonctions** : SDCC ne passe ni ne rend de structure. `real f(real a)` devient donc `void f(real *_qc_ret, const real *_qc_p_a)`, et la fonction travaille sur une copie de `a` : le passage par valeur est respecté.
- **Lignes :** une directive `#line` et les sauts de ligne gardés font que chaque ligne du C produit est celle du `.qc`.

## Limites

- **Pas de réel dans une structure ou une union**, ni de pointeur de fonction : le traducteur le signale.
- **Un réel global ou `static`** ne s'initialise qu'avec une constante.
- **`%`, `<<`, `&`… sur un réel** : refusés, comme en C pour un `double`.
- **`printf("%d", x)` avec un réel** est refusé, avec un message qui suggère `str(x)`.

## Fichiers

```
x07asm/qc.py         traducteur Quick C -> C
x07asm/c/x07rstr.c   str(x), fmt(x, ...) : textes dans des tampons tournants
x07asm/c/x07ftok.c   f_tok, qui sert à f_val : valeur suivante d'un fichier
exemples/qc/         reels.qc (Newton, e, sinus), pret.qc (prêt, courbe) : comparer à exemples/c/
                     tir.qc (tir balistique : durée, portée, hauteur, trajectoire),
                     conso.qc (consommation d'une voiture, dans un fichier en RAM),
                     notes.qc (carnet de notes : moyennes, écart type, dans un fichier),
                     dichotomie.qc (cos(x) = x : à suivre au débogueur, voir DEBOGUEUR.md)
tests/test_qc.py     traduction, calculs, fonctions, erreurs
```
