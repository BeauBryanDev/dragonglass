
#%%
import json
import os
import re
import time
from collections import Counter

import requests

#%%
RAW = "data/raw"
CLEAN = "data/clean"
CORPUS_PATH = os.path.join(CLEAN, "corpus.jsonl")
WIKI_PATH = os.path.join(RAW, "wikitext.jsonl")
WIKI_FAILED = os.path.join(RAW, "failed_wikitext.jsonl")
REDIRECTS_PATH = os.path.join(RAW, "redirects.jsonl")
STRUCT_PATH = os.path.join(CLEAN, "wiki_structured.jsonl")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongOfIceAndFireMind; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5
MAX_RETRIES = 4
BATCH = 20
REDIRECT_BATCH = 50


#%%
def api_get(params):
    params = {**params, "format": "json", "formatversion": 2}
    resp = requests.get(API, params=params, 
                        headers=HEADERS,
                        timeout=120)
    resp.raise_for_status()
    data = resp.json()
    
    if "error" in data:
        raise RuntimeError(data["error"].get("info", data["error"]))
    
    return data


def query_all(params):
    params = dict(params)
    pages, back = {}, {}
    while True:
        data = api_get(params)
        query = data.get("query", {})
        
        for item in query.get("normalized", []) + query.get("redirects", []):
            
            back[item["to"]] = back.get(item["from"], item["from"])
            
        for page in query.get("pages", []):
            
            merged = pages.setdefault(page["title"], page)
            
            if merged is not page:
                
                for key in ("revisions", "redirects"):
                    
                    merged.setdefault(key, []).extend(page.get(key, []))
                    
        if "continue" not in data:
            return pages, back
        
        params.update(data["continue"])
        time.sleep(DELAY)


def with_retries(fn, arg):
    
    delay = DELAY
    for attempt in range(MAX_RETRIES):
        try:
            return fn(arg), None
        
        except Exception as exc:
            if attempt == MAX_RETRIES - 1:
                return None, repr(exc)
            time.sleep(delay)
            delay *= 3
            
    return None, "unreachable"


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
                
            except json.JSONDecodeError:
                continue
    return rows


def fetch_batch(titles):
    pages, back = query_all({
        "action": "query",
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "titles": "|".join(titles),
        "redirects": 1,
    })
    records, missing = [], set(titles)
    for title, page in pages.items():
        if page.get("missing") or page.get("invalid") or not page.get("revisions"):
            continue
        rev = page["revisions"][0]
        requested = back.get(title, title)
        records.append({
            "title": title,
            "requested_title": requested,
            "pageid": page["pageid"],
            "revid": rev["revid"],
            "timestamp": rev["timestamp"],
            "wikitext": rev["slots"]["main"]["content"],
        })
        missing.discard(requested)
    return records, sorted(missing)


def fetch_redirects(titles):
    pages, _ = query_all({
        "action": "query",
        "prop": "redirects",
        "rdprop": "title",
        "rdnamespace": 0,
        "rdlimit": "max",
        "titles": "|".join(titles),
    })
    return [
        {"title": t, "aliases": sorted({r["title"] for r in p.get("redirects", [])})
         } for t, p in pages.items() if not p.get("missing") and not p.get("invalid")
    ]


#%%
with open(CORPUS_PATH, encoding="utf-8") as f:
    titles = [json.loads(line)["title"] for line in f if line.strip()]

done = {r["requested_title"] for r in read_jsonl(WIKI_PATH) + read_jsonl(WIKI_FAILED)}
pending = [t for t in titles if t not in done]
batches = [pending[i:i + BATCH] for i in range(0, len(pending), BATCH)]

print(len(titles), len(done), len(pending), "batches", len(batches))


#%%
start = time.time()
saved = failed = 0

with open(WIKI_PATH, "a", encoding="utf-8") as out_file, \
     open(WIKI_FAILED, "a", encoding="utf-8") as fail_file:

    for i, batch in enumerate(batches, 1):
        
        result, error = with_retries(fetch_batch, batch)
        records, missing = result if result else ([], batch)

        for record in records:
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved += 1
        for title in missing:
            fail_file.write(json.dumps({"requested_title": title, 
                                        "error": error or "missing"}) + "\n"
                            )
            failed += 1
        out_file.flush()
        fail_file.flush()

        if i % 10 == 0:
            left = (time.time() - start) / i * (len(batches) - i) / 60
            print(f"{i}/{len(batches)} saved={saved} failed={failed} eta_min={left:.1f}")

        time.sleep(DELAY)

