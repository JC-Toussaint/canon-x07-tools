program Fib;
{ Fibonacci(18) récursif : appels de fonction (2584).
  Comparaison Turbo Pascal / C : voir fib.c et mesure.py. }
function F(n: integer): integer;
begin
  if n < 2 then F := n else F := F(n - 1) + F(n - 2)
end;
begin
  writeln(F(18))
end.
