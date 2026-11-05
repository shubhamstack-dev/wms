// Thin client for the FastAPI middleware. The login token travels in the Authorization header.
const BASE = import.meta.env.VITE_API_BASE || '/api'
let token = localStorage.getItem('wms.token') || ''
let onLoggedOut = () => {}
export const setToken = t => { token = t || ''; t ? localStorage.setItem('wms.token', t) : localStorage.removeItem('wms.token') }
export const hasToken = () => !!token
export const onUnauthorized = fn => { onLoggedOut = fn }

function message(data, res) {
  let d = data && data.detail !== undefined ? data.detail : res.statusText
  if (Array.isArray(d)) d = d.map(x => String(x.msg || '').replace(/^Value error, /, '') +
    (x.loc && x.loc.length > 1 ? ` (${x.loc[x.loc.length - 1]})` : '')).join('; ')
  return typeof d === 'string' ? d : JSON.stringify(d)
}

const headers = extra => (token ? { ...extra, Authorization: 'Bearer ' + token } : { ...extra })

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: headers({ 'Content-Type': 'application/json' }),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const txt = await res.text()
  let data = null
  try { data = txt ? JSON.parse(txt) : null } catch { data = txt }
  if (res.status === 401 && token && !path.startsWith('/auth/')) { setToken(''); onLoggedOut() }
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
    const res = await fetch(BASE + p, { headers: headers({}) })
    if (res.status === 401) { setToken(''); onLoggedOut() }
    if (!res.ok) throw new Error(res.statusText)
    const blob = await res.blob()
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: filename })
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove() }, 500)
  },
}