print("done", saved, "failed", failed)


#%%
done_redirects = {r["title"] for r in read_jsonl(REDIRECTS_PATH)}
pending_redirects = [t for t in titles if t not in done_redirects]
redirect_batches = [pending_redirects[i:i + REDIRECT_BATCH]
                    for i in range(0, len(pending_redirects), REDIRECT_BATCH)]
print(len(pending_redirects), "batches", len(redirect_batches))

with open(REDIRECTS_PATH, "a", encoding="utf-8") as out_file:
    for i, batch in enumerate(redirect_batches, 1):
        rows, error = with_retries(fetch_redirects, batch)
        if rows is None:
            print("failed batch", i, error)
        for row in rows or []:
            out_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        out_file.flush()
        time.sleep(DELAY)

print("aliases", sum(len(r["aliases"]) for r in read_jsonl(REDIRECTS_PATH)))


#%%
BOOK_CODES = {"AGOT": 1, "ACOK": 2, "ASOS": 3, "AFFC": 4, "ADWD": 5, "TWOW": 6}
INFOBOXES = ("infobox", "noble house", "battlebox")
NOTE_TEMPLATES = ("refn", "efn")
SKIP_KEYS = {"image", "image_caption", "caption", "textcolor", "bgcolor", "bordercolor", "page"}
LIST_SECTIONS = (
    "character list", "characters appearing", "mentions", "places and terms", "place and terms",
    "terms and places", "places, houses", "houses, objects",
)
CAST_LABELS = {
    "appears": "appearing",
    "character list appearing/mentioned": "cast_unsplit",
    "characters appearing/mentioned": "cast_unsplit",
}
NON_ARTICLE = ("file:", "image:", "media:", "category:", "template:", "w:", "wikipedia:")

HEAD = re.compile(r"^(=+)\s*(.+?)\s*\1\s*$", re.M)
REF = re.compile(r"\{\{\s*ref\s*\|\s*([^|{}]+?)\s*\|\s*([^|{}]+?)\s*\}\}", re.I)
LINK = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]*)?\]\]")
INNER_TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")
INNER_LINK = re.compile(r"\[\[([^\[\]]*)\]\]")
REF_TAG = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"<[^>]+>")
ITEM_SPLIT = re.compile(r"<br\s*/?>|\n\s*\*", re.I)
BOLD_LABEL = re.compile(r"'''([^'\n]+?):?'''")


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


def template_name(body):
    return split_top(body)[0].strip().lower().removeprefix("template:").replace("_", " ")


def drop_templates(text, drop):
    out, depth, start, last, i = [], 0, 0, 0, 0
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
            if depth == 0 and drop(template_name(text[start + 2:i - 2])):
                out.append(text[last:start])
                last = i
        else:
            i += 1
    return "".join(out) + text[last:]


def is_note(name):
    return name in NOTE_TEMPLATES


def is_infobox(name):
    return name.startswith(INFOBOXES)


def link_target(raw):
    target = raw.split("#")[0].replace("_", " ").strip().lstrip(":")
    if not target or target.lower().startswith(NON_ARTICLE):
        return None
    return target[0].upper() + target[1:]


def links_in(text):
    text = drop_templates(REF_TAG.sub("", text), is_note)
    targets = (link_target(m) for m in LINK.findall(text))
    return list(dict.fromkeys(t for t in targets if t))


def refs_in(text):
    return [[code.upper(), chapter] for code, chapter in REF.findall(text)]


def books_of(refs):
    return sorted({BOOK_CODES[code] for code, _ in refs if code in BOOK_CODES})


def template_text(body):
    parts = [p.strip() for p in body.split("|")]
    name = parts[0].lower()
    if name == "date" and len(parts) > 1:
        return f"{parts[1]} AC"
    if name == "s" and len(parts) > 1:
        return f"({parts[1]})"
    if name == "!":
        return "|"
    return ""


