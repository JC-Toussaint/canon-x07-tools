"""Tests du Turbo Pascal simplifié (x07asm/pascal.py).

Chaque programme est traduit en QuickBASIC, compilé par qbcomp, exécuté
par la ROM du X-07 (émulateur) ; son affichage est comparé à celui qu'aurait
donné Turbo Pascal 3.0."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from x07asm import emu, pascal               # noqa: E402
from x07asm.asm import Assembler             # noqa: E402

needs_rom = unittest.skipUnless(emu.rom_path() is not None, "ROM_x07/x07.bin absente")


def run(src, inputs=(), keys="", setup=None):
    asm, comp, warns, lines = pascal.compile_pascal(src, "T", 0x1000)
    a = Assembler()
    mem = a.assemble_text(asm)
    assert not a.errors, a.errors
    m = emu.prepare_binary(mem, a.entry, keys, list(inputs), 16)
    if setup:
        setup(m)
    m.run(80_000_000)
    return m, warns


@needs_rom
class TestPascal(unittest.TestCase):
    def out(self, src, expected, **kw):
        m, warns = run(src, **kw)
        self.assertEqual(m.output().rstrip("\n"), expected.rstrip("\n"))
        return m, warns

    def test_records_recursion_case(self):
        self.out('''program Essai;
type
  Point = record x, y: real end;
  Couleur = (rouge, vert, bleu);
var
  p, q: Point;
  t: array[1..5] of integer;
  i: integer;
  c: Couleur;
  nom: string[10];
function Fact(n: integer): real;
begin
  if n <= 1 then Fact := 1 else Fact := n * Fact(n - 1)
end;
procedure Echange(var a, b: Point);
var tmp: Point;
begin
  tmp := a; a := b; b := tmp
end;
begin
  p.x := 1.5; p.y := 2; q.x := -3; q.y := 4.25;
  Echange(p, q);
  writeln(p.x:6:2, q.y:6:2);
  for i := 1 to 5 do t[i] := i * i;
  writeln('t[4]=', t[4], ' 10!=', Fact(10):0:0);
  c := bleu;
  case c of
    rouge: writeln('rouge');
    vert, bleu: writeln('vert ou bleu')
  end;
  nom := 'Pascal';
  writeln(nom, length(nom):3, ' ', ord(nom[1]))
end.''', " -3.00  2.00\nt[4]=16 10!=3628800\nvert ou bleu\nPascal  6 80")

    def test_nested_records_strings_formats(self):
        self.out('''program Essai2;
const
  Max = 3;
  Titre = 'Liste';
  Bonus: integer = 7;
type
  Adresse = record ville: string[12]; cp: integer end;
  Personne = record nom: string[12]; age: integer; adr: Adresse end;
  Groupe = array[1..Max] of Personne;
var
  g: Groupe;
  i, len, line, data: integer;
  c: char;
  s, mot: string[20];
  ok: boolean;
  x: real;
procedure Afficher(var p: Personne); forward;
function Somme(var t: Groupe): integer;
var k, total: integer;
begin
  total := 0;
  for k := 1 to Max do total := total + t[k].age;
  Somme := total
end;
procedure Afficher(var p: Personne);
begin
  with p, adr do writeln(nom, ' ', age, ' ', ville, cp:6)
end;
begin
  g[1].nom := 'Alice'; g[1].age := 30; g[1].adr.ville := 'Lyon'; g[1].adr.cp := 6900;
  g[2].nom := 'Bob';   g[2].age := 25; g[2].adr.ville := 'Nice'; g[2].adr.cp := 6000;
  g[3] := g[1]; g[3].nom := 'Eve'; g[3].age := g[3].age + Bonus;
  writeln(Titre);
  for i := Max downto 1 do Afficher(g[i]);
  writeln('somme=', Somme(g));
  len := -7; line := 2; data := len div line;
  writeln(data, ' ', len mod line, ' ', 5 shl 2, ' ', 100 shr 3);
  s := '';
  for c := 'a' to 'e' do s := s + upcase(c);
  writeln(s, ' ', succ('A'), pred(10));
  mot := 'bonjour';
  insert('XX', mot, 3); writeln(mot);
  delete(mot, 1, 2); writeln(mot, ' ', pos('jo', mot), ' ', copy(mot, 2, 3));
  i := 0;
  repeat i := i + 1 until i * i > 50;
  writeln('i=', i);
  while i > 0 do i := i - 3;
  ok := (i < 0) and not (i = -5);
  writeln(ok, ' ', 'k' in ['a'..'m', 'z'], ' ', odd(7));
  x := 1234.5678;
  writeln(x);
  writeln(x:12, ' ', -x:10:3, ' ', round(2.5), trunc(-2.7));
  writeln(sqrt(2.0):0:10, ' ', pi:0:12)
end.''', """Liste
Eve 37 Lyon  6900
Bob 25 Nice  6000
Alice 30 Lyon  6900
somme=92
-3 -1 20 12
ABCDE B9
boXXnjour
XXnjour 4 Xnj
i=8
TRUE TRUE TRUE
 1.2345678000E+03
 1.23457E+03  -1234.568 3-2
