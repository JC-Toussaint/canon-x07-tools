program Hanoi;  { récursivité : les tours de Hanoï }
{ python3 x07asm.py run exemples/pascal/hanoi.pas }
var
  coups: integer;

procedure Deplacer(n: integer; de, vers, par: char);
begin
  if n > 0 then begin
    Deplacer(n - 1, de, par, vers);
    coups := coups + 1;
    if n = 3 then writeln('disque 3 : ', de, '->', vers);
    Deplacer(n - 1, par, vers, de)
  end
end;

begin
  coups := 0;
  Deplacer(5, 'A', 'C', 'B');
  writeln(coups, ' coups')
end.
