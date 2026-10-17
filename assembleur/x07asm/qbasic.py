"""Traduction d'un programme QuickBASIC en BASIC du Canon X-07 (étude).

Le programme QuickBASIC (sans numéros de ligne, blocs structurés, SUB et
FUNCTION, noms longs) devient un programme numéroté que la ROM du X-07
exécute ; le compilateur (basic.py) peut ensuite en faire de l'assembleur.

Ce que la traduction doit corriger (vérifié dans la ROM, voir QBASIC.md) :
  - 2 caractères significatifs dans les noms, mots-clés interdits dans un
    nom (TOTAL contient TO) : toutes les variables sont renommées ;
  - pas de bloc IF, DO/LOOP, WHILE/WEND, SELECT CASE, SUB, FUNCTION :
    ils deviennent des IF ... THEN n, GOTO et GOSUB ;
  - FOR exécute toujours une fois le corps : garde ajoutée ;
  - CINT et l'affectation à un entier tronquent : QuickBASIC arrondit ;
  - LOCATE, POS, CSRLIN, TAB comptent à partir de 0 ; pas de SPC, SWAP.
"""
import re

from .basic import KEYWORDS as X07_KEYWORDS


class QBError(Exception):
    pass


# ======================================================================
#  Analyse lexicale
# ======================================================================

STATEMENT_WORDS = """
AS BEEP CALL CASE CIRCLE CLS COLOR CONST DATA DECLARE DEF DEFDBL DEFINT DEFLNG
DEFSNG DEFSTR DIM DO ELSE ELSEIF END ERASE ERROR EXIT FOR FUNCTION GOSUB GOTO
IF INPUT IS KEY LET LINE LOCATE LOOP NEXT ON PRESET PRINT PSET RANDOMIZE READ
REDIM RESTORE RESUME RETURN SCREEN SELECT SHARED SLEEP SOUND STATIC STEP STOP
SUB SWAP SYSTEM THEN TO TYPE UNTIL USING WEND WHILE WIDTH POKE OUT BEEP OFF
INTEGER LONG SINGLE DOUBLE STRING VIEW WRITE OPEN CLOSE CHAIN COMMON DEFSEG SEG
""".split()
OPERATOR_WORDS = "NOT AND OR XOR EQV IMP MOD".split()
FUNCTIONS = {   # nom QuickBASIC : (types des arguments, type rendu)
    "ABS": ("n", "="), "SGN": ("n", "i"), "INT": ("n", "="), "FIX": ("n", "="),
    "CINT": ("n", "i"), "CSNG": ("n", "s"), "CDBL": ("n", "d"), "CLNG": ("n", "d"),
    "SQR": ("n", "s"), "LOG": ("n", "s"), "EXP": ("n", "s"), "SIN": ("n", "s"),
    "COS": ("n", "s"), "TAN": ("n", "s"), "ATN": ("n", "s"), "RND": ("n?", "s"),
    "PEEK": ("n", "i"), "INP": ("n", "i"), "LEN": ("$", "i"), "ASC": ("$", "i"),
    "VAL": ("$", "d"), "POINT": ("nn", "i"), "STICK": ("n", "i"), "STRIG": ("n", "i"),
    "CSRLIN": ("", "i"), "POS": ("n", "i"), "INSTR": ("n?$$", "i"),
    "CHR$": ("n", "$"), "STR$": ("n", "$"), "HEX$": ("n", "$"), "OCT$": ("n", "$"),
    "LEFT$": ("$n", "$"), "RIGHT$": ("$n", "$"), "MID$": ("$nn?", "$"),
    "STRING$": ("nx", "$"), "SPACE$": ("n", "$"), "INKEY$": ("", "$"),
    "TIME$": ("", "$"), "DATE$": ("", "$"), "TIMER": ("", "s"),
    "UCASE$": ("$", "$"), "LCASE$": ("$", "$"), "LTRIM$": ("$", "$"), "RTRIM$": ("$", "$"),
    "TAB": ("n", "$"), "SPC": ("n", "$"), "ERR": ("", "i"), "ERL": ("", "i"),
    "FRE": ("x", "d"),
}
NOT_ON_X07 = {   # fonctions sans équivalent direct
    "UCASE$": "pas de UCASE$ sur le X-07 (les lettres sont déjà en majuscules)",
    "LCASE$": "pas de LCASE$ sur le X-07",
    "LTRIM$": "pas de LTRIM$ sur le X-07 (MID$(STR$(x),2) pour un nombre positif)",
    "RTRIM$": "pas de RTRIM$ sur le X-07",
    "OCT$": "pas de OCT$ sur le X-07",
}
WORDS = set(STATEMENT_WORDS) | set(OPERATOR_WORDS) | set(FUNCTIONS)

_TOKEN = re.compile(r"""
    (?P<sp>[ \t]+)
  | (?P<str>"[^"]*"?)
  | (?P<num>&H[0-9A-F]+|&O[0-7]+|(?:\d+\.?\d*|\.\d+)(?:[ED][+-]?\d+)?[%!#&]?)
  | (?P<id>[A-Z][A-Z0-9_.]*[%!#$&]?)
  | (?P<op><>|<=|>=|=<|=>|[-+*/\\^=<>(),;:?#])
  | (?P<rem>')
""", re.X)


class Tok:
    __slots__ = ("kind", "val", "line")

    def __init__(self, kind, val, line):
        self.kind, self.val, self.line = kind, val, line

    def __repr__(self):
        return "%s:%s" % (self.kind, self.val)


def tokenize(text):
    toks = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        pos = 0
        up = line.upper()
        start = len(toks)
        while pos < len(line):
            m = _TOKEN.match(up, pos)
            if not m:
                raise QBError("ligne %d : caractère inattendu %r" % (n, line[pos]))
            kind = m.lastgroup
            val = m.group(kind)
            if kind == "rem":
                break
            if kind == "str":
                val = line[m.start() + 1:m.end()].rstrip('"')      # casse d'origine
            pos = m.end()
            if kind == "sp":
                continue
            if kind == "id":
                if val == "REM":
                    break
                if val in WORDS:
                    kind = "kw"
            if kind == "num" and val[0].isdigit() and len(toks) == start and \
                    val.isdigit():
                kind = "linenum"                     # numéro de ligne en tête
            toks.append(Tok(kind, val, n))
        if len(toks) > start and toks[start].kind == "id" and len(toks) > start + 1 \
                and toks[start + 1].val == ":" and toks[start + 1].kind == "op":
            toks[start].kind = "label"                # étiquette « nom: »
            del toks[start + 1]
        toks.append(Tok("eol", "", n))
    toks.append(Tok("eof", "", len(text.splitlines()) + 1))
    return toks


# ======================================================================
#  Analyse syntaxique
# ======================================================================
#  Expressions : ('num', texte, type) ('str', s) ('var', nom) ('idx', nom, [args])
#                ('call', fonction, [args]) ('un', op, e) ('bin', op, a, b)
#                ('ufn', nom, [args])  appel d'une FUNCTION
#                ('fn', nom, [args])   appel d'une DEF FN
#                ('raw', texte, type)  déjà traduit

PREC = {"IMP": 1, "EQV": 2, "XOR": 3, "OR": 4, "AND": 5, "NOT": 6,
        "=": 7, "<>": 7, "<": 7, ">": 7, "<=": 7, ">=": 7,
        "+": 8, "-": 8, "MOD": 9, "\\": 10, "*": 11, "/": 11, "NEG": 12, "^": 13}
REL = ("=", "<>", "<", ">", "<=", ">=")
NORM_REL = {"=<": "<=", "=>": ">=", "><": "<>"}


