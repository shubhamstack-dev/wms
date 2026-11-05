// Thin client for the FastAPI middleware. The role travels in the X-Role header (replace with real auth — see README).
const BASE = import.meta.env.VITE_API_BASE || '/api'
let role = localStorage.getItem('wms.role') || 'ADMIN'
export const setApiRole = r => { role = r }

function message(data, res) {
  let d = data && data.detail !== undefined ? data.detail : res.statusText
  if (Array.isArray(d)) d = d.map(x => String(x.msg || '').replace(/^Value error, /, '') +
    (x.loc && x.loc.length > 1 ? ` (${x.loc[x.loc.length - 1]})` : '')).join('; ')
  return typeof d === 'string' ? d : JSON.stringify(d)
}

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Role': role },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const txt = await res.text()
  let data = null
  try { data = txt ? JSON.parse(txt) : null } catch { data = txt }
  if (!res.ok) throw new Error(message(data, res))
  return data
}

export const api = {
  get: p => req('GET', p),
  post: (p, b) => req('POST', p, b ?? {}),
  put: (p, b) => req('PUT', p, b),
  patch: (p, b) => req('PATCH', p, b),
  del: p => req('DELETE', p),
  async download(p, filename) {
    const res = await fetch(BASE + p, { headers: { 'X-Role': role } })
    if (!res.ok) throw new Error(res.statusText)
    const blob = await res.blob()
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: filename })
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove() }, 500)
  },
}