1.4142135624 3.141592653590""")

    def test_locals_shadow_globals_enum_char_index_input(self):
        self.out('''program Essai3;
type Jour = (lundi, mardi, mercredi);
var
  n, total: integer;
  compte: array['a'..'e'] of integer;
  c: char;
  j: Jour;
  nom: string;
function Fib(n: integer): integer;
var a, b: integer;
begin
  if n < 2 then begin Fib := n; exit end;
  a := Fib(n - 1);
  b := Fib(n - 2);
  Fib := a + b
end;
procedure Compter(s: string);
var total, k: integer;
begin
  total := 0;
  for k := 1 to length(s) do
    if s[k] in ['a'..'e'] then begin
      compte[s[k]] := compte[s[k]] + 1;
      total := total + 1
    end;
  writeln('lettres a-e : ', total)
end;
begin
  total := 99;
  for c := 'a' to 'e' do compte[c] := 0;
  Compter('abracadabra');
  writeln('total global : ', total, ' a=', compte['a'], ' b=', compte['b']);
  writeln('Fib(15)=', Fib(15));
  for j := lundi to mercredi do write(ord(j), ' ');
  writeln;
  mem[$1F00] := 123;
  writeln('mem=', mem[$1F00]);
  write('Nom ? ');
  readln(nom);
  write('Nombre ? ');
  readln(n);
  writeln('Bonjour ', nom, ', ', n, '*2=', n * 2)
end.''', """lettres a-e : 9
total global : 99 a=5 b=2
Fib(15)=610
0 1 2 \nmem=123
Nom ? Zoe
Nombre ? 21
Bonjour Zoe, 21*2=42""", inputs=["Zoe", "21"])

    def test_var_params_array_elements_and_value_params(self):
        # tri à bulles : éléments de tableau passés en var ; paramètre par
        # valeur modifié dans la procédure sans effet chez l'appelant
        self.out('''program Tri;
var t: array[0..4] of integer; i, n: integer;
procedure Echange(var a, b: integer);
var c: integer;
begin c := a; a := b; b := c end;
procedure Double(k: integer);
begin k := k * 2; write(k, ' ') end;
begin
  t[0] := 5; t[1] := 3; t[2] := 9; t[3] := 1; t[4] := 7;
  for i := 0 to 3 do
    for n := 0 to 3 - i do
      if t[n] > t[n + 1] then Echange(t[n], t[n + 1]);
  for i := 0 to 4 do write(t[i], ' ');
  writeln;
  n := 21; Double(n); writeln(n)
end.''', "1 3 5 7 9 \n42 21")

    def test_example_by_value(self):
        # exemples/pascal/valeur.pas : entier, record, chaîne ; par valeur, puis var
        with open(os.path.join(ROOT, "exemples", "pascal", "valeur.pas"), encoding="utf-8") as f:
            src = f.read()
        self.out(src, "valeur : 21\nvar    : 42\nrecord : 1 11\nchaine : AB *AB*")

    def test_example_gauss_jordan(self):
        # exemples/pascal/gauss_rand.pas : système tiré au hasard ; la solution
        # affichée, reportée dans la matrice affichée, vérifie les équations
        import re
        with open(os.path.join(ROOT, "exemples", "pascal", "gauss_rand.pas"),
                  encoding="utf-8") as f:
            src = f.read()
        m, _ = run(src, inputs=["4"])
        out = m.output()
        rows = [[float(x) for x in re.findall(r"-?\d+", line.replace("|", " "))]
                for line in out.splitlines() if "|" in line and "A | B" not in line]
        xs = [float(v) for v in re.findall(r"X\d+ = +(-?[\d.]+)", out)]
        self.assertEqual((len(rows), len(xs)), (4, 4), out)
        for row in rows:
            self.assertAlmostEqual(sum(c * x for c, x in zip(row[:4], xs)), row[4], delta=1e-3)

    def test_real_formats(self):
        # notation scientifique de Turbo Pascal 3.0 et virgule fixe
        # (1/3*3 = 1 serait faux : le X-07 calcule en décimal, sur 14 chiffres)
        self.out('''program Reels;
begin
  writeln(0.0);
  writeln(-0.000123);
  writeln(1e10:10);
  writeln(2/3:0:4, ' ', -0.004:0:2, ' ', 9.995:0:2, ' ', 12:5)
end.''', """ 0.0000000000E+00
-1.2300000000E-04
 1.000E+10
