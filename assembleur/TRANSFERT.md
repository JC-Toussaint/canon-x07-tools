# Transfert vers le X-07 par le câble série

`x07asm.py send` envoie un programme machine au X-07 par sa prise série. Le câble est un module FT232RL relié à la prise SERIAL du X-07 ; le câblage est décrit dans [ref_docs/X07_FT232RL_liaison_serie.md](../ref_docs/X07_FT232RL_liaison_serie.md).

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
   - un `.bas`, compilé au passage ;
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

Il reste à l'essayer avec le câble et la machine réels. Deux points sont à confirmer : le nombre de bits d'arrêt du mode `B`, et le comportement exact de l'UART, dont l'émulation est déduite du code de la ROM.

## Autres moyens de transfert

| Moyen | Commande | Remarque |
|---|---|---|
| chargeur BASIC | `basic prog.bas -f bas` | à taper ou envoyer ; chaque ligne de DATA porte une somme de contrôle. Il faut assez de place sous le programme |
| vidage hexadécimal | `basic prog.bas -f txt` | à recopier avec l'« entreur de codes » du livre |

`LOAD"COM:"`, qui chargerait directement un programme BASIC envoyé en texte, n'a pas fonctionné dans l'émulateur, même en ralentissant beaucoup l'envoi. Ce mode reste à étudier.

## Fichiers

```
x07asm/serie.py      récepteur BASIC, protocole, accès au port, transfert émulé
tests/test_serie.py  protocole, X-07 émulé, pseudo-port série
```
