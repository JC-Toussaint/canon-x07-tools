# Guide de démarrage : d'un programme BASIC au Canon X-07

Ce guide suit un programme du début à la fin : l'écrire, l'essayer sur le PC, le compiler, l'envoyer au X-07 par le câble série et le lancer. Toutes les sorties ci-dessous sont réelles.

Toutes les commandes se tapent dans le dossier `assembleur/` :

```sh
cd assembleur
```

**Prérequis :**
- Python 3, sans autre bibliothèque. pyserial est facultatif.
- Le vidage de la ROM dans `ROM_x07/x07.bin`, déjà présent dans le dépôt.
- Pour le transfert, le câble FT232RL décrit dans [ref_docs/X07_FT232RL_liaison_serie.md](ref_docs/X07_FT232RL_liaison_serie.md).

## 1. Écrire le programme

Un fichier texte ordinaire, dans le BASIC du X-07. Par exemple `exemples/table.bas` :

```basic
10 REM TABLE DE MULTIPLICATION
20 CLS:INPUT "TABLE DE";N
30 FOR I=1 TO 9
40 PRINT I;"x";N;"=";I*N
50 NEXT
60 PRINT "MOYENNE";N*5
```

## 2. L'essayer avec le vrai BASIC du X-07

```sh
python3 x07asm.py emu exemples/table.bas -i 7
```

La commande démarre la **ROM du X-07 dans un émulateur**, tape le programme et fait `RUN`. `-i 7` est la réponse à l'`INPUT`. Vous obtenez l'écran de 20 × 4 caractères du X-07 :

```
+--------------------+
| 8 x 7 = 56         |
| 9 x 7 = 63         |
|MOYENNE 35          |
|>                   |
+--------------------+
```

Une faute de frappe y donne le même message que sur la machine, par exemple `SN Error in 40`.

**Pour voir l'écran tel qu'il est vraiment** (120 × 32 points, police du X-07) et jouer avec le clavier, ajoutez `--fenetre` :

```sh
python3 x07asm.py emu exemples/table.bas --fenetre
```

Le programme répond aux touches. En fin de programme, l'invite `>` du BASIC revient : `LIST`, `RUN`, Échap pour BREAK… Sans affichage graphique, `--ecran` dessine l'écran en points dans le terminal, et `--png image.png` l'enregistre. Voir [assembleur/EMULATEUR.md](assembleur/EMULATEUR.md).

## 3. Le compiler et vérifier qu'il se comporte pareil

```sh
python3 x07asm.py run exemples/table.bas -i 7
```

`run` compile le programme en langage machine et l'exécute sur le même X-07 émulé. L'écran doit être **identique** à celui de l'étape 2. Ici, il l'est.

La version compilée exécute 34 662 instructions, contre 90 135 pour l'interpréteur. Avec des entiers (`DEFINT A-Z`), elle irait jusqu'à 30 fois plus vite ; voir [assembleur/COMPILATEUR.md](assembleur/COMPILATEUR.md).

**Pour lancer vous-même le programme compilé, comme sur la machine**, chargez-le dans la fenêtre de l'émulateur : voir l'étape 4.

## 4. Le compiler pour la machine

```sh
python3 x07asm.py basic exemples/table.bas --ram 16
```

```
773 octets de code, 940 avec les variables : $3C40-$3FEB
sur le X-07 : CLEAR 50,&H3C3F  puis  EXEC &H3C40
  -> exemples/table.asm
  -> exemples/table.bin
```

- **`--ram`** : mettez la mémoire de votre X-07 (8, 16 ou 24 Ko). Le programme est placé en haut de cette mémoire.
- **Les deux commandes affichées** (`CLEAR`, puis `EXEC`) sont celles qu'il faudra taper sur la machine.
- **`exemples/table.asm`** est le source assembleur, lisible et modifiable.
- **`exemples/table.bin`** est le code machine, à charger à l'adresse indiquée (ici `$3C40`). D'autres formats s'obtiennent par `-f` : `-f asm,bin,hex,lst,bas` (`bas` donne un chargeur BASIC à taper sur la machine).

### Charger le programme compilé dans l'émulateur

