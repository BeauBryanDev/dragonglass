
#%%
import json
import os
import re
import time
from collections import Counter

import requests

RAW = "data/raw"
OUT_PATH = os.path.join(RAW, "wikitext_probe.jsonl")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongOfIceAndFireMind; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5

PROBE = [
    "Roose Bolton",
    "House Bolton",
    "Dreadfort",
    "Battle in the Whispering Wood",
    "A Storm of Swords-Chapter 51",
]

LINK = re.compile(r"\[\[([^\]|#]+)")
HEAD = re.compile(r"^(=+)\s*(.+?)\s*=+\s*$", re.M)
INFOBOXES = ("infobox", "noble house", "battlebox")
REF = re.compile(r"\{\{[Rr]ef\|([A-Za-z]+)\|([^|}]+)")


#%%
def fetch_wikitext(title):
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": title,
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    resp = requests.get(API, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    page = resp.json()["query"]["pages"][0]
    if page.get("missing") or page.get("invalid"):
        return None
    return {
        "title": page["title"],
        "pageid": page["pageid"],
        "requested_title": title,
        "wikitext": page["revisions"][0]["slots"]["main"]["content"],
    }


def top_templates(text):
    out, depth, start, i = [], 0, 0, 0
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            if depth == 0:
                start = i
            depth += 1
            i += 2
        elif pair == "}}" and depth:
            depth -= 1
            i += 2
            if depth == 0:
                out.append(text[start + 2:i - 2])
        else:
            i += 1
    return out


def split_top(body):
    parts, cur, depth, i = [], [], 0, 0
    while i < len(body):
        pair = body[i:i + 2]
        if pair in ("{{", "[["):
            depth += 1
            cur.append(pair)
            i += 2
        elif pair in ("}}", "]]") and depth:
            depth -= 1
            cur.append(pair)
            i += 2
        elif body[i] == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(body[i])
            i += 1
    parts.append("".join(cur))
    return parts


def parse_template(body):
    parts = split_top(body)
    fields = {}
    for n, part in enumerate(parts[1:], 1):
        key, sep, value = part.partition("=")
        if sep:
            fields[key.strip()] = value.strip()
        else:
            fields[str(n)] = part.strip()
    return parts[0].strip(), fields


#%%
def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


pages = read_jsonl(OUT_PATH)
done = {p["requested_title"] for p in pages}
with open(OUT_PATH, "a", encoding="utf-8") as out_file:
    for title in (t for t in PROBE if t not in done):
        record = fetch_wikitext(title)
        if record is None:
            print("missing", title)
        else:
            pages.append(record)
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        time.sleep(DELAY)

print(len(pages), "pages saved to", OUT_PATH)


#%%
for page in pages:
    text = page["wikitext"]
    print("#" * 80)
    print(page["title"], "| chars", len(text))
    names = Counter(parse_template(b)[0].lower() for b in top_templates(text))
    print("  templates:", dict(names.most_common(12)))
    refs = REF.findall(text)
    print("  refs:", len(refs), dict(Counter(book for book, _ in refs)))
    for body in top_templates(text):
        name, fields = parse_template(body)
        if not name.lower().removeprefix("template:").startswith(INFOBOXES):
            continue
        print("  {{" + name + "}}", len(fields), "fields")
        for key, value in fields.items():
            flat = value.replace("\n", " ")
            print(f"    {key:<18} {flat[:90]}")
            links = LINK.findall(value)
            if links:
                print(f"    {'':<18} -> {links[:8]}")
    print("  sections:", [m.group(2) for m in HEAD.finditer(text)])


#%%
chapter = next(p for p in pages if p["title"].startswith("A Storm of Swords-"))
for m in HEAD.finditer(chapter["wikitext"]):
    if m.group(2).lower().startswith(("character", "place")):
        start = m.end()
        nxt = HEAD.search(chapter["wikitext"], start)
        block = chapter["wikitext"][start:nxt.start() if nxt else None]
        print("==", m.group(2), "| links", len(LINK.findall(block)))
        print(block[:800])
