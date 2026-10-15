# Canon X-07 : outils et documentation

Outils de développement et documentation pour le **Canon X-07**, ordinateur de poche de 1983. Il est équipé d'un processeur NSC800 (compatible Z80) et d'un BASIC Microsoft en ROM.

## Contenu

| Dossier | Contenu |
|---|---|
| [`assembleur/`](assembleur/) | **x07asm** : assembleur et désassembleur Z80, compilateur BASIC → Z80 et simulateur, en Python 3 sans dépendance |
| [`ref_docs/`](ref_docs/) | documentation : notes de référence en LaTeX/PDF tirées des livres, liaison série par FT232RL, documents d'origine numérisés |
| [`ROM_x07/`](ROM_x07/) | vidage de la ROM BASIC (`x07.bin`, à implanter en `$B000`) et jeu de caractères (`charset.rom`) |

## x07asm en bref

```sh
cd assembleur
python3 x07asm.py asm exemples/caso.asm -f bin,lst,bas     # assembler
python3 x07asm.py dis ../ROM_x07/x07.bin --org B000 \
        --start C1BE --end C1F8 -l                         # désassembler la ROM
python3 x07asm.py basic exemples/premiers.bas              # compiler du BASIC
python3 x07asm.py run exemples/devine.bas                  # l'essayer sur PC
python3 -m unittest discover -s tests                      # tests
```

- **Assembleur et désassembleur** : décrits dans [assembleur/README.md](assembleur/README.md).
- **Compilateur BASIC et simulateur** : décrits dans [assembleur/COMPILATEUR.md](assembleur/COMPILATEUR.md).
- Les adresses de la ROM utilisées par les outils ont été **vérifiées dans le vidage de la ROM**. Les erreurs relevées dans les livres sont signalées par des notes dans `ref_docs/*.tex`.

## Documentation de référence

- *Les mystères du X-07* et *Applications en assembleur* (Éditions Neptune) : notes de référence (`X07_mysteres_reference.tex`, `X07_AppsASM.tex`) et originaux numérisés.
- *Canon X-07 Technical Guide / Parts Catalog* (`x07_technicalguide.pdf`).
- Raccordement du port série à un PC par un module FT232RL (`X07_FT232RL_liaison_serie.md`).

La ROM, les livres et le guide technique restent la propriété de leurs auteurs et éditeurs (Canon, Éditions Neptune). Ils sont fournis ici à des fins de conservation et d'étude de cette machine ancienne.
