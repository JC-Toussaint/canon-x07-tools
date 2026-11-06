# Transfert vers le X-07 par le câble série

`x07asm.py send` envoie un programme machine au X-07 par sa prise série. Le câble est un module FT232RL relié à la prise SERIAL du X-07 ; le câblage est décrit dans [ref_docs/X07_FT232RL_liaison_serie.md](../ref_docs/X07_FT232RL_liaison_serie.md).

> ⚠️ **Le X-07 a une liaison série en logique inversée** (0 V au repos). Il faut inverser TXD et RXD du FT232R (FT_Prog : *Invert TXD*, *Invert RXD*), sinon le récepteur s'arrête sur « IO Error in 30 ». Voir la fiche de câblage, §5.

```sh
python3 x07asm.py recepteur                                    # à taper une fois sur le X-07
python3 x07asm.py send jeu.bas --ram 16 --port /dev/ttyUSB0    # l'envoi
python3 x07asm.py send jeu.bas --ram 16 --emu                  # essai complet sans câble
```

## Mode d'emploi

1. **Une seule fois, tapez le récepteur sur le X-07.** C'est un programme BASIC de 13 lignes, produit par la commande `recepteur` :
   ```sh
   python3 x07asm.py recepteur                       # à l'écran
   python3 x07asm.py recepteur -o recepteur.bas      # dans un fichier
   python3 x07asm.py recepteur --baud 1200           # pour une autre vitesse (1200, 2400, 4800, 8000)
   ```
   Le X-07 le garde en mémoire, même éteint. Vous pouvez aussi le sauvegarder sur cassette (`CSAVE"RECEPT"`).
2. **Sur le PC, lancez `send`.** Il accepte :
   - un `.bas`, un `.qbas` (QuickBASIC) ou un `.pas` (Pascal), compilé au passage ;
   - un `.asm`, assemblé au passage ;
   - un `.hex` ;
   - un `.bin`, avec `--org`, et `--entry` si l'adresse de lancement diffère de l'adresse de chargement.

   Le PC affiche la commande `CLEAR` à taper, puis attend le X-07.
3. **Sur le X-07, tapez `CLEAR 50,&H…`, puis `RUN`.** Le transfert se termine par `OK. EXEC &H…`. Si le `CLEAR` a été oublié, le X-07 affiche la commande à taper, et le PC le signale aussi.
4. **Tapez `EXEC &H…`** pour lancer le programme.

| Option de `send` | Rôle |
|---|---|
| `--port` | port série : `/dev/ttyUSB0` sous Linux, `COM3` sous Windows |
| `--baud` | 1200, 2400, 4800 (défaut) ou 8000. 9600 n'existe pas sur le X-07. Même valeur que pour `recepteur` |
| `--ram`, `--org` | comme pour `basic` : mémoire du X-07, implantation |
| `--timeout` | attente maximale d'une réponse du X-07, en secondes (défaut 60) |
| `--emu` | transfert complet avec le X-07 émulé, sans câble |

## Sous WSL2

Un module USB branché sous Windows n'est pas visible dans WSL2. Deux solutions :

- **L'attacher à WSL** avec [usbipd-win](https://github.com/dorssel/usbipd-win), depuis Windows : `usbipd list`, puis `usbipd attach --wsl --busid <n°>`. Il apparaît alors comme `/dev/ttyUSB0`.
- **Lancer `send` depuis Windows**, avec Python et pyserial (`pip install pyserial`) : `python x07asm.py send jeu.bas --port COM3`.

L'outil utilise pyserial s'il est installé, sinon l'accès direct `termios` (Linux, WSL). Sans pyserial, seules les vitesses 1200, 2400 et 4800 sont possibles.

## Ce que la ROM impose

Les réglages ci-dessous ont été lus dans la ROM :

- **Ouverture :** `INIT#1,"COM:",vitesse,"mode"`. Lecture par `INP(#1)`, écriture par `OUT#1,octet`.
- **Vitesse :** de 100 à 8000 bauds, avec un diviseur de 24000/vitesse − 1.
- **Mode :** une lettre de A à H. Le récepteur utilise `B`, qui donne 8 bits sans parité. Le PC envoie en 8 bits, sans parité, avec 2 bits d'arrêt ; le X-07 accepte cela qu'il en attende un ou deux.
- **Réception :** sous interruption, dans un tampon de **32 octets**. La ROM coupe RTS dès 6 octets en attente. Avec le câblage minimal, RTS n'est pas relié : le PC doit donc se régler lui-même sur le X-07.

## Protocole

```
X-07 -> PC   « R »                             le récepteur est prêt
PC -> X-07   adresse, longueur, lancement      3 mots, poids faible d'abord
PC -> X-07   blocs de 16 octets                après chacun, le X-07 répond « K »
PC -> X-07   somme des octets (mod 65536)      envoyée avec le dernier bloc
X-07 -> PC   « O » correct, « E » erreur, « C » CLEAR à faire d'abord
```

Le PC n'a jamais plus de 22 octets d'avance, ce qui tient dans le tampon de 32 octets. Le débit s'adapte ainsi seul à la vitesse du BASIC du X-07 : environ 70 octets par seconde, soit une dizaine de secondes pour 750 octets.

## Vérification

- **Avec le X-07 émulé**, qui fait tourner les vrais pilotes série de la ROM et une UART émulée : le binaire arrive intact à 1200, 4800 et 8000 bauds, sans octet perdu. Le cas du `CLEAR` oublié est bien détecté.
- **Par un pseudo-port série Linux** relié au X-07 émulé : le vrai code d'envoi fonctionne, avec pyserial comme avec termios.

