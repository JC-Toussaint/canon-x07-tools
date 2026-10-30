"""Coloration syntaxique de l'éditeur : découpe un programme BASIC X-07,
QuickBASIC ou assembleur en zones (mot-clé, fonction, chaîne, commentaire,
numéro de ligne ; en assembleur, instruction, directive, registre, étiquette).

zones(texte, sorte) rend des (catégorie, ligne, colonne de début, colonne de
fin) ; les lignes comptent depuis 1, les colonnes depuis 0, comme tkinter."""
import functools
import re

from . import asm, basic, pascal, qbasic, z80

CATEGORIES = ("motcle", "fonction", "chaine", "commentaire", "numero", "directive",
              "registre", "etiquette")

# BASIC X-07 : le découpage de la ROM, mots-clés reconnus même collés (FORI=1TO9)
BAS_FUNCS = set(basic.NUM_FUNCS) | set(basic.STR_FUNCS) | {
    "TAB", "SPC", "FRE", "ERL", "ERR", "INSTR", "VARPTR", "USR", "TKEY", "SNS"}

# QuickBASIC : des mots entiers, en majuscules ou non
QB_KEYWORDS = set(qbasic.STATEMENT_WORDS) | set(qbasic.OPERATOR_WORDS) | {"REM"}
QB_FUNCS = set(qbasic.FUNCTIONS) | {"UBOUND", "LBOUND"}
_QB_TOKEN = re.compile(r'"[^"]*"?|\'.*|[A-Za-z_][A-Za-z0-9_.]*[$%!#&]?|&[HhOo][0-9A-Fa-f]+'
                       r'|\d[\d.]*(?:[EeDd][+-]?\d+)?[%!#&]?|.')


def zones(text, kind):
    line_zones = {"bas": _bas_line, "qbas": _qb_line, "asm": _asm_line,
                  "pas": _pas_line}.get(kind)
    if line_zones is None:
        return []
    return [(c, n, a, b) for n, line in enumerate(text.split("\n"), 1)
            for c, a, b in line_zones(line)]


@functools.lru_cache(maxsize=4096)                 # à chaque frappe, une ligne change
def _bas_line(text):
    up, i, out = text.upper(), 0, []
    m = re.match(r"\s*(\d+)", text)                # numéro de ligne
    if m:
        out.append(("numero", m.start(1), m.end(1)))
        i = m.end()
    while i < len(text):
        c = text[i]
        if c == '"':
            j = text.find('"', i + 1)
            j = len(text) if j < 0 else j + 1
            out.append(("chaine", i, j))
            i = j
        elif c == "'":
            out.append(("commentaire", i, len(text)))
            break
        elif c == "&":                             # &H1F : pas de mot-clé dedans
            i += 1
            while i < len(text) and text[i].isalnum():
                i += 1
        elif c.isalpha():
            kw = basic._kw_at(up, i)
            if kw == "REM":
                out.append(("commentaire", i, len(text)))
                break
            if kw:
                word = kw.rstrip("(")
                out.append(("fonction" if word in BAS_FUNCS else "motcle", i, i + len(word)))
                i += len(kw)
                if kw == "DATA":                   # données jusqu'au « : »
                    q = False
                    while i < len(text) and (q or text[i] != ":"):
                        q ^= text[i] == '"'
                        i += 1
                continue
            i += 1                                 # nom de variable
            while i < len(text) and up[i].isalnum() and not (up[i].isalpha()
                                                             and basic._kw_at(up, i)):
                i += 1
        else:
            i += 1
    return tuple(out)


@functools.lru_cache(maxsize=4096)
def _qb_line(text):
    out, start = [], True                         # start : début d'instruction
    for m in _QB_TOKEN.finditer(text):
        tok, a, b = m.group(), m.start(), m.end()
        up = tok.upper()
        if tok[0] == '"':
            out.append(("chaine", a, b))
        elif tok[0] == "'" or (up == "REM" and start):
            out.append(("commentaire", a, len(text)))
            break
        elif up in QB_FUNCS:
            out.append(("fonction", a, b))
        elif up in QB_KEYWORDS:
            out.append(("motcle", a, b))
        elif tok.isdigit() and not text[:a].strip():   # numéro de ligne (ancien style)
            out.append(("numero", a, b))
        if not tok.isspace():
            start = tok == ":"
    return tuple(out)


