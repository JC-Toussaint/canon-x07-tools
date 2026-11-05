program Prodi;
{ Double boucle 100 x 100 avec multiplication entière (27292).
  Comparaison Turbo Pascal / C : voir prodi.c et mesure.py. }
var i, j, s: integer;
begin
  s := 0;
  for i := 0 to 99 do
    for j := 0 to 99 do
      s := s + ((i * j) and 7);
  writeln(s)
end.
