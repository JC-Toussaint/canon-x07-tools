program Fiches;  { tableau de records, tri, with }
{ python3 x07asm.py run exemples/pascal/fiches.pas --fenetre }
const
  N = 4;
type
  Fiche = record
    nom: string[8];
    age: integer;
    taille: real
  end;
  Liste = array[1..N] of Fiche;
var
  l: Liste;
  i: integer;

procedure Remplir(var f: Fiche; n: string; a: integer; t: real);
begin
  with f do begin nom := n; age := a; taille := t end
end;

procedure Trier(var l: Liste);  { tri par âge croissant }
var i, j: integer; tmp: Fiche;
begin
  for i := 1 to N - 1 do
    for j := i + 1 to N do
      if l[j].age < l[i].age then begin
        tmp := l[i]; l[i] := l[j]; l[j] := tmp
      end
end;

begin
  Remplir(l[1], 'Alice', 34, 1.68);
  Remplir(l[2], 'Bob', 27, 1.82);
  Remplir(l[3], 'Chloe', 45, 1.59);
  Remplir(l[4], 'David', 19, 1.75);
  Trier(l);
  ClrScr;
  for i := 1 to N do
    with l[i] do writeln(nom:6, age:3, taille:6:2)
end.
