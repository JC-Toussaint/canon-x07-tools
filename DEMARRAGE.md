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

## 3. Le compiler et vérifier qu'il se comporte pareil

```sh
python3 x07asm.py run exemples/table.bas -i 7
```

`run` compile le programme en langage machine et l'exécute sur le même X-07 émulé. L'écran doit être **identique** à celui de l'étape 2. Ici, il l'est.

La version compilée exécute 34 581 instructions, contre 90 135 pour l'interpréteur. Avec des entiers (`DEFINT A-Z`), elle irait jusqu'à 30 fois plus vite ; voir [assembleur/COMPILATEUR.md](assembleur/COMPILATEUR.md).

## 4. Le compiler pour la machine

```sh
python3 x07asm.py basic exemples/table.bas --ram 16
```

```
720 octets de code, 821 avec les variables : $3CC0-$3FF4
sur le X-07 : CLEAR 50,&H3CBF  puis  EXEC &H3CC0
  -> exemples/table.asm
  -> exemples/table.bin
```

- **`--ram`** : mettez la mémoire de votre X-07 (8, 16 ou 24 Ko). Le programme est placé en haut de cette mémoire.
- **Les deux commandes affichées** (`CLEAR`, puis `EXEC`) sont celles qu'il faudra taper sur la machine.
- **`exemples/table.asm`** est le source assembleur, lisible et modifiable.

## 5. L'envoyer au X-07 par le câble série

**Une seule fois,** tapez sur le X-07 le petit programme de réception. Il reste en mémoire, même machine éteinte :

```sh
python3 x07asm.py recepteur
```

**À chaque envoi :**

1. **Sur le PC :**
   ```sh
   python3 x07asm.py send exemples/table.bas --ram 16 --port /dev/ttyUSB0
   ```
   Le PC compile le programme puis attend le X-07.
2. **Sur le X-07 :** `CLEAR 50,&H3CBF`, puis `RUN`. Le transfert prend une dizaine de secondes et se termine par :
   ```
   RECEPTION...
   OK. EXEC &H3CC0
   ```
3. **Sur le X-07 :** `EXEC &H3CC0`.

**Sous WSL2,** le module USB n'est pas visible par défaut. Attachez-le avec `usbipd attach --wsl --busid <n°>`, ou lancez `send` depuis Windows avec `--port COM3`.

**Pour essayer tout le transfert sans câble ni machine :**

```sh
python3 x07asm.py send exemples/table.bas --ram 16 --emu
```

## 6. Sans câble

Deux autres façons de mettre le programme dans le X-07 :

- **Chargeur BASIC :** `python3 x07asm.py basic exemples/table.bas -f bin,bas` produit `table_chargeur.bas`, à taper sur le X-07 puis à lancer par `RUN`. Chaque ligne de `DATA` porte une somme de contrôle. Il faut assez de place sous le programme pour ce chargeur.
- **Vidage hexadécimal :** `-f txt` produit les octets à recopier avec l'« entreur de codes » du livre.

## 7. Pour aller plus loin

| Pour… | Voir |
|---|---|
| le BASIC compilé : types, vitesse, différences | [assembleur/COMPILATEUR.md](assembleur/COMPILATEUR.md) |
| programmer directement en assembleur, désassembler la ROM | [assembleur/README.md](assembleur/README.md) |
| les erreurs des livres de référence | [ref_docs/ERRATA.md](ref_docs/ERRATA.md) |
| le câble série | [ref_docs/X07_FT232RL_liaison_serie.md](ref_docs/X07_FT232RL_liaison_serie.md) |

> **État :** tout ce parcours a été vérifié dans l'émulateur, qui exécute la vraie ROM. Il n'a pas encore été essayé sur un X-07 réel. Pour le premier essai, `exemples/test_x07.bas` vérifie les points qui dépendent de la machine.
