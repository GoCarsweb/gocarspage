#!/usr/bin/env python3
"""
GoCar's -- Scraper catalogo Quiroz Chile
Corre via GitHub Actions, guarda quiroz_data.json con markup 28%
"""

import os, json, math, re, sys, time, html as htmllib
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

VEHICULOS = [
    ("Toyota",        "Hilux"),
    ("Toyota",        "Land Cruiser"),
    ("Toyota",        "Fortuner"),
    ("Toyota",        "RAV4"),
    ("Toyota",        "Yaris"),
    ("Toyota",        "Corolla"),
    ("Nissan",        "Navara"),
    ("Nissan",        "Frontier"),
    ("Nissan",        "X-Trail"),
    ("Nissan",        "Note"),
    ("Mitsubishi",    "L200"),
    ("Mitsubishi",    "Outlander"),
    ("Mitsubishi",    "ASX"),
    ("Mitsubishi",    "Montero Sport"),
    ("Ford",          "Ranger"),
    ("Ford",          "Explorer"),
    ("Ford",          "F-150"),
    ("Ford",          "EcoSport"),
    ("Mazda",         "BT-50"),
    ("Mazda",         "CX-5"),
    ("Mazda",         "CX-3"),
    ("Mazda",         "Mazda3"),
    ("Chevrolet",     "D-Max"),
    ("Chevrolet",     "TrailBlazer"),
    ("Chevrolet",     "Captiva"),
    ("Chevrolet",     "Spark"),
    ("Isuzu",         "D-Max"),
    ("Isuzu",         "MU-X"),
    ("Hyundai",       "Tucson"),
    ("Hyundai",       "Santa Fe"),
    ("Hyundai",       "H1"),
    ("Hyundai",       "H100"),
    ("Hyundai",       "Accent"),
    ("Kia",           "Sportage"),
    ("Kia",           "Sorento"),
    ("Kia",           "Rio"),
    ("Volkswagen",    "Amarok"),
    ("Volkswagen",    "Golf"),
    ("Volkswagen",    "Tiguan"),
    ("Subaru",        "Forester"),
    ("Subaru",        "XV"),
    ("Suzuki",        "Vitara"),
    ("Suzuki",        "Grand Vitara"),
    ("Peugeot",       "Partner"),
    ("Peugeot",       "207"),
    ("Renault",       "Duster"),
    ("Renault",       "Logan"),
    ("Mercedes-Benz", "Sprinter"),
    ("Mercedes-Benz", "Vito"),
]

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

def extract_categories(html):
    cats = []
    for m in re.finditer(r'href="[^"]*mod=search[^"]*kw=([^"&]+)"', html):
        kw = urllib.parse.unquote_plus(m.group(1))
        if kw not in cats:
            cats.append(kw)
    print(f"[cats] {len(cats)} categorias encontradas")
    return cats

def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = htmllib.unescape(s)           # decodifica &ntilde; &amp; etc.
    return re.sub(r"\s+", " ", s).strip()

def parse_price(text):
    # Extrae todos los candidatos a precio (formato CLP: 1-3 dígitos + grupos de 3)
    matches = re.findall(r"\$\s*([\d]{1,3}(?:[.,][\d]{3})+)", text)
    if not matches:
        # Fallback: números sin símbolo $
        matches = re.findall(r"\b([\d]{1,3}(?:[.,][\d]{3})+)\b", text)
    vals = []
    for m in matches:
        v = float(m.replace(".", "").replace(",", ""))
        if v >= 5000:   # Precio mínimo realista para repuesto automotriz
            vals.append(v)
    # Usamos el valor más alto encontrado (evita capturar specs técnicas como "1.100A")
    return max(vals) if vals else 0.0

def extraer_vehiculos(name):
    """Detecta marcas/modelos en el nombre del producto (ej: 'TOYOTA HILUX C MOT...')"""
    name_up = name.upper()
    tags = []
    for marca, modelo in VEHICULOS:
        pat  = re.compile(r'\b' + re.escape(marca.upper()) + r'\b')
        pat2 = re.compile(r'\b' + re.escape(modelo.upper().replace(' ', r'[\s\-]?')) + r'\b')
        if pat.search(name_up) and pat2.search(name_up):
            tag = f"{marca} {modelo}"
            if tag not in tags:
                tags.append(tag)
    return tags