class Parser:
    def __init__(self, toks, functions):
        self.t, self.i = toks, 0
        self.functions = functions        # noms des FUNCTION (pour f(x) ≠ tableau)
        self.deffns = set()

    # -------------------------------------------------- outils
    @property
    def cur(self):
        return self.t[self.i]

    def peek(self, k=1):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def next(self):
        t = self.t[self.i]
        self.i += 1
        return t

    def err(self, msg, tok=None):
        tok = tok or self.cur
        raise QBError("ligne %d : %s" % (tok.line, msg))

    def is_op(self, v, tok=None):
        tok = tok or self.cur
        return tok.kind == "op" and NORM_REL.get(tok.val, tok.val) == v

    def is_kw(self, *vals, tok=None):
        tok = tok or self.cur
        return tok.kind == "kw" and tok.val in vals

    def accept_op(self, v):
        if self.is_op(v):
            self.next()
            return True
        return False

    def accept_kw(self, v):
        if self.is_kw(v):
            self.next()
            return True
        return False

    def expect_op(self, v):
        if not self.accept_op(v):
            self.err("« %s » attendu%s" % (v, self.near()))

    def expect_kw(self, v):
        if not self.accept_kw(v):
            self.err("%s attendu%s" % (v, self.near()))

    def near(self):
        c = self.cur
        return " (près de « %s »)" % c.val if c.kind not in ("eol", "eof") else " (fin de ligne)"

    def at_sep(self):
        return self.cur.kind in ("eol", "eof") or self.is_op(":") or self.is_kw("ELSE")

    def end_stmt(self):
        if not self.at_sep():
            self.err("fin d'instruction attendue%s" % self.near())

    # -------------------------------------------------- expressions
    def expr(self, level=1):
        if level > 13:
            return self.primary()
        if level == 6:                                    # NOT
            if self.accept_kw("NOT"):
                return ("un", "NOT", self.expr(6))
            return self.expr(7)
        if level == 12:                                   # moins unaire
            if self.accept_op("-"):
                return ("un", "-", self.expr(12))
            if self.accept_op("+"):
                return self.expr(12)
            return self.expr(13)
        left = self.expr(level + 1)
        while True:
            c = self.cur
            op = None
            if c.kind == "op" and PREC.get(NORM_REL.get(c.val, c.val)) == level:
                op = NORM_REL.get(c.val, c.val)
            elif c.kind == "kw" and PREC.get(c.val) == level and c.val != "NOT":
                op = c.val
            if op is None:
                return left
            self.next()
            if level == 13:                               # ^ : -2^2 = -4, 2^-1 permis
                right = self.expr(12)
            else:
                right = self.expr(level + 1)
            left = ("bin", op, left, right)

    def args(self):
        out = []
        self.expect_op("(")
        if not self.is_op(")"):
            while True:
                out.append(self.expr())
                if not self.accept_op(","):
                    break
        self.expect_op(")")
        return out

    def primary(self):
        t = self.cur
        if t.kind == "num":
            self.next()
            return num_literal(t.val)
        if t.kind == "str":
            self.next()
            return ("str", t.val)
        if self.accept_op("("):
            e = self.expr()
            self.expect_op(")")
            return ("paren", e)
        if t.kind == "kw" and t.val in FUNCTIONS:
            self.next()
            if self.is_op("("):
                return ("call", t.val, self.args())
            if FUNCTIONS[t.val][0] in ("", "n?", "x"):
                return ("call", t.val, [])
            self.err("« ( » attendu après %s" % t.val, t)
        if t.kind == "id":
            self.next()
            name = t.val
            if name.startswith("FN") and name in self.deffns:
                return ("fn", name, self.args() if self.is_op("(") else [])
            if base(name) in self.functions:
                return ("ufn", base(name), self.args() if self.is_op("(") else [])
            if self.is_op("("):
                return ("idx", name, self.args())
            return ("var", name)
        self.err("expression attendue%s" % self.near())

    # -------------------------------------------------- instructions
    def program(self):
        """Renvoie (instructions du module, procédures)."""
        main, procs = [], []
        while self.cur.kind != "eof":
            if self.is_kw("SUB", "FUNCTION") or (self.is_kw("STATIC") and
                                                 self.is_kw("SUB", "FUNCTION", tok=self.peek())):
                procs.append(self.procedure())
                continue
            if self.is_kw("DECLARE"):
                while self.cur.kind not in ("eol", "eof"):
                    self.next()
                continue
            main += self.line_stmts(("eof",))
        return main, procs

    def line_stmts(self, stop):
        """Une ligne : étiquettes, puis instructions séparées par « : »."""
        out = []
        while self.cur.kind in ("label", "linenum"):
            out.append(("label", self.next().val))
        while True:
            if self.cur.kind in ("eol", "eof"):
                if self.cur.kind == "eol":
                    self.next()
                return out
            if self.accept_op(":"):
                continue
            s = self.statement()
            if s is not None:
                out.append(s)
            if not (self.cur.kind in ("eol", "eof") or self.is_op(":")):
                self.err("fin d'instruction attendue%s" % self.near())

    def block(self, enders):
        """Instructions jusqu'à l'un des mots de fin (non consommé)."""
        out = []
        while True:
            if self.cur.kind == "eof":
                self.err("fin de fichier : %s attendu" % " / ".join(" ".join(e) for e in enders))
            # une ligne peut commencer par le mot de fin
            save = self.i
            while self.cur.kind in ("label", "linenum"):
                out.append(("label", self.next().val))
            for e in enders:
                if all(self.is_kw(w, tok=self.peek(k)) for k, w in enumerate(e)):
                    return out, e
            self.i = save
            out += self.block_line(enders)

    def block_line(self, enders):
        out = []
        while self.cur.kind in ("label", "linenum"):
            out.append(("label", self.next().val))
        while True:
            if self.cur.kind in ("eol", "eof"):
                if self.cur.kind == "eol":
                    self.next()
                return out
            if self.accept_op(":"):
                continue
            for e in enders:
                if all(self.is_kw(w, tok=self.peek(k)) for k, w in enumerate(e)):
                    return out
            s = self.statement()
            if s is not None:
                out.append(s)
            if not (self.cur.kind in ("eol", "eof") or self.is_op(":")):
                self.err("fin d'instruction attendue%s" % self.near())

    def skip_eol(self):
        if self.cur.kind == "eol":
            self.next()

    def procedure(self):
        static = self.accept_kw("STATIC")
        kind = self.next().val                         # SUB / FUNCTION
        t = self.next()
        if t.kind not in ("id", "kw"):
            self.err("nom de procédure attendu", t)
        name = t.val
        params = []
        if self.accept_op("("):
            if not self.is_op(")"):
                while True:
                    p = self.next()
                    if p.kind != "id":
                        self.err("paramètre attendu", p)
                    is_arr = False
                    if self.accept_op("("):
                        self.expect_op(")")
                        is_arr = True
                    typ = self.as_type()
                    params.append((p.val, is_arr, typ))
                    if not self.accept_op(","):
                        break
            self.expect_op(")")
        static = self.accept_kw("STATIC") or static
        self.skip_eol()
        body, _ = self.block([("END", kind)])
        self.next()
        self.next()
        return {"kind": kind, "name": name, "params": params, "body": body,
                "static": static}

    def as_type(self):
        if self.accept_kw("AS"):
            t = self.next()
            types = {"INTEGER": "i", "SINGLE": "s", "DOUBLE": "d", "STRING": "$", "LONG": "l"}
            if t.val not in types:
                self.err("type %s non traduisible (TYPE ... END TYPE : pas sur le X-07)" % t.val, t)
            if t.val == "STRING" and self.accept_op("*"):
                self.next()                           # longueur fixe : ignorée
            return types[t.val]
        return None

    def statement(self):
        t = self.cur
        if t.kind == "id":
            if base(t.val) in self.functions and self.is_op("=", self.peek()):
                self.next()
                self.next()
                return ("let", ("var", t.val), self.expr())
            if self.is_op("(", self.peek()) and self.call_like_sub(t):
                # « Sub (x) » sans CALL : (x) est une expression, passée par valeur
                return self.sub_call(self.next().val, paren=False)
            if self.is_op("=", self.peek()) or self.is_op("(", self.peek()):
                return self.let()
            return self.sub_call(self.next().val, paren=False)
        if t.kind == "op" and t.val == "?":
            self.next()
            return self.st_print()
        if t.kind != "kw":
            self.err("instruction attendue%s" % self.near())
        k = self.next().val
        m = getattr(self, "st_" + k.replace("$", "S"), None)
        if m is None:
            self.err("instruction %s non traduite" % k, t)
        return m()

    def call_like_sub(self, t):
        return getattr(self, "subs", None) and base(t.val) in self.subs

    def let(self):
        tgt = self.target()
        self.expect_op("=")
        return ("let", tgt, self.expr())

    def target(self):
        t = self.next()
        if t.kind != "id":
            self.err("variable attendue", t)
        if self.is_op("("):
            return ("idx", t.val, self.args())
        return ("var", t.val)

    def st_LET(self):
        return self.let()

    def sub_call(self, name, paren):
        args = []
        if paren:
            args = self.args()
        elif not self.at_sep():
            while True:
                args.append(self.expr())
                if not self.accept_op(","):
                    break
        return ("callsub", base(name), args)

    def st_CALL(self):
        t = self.next()
        return self.sub_call(t.val, paren=self.is_op("("))

    def st_PRINT(self):
        if self.accept_kw("USING"):
            fmt = self.expr()
            self.expect_op(";")
            items = self.print_items()
            return ("using", fmt, items)
        return ("print", self.print_items())

    def print_items(self):
        items = []
        while not self.at_sep():
            if self.accept_op(";"):
                items.append(";")
            elif self.accept_op(","):
                items.append(",")
            else:
                items.append(self.expr())
        return items

    def st_INPUT(self):
        self.accept_op(";")
        prompt, comma = None, False
        if self.cur.kind == "str":
            prompt = self.next().val
            if self.accept_op(","):
                comma = True
            else:
                self.expect_op(";")
        tg = [self.target()]
        while self.accept_op(","):
            tg.append(self.target())
        return ("input", prompt, comma, tg)

    def st_LINE(self):
        if self.accept_kw("INPUT"):
            self.accept_op(";")
            prompt = None
            if self.cur.kind == "str":
                prompt = self.next().val
                if not self.accept_op(";"):
                    self.expect_op(",")
            return ("lineinput", prompt, self.target())
        if self.is_op("-"):
            self.err("LINE -(x,y) (depuis le dernier point) non traduit")
        a = self.point()
        self.expect_op("-")
        b = self.point()
        color, box = None, None
        if self.accept_op(","):
            if not self.is_op(","):
                color = self.expr()
            if self.accept_op(","):
                w = self.next()
                if w.val not in ("B", "BF"):
                    self.err("B ou BF attendu", w)
                box = w.val
        return ("line", a, b, color, box)

    def point(self):
        self.expect_op("(")
        x = self.expr()
        self.expect_op(",")
        y = self.expr()
        self.expect_op(")")
        return x, y

    def st_PSET(self):
        p = self.point()
        c = self.expr() if self.accept_op(",") else None
        return ("pset", p, c, "PSET")

    def st_PRESET(self):
        p = self.point()
        if self.accept_op(","):
            self.expr()
        return ("pset", p, None, "PRESET")

    def st_CIRCLE(self):
        p = self.point()
        self.expect_op(",")
        r = self.expr()
        while self.accept_op(","):                     # couleur, arcs, aspect : ignorés
            if not self.at_sep() and not self.is_op(","):
                self.expr()
        return ("circle", p, r)

    def st_IF(self):
        cond = self.expr()
        if self.accept_kw("GOTO"):
            return ("if", [(cond, [("goto", self.label_ref())])], None)
        self.expect_kw("THEN")
        if self.cur.kind == "eol":                      # bloc IF
            self.next()
            arms, other = [], None
            body, end = self.block([("ELSEIF",), ("ELSE",), ("END", "IF")])
            arms.append((cond, body))
            while True:
                if end == ("ELSEIF",):
                    self.next()
                    c = self.expr()
                    self.expect_kw("THEN")
                    self.skip_eol()
                    body, end = self.block([("ELSEIF",), ("ELSE",), ("END", "IF")])
                    arms.append((c, body))
                elif end == ("ELSE",):
                    self.next()
                    self.skip_eol()
                    other, end = self.block([("END", "IF")])
                else:
                    self.next()
                    self.next()
                    return ("if", arms, other)
        then = self.inline_part()                       # IF sur une ligne
        other = None
        if self.accept_kw("ELSE"):
            other = self.inline_part()
        return ("if", [(cond, then)], other)

    def inline_part(self):
        if self.cur.kind in ("num", "linenum") or (self.cur.kind == "id" and False):
            return [("goto", self.label_ref())]
        out = []
        while not (self.cur.kind in ("eol", "eof") or self.is_kw("ELSE")):
            if self.accept_op(":"):
                continue
            s = self.statement()
            if s is not None:
                out.append(s)
        return out

    def label_ref(self):
        t = self.next()
        if t.kind in ("num", "linenum", "id", "label"):
            return t.val
        self.err("étiquette attendue", t)

    def st_GOTO(self):
        return ("goto", self.label_ref())

    def st_GOSUB(self):
        return ("gosub", self.label_ref())

    def st_RETURN(self):
        if not self.at_sep():
            self.err("RETURN étiquette non traduit")
        return ("return",)

    def st_ON(self):
        if self.accept_kw("ERROR"):
            self.expect_kw("GOTO")
            return ("onerror", self.label_ref())
        e = self.expr()
        w = self.next().val
        if w not in ("GOTO", "GOSUB"):
            self.err("GOTO ou GOSUB attendu après ON")
        labels = [self.label_ref()]
        while self.accept_op(","):
            labels.append(self.label_ref())
        return ("on", e, w, labels)

    def st_RESUME(self):
        if self.at_sep():
            return ("raw", "RESUME")
        if self.accept_kw("NEXT"):
            return ("raw", "RESUME NEXT")
        return ("resume", self.label_ref())

    def st_ERROR(self):
        return ("rawe", "ERROR ", self.expr())

    def st_END(self):
        if self.is_kw("IF", "SELECT", "SUB", "FUNCTION", "TYPE"):
            self.err("END %s sans début de bloc" % self.cur.val)
        return ("end",)

    st_SYSTEM = st_END

    def st_STOP(self):
        return ("raw", "STOP")

    def st_FOR(self):
        v = self.next()
        if v.kind != "id":
            self.err("variable de boucle attendue", v)
        self.expect_op("=")
        a = self.expr()
        self.expect_kw("TO")
        b = self.expr()
        step = self.expr() if self.accept_kw("STEP") else None
        self.end_stmt()
        body, _ = self.block([("NEXT",)])
        self.next()
        names = []
        while self.cur.kind == "id":
            names.append(self.next().val)
            if not self.accept_op(","):
                break
        if names and base(names[0]) != base(v.val):
            self.err("NEXT %s ne ferme pas FOR %s" % (names[0], v.val))
        if len(names) > 1:
            self.err("NEXT avec plusieurs variables : écrivez un NEXT par boucle")
        return ("for", v.val, a, b, step, body)

    def st_DO(self):
        pre = None
        if self.is_kw("WHILE", "UNTIL"):
            pre = (self.next().val, self.expr())
        self.end_stmt()
        body, _ = self.block([("LOOP",)])
        self.next()
        post = None
        if self.is_kw("WHILE", "UNTIL"):
            post = (self.next().val, self.expr())
        return ("do", pre, body, post)

    def st_WHILE(self):
        c = self.expr()
        self.end_stmt()
        body, _ = self.block([("WEND",)])
        self.next()
        return ("do", ("WHILE", c), body, None)

    def st_EXIT(self):
        w = self.next().val
        if w not in ("FOR", "DO", "SUB", "FUNCTION"):
            self.err("EXIT %s non traduit" % w)
        return ("exit", w)

    def st_SELECT(self):
        self.expect_kw("CASE")
        sel = self.expr()
        self.skip_eol()
        cases, other = [], None
        while True:
            while self.cur.kind == "eol":
                self.next()
            if self.is_kw("END") and self.is_kw("SELECT", tok=self.peek()):
                self.next()
                self.next()
                return ("select", sel, cases, other)
            self.expect_kw("CASE")
            if self.accept_kw("ELSE"):
                other, _ = self.block([("END", "SELECT")])
                continue
            tests = []
            while True:
                if self.accept_kw("IS"):
                    op = NORM_REL.get(self.cur.val, self.cur.val)
                    if op not in REL:
                        self.err("opérateur de comparaison attendu après IS")
                    self.next()
                    tests.append(("is", op, self.expr()))
                else:
                    a = self.expr()
                    if self.accept_kw("TO"):
                        tests.append(("range", a, self.expr()))
                    else:
                        tests.append(("is", "=", a))
                if not self.accept_op(","):
                    break
            body, _ = self.block([("CASE",), ("END", "SELECT")])
            cases.append((tests, body))

    def st_DIM(self):
        shared = self.accept_kw("SHARED")
        decls = []
        while True:
            t = self.next()
            if t.kind != "id":
                self.err("nom attendu dans DIM", t)
            dims = None
            if self.accept_op("("):
                dims = []
                while True:
                    lo = None
                    hi = self.expr()
                    if self.accept_kw("TO"):
                        lo, hi = hi, self.expr()
                    dims.append((lo, hi))
                    if not self.accept_op(","):
                        break
                self.expect_op(")")
            decls.append((t.val, dims, self.as_type()))
            if not self.accept_op(","):
                break
        return ("dim", shared, decls)

    st_REDIM = None

    def st_SHARED(self):
        names = []
        while True:
            t = self.next()
            is_arr = False
            if self.accept_op("("):
                self.expect_op(")")
                is_arr = True
            names.append((t.val, is_arr, self.as_type()))
            if not self.accept_op(","):
                break
        return ("shared", names)

    def st_STATIC(self):
        return ("static", self.st_SHARED()[1])

    def st_CONST(self):
        out = []
        while True:
            t = self.next()
            self.expect_op("=")
            out.append((t.val, self.expr()))
            if not self.accept_op(","):
                break
        return ("const", out)

    def _deftype(self, typ):
        ranges = []
        while True:
            a = self.next().val
            b = a
            if self.accept_op("-"):
                b = self.next().val
            ranges.append((a, b))
            if not self.accept_op(","):
                break
        return ("deftype", typ, ranges)

    def st_DEFINT(self):
        return self._deftype("i")

    def st_DEFSNG(self):
        return self._deftype("s")

    def st_DEFDBL(self):
        return self._deftype("d")

    def st_DEFSTR(self):
        return self._deftype("$")

    def st_DEFLNG(self):
        return self._deftype("l")

    def st_DEF(self):
        t = self.next()
        if t.kind == "kw" and t.val == "SEG":
            while not self.at_sep():
                self.next()
            return ("warn", "DEF SEG ignoré : la mémoire du X-07 n'a pas de segments")
        if not t.val.startswith("FN"):
            self.err("DEF FN attendu", t)
        name = t.val
        params = []
        if self.accept_op("("):
            while True:
                params.append(self.next().val)
                if not self.accept_op(","):
                    break
            self.expect_op(")")
        self.expect_op("=")
        self.deffns.add(name)
        return ("deffn", name, params, self.expr())

    def st_DATA(self):
        items = []
        cur = []
        while self.cur.kind not in ("eol", "eof"):
            t = self.next()
            if t.kind == "op" and t.val == ",":
                items.append("".join(cur))
                cur = []
            elif t.kind == "op" and t.val == ":":
                break
            elif t.kind == "str":
                cur.append('"%s"' % t.val)
            else:
                cur.append(t.val if t.kind != "num" else strip_num(t.val))
        items.append("".join(cur))
        return ("data", items)

    def st_READ(self):
        tg = [self.target()]
        while self.accept_op(","):
            tg.append(self.target())
        return ("read", tg)

    def st_RESTORE(self):
        return ("restore", None if self.at_sep() else self.label_ref())

    def st_CLS(self):
        if not self.at_sep():
            self.expr()
        return ("raw", "CLS")

    def st_LOCATE(self):
        row = None if self.is_op(",") else self.expr()
        col = None
        if self.accept_op(","):
            if not self.at_sep() and not self.is_op(","):
                col = self.expr()
            while self.accept_op(","):              # curseur visible, forme : ignorés
                if not self.at_sep() and not self.is_op(","):
                    self.expr()
        return ("locate", row, col)

    def st_BEEP(self):
        return ("raw", "BEEP")

    def st_SOUND(self):
        self.expr()
        self.expect_op(",")
        self.expr()
        return ("warnraw", "SOUND remplacé par BEEP (sons différents)", "BEEP")

    def st_SWAP(self):
        a = self.target()
        self.expect_op(",")
        return ("swap", a, self.target())

    def st_RANDOMIZE(self):
        if self.at_sep():
            return ("randomize", ("call", "TIMER", []))
        return ("randomize", self.expr())

    def st_SLEEP(self):
        if not self.at_sep():
            self.expr()
        return ("sleep",)

    def _ignored(self, what):
        while not self.at_sep():
            self.next()
        return ("warn", "%s ignoré : sans objet sur le X-07" % what)

    def st_SCREEN(self):
        return self._ignored("SCREEN")

    def st_COLOR(self):
        return self._ignored("COLOR")

    def st_WIDTH(self):
        return self._ignored("WIDTH")

    def st_VIEW(self):
        return self._ignored("VIEW")

    def st_KEY(self):
        return self._ignored("KEY")

    def st_POKE(self):
        a = self.expr()
        self.expect_op(",")
        return ("poke", "POKE", a, self.expr())

    def st_OUT(self):
        a = self.expr()
        self.expect_op(",")
        return ("poke", "OUT", a, self.expr())

    def st_ERASE(self):
        names = [self.next().val]
        while self.accept_op(","):
            names.append(self.next().val)
        return ("erase", names)

    def st_TYPE(self):
        self.err("TYPE ... END TYPE non traduit : le X-07 n'a pas d'enregistrements "
                 "(utilisez des tableaux parallèles)")

    def st_OPEN(self):
        self.err("fichiers (OPEN) non traduits")

    def st_WRITE(self):
        self.err("WRITE non traduit : utilisez PRINT")


