program Meteo;  { carnet de températures, un fichier par mois }
{ python3 x07asm.py run exemples/pascal/meteo.pas --ram 16 --fenetre
  Les relevés sont gardés dans un fichier en RAM du X-07 (METJAN, METFEV...) :
  ils survivent à l'extinction (run --memoire x07.mem pour l'émulateur).
  On tape « jour température » sur une ligne (12 18.5), puis 0 pour finir.
  Met en oeuvre : fichiers texte, nom calculé, ensembles, readln(a, b),
  single, constante tableau, records, s[0], largeurs constantes. }
const
  Mois: array[1..12] of string[3] =
    ('JAN', 'FEV', 'MAR', 'AVR', 'MAI', 'JUN', 'JUL', 'AOU', 'SEP', 'OCT', 'NOV', 'DEC');
  Taille = 600;                       { octets du fichier en RAM }
type
  Releve = record
    jour: integer;
    temp: single;                     { simple précision : bien assez ici }
  end;
var
  f: text;
  rel: array[1..31] of Releve;        { les relevés, rangés par jour }
  jours: set of 1..31;                { jours déjà relevés }
  m, j, n: integer;
  t: single;
  c: char;

procedure Couper(var s: string; largeur: integer);   { à la largeur de l'écran }
begin
  if length(s) > largeur then s[0] := chr(largeur)
end;

procedure Ajouter(j: integer; x: single);
begin
  rel[j].jour := j;                   { pas de with ici : dans with rel[j], « jour »
                                        désignerait le champ, pas un paramètre }
  rel[j].temp := x;
  jours := jours + [j];
  n := n + 1
end;

procedure Relire;                     { relevés déjà enregistrés pour ce mois }
begin
  append(f, Taille); close(f);        { crée le fichier s'il n'existe pas }
  reset(f);
  while not eof(f) do begin
    readln(f, j, t);
    if (j >= 1) and (j <= 31) then Ajouter(j, t)
  end;
  close(f)
end;

procedure Saisir;
var
  msg: string[20];                    { longueurs courtes : programme plus petit }
begin
  ClrScr;
  writeln(Mois[m], ' : ', n, ' releves');
  repeat
    write('Jour temp ? ');
    readln(j, t);
    if (j >= 1) and (j <= 31) then
      if j in jours then begin
        msg := 'jour ' + chr(48 + j div 10) + chr(48 + j mod 10) + ' deja saisi !!';
        Couper(msg, 19);
        writeln(msg)
      end else begin
        Ajouter(j, t);
        append(f, Taille);
        writeln(f, j, ' ', t:0:1);
        close(f)
      end
  until j = 0
end;

procedure Bilan;
var
  mini, maxi, somme: single;
  k, manque: integer;
begin
  ClrScr;
  if n = 0 then begin writeln('Aucun releve'); exit end;
  mini := 99; maxi := -99; somme := 0; manque := 0;
  for k := 1 to 31 do
    if k in jours then
      with rel[k] do begin
        if temp < mini then mini := temp;
        if temp > maxi then maxi := temp;
        somme := somme + temp
      end
    else manque := manque + 1;
  writeln(Mois[m], ' ', n:2, ' releves');
  writeln('min', mini:6:1, ' max', maxi:6:1);
  writeln('moyenne', somme / n:7:2);
  write('jours manquants', manque:3)
end;

procedure Courbe;                     { températures de 0 à 40 degrés }
var
  k, x, y, x0, y0: integer;
  premier: boolean;
begin
  ClrScr;
  Draw(0, 31, 119, 31);               { axe des jours }
  for k := 1 to 31 do Plot(k * 3 + 10, 30);
  premier := true;
  for k := 1 to 31 do
    if k in jours then begin
      x := k * 3 + 10;
      y := 31 - round(rel[k].temp * 0.75);
      if y < 0 then y := 0;
      if not premier then Draw(x0, y0, x, y);
      Plot(x, y);
      x0 := x; y0 := y; premier := false
    end;
  GotoXY(1, 1); write(Mois[m])
end;

begin
  ClrScr;
  write('Mois (1-12) ? ');
  readln(m);
  if (m < 1) or (m > 12) then halt;
  assign(f, 'MET' + Mois[m]);         { nom calculé : METJAN, METFEV... }
  jours := []; n := 0;
  Relire;
  Saisir;
  Bilan;
  repeat until KeyPressed; c := ReadKey;
  Courbe;
  repeat until KeyPressed; c := ReadKey;
  ClrScr
end.
