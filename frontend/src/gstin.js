// Same GSTIN check as the middleware — used only for instant feedback while typing.
const B36 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
export function checkChar(s14) {
  let sum = 0
  for (let i = 0; i < 14; i++) { const p = B36.indexOf(s14[i]) * (i % 2 ? 2 : 1); sum += Math.floor(p / 36) + p % 36 }
  return B36[(36 - sum % 36) % 36]
}
export function checkGstin(g, states = {}) {
  g = String(g || '').trim().toUpperCase()
  if (!g) return { ok: false, empty: true, msg: 'GSTIN not maintained' }
  if (g.length !== 15) return { ok: false, msg: `GSTIN must be 15 characters (now ${g.length})` }
  if (!/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/.test(g)) return { ok: false, msg: 'Format: state code + PAN + entity no. + Z + check character' }
  if (Object.keys(states).length && !states[g.slice(0, 2)]) return { ok: false, msg: `State code ${g.slice(0, 2)} is not a GST state code` }
  if (checkChar(g.slice(0, 14)) !== g[14]) return { ok: false, msg: 'Check character does not match — please re-check the GSTIN' }
  return { ok: true, gstin: g, state: g.slice(0, 2), pan: g.slice(2, 12) }
}