Avant de l'envoyer à la machine, on peut le charger dans la fenêtre de l'émulateur et le lancer soi-même par `EXEC`, exactement comme sur le X-07. Exemple avec `premiers.bas` (le crible d'Ératosthène) :

```sh
python3 x07asm.py basic exemples/premiers.bas --ram 16
```

```
552 octets de code, 1562 avec les variables : $39D0-$3FE9
sur le X-07 : CLEAR 50,&H39CF  puis  EXEC &H39D0
  -> exemples/premiers.asm
  -> exemples/premiers.bin
```

Un `.bin` ne contient pas son adresse de chargement : donnez-la par `--org`.

```sh
python3 x07asm.py emu --fenetre --charger exemples/premiers.bin --org 39D0 --ram 16
```

On peut aussi donner directement le `.bas`, qui est alors compilé au passage :

```sh
python3 x07asm.py emu --fenetre --charger exemples/premiers.bas --ram 16
```

Dans la fenêtre du X-07 :

1. `CLEAR 50,&H39CF` est tapé pour vous, puis le programme est mis en mémoire.
2. Tapez `EXEC &H39D0` puis Entrée.
3. Les nombres premiers jusqu'à 499 s'affichent, puis l'invite `>` revient.

`EXEC &H39D0` peut être relancé autant de fois que vous voulez. `RUN`, lui, ne fait rien : aucun programme BASIC n'a été tapé, seul le code machine est en mémoire.

Prenez la même valeur de `--ram` pour compiler et pour charger : sinon le programme est placé, ou attendu, à une autre adresse.

## 5. L'envoyer au X-07 par le câble série

**Une seule fois,** tapez sur le X-07 le petit programme de réception. Il reste en mémoire, même machine éteinte ; vous pouvez aussi le sauver sur cassette (`CSAVE"RECEPT"`) :

```sh
python3 x07asm.py recepteur
```

**À chaque envoi :**

1. **Sur le PC :**
   ```sh
   python3 x07asm.py send exemples/table.bas --ram 16 --port /dev/ttyUSB0
   ```
   Le PC compile le programme puis attend le X-07. Un programme déjà compilé s'envoie aussi : `send exemples/premiers.bin --org 39D0`.
2. **Sur le X-07 :** `CLEAR 50,&H3C3F`, puis `RUN`. Le transfert prend une dizaine de secondes et se termine par :
   ```
   RECEPTION...
   OK. EXEC &H3C40
   ```
3. **Sur le X-07 :** `EXEC &H3C40`.

Le récepteur contrôle chaque bloc reçu par une somme de contrôle.

**Sous WSL2,** le module USB n'est pas visible par défaut. Attachez-le avec `usbipd attach --wsl --busid <n°>`, ou lancez `send` depuis Windows avec `--port COM3`.

**Pour essayer tout le transfert sans câble ni machine :**

```sh
python3 x07asm.py send exemples/table.bas --ram 16 --emu
```

## 6. Sans câble : le chargeur BASIC à taper

```sh
python3 x07asm.py basic exemples/premiers.bas --ram 16 -f bas
```

Cette commande produit `exemples/premiers_chargeur.bas`, un programme BASIC ordinaire :

```
10 REM PREMIERS - chargeur x07asm
20 CLEAR 50,&H39CF
30 L=1000
40 READ A$:IF A$="*" THEN 100
...
1000 DATA 39D0,8,F5,C5,D5,E5,DD,E5,FD,E5,1816
1010 DATA 39D8,8,ED,73,F3,3B,2A,AB,0,22,901
...
1690 DATA *
```

1. **Sur le X-07 :** tapez le chargeur, puis `RUN`. Il range les octets en mémoire par `POKE`, puis affiche `OK. EXEC &H39D0`.
2. **Sur le X-07 :** `EXEC &H39D0`.

Chaque ligne de `DATA` se termine par une somme de contrôle : une faute de frappe donne `ERREUR LIGNE n`, avec le numéro de la ligne à corriger. Pour `premiers.bas`, cela fait 70 lignes de `DATA` : c'est long, mais faisable. Une fois tapé, sauvez le chargeur sur cassette (`CSAVE`) pour ne pas avoir à le retaper. Le chargeur occupe lui-même de la mémoire : il faut assez de place sous le programme compilé.

**Autre possibilité :** `-f txt` produit un vidage hexadécimal, à recopier avec l'« entreur de codes » du livre.

**Dans tous les cas :**

- **`--ram`** doit correspondre à la mémoire réelle de votre X-07. Avec 8 Ko, recompilez avec `--ram 8`, sinon l'adresse sera fausse.
- **Le code n'est pas protégé :** il est perdu après un `CLEAR` qui remonte le haut de la zone BASIC, ou après un démarrage à froid. Il suffit alors de le recharger.

## 7. Pour aller plus loin

| Pour… | Voir |
|---|---|
| le BASIC compilé : types, vitesse, différences | [assembleur/COMPILATEUR.md](assembleur/COMPILATEUR.md) |
| programmer directement en assembleur, désassembler la ROM | [assembleur/README.md](assembleur/README.md) |
| les erreurs des livres de référence | [ref_docs/ERRATA.md](ref_docs/ERRATA.md) |
| le câble série | [ref_docs/X07_FT232RL_liaison_serie.md](ref_docs/X07_FT232RL_liaison_serie.md) |

> **État :** tout ce parcours a été vérifié dans l'émulateur, qui exécute la vraie ROM. Il n'a pas encore été essayé sur un X-07 réel. Pour le premier essai, `exemples/test_x07.bas` vérifie les points qui dépendent de la machine.
