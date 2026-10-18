# Errata des livres de référence du Canon X-07

Ce document rassemble les erreurs relevées dans deux livres des Éditions Neptune :

- ***Les mystères du X-07*** (notes : [X07_mysteres_reference.tex](X07_mysteres_reference.tex)) ;
- ***Applications en assembleur*** (notes : [X07_AppsASM.tex](X07_AppsASM.tex)).

Chaque correction figure aussi, en détail, dans une note « N.d.R. » de ces documents.

Le **guide technique officiel de la carte XP-140** (Canon, `XP-140Guide.pdf`) a permis d'en trancher plusieurs ; ses propres coquilles sont relevées [à la fin](#guide-technique-xp-140-canon).

**Colonne « Vérifié par » :**
- **ROM** : lu dans le code de la ROM (`ROM_x07/x07.bin`) ;
- **émul.** : constaté en exécutant la vraie ROM dans l'émulateur (`x07asm.py emu`) ;
- **livre** : incohérence interne au livre, coquille ou erreur de recopie ;
- **guide** : confirmé par le guide technique XP-140 de Canon.

Rien n'a encore été vérifié sur une machine réelle.

## Les plus importantes

Ces erreurs changent le comportement d'un programme ou font planter la machine :

| Sujet | Le livre dit | En réalité |
|---|---|---|
| Curseur | `$B8` = X (colonne), `$B9` = Y | **`$B8` = ligne, `$B9` = colonne**, à partir de 1 |
| Type des variables | (sous-entendu : simple précision) | **double précision** par défaut |
| RST 18 | commande vers le T6834, en `$C937` | **signe de l'accumulateur**, en `$C9C7` |
| `RST 30`, entier | NC, Z, M | **C, NZ, M** |
| `$BBAB` | conversion formatée (PRINT USING) | **conversion libre (FOUT)** de `PRINT` et `STR$` |
| Routines « simple précision » `$CDA9`… | calcul en simple | **calcul en double**, arrondi seulement au rangement |
| `$E8E8` | Z = 1 si un indicateur est levé | **Z = 0** si BREAK, piles ou OFF |
| NMI, expérience 1 | routine sans sauvegarde | **AF doit être sauvegardé**, sinon le BASIC interrompu est faussé |

## *Les mystères du X-07*

