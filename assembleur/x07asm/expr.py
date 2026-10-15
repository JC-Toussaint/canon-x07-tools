"""Évaluateur d'expressions de l'assembleur.

Nombres :  123   $1C00   &H1C00   0x1C00   1C00H   %1010   &B1010   1010B
           'A' (code ASCII)   $ seul = adresse courante
Opérateurs (priorité croissante) :
           |   ^   &   << >>   + -   * / MOD %   unaires - + ~ NOT
Fonctions : HIGH(x)  LOW(x)
"""


class ExprError(Exception):
    pass


class Undefined(ExprError):
    def __init__(self, name):
        super().__init__("symbole non défini : %s" % name)
        self.name = name


_SYM0 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_.@?")
_SYM = _SYM0 | set("0123456789")
_HEX = set("0123456789ABCDEFabcdef")


def evaluate(text, lookup, pc=0):
    """`lookup(nom)` renvoie la valeur du symbole ou lève Undefined."""
    p = _Parser(text, lookup, pc)
    v = p.expr()
    p.ws()
    if p.i < len(p.s):
        raise ExprError("expression incorrecte : %r" % text)
    return v


class _Parser:
    def __init__(self, s, lookup, pc):
        self.s, self.i, self.lookup, self.pc = s, 0, lookup, pc

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def peek(self, n=1):
        self.ws()
        return self.s[self.i:self.i + n]

    def word(self):
        """Mot-clé alphabétique à la position courante (sans le consommer)."""
        self.ws()
        j = self.i
        while j < len(self.s) and self.s[j].isalpha():
            j += 1
        return self.s[self.i:j].upper()

    def take(self, tok):
        if self.peek(len(tok)) == tok:
            self.i += len(tok)
            return True
        return False

    def expr(self):
        v = self.xor()
        while True:
            if self.peek(2) != "||" and self.take("|"):
                v |= self.xor()
            elif self.word() == "OR":
                self.i += 2
                v |= self.xor()
            else:
                return v

    def xor(self):
        v = self.and_()
        while True:
            if self.take("^"):
                v ^= self.and_()
            elif self.word() == "XOR":
                self.i += 3
                v ^= self.and_()
            else:
                return v

    def and_(self):
        v = self.shift()
        while True:
            if self.take("&"):
                v &= self.shift()
            elif self.word() == "AND":
                self.i += 3
                v &= self.shift()
            else:
                return v

    def shift(self):
        v = self.add()
        while True:
            if self.take("<<"):
                v <<= self.add()
            elif self.take(">>"):
                v >>= self.add()
            else:
                return v

    def add(self):
        v = self.mul()
        while True:
            if self.take("+"):
                v += self.mul()
            elif self.take("-"):
                v -= self.mul()
            else:
                return v

    def mul(self):
        v = self.unary()
        while True:
            if self.take("*"):
                v *= self.unary()
            elif self.take("/"):
                d = self.unary()
                if d == 0:
                    raise ExprError("division par zéro")
                v = int(v / d)
            elif self.take("%") or (self.word() == "MOD" and self._skip(3)):
                d = self.unary()
                if d == 0:
                    raise ExprError("division par zéro")
                v %= d
            else:
                return v

    def _skip(self, n):
        self.i += n
        return True

    def unary(self):
        if self.take("-"):
            return -self.unary()
        if self.take("+"):
            return self.unary()
        if self.take("~"):
            return ~self.unary()
        if self.word() == "NOT":
            self.i += 3
            return ~self.unary()
        return self.primary()

    def primary(self):
        self.ws()
        s, i = self.s, self.i
        if i >= len(s):
            raise ExprError("expression incomplète")
        c = s[i]
        if c == "(":
            self.i += 1
            v = self.expr()
            if not self.take(")"):
                raise ExprError("parenthèse fermante manquante")
            return v
        if c == "'":
            if i + 2 < len(s) and s[i + 2] == "'":
                self.i += 3
                return ord(s[i + 1])
            raise ExprError("caractère incorrect")
        if c == "$":
            j = i + 1
            while j < len(s) and s[j] in _HEX:
                j += 1
            self.i = j
            return int(s[i + 1:j], 16) if j > i + 1 else self.pc
        if c == "&" and i + 1 < len(s) and s[i + 1] in "HhBbOo":
            base = {"H": 16, "B": 2, "O": 8}[s[i + 1].upper()]
            j = i + 2
            while j < len(s) and s[j] in _HEX:
                j += 1
            try:
                v = int(s[i + 2:j], base)
            except ValueError:
                raise ExprError("nombre incorrect : %s" % s[i:j])
            self.i = j
            return v
        if c == "%" and i + 1 < len(s) and s[i + 1] in "01":
            j = i + 1
            while j < len(s) and s[j] in "01":
                j += 1
            self.i = j
            return int(s[i + 1:j], 2)
        if c.isdigit():
            j = i
            while j < len(s) and (s[j].isalnum()):
                j += 1
            tok = s[i:j].upper()
            self.i = j
            try:
                if tok.startswith("0X"):
                    return int(tok[2:], 16)
                if tok.endswith("H"):
                    return int(tok[:-1], 16)
                if tok.endswith("B") and set(tok[:-1]) <= set("01"):
                    return int(tok[:-1], 2)
                return int(tok, 10)
            except ValueError:
                raise ExprError("nombre incorrect : %s" % tok)
        if c in _SYM0:
            j = i
            while j < len(s) and s[j] in _SYM:
                j += 1
            name = s[i:j].upper()
            self.i = j
            if name in ("HIGH", "LOW") and self.peek() == "(":
                v = self.primary()
                return (v >> 8) & 0xFF if name == "HIGH" else v & 0xFF
            return self.lookup(name)
        raise ExprError("caractère inattendu : %r" % c)
