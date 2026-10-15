; Efface l'écran, affiche un message et attend une touche.
; Chargement : CLEAR 50,&H1BFF  puis  EXEC &H1C00
; Routines de la ROM d'après « Les mystères du X-07 » (non testé sur machine).

        ORG  $1C00

DEBUT:  CALL LCDCLS          ; CLS ($CE9E)
        LD   HL,MSG
        CALL PRTMSG          ; affiche (HL) jusqu'à 00 ($FEF7)
.ATT:   XOR  A
        CALL INKEY           ; Z=1 si aucune touche ($C90A)
        JR   Z,.ATT
        RET                  ; retour au BASIC

MSG:    DZ   "BONJOUR X-07 !"
