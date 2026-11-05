# Canon X-07 : test de bouclage du port série (SP-4 → SP-5)

Ce test vérifie l'électronique série du X-07 seul, sans PC. Le X-07 envoie des octets sur sa sortie TXD (SP-4), qui est reliée par un fil à son entrée RXD (SP-5), et il contrôle qu'ils reviennent intacts.

Le programme a été validé dans l'émulateur, qui fait tourner la vraie ROM, dans trois cas :

| Situation | Résultat affiché |
|---|---|
| avec le fil | les 256 octets reviennent, « BOUCLAGE OK » |
| sans fil | « RIEN RECU, OCTET 0 », au lieu d'un blocage |
| un octet volontairement faussé | l'erreur est détectée et affichée (`41>40`, « 1 ERREUR(S) ») |

Il reste à l'essayer sur une machine réelle.

---

## 1. Câblage sur la prise SERIAL (CN9)

| De | Vers | Rôle |
|---|---|---|
| **SP-4** (TXD) | **SP-5** (RXD) | le bouclage, par un simple fil |
| **SP-6** (CTS) | **+5 V** | sans lui, le X-07 n'émet rien |
| GND de la source de +5 V | **SP-8** (GND) | masse commune |

- **Pas de résistance sur le fil SP-4 → SP-5.** L'entrée RXD du X-07 contient déjà sa propre résistance vers la masse, qui remet la ligne à 0 V quand la sortie TXD est inactive.
- **La logique inversée du X-07 ne compte pas ici.** Le X-07 émet et reçoit avec la même convention, donc le bouclage marche dans tous les cas.
- **Pour le +5 V de CTS,** la prise SERIAL n'en fournit pas. Le plus simple est de garder le module FT232R branché au PC et de n'en utiliser que **+5 V → SP-6** et **GND → SP-8**, en laissant ses TXD et RXD débranchés.
- ⚠️ **Ne branchez jamais SP-9** : c'est la tension brute des piles.

Le brochage complet de CN9 est dans [X07_FT232RL_liaison_serie.md](X07_FT232RL_liaison_serie.md).

---

## 2. Le programme BASIC

```basic
10 REM TEST BOUCLAGE SP4-SP5
20 DEFINT D,E,I,R,T:CLS
30 INIT#1,"COM:",4800,"B":E=0
40 FOR I=0 TO 255:D=0:IF I=0 THEN D=255
50 OUT#1,I:T=0
60 R=SNS(#1,D):T=T+1
70 IF R<>D THEN 100
80 IF T<200 THEN 60
90 PRINT "RIEN RECU, OCTET";I:END
100 IF R<>I THEN E=E+1:PRINT HEX$(I);">";HEX$(R);" ";
110 LOCATE 0,3:PRINT I;
120 NEXT
130 CLS:IF E=0 THEN PRINT "BOUCLAGE OK":END
140 PRINT E;"ERREUR(S)"
```

### Comment il marche

- Le programme envoie les 256 valeurs d'octet une à une (`OUT#1`) et relit chacune au retour.
- `SNS(#1,D)` lit le port **sans attendre** : si rien n'est arrivé, il renvoie D. On ne peut pas utiliser `INP(#1)`, qui attendrait sans fin en l'absence du fil.
- D vaut 0, sauf pour l'octet 0, où il vaut 255, pour qu'un octet nul reçu ne soit pas confondu avec « rien reçu ».
- Le compteur T limite l'attente de chaque octet (ligne 80).
- Le numéro affiché en bas de l'écran montre la progression.
- On peut remplacer 4800 par une autre vitesse (par exemple 1200) dans la ligne 30.

---

## 3. Lire le résultat

| Affichage | Signification |
|---|---|
| **BOUCLAGE OK** | l'émission (SP-4) et la réception (SP-5) du X-07 fonctionnent |
| **RIEN RECU, OCTET n** | vérifier le fil SP-4 → SP-5 et surtout CTS (SP-6) au +5 V : sans CTS, le X-07 n'émet pas du tout |
| des paires **`XX>YY`** (envoyé > reçu) | des bits sont perdus ou faussés, par exemple par un mauvais contact |

---

## 4. Ce que ce test ne vérifie pas

Il valide l'électronique du X-07 elle-même. Il ne vérifie ni la compatibilité des niveaux et de la polarité avec le PC, ni le câble vers le FT232R.

Une fois ce test réussi, l'étape suivante est le test d'écho entre le PC et le X-07, avec `test_echo_x07.py` (à la racine du projet). Le PC envoie des octets, le X-07 les renvoie, et le script vérifie chaque écho.
