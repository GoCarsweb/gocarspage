#!/usr/bin/env python3
"""
GoCar's — Scraper catálogo Quiroz Chile
Corre via GitHub Actions, guarda quiroz_data.json con markup 28%
"""

import os, json, math, re, sys
from datetime import datetime
import urllib.request
import urllib.parse
import http.cookiejar

MARKUP    = 1.28
BASE_URL  = "https://carro.quirozchile.cl"
LOGIN_URL = BASE_URL + "/"
RUT       = os.environ["QUIROZ_RUT"]
PASS      = os.environ["QUIROZ_PASS"]
OUT_FILE  = "quiroz_data.json"

# ── SESIÓN ────────────────────────────────────────────────────────────
def make_session():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "es-CL,es;q=0.9"),
    ]
    return opener

def login(opener):
    resp0 = opener.open(LOGIN_URL, timeout=20)
    html0 = resp0.read().decode("utf-8", errors="replace")

    # Extraer nombre real de campos
    rut_name, pass_name = "rutid", "pwid"
    for m in re.finditer(r'<input[^>]+>', html0, re.IGNORECASE):
        tag = m.group(0)
        t = re.search(r'type=["\']([^"\']+)["\']', tag)
        n = re.search(r'name=["\']([^"\']+)["\']', tag)
        if not t or not n: continue
        if t.group(1).lower() in ("text","email") and re.search(r'rut|user', n.group(1), re.I):
            rut_name = n.group(1)
        if t.group(1).lower() == "password":
            pass_name = n.group(1)

    payload = urllib.parse.urlencode({rut_name: RUT, pass_name: PASS, "submitb": "Entrar"}).encode()
    req = urllib.request.Request(LOGIN_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Referer", LOGIN_URL)
    resp = opener.open(req, timeout=20)
    html = resp.read().decode("utf-8", errors="replace")
    print(f"[login] html_len={len(html)} url={resp.url}")
    return html

def fetch(opener, url):
    try:
        resp = opener.open(url, timeout=30)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[fetch] ERROR {url}: {e}")
        return ""

# ── EXTRAER CATEGORÍAS DEL HOME ────────────────────────────────────────
def extract_categories(html):
    """Extrae keywords de categoría de los links del sidebar."""
    cats = []
    for m in re.finditer(r'href="[^"]*mod=search[^"]*kw=([^"&]+)"', html):
        kw = urllib.parse.unquote_plus(m.group(1))
        if kw not in cats:
            cats.append(kw)
    print(f"[cats] {len(cats)} categorías: {cats[:10]}...")
    return cats

# ── PARSER ─────────────────────────────────────────────────────────────
def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&[a-zA-Z]+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def parse_price(text):
    matches = re.findall(r"\$?\s*([\d]{1,3}(?:[\.,][\d]{3})*)", text)
    for m in reversed(matches):
        val = float(m.replace(".", "").replace(",", ""))
        if val >= 500:
            return val
    return 0.0

_first_row_printed = False

def fix_img(src):
    if not src:
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("http"):
        return src
    return BASE_URL + ("" if src.startswith("/") else "/") + src

def parse_products_from_page(html, debug=False):
    global _first_row_printed
    products = []

    rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, re.IGNORECASE)
    for row in rows:
        cells_raw = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.IGNORECASE)
        cells = [strip_tags(c) for c in cells_raw]
        if len(cells) < 2:
            continue
        text = " ".join(cells)
        price = parse_price(text)
        if price < 500:
            continue

        # Debug: print first valid row to understand column order
        if debug and not _first_row_printed:
            print(f"[row_debug] cells={cells}")
            _first_row_printed = True

        # Código: primera celda que parece un código de producto
        code_m = re.search(r"\b([A-Z]{2,}[\-\/\.][A-Z0-9\-\/\.]{2,})\b", text)
        code = code_m.group(1) if code_m else cells[0]

        # Nombre: celda más larga que no sea código ni precio ni número
        code_pat = re.compile(r'^[A-Z]{2,}[\-\/\.]', re.IGNORECASE)
        name = ""
        best_len = 0
        for c in cells:
            if re.match(r"^[\d\$\$]", c): continue
            if code_pat.match(c) and len(c) < 20: continue  # parece código corto
            if len(c) > best_len:
                best_len = len(c)
                name = c
        if not name:
            name = code  # fallback

        img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', "".join(cells_raw), re.IGNORECASE)
        img = fix_img(img_m.group(1) if img_m else "")

        products.append({"name": name, "code": code, "img": img, "precioBase": price})

    return products

# ── MAIN ────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().isoformat()}] Iniciando scraper Quiroz Chile…")

    opener = make_session()
    home_html = login(opener)

    if len(home_html) < 8000:
        print(f"[WARN] Login posiblemente fallido — html corto:\n{home_html[:2000]}")
        sys.exit(1)

    # Extraer categorías del sidebar
    categories = extract_categories(home_html)
    if not categories:
        # Fallback: categorías conocidas del sitio
        categories = ["alternador", "bendix", "filtro", "carbon", "inducido",
                      "electroventilador", "bomba", "bujia", "fusible", "horquilla"]

    all_products = []
    seen_keys = set()

    for cat in categories:
        is_first = (cat == categories[0])
        new = 0
        pg = 1
        while True:
            url = f"{BASE_URL}/?mod=search&ty=pro&kw={urllib.parse.quote(cat)}&pg={pg}"
            html = fetch(opener, url)
            prods = parse_products_from_page(html, debug=is_first and pg == 1)
            if not prods:
                break
            added = 0
            for p in prods:
                key = (p["code"] or p["name"]).strip()
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    p["categoria"] = cat
                    all_products.append(p)
                    new += 1
                    added += 1
            if added == 0:
                break  # página sin productos nuevos = fin
            pg += 1
            if pg > 50:  # tope de seguridad
                break
        print(f"[cat='{cat}'] +{new} ({pg-1} págs) → total {len(all_products)}")

    # Aplicar markup 28%
    for p in all_products:
        p["precio"] = math.ceil(p["precioBase"] * MARKUP / 100) * 100
        del p["precioBase"]

    output = {
        "ok":         True,
        "total":      len(all_products),
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "products":   all_products
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(all_products)} productos guardados en {OUT_FILE}")

    if len(all_products) == 0:
        with open("quiroz_diag.html", "w", encoding="utf-8") as f:
            f.write(home_html)
        sys.exit(1)

if __name__ == "__main__":
    main()
