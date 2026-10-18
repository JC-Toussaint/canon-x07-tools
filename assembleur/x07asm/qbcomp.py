"""Compilation directe d'un programme QuickBASIC en assembleur Z80 pour le X-07.

Sans passer par le BASIC du X-07 : le programme QuickBASIC, analysé par
qbasic.Parser, est traduit en instructions internes du compilateur
(basic.Compiler), dont le générateur de code est réutilisé tel quel.

Ce que cela permet, par rapport à la traduction en BASIC (qbasic.py) :
  - noms longs, sans mot-clé interdit ni limite à 2 caractères ;
  - SUB et FUNCTION appelées par CALL / RET ;
  - récursivité : une procédure récursive empile ses variables locales à
    l'entrée et les dépile à la sortie (les variables gardent une adresse
    fixe, le générateur de code existant sert tel quel) ;
  - tableaux passés en paramètre par adresse : l'appelant transmet
    l'adresse d'un descripteur (adresse du tableau, dimensions), chargée
    dans un registre à chaque accès ; une seule copie de la procédure.

Passage des paramètres : l'appelant range les arguments dans des cases
propres à la procédure (ARG), la procédure les recopie dans ses paramètres
à l'entrée ; à la sortie elle range les paramètres dans des cases OUT, que
l'appelant recopie dans les variables passées (passage par référence de
QuickBASIC).  Les cases ARG et OUT ne sont jamais empilées : la récursivité
reste exacte.
"""
import re

from . import basic
from .basic import CompileError
from .qbasic import (FILE_SIZE, FILE_SPACE, FUNCTIONS, NOT_ON_X07, REL, Parser, QBError, base,
                     check_argument, num_literal, ram_file_name, tokenize)

SUFFIX = {"i": "%", "s": "!", "d": "#", "$": "$"}
SIZE = {"i": 2, "s": 4, "d": 8}

# fonctions que le compilateur connaît sous le même nom
SAME = {"ABS", "SGN", "INT", "FIX", "CSNG", "CDBL", "SQR", "LOG", "EXP", "SIN", "COS", "TAN",
        "ATN", "PEEK", "INP", "LEN", "ASC", "VAL", "POINT", "STICK", "STRIG", "CHR$", "STR$",
        "HEX$", "LEFT$", "RIGHT$", "MID$", "STRING$", "INKEY$"}
NOT_COMPILED = {
    "INSTR": "INSTR n'est pas géré par le compilateur",
    "TIMER": "TIMER : le compilateur n'a pas accès à l'horloge (TIME$)",
    "TIME$": "TIME$ n'est pas géré par le compilateur",
    "DATE$": "DATE$ n'est pas géré par le compilateur",
    "ERR": "ERR : ON ERROR n'est pas géré par le compilateur",
    "ERL": "ERL : ON ERROR n'est pas géré par le compilateur",
}


def ident(name):
    """Partie d'étiquette assembleur sûre."""
    return re.sub(r"[^A-Z0-9]", "_", name.upper())


class Proc:
    def __init__(self, key, p):
        self.key, self.p = key, p
        self.kind = p["kind"]
        self.label = "QP_" + ident(key)
        self.exit = self.label + "_X"
        self.params = []          # (nom QB, tableau ?, nom compilateur)
        self.arg = []             # case ARG de chaque paramètre (nom compilateur)
        self.out = []             # case OUT (paramètres simples)
        self.result = None        # variable du résultat (FUNCTION), locale
        self.result_out = None    # case où l'appelant lit le résultat
        self.locals = []          # noms compilateur des variables locales (empilées)
        self.arrays = set()       # paramètres tableau (nom QB de base)
        self.recursive = False
        self.static = p["static"]


class Scope:
    def __init__(self, proc=None):
        self.proc = proc
        self.vars = {}            # (base, type, tableau ?) -> nom compilateur
        self.declared = {}
        self.shared = set()
        self.statics = set()