# Pascal : mots-clés, fonctions et procédures standard, chaînes '...',
# commentaires { } et (* *) (sur une ligne ; ouvert, jusqu'au bout de la ligne)
PAS_KEYWORDS = set(pascal.KEYWORDS) | {"true", "false"}
PAS_FUNCS = {"write", "writeln", "read", "readln", "abs", "sqr", "sqrt", "sin", "cos", "arctan",
             "exp", "ln", "trunc", "round", "frac", "int", "odd", "ord", "chr", "succ", "pred",
             "length", "copy", "concat", "pos", "upcase", "insert", "delete", "str", "val",
             "inc", "dec", "random", "randomize", "pi", "keypressed", "readkey", "clrscr",
             "gotoxy", "wherex", "wherey", "delay", "sound", "nosound", "halt", "exit", "mem",
             "port", "plot", "draw", "circle", "beep", "integer", "real", "boolean", "char",
             "byte"}
_PAS_TOKEN = re.compile(r"\{[^}]*\}?|\(\*.*?(?:\*\)|$)|'(?:[^']|'')*'?|#\d+|\$[0-9A-Fa-f]+"
                        r"|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|.")


@functools.lru_cache(maxsize=4096)
def _pas_line(text):
    out = []
    for m in _PAS_TOKEN.finditer(text):
        tok, a, b = m.group(), m.start(), m.end()
        low = tok.lower()
        if tok[0] == "{" or tok.startswith("(*"):
            out.append(("commentaire", a, b))
        elif tok[0] in "'#":
            out.append(("chaine", a, b))
        elif low in PAS_KEYWORDS:
            out.append(("motcle", a, b))
        elif low in PAS_FUNCS:
            out.append(("fonction", a, b))
        elif tok[0].isdigit() or tok[0] == "$":
            out.append(("numero", a, b))
    return tuple(out)


# Assembleur : les règles de x07asm/asm.py (commentaire « ; » ou « * » en tête,
# étiquette en colonne 1 ou suivie de « : », AF', caractère 'x')
_ASM_TOKEN = re.compile(r'"[^"]*"?|[A-Za-z_.@?][\w.@?]*|\'[^\']*\'?|.')


def _asm_comment(text):
    """Position du « ; » qui commence le commentaire (hors chaînes), ou None."""
    i, q = 0, None
    while i < len(text):
        c = text[i]
        if q:
            q = None if c == q else q
        elif c == ";":
            return i
        elif c == '"':
            q = c
        elif c == "'":
            if text[max(0, i - 2):i].upper() == "AF" and not (i >= 3 and text[i - 3].isalnum()):
                pass                                # AF'
            elif i + 2 < len(text) and text[i + 2] == "'":
                i += 2                              # 'x'
            else:
                q = c
        i += 1
    return None


@functools.lru_cache(maxsize=4096)
def _asm_line(text):
    out = []
    if text.startswith("*"):
        return (("commentaire", 0, len(text)),)
    end = _asm_comment(text)
    code = text if end is None else text[:end]
    label, kw, _ = asm.parse_line(code)
    i = 0
    if label:
        i = code.index(label)
        out.append(("etiquette", i, i + len(label)))
        i += len(label)
    m = kw and re.compile(r"(?i)(?<![\w.@?])%s(?![\w.@?])" % re.escape(kw)).search(code, i)
    if m:                                           # absent pour « X = 3 »
        out.append(("motcle" if kw in z80.MNEMONICS else "directive", m.start(), m.end()))
        i = m.end()
    while i < len(code):
        m = _ASM_TOKEN.match(code, i)
        tok, a, i = m.group(), m.start(), m.end()
        up = tok.upper()
        if tok[0] in "\"'":
            out.append(("chaine", a, i))
        elif up in z80.REGISTERS:
            if up == "AF" and code[i:i + 1] == "'":
                i += 1
            out.append(("registre", a, i))
    if end is not None:
        out.append(("commentaire", end, len(text)))
    return tuple(out)
