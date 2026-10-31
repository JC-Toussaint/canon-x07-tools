program Valeur;  { passage des paramètres : par valeur ou par var }
{ python3 x07asm.py run exemples/pascal/valeur.pas --fenetre }
{ - sans var, par valeur : la procédure travaille sur une copie ;
  - avec var, par adresse : la procédure modifie la variable de l'appelant.
  C'est la déclaration de la procédure qui décide, pas l'appel (à
  l'inverse du QuickBASIC, voir exemples/qbasic/valeur.qbas).  Un
  paramètre var exige une variable : DoublerVar(n + 1) serait refusé. }
type
  Point = record x, y: integer end;
var
  n: integer;
  p: Point;
  s: string[10];

procedure Doubler(k: integer);           { par valeur }
begin
  k := k * 2
end;

procedure DoublerVar(var k: integer);    { par adresse }
begin
  k := k * 2
end;

procedure Decaler(p: Point);             { record par valeur : copie }
begin
  p.x := p.x + 10
end;

procedure DecalerVar(var p: Point);      { record par adresse }
begin
  p.x := p.x + 10
end;

procedure Etoiles(s: string);            { chaîne par valeur }
begin
  s := '*' + s + '*'
end;

procedure EtoilesVar(var s: string);     { chaîne par adresse }
begin
  s := '*' + s + '*'
end;

begin
  ClrScr;
  n := 21; Doubler(n);
  writeln('valeur : ', n);               { 21 : inchangé }
  n := 21; DoublerVar(n);
  writeln('var    : ', n);               { 42 : modifié }
  p.x := 1; p.y := 2;
  Decaler(p); write('record : ', p.x, ' ');
  DecalerVar(p); writeln(p.x);           { 1, puis 11 }
  s := 'AB';
  Etoiles(s); write('chaine : ', s, ' ');
  EtoilesVar(s); write(s)                { AB, puis *AB* }
end.
