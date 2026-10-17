# Fichiers en RAM du X-07 : étude pour QuickBASIC

**Question :** un programme QuickBASIC pour le X-07 peut-il garder des données dans un fichier, au moins en RAM ?

**Réponse : oui.** Le X-07 a déjà un **système de fichiers en RAM**, géré par sa ROM, et ces fichiers **survivent à l'extinction**. Tout ce qui suit a été vérifié dans l'émulateur, qui exécute la vraie ROM (`tests/test_fichiers.py`).

Cette page est l'étape 1 : comprendre ce que fait la ROM. La prise en charge de `OPEN`, `PRINT #`, `INPUT #`, `EOF`… dans la traduction et la compilation viendra ensuite.

## Ce que la ROM sait faire

```basic
10 FSET 400                      ' 400 octets pour les fichiers
20 INIT#1,"RAM:DATA",100         ' crée DATA (100 octets) sur le canal 1
30 PRINT #1,"BONJOUR,12"
40 INIT#2,"RAM:DATA"             ' le rouvre sur le canal 2, en lecture
50 INPUT #2,A$,B
60 PRINT A$;B                    '  BONJOUR 12
70 DIR                           '  RAM: / DATA   D / 400/273
```

| Commande | Rôle |
|---|---|
| `FSET n` | réserve n octets pour les fichiers. `DIR` affiche la taille totale et la place libre (`400/273`) |
| `INIT#c,"RAM:NOM",taille` | ouvre le fichier sur le canal c (1 à 5). Il est **créé** s'il n'existe pas, avec cette taille |
| `PRINT #c`, `INPUT #c`, `LINE INPUT #c` | écrire, lire des valeurs, lire une ligne |
| `OUT #c,octet`, `INP(#c)` | écrire, lire un octet |
| `DIR` | liste des fichiers : nom, type (`D` données, `P` programme), place |
| `DELETE "NOM"` | supprime le fichier (le nom **seul** : `DELETE "RAM:NOM"` donne `NE Error`) et rend sa place |
| `SAVE "RAM:NOM"`, `LOAD "RAM:NOM"` | ranger et relire un programme BASIC |

**Contraintes vérifiées :**

| Point | X-07 | QuickBASIC |
|---|---|---|
| taille | **fixe**, donnée à la création ; écrire au-delà donne `IO Error` | un fichier grandit |
| noms | 6 caractères (`NOMLONG1` devient `NOMLON`) | 8 + 3 |
| fin de fichier | lire au-delà donne `IO Error` ; **pas de `EOF`** (`EOF(1)` est lu comme un tableau) | `EOF(n)` |
| fermeture | **pas de `CLOSE`** (`SN Error`) | `CLOSE` |
| réouverture en écriture | `INIT#` sur un fichier existant **ne le vide pas** : écrire `COURT` sur `LONGUE LIGNE` laisse `LIGNE` derrière, que la lecture suivante retrouve | `FOR OUTPUT` vide le fichier |
| `LINE INPUT #` | s'arrête au retour chariot, et **laisse le saut de ligne** : la ligne suivante commence par `CHR$(10)` | lit des lignes propres |
| fichier absent | `NE Error` | « File not found » |
| commande directe | `INIT#`, `INPUT #` interdits (`ID Error`) | — |

## Organisation en mémoire

- **La zone des fichiers** est **en haut de la RAM**. Ses limites sont `RAMSTR` (`$0210`) et `RAMEND` (`$0212`) ; avec 16 Ko, `RAMEND` vaut `$3FF7`. `FSET` abaisse d'autant la fin de la zone BASIC (`MEMSIZ`). La ROM recopie `RAMSTR` en `$3FFC`, dans les 14 octets du haut qu'elle se réserve.
- **Un fichier** : un en-tête de 14 octets, puis les données. L'en-tête contient le nom (6 caractères complétés par des espaces), le type (`D` ou `P`), la longueur totale (en-tête compris) sur 2 octets, et 5 octets non identifiés. Les octets non écrits valent 0, et **un octet 0 marque la fin des données**.
- **Un canal ouvert** : 8 octets dans `KBNTAB` (`$02C5 + 8 × (c−1)`).

| Octets | Contenu |
|---|---|
| +0, +1 | adresse du pilote `RAM:` (`$E7CE`) |
| +2, +3 | **pointeur d'écriture** |
| +4, +5 | **pointeur de lecture** |
| +6, +7 | dernière adresse des données |

  Les deux pointeurs partent du début des données à l'ouverture, et avancent indépendamment.
- **Le pilote `RAM:`** (table de la ROM en `$E7CA`) : écrire un octet `$E5B4`, lire un octet `$E5CB`, ouvrir `$E449`.

## Ce que QuickBASIC demande, et comment l'obtenir (vérifié)

| QuickBASIC | Sur le X-07 |
|---|---|
| `OPEN "f" FOR OUTPUT AS #1` | `INIT#1,"RAM:F",taille`, puis **remise à zéro des données**, du pointeur de lecture à la fin du canal |
| `OPEN "f" FOR APPEND AS #1` | `INIT#1`, puis **pointeur d'écriture placé sur le premier octet nul** |
| `OPEN "f" FOR INPUT AS #1` | `INIT#1,"RAM:F"` (`NE Error` si absent) |
| `EOF(1)` | vrai si le **pointeur de lecture** dépasse la fin ou pointe un octet nul, en sautant un saut de ligne restant |
| `LINE INPUT #1, a$` | `LINE INPUT #1,A$`, puis retrait du `CHR$(10)` de tête |
| `KILL "f"` | `DELETE "F"` |
| `CLOSE` | rien |
| taille | à prévoir : `LEN =` de `OPEN`, ou une valeur par défaut |

