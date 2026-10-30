program Dessin;  { graphismes du X-07 : écran de 120 x 32 points }
{ python3 x07asm.py run exemples/pascal/dessin.pas --fenetre }
var
  i: integer;
  x, y: real;
  c: char;
begin
  ClrScr;
  Draw(0, 31, 119, 31);                    { axe horizontal }
  for i := 0 to 119 do begin               { sinusoïde, point par point }
    x := i / 10;
    y := 16 - 12 * sin(x);
    Plot(i, round(y))
  end;
  Circle(100, 10, 7);
  Sound(880); Delay(150); NoSound;
  GotoXY(1, 1); write('Une touche...');
  repeat until KeyPressed;
  c := ReadKey;
  ClrScr;
  writeln('Touche : ', c)
end.