class Lowering:
    """Programme QuickBASIC -> éléments pour QBCompiler :
    ('label', nom) ou ('stmt', instruction du compilateur, ligne QuickBASIC)."""

    def __init__(self, text):
        self.warnings = []
        self.source = text.split("\n")            # pour le listing : ligne -> texte
        toks = tokenize(text)
        funcs, subs = set(), set()
        for k, t in enumerate(toks[:-1]):
            if t.kind == "kw" and t.val in ("FUNCTION", "SUB") and toks[k + 1].kind in ("id", "kw"):
                prev = toks[k - 1] if k else None
                if prev is None or prev.kind == "eol" or prev.val in ("DECLARE", "STATIC"):
                    (funcs if t.val == "FUNCTION" else subs).add(base(toks[k + 1].val))
        parser = Parser(toks, funcs)
        parser.subs = subs
        parser.track_lines = True                  # ligne QuickBASIC de chaque instruction
        self.main, procs = parser.program()
        self.procs = {}
        for p in procs:
            key = p["name"] if p["kind"] == "SUB" else base(p["name"])
            self.procs[key] = Proc(key, p)
        self.deftype = {c: "s" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
        self.consts = {}
        self.items = []
        self.n_temp = 0
        self.n_label = 0
        self.global_scope = Scope()
        self.scope = self.global_scope
        self.global_shared = set()
        self.deffns = {}
        self.data_lines = []      # lignes des DATA, dans l'ordre
        self.labels_at = {}       # étiquette utilisateur -> position (pour RESTORE)
        self.line = 0

    # -------------------------------------------------- sortie
    def warn(self, msg):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def err(self, msg):
        raise QBError("ligne %d : %s" % (self.line, msg) if self.line else msg)

    def new_label(self):
        self.n_label += 1
        return "QG_%d" % self.n_label

    def user_label(self, name):
        return "QU_" + ident(name)

    def place(self, lab):
        self.items.append(("label", lab))

    def emit(self, stmt):
        self.items.append(("stmt", stmt, self.line))

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
            self.warn("LONG remplacé par la double précision (pas d'entiers 32 bits)")
            t = "d"
        return t

    def cvar(self, name, is_arr=False, scope=None):
        """Nom compilateur (avec suffixe de type) de la variable QuickBASIC."""
        scope = scope or self.scope
        b = base(name)
        t = self.type_of(name if name[-1] in "%!#$&" else b, scope)
        if scope is not self.global_scope and (b in scope.shared or b in self.global_shared):
            scope = self.global_scope
        key = (b, t, is_arr)
        if key not in scope.vars:
            prefix = "" if scope.proc is None else ident(scope.proc.key) + "__"
            n = prefix + ident(b) + ("__A" if is_arr else "") + SUFFIX[t]
            scope.vars[key] = n
            if scope.proc is not None and not is_arr and b not in scope.statics:
                scope.proc.locals.append(n)
        return scope.vars[key]

    def temp(self, t):
        self.n_temp += 1
        n = "QT_%d%s" % (self.n_temp, SUFFIX[t])
        if self.scope.proc is not None:            # empilé si la procédure est récursive
            self.scope.proc.locals.append(n)
        return n

    def is_param_array(self, name):
        p = self.scope.proc
        return p is not None and base(name) in p.arrays

    # -------------------------------------------------- types
    def etype(self, e):
        k = e[0]
        if k == "num":
            return e[2]
        if k == "str":
            return "$"
        if k == "paren":
            return self.etype(e[1])
        if k in ("var", "idx"):
            if k == "var" and base(e[1]) in self.consts:
                return self.etype(self.consts[base(e[1])])
            return self.type_of(e[1])
        if k == "ufn":
            return self.type_of(self.procs[e[1]].p["name"], self.global_scope)
        if k == "fn":
            return self.type_of(e[1])
        if k == "call":
            r = FUNCTIONS[e[1]][1]
            return self.etype(e[2][0]) if r == "=" else r
        if k == "un":
            return "i" if e[1] == "NOT" else self.etype(e[2])
        if k == "bin":
            op = e[1]
            if op in REL or op in ("AND", "OR", "XOR", "EQV", "IMP", "\\", "MOD"):
                return "i"
            a, b = self.etype(e[2]), self.etype(e[3])
            if a == "$":
                return "$"
            if op in ("/", "^"):
                return "d" if "d" in (a, b) else "s"
            order = "isd"
            return order[max(order.index(a), order.index(b))]
        if k == "c":                                     # déjà traduit
            return e[2]
        raise QBError("expression inconnue %r" % (e,))

    def integral(self, e):
        k = e[0]
        if k == "num":
            return not re.search(r"[.ED]", e[1].rstrip("#")) or e[1].startswith("&")
        if k == "paren":
            return self.integral(e[1])
        if k == "call":
            return e[1] in ("INT", "FIX", "CINT", "SGN", "LEN", "ASC", "PEEK", "INP",
                            "POINT", "POS", "CSRLIN")
        if k == "un":
            return self.integral(e[2]) or e[1] == "NOT"
        if k == "bin":
            if e[1] in ("+", "-", "*"):
                return self.integral(e[2]) and self.integral(e[3])
            return e[1] not in ("/", "^")
        return self.etype(e) == "i"

    def rounded(self, e, t):
        """QuickBASIC arrondit quand un nombre non entier va dans un entier."""
        if t == "i" and self.etype(e) in ("s", "d") and not self.integral(e):
            return ("call", "INT", [("bin", "+", e, ("num", ".5", "s"))])
        return e

    def const_value(self, e):
        if e is None:
            return None
        if e[0] == "num" and not e[1].startswith("&"):
            try:
                return float(e[1].rstrip("#").replace("D", "E"))
            except ValueError:
                return None
        if e[0] == "num":
            return int(e[1][2:], 16 if e[1][1] == "H" else 8)
        if e[0] == "un" and e[1] == "-":
            v = self.const_value(e[2])
            return -v if v is not None else None
        if e[0] == "var" and base(e[1]) in self.consts:
            return self.const_value(self.consts[base(e[1])])
        if e[0] == "paren":
            return self.const_value(e[1])
        return None

    # -------------------------------------------------- expressions
    def hoist(self, e):
        """Exécute d'abord les appels de FUNCTION contenus dans e."""
        if not isinstance(e, tuple):
            return e
        k = e[0]
        if k == "ufn":
            proc = self.procs[e[1]]
            self.call_proc(proc, e[2])
            t = self.etype(e)
            tmp = self.temp(t)
            self.emit(("let", ("var", tmp), ("var", proc.result_out)))
            return ("c", ("var", tmp), t)
        if k in ("idx", "call", "fn"):
            return (k, e[1], [self.hoist(a) for a in e[2]])
        if k == "un":
            return ("un", e[1], self.hoist(e[2]))
        if k == "bin":
            return ("bin", e[1], self.hoist(e[2]), self.hoist(e[3]))
        if k == "paren":
            return ("paren", self.hoist(e[1]))
        return e

    def x(self, e):
        """Expression du compilateur (appels de FUNCTION déjà sortis)."""
        k = e[0]
        if k == "c":
            return e[1]
        if k == "num":
            text = e[1]
            if text.startswith("&"):
                v = int(text[2:], 16 if text[1] == "H" else 8)
                if v > 0xFFFF:
                    return ("flt", str(v))
                return ("int", v - 0x10000 if v > 0x7FFF else v)
            t = text.rstrip("#")
            if re.fullmatch(r"\d+", t) and int(t) <= 32767 and e[2] == "i":
                return ("int", int(t))
            return ("flt", text if e[2] != "d" or text.endswith("#") or "D" in text
                    else text + "#")
        if k == "str":
            return ("str", e[1])
        if k == "paren":
            return self.x(e[1])
        if k == "var":
            b = base(e[1])
            if b in self.consts:
                return self.x(self.consts[b])
            return ("var", self.cvar(e[1]))
        if k == "idx":
            return ("arr", self.cvar(e[1], True), [self.x(a) for a in e[2]])
        if k == "fn":
            if e[1] not in self.deffns:
                self.err("%s utilisée avant DEF %s" % (e[1], e[1]))
            return ("fn", self.deffns[e[1]], [self.x(a) for a in e[2]])
        if k == "un":
            return ("un", e[1], self.x(e[2]))
        if k == "bin":
            return ("bin", e[1], self.x(e[2]), self.x(e[3]))
        if k == "call":
            return self.x_call(e[1], e[2])
        raise QBError("expression non traduite %r" % (e,))

    def x_call(self, f, args):
        if f in NOT_ON_X07:
            self.err(NOT_ON_X07[f])
        if f in NOT_COMPILED:
            self.err(NOT_COMPILED[f])
        a = [self.x(v) for v in args]
        one = ("int", 1)
        if f == "EOF":                                  # fichiers en RAM : RT_FEOF
            self.check_channel(args[0])
            return ("call", "EOF", a)
        if f == "SPACE$":
            return ("call", "STRING$", [a[0], ("int", 32)])
        if f in ("CINT", "CLNG"):
            return ("call", "INT", [("bin", "+", a[0], ("flt", ".5"))])
        if f == "RND":
            return ("call", "RND", a or [one])
        if f == "POS":
            return ("bin", "+", ("call", "POS", [("int", 0)]), one)
        if f == "CSRLIN":
            return ("bin", "+", ("call", "CSRLIN", []), one)
        if f in ("TAB", "SPC"):
            self.err("%s s'emploie dans PRINT" % f)
        if f == "FRE":
            self.err("FRE n'est pas géré par le compilateur")
        if f not in SAME:
            self.err("fonction %s non gérée" % f)
        return ("call", f, a)

    def value(self, e, t=None):
        """Expression QuickBASIC -> expression du compilateur (avec arrondi vers t)."""
        e = self.hoist(e)
        if t is not None:
            e = self.rounded(e, t)
        return self.x(e)

    def target(self, tgt):
        tgt = self.hoist(tgt)
        if tgt[0] == "var":
            if base(tgt[1]) in self.consts:
                self.err("affectation de la constante %s" % tgt[1])
            return ("var", self.cvar(tgt[1]))
        return ("arr", self.cvar(tgt[1], True), [self.x(a) for a in tgt[2]])

    def assign(self, tgt, e):
        t = self.type_of(tgt[1])
        self.emit(("let", self.target(tgt), self.value(e, t)))

    # -------------------------------------------------- sauts
    def jump_if_false(self, cond, lab):
        c = self.x(self.hoist(cond))
        self.emit(("qjf", c, lab))

    def jump_if_true(self, cond, lab):
        c = self.x(self.hoist(cond))
        self.emit(("qjf", ("bin", "=", c, ("int", 0)), lab))

    # -------------------------------------------------- procédures
    def call_proc(self, proc, args):
        params = proc.p["params"]
        if len(args) != len(params):
            self.err("%s : %d paramètre(s) attendu(s), %d donné(s)"
                     % (proc.p["name"], len(params), len(args)))
        lets, back = [], []
        for (pname, is_arr, _), a, slot in zip(params, args, proc.arg):
            ptype = self.type_of(pname, proc.scope)
            if is_arr:
                if a[0] == "idx" and not a[2]:            # t() : tout le tableau
                    a = ("var", a[1])
                if a[0] != "var":
                    self.err("%s : tableau attendu pour %s" % (proc.p["name"], pname))
                self.check_arg(proc, pname, ptype, a, True)
                if self.is_param_array(a[1]):            # tableau reçu : on le transmet
                    lets.append(("let", ("var", slot), ("var", self.cvar(a[1]))))
                else:
                    lets.append(("let", ("var", slot), ("adesc", self.cvar(a[1], True))))
                continue
            self.check_arg(proc, pname, ptype, a, False)
            t = ptype
            lets.append(("let", ("var", slot), self.value(a, t)))
            if a[0] in ("var", "idx") and not (a[0] == "var" and base(a[1]) in self.consts):
                back.append(a)
        for s in lets:
            self.emit(s)
        self.emit(("qcall", proc.label))
        outs = [o for (pn, arr, _), o in zip(params, proc.out_all) if not arr]
        k = 0
        for (pname, is_arr, _), a in zip(params, args):
            if is_arr:
                continue
            o = outs[k]
            k += 1
            if a in back:                                  # passage par référence
                self.emit(("let", self.target(a), ("var", o)))

    def check_arg(self, proc, pname, ptype, a, is_arr):
        by_ref = a[0] in ("var", "idx") and not (a[0] == "var" and base(a[1]) in self.consts)
        atype = self.type_of(a[1]) if is_arr else self.etype(a)
        shown = a[1] + ("()" if is_arr else "") if a[0] in ("var", "idx") else "l'expression"
        try:
            check_argument(proc.p["name"], pname, ptype, shown, atype, by_ref, is_arr)
        except QBError as e:
            self.err(str(e))

    def prepare(self):
        for key, proc in self.procs.items():
            proc.scope = Scope(proc)
            self.scope = proc.scope
            for pname, is_arr, typ in proc.p["params"]:
                b = base(pname)
                if b in self.consts:
                    self.err("%s : le paramètre %s porte le nom d'une constante"
                             % (proc.p["name"], pname))
                if typ:
                    proc.scope.declared[b] = typ
                if is_arr:
                    proc.arrays.add(b)
                    # pointeur vers le descripteur du tableau reçu (entier)
                    ptr = ident(key) + "__" + ident(b) + "__P%"
                    proc.scope.vars[(b, self.type_of(pname), False)] = ptr
                    proc.locals.append(ptr)
                    proc.params.append((pname, True, ptr))
                else:
                    proc.params.append((pname, False, self.cvar(pname)))
            for s in proc.p["body"]:
                if s[0] == "shared":
                    for n, _, typ in s[1]:
                        proc.scope.shared.add(base(n))
                        if typ:
                            self.global_scope.declared[base(n)] = typ
                if s[0] == "static":
                    for n, _, typ in s[1]:
                        proc.scope.statics.add(base(n))
                        if typ:
                            proc.scope.declared[base(n)] = typ
                if s[0] == "dim":
                    for n, _, typ in s[2]:
                        if typ:
                            proc.scope.declared[base(n)] = typ
            tag = ident(key)
            proc.arg, proc.out_all = [], []
            for pname, is_arr, cname in proc.params:
                suf = "%" if is_arr else cname[-1]
                proc.arg.append("QA_%s_%d%s" % (tag, len(proc.arg), suf))
                proc.out_all.append("QO_%s_%d%s" % (tag, len(proc.out_all), suf))
            if proc.kind == "FUNCTION":
                t = self.type_of(proc.p["name"], self.global_scope)
                proc.result = tag + "__RESULTAT" + SUFFIX[t]
                proc.locals.append(proc.result)
                proc.result_out = "QR_%s%s" % (tag, SUFFIX[t])
            self.scope = self.global_scope
        # récursivité : procédures dans un cycle du graphe des appels
        graph = {k: self.calls_in(p.p["body"]) for k, p in self.procs.items()}
        for start in graph:
            seen, todo = set(), list(graph[start])
            while todo:
                n = todo.pop()
                if n == start:
                    self.procs[start].recursive = True
                    break
                if n in seen or n not in graph:
                    continue
                seen.add(n)
                todo += graph[n]

    def calls_in(self, node, out=None):
        out = set() if out is None else out
        if isinstance(node, tuple):
            if node and node[0] in ("callsub", "ufn"):
                out.add(node[1])
            for c in node[1:]:
                self.calls_in(c, out)
        elif isinstance(node, list):
            for c in node:
                self.calls_in(c, out)
        return out

    def gen_proc(self, proc):
        self.scope = proc.scope
        self.line = 0
        self.place(proc.label)
        self.emit(("qbegin", proc.key))
        for (pname, is_arr, cname), slot in zip(proc.params, proc.arg):
            self.emit(("let", ("var", cname), ("var", slot)))
        if not proc.static:
            for n in self.locals_to_zero(proc):
                self.emit(("let", ("var", n), ("str", "") if n.endswith("$") else ("int", 0)))
        ctx = {"proc": proc}
        self.gen_block(proc.p["body"], ctx)
        self.place(proc.exit)
        for (pname, is_arr, cname), o in zip(proc.params, proc.out_all):
            if not is_arr:
                self.emit(("let", ("var", o), ("var", cname)))
        if proc.result:
            self.emit(("let", ("var", proc.result_out), ("var", proc.result)))
        self.emit(("qend", proc.key))
        self.emit(("qret",))
        self.scope = self.global_scope

    def locals_to_zero(self, proc):
        names = []

        def walk(node):
            if isinstance(node, tuple) and node:
                if node[0] == "var" and isinstance(node[1], str):
                    b = base(node[1])
                    if b not in self.consts and b not in proc.scope.statics and \
                            b not in proc.scope.shared and b not in self.global_shared and \
                            b not in [base(p[0]) for p in proc.p["params"]] and \
                            b != base(proc.p["name"]):
                        n = self.cvar(node[1])
                        if n not in names:
                            names.append(n)
                if node[0] == "for":
                    walk(("var", node[1]))
                for c in node[1:]:
                    walk(c)
            elif isinstance(node, list):
                for c in node:
                    walk(c)
        walk(proc.p["body"])
        if proc.result:
            names.append(proc.result)
        return names

    # -------------------------------------------------- programme
    def lower(self):
        for s in self.main:
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
        self.prepare()
        if self.uses_files():
            # zone des fichiers : FSET seulement si elle est trop petite (comme la traduction)
            zone = ("bin", "-", ("bin", "+", self.peek(0x212), ("bin", "*", ("int", 256),
                                                                 self.peek(0x213))),
                    ("bin", "+", self.peek(0x210), ("bin", "*", ("int", 256), self.peek(0x211))))
            skip = self.new_label()
            self.emit(("qjf", ("bin", "<", zone, ("int", self.file_space - 13)), skip))
            self.emit(("fset", ("int", self.file_space)))
            self.place(skip)
        self.gen_block(self.main, {})
        self.emit(("end",))
        for proc in self.procs.values():
            self.gen_proc(proc)
        return self.items

    def apply_deftype(self, s):
        _, typ, ranges = s
        for a, b in ranges:
            for c in range(ord(a[0]), ord(b[0]) + 1):
                self.deftype[chr(c)] = typ

    def gen_block(self, stmts, ctx):
        for s in stmts:
            self.line = getattr(s, "line", self.line)
            getattr(self, "g_" + s[0])(s, ctx)

    # -------------------------------------------------- instructions
    def g_label(self, s, ctx):
        self.place(self.user_label(s[1]))
        self.labels_at[s[1]] = len(self.data_lines)

    def g_let(self, s, ctx):
        tgt, e = s[1], s[2]
        proc = ctx.get("proc")
        if tgt[0] == "var" and proc and proc.kind == "FUNCTION" and \
                base(tgt[1]) == base(proc.p["name"]):
            t = self.type_of(proc.p["name"], self.global_scope)
            self.emit(("let", ("var", proc.result), self.value(e, t)))
            return
        self.assign(tgt, e)

    def g_print(self, s, ctx):
        items, nl = self.print_items(s[1])
        self.emit(("print", items, nl))

    def g_using(self, s, ctx):
        self.err("PRINT USING n'est pas géré par le compilateur")

    # -------------------------------------------------- fichiers en RAM (FICHIERS.md)
    file_space, file_size = FILE_SPACE, FILE_SIZE

    @staticmethod
    def peek(a):
        return ("call", "PEEK", [("int", a)])

    def uses_files(self):
        kinds = ("open", "kill", "fprint", "finput", "flineinput")

        def walk(node):
            if isinstance(node, tuple) and node:
                if node[0] in kinds or (node[0] == "write" and node[1] is not None) or \
                        (node[0] == "call" and node[1] == "EOF"):
                    return True
                return any(walk(c) for c in node[1:])
            if isinstance(node, list):
                return any(walk(c) for c in node)
            return False
        return walk(self.main) or any(walk(p.p["body"]) for p in self.procs.values())

    def check_channel(self, ch):
        v = self.const_value(ch)
        if v is not None and not 1 <= v <= 5:
            self.err("fichier #%d : le X-07 n'a que les canaux 1 à 5" % v)

    def chan(self, ch):
        self.check_channel(ch)
        return self.value(ch, "i")

    def file_name(self, e):
        if e[0] == "str":
            name, note = ram_file_name(e[1])
            if note:
                self.warn(note)
            return name, ("str", "RAM:" + name)
        self.warn("nom de fichier calculé : 6 caractères au plus sur le X-07")
        v = self.value(e)
        return None, ("bin", "+", ("str", "RAM:"), v)

    def g_open(self, s, ctx):
        _, name, mode, ch, size = s
        c = self.chan(ch)
        _, full = self.file_name(name)
        if mode == "INPUT":
            self.emit(("finit", c, full, None))
            return
        n = self.value(size, "i") if size is not None else ("int", self.file_size)
        self.emit(("finit", c, full, n))
        self.emit(("rtcall", "RT_FZERO" if mode == "OUTPUT" else "RT_FAPP", c))

    def g_close(self, s, ctx):
        pass                                            # rien à fermer sur le X-07

    def g_kill(self, s, ctx):
        short, full = self.file_name(s[1])
        self.emit(("fdel", ("str", short) if short else self.value(s[1])))

    def print_items(self, raw):
        items = []
        for i in raw:
            if i == ";":
                items.append(("sep", ";"))
            elif i == ",":
                items.append(("sep", ","))
            elif i[0] == "call" and i[1] == "TAB":
                items.append(("tab", self.value(("bin", "-", i[2][0], ("num", "1", "i")))))
            elif i[0] == "call" and i[1] == "SPC":
                items.append(("spc", self.value(i[2][0])))
            else:
                if items and items[-1][0] != "sep":
                    items.append(("sep", ";"))
                items.append(("expr", self.value(i)))
        return items, not items or items[-1][0] != "sep"

    def g_fprint(self, s, ctx):
        c = self.chan(s[1])
        items, nl = self.print_items(s[2])
        self.emit(("fprint", c, items, nl))

    def g_write(self, s, ctx):
        """WRITE : valeurs séparées par des virgules, chaînes entre guillemets."""
        _, ch, raw = s
        quote = ("expr", ("call", "CHR$", [("int", 34)]))
        items = []
        for k, i in enumerate(raw):
            if k:
                items += [("sep", ";"), ("expr", ("str", ",")), ("sep", ";")]
            v = self.value(i)
            if self.etype(i) == "$":
                items += [quote, ("sep", ";"), ("expr", v), ("sep", ";"), quote]
            else:
                items.append(("expr", v))
        if ch is None:
            self.emit(("print", items, True))
        else:
            self.emit(("fprint", self.chan(ch), items, True))

    def g_finput(self, s, ctx):
        c = self.chan(s[1])
        self.emit(("finput", c, [self.target(t) for t in s[2]]))

    def g_flineinput(self, s, ctx):
        c = self.chan(s[1])
        self.emit(("flineinput", c, self.target(s[2])))

    def g_input(self, s, ctx):
        _, prompt, comma, tg = s
        self.emit(("input", prompt, not comma, [self.target(t) for t in tg]))

    def g_lineinput(self, s, ctx):
        self.emit(("lineinput", s[1], self.target(s[2])))

    def g_if(self, s, ctx):
        _, arms, other = s
        end = self.new_label()
        for k, (cond, body) in enumerate(arms):
            nxt = self.new_label()
            self.jump_if_false(cond, nxt)
            self.gen_block(body, ctx)
            if other is not None or k < len(arms) - 1:
                self.emit(("qjump", end, False))
            self.place(nxt)
        if other is not None:
            self.gen_block(other, ctx)
        self.place(end)

    def g_goto(self, s, ctx):
        self.emit(("qjump", self.user_label(s[1]), True))

    def g_gosub(self, s, ctx):
        self.emit(("qcall", self.user_label(s[1])))

    def g_return(self, s, ctx):
        self.emit(("qret",))

    def g_on(self, s, ctx):
        _, e, kind, labels = s
        t = self.temp("i")
        self.emit(("let", ("var", t), self.value(e, "i")))
        after = self.new_label()
        for k, lab in enumerate(labels, 1):
            nxt = self.new_label()
            self.emit(("qjf", ("bin", "=", ("var", t), ("int", k)), nxt))
            if kind == "GOTO":
                self.emit(("qjump", self.user_label(lab), True))
            else:
                self.emit(("qcall", self.user_label(lab)))
                self.emit(("qjump", after, False))
            self.place(nxt)
        self.place(after)

    def g_onerror(self, s, ctx):
        self.err("ON ERROR n'est pas géré par le compilateur")

    def g_resume(self, s, ctx):
        self.err("RESUME n'est pas géré par le compilateur")

    def g_raw(self, s, ctx):
        word = s[1].split()[0]
        if word == "CLS":
            self.emit(("cls",))
        elif word == "STOP":
            self.emit(("end",))
        else:
            self.err("%s n'est pas géré par le compilateur" % s[1])

    def g_rawe(self, s, ctx):
        self.err("%s n'est pas géré par le compilateur" % s[1].strip())

    def g_warn(self, s, ctx):
        self.warn(s[1])

    def g_beep(self, s, ctx):
        _, note, dur, warn = s
        if warn:
            self.warn(warn)
        self.emit(("beep", self.value(note), self.value(dur)))

    def g_end(self, s, ctx):
        self.emit(("end",))

    def g_for(self, s, ctx):
        _, var, a, b, step, body = s
        self.for_loop(var, a, b, step, lambda inner: self.gen_block(body, inner), ctx)

    def for_loop(self, var, a, b, step, body_fn, ctx):
        """FOR du compilateur, avec la garde de QuickBASIC (pas d'exécution
        d'une boucle vide ; le X-07 l'exécuterait une fois)."""
        t = self.type_of(var)
        v = self.cvar(var)
        av, bv = self.const_value(a), self.const_value(b)
        sv = self.const_value(step) if step is not None else 1
        a_x = self.value(a, t)
        b_x = self.value(b)
        if b_x[0] not in ("int", "flt", "var"):
            tb = self.temp("i" if t == "i" else "d")
            self.emit(("let", ("var", tb), b_x))
            b_x = ("var", tb)
        s_x = ("int", 1)
        if step is not None:
            s_x = self.value(step)
            if s_x[0] not in ("int", "flt", "var"):
                ts = self.temp("i" if t == "i" else "d")
                self.emit(("let", ("var", ts), s_x))
                s_x = ("var", ts)
        after = self.new_label()
        if av is not None and bv is not None and sv is not None:
            if (sv > 0 and av > bv) or (sv < 0 and av < bv):
                self.emit(("let", ("var", v), a_x))         # boucle vide
                return
            need = False
        else:
            need = True
        if need:
            if sv is None:
                cond = ("bin", ">", ("bin", "*", ("call", "SGN", [s_x]),
                                     ("bin", "-", a_x, b_x)), ("int", 0))
            elif sv >= 0:
                cond = ("bin", ">", a_x, b_x)
            else:
                cond = ("bin", "<", a_x, b_x)
            self.emit(("qjf", ("bin", "=", cond, ("int", 0)), after))
        self.emit(("for", v, a_x, b_x, s_x))
        inner = dict(ctx)
        inner["for"] = after
        body_fn(inner)
        self.emit(("next", [v]))
        self.place(after)

    def g_do(self, s, ctx):
        _, pre, body, post = s
        top, end = self.new_label(), self.new_label()
        self.place(top)
        if pre:
            w, c = pre
            (self.jump_if_false if w == "WHILE" else self.jump_if_true)(c, end)
        inner = dict(ctx)
        inner["do"] = end
        self.gen_block(body, inner)
        if post:
            w, c = post
            self.emit(("qbrk",))                            # BREAK reste actif
            (self.jump_if_true if w == "WHILE" else self.jump_if_false)(c, top)
        else:
            self.emit(("qjump", top, True))
        self.place(end)

    def g_exit(self, s, ctx):
        w = s[1]
        if w == "DO":
            if "do" not in ctx:
                self.err("EXIT DO hors d'une boucle DO")
            self.emit(("qjump", ctx["do"], False))
        elif w == "FOR":
            if "for" not in ctx:
                self.err("EXIT FOR hors d'une boucle FOR")
            self.emit(("qjump", ctx["for"], False))
        else:
            if "proc" not in ctx:
                self.err("EXIT %s hors d'une procédure" % w)
            self.emit(("qjump", ctx["proc"].exit, False))

    def g_select(self, s, ctx):
        _, sel, cases, other = s
        t = self.etype(sel)
        tmp = self.temp(t)
        self.emit(("let", ("var", tmp), self.value(sel)))
        tv = ("c", ("var", tmp), t)
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
            self.jump_if_false(c, nxt)
            self.gen_block(body, ctx)
            self.emit(("qjump", end, False))
            self.place(nxt)
        if other:
            self.gen_block(other, ctx)
        self.place(end)

    def g_dim(self, s, ctx):
        _, shared, decls = s
        for name, dims, typ in decls:
            if typ:
                self.scope.declared[base(name)] = typ
            if dims is None:
                continue
            sizes = []
            for lo, hi in dims:
                if lo is not None and self.const_value(lo) not in (0, 1):
                    self.err("DIM %s(... TO ...) : indices de 0 à n seulement" % name)
                v = self.const_value(hi)
                if v is None:
                    self.err("DIM %s : dimensions constantes seulement (compilateur)" % name)
                sizes.append(int(v))
            cname = self.cvar(name, True)
            self.emit(("dim", [(cname, sizes)]))
            if "proc" in ctx and not ctx["proc"].static and \
                    base(name) not in self.scope.statics:
                if ctx["proc"].recursive:
                    self.warn("tableau local d'une procédure récursive : partagé par "
                              "tous les appels")
                self.emit(("qzero", cname))                 # QuickBASIC : remis à zéro

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
        t = self.type_of(name)
        if t == "$":
            self.err("DEF FN chaîne non gérée par le compilateur")
        cname = "FN_" + ident(base(name)[2:]) + SUFFIX[t]
        self.deffns[name] = cname
        ps = []
        for p in params:
            if self.type_of(p) == "$":
                self.err("DEF FN : paramètres numériques seulement")
            ps.append("FNP_" + ident(base(name)) + "_" + ident(base(p)) + SUFFIX[self.type_of(p)])
        saved = dict(self.scope.vars)
        for p, cp in zip(params, ps):
            self.scope.vars[(base(p), self.type_of(p), False)] = cp
        body = self.x(self.hoist(e))
        self.scope.vars = saved
        self.emit(("deffn", cname, ps, body))

    def g_data(self, s, ctx):
        self.data_lines.append(self.line)
        self.emit(("data", [d.strip('"') if d.startswith('"') else d for d in s[1]]))

    def g_read(self, s, ctx):
        self.emit(("read", [self.target(t) for t in s[1]]))

    def g_restore(self, s, ctx):
        self.emit(("restore", None if s[1] is None else ("qlabel", s[1])))

    def g_locate(self, s, ctx):
        _, row, col = s
        if row is None or col is None:
            self.err("LOCATE : ligne et colonne obligatoires (compilateur)")
        self.emit(("locate", self.value(("bin", "-", col, ("num", "1", "i"))),
                   self.value(("bin", "-", row, ("num", "1", "i")))))

    def g_pset(self, s, ctx):
        _, (x, y), c, word = s
        code = 0x12 if word == "PRESET" or (c is not None and self.const_value(c) == 0) else 0x11
        if c is not None and self.const_value(c) is None:
            self.err("PSET : couleur constante seulement (compilateur)")
        self.emit(("t6", code, [self.value(x), self.value(y)]))

    def g_line(self, s, ctx):
        _, (x1, y1), (x2, y2), color, box = s
        x1, y1, x2, y2 = (self.value(v) for v in (x1, y1, x2, y2))
        if box is None:
            self.emit(("t6", 0x14, [x1, y1, x2, y2]))
        elif box == "B":
            for a, b, c, d in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2),
                               (x1, y2, x1, y1)):
                self.emit(("t6", 0x14, [a, b, c, d]))
        else:
            t = self.temp("i")
            self.emit(("for", t, y1, y2, ("int", 1)))
            self.emit(("t6", 0x14, [x1, ("var", t), x2, ("var", t)]))
            self.emit(("next", [t]))

    def g_circle(self, s, ctx):
        _, (x, y), r = s
        self.emit(("t6", 0x15, [self.value(x), self.value(y), self.value(r)]))

    def g_swap(self, s, ctx):
        t = self.type_of(s[1][1])
        tmp = self.temp(t)
        a, b = self.target(s[1]), self.target(s[2])
        self.emit(("let", ("var", tmp), a))
        self.emit(("let", a, b))
        self.emit(("let", b, ("var", tmp)))

    def g_randomize(self, s, ctx):
        tmp = self.temp("s")
        self.emit(("let", ("var", tmp), ("call", "RND", [("un", "-", self.value(s[1]))])))

    def g_sleep(self, s, ctx):
        lab = self.new_label()
        self.place(lab)
        self.emit(("qjf", ("bin", "<>", ("call", "INKEY$", []), ("str", "")), lab))

    def g_poke(self, s, ctx):
        self.emit(("poke" if s[1] == "POKE" else "out", self.value(s[2]), self.value(s[3])))

    def g_erase(self, s, ctx):
        for n in s[1]:
            self.emit(("qzero", self.cvar(n, True)))

    def g_callsub(self, s, ctx):
        if s[1] not in self.procs:
            self.err("SUB %s inconnue" % s[1])
        self.call_proc(self.procs[s[1]], s[2])


