# Émulateur du Canon X-07

L'outil contient un simulateur du processeur Z80 (NSC800), qui exécute **la vraie ROM du X-07** (`ROM_x07/x07.bin`). La machine y démarre à froid comme à la mise sous tension, avec le message « Copyright(c) 1983 by Microsoft & Canon ».

Deux commandes s'en servent :

```sh
python3 x07asm.py emu exemples/devine.bas      # le BASIC du X-07 : le programme est tapé, puis RUN
python3 x07asm.py run exemples/devine.bas      # le même programme, compilé, lancé par EXEC
```

- **`emu`** fait exécuter le programme par **l'interpréteur BASIC de la ROM** : c'est le BASIC du X-07 sur votre PC.
- **`run`** compile le programme et lance le code machine obtenu sur la même machine émulée. Les deux écrans doivent être identiques ; c'est ainsi que le compilateur est testé.

À la fin, l'écran de 20 × 4 caractères est affiché, avec le nombre d'instructions Z80 exécutées.

## L'afficheur graphique

L'écran du X-07 peut être montré tel qu'il est vraiment : **120 × 32 points**, partagés par le texte (20 × 4 caractères de 6 × 8 points) et les graphismes. Le texte est dessiné avec **la police du X-07** (`ROM_x07/charset.rom`).

```sh
python3 x07asm.py emu exemples/devine.bas --fenetre    # fenêtre en direct, avec le clavier
python3 x07asm.py emu --fenetre                        # le BASIC du X-07, sans programme
python3 x07asm.py run jeu.bas --fenetre                # programme compilé
python3 x07asm.py emu exemples/graphisme.bas --fenetre  # texte, lignes, cercles, caractères redéfinis
python3 x07asm.py emu logo.bas --png logo.png          # image de l'écran final
python3 x07asm.py emu logo.bas --ecran                 # écran final en points, dans le terminal
```

![Le logo CANON des Applications en assembleur, tracé par PSET](../ref_docs/images/logo_canon.png)

**La fenêtre** montre l'écran en direct, à l'aspect d'un LCD (taille réglable par `--zoom`, 5 par défaut).