def base(name):
    return name.rstrip("%!#$&")


def strip_num(text):
    if text.startswith("&"):
        return text
    return text.rstrip("%!&")


def num_literal(text):
    if text.startswith("&H") or text.startswith("&O"):
        v = int(text[2:], 16 if text[1] == "H" else 8)
        return ("num", text, "i" if v <= 0xFFFF else "d")
    t = text.rstrip("%!#&")
    suffix = text[len(t):]
    if suffix == "#" or "D" in t:
        typ = "d"
    elif suffix == "%":
        typ = "i"
    elif suffix == "&":
        typ = "d"
    elif "." in t or "E" in t:
        typ = "s"
    else:
        typ = "i" if int(t) <= 32767 else ("d" if len(t) > 7 else "s")
    return ("num", t + ("#" if suffix == "#" else ""), typ)


# ======================================================================
#  Noms du X-07
# ======================================================================

_BAD2 = {k for k in X07_KEYWORDS if len(k.rstrip("$(")) <= 2}


def valid_x07_name(n):
    if n.startswith("FN") or n in _BAD2:
        return False
    return not any(len(k) >= 2 and k in n for k in X07_KEYWORDS)


class Names:
    """Attribue des noms de 1 ou 2 caractères, uniques, sans mot-clé."""

    def __init__(self):
        self.used = set()

    def new(self, hint=""):
        hint = re.sub(r"[^A-Z0-9]", "", hint.upper())
        cands = []
        if hint and hint[0].isalpha():
            cands.append(hint[0])
            cands += [hint[0] + c for c in hint[1:]]
            cands += [hint[0] + d for d in "0123456789"]
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        cands += list(letters)
        cands += [a + b for a in letters for b in "0123456789" + letters]
        for c in cands:
            if c not in self.used and valid_x07_name(c):
                self.used.add(c)
                return c
        raise QBError("trop de variables pour le X-07")


