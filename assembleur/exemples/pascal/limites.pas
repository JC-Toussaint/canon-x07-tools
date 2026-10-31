program Limites;  { le Canon X-07 poussé dans ses retranchements }
{ python3 x07asm.py run exemples/pascal/limites.pas --ram 16 --fenetre
  Quatre écrans, une touche pour passer au suivant :
  1. calculs à 14 chiffres, en décimal (BCD) ;
  2. l'écran graphique de 120 x 32 points, d'un bord à l'autre ;
  3. l'ensemble de Mandelbrot sur 40 x 32 points, en entiers ;
  4. le buzzer, de 47 à 3918 Hz (diviseur de 49 à 4095).
  Vitesse (mesurée en instructions Z80, environ 2 microsecondes chacune) :
  un sin en double précision coûte 34 000 instructions (70 ms), une
  itération de Mandelbrot 20 000 en double précision, 1 100 en entiers.
  D'où une table de sinus et un Mandelbrot en virgule fixe. }
const
  Largeur = 120;            { points }
  Hauteur = 32;
  IterMax = 16;             { Mandelbrot : itérations au plus par point }
var
  c: char;

procedure Attendre;         { une touche pour continuer }
begin
  repeat until KeyPressed;
  c := ReadKey
end;

{ ---------------------------------------------------------- 1. calculs }
procedure Calculs;
var
  e, pi, x, puiss: real;
  k: integer;
begin
  ClrScr;
  { e = 1 + 1/1 (1 + 1/2 (1 + 1/3 (...))) : Horner.  Le X-07 trouve
    2,71828182845915 : son 14e chiffre est faux d'une ou deux unités (arrondis
    des divisions), d'où 12 décimales seulement ; pi est juste sur 14 chiffres. }
  e := 1;
  for k := 18 downto 1 do e := 1 + e / k;
  { pi = 16 arctan(1/5) - 4 arctan(1/239), séries de Machin }
  pi := 0; x := 1 / 5; puiss := x;
  for k := 0 to 10 do begin
    if odd(k) then pi := pi - 16 * puiss / (2 * k + 1)
    else pi := pi + 16 * puiss / (2 * k + 1);
    puiss := puiss * x * x
  end;
  x := 1 / 239; puiss := x;
  for k := 0 to 3 do begin
    if odd(k) then pi := pi + 4 * puiss / (2 * k + 1)
    else pi := pi - 4 * puiss / (2 * k + 1);
    puiss := puiss * x * x
  end;
  writeln('e =', e:0:12);
  writeln('pi=', pi:0:13);
  writeln('0.1+0.2=0.3 : ', 0.1 + 0.2 = 0.3);     { vrai : calcul décimal }
  write('1/3*3=1     : ', 1 / 3 * 3 = 1);         { faux : 14 chiffres }
  Attendre
end;

{ ---------------------------------------------------------- 2. écran }
var
  QuartSin: array[0..18] of real;   { sin de 0 à 90 degrés, par pas de 5 }

function Sinus(k: integer): real;   { sin(5k degrés), par symétrie }
begin
  k := k mod 72;
  if k <= 18 then Sinus := QuartSin[k]
  else if k <= 36 then Sinus := QuartSin[36 - k]
  else if k <= 54 then Sinus := -QuartSin[k - 36]
  else Sinus := -QuartSin[72 - k]
end;

procedure Ecran;
var
  t, x, y, x0, y0: integer;
begin
  ClrScr;
  for t := 0 to 18 do QuartSin[t] := sin(t * 5 * pi / 180);   { 19 sin seulement }
  Draw(0, 0, Largeur - 1, 0); Draw(Largeur - 1, 0, Largeur - 1, Hauteur - 1);
  Draw(Largeur - 1, Hauteur - 1, 0, Hauteur - 1); Draw(0, Hauteur - 1, 0, 0);
  x0 := 60; y0 := 16;
  for t := 0 to 72 do begin                       { courbe de Lissajous 3:2 }
    x := round(59.5 + 57 * Sinus(3 * t));
    y := round(15.5 + 13 * Sinus(2 * t));
    if t > 0 then Draw(x0, y0, x, y);             { segment tracé par le T6834 }
    x0 := x; y0 := y
  end;
  GotoXY(8, 2); write('120x32');
  Attendre
end;

{ ---------------------------------------------------------- 3. Mandelbrot }
{ En virgule fixe : un nombre x est rangé dans l'entier x * 64.  Les entiers
  du X-07 ont 16 bits (32767 au plus) : |z| > 2 est testé sur |x| et |y|
  avant tout carré, puis x*x + y*y > 4 s'écrit x*x > 16384 - y*y. }
procedure Mandelbrot;
const
  Un = 64;                                        { 1,0 en virgule fixe }
  Cote = 40;            { 40 x 32 points : points carrés, 0,075 chacun }
var
  px, py, n, cx, cy, zx, zy, t: integer;
  dehors: boolean;
begin
  ClrScr;
  for py := 0 to Hauteur div 2 do begin          { symétrique : moitié haute }
    cy := (py - Hauteur div 2) * 154 div Hauteur;          { de -1,2 à 0 }
    for px := 0 to Cote - 1 do begin
      cx := -141 + px * 192 div Cote;                      { de -2,2 à 0,8 }
      zx := 0; zy := 0; n := 0;
      repeat
        t := (zx * zx - zy * zy) div Un + cx;
        zy := (zx * zy) div (Un div 2) + cy;
        zx := t;
        n := n + 1;
        dehors := (abs(zx) > 2 * Un) or (abs(zy) > 2 * Un);
        if not dehors then dehors := zx * zx > 4 * Un * Un - zy * zy
      until (n = IterMax) or dehors;
      if n = IterMax then begin
        Plot(px, py);
        Plot(px, Hauteur - 1 - py)
      end
    end
  end;
  GotoXY(9, 1); write('Mandelbrot');
  GotoXY(9, 2); write('40x32 points');
  GotoXY(9, 3); write('en entiers');
  GotoXY(9, 4); write('16 iter./pt');
  Attendre
end;

{ ---------------------------------------------------------- 4. son }
procedure Son;
const
  Gamme: array[1..8] of integer = (262, 294, 330, 349, 392, 440, 494, 523);
var
  k: integer;
begin
  ClrScr;
  writeln('Gamme...');
  for k := 1 to 8 do begin
    Sound(Gamme[k]); Delay(150)
  end;
  NoSound;
  writeln('Grave : 47 Hz');
  Sound(47); Delay(400); NoSound;
  writeln('Aigu : 3918 Hz');
  Sound(3918); Delay(400); NoSound;
  write('Fin. Une touche...');
  Attendre
end;

begin
  Calculs;
  Ecran;
  Mandelbrot;
  Son;
  ClrScr
end.
