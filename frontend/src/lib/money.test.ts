import { describe, expect, it } from 'vitest'
import { formatCents } from './money'

describe('formatCents', () => {
  it('formats cents as BRL', () => {
    // Intl uses a non-breaking space after R$
    expect(formatCents(123456).replace(/ /g, ' ')).toBe('R$ 1.234,56')
    expect(formatCents(-5).replace(/ /g, ' ')).toBe('-R$ 0,05')
  })
})