SUFFIX = {"i": "%", "s": "", "d": "#", "$": "$"}


# ======================================================================
#  Traduction
# ======================================================================

class Scope:
    def __init__(self, parent=None, proc=None):
        self.parent, self.proc = parent, proc
        self.vars = {}         # (nom de base, type, tableau ?) -> nom X-07
        self.declared = {}     # nom de base -> type (DIM ... AS)
        self.shared = set()    # noms de base partagés avec le module
        self.alias = {}        # paramètre tableau -> tableau réel
        self.statics = set()   # STATIC : gardées d'un appel à l'autre


class Translator:
    def __init__(self, text, line_len=72):
        self.line_len = line_len
        self.warnings = []
        self.names = Names()
        self.labels = {}       # étiquette QuickBASIC -> étiquette interne
        self.n_label = 0
        self.items = []        # ('label', id) | ('stmt', texte, fin_de_ligne)
        self.deftype = {c: "s" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
        self.consts = {}
        self.deffn_names = {}
        toks = tokenize(text)
        funcs, subs = set(), set()
        for k, t in enumerate(toks[:-1]):
            if t.kind == "kw" and t.val in ("FUNCTION", "SUB") and toks[k + 1].kind in ("id", "kw"):
                prev = toks[k - 1] if k else None
                if prev is None or prev.kind == "eol" or prev.val in ("DECLARE", "STATIC"):
                    (funcs if t.val == "FUNCTION" else subs).add(base(toks[k + 1].val))
        self.parser = Parser(toks, funcs)
        self.parser.subs = subs
        self.main, procs = self.parser.program()
        self.procs = {p["name"] if p["kind"] == "SUB" else base(p["name"]): p for p in procs}
        self.global_scope = Scope()
        self.scope = self.global_scope
        self.check_recursion()

    # -------------------------------------------------- étiquettes, sortie
    def new_label(self):
        self.n_label += 1
        return "G%d" % self.n_label

    def user_label(self, name):
        key = "U" + name
        if key not in self.labels:
            self.labels[key] = self.new_label()
        return self.labels[key]

    def place(self, lab):
        self.items.append(("label", lab))

    def emit(self, text, ends_line=False):
        self.items.append(("stmt", text, ends_line))

    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    # -------------------------------------------------- variables
    def type_of(self, name, scope=None):
        scope = scope or self.scope
        if name[-1] in "%!#$&":
            t = {"%": "i", "!": "s", "#": "d", "$": "$", "&": "l"}[name[-1]]
        else:
            t = scope.declared.get(name)
            if t is None and scope is not self.global_scope and \
                    (name in scope.shared or name in self.global_shared):
                t = self.global_scope.declared.get(name)
            if t is None:
                t = self.deftype[name[0]]
        if t == "l":
            self.warn("LONG remplacé par la double précision (pas d'entiers 32 bits sur le X-07)")
            t = "d"
        return t

    def xvar(self, name, is_arr=False):
        """Nom X-07 (avec suffixe) de la variable QuickBASIC name."""
        b = base(name)
        t = self.type_of(name if name[-1] in "%!#$&" else b)
        s = self.scope
        if is_arr and b in s.alias:
            return s.alias[b]
        if s is not self.global_scope and (b in s.shared or b in self.global_shared):
            s = self.global_scope
        key = (b, t, is_arr)
        if key not in s.vars:
            s.vars[key] = self.names.new(b) + SUFFIX[t]
            self.name_map.append(("%s%s%s" % (
                "%s." % s.proc if s.proc else "", b, "()" if is_arr else ""), s.vars[key]))
        return s.vars[key]

    def temp(self, t):
        n = self.names.new("") + SUFFIX[t]
        return n

    # -------------------------------------------------- expressions
    def etype(self, e):
        k = e[0]
        if k == "num":
            return e[2]
        if k in ("str",):
            return "$"
        if k == "raw":
            return e[2]
        if k == "paren":
            return self.etype(e[1])
        if k == "var":
            if base(e[1]) in self.consts:
                return self.etype(self.consts[base(e[1])])
            return self.type_of(e[1])
        if k == "idx":
            return self.type_of(e[1])
        if k == "ufn":
            return self.type_of(self.procs[e[1]]["name"])
        if k == "fn":
            return self.type_of(e[1])
        if k == "call":
            r = FUNCTIONS[e[1]][1]
            if r == "=":
                return self.etype(e[2][0])
            return r
        if k == "un":
            if e[1] == "NOT":
                return "i"
            return self.etype(e[2])
        if k == "bin":
            op = e[1]
            a, b = self.etype(e[2]), self.etype(e[3])
            if op in REL or op in ("AND", "OR", "XOR", "EQV", "IMP", "\\", "MOD"):
                return "i"
            if a == "$":
                return "$"
            if op in ("/", "^"):
                return "d" if "d" in (a, b) else "s"
            order = "isd"
            return order[max(order.index(a), order.index(b))]
        raise QBError("expression inconnue %r" % (e,))

    def x(self, e, prec=0):
        """Texte X-07 de l'expression (déjà débarrassée des appels de FUNCTION)."""
        k = e[0]
        if k == "num":
            return e[1]
        if k == "str":
            return '"%s"' % e[1]
        if k == "raw":
            return e[1]
        if k == "paren":
            return self.x(e[1], prec)
        if k == "var":
            b = base(e[1])
            if b in self.consts:
                return self.x(("paren", self.consts[b]) if self.consts[b][0] in ("bin", "un")
                              else self.consts[b], prec)
            return self.xvar(e[1])
        if k == "idx":
            return "%s(%s)" % (self.xvar(e[1], True), ",".join(self.x(a) for a in e[2]))
        if k == "fn":
            fn = self.deffn_names[e[1]]
            return fn + ("(%s)" % ",".join(self.x(a) for a in e[2]) if e[2] else "")
        if k == "call":
            return self.x_call(e[1], e[2], prec)
        if k == "un":
            if e[1] == "NOT":
                s = "NOT " + self.x(e[2], PREC["NOT"])
                p = PREC["NOT"]
            else:
                s = "-" + self.x(e[2], PREC["NEG"] + 1)
                p = PREC["NEG"]
            return "(%s)" % s if p < prec else s
        if k == "bin":
            op = e[1]
            p = PREC[op]
            right_p = p + 1 if op != "^" else PREC["NEG"]
            sep = " %s " % op if op.isalpha() else op
            s = self.x(e[2], p) + sep + self.x(e[3], right_p)
            return "(%s)" % s if p < prec else s
        raise QBError("expression non traduite %r" % (e,))

    def x_call(self, f, args, prec):
        if f in NOT_ON_X07:
            raise QBError(NOT_ON_X07[f])
        a = [self.x(v) for v in args]
        if f == "SPACE$":
            return 'STRING$(%s," ")' % a[0]
        if f == "SPC":
            return 'STRING$(%s," ")' % a[0]
        if f == "TAB":
            return "TAB(%s)" % self.x(("bin", "-", args[0], ("num", "1", "i")))
        if f == "CINT":                                  # QuickBASIC arrondit
            return "INT(%s)" % self.x(("bin", "+", args[0], ("num", ".5", "s")))
        if f == "CLNG":
            return "INT(%s)" % self.x(("bin", "+", args[0], ("num", ".5", "s")))
        if f == "RND":
            if args and args[0][0] == "num" and args[0][1] == "0":
                self.warn("RND(0) : le X-07 tire un nouveau nombre")
            return "RND(%s)" % (a[0] if args else "1")
        if f == "POS":
            s = "POS(0)+1"
            return "(%s)" % s if prec > PREC["+"] else s
        if f == "CSRLIN":
            s = "CSRLIN+1"
            return "(%s)" % s if prec > PREC["+"] else s
        if f == "TIMER":
            s = ('VAL(LEFT$(TIME$,2))*3600+VAL(MID$(TIME$,4,2))*60+VAL(RIGHT$(TIME$,2))')
            return "(%s)" % s if prec > PREC["+"] else s
        if f in ("INKEY$", "TIME$", "DATE$", "ERR", "ERL"):
            if f == "ERL":
                self.warn("ERL rend un numéro de ligne du programme traduit")
            return f
        if f == "FRE":
            return "FRE(0)"
        if f == "INSTR":
            self.warn("INSTR : accepté par la ROM, pas encore par le compilateur")
        return "%s(%s)" % (f, ",".join(a))

    # -------------------------------------------------- appels de FUNCTION
    def hoist(self, e):
        """Exécute d'abord les appels de FUNCTION de e ; rend e sans appel."""
        if not isinstance(e, tuple):
            return e
        k = e[0]
        if k == "ufn":
            args = [self.hoist(a) for a in e[2]]
            proc = self.procs[e[1]]
            self.call_proc(proc, args, e[2])
            t = self.etype(e)
            tmp = self.temp(t)
            self.emit("%s=%s" % (tmp, self.result_var(proc)))
            return ("raw", tmp, t)
        if k in ("idx", "call", "fn"):
            return (k, e[1], [self.hoist(a) for a in e[2]])
        if k == "un":
            return ("un", e[1], self.hoist(e[2]))
        if k == "bin":
            return ("bin", e[1], self.hoist(e[2]), self.hoist(e[3]))
        if k == "paren":
            return ("paren", self.hoist(e[1]))
        return e

    def result_var(self, proc):
        return self.proc_info[proc["name"] if proc["kind"] == "SUB" else base(proc["name"])]["result"]

    def call_proc(self, proc, args, orig_args):
        key = proc["name"] if proc["kind"] == "SUB" else base(proc["name"])
        info = self.proc_info[key]
        if len(args) != len(proc["params"]):
            raise QBError("%s : %d paramètre(s) attendu(s), %d donné(s)" % (
                proc["name"], len(proc["params"]), len(args)))
        back, arrays = [], []
        for (pname, is_arr, _), a, orig in zip(proc["params"], args, orig_args):
            if is_arr:                                   # tableau : copie de la procédure
                if orig[0] == "idx" and not orig[2]:     # v() : tout le tableau
                    orig = ("var", orig[1])
                if orig[0] != "var":
                    raise QBError("%s : tableau attendu pour %s" % (proc["name"], pname))
                arrays.append(self.xvar(orig[1], True))
                continue
            px = info["params"][pname]
            self.emit("%s=%s" % (px, self.x(self.convert(a, px))))
            if orig[0] in ("var", "idx") and not (orig[0] == "var" and base(orig[1]) in self.consts):
                back.append((orig, px))
        self.emit("GOSUB @%s" % self.spec(key, tuple(arrays))[0])
        for orig, px in back:                            # passage par référence
            tgt = self.x(self.hoist(orig))
            if tgt != px:
                self.emit("%s=%s" % (tgt, px))

    def integral(self, e):
        """e est-il toujours un nombre entier (pas besoin d'arrondir) ?"""
        k = e[0]
        if k == "num":
            return not re.search(r"[.ED]", e[1].rstrip("#")) or e[1].startswith("&")
        if k == "paren":
            return self.integral(e[1])
        if k == "call":
            return e[1] in ("INT", "FIX", "CINT", "SGN", "LEN", "ASC", "PEEK", "INP",
                            "INSTR", "POINT", "POS", "CSRLIN")
        if k == "un":
            return self.integral(e[2]) or e[1] == "NOT"
        if k == "bin":
            if e[1] in ("+", "-", "*"):
                return self.integral(e[2]) and self.integral(e[3])
            return e[1] not in ("/", "^")
        return self.etype(e) == "i"

    def convert(self, e, target_name):
        """Arrondi de QuickBASIC quand un nombre non entier va dans un entier."""
        if target_name.endswith("%") and self.etype(e) in ("s", "d") and not self.integral(e):
            return ("call", "INT", [("bin", "+", e, ("num", ".5", "s"))])
        return e

    # -------------------------------------------------- procédures
    def check_recursion(self):
        graph = {}

        def calls(stmts, out):
            for s in stmts:
                walk(s, out)

        def walk(node, out):
            if isinstance(node, tuple):
                if node and node[0] == "callsub":
                    out.add(node[1])
                if node and node[0] == "ufn":
                    out.add(node[1])
                for c in node[1:]:
                    walk(c, out)
            elif isinstance(node, list):
                for c in node:
                    walk(c, out)
        for name, p in self.procs.items():
            out = set()
            calls(p["body"], out)
            graph[name] = out
        for start in graph:
            seen, todo = set(), list(graph[start])
            while todo:
                n = todo.pop()
                if n == start:
                    raise QBError("%s est récursive : le X-07 n'a pas de variables locales "
                                  "(la traduction exige un programme non récursif)" % start)
                if n in seen or n not in graph:
                    continue
                seen.add(n)
                todo += graph[n]

    def prepare_procs(self):
        self.proc_info = {}
        for key, p in self.procs.items():
            sc = Scope(self.global_scope, key)
            info = {"scope": sc, "params": {}, "result": None,
                    "specs": {},        # tableaux reçus -> (étiquette, sortie)
                    "dimflags": {}}     # tableaux locaux déjà créés
            self.scope = sc
            for pname, is_arr, typ in p["params"]:
                b = base(pname)
                if b in self.consts:
                    raise QBError("%s : le paramètre %s porte le nom d'une constante "
                                  "(QuickBASIC le refuse aussi)" % (p["name"], pname))
                if typ:
                    sc.declared[b] = typ
                if not is_arr:
                    info["params"][pname] = self.xvar(pname)
            if p["kind"] == "FUNCTION":
                info["result"] = self.names.new(base(p["name"])) + SUFFIX[self.type_of(p["name"], sc)]
                self.name_map.append(("%s (résultat)" % p["name"], info["result"]))
            self.proc_info[key] = info
            self.scope = self.global_scope

    def spec(self, key, arrays):
        """Étiquettes de la copie de la procédure key pour ces tableaux réels.

        Sans pointeurs, une procédure qui reçoit des tableaux différents est
        recopiée pour chacun ; ses variables simples restent communes."""
        info = self.proc_info[key]
        if arrays not in info["specs"]:
            info["specs"][arrays] = (self.new_label(), self.new_label())
            self.pending.append((key, arrays))
        return info["specs"][arrays]

    # -------------------------------------------------- programme
    def translate(self):
        self.name_map = []
        self.global_shared = set()
        for s in self.main:                                # DIM SHARED, CONST, DEF...
            if s[0] == "dim" and s[1]:
                for n, _, _ in s[2]:
                    self.global_shared.add(base(n))
            if s[0] == "deftype":
                self.apply_deftype(s)
            if s[0] == "dim":
                for n, _, typ in s[2]:
                    if typ:
                        self.global_scope.declared[base(n)] = typ
            if s[0] == "const":
                for n, e in s[1]:
                    self.consts[base(n)] = e
        self.prepare_procs()
        self.pending = []
        self.hoisted_dims = {}                             # tableaux locaux des procédures
        for key, p in self.procs.items():              # sans tableau : une seule copie
            if not any(is_arr for _, is_arr, _ in p["params"]):
                self.spec(key, ())
        self.emit("DEFSNG A-Z")                            # QuickBASIC : simple par défaut
        self.gen_block(self.main, {})
        self.emit("END")
        while self.pending:                                # copies demandées par les appels
            key, arrays = self.pending.pop(0)
            self.gen_proc(key, self.procs[key], arrays)
        if self.hoisted_dims:                              # juste après DEFSNG A-Z
            self.items.insert(1, ("stmt", "DIM " + ",".join(self.hoisted_dims.values()), False))
        for key, info in self.proc_info.items():
            if len(info["specs"]) > 1:
                self.warn("%s reçoit %d tableaux différents : une copie de la procédure "
                          "pour chacun" % (self.procs[key]["name"], len(info["specs"])))
        return self.layout()

    def apply_deftype(self, s):
        _, typ, ranges = s
        for a, b in ranges:
            for c in range(ord(a[0]), ord(b[0]) + 1):
                self.deftype[chr(c)] = typ

    def gen_proc(self, key, p, arrays=()):
        info = self.proc_info[key]
        self.scope = info["scope"]
        self.scope.alias = {base(pn): a for (pn, _, _), a in
                            zip([q for q in p["params"] if q[1]], arrays)}
        label, exit_label = info["specs"][arrays]
        for s in p["body"]:
            if s[0] == "shared":
                for n, _, typ in s[1]:
                    self.scope.shared.add(base(n))
                    if typ:
                        self.global_scope.declared[base(n)] = typ
            if s[0] == "static":
                for n, _, typ in s[1]:
                    self.scope.statics.add(base(n))
                    if typ:
                        self.scope.declared[base(n)] = typ
            if s[0] == "dim":
                for n, _, typ in s[2]:
                    if typ:
                        self.scope.declared[base(n)] = typ
        self.place(label)
        if not p["static"]:
            self.zero_locals(p, info)
        ctx = {"proc": p, "info": info, "exit": exit_label}
        self.gen_block(p["body"], ctx)
        self.place(exit_label)
        self.emit("RETURN")
        self.scope = self.global_scope

    def zero_locals(self, p, info):
        """Variables locales remises à zéro à chaque appel (sauf STATIC)."""
        names = set()

        def walk(node):
            if isinstance(node, tuple) and node:
                if node[0] in ("var",) and base(node[1]) not in self.consts \
                        and base(node[1]) not in self.scope.statics \
                        and base(node[1]) not in self.scope.shared \
                        and base(node[1]) not in self.global_shared \
                        and node[1] not in info["params"] and base(node[1]) != base(p["name"]):
                    names.add(node[1])
                for c in node[1:]:
                    walk(c)
            elif isinstance(node, list):
                for c in node:
                    walk(c)
        walk(p["body"])
        for n in sorted(names):
            xv = self.xvar(n)
            self.emit('%s=%s' % (xv, '""' if xv.endswith("$") else "0"))
        if info["result"]:
            self.emit('%s=%s' % (info["result"], '""' if info["result"].endswith("$") else "0"))

    def gen_block(self, stmts, ctx):
        for s in stmts:
            self.gen(s, ctx)

    def jump(self, lab):
        return "@" + lab

    def cond_false_jump(self, cond, lab):
        """Saute à lab si cond est faux (QuickBASIC : faux = 0)."""
        c = self.hoist(cond)
        if c[0] == "bin" and c[1] in REL:
            inv = {"=": "<>", "<>": "=", "<": ">=", ">=": "<", ">": "<=", "<=": ">"}[c[1]]
            self.emit("IF %s THEN @%s" % (self.x(("bin", inv, c[2], c[3])), lab), True)
        else:
            self.emit("IF %s=0 THEN @%s" % (self.x(c, PREC["="] + 1), lab), True)

    def cond_true_jump(self, cond, lab):
        c = self.hoist(cond)
        self.emit("IF %s THEN @%s" % (self.x(c), lab), True)

    def gen(self, s, ctx):
        k = s[0]
        getattr(self, "g_" + k)(s, ctx)

    def g_label(self, s, ctx):
        self.place(self.user_label(s[1]))

    def g_let(self, s, ctx):
        tgt, e = s[1], s[2]
        proc = ctx.get("proc")
        if tgt[0] == "var" and proc and proc["kind"] == "FUNCTION" and base(tgt[1]) == base(proc["name"]):
            res = ctx["info"]["result"]
            e = self.hoist(e)
            self.emit("%s=%s" % (res, self.x(self.convert(e, res))))
            return
        e = self.hoist(e)
        t = self.x(self.hoist(tgt))
        self.emit("%s=%s" % (t, self.x(self.convert(e, t))))

    def g_print(self, s, ctx):
        parts = []
        items = [i if isinstance(i, str) else self.hoist(i) for i in s[1]]
        for i in items:
            if isinstance(i, str):
                parts.append(i)
            else:
                if parts and not isinstance(parts[-1], str):
                    parts.append(";")
                parts.append(self.x(i))
        self.emit(("PRINT " + "".join(parts)).rstrip())

    def g_using(self, s, ctx):
        fmt = self.hoist(s[1])
        items = [i if isinstance(i, str) else self.x(self.hoist(i)) for i in s[2]]
        self.warn("PRINT USING : accepté par la ROM, pas encore par le compilateur")
        self.emit("PRINT USING %s;%s" % (self.x(fmt), "".join(items)))

    def g_input(self, s, ctx):
        _, prompt, comma, tg = s
        if comma:
            self.warn('INPUT "texte", v : le X-07 affiche toujours « ? » (« ; » utilisé)')
        names = ",".join(self.x(self.hoist(t)) for t in tg)
        self.emit("INPUT %s%s" % ('"%s";' % prompt if prompt is not None else "", names))

    def g_lineinput(self, s, ctx):
        self.warn("LINE INPUT : accepté par la ROM, pas encore par le compilateur")
        self.emit("LINE INPUT %s%s" % ('"%s";' % s[1] if s[1] is not None else "",
                                      self.x(self.hoist(s[2]))))

    def g_if(self, s, ctx):
        _, arms, other = s
        # forme courte : IF c THEN instructions simples [ELSE ...] sur une ligne
        if len(arms) == 1 and self.simple_inline(arms[0][1]) and \
                (other is None or self.simple_inline(other)) and not self.has_ufn(arms[0][0]):
            text = self.inline_if(arms[0][0], arms[0][1], other, ctx)
            if text and len(text) <= self.line_len - 6:
                self.emit(text, True)
                return
        end = self.new_label()
        for cond, body in arms:
            nxt = self.new_label()
            self.cond_false_jump(cond, nxt)
            self.gen_block(body, ctx)
            if other is not None or cond is not arms[-1][0]:
                self.emit("GOTO @%s" % end)
            self.place(nxt)
        if other is not None:
            self.gen_block(other, ctx)
        self.place(end)

    def simple_inline(self, body):
        simple = ("let", "print", "goto", "gosub", "return", "end", "raw", "pset", "circle")
        return all(st[0] in simple for st in body) and not self.has_ufn(body) and len(body) <= 3

    def has_ufn(self, node):
        if isinstance(node, tuple):
            if node and node[0] in ("ufn", "callsub"):
                return True
            return any(self.has_ufn(c) for c in node[1:])
        if isinstance(node, list):
            return any(self.has_ufn(c) for c in node)
        return False

    def inline_if(self, cond, then, other, ctx):
        saved = len(self.items)

        def part(body):
            if len(body) == 1 and body[0][0] == "goto":
                return "@" + self.user_label(body[0][1])
            start = len(self.items)
            self.gen_block(body, ctx)
            texts = [it[1] for it in self.items[start:] if it[0] == "stmt"]
            if any(it[0] == "label" for it in self.items[start:]):
                return None
            del self.items[start:]
            return ":".join(texts)
        t = part(then)
        o = part(other) if other is not None else ""
        if t is None or o is None:
            del self.items[saved:]
            return None
        c = self.x(cond)
        return "IF %s THEN %s%s" % (c, t, " ELSE " + o if other is not None else "")

    def g_goto(self, s, ctx):
        self.emit("GOTO @%s" % self.user_label(s[1]))

    def g_gosub(self, s, ctx):
        self.emit("GOSUB @%s" % self.user_label(s[1]))

    def g_return(self, s, ctx):
        self.emit("RETURN")

    def g_on(self, s, ctx):
        e = self.hoist(s[1])
        self.emit("ON %s %s %s" % (self.x(e), s[2], ",".join("@" + self.user_label(l) for l in s[3])))

    def g_onerror(self, s, ctx):
        self.warn("ON ERROR : accepté par la ROM, pas par le compilateur")
        if s[1] == "0":
            self.emit("ON ERROR GOTO 0")
        else:
            self.emit("ON ERROR GOTO @%s" % self.user_label(s[1]))

    def g_resume(self, s, ctx):
        self.emit("RESUME @%s" % self.user_label(s[1]))

    def g_raw(self, s, ctx):
        self.emit(s[1])

    def g_rawe(self, s, ctx):
        self.emit(s[1] + self.x(self.hoist(s[2])))

    def g_warn(self, s, ctx):
        self.warn(s[1])

    def g_warnraw(self, s, ctx):
        self.warn(s[1])
        self.emit(s[2])

    def g_end(self, s, ctx):
        self.emit("END")

    def g_for(self, s, ctx):
        _, var, a, b, step, body = s
        v = self.x(("var", var))
        a, b = self.hoist(a), self.hoist(b)
        step = self.hoist(step) if step is not None else None
        after = self.new_label()
        # QuickBASIC n'exécute pas une boucle vide ; le X-07 l'exécute une fois
        sv = self.const_value(step) if step is not None else 1
        av, bv = self.const_value(a), self.const_value(b)
        bx = self.x(b)
        if not self.simple(b):
            tb = self.temp(self.etype(b) if self.etype(b) != "i" else "i")
            self.emit("%s=%s" % (tb, bx))
            bx = tb
        sx = None
        if step is not None:
            sx = self.x(step)
            if not self.simple(step) and sv is None:
                ts = self.temp(self.etype(step))
                self.emit("%s=%s" % (ts, sx))
                sx = ts
        ax = self.x(self.convert(a, v))
        if av is not None and bv is not None and sv is not None and \
                ((sv > 0 and av > bv) or (sv < 0 and av < bv)):
            self.emit("%s=%s" % (v, ax))              # boucle vide : jamais exécutée
            return
        need_guard = not (av is not None and bv is not None and sv is not None and
                          ((sv > 0 and av <= bv) or (sv < 0 and av >= bv)))
        if need_guard:
            if sv is None:
                self.emit("IF SGN(%s)*(%s-%s)>0 THEN @%s" % (sx, self.paren(ax), bx, after), True)
            elif sv >= 0:
                self.emit("IF %s>%s THEN @%s" % (ax, bx, after), True)
            else:
                self.emit("IF %s<%s THEN @%s" % (ax, bx, after), True)
        self.emit("FOR %s=%s TO %s%s" % (v, ax, bx, " STEP %s" % sx if sx else ""))
        inner = dict(ctx)
        inner["for"] = after
        self.gen_block(body, inner)
        self.emit("NEXT %s" % v)
        self.place(after)

    def paren(self, s):
        return s if re.fullmatch(r"[A-Z0-9.#%!$]+", s) else "(%s)" % s

    def simple(self, e):
        return e[0] in ("num", "var", "raw") and not (e[0] == "num" and e[1].startswith("-"))

    def const_value(self, e):
        if e is None:
            return None
        if e[0] == "num" and not e[1].startswith("&"):
            try:
                return float(e[1].rstrip("#").replace("D", "E"))
            except ValueError:
                return None
        if e[0] == "un" and e[1] == "-":
            v = self.const_value(e[2])
            return -v if v is not None else None
        if e[0] == "var" and base(e[1]) in self.consts:
            return self.const_value(self.consts[base(e[1])])
        if e[0] == "paren":
            return self.const_value(e[1])
        return None

    def g_do(self, s, ctx):
        _, pre, body, post = s
        top, end = self.new_label(), self.new_label()
        self.place(top)
        if pre:
            w, c = pre
            if w == "WHILE":
                self.cond_false_jump(c, end)
            else:
                self.cond_true_jump(c, end)
        inner = dict(ctx)
        inner["do"] = end
        self.gen_block(body, inner)
        if post:
            w, c = post
            if w == "UNTIL":
                self.cond_false_jump(c, top)
            else:
                self.cond_true_jump(c, top)
        else:
            self.emit("GOTO @%s" % top)
        self.place(end)

    def g_exit(self, s, ctx):
        w = s[1]
        if w == "DO":
            if "do" not in ctx:
                raise QBError("EXIT DO hors d'une boucle DO")
            self.emit("GOTO @%s" % ctx["do"])
        elif w == "FOR":
            if "for" not in ctx:
                raise QBError("EXIT FOR hors d'une boucle FOR")
            self.emit("GOTO @%s" % ctx["for"])
        else:
            if "info" not in ctx:
                raise QBError("EXIT %s hors d'une procédure" % w)
            self.emit("GOTO @%s" % ctx["exit"])

    def g_select(self, s, ctx):
        _, sel, cases, other = s
        sel = self.hoist(sel)
        t = self.temp(self.etype(sel))
        self.emit("%s=%s" % (t, self.x(sel)))
        tv = ("raw", t, self.etype(sel))
        end = self.new_label()
        for tests, body in cases:
            nxt = self.new_label()
            conds = []
            for test in tests:
                if test[0] == "is":
                    conds.append(("bin", test[1], tv, test[2]))
                else:
                    conds.append(("bin", "AND", ("bin", ">=", tv, test[1]),
                                  ("bin", "<=", tv, test[2])))
            c = conds[0]
            for d in conds[1:]:
                c = ("bin", "OR", c, d)
            self.cond_false_jump(c, nxt)
            self.gen_block(body, ctx)
            self.emit("GOTO @%s" % end)
            self.place(nxt)
        if other:
            self.gen_block(other, ctx)
        self.place(end)

    def g_dim(self, s, ctx):
        _, shared, decls = s
        out, local = [], []
        for name, dims, typ in decls:
            if typ:
                self.scope.declared[base(name)] = typ
            if dims is None:
                continue
            sizes = []
            for lo, hi in dims:
                if lo is not None:
                    lv = self.const_value(lo)
                    if lv not in (0, 1):
                        raise QBError("DIM %s(%s TO ...) : le X-07 commence toujours à 0"
                                      % (name, self.x(lo)))
                sizes.append(self.x(self.hoist(hi)))
            xn = self.xvar(name, True)
            text = "%s(%s)" % (xn, ",".join(sizes))
            consts = [self.const_value(hi) for _, hi in dims]
            if "proc" in ctx and None not in consts and len(dims) <= 2:
                local.append((name, xn, text, [int(c) for c in consts]))
            else:
                out.append(text)
        for name, xn, text, sizes in local:
            # tableau local de taille constante : DIM une seule fois, en tête du
            # programme (un DIM refait donnerait DD Error, et le compilateur
            # refuse deux DIM) ; remis à zéro à chaque appel, comme QuickBASIC
            self.hoisted_dims[xn] = text
            if ctx["proc"]["static"] or base(name) in self.scope.statics:
                continue
            zero = '""' if xn.endswith("$") else "0"
            idx = [self.temp("i") for _ in sizes]
            loops = ":".join("FOR %s=0 TO %d" % (t, n) for t, n in zip(idx, sizes))
            nexts = ":".join("NEXT %s" % t for t in reversed(idx))
            self.emit("%s:%s(%s)=%s:%s" % (loops, xn, ",".join(idx), zero, nexts))
        if out and "proc" in ctx:
            # taille variable : DIM au premier appel seulement (ROM uniquement)
            self.warn("tableau local de taille variable : créé au premier appel, jamais "
                      "remis à zéro (comme STATIC) ; le compilateur ne l'accepte pas "
                      "si la procédure est recopiée")
            key = ",".join(out)                 # même DIM dans chaque copie : un seul drapeau
            flag = ctx["info"]["dimflags"].get(key) or self.temp("i")
            ctx["info"]["dimflags"][key] = flag
            self.emit("IF %s=0 THEN DIM %s:%s=1" % (flag, ",".join(out), flag), True)
        elif out:
            self.emit("DIM " + ",".join(out))

    def g_shared(self, s, ctx):
        pass

    def g_static(self, s, ctx):
        pass

    def g_const(self, s, ctx):
        for n, e in s[1]:
            self.consts[base(n)] = e

    def g_deftype(self, s, ctx):
        self.apply_deftype(s)

    def g_deffn(self, s, ctx):
        _, name, params, e = s
        fn = "FN" + self.names.new(base(name)[2:]) + SUFFIX[self.type_of(name)]
        self.deffn_names[name] = fn
        self.name_map.append((name, fn))
        ps = [self.xvar(p) for p in params]
        self.emit("DEF%s%s=%s" % (fn, "(%s)" % ",".join(ps) if ps else "", self.x(e)))

    def g_data(self, s, ctx):
        self.emit("DATA " + ",".join(s[1]), True)

    def g_read(self, s, ctx):
        self.emit("READ " + ",".join(self.x(self.hoist(t)) for t in s[1]))

    def g_restore(self, s, ctx):
        self.emit("RESTORE" + (" @%s" % self.user_label(s[1]) if s[1] else ""))

    def g_locate(self, s, ctx):
        _, row, col = s
        r = self.x(("bin", "-", self.hoist(row), ("num", "1", "i"))) if row is not None else "CSRLIN"
        c = self.x(("bin", "-", self.hoist(col), ("num", "1", "i"))) if col is not None else "POS(0)"
        self.emit("LOCATE %s,%s" % (self.fold(c), self.fold(r)))

    def fold(self, text):
        m = re.fullmatch(r"(\d+)-1", text)
        return str(int(m.group(1)) - 1) if m else text

    def g_pset(self, s, ctx):
        _, (x, y), c, word = s
        x, y = self.hoist(x), self.hoist(y)
        if c is not None:
            cv = self.const_value(c)
            if cv == 0:
                word = "PRESET"
            elif cv is None:
                cx = self.x(self.hoist(c))
                self.emit("IF %s=0 THEN PRESET(%s,%s) ELSE PSET(%s,%s)" % (
                    self.paren(cx), self.x(x), self.x(y), self.x(x), self.x(y)), True)
                return
        self.emit("%s(%s,%s)" % (word, self.x(x), self.x(y)))

    def g_line(self, s, ctx):
        _, (x1, y1), (x2, y2), color, box = s
        if color is not None and self.const_value(color) == 0:
            self.warn("LINE en couleur 0 (effacement) : non traduit, tracé normal")
        x1, y1, x2, y2 = (self.x(self.hoist(v)) for v in (x1, y1, x2, y2))
        if box is None:
            self.emit("LINE(%s,%s)-(%s,%s)" % (x1, y1, x2, y2))
        elif box == "B":
            for a, b, c, d in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
                self.emit("LINE(%s,%s)-(%s,%s)" % (a, b, c, d))
        else:
            t = self.temp("i")
            self.emit("FOR %s=%s TO %s:LINE(%s,%s)-(%s,%s):NEXT" % (t, y1, y2, x1, t, x2, t))

    def g_circle(self, s, ctx):
        _, (x, y), r = s
        self.emit("CIRCLE(%s,%s),%s" % (self.x(self.hoist(x)), self.x(self.hoist(y)),
                                         self.x(self.hoist(r))))

    def g_swap(self, s, ctx):
        a, b = self.x(self.hoist(s[1])), self.x(self.hoist(s[2]))
        t = self.temp(self.etype(s[1]))
        self.emit("%s=%s:%s=%s:%s=%s" % (t, a, a, b, b, t))

    def g_randomize(self, s, ctx):
        t = self.temp("s")
        self.emit("%s=RND(-%s)" % (t, self.paren(self.x(self.hoist(s[1])))))

    def g_sleep(self, s, ctx):
        lab = self.new_label()
        self.place(lab)
        self.emit('IF INKEY$="" THEN @%s' % lab, True)

    def g_poke(self, s, ctx):
        self.warn("%s : les adresses et ports du X-07 diffèrent de ceux du PC" % s[1])
        self.emit("%s %s,%s" % (s[1], self.x(self.hoist(s[2])), self.x(self.hoist(s[3]))))

    def g_erase(self, s, ctx):
        self.emit("ERASE " + ",".join(self.xvar(n, True) for n in s[1]))

    def g_callsub(self, s, ctx):
        name = s[1]
        if name not in self.procs:
            raise QBError("SUB %s inconnue" % name)
        args = [self.hoist(a) for a in s[2]]
        self.call_proc(self.procs[name], args, s[2])

    # -------------------------------------------------- numérotation
    def layout(self, start=10, step=10):
        items = []
        for it in self.items:          # END ; END -> END
            if not (it[0] == "stmt" and it[1] == "END" and items and items[-1][0] == "stmt"
                    and items[-1][1] == "END"):
                items.append(it)
        self.items = items
        lines = []                     # [labels, [textes], fin]
        pending = []
        for it in self.items:
            if it[0] == "label":
                pending.append(it[1])
                continue
            _, text, ends = it
            cur = lines[-1] if lines else None
            if cur and not pending and not cur[2] and \
                    len(":".join(cur[1] + [text])) <= self.line_len and \
                    not text.startswith(("DATA", "DEF")) and \
                    not cur[1][-1].startswith(("DATA", "DEF")):
                cur[1].append(text)
                cur[2] = ends
            else:
                lines.append([pending, [text], ends])
                pending = []
        if pending:
            lines.append([pending, ["END"], True])
        numbers = {}
        for k, l in enumerate(lines):
            num = start + k * step
            for lab in l[0]:
                numbers[lab] = num
        # « @Gn+ » : ligne qui suit l'étiquette Gn (sortie de FOR)
        out = []
        for k, l in enumerate(lines):
            text = ":".join(l[1])

            def repl(m):
                lab, plus = m.group(1), m.group(2)
                if lab not in numbers:
                    raise QBError("étiquette introuvable")
                n = numbers[lab]
                return str(n + step if plus else n)
            text = '"'.join(re.sub(r"@(G\d+)(\+?)", repl, piece) if k % 2 == 0 else piece
                           for k, piece in enumerate(text.split('"')))
            out.append("%d %s" % (start + k * step, text))
        for key in self.labels:
            if self.labels[key] not in numbers:
                raise QBError("étiquette %s introuvable" % key[1:])
        if start + (len(lines) - 1) * step > 65529:
            raise QBError("programme trop long pour les numéros de ligne du X-07")
        return "\n".join(out) + "\n"


def translate(text, line_len=72):
    """Rend (programme X-07, avertissements, correspondance des noms)."""
    tr = Translator(text, line_len)
    out = tr.translate()
    return out, tr.warnings, tr.name_map
