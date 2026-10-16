# Canon X-07 : outils et documentation

Outils de développement et documentation pour le **Canon X-07**, ordinateur de poche de 1983. Il est équipé d'un processeur NSC800 (compatible Z80) et d'un BASIC Microsoft en ROM.

## Contenu

| Dossier | Contenu |
|---|---|
| [`assembleur/`](assembleur/) | **x07asm** : assembleur et désassembleur Z80, compilateur BASIC → Z80 (entiers, flottants BCD, chaînes), simulateur et émulateur du BASIC du X-07, en Python 3 sans dépendance |
| [`ref_docs/`](ref_docs/) | documentation : notes de référence en LaTeX/PDF tirées des livres, liaison série par FT232RL, documents d'origine numérisés |
| [`ROM_x07/`](ROM_x07/) | vidage de la ROM BASIC (`x07.bin`, à implanter en `$B000`) et jeu de caractères (`charset.rom`) |

**Pour commencer : le [guide de démarrage](DEMARRAGE.md)**, d'un programme BASIC jusqu'au X-07.

## x07asm en bref

```sh
cd assembleur
python3 x07asm.py asm exemples/caso.asm -f bin,lst,bas     # assembler
python3 x07asm.py dis ../ROM_x07/x07.bin --org B000 \
        --start C1BE --end C1F8 -l                         # désassembler la ROM
python3 x07asm.py basic exemples/premiers.bas              # compiler du BASIC
python3 x07asm.py run exemples/devine.bas                  # l'essayer sur PC
python3 x07asm.py emu exemples/devine.bas                  # le BASIC du X-07 (vraie ROM)
python3 x07asm.py emu --fenetre                            # le X-07 dans une fenêtre, au clavier
python3 x07asm.py send exemples/devine.bas --emu           # transfert série (ici émulé)
python3 -m unittest discover -s tests                      # tests
```

| Document | Sujet |
|---|---|
| [DEMARRAGE.md](DEMARRAGE.md) | guide de démarrage, de bout en bout |
| [assembleur/README.md](assembleur/README.md) | assembleur et désassembleur |
| [assembleur/COMPILATEUR.md](assembleur/COMPILATEUR.md) | compilateur BASIC : langage, types, vitesse |
| [assembleur/EMULATEUR.md](assembleur/EMULATEUR.md) | émulateur : la vraie ROM sur PC (`emu`, `run`), afficheur graphique 120 × 32 points |
| [assembleur/TRANSFERT.md](assembleur/TRANSFERT.md) | envoi au X-07 par le câble série (`send`) |
| [assembleur/ROM.md](assembleur/ROM.md) | carte des routines et variables de la ROM (109 sur 161 vérifiées) |
| [ref_docs/ERRATA.md](ref_docs/ERRATA.md) | **errata** des *Mystères du X-07* et des *Applications en assembleur* |

Les adresses de la ROM utilisées par les outils ont été vérifiées dans le vidage de la ROM. Tout a été essayé dans l'émulateur, **pas encore sur une machine réelle**.

## Documentation de référence

- *Les mystères du X-07* et *Applications en assembleur* (Éditions Neptune) : notes de référence (`X07_mysteres_reference.tex`, `X07_AppsASM.tex`) et originaux numérisés.
- *Canon X-07 Technical Guide / Parts Catalog* (`x07_technicalguide.pdf`).
- Raccordement du port série à un PC par un module FT232RL (`X07_FT232RL_liaison_serie.md`).

La ROM, les livres et le guide technique restent la propriété de leurs auteurs et éditeurs (Canon, Éditions Neptune). Ils sont fournis ici à des fins de conservation et d'étude de cette machine ancienne.
