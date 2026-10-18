"""Coloration syntaxique de l'éditeur : découpe un programme BASIC X-07 ou
QuickBASIC en zones (mot-clé, fonction, chaîne, commentaire, numéro de ligne).

zones(texte, sorte) rend des (catégorie, ligne, colonne de début, colonne de
fin) ; les lignes comptent depuis 1, les colonnes depuis 0, comme tkinter."""
import functools
import re

from . import basic, qbasic

CATEGORIES = ("motcle", "fonction", "chaine", "commentaire", "numero")

# BASIC X-07 : le découpage de la ROM, mots-clés reconnus même collés (FORI=1TO9)
BAS_FUNCS = set(basic.NUM_FUNCS) | set(basic.STR_FUNCS) | {
    "TAB", "SPC", "FRE", "ERL", "ERR", "INSTR", "VARPTR", "USR", "TKEY", "SNS"}

# QuickBASIC : des mots entiers, en majuscules ou non
QB_KEYWORDS = set(qbasic.STATEMENT_WORDS) | set(qbasic.OPERATOR_WORDS) | {"REM"}
QB_FUNCS = set(qbasic.FUNCTIONS)
_QB_TOKEN = re.compile(r'"[^"]*"?|\'.*|[A-Za-z_][A-Za-z0-9_.]*[$%!#&]?|&[HhOo][0-9A-Fa-f]+'
                       r'|\d[\d.]*(?:[EeDd][+-]?\d+)?[%!#&]?|.')


def zones(text, kind):
    line_zones = {"bas": _bas_line, "qbas": _qb_line}.get(kind)
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
