# Canon X-07 ↔ PC via FTDI FT232RL — liaison série

Source : *Canon X-07 Technical Guide / Parts Catalog* (`x07_technicalguide.pdf`).

- Schéma de la carte mémoire, connecteur **CN9 « SERIAL PORT »** : section 9.3, p. 34 du guide.
- Convertisseur RS-232C **X-722** (schéma, chronogrammes, dépannage) : section 11-3, p. 57 à 65.

---

## 1. Faisabilité

**Oui, c'est possible.** Le port série du X-07 **n'est pas en niveaux RS-232** (±12 V). Il fonctionne en **logique 0 / 4,6 V** (alimentation VCC1/VCC2 = 4,6 V), avec la **polarité TTL normale** : la ligne est à l'état haut au repos. Canon vendait d'ailleurs le X-722 pour passer en vrai RS-232.

Un module FT232RL **en version TTL** se branche donc directement, **sans MAX232 et sans inversion des données**.

> ⚠️ N'utilisez pas un câble « USB-RS232 » à niveaux ±12 V : il faut un module ou un câble FT232RL **TTL**.

---

## 2. Analyse des étages d'entrée/sortie (carte mémoire, p. 34)

| Broche CN9 | Signal | Circuit côté X-07 | Conséquence |
|---|---|---|---|
| SP-4 | **TXD** (sortie) | Transistor PNP TR201 (2SA1115) relié au +4,6 V, puis R201 = 100 Ω. ~4,6 V au repos. **Aucune résistance de rappel à la masse côté X-07** : le niveau bas est une ligne « en l'air ». | Il faut une **résistance de 10 kΩ vers GND** côté récepteur. |
| SP-5 | **RXD** (entrée) | R207 = 10 kΩ, puis la base du NPN TR203 (2SC2603), avec R209 = 3,3 kΩ vers la masse et une diode de protection D1 (1S1588). Seuil d'environ 2,5 V. | Accepte directement du 3,3 V ou du 5 V. |
| SP-6 | **CTS** (entrée) | Même circuit que RXD (R210 = 10 kΩ, TR204, R211). Si la broche est en l'air, /CTS est tiré à l'état haut par 47 kΩ, donc **CTS est inactif**. | **Il faut forcer CTS à l'état haut**, sinon le X-07 n'émet pas. |
| SP-7 | RTS (sortie) | PNP TR202, même montage que TXD. | Optionnel, non utilisé. |
| SP-2, SP-8 | GND | — | Masse commune. |
| SP-1 | LTXD | Sortie pour le coupleur optique X-720 (IC20, TR205). | Ne pas brancher. |
| SP-3 | NC | — | — |
| SP-9 | **VBB** | **Tension des piles, environ 6 V.** | **Ne surtout pas brancher.** |

### Pourquoi CTS doit être à l'état haut

Le guide de dépannage du X-722 (p. 65) indique, pour le cas « Transmission impossible » : *« Is CTS signal "H"? »*, et précise :

> *CTS: A signal for X-07 to know that a receiver is ready for receiving. Partner's signal is RTS.*

Si SP-6 reste en l'air, le X-07 **reçoit** normalement, mais **n'émet rien** vers le PC.

### Pourquoi une résistance de 10 kΩ vers la masse

La sortie TXD est un transistor PNP relié au +4,6 V, sans résistance vers la masse. Sans charge, la ligne ne redescend jamais franchement à 0 V. La résistance de rappel interne du FT232R (environ 200 kΩ) la maintiendrait même à l'état haut. Le X-722 a lui aussi des résistances de 10 kΩ vers la masse sur ses entrées (R28, R29).

---

## 3. Brochage de CN9

Dessin repris du guide (encadré « SERIAL PORT CN9 », p. 34) :

```
                     SERIAL PORT CN9
        ┌───────────────────────────────────────┐
       ╱                                         ╲
      ╱    ┌───┐      ┌───┐      ┌───┐      ┌───┐  ╲
     │     │ 2 │      │ 4 │      │ 6 │      │ 8 │   │
     │     └───┘      └───┘      └───┘      └───┘   │
     │      GND        TXD        CTS        GND    │
     │ ┌───┐      ┌───┐      ┌───┐      ┌───┐      ┌───┐
     │ │ 1 │      │ 3 │      │ 5 │      │ 7 │      │ 9 │
     │ └───┘      └───┘      └───┘      └───┘      └───┘
     │  LTXD       NC         RXD        RTS        VBB │
     └──────────────────┐            ┌──────────────────┘
                        └────────────┘   ← détrompeur (encoche en bas)
```

Version compacte :

```
   Rangée haute :    [2]GND    [4]TXD    [6]CTS    [8]GND
   Rangée basse : [1]LTXD  [3]NC   [5]RXD   [7]RTS   [9]VBB
```

> ⚠️ **Sens de lecture :** le guide n'indique pas si ce dessin montre la face avant de la prise ou le côté soudure. Le connecteur CN12 du X-722 (p. 62) est dessiné avec le même brochage, tourné de 180°. **Vérifiez l'orientation au multimètre avant de souder** (voir §6).

---

## 4. Câblage

| X-07 (CN9) | Signal | FT232RL |
|---|---|---|
| **SP-8** (ou SP-2) | GND | **GND** |
| **SP-4** | TXD du X-07 | **RXD**, avec **10 kΩ vers GND** |
| **SP-5** | RXD du X-07 | **TXD** |
| **SP-6** | CTS | **+5 V** (simple fil) |
| SP-1, SP-3, SP-7, SP-9 | — | Non connectés |