Exemple vérifié, une lecture jusqu'à la fin du fichier :

```basic
50 C=2:GOSUB 900:IF E THEN 80          ' WHILE NOT EOF(2)
60 LINE INPUT #2,A$:GOSUB 940:PRINT A$
70 GOTO 50
...
900 K=&H2C5+8*(C-1):P=PEEK(K+4)+256*PEEK(K+5):F=PEEK(K+6)+256*PEEK(K+7)
910 IF P<=F THEN IF PEEK(P)=10 THEN P=P+1
920 E=(P>F):IF NOT E THEN E=(PEEK(P)=0)
930 RETURN
940 IF LEFT$(A$,1)=CHR$(10) THEN A$=MID$(A$,2)
950 RETURN
```

## Persistance : les fichiers survivent à l'extinction

Sur le X-07, la RAM reste alimentée machine éteinte. Quand on éteint par `OFF`, la ROM (`POWEROFF`, `$C5C3`) range son état en RAM, puis demande au T6834 de couper l'alimentation (commande `$23`, « OFF REQUEST »). À l'allumage, elle interroge le T6834 (commande `$22`, « ON STATE ») :
- **bit 0 à 1** (rallumée après `OFF`) : la RAM est gardée ;
- **bit 0 à 0** (démarrage à froid) : la zone BASIC est effacée ;
- **bit 6 à 1** : reprise d'un `SLEEP`.

L'émulateur reproduit maintenant ce cycle : `emu.power_off(machine)` éteint par `OFF` et rend l'image de la RAM, et `emu.power_on(image)` rallume. Vérifié : après extinction et rallumage, le programme est toujours là (`LIST`, `RUN`), et un nouveau programme relit le fichier écrit avant l'extinction. Un démarrage à froid, lui, efface tout.

## La difficulté : la place en mémoire du code compilé

`FSET` prend sa place **en haut de la RAM**, justement là où le compilateur range un programme compilé en adresse automatique (`--org auto`). Il ne faut donc pas qu'un programme compilé recouvre la zone des fichiers. Pour la traduction en BASIC, le problème ne se pose pas : le BASIC respecte la limite que `FSET` abaisse.

Pistes : une option qui indique la taille de la zone de fichiers prévue, pour placer le code en dessous ; ou lire `RAMSTR` sur la machine.

## Étape 2 : QuickBASIC

**Traduction (`qb`) : faite.** Un programme QuickBASIC lit et écrit des fichiers en RAM :

```basic
OPEN "notes" FOR APPEND AS #1 LEN = 400   ' LEN = : taille du fichier (256 par défaut)
PRINT #1, note$
CLOSE #1
OPEN "notes" FOR INPUT AS #1
DO WHILE NOT EOF(1)
    LINE INPUT #1, ligne$
    PRINT ligne$
LOOP
```

| QuickBASIC | Traduction |
|---|---|
| `OPEN nom FOR OUTPUT AS #n [LEN = t]` | `INIT #n,"RAM:NOM",t`, puis remise à zéro des données (sous-programme) |
| `OPEN nom FOR APPEND AS #n [LEN = t]` | `INIT #n,"RAM:NOM",t` (créé s'il n'existe pas), puis pointeur d'écriture après les données |
| `OPEN nom FOR INPUT AS #n` | `INIT #n,"RAM:NOM"` (`NE Error` si absent) |
| `PRINT #n, ...`, `INPUT #n, ...` | tels quels |
| `WRITE #n, a$, x` | `PRINT #n,CHR$(34);A$;CHR$(34);",";X` (chaînes entre guillemets) |
| `LINE INPUT #n, a$` | `LINE INPUT #n,A$`, puis retrait du saut de ligne de tête |
| `EOF(n)` | sous-programme : pointeur de lecture du canal |
| `KILL nom` | `DELETE "NOM"` |
| `CLOSE` | rien |

- **La zone des fichiers :** en tête du programme, `FSET 1024` n'est fait que si la zone est plus petite. Un `FSET` plus petit donnerait `OM Error`, et un plus grand garde les fichiers.
- **Les noms :** ils sont ramenés à 6 caractères, en majuscules, sans extension (`notes.dat` devient `NOTES`), avec un avertissement.
- **Les canaux :** de 1 à 5.

Exemple : `exemples/qbasic/journal.qbas`. Chaque lancement ajoute une note, puis réaffiche toutes les notes.

**Mémoire gardée dans l'émulateur : faite.** L'option `--memoire FICHIER` de `emu` rallume le X-07 avec la RAM enregistrée (programmes et fichiers), puis l'éteint par `OFF` à la fin et enregistre sa RAM :

```sh
python3 x07asm.py emu exemples/qbasic/journal.qbas --memoire x07.mem -i "Acheter du pain"
python3 x07asm.py emu exemples/qbasic/journal.qbas --memoire x07.mem -i "Appeler Zoe"
```

Au second lancement, le journal contient les deux notes. Dans la fenêtre (`--fenetre`), on éteint en tapant `OFF`. Sans cela, la mémoire n'est pas enregistrée.

**Compilation : à faire.** Voir ci-dessous.

## Pour la suite

1. ~~Traduction~~ : faite.
2. **Compilation** (traduction compilée et `--direct`) : appeler le pilote `RAM:` de la ROM (`$E449`, `$E5B4`, `$E5CB`) depuis le code compilé, et placer le code sous la zone des fichiers.
3. ~~Émulateur~~ : fait pour `emu` (`--memoire`) ; reste l'éditeur-débogueur (`ide`).