def link_label(body):
    parts = body.split("|")
    target = parts[0].strip().lstrip(":").lower()
    if target.startswith(("file:", "image:", "media:", "category:")):
        return ""
    return parts[-1] if len(parts) > 1 and parts[-1].strip() else parts[0].lstrip(":")


def strip_markup(text):
    text = REF_TAG.sub("", COMMENT.sub("", text))
    for pattern, repl in ((INNER_TEMPLATE, template_text), (INNER_LINK, link_label)):
        prev = None
        while prev != text:
            prev = text
            text = pattern.sub(lambda m: repl(m.group(1)), text)
    text = TAG.sub("", text).replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", text).strip(" ,;")


def parse_value(value):
    items = []
    value = drop_templates(REF_TAG.sub("", COMMENT.sub("", value)), is_note)
    for raw in ITEM_SPLIT.split(value):
        text, links = strip_markup(raw), links_in(raw)
        if text or links:
            items.append({"text": text, 
                          "links": links, 
                          "refs": refs_in(raw)}
                         )
            
    return items


def parse_infoboxes(text):
    boxes = []
    for body in top_templates(text):
        name = template_name(body)
        if not is_infobox(name):
            continue
        parts = split_top(body)
        fields = {}
        
        for part in parts[1:]:
            key, sep, value = part.partition("=")
            key = key.strip().lower().replace(" ", "_")
            
            if not sep or key in SKIP_KEYS:
                continue
            
            items = parse_value(value)
            
            if items:
                fields.setdefault(key, []).extend(items)
        boxes.append({"template": name, "fields": fields})
        
    return boxes


def section_spans(text):
    marks = list(HEAD.finditer(text))
    spans = [([], text[: marks[0].start()] if marks else text)]
    stack = []
    for k, m in enumerate(marks):
        stack = stack[: max(len(m.group(1)) - 2, 0)] + [strip_markup(m.group(2))]
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        spans.append((list(stack), text[m.end():end]))
    return spans


def cast_lists(name, body):
    pieces = BOLD_LABEL.split(body)
    if len(pieces) == 1:
        return {name: links_in(body)}
    return {label.strip().lower(): links_in(block) for label, block in zip(pieces[1::2], pieces[2::2])}


def split_pov(lists, infoboxes):
    if "cast_unsplit" not in lists:
        return
    pov = [link for box in infoboxes for item in box["fields"].get("pov", []) for link in item["links"]]
    lists["appearing"] = list(dict.fromkeys(lists.get("appearing", []) + pov))
    lists["cast_unsplit"] = [t for t in lists["cast_unsplit"] if t not in pov]


def structure(rec):
    sections, lists = [], {}
    prose = drop_templates(rec["wikitext"], is_infobox)
    for path, body in section_spans(prose):
        refs = refs_in(body)
        books = books_of(refs)
        sections.append({
            "path": path,
            "books": books,
            "max_book": books[-1] if books else None,
            "refs": refs,
            "links": links_in(body),
        })
        if path and path[-1].lower().startswith(LIST_SECTIONS):
            for label, links in cast_lists(path[-1].lower(), body).items():
                lists.setdefault(CAST_LABELS.get(label, label), []).extend(links)
    infoboxes = parse_infoboxes(rec["wikitext"])
    split_pov(lists, infoboxes)
    return {
        "title": rec["title"],
        "pageid": rec["pageid"],
        "revid": rec["revid"],
        "infoboxes": infoboxes,
        "sections": sections,
        "lists": lists,
    }


#%%
records = read_jsonl(WIKI_PATH)
structured = [structure(r) for r in records]

with open(STRUCT_PATH, "w", encoding="utf-8") as f:
    for row in structured:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

templates = Counter(b["template"] for r in structured for b in r["infoboxes"])
sections = [s for r in structured for s in r["sections"]]
print(len(structured), "pages |", sum(not r["infoboxes"] for r in structured), "without infobox")
print(templates.most_common(25))
print(len(sections), "sections |", sum(s["max_book"] is not None for s in sections), "with a book ref")
print(Counter(label for r in structured for label in r["lists"]).most_common(10))
