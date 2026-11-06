"""Quick C (.qc) : du C où les réels du X-07 s'écrivent comme des nombres.

    real x, y = 2.5;
    x = sqrt(y) * 3 + 1;            ->  r_sqrt, r_mul, r_add
    if (x > y) printf("%s\\n", str(x));

Le traducteur réécrit en appels de la bibliothèque (r_add, r_cmp...) les seules
expressions où paraît un réel ; le reste du programme est recopié tel quel,
ligne pour ligne (une directive #line garde les numéros du fichier .qc pour les
messages de SDCC, le débogueur et l'IDE).  Le C produit est compilé par SDCC
comme un .c (voir ccomp.py).

Règles :
  - real : réel en double précision de la ROM (14 chiffres, calcul décimal).
    Un entier mêlé à un réel est converti ; un réel rangé dans un entier est
    tronqué (r_toint), comme en C ; dans une condition, un réel est vrai s'il
    n'est pas nul.
  - constantes (2.5, 1E-3, et les entiers mêlés aux réels) : converties à la
    compilation par la routine FIN de la ROM.
  - fonctions : sqrt sin cos tan atan exp log fabs floor (INT) trunc (FIX)
    pow(a, b) ; val(texte) -> réel ; str(x), fmt(x, chiffres, décimales) ->
    texte (4 tampons tournants, pour printf).
  - une fonction peut prendre et rendre des réels (real f(real a, int n)) ; ils
    sont passés par valeur, comme en C (SDCC, qui ne passe pas de structure,
    reçoit des adresses).
  - non gérés : réels dans une structure ou une union, pointeurs de fonction.
"""
import os
import re

__all__ = ["QCError", "translate"]


class QCError(Exception):
    def __init__(self, msg, line=None):
        super().__init__(msg)
        self.line = line


# ---------------------------------------------------------------- lexique
_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r\f\v]+|\n)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<num>(?:0[xX][0-9A-Fa-f]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)[uUlLfF]*)
  | (?P<id>[A-Za-z_]\w*)
  | (?P<str>"(?:[^"\\\n]|\\.)*")
  | (?P<chr>'(?:[^'\\\n]|\\.)*')
  | (?P<op>\.\.\.|<<=|>>=|->|\+\+|--|<<|>>|<=|>=|==|!=|&&|\|\||[-+*/%&^|]=|[-+*/%&|^!~<>=?:;,.()\[\]{}])
