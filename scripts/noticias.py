#!/usr/bin/env python3
"""Busca as principais manchetes de portais confiáveis (RSS) e salva em noticias.json.
Roda no GitHub Actions a cada hora. Só usa a biblioteca padrão do Python."""
import json, re, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

def gnews(site):
    q = urllib.parse.quote(f"site:{site} when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"

# página inicial de cada portal: as manchetes em destaque vêm primeiro no HTML
CAPAS = {
    "g1": "https://g1.globo.com/",
    "Estadão": "https://www.estadao.com.br/",
    "Folha": "https://www.folha.uol.com.br/",
    "TechTudo": "https://www.techtudo.com.br/",
    "Olhar Digital": "https://olhardigital.com.br/",
    "ge": "https://ge.globo.com/",
    "O São Gonçalo": "https://www.osaogoncalo.com.br/",
    "O Fluminense": "https://www.ofluminense.com.br/",
    "Jovem Pan": "https://jovempan.com.br/",
}
RE_A = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.S | re.I)
RE_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
RE_TIT = re.compile(r'(?:title|aria-label)\s*=\s*["\']([^"\']{25,220})["\']', re.I)
RUIDO = re.compile(r"assine|newsletter|podcast|^v[ií]deos?\b|ao vivo|cookies|termos de uso|publicidade|ofertas? do dia|cupo(m|ns)|melhores promoções|_edi[cç][aã]o de", re.I)

def eh_materia(url, dominio):
    u = urllib.parse.urlparse(url)
    if dominio not in u.netloc:
        return False
    if re.search(r"edicoes|edicao-|/edicao|/tag/|/autor/|/categoria/", u.path, re.I):
        return False
    caminho = u.path
    if caminho.endswith((".ghtml", ".shtml")) or re.search(r"/20\d\d/\d\d/", caminho):
        return True
    ult = [x for x in caminho.split("/") if x]
    return len(ult) >= 1 and ult[-1].count("-") >= 4

def destaques(nome, dominio, limite=12):
    raw = baixar(CAPAS[nome]).decode("utf-8", "replace")
    out, vistos = [], set()
    for attrs, inner in RE_A.findall(raw):
        m = RE_HREF.search(attrs)
        if not m:
            continue
        link = urllib.parse.urljoin(CAPAS[nome], html.unescape(m.group(1))).split("#")[0]
        if not eh_materia(link, dominio) or link in vistos:
            continue
        # só o título: ignora "chapéu"/seção/nome do colunista que vêm em outros blocos do link
        mh = re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", inner, re.S | re.I)
        if mh:
            titulo = limpa(mh.group(1))
        else:
            partes = [limpa(x) for x in re.split(r"<[^>]+>", inner)]
            titulo = max(partes, key=len) if partes else ""
        if len(titulo) < 30:
            mt = RE_TIT.search(attrs)
            titulo = limpa(mt.group(1)) if mt else titulo
        if not (30 <= len(titulo) <= 220) or RUIDO.search(titulo):
            continue
        vistos.add(link)
        out.append({"fonte": nome, "titulo": titulo, "resumo": "", "link": link, "data": None})
        if len(out) >= limite:
            break
    return out

FONTES = [
    ("g1",            "#c4170c", ["https://g1.globo.com/rss/g1/"], "g1.globo.com"),
    ("Estadão",       "#1d3f6e", ["https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/brasil/",
                                  "https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/economia/"], "estadao.com.br"),
    ("Folha",         "#00618a", ["https://feeds.folha.uol.com.br/emcimadahora/rss091.xml"], "folha.uol.com.br"),
    ("TechTudo",      "#0a4ea8", ["https://pox.globo.com/rss/techtudo/"], "techtudo.com.br"),
    ("Olhar Digital", "#0d6efd", ["https://olhardigital.com.br/feed/"], "olhardigital.com.br"),
    ("ge",            "#06aa48", ["https://ge.globo.com/rss/ge/"], "ge.globo.com"),
    ("O São Gonçalo", "#0b4f9c", ["https://www.osaogoncalo.com.br/feed/", "https://www.osaogoncalo.com.br/rss"], "osaogoncalo.com.br"),
    ("O Fluminense",  "#1b3f8b", ["https://www.ofluminense.com.br/feed/", "https://www.ofluminense.com.br/rss"], "ofluminense.com.br"),
    ("Jovem Pan",     "#d71920", ["https://jovempan.com.br/feed"], "jovempan.com.br"),
]
POR_FONTE = 6
UA = {"User-Agent": "Mozilla/5.0 (JaylsonStore vitrine; +https://jaylsonstore.github.io/loja/)"}

