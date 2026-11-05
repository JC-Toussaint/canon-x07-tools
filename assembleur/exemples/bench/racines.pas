program Racines;
{ Somme des racines carrées de 1 à 30, en réels de la ROM (112.08284521569).
  Comparaison Turbo Pascal / C : voir racines.c et mesure.py. }
var s: real; i: integer;
begin
  s := 0;
  for i := 1 to 30 do s := s + sqrt(i);
  writeln(s:0:10)
end.