**Avec la machine réelle**, le premier essai a montré que la liaison du X-07 est en logique inversée : le « R » arrive en `2B 00` sur un FT232RL non inversé, et le X-07 répond « IO Error in 30 ». Avec TXD et RXD inversés (par un 74HC04 sur un clone de FT232R), la liaison fonctionne dans les deux sens, et l'envoi en texte (`--texte`) est vérifié. Le transfert d'un programme machine par le récepteur reste à confirmer. Il reste aussi à vérifier le nombre de bits d'arrêt du mode `B`.

## Envoi d'un programme BASIC en texte (`--texte`)

`send --texte` envoie un `.bas` **sans le compiler**, comme si on le tapait au clavier du X-07. Aucun récepteur n'est nécessaire.

```sh
python3 x07asm.py send jeu.bas --texte --port COM3        # l'envoi
python3 x07asm.py send jeu.bas --texte --emu              # essai sans câble
```

1. Sur le PC, lancez la commande : elle affiche la ligne à taper sur le X-07, puis attend.
2. **Sur le X-07, tapez** (avec la même vitesse que `--baud`) :
   ```
   INIT#5,"COM:",4800,"B":EXEC &HEE1F
   ```
   À partir de là, le BASIC lit ses lignes **sur la prise série**, et le clavier du X-07 ne répond plus.
3. Sur le PC, appuyez sur Entrée : les lignes partent une à une, puis le PC envoie `POKE &HA3,&H0A:POKE &HA4,&HC9`, qui **rend le clavier** au X-07.
4. Sur le X-07 : `LIST` pour vérifier, puis `RUN`.

Les lignes s'ajoutent au programme déjà en mémoire : faites `NEW` avant l'étape 2 si nécessaire.

| Option | Rôle |
|---|---|
| `--pause-car` | pause après chaque caractère, en secondes (défaut 0,02) |
| `--pause-ligne` | pause après chaque ligne, le temps que le X-07 la range (défaut 0,5) |
| `--garder` | ne pas rendre le clavier à la fin : le X-07 continue de lire la prise série, et l'on peut lui envoyer des commandes depuis un terminal |

Rien ne signale au PC que le X-07 a fini une ligne : pas d'écho, et RTS n'est pas câblé. L'envoi repose donc sur des pauses fixes. Si des caractères manquent dans les lignes longues, augmentez `--pause-car` ; si des lignes entières manquent ou se collent, augmentez `--pause-ligne`. Les lignes de plus de 79 caractères et les caractères hors ASCII (lettres accentuées) sont refusés avant l'envoi : l'éditeur du X-07 les perdrait.

### La fonction cachée `$EE1F`

Lue dans la ROM : **aucune routine ne l'appelle**, on n'y accède que par `EXEC &HEE1F`.

- Elle lit l'entrée du **fichier #5** dans la table des fichiers ouverts (`$02E5` = `$02C5` + 4 × 8). D'où l'obligation d'ouvrir COM: sous le numéro 5.
- Elle range la routine d'entrée de ce dispositif dans le **crochet d'entrée de la console** (`JP` en `$00A2`, normalement `JP $C90A`, la lecture du clavier). Pour COM:, c'est `$E00A`.
- L'attente d'une touche de la ROM (`$C8C5`) appelle ce crochet : l'éditeur reçoit donc les caractères de la prise série.

Si un envoi est interrompu, le clavier reste muet. Pour le rétablir, envoyez la ligne `POKE &HA3,&H0A:POKE &HA4,&HC9` (suivie d'un retour chariot) depuis un terminal, ou éteignez puis rallumez le X-07.

### Vérification

Dans l'émulateur, avec le vrai éditeur de la ROM et l'UART émulée : le programme reçu est **identique, octet pour octet**, à celui tapé au clavier, sans octet perdu, et le clavier est bien rétabli. L'émulation n'impose aucune pause, car son affichage est instantané.

**Sur la machine réelle**, à 4800 bauds, avec `exemples/titre.bas` (lignes de plus de 70 caractères) :

| `--pause-car` | `--pause-ligne` | Résultat |
|---|---|---|
| 0,01 | 0,3 | erreurs : le X-07, qui affiche et fait défiler chaque ligne, prend du retard et son tampon de 32 octets déborde |
| 0,02 | 0,5 | programme reçu sans erreur : ce sont les valeurs par défaut |

Compter environ 0,02 s par caractère et 0,5 s par ligne : une dizaine de lignes partent en une quinzaine de secondes.

## Autres moyens de transfert

| Moyen | Commande | Remarque |
|---|---|---|
| chargeur BASIC | `basic prog.bas -f bas` | à taper ou envoyer ; chaque ligne de DATA porte une somme de contrôle. Il faut assez de place sous le programme |
| vidage hexadécimal | `basic prog.bas -f txt` | à recopier avec l'« entreur de codes » du livre |

`LOAD"COM:"`, qui chargerait directement un programme BASIC envoyé en texte, n'a pas fonctionné dans l'émulateur, même en ralentissant beaucoup l'envoi. L'envoi en texte (`--texte`, ci-dessus) le remplace.

## Fichiers

```
x07asm/serie.py      récepteur BASIC, protocole, accès au port, transfert émulé
tests/test_serie.py  protocole, X-07 émulé, pseudo-port série
```
