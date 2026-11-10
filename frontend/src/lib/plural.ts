/** Русское склонение по числу: 1 файл, 2 файла, 5 файлов. */
export function pluralRu(n: number, forms: readonly [string, string, string]): string {
  // Отрицательные и дробные («1.5 файла», «-1 файлов») — всегда третья форма.
  if (!Number.isInteger(n) || n < 0) return forms[2]
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 14) return forms[2]
  const mod10 = mod100 % 10
  if (mod10 === 1) return forms[0]
  if (mod10 >= 2 && mod10 <= 4) return forms[1]
  return forms[2]
}