Dans ce mode, **la ROM affiche elle-même** : elle démarre à froid (« Copyright(c) 1983… »), et seul le sous-processeur T6834 est imité, au niveau de ses commandes (un caractère en x, y, le défilement, l'effacement…). Le **vrai éditeur plein écran** du X-07 reçoit donc les touches. Vous pouvez remonter avec les flèches sur une ligne affichée par `LIST`, la corriger et la valider par Entrée, comme sur la machine. Le programme, `RUN` et les réponses données par `-i` sont tapés au clavier, puis vous avez la main.

| Touche du PC | Pour le X-07 |
|---|---|
| lettres | majuscules, comme le X-07 ; avec Maj, minuscules |
| Entrée | RETURN : valide la ligne où se trouve le curseur |
| flèches | déplacent le curseur dans l'écran (`$1C` à `$1F`, lus aussi par `INKEY$`) |
| Retour arrière, Suppr, Inser, Origine | BS, DEL, INS, HOME |
| Échap | BREAK : arrête un programme, ou interrompt une saisie |

Un curseur clignote quand le X-07 attend une touche. Fermer la fenêtre arrête l'émulation.

**Un programme machine en mémoire**, comme s'il venait d'arriver par le câble série :

```sh
python3 x07asm.py emu --fenetre --charger exemples/table.bas --ram 16   # compilé au passage
python3 x07asm.py emu --fenetre --charger caso.asm
python3 x07asm.py emu --fenetre --charger prog.bin --org 3000 --entry 3010
```

`CLEAR 50,&H…` est tapé pour vous, puis le programme est mis en mémoire juste après ce `CLEAR` (avant, la pile et les chaînes du BASIC, encore en haut de la mémoire, l'écraseraient). Il reste à taper la commande `EXEC &H…` indiquée dans le terminal ; vous pouvez la relancer autant de fois que vous voulez. Un `.bas` est placé en haut de la RAM choisie par `--ram`, sauf si `--org` est donné.

Sous WSL2, la fenêtre s'ouvre grâce à WSLg (Windows 11 ou Windows 10 récent). Sans affichage graphique, utilisez `--png` ou `--ecran`.

**Graphismes reproduits :** `PSET`, `PRESET`, PEOR, `LINE`, `CIRCLE`, `POINT` (qui voit aussi le texte, comme sur la machine), les caractères redéfinis (UDC WRITE), le défilement et l'effacement d'une ligne. Les tracés de `LINE` et `CIRCLE` suivent les algorithmes classiques : ceux du T6834 ne sont pas dans la ROM, et un point peut donc différer en bout de tracé.

## Options

| Option | `emu` | `run` | Rôle |
|---|---|---|---|
| `-i LIGNE` | oui | oui | réponse à un `INPUT`, répétable dans l'ordre |
| `-k TOUCHES` | oui | oui | touches lues par `INKEY$`, par exemple `-k "ZZQ\r"` |
| `--ram 8\|16\|24` | oui (défaut 16) | oui (défaut 8) | mémoire de la machine, en Ko |
| `--max N` | oui | oui | arrêt après N instructions (boucle sans fin) |
| `--fenetre`, `--zoom N` | oui | oui | affichage graphique en direct |
| `--charger FICHIER` (`--org`, `--entry`) | oui, avec `--fenetre` | — | programme machine mis en mémoire, à lancer par `EXEC` |
| `--png FICHIER`, `--ecran` | oui | oui | écran final en image, ou en points dans le terminal |
| `--debug`, `--default`, `--strlen`, `--org` | — | oui | options du compilateur ([COMPILATEUR.md](COMPILATEUR.md)) |

Si `run` n'a pas de réponse pour un `INPUT`, il la demande au clavier du PC. Si la liste est épuisée, `emu` s'arrête et affiche l'écran obtenu jusque-là.

## Ce qui s'exécute pour de vrai

**Tout le code de la ROM**, de `$B000` à `$FFFF` :
- l'interpréteur et son évaluateur ;
- les calculs BCD, les fonctions mathématiques et `RND` ;
- les erreurs et leurs messages ;
- les pilotes de périphériques ;
- le traitement de BREAK et OFF, et le BEEP.

**Côté matériel :**
- **RAM :** au-delà de la taille choisie, une écriture est ignorée et une lecture rend `$FF`, comme sur la machine. Le démarrage à froid trouve ainsi la bonne taille (« 14940 Bytes free » avec 16 Ko).
- **UART du HD61L202F** (ports `$F6`/`$F7`) : les octets arrivent au rythme du débit choisi et déclenchent l'interruption de réception (INT B, vecteur `$0034`). Un octet non lu à temps est **perdu**, comme sur la machine. Cela sert à essayer le transfert série (`send --emu`, voir [TRANSFERT.md](TRANSFERT.md)).

## Ce qui est imité

Le **sous-processeur T6834**, qui gère l'écran, le clavier et les graphismes, n'est pas dans la ROM. Les routines qui dialoguent avec lui sont remplacées par du Python :

| Routine | Imitation |
|---|---|
| `$C1BE` affichage, `$CE9E` CLS, `$C164` curseur | écran de 120 × 32 points (police du X-07) et texte 20 × 4, codes de contrôle, défilement |
| `$C90A` INKEY, `$C8C5` attente de touche | touches fournies par `-k` |
| `$EBF2` / `$EBFF` saisie d'une ligne | lignes fournies par `-i`. Le tampon et HL sont rendus comme par la ROM |
| `$C92F` commande avec paramètres | graphismes (`PSET`, `PRESET`, PEOR, `LINE`, `CIRCLE`, `POINT`), caractères redéfinis, effacement d'une ligne, défilement |
| `$E428`, `$E334`, `$E348`, `$C0BD` | autres échanges avec le T6834 |
| `$C5A6` | demande d'extinction (OFF) : comptée, la machine ne s'éteint pas |

## Limites

- **Graphismes :** les tracés de `LINE` et `CIRCLE` sont des algorithmes classiques, pas ceux du T6834.
- **Interruptions :** pas d'interruption clavier (INT A) ni d'horloge ; les touches arrivent par les routines imitées. Pas de NMI.
- **Périphériques absents :** cassette, imprimante, table traçante X-710, interface vidéo X-720.
- **Son :** les ports du buzzer sont écrits, mais rien n'est joué.
- **Temps :** il est compté en instructions, pas en cycles. Les rapports de vitesse donnés dans la documentation sont donc approximatifs.
- **Codes du T6834** (touches de `STICK`, motifs des caractères…) : ils ne sont pas dans la ROM. Leurs valeurs viennent des livres.

## Débogueur

`python3 x07asm.py debug PROGRAMME` exécute un programme machine pas à pas dans cet émulateur : points d'arrêt, registres, mémoire, variables BASIC. Voir [DEBOGUEUR.md](DEBOGUEUR.md).

## Usage en Python

```python
from x07asm import emu
sortie, machine = emu.run_basic('10 PRINT 1/3', inputs=[], keys="")
print(sortie)                  # ' .33333333333333 \n'
print(machine.screen_text())   # l'écran du X-07
```

- `emu.boot(ram)` rend une machine démarrée à froid. Le démarrage est mémorisé, donc les appels suivants sont instantanés.
- `emu.run_binary(mem, entrée)` exécute un programme machine comme `CLEAR 50,&H…` suivi de `EXEC`.
- La variable d'environnement `X07_ROM` indique un autre fichier de ROM.

## Fichiers

```
x07asm/sim.py        processeur Z80, ports, UART, imitation du T6834
x07asm/emu.py        démarrage de la ROM, frappe du programme, RUN, EXEC
x07asm/lcd.py        écran de 120 x 32 points, police, graphismes, PNG, braille
x07asm/afficheur.py  fenêtre en direct (tkinter) et clavier
x07asm/debug.py      débogueur (points d'arrêt, pas à pas, registres)
```