```
FT232RL (VCCIO = 5V)            Canon X-07 CN9
  GND  ─────────────────────────  SP-8 GND
  RXD  ──┬──────────────────────  SP-4 TXD
         └─[10kΩ]── GND
  TXD  ─────────────────────────  SP-5 RXD
  +5V  ─────────────────────────  SP-6 CTS   ← simple fil, pas de composant
                                  SP-1, SP-3, SP-7, SP-9 : NON CONNECTÉS
```

**Liste du matériel :**

- 1 module FT232RL (TTL) ;
- 1 résistance de 10 kΩ (pull-down sur RXD du FTDI) ;
- 1 fil entre le +5 V du FTDI et SP-6 (vous pouvez aussi le souder dans la fiche du câble) ;
- 1 fiche compatible avec CN9.

---

## 5. Réglages du FTDI

1. **VCCIO = 5 V** (cavalier 3,3 V / 5 V sur la plupart des modules). Le X-07 envoie du 4,6 V : en 5 V, les niveaux lus sont sûrs. En 3,3 V, l'entrée RXD du X-07 fonctionne aussi (seuil d'environ 2,5 V), mais avec moins de marge.
2. **Ne pas relier le VCC du FTDI à l'alimentation du X-07.** Seule la masse est commune. Le +5 V ne va que sur SP-6 (CTS), qui est une entrée à travers 10 kΩ (environ 0,4 mA).
3. **Pas d'inversion, pas de reprogrammation.** Les lignes TXD et RXD du FT232RL ont déjà la bonne polarité. FT_Prog n'est **pas nécessaire**.

> Note : FT_Prog ne servirait que pour un contrôle de flux matériel. RTS# et CTS# du FTDI sont actifs à l'état bas, alors que CTS et RTS du X-07 sont actifs à l'état haut. Il faudrait alors les inverser dans l'EEPROM (« Invert RTS », « Invert CTS ») et mettre 10 kΩ vers GND sur SP-7. C'est inutile avec le câblage minimal ci-dessus.

**Aucun risque d'alimenter le X-07 par ses entrées quand il est éteint.** RXD et CTS arrivent sur la base de transistors NPN reliés à la masse, et non sur l'alimentation interne.

---

## 6. Vérifications avant de souder

X-07 allumé, câble FTDI débranché, multimètre par rapport à GND (SP-8 ou SP-2) :

| Broche | Tension attendue |
|---|---|
| SP-4 (TXD) | environ **4,6 V** au repos |
| SP-9 (VBB) | **tension des piles**, environ 6 V |

Si vous trouvez ces deux tensions là où le dessin les place, l'orientation est la bonne.

---

## 7. Côté logiciel

- La **vitesse**, la **parité** et la **longueur des données** doivent être identiques sur le X-07 et sur le terminal du PC (recommandation du guide de dépannage du X-722).
- Pour tester, le guide cite le programme de vérification **`JSERI.X07`**.
- Côté PC : port COM virtuel du FTDI, sans contrôle de flux (*none*).

### Réglages du port série du X-07 (vérifiés dans la ROM)

- **Ouverture en BASIC :** `INIT#1,"COM:",vitesse,"mode"`. La vitesse et le mode sont facultatifs (4800 bauds et mode `B` par défaut). On lit ensuite par `INP(#1)` et on écrit par `OUT#1,octet`.
- **Vitesse :** de 100 à 8000 bauds, avec un diviseur de 24000/vitesse − 1. Les vitesses exactes sont 1200, 2400, 4800 et 8000 bauds ; **9600 est refusé**.
- **Mode :** une lettre de `A` à `H`. Elle règle la longueur des données et la parité : `B` = 8 bits sans parité, `G` = 7 bits parité paire (Minitel). Le nombre de bits d'arrêt n'est pas établi ; le PC envoie donc avec 2 bits d'arrêt, que le X-07 accepte dans les deux cas.
- **Réception :** sous interruption, dans un tampon de **32 octets**. La ROM coupe RTS dès 6 octets en attente. Avec le câblage minimal ci-dessus (RTS non relié), le PC doit donc se régler lui-même sur le X-07.

### Envoyer un programme : `x07asm.py send`

Le dossier `assembleur/` fournit le transfert complet. Le protocole par blocs de 16 octets, avec accusé de réception, convient au câblage minimal ; le détail est dans `assembleur/COMPILATEUR.md`.

1. **Une seule fois, tapez le récepteur sur le X-07.** Depuis le dossier `assembleur/` :
   ```sh
   python3 x07asm.py recepteur                       # à l'écran
   python3 x07asm.py recepteur -o recepteur.bas      # dans un fichier
   python3 x07asm.py recepteur --baud 1200           # pour une autre vitesse (1200, 2400, 4800, 8000)
   ```
   Utilisez la même vitesse ici et dans `send --baud`. Le récepteur reste en mémoire, même machine éteinte.
2. **Sur le PC :** `python3 x07asm.py send monprog.bas --port /dev/ttyUSB0 --ram 16`. Un `.bas` est compilé au passage ; un `.bin`, un `.hex` ou un `.asm` sont aussi acceptés.
3. **Sur le X-07 :** `CLEAR 50,&H…` (la commande exacte est affichée par le PC), puis `RUN`. À la fin, le X-07 affiche `OK. EXEC &H…`.

**Sous WSL2,** le module USB n'est pas visible par défaut. Deux possibilités :
- l'attacher depuis Windows avec `usbipd attach --wsl --busid <n°>` (outil usbipd-win), puis utiliser `/dev/ttyUSB0` ;
- lancer `python x07asm.py send … --port COM3` depuis Windows, avec pyserial installé (`pip install pyserial`).