class QBCompiler(basic.Compiler):
    """Le compilateur BASIC, avec les instructions de la compilation directe :
    étiquettes, sauts, appels, procédures récursives, tableaux par adresse."""

    def compile_items(self, items, lowering, name="PROG", org=0x1000):
        self.ty = basic.Types("f")
        self.lw = lowering
        self.lines = []
        for it in items:
            if it[0] == "stmt":
                self.lines.append((None, [it[1]], "", it[2]))
        self.code = []
        self.lits, self.flits, self.vars, self.arrays = {}, {}, {}, {}
        self.temps, self.used = set(), set()
        self.tables, self.fors, self.whiles = [], [], []
        self.nlab, self.fns, self.fnparams, self.tmpbase = 0, {}, {}, 0
        self.linenums = []
        self.descs = {}
        self.param_ptr = {}                     # tableau paramètre -> pointeur
        for proc in lowering.procs.values():
            for (pname, is_arr, cname) in proc.params:
                if is_arr:
                    self.param_ptr[ident(proc.key) + "__" + ident(base(pname))] = cname
        self._prescan_qb()
        self.proc_vars = {}
        last_line = None
        seen_lines = set()
        for it in items:
            if it[0] == "label":
                self.label(it[1])
                continue
            _, s, line = it
            self.where = line or "?"
            self.cur_line = None
            if line and line not in seen_lines and s[0] not in ("data", "dim", "deffn"):
                seen_lines.add(line)               # ligne du source : débogueur (b ligne 12)
                if line <= len(lowering.source):   # le texte QuickBASIC, dans le listing
                    self.emit("")
                    self.emit("; %d: %s" % (line, lowering.source[line - 1].strip()
                                                     .replace("\t", " ")))
                self.label("LN_%d" % line)
            if self.debug and line and line != last_line and s[0] not in ("data", "dim"):
                self.emit("LD   HL,%d" % line)
                self.emit("LD   (RT_LINE),HL")
                last_line = line
            self.stmt(s)
        if self.fors:
            raise CompileError("FOR sans NEXT")
        self.emit("")
        self.emit("JP   RT_END")
        self._gen_fns()
        for d, (lab, dims) in sorted(self.descs.items()):
            n = [x + 1 for x in dims] + [0] * (2 - len(dims))
            self.code.append("%s:" % d)
            self.emit("DW   %s,%d,%d" % (lab, n[0], n[1]))
        self._fill_frames()
        return self._assemble_text(name, org)

    def _prescan_qb(self):
        """Comme _prescan, avec les DATA repérés par leur ligne QuickBASIC."""
        self.targets = set()
        self.data, self.data_at = [], {}
        for _, stmts, _, where in self.lines:
            for s in stmts:
                if s[0] == "dim":
                    for name, dims in s[1]:
                        key = self.akey(name)
                        if key in self.arrays and self.arrays[key] != dims:
                            raise CompileError("tableau %s dimensionné deux fois" % name, where)
                        self.arrays[key] = dims
                elif s[0] == "deffn":
                    self.fns[self.vkey(s[1])] = (s[1], s[2], basic._fold(s[3]), where)
                elif s[0] == "data":
                    w = where if isinstance(where, int) else 0
                    self.data_at.setdefault(w, len(self.data))
                    for item in s[1]:
                        self.data.append((w, item))

    def _need_line(self, n, where):
        pass

    # -------------------------------------------------- tableaux paramètres
    def _ptr_of(self, arrname):
        key = arrname.rsplit("__A", 1)[0]
        return self.param_ptr.get(key)

    def const_addr(self, e):
        if self._ptr_of(e[1]):
            return None
        return super().const_addr(e)

    def gen_addr(self, e, d):
        ptr = self._ptr_of(e[1])
        if not ptr:
            return super().gen_addr(e, d)
        idx = [basic._fold(i) for i in e[2]]
        t = self.ty.of(e[1])
        esz = self.strcap + 1 if t == "s" else basic.TYPE_SIZE[t]
        pv = self.var(ptr)
        if len(idx) == 1:
            self.gen_i(idx[0], d)
            self.emit("LD   DE,(%s)" % pv)
            self.emit("LD   A,%d" % esz)
            self.emit("CALL RT_PA1")
        elif len(idx) == 2:
            self.gen_i(idx[0], d)
            self.emit("PUSH HL")
            self.gen_i(idx[1], d)
            self.emit("POP  DE")
            self.emit("LD   BC,(%s)" % pv)
            self.emit("LD   A,%d" % esz)
            self.emit("CALL RT_PA2")
        else:
            self.err("tableau passé en paramètre : 1 ou 2 indices seulement")

    def gen_i(self, e, d):
        if e[0] == "adesc":                       # adresse du descripteur d'un tableau
            lab, dims, _ = self.array(e[1], len(self.arrays.get(self.akey(e[1]), [10])))
            if len(dims) > 2:
                self.err("tableau %s : 1 ou 2 dimensions pour le passer en paramètre" % e[1])
            d_lab = "QD_" + lab
            self.descs[d_lab] = (lab, dims)
            self.emit("LD   HL,%s" % d_lab)
            return
        return super().gen_i(e, d)

    def et(self, e):
        if e[0] == "adesc":
            return "i"
        return super().et(e)

    # -------------------------------------------------- instructions ajoutées
    def s_qjump(self, s):
        if s[2] and self.brk:
            self.emit("CALL RT_BRK")              # boucle : la touche BREAK reste active
        self.emit("JP   %s" % s[1])

    def s_qbrk(self, s):
        if self.brk:
            self.emit("CALL RT_BRK")

    def s_qjf(self, s):
        self.gen_cond(s[1], s[2])

    def s_qcall(self, s):
        self.emit("CALL %s" % s[1])

    def s_qret(self, s):
        self.emit("RET")

    def s_qbegin(self, s):
        self.cur_proc = s[1]
        self.proc_vars[s[1]] = set(self.vars)
        self.emit("@SAVE %s" % s[1])

    def s_qend(self, s):
        before = self.proc_vars[s[1]]
        self.proc_vars[s[1]] = sorted(k for k in self.vars if k not in before
                                      and re.fullmatch(r"G_\d+_[LSG]", k))
        self.emit("@REST %s" % s[1])

    def s_qzero(self, s):
        lab, dims, esz = self.array(s[1], len(self.arrays[self.akey(s[1])]))
        size = esz
        for x in dims:
            size *= x + 1
        self.emit("LD   HL,%s" % lab)
        self.emit("LD   BC,%d" % size)
        self.emit("CALL RT_ZERO")

    def s_restore(self, s):
        if s[1] is not None and s[1][0] == "qlabel":
            pos = self.lw.labels_at.get(s[1][1])
            if pos is None:
                self.err("RESTORE : étiquette %s inconnue" % s[1][1])
            lines = self.lw.data_lines
            line = lines[pos] if pos < len(lines) else None
            s = ("restore", line if line is not None else 10 ** 9)
        return super().s_restore(s)

    def _fill_frames(self):
        """Remplace @SAVE / @REST : variables locales empilées (procédures
        récursives seulement)."""
        out = []
        for line in self.code:
            m = re.match(r"\s*@(SAVE|REST) (\S+)$", line)
            if not m:
                out.append(line)
                continue
            proc = self.lw.procs[m.group(2)]
            if not proc.recursive:
                continue
            labels = []
            for n in proc.locals:
                lab = self.var(n)
                if lab not in labels:
                    labels.append(lab)
            labels += [k for k in self.proc_vars[proc.key] if k not in labels]
            if m.group(1) == "REST":
                labels.reverse()
            for lab in labels:
                out.append("        LD   HL,%s" % lab)
                out.append("        LD   BC,%d" % self.vars[lab])
                out.append("        CALL RT_%s" % m.group(1))
                self.used.add("RT_" + m.group(1))
        self.code = out


def compile_qbasic(text, name="PROG", org=0x1000, **opts):
    """Programme QuickBASIC -> (texte assembleur, compilateur, avertissements)."""
    lw = Lowering(text)
    items = lw.lower()
    comp = QBCompiler(**opts)
    try:
        asm = comp.compile_items(items, lw, name, org)
    except CompileError as e:
        raise QBError(str(e))
    return asm, comp, lw.warnings + comp.warnings
