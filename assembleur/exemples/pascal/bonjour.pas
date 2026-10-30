program Bonjour;  { Turbo Pascal simplifié pour le Canon X-07 }
{ python3 x07asm.py run exemples/pascal/bonjour.pas --fenetre }
var
  nom: string[12];
  age: integer;
begin
  ClrScr;
  write('Nom ? ');
  readln(nom);
  write('Age ? ');
  readln(age);
  writeln('Bonjour ', nom, ' !');
  writeln('Dans 10 ans : ', age + 10)
end.
