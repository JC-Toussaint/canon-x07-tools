program GaussRand;  { système d'équations aléatoire, résolu par Gauss-Jordan }
{ traduction de exemples/qbasic/gauss_rand.qbas ;
  python3 x07asm.py run exemples/pascal/gauss_rand.pas --fenetre
  5 Ko en tout : tient dans un X-07 de 8 Ko, même avec 10 équations. }
const
  NMax = 10;
type
  Matrice = array[1..NMax, 1..11] of real;   { matrice augmentée (A | B) }
var
  a: Matrice;
  n, i, j: integer;
  somme: real;

procedure GaussJordan(var a: Matrice; n: integer);
const
  Eps = 0.00001;
var
  k, p, i, j: integer;
  temp, pivot, fact: real;
begin
  for k := 1 to n do begin
    { recherche du pivot maximal }
    p := k;
    for i := k + 1 to n do
      if abs(a[i, k]) > abs(a[p, k]) then p := i;

    { vérification du pivot }
    if abs(a[p, k]) < Eps then begin
      writeln;
      writeln('Solution unique impossible.');
      writeln('Systeme incompatible ou indefini.');
      exit
    end;

    { permutation des lignes }
    if p <> k then
      for j := 1 to n + 1 do begin
        temp := a[k, j]; a[k, j] := a[p, j]; a[p, j] := temp
      end;

    { normalisation de la ligne pivot }
    pivot := a[k, k];
    for j := 1 to n + 1 do a[k, j] := a[k, j] / pivot;

    { élimination des autres coefficients }
    for i := 1 to n do
      if i <> k then begin
        fact := a[i, k];
        for j := 1 to n + 1 do a[i, j] := a[i, j] - fact * a[k, j]
      end
  end;

  { affichage de la solution }
  writeln;
  writeln('Solution du systeme :');
  for i := 1 to n do
    writeln('X', i, ' = ', a[i, n + 1]:9:5)
end;

begin
  ClrScr;
  Randomize;                                { initialise le générateur aléatoire }
  write('Nombre d''equations (maximum 10) : ');
  readln(n);
  if (n < 1) or (n > NMax) then begin
    writeln('Nombre d''equations invalide.');
    halt
  end;

  { génération de la matrice à diagonale dominante et du second membre }
  for i := 1 to n do begin
    somme := 0;
    { 1. coefficients non diagonaux entre -5 et 5, somme de leurs valeurs absolues }
    for j := 1 to n do
      if i <> j then begin
        a[i, j] := random(11) - 5;
        somme := somme + abs(a[i, j])
      end;
    { 2. dominance diagonale stricte }
    a[i, i] := somme + random(5) + 1;
    { 3. second membre (colonne n + 1) entre -20 et 20 }
    a[i, n + 1] := random(41) - 20
  end;

  { affichage de la matrice générée, pour vérification }
  writeln;
  writeln('--- Matrice augmentee generee (A | B) ---');
  for i := 1 to n do begin
    for j := 1 to n + 1 do begin
      if j = n + 1 then write(' | ');
      write(a[i, j]:4:0)
    end;
    writeln
  end;
  writeln;

  GaussJordan(a, n)
end.
