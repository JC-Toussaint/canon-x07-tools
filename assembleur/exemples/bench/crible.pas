program Crible;
{ Crible d'Ératosthène jusqu'à 2000 : tableau, boucles (303 nombres premiers).
  Comparaison Turbo Pascal / C : voir crible.c et mesure.py. }
const N = 2000;
var premier: array[0..N] of boolean;
    i, j, nb: integer;
begin
  nb := 0;
  for i := 2 to N do premier[i] := true;
  i := 2;
  while i * i <= N do begin
    if premier[i] then begin
      j := i * i;
      while j <= N do begin premier[j] := false; j := j + i end
    end;
    i := i + 1
  end;
  for i := 2 to N do if premier[i] then nb := nb + 1;
  writeln(nb)
end.