| Page / § | Sujet | Erreur | Correction | Vérifié par |
|---|---|---|---|---|
| Table des mots-clés | Adresse de `FSET` (jeton `$B0`) | `BF36` | **`$BF56`** (table de répartition en `$F0D6` : `INIT`, `ERASE`… voisins concordent) | ROM |
| 69–74 | Port `$F6` en lecture | « T\*RDY : réception, R\*RDY : transmission » | RXRDY = réception prête (bit 1), TXRDY = émission prête (bit 0) | ROM |
| 74–86 | Commandes `$38`/`$39` du T6834 | « CLICK OFF déclenche, CLICK ON enclenche » | OFF = désactivé, ON = activé | livre |
| Routines, buzzer | `$C2DF` (bip) et `$C331` (haut-parleur) | « IY = tonalité, H = durée », sans plus | elles dépilent un mot de plus qu'elles n'empilent : **empiler une adresse de retour avant le `CALL`** (comme « Musique » des *Applications*) ; en `$C331`, **C = `$FF` donne le silence** | ROM |
| § 7.6.1 | Codes de `STICK` (touches curseur) | `$32` droite, `$36` bas | **`$33` droite, `$35` bas** ; `$32` et `$36` sont les diagonales haut-droite et bas-gauche (tableau 6 du guide) | guide |
| § 7.6.1 | Adresse de `RAM READ` / `RAM WRITE` (`$05`, `$06`) | octet haut, puis octet bas | **octet bas d'abord** ; `RAM WRITE` : donnée, octet bas, octet haut | ROM, guide |
| 74–86 | `STICK`, `STRIG` | non précisé | `STICK` : commande `$82`, réponse `AND $0F`. `STRIG(0)` = `$84` (espace), `STRIG(1)` = `$83` (F6) ; −1 si enfoncée | ROM |
| § 7.6.2 | RAM du T6834, touche F3 | `$C85A` | `$C854`, d'après le pas de `$2A` | livre |
| § 7.6.3 | Exemple d'utilisation du T6834 | `LD B,$2B` | `LD A,$2B` | livre |
| § 7.6.3 | Programme de démonstration | `CALL $C0C9`, `POP HL` | `CALL $C9C0`, `POP AF` (d'après le code hexadécimal) | livre |
| 90–95 | Table des vecteurs : RST 18 | `JP C9C7` (table) et `$C937` (§ 9.5.1) | `$C9C7`. Le rôle est faux : c'est le **signe de l'accumulateur** (A = 0, 1 ou `$FF`) | ROM |
| 90–95 | Curseur `$0B8`/`$0B9` | X / Y | **`$0B8` = ligne, `$0B9` = colonne**, comptées à partir de 1 | ROM, émul. |
| 90–95 | Types par défaut `$032A`–`$0343` | non précisé | `RUN` les met tous à 8 : **double précision** | ROM, émul. |
| 90–95 | BREAKFLAG `$002B` | bits 0, 1, 3, 6, 7 | Il faut ajouter le **bit 2 (pause)**. Le bit 6 n'est pas testé par `$C000` | ROM |
| 96–110 | `$BBAB` | conversion avec format (A, B, C) | **conversion libre (FOUT)** : elle ignore A, B et C et rend HL = texte terminé par 00 | ROM, émul. |
| 96–110 | `$CDA9`…`$CDC2` (simple précision) | calcul en simple | calcul **en double** (type 8). L'opérande gauche est en BC:DE. `CINT` tronque | ROM, émul. |
| 96–110 | RST 38 (`$E906`) | « calcul de l'adresse d'un élément de tableau » | suivi d'un **octet en ligne** n. Si n < `$80`, DE = mot en HL+n (lecture dans une table) ; sinon, appel de la fonction n du **pilote du périphérique courant** (`PRINT`, `TAB`, `INIT#`…) | ROM |
| 96–110 | `RST 30`, ligne de l'entier | NC, Z, M | **C, NZ, M** (A = −1) | émul. |
| 96–110 | `$C5A6` décrit deux fois | piles **ou** extinction | **extinction** (bit 7). Les messages de piles faibles sont en `$C06C` | ROM |
| 96–110 | `$C02D` | teste le bit 6 | teste le **bit 0** (BREAK), efface les bits 0 et 2 | ROM |
| 96–110 | `$E8E8` | Z = 1 si un bit est à 1 | `AND $83` : **Z = 0** si BREAK, piles ou OFF | ROM |
| 96–110 | `$EBF2` / `$EBFF` | HL = tampon − 1 | Le tampon se termine par 00, et **C = 1 si BREAK** pendant la saisie | ROM, émul. |
| 96–110 | `$C59B` | sauvegarde des piles en « 226h » | coquille probable | livre |
| 111–115 | X-720 : mémoire vidéo et ROM TV | « 800h–97FFh » ; ROM en « 4000h–B000h » | `$8000`–`$97FF` ; ROM TV en `$A000`–`$AFFF` | livre |
| 119–120 | Motif 8 × 8 | renvoi au « § 7.7 » | § 7.6.2. Pour relancer la routine, remettre `$00,$E0` en `$1B23` | livre |
| 123–124 | Inversion de l'écran LCD | `FOR … TO &H1C1B` | jusqu'à `&H1C1C` : sinon le dernier octet n'est pas chargé et le `JR` final saute n'importe où | livre |
| 125–126 | Affichage d'un titre | 44 octets | 45 octets, jusqu'à `$1C2C` | livre |
| 127–128 | Copyright personnel | 29 octets, `$200A`–`$2026` | 30 octets, jusqu'à `$2027` | livre |
| 131–132 | Bruitages | « ports du NSC800 », « 8 octets dans F2 » | ports du **HD61L202F** ; 8 **bits** dans F2, 4 dans F3 | livre |
| 133–134 | Redéfinition d'une touche | routine d'origine en `$CEB1` ; 32 octets | `$C1BE`, adresse du saut en `$009F` ; 33 octets | livre |

## *Applications en assembleur*

| Page | Sujet | Erreur | Correction | Vérifié par |
|---|---|---|---|---|
| 19 | Code dans un tableau, `EX(6)` | −20234 | **−20243** (`$B0ED`, `LDIR`) | livre |
| 19–21 | Arguments par `IX` | `ARG(0)=aa00` donne `(IX+0)=aa` | `(IX+0)=00`, `(IX+1)=aa` : poids faible d'abord | livre |
| 31–40 | Temporisation | `DEC B` | `DEC BC`, sinon la boucle ne s'arrête jamais | livre |
| 31–40 | Musique `$C2DF` | « IY = durée, HL = note » | IY = tonalité, H = durée (le code est juste, pas les commentaires) | ROM |
| 31–40 | `POINT` | commande `$13` | `POINT` = `$10`, avec `LD BC,$0201`, comme le fait la ROM (`$CE0E`). Selon les *Mystères*, `$13` est PEOR | ROM, livre |
| 31–40 | « Équivalent de `INPUT A%` » | `$F595` lit un entier | `$F595` lit un **numéro de ligne** : entier non signé seulement (`-56` donne 0, `40000` sans `OV`) | émul. |
| 41–45 | Messages en français | « ERREURE DE SYMTAXE », `$04` au lieu de `$44` | corrigé dans les DATA, sans changer les longueurs | livre, émul. |
| 47–51 | Ligne d'interruption B | « vient du sous-processeur » (§ 5.1.4) | INT B = série (`JP $C7A3`), INT A = T6834 (`JP $C799`) | ROM |
| 51–53 | NMI, expérience 1 | pas d'`EXEC` ; `RETI` | ajouter `EXEC &H1B00` ; terminer par `RETN` | livre |
| 51–53 | NMI, expérience 1 | A écrasé sans sauvegarde | encadrer par **`PUSH AF` / `POP AF`** : `102 DATA F5,3E,7,CD,BE,C1,F1,ED,45` | émul. |
| 60 | Sortie sur cassette | `LD DE,$E987` ; `LD B,$00` | `$E796` (table CASO) ; `LD B,$7F` | ROM, livre |
| 61 | Lecture sur cassette | octet parasite `$8F` dans les DATA | retiré : 82 octets (`FOR … +81`) | livre |
| 62 | Clavier vers imprimante | `CALL $F6A8` ; table GPR | `CALL $E6A8` ; les DATA visent LPT (`$E7F8`) | ROM |
| 66 | Réception série | `FOR … +29` ; `CD,DE,C1` | `+30` (charger le `RET`) ; `CD,BE,C1` (`CALL $C1BE`) | émul. |
| 80–82 | Utilitaire X-720 | `LD A,(&16-8+1)` | `LD A,9` (`3E,09`) | livre |
| 86–88 | LMDATA | ligne 55 annonce `10000+10J` | `10000+10(J−1)` | livre |
| 86–88 | LMDATA, gabarit | `10000 DATA ...,...` | **sans espace** : `10000 DATA...,...`, sinon tout est décalé d'un caractère | émul. |
| 89–90 | LOGOGÉNÈSE | ligne 107 à 3 mots ; « JICRO, MKsO » | sans conséquence ; « MICRO, MISO » probable | livre, émul. |
| 91–95 | Relogeur de LLIST | fin de table testée sur un seul octet | une adresse dont l'octet faible vaut `$00` arrête la relocation | livre |
| 96–100 | LABYRINTHE 3D | 20 points annoncés | le message du programme en indique 22 | livre |
| 114–116 | AUTONUM | `LD ($300),(HL)` ; « mémoire morte » | `LD ($300),HL` ; RAM. Le chargeur écrit de `F-215` à `F` | livre |

## Guide technique XP-140 (Canon)

Le guide officiel (*Canon XP-140 Monitor Card, guide technique*) est la source la plus sûre : il confirme les adresses de la ROM des livres et les codes du T6834. Il contient pourtant quelques coquilles.

| Page | Sujet | Erreur | Correction | Vérifié par |
|---|---|---|---|---|
| 33, 37 | `CHKBAT` et `OFFCHECK` | tous deux en `$C5A6` | `$C5A6` est **`OFFCHECK`** (teste le bit OFF) ; les messages de piles sont en `$C06C` | ROM |
| 38 | `TBREAK` (`$E8E8`) | « Z à 1 si un bit est à 1 » | **Z = 0** (NZ) si BREAK, piles ou OFF | ROM |
| 58 | Tableau 6 (`STICK`), bas seul | `$33` | **`$35`** (`$33` est droite) | guide |
| 58 | Tableau 6, haut et bas ensemble | `$35` | probablement `$30` : les autres flèches opposées s'annulent (gauche et droite donnent `$30`) ; l'émulateur répond 0 | — |
| 59 | `RAM READ`, `RAM WRITE` | « octets hauts et bas (dans cet ordre) » | **octet bas d'abord**, comme les exemples du guide (`05,06,C0` lit `$C006`) | ROM |
| 24 | `BEEP6` (`$C331`) | f = 19200 / (IY + 1) Hz ; t = HL / f | **f = 192 000 / IY Hz** ; **t = HL × IY / 384 000 s** (HL compte des demi-périodes) | ROM, manuel |
| 89, 90 | Hook ABORT | `$00A8` (p. 89), `ABTHOCK = $00AB` (p. 90) | **`$00A8`** ; `$00AB` est `ERRHOCK` | ROM |

Les noms officiels des routines (`KBDSNS`, `CMDPUT`, `LCDPUT`…) sont acceptés par l'assembleur, à côté de ceux des livres (voir [ROM.md](../assembleur/ROM.md)).

## Manuel de référence du BASIC (Canon)

| Page | Sujet | Erreur | Correction | Vérifié par |
|---|---|---|---|---|
| 34 | `BEEP`, notes 49 à 4095 | « 19200/⟨note⟩ en Hz » | **192 000 / ⟨note⟩ Hz**. Avec 19 200, `BEEP 1` ferait 26 Hz au lieu du do annoncé ; avec 192 000, la ROM donne 262 Hz pour `BEEP 1` et 440 Hz pour `BEEP 10` (la). La durée de 50 ms par unité confirme ce facteur | ROM |

## Vérifié et juste

La vérification a aussi confirmé, dans *Applications en assembleur*, ce qui suit :

- **Adresses de la ROM :** les 41 citées. Les astuces `$F30B`/`$FE8A` (édition de la ligne fautive) et `$C880` (AUTONUM) sont voulues.
- **Listings désassemblés :** les octets des 11 listings, réassemblés instruction par instruction.
- **Programmes qui fonctionnent comme décrit dans l'émulateur :**
  - exemples 1 à 4 du chapitre 1 ;
  - messages en français, `CARTE`, `RESTORE` calculé, logo CANON, LOGOGÉNÈSE ;
  - émission vers le Minitel (1200 bauds, mode G) et réception série ;
  - NMI, expérience 2 ;
  - entreur de codes, `ACQMES`.
- **Table des vecteurs d'interruption :** INT A, INT B, INT C, NMI.