0.6667 -0.00 10.00    12""")

    def test_keyboard_graphics_sound(self):
        notes = []
        m, _ = self.out('''program Divers;
var c: char; k: integer;
begin
  k := 0;
  while not KeyPressed do k := k + 1;
  c := ReadKey;
  writeln('touche ', c, ' ', KeyPressed);
  Plot(3, 4); Draw(0, 31, 119, 31); Circle(60, 15, 8);
  Sound(440); Delay(500); NoSound;
  GotoXY(5, 3); write('ici')
end.''', "touche A FALSE\nici", keys="A", setup=lambda m: setattr(m, "on_note",
                                                               lambda f, d: notes.append(f)))
        self.assertTrue(m.lcd.get(3, 4) and m.lcd.get(119, 31) and m.lcd.get(68, 15))
        self.assertEqual(len(notes), 1)
        self.assertAlmostEqual(notes[0], 192000 / (192000 // 440), places=1)
        self.assertIn("    ici", m.lcd.text()[2])

    def test_errors_give_pascal_lines(self):
        cases = [("program A;\nbegin\n  x := 1\nend.", "ligne 3", "inconnu : x"),
                 ("program A;\nvar s: set of char;\nbegin end.", "ligne 2", "set"),
                 ("program A;\nprocedure P;\n  procedure Q; begin end;\nbegin end;\nbegin end.",
                  "ligne 3", "imbriquée"),
                 ("program A;\nvar i: integer;\nbegin\n  i := 2.5\nend.", "ligne 4", "Round")]
        for src, line, what in cases:
            with self.assertRaises(pascal.PasError) as cm:
                pascal.compile_pascal(src)
            self.assertIn(line, str(cm.exception))
            self.assertIn(what, str(cm.exception))


@needs_rom
class TestDebugger(unittest.TestCase):
    def test_variables_with_pascal_names_and_bounds(self):
        # onglet Variables de l'IDE : noms Pascal, champs, bornes des tableaux,
        # variable locale homonyme d'une globale, paramètre « a » (nom court)
        from x07asm.ide import Session
        s = Session(os.path.join(ROOT, "exemples", "pascal", "fiches.pas"))
        s.build()
        self.assertEqual(s.toggle_break(26), (26, True))
        s.run()
        self.assertEqual(s.current_line(), 26)
        v = s.variables()
        for want in ("Trier.i = 1", "Trier.j = 2", "Remplir.a = 19",
                     "Trier.l.age() -> l.age()", "l.age(1..4) = 34 27 45 19"):
            self.assertIn(want, v)
        self.assertFalse([x for x in v if "TP" in x.split(" = ")[0]])   # bibliothèque cachée


class TestTranslation(unittest.TestCase):
    def test_names_and_line_map(self):
        qb, warns, lines = pascal.translate(
            "program N;\nvar len, tpx, my_var: integer;\nbegin\n  len := 1;\n"
            "  tpx := len;\n  my_var := 3\nend.")
        self.assertIn("LENV% = 1", qb)                 # mot réservé de QuickBASIC
        self.assertIn("PTPX% = LENV%", qb)             # TP : réservé à la bibliothèque
        self.assertIn("MYVAR% = 3", qb)
        k = qb.splitlines().index("LENV% = 1") + 1
        self.assertEqual(lines[k], 4)

    def test_tokens(self):
        toks = pascal.tokenize("x := 'it''s'#13#10 + $1F; { com\nmentaire } (* et *) 1.5e2")
        kinds = [(t.kind, t.val) for t in toks[:-1]]
        self.assertEqual(kinds, [("id", "x"), ("op", ":="), ("str", "it's\r\n"), ("op", "+"),
                                 ("num", 31), ("op", ";"), ("real", "1.5e2")])
        self.assertEqual(toks[-1].line, 2)


if __name__ == "__main__":
    unittest.main()
