# Canon X-07 ↔ FT232 : montage avec un inverseur 74HC04

La liaison série du X-07 est en **logique inversée** : 0 V au repos (voir [X07_FT232RL_liaison_serie.md](X07_FT232RL_liaison_serie.md)). Un FT232 qui ne sait pas inverser ses lignes, comme un clone dont l'EEPROM refuse le réglage, a donc besoin d'un inverseur sur TX et sur RX. Deux des six portes d'un 74HC04 suffisent, une par sens.

---

## 1. Brochage du 74HC04N

Boîtier DIP-14, vu de dessus, encoche en haut : la broche 1 est en haut à gauche.

```
        ┌───┬─┬───┐
   1A  1│   └─┘   │14  VCC (+5 V)
   1Y  2│         │13  6A
   2A  3│ 74HC04  │12  6Y
   2Y  4│         │11  5A
   3A  5│         │10  5Y
   3Y  6│         │9   4A
  GND  7│         │8   4Y
        └─────────┘
```

---

## 2. Câblage

| De | Vers |
|---|---|
| FT232 **+5 V** | broche **14** du 74HC04 (VCC) |
| FT232 **GND** | broche **7** du 74HC04, et GND du X-07 (**SP-2** ou **SP-8**) |
| FT232 **TXD** | broche **1** (1A) |
| broche **2** (1Y) | **SP-5** (RXD du X-07) |
| **SP-4** (TXD du X-07) | broche **3** (2A), **avec une résistance de 10 kΩ de la broche 3 vers GND** |
| broche **4** (2Y) | FT232 **RXD** |
| FT232 **+5 V** | **SP-6** (CTS du X-07), en direct, **sans passer par l'inverseur** |
| broches **5, 9, 11, 13** (entrées inutilisées) | **GND** |

```
 FT232 (VCCIO = 5 V)          74HC04                   Canon X-07 (CN9)

  +5V ──┬────────────────── 14 VCC
        │   100 nF
        ├──||── GND
        └─────────────────────────────────────────────  SP-6 CTS

  GND ──────────────────── 7 GND ─────────────────────  SP-8 GND

  TXD ──────────────────── 1 (1A)   2 (1Y) ───────────  SP-5 RXD

  RXD ──────────────────── 4 (2Y)   3 (2A) ──┬────────  SP-4 TXD
                                             └─[10 kΩ]── GND

                           5, 9, 11, 13 ── GND
                                              SP-1, SP-3, SP-7, SP-9 : NON CONNECTÉS
```

**Précautions :**
- **Condensateur de 100 nF** entre les broches 14 et 7, au plus près du circuit.
- **La résistance de 10 kΩ sur SP-4 reste indispensable** : la sortie du X-07 est « en l'air » au repos, et une entrée CMOS en l'air fait n'importe quoi.
- **Entrées inutilisées à la masse** (5, 9, 11, 13), pour la même raison.
- **Marge sur la réception :** à 5 V, le 74HC04 exige au moins 3,5 V pour voir un état haut, et la sortie du X-07 monte à environ 4,5 V. Ça devrait passer. Si la réception est capricieuse, prenez un **74HCT04**, de même brochage, qui se contente de 2 V.
- **La fiche du côté du X-07 :** la prise CN9 n'est pas normalisée. Elle accepte des broches rondes d'environ 1 mm, comme celles d'une fiche DB9 mâle. Les broches Dupont, trop fines, y font de faux contacts. Voir [X07_FT232RL_liaison_serie.md](X07_FT232RL_liaison_serie.md), §3, « La prise et sa fiche ».

---

## 3. D'où vient le +5 V de SP-6 (CTS) ?

**Du FT232.** Le X-07 n'a **pas de sortie +5 V** sur sa prise série.

- **SP-9 (VBB) ne convient pas :** c'est la tension brute des piles, environ 6 V, qui n'est pas faite pour alimenter quoi que ce soit. **Ne la branchez jamais.**
- **Brancher le +5 V du FT232 sur SP-6 est sans risque :** SP-6 est une entrée, protégée dans le X-07 par une résistance de 10 kΩ. Le FT232 n'y fournit qu'environ 0,4 mA, juste de quoi signaler au X-07 que le PC est prêt à recevoir. Sans ce fil, le X-07 n'émet rien.

**Toute l'alimentation du montage vient donc du FT232.** Son +5 V alimente le 74HC04 (broche 14) et CTS (SP-6). Sa masse est commune avec celle du X-07. Entre les deux appareils ne passent que la masse et les deux lignes de données, à travers l'inverseur.

---

## 4. Vérification

1. **Rattacher le câble à WSL** (dans PowerShell) : `usbipd attach --wsl --busid 1-3`.
2. **Le « R » du X-07 :** avec le récepteur en mémoire (`python3 x07asm.py recepteur`), tapez `RUN` sur le X-07 pendant qu'on écoute le port. Le PC doit recevoir **`52`**. Sans inversion, il recevait `2B 00`.
3. **Le transfert complet**, depuis le dossier `assembleur/` :
   ```sh
   python3 x07asm.py send exemples/bonjour.asm --port /dev/ttyUSB0
   ```
   Sur le X-07 : tapez le `CLEAR 50,&H…` affiché par le PC, puis `RUN`. Attendez `OK. EXEC &H…`, puis tapez `EXEC &H…`.