def baixar(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def limpa(txt, n=None):
    txt = html.unescape(re.sub(r"<[^>]+>", " ", txt or ""))
    txt = re.sub(r"\s+", " ", txt).strip()
    if n and len(txt) > n:
        txt = txt[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return txt

def data(item):
    for tag in ("pubDate", "{http://purl.org/dc/elements/1.1/}date", "published", "updated"):
        el = item.find(tag)
        if el is not None and el.text:
            try:
                d = parsedate_to_datetime(el.text.strip())
            except Exception:
                try: d = datetime.fromisoformat(el.text.strip().replace("Z", "+00:00"))
                except Exception: continue
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None

def ler(conteudo, nome, google=False):
    raiz = ET.fromstring(conteudo)
    itens = raiz.findall(".//item")
    out = []
    for it in itens:
        titulo = limpa(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        resumo = "" if google else limpa(it.findtext("description"), 170)
        if google:
            titulo = re.sub(r"\s+-\s+[^-]+$", "", titulo)  # tira " - Nome do site"
        if resumo and resumo.lower().startswith(titulo.lower()[:40]):
            resumo = ""
        d = data(it)
        if re.match(r"^(V[IÍ]DEOS?|AO VIVO|PODCAST|PLAYLIST)\b", titulo, re.I):
            continue  # pula chamadas de vídeo/programa
        if titulo and link:
            out.append({"fonte": nome, "titulo": titulo, "resumo": resumo, "link": link,
                        "data": d.isoformat() if d else None})
    return out

def main():
    agora = datetime.now(timezone.utc)
    todas, log = [], []
    for nome, cor, urls, site in FONTES:
        capa = []
        try:
            capa = destaques(nome, site)
            log.append(f"{nome}: {len(capa)} destaques na capa")
        except Exception as e:
            log.append(f"{nome}: capa falhou ({type(e).__name__})")
        itens = []
        for u in urls:
            try:
                itens += ler(baixar(u), nome)
            except Exception as e:
                log.append(f"{nome}: falhou {u} ({type(e).__name__})")
        if not itens:
            try:
                itens = ler(baixar(gnews(site)), nome, google=True)
                log.append(f"{nome}: usando Google Notícias")
            except Exception as e:
                log.append(f"{nome}: sem notícias ({type(e).__name__})")
        # completa os destaques da capa com resumo/horário do RSS (mesmo link ou mesmo título)
        por_link = {i["link"].split("?")[0]: i for i in itens}
        por_tit = {i["titulo"].lower()[:50]: i for i in itens}
        for c in capa:
            r = por_link.get(c["link"].split("?")[0]) or por_tit.get(c["titulo"].lower()[:50])
            if r:
                c["resumo"] = r["resumo"] or c["resumo"]; c["data"] = r["data"]
        def fresco(i, horas):
            if i["data"]:
                return agora - datetime.fromisoformat(i["data"]) < timedelta(hours=horas)
            m = re.search(r"/(20\d\d)/(\d\d)/(\d\d)/", i["link"])  # data no endereço da matéria
            if m:
                try: return agora.date() - datetime(*map(int, m.groups())).date() <= timedelta(days=1)
                except ValueError: pass
            m = re.search(r"/(20\d\d)/(\d\d)/", i["link"])
            if m and (int(m.group(1)), int(m.group(2))) < (agora.year, agora.month) and agora.day > 2:
                return False
            return True
        # 1º: destaques da capa (na ordem do site); 2º: as mais recentes do RSS
        recentes = [i for i in itens if fresco(i, 12)] or [i for i in itens if fresco(i, 36)]
        recentes.sort(key=lambda i: i["data"] or "", reverse=True)
        vistos, sel = set(), []
        for i in [c for c in capa if fresco(c, 12)] + recentes:
            k = i["titulo"].lower()[:60]
            if k in vistos: continue
            vistos.add(k); i["cor"] = cor; sel.append(i)
            if len(sel) >= POR_FONTE: break
        todas += sel
        log.append(f"{nome}: {len(sel)} manchetes")
    # intercala as fontes (uma de cada por vez)
    por = {}
    for i in todas: por.setdefault(i["fonte"], []).append(i)
    mix = []
    while any(por.values()):
        for f in list(por):
            if por[f]: mix.append(por[f].pop(0))
    with open("noticias.json", "w", encoding="utf-8") as fp:
        json.dump({"atualizado": agora.isoformat(), "itens": mix}, fp, ensure_ascii=False, indent=1)
    print("\n".join(log)); print(f"Total: {len(mix)}")

if __name__ == "__main__":
    main()
