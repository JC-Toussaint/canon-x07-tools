/* Fibonacci(18) récursif : appels de fonction (2584).
   Comparaison C / Turbo Pascal : voir fib.pas et mesure.py. */
#include <stdio.h>
#include "x07.h"
static int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
int main(void) { printf("%d\n", fib(18)); return 0; }