def extraer_oem(name):
    """Extrae números OEM/originales del nombre del producto"""
    found = []
    seen  = set()
    pats  = [
        re.compile(r'\b([A-Z0-9]{2,}(?:-[A-Z0-9]{2,}){1,4})\b', re.IGNORECASE),
        re.compile(r'\b([A-Z]{1,3}[0-9]{4,}[A-Z0-9]*)\b',        re.IGNORECASE),
        re.compile(r'\b([0-9]{7,})\b'),
    ]
    for pat in pats:
        for m in pat.finditer(name):
            v = m.group(1).upper()
            if re.match(r'^(19|20)\d{2}$', v): continue   # excluir años
            if len(v) < 5: continue
            if v not in seen:
                seen.add(v)
                found.append(v)
    return found[:8]

def fix_img(src):
    if not src: return ""
    if src.startswith("//"): return "https:" + src
    if src.startswith("http"): return src
    return BASE_URL + ("" if src.startswith("/") else "/") + src

def parse_products_from_page(html):
    products = []
    rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, re.IGNORECASE)
    for row in rows:
        cells_raw = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.IGNORECASE)
        cells = [strip_tags(c) for c in cells_raw]
        if len(cells) < 2: continue
        text = " ".join(cells)
        price = parse_price(text)
        if price < 5000: continue
        code_m = re.search(r"\b([A-Z]{2,}[\-\/\.][A-Z0-9\-\/\.]{2,})\b", text)
        code = code_m.group(1) if code_m else cells[0]
        code_pat = re.compile(r'^[A-Z]{2,}[\-\/\.]', re.IGNORECASE)
        name = ""
        best_len = 0
        for c in cells:
            if re.match(r"^[\d\$]", c): continue
            if code_pat.match(c) and len(c) < 20: continue
            if len(c) > best_len:
                best_len = len(c)
                name = c
        if not name: name = code
        img_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', "".join(cells_raw), re.IGNORECASE)
        img = fix_img(img_m.group(1) if img_m else "")
        products.append({"name": name, "code": code, "img": img, "precioBase": price})
    return products

def scrape_keyword(opener, kw, label=""):
    results = []
    seen = set()
    pg = 1
    pag_param = "pg"
    while pg <= 100:
        url = f"{BASE_URL}/?mod=search&ty=pro&kw={urllib.parse.quote(kw)}&{pag_param}={pg}"
        html = fetch(opener, url)
        if not html: break
        if pg == 1:
            pag_m = re.search(r'href="[^"]*mod=search[^"]*kw=[^"]*&([a-z_]+)=(\d+)"', html, re.IGNORECASE)
            if pag_m:
                pag_param = pag_m.group(1)
        prods = parse_products_from_page(html)
        if not prods: break
        added = 0
        for p in prods:
            key = p["code"].strip()
            if key and key not in seen:
                seen.add(key)
                results.append(p)
                added += 1
        if added == 0: break
        pg += 1
        time.sleep(0.3)
    if label:
        print(f"  [{label}] -> {len(results)} productos ({pg-1} pags)")
    return results

