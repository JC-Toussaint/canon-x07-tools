; Sortie sur cassette (CASO) - « Applications en assembleur », p. 60
; Données précédées de trois 00 et suivies de trois FF.
        ORG  $1C00
        LD   DE,DEV_CASO     ; table CASO ($E796)
        LD   IY,FILE1        ; fichier #1 ($02C5)
        LD   A,0
        CALL DEVOPEN         ; INIT #1,"CASO:"
        IN   A,(P_MODE)
        SET  0,A             ; moteur en marche
        OUT  (P_MODE),A
        CALL TP              ; temporisation
        CALL TP
        LD   DE,FILE1
        CALL DEVSEL          ; assignation
        LD   A,0
        CALL DEVPUT          ; trois 00 de début
        LD   A,0
        CALL DEVPUT
        LD   A,0
        CALL DEVPUT
        LD   HL,DD           ; données
ST:     LD   A,(HL)
        CP   0               ; fin des données ?
        JR   Z,TE
        CALL DEVPUT          ; envoi de l'octet
        INC  HL
        JR   ST
TE:     LD   A,$FF           ; trois FF de fin
        CALL DEVPUT
        LD   A,$FF
        CALL DEVPUT
        LD   A,$FF
        CALL DEVPUT
        CALL TP
        IN   A,(P_MODE)
        RES  0,A             ; moteur arrêté
        OUT  (P_MODE),A
        RET
TP:     PUSH BC              ; temporisation
        LD   B,$7F
.E1:    LD   C,$FF
.E2:    DEC  C
        JR   NZ,.E2
        DEC  B
        JR   NZ,.E1
        POP  BC
        RET
DD:     DB   1,2,3,4,5,6,0   ; données, puis 0
