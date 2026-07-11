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

MARKUP   = 1.28
LOGIN_URL = "https://carro.quirozchile.cl/"
RUT      = os.environ["QUIROZ_RUT"]
PASS     = os.environ["QUIROZ_PASS"]
OUT_FILE = "quiroz_data.json"

# ── SESIÓN ────────────────────────────────────────────────────────────
def make_session():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "es-CL,es;q=0.9"),
    ]
    return opener, jar

def login(opener):
    data = urllib.parse.urlencode({"rut": RUT, "password": PASS}).encode()
    req  = urllib.request.Request(LOGIN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        resp = opener.open(req, timeout=20)
        html = resp.read().decode("utf-8", errors="replace")
        print(f"[login] status={resp.status} url={resp.url} html_len={len(html)}")
        return html, resp.url
    except Exception as e:
        print(f"[login] ERROR: {e}")
        return "", LOGIN_URL

def fetch_page(opener, url):
    try:
        resp = opener.open(url, timeout=20)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[fetch] ERROR {url}: {e}")
        return ""

# ── PARSER ─────────────────────────────────────────────────────────────
def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&[a-z]+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def parse_price(text):
    """Extraer precio en CLP de un string de texto."""
    # Formato chileno: $123.456 o 123.456 o 123456
    matches = re.findall(r"\$?\s*([\d]{1,3}(?:[\.,][\d]{3})*)", text)
    for m in reversed(matches):
        val = float(m.replace(".", "").replace(",", "."))
        if val >= 500:   # mínimo razonable en CLP
            return val
    return 0.0

def parse_products(html, base_url="https://carro.quirozchile.cl"):
    products = []

    # Estrategia 1 — filas de tabla (típico en sistemas de repuestos chilenos)
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
        name = next((c for c in cells if len(c) > 5 and not c.startswith("$") and not re.match(r"^\d", c)), "")
        if not name:
            continue
        code_m = re.search(r"\b([A-Z]{2,}[\d\-\/\.]{2,}[A-Z\d]*)\b", text)
        code   = code_m.group(1) if code_m else cells[0]
        img_m  = re.search(r'<img[^>]+src="([^"]+)"', "".join(cells_raw), re.IGNORECASE)
        img    = img_m.group(1) if img_m else ""
        if img and not img.startswith("http"):
            img = base_url + img
        products.append({"name": name, "code": code, "img": img, "precioBase": price})

    # Estrategia 2 — divs de producto
    if not products:
        blocks = re.findall(
            r'<(?:div|article|li)[^>]+class="[^"]*(?:product|item|repuesto)[^"]*"[^>]*>([\s\S]*?)</(?:div|article|li)>',
            html, re.IGNORECASE
        )
        for block in blocks:
            text  = strip_tags(block)
            price = parse_price(text)
            if price < 500:
                continue
            name_m = re.search(r'<(?:h[1-6]|strong|a)[^>]*>([^<]{5,})</(?:h[1-6]|strong|a)>', block, re.IGNORECASE)
            name   = name_m.group(1).strip() if name_m else text[:60].strip()
            code_m = re.search(r"\b([A-Z]{2,}[\d\-\/\.]{2,}[A-Z\d]*)\b", text)
            code   = code_m.group(1) if code_m else ""
            img_m  = re.search(r'<img[^>]+src="([^"]+)"', block, re.IGNORECASE)
            img    = img_m.group(1) if img_m else ""
            if img and not img.startswith("http"):
                img = base_url + img
            products.append({"name": name, "code": code, "img": img, "precioBase": price})

    return products

# ── BÚSQUEDA / PAGINACIÓN ───────────────────────────────────────────────
SEARCH_PATTERNS = [
    "{base}?buscar={q}",
    "{base}buscar?q={q}",
    "{base}search?q={q}",
    "{base}productos?buscar={q}",
    "{base}catalogo?buscar={q}",
]

def search_products(opener, query="", base_url=LOGIN_URL):
    """Intenta distintos patrones de URL hasta encontrar productos."""
    for pattern in SEARCH_PATTERNS:
        url = pattern.format(base=base_url, q=urllib.parse.quote(query))
        html = fetch_page(opener, url)
        products = parse_products(html, base_url)
        if products:
            print(f"[search] Encontrado con patrón: {url} → {len(products)} productos")
            return products, url
    # Último recurso: parsear página principal post-login
    html = fetch_page(opener, base_url)
    products = parse_products(html, base_url)
    return products, base_url

# ── MAIN ────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().isoformat()}] Iniciando scraper Quiroz Chile…")

    opener, jar = make_session()
    html_login, final_url = login(opener)
    base_url = urllib.parse.urljoin(final_url, "/")
    print(f"[main] base_url={base_url}")

    # Guardar diagnóstico HTML para depurar si hay problemas
    diag_preview = html_login[:3000] if html_login else "(vacío)"
    print(f"[diag] HTML post-login preview:\n{diag_preview}\n{'—'*60}")

    # Intentar obtener catálogo completo (sin búsqueda) + por categorías comunes
    all_products = []
    seen_codes   = set()

    categories = ["", "embrague", "alternador", "partida", "rodamiento", "motor"]
    for cat in categories:
        prods, url = search_products(opener, cat, base_url)
        for p in prods:
            key = p["code"] or p["name"]
            if key not in seen_codes:
                seen_codes.add(key)
                all_products.append(p)
        print(f"[cat='{cat}'] +{len(prods)} → total {len(all_products)}")

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
        print("[WARN] 0 productos — el parser necesita ajustarse al HTML del sitio")
        # Guardar HTML para diagnóstico
        with open("quiroz_diag.html", "w", encoding="utf-8") as f:
            f.write(html_login)
        print("[diag] HTML guardado en quiroz_diag.html")
        sys.exit(1)   # Falla el workflow → visible en GitHub Actions logs

if __name__ == "__main__":
    main()