# Listado amplio de piezas de automóvil para cubrir todo el catálogo
KEYWORDS_EXTRA = [
    # Arranque y carga eléctrica
    "alternador","bendix","inducido","carbon","escobilla","regulador voltaje",
    "motor arranque","armadura","porta escobillas","polea alternador",
    # Filtros
    "filtro aceite","filtro aire","filtro petroleo","filtro gasolina",
    "filtro combustible","filtro habitaculo","filtro polen",
    # Correas y distribución
    "correa distribucion","correa poly v","tensor distribucion","kit distribucion",
    "bomba agua","termostato","polea tensora","correa accesorios",
    # Frenos
    "pastilla freno","balata freno","disco freno","cilindro freno","bomba freno",
    "liquido frenos","caliper","mordaza freno","zapata","servo freno",
    # Suspensión y dirección
    "amortiguador","resorte suspension","horquilla","rotula","buje suspension",
    "barra estabilizadora","terminal direccion","cremallera direccion",
    "bomba direccion","caja direccion","brazo pitman","columna direccion",
    "kit reparacion suspension","barra torsion","muelle",
    # Embrague
    "disco embrague","prensa embrague","rodamiento embrague","kit embrague",
    "piloto embrague","volante bimasa","cilindro embrague","actuador embrague",
    # Motor
    "bujia","cable bujia","bobina encendido","distribuidor encendido",
    "junta culata","kit junta motor","sello valvula","anillo piston",
    "cojinete biela","cojinete bancada","leva","empuje axial","tapa distribucion",
    # Inyección y combustible
    "inyector","bomba combustible","regulador presion","caudalimetro",
    "cuerpo aceleracion","sensor oxigeno","sonda lambda","egr","turbocompresor",
    # Electroventilador
    "electroventilador","ventilador radiador","moto ventilador","electrico radiador",
    # Refrigeración
    "radiador","tapa radiador","manguera radiador","deposito expansion","bomba agua",
    # Transmisión
    "caja cambios","sincronizador","horquilla cambio","palier","junta homoinetica",
    "junta tripoide","guardapolvo palier","corona diferencial","semieje",
    # Carrocería y luces
    "faro delantero","faro trasero","piloto trasero","plumilla parabrisas",
    "motor limpia parabrisas","tapa combustible","espejo lateral","manilla puerta",
    # Sensores y electrónico
    "sensor temperatura","sensor presion aceite","sensor abs","sensor rpm",
    "sensor ciguenal","sensor arbol levas","modulo encendido","ecu",
    # Varios
    "aceite motor","aceite transmision","correa ventilador","kit reparacion",
    "reten aceite","retén ciguenal","sello transmision","fusible","rele relay",
]

def main():
    print(f"[{datetime.now().isoformat()}] Iniciando scraper Quiroz Chile...")

    opener = make_session()
    home_html = login(opener)

    if len(home_html) < 8000:
        print(f"[WARN] Login fallido -- html corto:\n{home_html[:2000]}")
        sys.exit(1)

    print("\n=== FASE 1: Categorias del sitio ===")
    categories = extract_categories(home_html)
    if not categories:
        categories = ["alternador","bendix","filtro","carbon","inducido",
                      "electroventilador","bomba","bujia","fusible","horquilla"]

    # Combinar con keywords extra, sin duplicados
    all_keywords = list(categories)
    for kw in KEYWORDS_EXTRA:
        if kw not in all_keywords:
            all_keywords.append(kw)
    print(f"[fase1] {len(all_keywords)} keywords a buscar")

    all_products = {}  # code -> producto

    for cat in all_keywords:
        prods = scrape_keyword(opener, cat, label=f"kw:{cat}")
        for p in prods:
            key = p["code"]
            if key not in all_products:
                p["categoria"] = cat
                p["vehiculos"] = []
                all_products[key] = p

    print(f"\n[fase1] {len(all_products)} productos únicos por keyword")

    print("\n=== FASE 2: Extraer vehículos y OEM desde nombre ===")
    for key, p in all_products.items():
        tags = extraer_vehiculos(p.get("name", ""))
        if tags:
            p["vehiculos"] = tags
        oems = extraer_oem(p.get("name", ""))
        if oems:
            p["oem"] = oems

    final = list(all_products.values())
    for p in final:
        p["precio"] = math.ceil(p["precioBase"] * MARKUP / 100) * 100
        del p["precioBase"]

    con_vehiculo = sum(1 for p in final if p.get("vehiculos"))
    con_oem      = sum(1 for p in final if p.get("oem"))
    print(f"[fase2] {con_vehiculo} con vehículo | {con_oem} con OEM detectado")

    output = {
        "ok":         True,
        "total":      len(final),
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "products":   final
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(final)} productos guardados en {OUT_FILE}")

    if not final:
        with open("quiroz_diag.html", "w", encoding="utf-8") as f:
            f.write(home_html)
        sys.exit(1)

if __name__ == "__main__":
    main()
