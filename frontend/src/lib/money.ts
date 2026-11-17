const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

/** Money is integer cents everywhere; format as BRL only here, in the UI. */
export function formatCents(cents: number): string {
  return brl.format(cents / 100)
}