""", re.S | re.X)

TYPE_WORDS = {"void", "char", "short", "int", "long", "float", "double", "signed",
              "unsigned", "_Bool", "bool", "real", "const", "volatile", "static", "extern",
              "register", "auto", "inline", "struct", "union", "enum", "typedef"}
ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}
BIN_PREC = {"*": 13, "/": 13, "%": 13, "+": 12, "-": 12, "<<": 11, ">>": 11,
            "<": 10, ">": 10, "<=": 10, ">=": 10, "==": 9, "!=": 9, "&": 8, "^": 7,
            "|": 6, "&&": 5, "||": 4}
REAL_FUNCS = {"sqrt": "r_sqrt", "sin": "r_sin", "cos": "r_cos", "tan": "r_tan",
              "atan": "r_atn", "exp": "r_exp", "log": "r_log", "fabs": "r_abs",
              "floor": "r_intp", "trunc": "r_fix"}
ARITH = {"+": "r_add", "-": "r_sub", "*": "r_mul", "/": "r_div"}
REALS = ("real", "realptr", "realarr")


class Tok:
    __slots__ = ("kind", "text", "start", "end", "line")

    def __init__(self, kind, text, start, end, line):
        self.kind, self.text, self.start, self.end, self.line = kind, text, start, end, line

    def __repr__(self):
        return "Tok(%s %r l%d)" % (self.kind, self.text, self.line)


def tokenize(text):
    toks, pos, line, bol = [], 0, 1, True
    while pos < len(text):
        if bol:                                  # directive du préprocesseur : une ligne
            m = re.match(r"[ \t]*#(?:[^\n\\]|\\.)*", text[pos:], re.S)
            if m:
                toks.append(Tok("pp", m.group(), pos, pos + m.end(), line))
                line += m.group().count("\n")
                pos += m.end()
                continue
        m = _TOKEN.match(text, pos)
        if not m:
            raise QCError("caractère inattendu %r" % text[pos], line)
        kind = m.lastgroup
        s = m.group()
        if kind == "ws":
            if s == "\n":
                line += 1
                bol = True
            pos = m.end()
            continue
        bol = False
        if kind == "comment":
            line += s.count("\n")
            pos = m.end()
            continue
        toks.append(Tok(kind, s, pos, m.end(), line))
        pos = m.end()
    return toks


def is_real_literal(s):
    if s.lower().startswith("0x"):
        return False
    return bool(re.fullmatch(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[fFlL]?", s)) and \
        bool(re.search(r"[.eE]", s))


# ---------------------------------------------------------------- arbre
class Node:
    __slots__ = ("k", "a", "s", "e", "t")

    def __init__(self, k, a, s, e):
        self.k, self.a, self.s, self.e = k, a, s, e       # sorte, enfants, jetons [s, e)
        self.t = None                                      # type, calculé ensuite


class Translator:
    def __init__(self, text, filename="programme.qc"):
        self.src = text
        self.filename = filename
        self.toks = tokenize(text)
        self.code = [t for t in self.toks if t.kind != "pp"]
        self.pos = 0
        self.edits = []                                    # (début, fin, texte)
        self.scopes = [{}]                                 # nom -> type
        self.typedefs = {"real"}
        self.funcs = {}                                    # nom -> (rend un réel, [types])
        self.consts = {}                                   # texte -> (nom, octets)
        self.real_macros = {}                              # #define PI 3.14 -> texte
        self.temps = 0
        self.max_temps = 0
        self.in_func = None
        self.after = []
        self.in_for = False
        self.static = False
        for t in self.toks:
            if t.kind == "pp":
                m = re.match(r"\s*#\s*define\s+(\w+)\s+(-?)\s*([\d.]+(?:[eE][+-]?\d+)?)\s*$",
                             t.text)
                if m and is_real_literal(m.group(3)):
                    self.real_macros[m.group(1)] = m.group(2) + m.group(3)

    # ------------------------------------------------ jetons
    def tok(self, k=0):
        i = self.pos + k
        return self.code[i] if i < len(self.code) else Tok("eof", "", len(self.src),
                                                         len(self.src), self.line())

    def line(self):
        if not self.code:
            return 1
        return self.code[min(self.pos, len(self.code) - 1)].line

    def err(self, msg, line=None):
        raise QCError(msg, line or self.line())

    def next(self):
        t = self.tok()
        self.pos += 1
        return t

    def isop(self, s, k=0):
        t = self.tok(k)
        return t.kind == "op" and t.text == s

    def expect(self, s):
        if not self.isop(s):
            self.err("« %s » attendu près de « %s »" % (s, self.tok().text))
        return self.next()

    def text_of(self, s, e):
        """Texte d'origine des jetons [s, e)."""
        if e <= s:
            return ""
        return self.src[self.code[s].start:self.code[e - 1].end]

    def replace(self, s, e, text):
        """Remplace les jetons [s, e) ; les sauts de ligne sont gardés (#line)."""
        old = self.text_of(s, e)
        self.edits.append((self.code[s].start, self.code[e - 1].end,
                           text + "\n" * old.count("\n")))

    # ------------------------------------------------ portées et types
    def lookup(self, name):
        for sc in reversed(self.scopes):
            if name in sc:
                return sc[name]
        return None

    def declare(self, name, typ):
        self.scopes[-1][name] = typ

    def is_type_start(self, k=0):
        t = self.tok(k)
        return t.kind == "id" and (t.text in TYPE_WORDS or
                                   (t.text in self.typedefs and self.lookup(t.text) is None
                                    and not self.isop("(", k + 1)))

    # ------------------------------------------------ constantes
    def const_bytes(self, text):
        from . import basic
        t = text.rstrip("fFlL")
        try:
            data, _ = basic.rom_constant(t + "#")          # en double précision
        except basic.CompileError as e:
            self.err(str(e))
        return data

    def init_bytes(self, text):
        return "{{%s}}" % ", ".join("0x%02X" % b for b in self.const_bytes(text))

    def const(self, text):
        if text not in self.consts:
            self.consts[text] = ("_qc_k%d" % (len(self.consts) + 1), self.const_bytes(text))
        return "&" + self.consts[text][0]

    def literal_text(self, n):
        """Texte d'une constante numérique (n : nombre, -nombre, macro réelle), ou None."""
        if n.k == "num":
            return self.code[n.s].text
        if n.k == "id" and n.a in self.real_macros and self.lookup(n.a) is None:
            return self.real_macros[n.a]
        if n.k == "unary" and n.a[0] == "-":
            inner = self.literal_text(n.a[1])
            if inner is not None:
                return inner[1:] if inner.startswith("-") else "-" + inner
        if n.k == "paren":
            return self.literal_text(n.a)
        return None

    # ================================================ programme
    def translate(self):
        while self.tok().kind != "eof":
            self.top_level()
        out, last = [], 0
        for s, e, text in sorted(self.edits, key=lambda x: (x[0], x[1])):
            out.append(self.src[last:s])
            out.append(text)
            last = e
        out.append(self.src[last:])
        prelude = ['#include "x07.h"']
        for text, (name, data) in self.consts.items():
            prelude.append("static const real %s = {{%s}};  /* %s */" % (
                name, ", ".join("0x%02X" % b for b in data), text))
        prelude.append('#line 1 "%s"' % self.filename)
        return "\n".join(prelude) + "\n" + "".join(out)

    def top_level(self):
        if self.isop(";"):
            self.next()
            return
        if not self.is_type_start():
            self.err("déclaration attendue près de « %s »" % self.tok().text)
        self.declaration(top=True)

    # ------------------------------------------------ déclarations
    def specifiers(self):
        """Jetons de type ; rend (est un réel, typedef, struct/union/enum avec corps)."""
        real = typedef = False
        while self.is_type_start():
            t = self.next()
            if t.text == "typedef":
                typedef = True
            elif t.text == "real":
                real = True
            elif t.text in ("struct", "union", "enum"):
                if self.tok().kind == "id":
                    self.next()
                if self.isop("{"):                         # corps : recopié tel quel
                    depth = 0
                    while True:
                        t2 = self.next()
                        if t2.kind == "eof":
                            self.err("« } » manquant")
                        if t2.text == "{":
                            depth += 1
                        elif t2.text == "}":
                            depth -= 1
                            if depth == 0:
                                break
                        elif t2.text == "real" and t2.kind == "id":
                            self.err("réel dans une structure : non géré par Quick C", t2.line)
        return real, typedef

    def declarator(self):
        """Rend (nom, pointeurs, tableau, paramètres ou None, jeton du nom)."""
        stars = 0
        while self.isop("*") or (self.tok().kind == "id" and self.tok().text in
                                 ("const", "volatile")):
            if self.isop("*"):
                stars += 1
            self.next()
        if self.isop("("):
            self.err("déclarateur entre parenthèses (pointeur de fonction) : non géré")
        name = None
        if self.tok().kind == "id":
            name = self.next()
        array = False
        params = None
        while True:
            if self.isop("["):
                depth = 0
                while True:
                    t = self.next()
                    if t.text == "[":
                        depth += 1
                    elif t.text == "]":
                        depth -= 1
                        if depth == 0:
                            break
                array = True
            elif self.isop("(") and params is None:
                params = self.param_list()
            elif self.tok().kind == "id" and self.tok().text.startswith("__"):
                self.next()                                # __naked, __sdcccall(1)...
                if self.isop("("):
                    self.skip_parens()
            else:
                break
        return name, stars, array, params

    def param_list(self):
        """( paramètres ) -> [(nom, type, début, fin)] (jetons)."""
        self.expect("(")
        params = []
        if self.isop(")"):
            self.next()
            return params
        while True:
            s = self.pos
            if self.isop("..."):
                self.next()
                params.append((None, "other", s, self.pos))
            else:
                real, _ = self.specifiers()
                name, stars, array, sub = self.declarator()
                typ = self.var_type(real, stars, array)
                params.append((name.text if name else None, typ, s, self.pos))
            if self.isop(","):
                self.next()
                continue
            self.expect(")")
            break
        if len(params) == 1 and params[0][0] is None and \
                self.text_of(params[0][2], params[0][3]).strip() == "void":
            return []
        return params

    @staticmethod
    def var_type(real, stars, array):
        if not real:
            return "other"
        if stars == 0:
            return "realarr" if array else "real"
        if stars == 1 and not array:
            return "realptr"
        return "other"

    def declaration(self, top=False, in_for=False):
        start = self.pos
        self.after = []                                    # affectations après la déclaration
        self.in_for = in_for
        real, typedef = self.specifiers()
        if self.isop(";"):                                 # struct x {...};
            self.next()
            return
        spec_end = self.pos
        self.static = "static" in [t.text for t in self.code[start:spec_end]]
        first = True
        while True:
            name, stars, array, params = self.declarator()
            if name is None:
                self.err("nom attendu dans la déclaration")
            if typedef:
                if real and stars == 0 and not array:
                    self.err("typedef d'un réel : non géré par Quick C")
                self.typedefs.add(name.text)
            elif params is not None:                       # fonction
                rets = real and stars == 0
                ptypes = [p[1] for p in params]
                self.funcs[name.text] = (rets, ptypes)
                self.declare(name.text, "func")
                if first and self.isop("{") and top:
                    self.function(start, spec_end, name, rets, params)
                    return
                if rets or "real" in ptypes:
                    self.replace(start if first else name_start, self.pos,
                                 self.signature(start, spec_end, name, rets, params, first))
            else:
                typ = self.var_type(real, stars, array)
                self.declare(name.text, typ)
                if self.isop("="):
                    self.next()
                    self.initializer(typ, top, name)
            first = False
            if self.isop(","):
                self.next()
                name_start = self.pos
                continue
            semi = self.expect(";")
            if self.after:                                 # real x = a * b; -> real x; x = ...
                self.edits.append((semi.end, semi.end, " " + " ".join(self.after)))
            return

    def signature(self, start, spec_end, name, rets, params, with_specs=True):
        spec = self.text_of(start, spec_end) if with_specs else ""
        if rets:
            spec = re.sub(r"\breal\b", "void", spec)
        out = []
        if rets:
            out.append("real *_qc_ret")
        for pname, ptyp, s, e in params:
            if ptyp == "real":
                out.append("const real *_qc_p_%s" % (pname or "x%d" % len(out)))
            else:
                out.append(self.text_of(s, e))
        return "%s%s(%s)" % (spec + " " if spec else "", name.text, ", ".join(out) or "void")

    def initializer(self, typ, top, name):
        s = self.pos
        if typ == "realarr" or (typ == "real" and self.isop("{")):
            if not self.isop("{"):
                self.err("tableau de réels : valeurs entre accolades attendues")
            self.next()
            items = []
            while not self.isop("}"):
                n = self.expr_assign()
                lit = self.literal_text(n)
                if lit is None:
                    self.err("tableau de réels : constantes seulement")
                items.append(self.init_bytes(lit))
                if self.isop(","):
                    self.next()
            self.expect("}")
            self.replace(s, self.pos, "{ %s }" % ", ".join(items))
            return
        n = self.expr_assign()
        self.typeof(n)
        if typ == "real":
            lit = self.literal_text(n)
            if lit is not None:
                self.replace(s, self.pos, self.init_bytes(lit))
            elif top or self.in_func is None or self.static:
                self.err("réel global ou statique : une constante est attendue", name.line)
            elif self.in_for:
                self.err("for (real x = ...) : seule une constante est admise ici", name.line)
            else:                                          # SDCC n'initialise une structure
                self.start_expr()                          # qu'avec des accolades
                self.after.append("%s;" % self.rexpr(n, "&%s" % name.text))
                self.end_expr()
                self.replace(s - 1, self.pos, "")
        elif self.needs(n):
            if top:
                self.err("initialisation globale : pas de réel", name.line)
            self.start_expr()
            self.replace(s, self.pos, self.iexpr(n))
            self.end_expr()

    # ------------------------------------------------ fonctions
    def function(self, start, spec_end, name, rets, params):
        transformed = rets or any(p[1] == "real" for p in params)
        if transformed:
            self.replace(start, self.pos, self.signature(start, spec_end, name, rets, params))
        self.in_func = (name.text, rets)
        self.max_temps = 0
        self.scopes.append({})
        copies = []
        for pname, ptyp, s, e in params:
            if pname:
                self.declare(pname, ptyp)
                if ptyp == "real":                         # par valeur : une copie locale
                    copies.append("real %s; %s = *_qc_p_%s;" % (pname, pname, pname))
        brace = self.tok()
        self.block(new_scope=False)
        self.scopes.pop()
        temps = ["_qc_t%d" % (k + 1) for k in range(self.max_temps)]
        decl = (" real %s;" % ", ".join(temps) if temps else "") + \
            "".join(" " + c for c in copies)
        if decl:
            self.edits.append((brace.end, brace.end, decl))
        self.in_func = None

    # ------------------------------------------------ instructions
    def block(self, new_scope=True):
        self.expect("{")
        if new_scope:
            self.scopes.append({})
        while not self.isop("}"):
            if self.tok().kind == "eof":
                self.err("« } » manquant")
            self.statement()
        self.next()
        if new_scope:
            self.scopes.pop()

    def statement(self):
        t = self.tok()
        if self.isop("{"):
            return self.block()
        if self.isop(";"):
            self.next()
            return
        if t.kind == "id":
            w = t.text
            if w == "if":
                self.next()
                self.cond_paren()
                self.statement()
                if self.tok().text == "else":
                    self.next()
                    self.statement()
                return
            if w in ("while", "switch"):
                self.next()
                if w == "while":
                    self.cond_paren()
                else:
                    self.expect("(")
                    self.full_expr(int_ctx=True)
                    self.expect(")")
                self.statement()
                return
            if w == "do":
                self.next()
                self.statement()
                if self.tok().text != "while":
                    self.err("« while » attendu après do")
                self.next()
                self.cond_paren()
                self.expect(";")
                return
            if w == "for":
                self.next()
                self.expect("(")
                self.scopes.append({})
                if self.is_type_start():
                    self.declaration(in_for=True)
                else:
                    if not self.isop(";"):
                        self.full_expr()
                    self.expect(";")
                if not self.isop(";"):
                    self.full_expr(cond=True)
                self.expect(";")
                if not self.isop(")"):
                    self.full_expr()
                self.expect(")")
                self.statement()
                self.scopes.pop()
                return
            if w == "return":
                return self.return_stmt()
            if w in ("break", "continue"):
                self.next()
                self.expect(";")
                return
            if w == "goto":
                self.next()
                self.next()
                self.expect(";")
                return
            if w == "case":
                self.next()
                self.full_expr(int_ctx=True)
                self.expect(":")
                return
            if w == "default":
                self.next()
                self.expect(":")
                return
            if self.isop(":", 1) and w not in TYPE_WORDS:     # étiquette
                self.next()
                self.next()
                return
            if self.is_type_start():
                return self.declaration()
        self.full_expr()
        self.expect(";")

    def cond_paren(self):
        self.expect("(")
        self.full_expr(cond=True)
        self.expect(")")

    def return_stmt(self):
        s = self.pos
        self.next()
        if self.isop(";"):
            self.next()
            return
        es = self.pos
        n = self.expr()
        self.typeof(n)
        fname, rets = self.in_func or (None, False)
        if rets:
            self.start_expr()
            p = self.rexpr(n)
            self.end_expr()
            self.expect(";")
            self.replace(s, self.pos, "{ *_qc_ret = *(%s); return; }" % p)
            return
        if self.needs(n):
            self.start_expr()
            self.replace(es, self.pos, self.iexpr(n))
            self.end_expr()
        self.expect(";")

    def full_expr(self, cond=False, int_ctx=False):
        s = self.pos
        n = self.expr()
        self.typeof(n)
        if not self.needs(n):
            return
        self.start_expr()
        if cond:
            text = self.bexpr(n)
        elif n.t == "real":
            text = self.rexpr(n)
        else:
            text = self.iexpr(n)
        self.end_expr()
        self.replace(s, self.pos, text)

    def start_expr(self):
        self.temps = 0

    def end_expr(self):
        self.max_temps = max(self.max_temps, self.temps)

    # ================================================ expressions : analyse
    def expr(self):
        s = self.pos
        n = self.expr_assign()
        while self.isop(","):
            self.next()
            b = self.expr_assign()
            n = Node("comma", (n, b), s, self.pos)
        return n

    def expr_assign(self):
        s = self.pos
        n = self.expr_cond()
        t = self.tok()
        if t.kind == "op" and t.text in ASSIGN_OPS:
            self.next()
            r = self.expr_assign()
            return Node("assign", (t.text, n, r), s, self.pos)
        return n

    def expr_cond(self):
        s = self.pos
        c = self.expr_bin(4)
        if self.isop("?"):
            self.next()
            a = self.expr()
            self.expect(":")
            b = self.expr_cond()
            return Node("cond", (c, a, b), s, self.pos)
        return c

    def expr_bin(self, minprec):
        s = self.pos
        left = self.expr_unary()
        while True:
            t = self.tok()
            prec = BIN_PREC.get(t.text) if t.kind == "op" else None
            if prec is None or prec < minprec:
                return left
            self.next()
            right = self.expr_bin(prec + 1)
            left = Node("bin", (t.text, left, right), s, self.pos)

    def cast_ahead(self):
        return self.isop("(") and self.is_type_start(1)

    def expr_unary(self):
        s = self.pos
        t = self.tok()
        if t.kind == "op" and t.text in ("++", "--"):
            self.next()
            return Node("preinc", (t.text, self.expr_unary()), s, self.pos)
        if t.kind == "op" and t.text in ("+", "-", "!", "~", "*", "&"):
            self.next()
            return Node("unary", (t.text, self.expr_unary()), s, self.pos)
        if t.kind == "id" and t.text == "sizeof":
            self.next()
            if self.cast_ahead():
                self.skip_parens()
            else:
                self.expr_unary()
            return Node("leaf", None, s, self.pos)
        if self.cast_ahead():
            self.next()
            ts = self.pos
            while not self.isop(")"):
                self.next()
            words = [x.text for x in self.code[ts:self.pos]]
            self.next()
            return Node("cast", (words, self.expr_unary()), s, self.pos)
        return self.expr_postfix()

    def skip_parens(self):
        depth = 0
        while True:
            t = self.next()
            if t.text == "(":
                depth += 1
            elif t.text == ")":
                depth -= 1
                if depth == 0:
                    return
            elif t.kind == "eof":
                self.err("« ) » manquant")

    def expr_postfix(self):
        s = self.pos
        n = self.primary()
        while True:
            if self.isop("["):
                self.next()
                i = self.expr()
                self.expect("]")
                n = Node("index", (n, i), s, self.pos)
            elif self.isop("("):
                self.next()
                args = []
                while not self.isop(")"):
                    args.append(self.expr_assign())
                    if self.isop(","):
                        self.next()
                    elif not self.isop(")"):
                        self.err("« , » ou « ) » attendu dans l'appel")
                self.next()
                n = Node("call", (n, args), s, self.pos)
            elif self.isop(".") or self.isop("->"):
                op = self.next().text
                self.next()
                n = Node("member", (op, n), s, self.pos)
            elif self.isop("++") or self.isop("--"):
                op = self.next().text
                n = Node("postinc", (op, n), s, self.pos)
            else:
                return n

    def primary(self):
        s = self.pos
        t = self.tok()
        if t.kind == "id" and t.text not in TYPE_WORDS:
            self.next()
            return Node("id", t.text, s, self.pos)
        if t.kind == "num":
            self.next()
            return Node("num", t.text, s, self.pos)
        if t.kind == "str":
            while self.tok().kind == "str":
                self.next()
            return Node("leaf", None, s, self.pos)
        if t.kind == "chr":
            self.next()
            return Node("leaf", None, s, self.pos)
        if self.isop("("):
            self.next()
            n = self.expr()
            self.expect(")")
            return Node("paren", n, s, self.pos)
        self.err("expression attendue près de « %s »" % t.text)

    # ================================================ types
    def typeof(self, n):
        k = n.k
        if k == "num":
            t = "real" if is_real_literal(n.a) else "int"
        elif k == "id":
            v = self.lookup(n.a)
            if v is None and n.a in self.real_macros:
                v = "real"
            t = v if v in REALS or v == "func" else "int"
        elif k == "leaf":
            t = "int"
        elif k == "paren":
            t = self.typeof(n.a)
        elif k == "comma":
            self.typeof(n.a[0])
            t = self.typeof(n.a[1])
        elif k == "assign":
            op, l, r = n.a
            lt, rt = self.typeof(l), self.typeof(r)
            if lt != "real" and rt == "real" and op != "=":
                self.err("« %s » d'un réel dans un entier : écrivez n = n %s x"
                         % (op, op[0]), self.code[n.s].line)
            t = lt
        elif k == "cond":
            self.typeof(n.a[0])
            a, b = self.typeof(n.a[1]), self.typeof(n.a[2])
            t = "real" if "real" in (a, b) else a
        elif k == "bin":
            op, a, b = n.a
            ta, tb = self.typeof(a), self.typeof(b)
            if op in ARITH and "real" in (ta, tb):
                if ta in ("realptr", "realarr") or tb in ("realptr", "realarr"):
                    self.err("calcul mêlant un réel et un pointeur", self.code[n.s].line)
                t = "real"
            elif op in ("+", "-") and ta in ("realptr", "realarr") and tb == "int":
                t = "realptr"
            elif "real" in (ta, tb) and op not in ("<", ">", "<=", ">=", "==", "!=",
                                                   "&&", "||"):
                self.err("opérateur « %s » sur un réel" % op, self.code[n.s].line)
            else:
                t = "int"
        elif k == "unary":
            op, x = n.a
            tx = self.typeof(x)
            if op == "*":
                t = "real" if tx in ("realptr", "realarr") else "int"
            elif op == "&":
                t = "realptr" if tx == "real" else "int"
            elif op in ("-", "+"):
                t = tx
            elif op == "~" and tx == "real":
                self.err("opérateur « ~ » sur un réel", self.code[n.s].line)
            else:
                t = "int"
        elif k in ("preinc", "postinc"):
            t = self.typeof(n.a[1])
        elif k == "cast":
            words, x = n.a
            self.typeof(x)
            if "real" in words:
                t = "real" if "*" not in words else "realptr"
            else:
                t = "int"
        elif k == "index":
            tb = self.typeof(n.a[0])
            self.typeof(n.a[1])
            t = "real" if tb in ("realptr", "realarr") else "int"
        elif k == "member":
            self.typeof(n.a[1])
            t = "int"
        elif k == "call":
            f, args = n.a
            for x in args:
                self.typeof(x)
            name = f.a if f.k == "id" else None
            if name and name in self.funcs and self.lookup(name) == "func":
                t = "real" if self.funcs[name][0] else "int"
            elif name in REAL_FUNCS or name in ("pow", "val"):
                t = "real"
            else:
                self.typeof(f)
                t = "int"
        else:
            t = "int"
        n.t = t
        return t

    def needs(self, n):
        """L'expression demande-t-elle une réécriture (un réel y paraît) ?"""
        if n.t == "real":
            return True
        if n.k == "call":
            f = n.a[0]
            name = f.a if f.k == "id" else None
            if name in ("str", "fmt") and self.lookup(name) is None:
                return True
            if name in self.funcs and self.lookup(name) == "func" and \
                    "real" in self.funcs[name][1]:
                return True
            return any(self.needs(x) for x in n.a[1]) or self.needs(f)
        for c in self.children(n):
            if self.needs(c):
                return True
        return False

    @staticmethod
    def children(n):
        k = n.k
        if k in ("num", "id", "leaf"):
            return []
        if k == "paren":
            return [n.a]
        if k == "comma":
            return list(n.a)
        if k in ("assign", "bin"):
            return [n.a[1], n.a[2]]
        if k == "cond":
            return list(n.a)
        if k in ("unary", "preinc", "postinc", "member", "cast"):
            return [n.a[1]]
        if k == "index":
            return list(n.a)
        if k == "call":
            return [n.a[0]] + list(n.a[1])
        return []

    # ================================================ expressions : production
    def temp(self):
        self.temps += 1
        return "&_qc_t%d" % self.temps

    def orig(self, n):
        return self.text_of(n.s, n.e)

    def lvalue(self, n):
        """Texte C d'un réel désignable (variable, t[i], *p) ; None sinon."""
        if n.k == "id" and n.t == "real" and n.a not in self.real_macros:
            return n.a
        if n.k == "id" and n.t == "real":
            return n.a
        if n.k == "paren":
            return self.lvalue(n.a)
        if n.k == "index" and n.t == "real":
            return "%s[%s]" % (self.iexpr(n.a[0]), self.iexpr(n.a[1]))
        if n.k == "unary" and n.a[0] == "*" and n.t == "real":
            return "*%s" % self.iexpr(n.a[1])
        return None

    def rexpr(self, n, dst=None):
        """Texte C qui calcule le réel n et vaut son adresse (const real *).
        dst : adresse où ranger le résultat (sinon un temporaire)."""
        def into(call):                                  # call(d) : l'appel qui range en d
            d = dst or self.temp()
            return "(%s, %s)" % (call(d), d)

        lit = self.literal_text(n)
        if lit is not None:
            p = self.const(lit)
            return "(*%s = *%s, %s)" % (dst, p, dst) if dst else p
        if n.t != "real":                                  # entier -> réel
            i = self.iexpr(n)
            return into(lambda d: "r_int(%s, %s)" % (d, i))
        k = n.k
        lv = self.lvalue(n)
        if lv is not None:
            p = "&(%s)" % lv if n.k != "id" else "&" + lv
            return "(*%s = %s, %s)" % (dst, lv, dst) if dst else p
        if k == "paren":
            return self.rexpr(n.a, dst)
        if k == "bin":
            op, a, b = n.a
            ra, rb = self.rexpr(a), self.rexpr(b)
            return into(lambda d: "%s(%s, %s, %s)" % (ARITH[op], d, ra, rb))
        if k == "unary":
            op, x = n.a
            if op == "+":
                return self.rexpr(x, dst)
            rx = self.rexpr(x)
            return into(lambda d: "r_neg(%s, %s)" % (d, rx))
        if k == "cast":
            if n.a[1].t == "real":
                return self.rexpr(n.a[1], dst)
            i = self.iexpr(n.a[1])
            return into(lambda d: "r_int(%s, %s)" % (d, i))
        if k == "cond":
            c, a, b = n.a
            return "(%s ? %s : %s)" % (self.bexpr(c), self.rexpr(a, dst), self.rexpr(b, dst))
        if k == "comma":
            return "(%s, %s)" % (self.vexpr(n.a[0]), self.rexpr(n.a[1], dst))
        if k == "assign":
            op, l, r = n.a
            target = self.lvalue(l)
            if target is None:
                self.err("affectation : variable réelle attendue", self.code[n.s].line)
            a = "&(%s)" % target
            if op == "=":
                return self.rexpr(r, a)
            if op[0] not in ARITH:
                self.err("opérateur « %s » sur un réel" % op, self.code[n.s].line)
            return "(%s(%s, %s, %s), %s)" % (ARITH[op[0]], a, a, self.rexpr(r), a)
        if k in ("preinc", "postinc"):
            op, x = n.a
            target = self.lvalue(x)
            if target is None:
                self.err("%s : variable réelle attendue" % op, self.code[n.s].line)
            a = "&(%s)" % target
            step = "%s(%s, %s, %s)" % (ARITH[op[0]], a, a, self.const("1"))
            if k == "preinc":
                return "(%s, %s)" % (step, a)
            old = self.temp()
            return "(*%s = %s, %s, %s)" % (old, target, step, old)
        if k == "call":
            return self.rcall(n, dst)
        self.err("expression réelle non gérée", self.code[n.s].line)

    def rcall(self, n, dst):
        f, args = n.a
        name = f.a if f.k == "id" else None
        line = self.code[n.s].line

        def into(fn, parts):                               # fn(d, parties) : l'appel
            d = dst or self.temp()
            return "(%s(%s), %s)" % (fn, ", ".join([d] + parts), d)
        if name in self.funcs and self.lookup(name) == "func":
            return into(name, self.args(name, args))
        if name in REAL_FUNCS:
            if len(args) != 1:
                self.err("%s : un argument attendu" % name, line)
            return into(REAL_FUNCS[name], [self.rexpr(args[0])])
        if name == "pow":
            if len(args) != 2:
                self.err("pow : deux arguments attendus", line)
            return into("r_pow", [self.rexpr(args[0]), self.rexpr(args[1])])
        if name == "val":
            if len(args) != 1:
                self.err("val : un argument (texte) attendu", line)
            return into("r_set", [self.iexpr(args[0])])
        self.err("fonction réelle inconnue : %s" % name, line)

    def args(self, name, args):
        """Arguments d'une fonction Quick C : un réel par valeur passe par adresse."""
        ptypes = self.funcs[name][1]
        if len(args) != len(ptypes) and "other" not in ptypes[-1:]:
            self.err("%s : %d argument(s) attendu(s)" % (name, len(ptypes)))
        out = []
        for k, a in enumerate(args):
            pt = ptypes[k] if k < len(ptypes) else "other"
            out.append(self.rexpr(a) if pt == "real" else self.iexpr(a))
        return out

    def bexpr(self, n):
        """Condition : un réel est vrai s'il n'est pas nul."""
        if n.t == "real":
            return "(r_cmp(%s, %s) != 0)" % (self.rexpr(n), self.const("0"))
        return self.iexpr(n)

    def vexpr(self, n):
        """Expression évaluée pour ses effets (gauche d'une virgule)."""
        return self.rexpr(n) if n.t == "real" else self.iexpr(n)

    def iexpr(self, n):
        """Texte C d'une expression non réelle, ses parties réelles réécrites."""
        if not self.needs(n):
            return self.orig(n)
        k = n.k
        line = self.code[n.s].line
        if n.t == "real":                                  # réel -> entier : tronqué
            return "r_toint(%s)" % self.rexpr(n)
        if k == "paren":
            return "(%s)" % self.iexpr(n.a)
        if k == "bin":
            op, a, b = n.a
            if "real" in (a.t, b.t):
                if op in ("&&", "||"):
                    return "(%s %s %s)" % (self.bexpr(a), op, self.bexpr(b))
                return "(r_cmp(%s, %s) %s 0)" % (self.rexpr(a), self.rexpr(b), op)
            return "%s %s %s" % (self.iexpr(a), op, self.iexpr(b))
        if k == "unary":
            op, x = n.a
            if op == "!" and x.t == "real":
                return "(r_cmp(%s, %s) == 0)" % (self.rexpr(x), self.const("0"))
            if op == "&" and x.t == "real":
                lv = self.lvalue(x)
                if lv is None:
                    self.err("& d'un réel calculé", line)
                return "&(%s)" % lv
            return "%s%s" % (op, self.iexpr(x))
        if k == "cast":
            words, x = n.a
            inner = self.iexpr(x) if x.t != "real" else "r_toint(%s)" % self.rexpr(x)
            return "(%s)%s" % (" ".join(words), inner)
        if k == "assign":
            op, l, r = n.a
            if r.t == "real":                              # n = x : tronqué
                return "%s = r_toint(%s)" % (self.iexpr(l), self.rexpr(r))
            return "%s %s %s" % (self.iexpr(l), op, self.iexpr(r))
        if k == "cond":
            c, a, b = n.a
            return "(%s ? %s : %s)" % (self.bexpr(c), self.iexpr(a), self.iexpr(b))
        if k == "comma":
            return "(%s, %s)" % (self.vexpr(n.a[0]), self.iexpr(n.a[1]))
        if k == "index":
            return "%s[%s]" % (self.iexpr(n.a[0]), self.iexpr(n.a[1]))
        if k in ("preinc", "postinc"):
            op, x = n.a
            return op + self.iexpr(x) if k == "preinc" else self.iexpr(x) + op
        if k == "member":
            op, x = n.a
            return "%s%s%s" % (self.iexpr(x), op, self.code[n.e - 1].text)
        if k == "call":
            f, args = n.a
            name = f.a if f.k == "id" else None
            if name in ("str", "fmt") and self.lookup(name) is None:
                if name == "str":
                    if len(args) != 1:
                        self.err("str : un argument attendu", line)
                    return "r_s(%s)" % self.rexpr(args[0])
                if len(args) != 3:
                    self.err("fmt(x, chiffres, décimales) : trois arguments attendus", line)
                return "r_f(%s, %s, %s)" % (self.rexpr(args[0]), self.iexpr(args[1]),
                                            self.iexpr(args[2]))
            if name in self.funcs and self.lookup(name) == "func":
                return "%s(%s)" % (name, ", ".join(self.args(name, args)))
            for a in args:
                if a.t == "real":
                    self.err("réel passé à %s : écrivez str(x) pour l'afficher"
                             % (name or "une fonction"), line)
            return "%s(%s)" % (self.iexpr(f), ", ".join(self.iexpr(a) for a in args))
        return self.orig(n)


def translate(text, filename="programme.qc"):
    """Quick C -> C pour SDCC.  filename : chemin du .qc, mis dans #line (SDCC y
    relit les lignes pour son listing).  QCError(message, ligne) en cas d'erreur."""
    return Translator(text, filename.replace("\\", "/")).translate()
