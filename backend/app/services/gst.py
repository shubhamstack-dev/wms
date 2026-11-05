"""GSTIN validation (format, state code, check character). Captured master data only — no billing."""
GST_STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory",
}
_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
import re

_FMT = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
PIN_RE = re.compile(r"^[1-9][0-9]{5}$")


def check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        p = _B36.index(ch) * (2 if i % 2 else 1)
        total += p // 36 + p % 36
    return _B36[(36 - total % 36) % 36]


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    base = f"{state}{pan}{entity}Z"
    return base + check_char(base)


def check_gstin(g: str | None) -> dict:
    g = (g or "").strip().upper()
    if not g:
        return {"ok": False, "empty": True, "msg": "GSTIN not maintained"}
    if len(g) != 15:
        return {"ok": False, "msg": f"GSTIN must be 15 characters (now {len(g)})"}
    if not _FMT.match(g):
        return {"ok": False, "msg": "Format: 2-digit state code + 10-char PAN + entity no. + Z + check character"}
    if g[:2] not in GST_STATES:
        return {"ok": False, "msg": f"State code {g[:2]} is not a valid GST state code"}
    if check_char(g[:14]) != g[14]:
        return {"ok": False, "msg": "Check character does not match — please re-check the GSTIN"}
    return {"ok": True, "gstin": g, "state": g[:2], "state_name": GST_STATES[g[:2]], "pan": g[2:12]}
