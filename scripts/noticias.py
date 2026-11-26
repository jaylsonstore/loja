#!/usr/bin/env python3
"""Busca as principais manchetes de portais confiáveis (RSS) e salva em noticias.json.
Roda no GitHub Actions a cada hora. Só usa a biblioteca padrão do Python."""
import json, re, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

def gnews(site):
    q = urllib.parse.quote(f"site:{site} when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"

FONTES = [
    ("g1",            "#c4170c", ["https://g1.globo.com/rss/g1/"], "g1.globo.com"),
    ("Estadão",       "#1d3f6e", ["https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/brasil/",
                                  "https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/economia/"], "estadao.com.br"),
    ("Folha",         "#00618a", ["https://feeds.folha.uol.com.br/emcimadahora/rss091.xml"], "folha.uol.com.br"),
    ("TechTudo",      "#0a4ea8", ["https://pox.globo.com/rss/techtudo/"], "techtudo.com.br"),
    ("Olhar Digital", "#0d6efd", ["https://olhardigital.com.br/feed/"], "olhardigital.com.br"),
    ("ge",            "#06aa48", ["https://ge.globo.com/rss/ge/"], "ge.globo.com"),
]
POR_FONTE = 5
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
        if titulo and link:
            out.append({"fonte": nome, "titulo": titulo, "resumo": resumo, "link": link,
                        "data": d.isoformat() if d else None})
    return out

def main():
    agora = datetime.now(timezone.utc)
    todas, log = [], []
    for nome, cor, urls, site in FONTES:
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
        vistos, sel = set(), []
        recentes = [i for i in itens if not i["data"] or agora - datetime.fromisoformat(i["data"]) < timedelta(hours=36)]
        recentes.sort(key=lambda i: i["data"] or "", reverse=True)
        for i in recentes:
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
