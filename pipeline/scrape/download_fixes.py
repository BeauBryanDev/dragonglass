
#%%
import json
import os
import time

import requests

BASE = "data"
RAW = os.path.join(BASE, "raw")
OUT_PATH = os.path.join(RAW, "pages_fixes.jsonl")
HINTS_PATH = os.path.join(RAW, "search_hints.jsonl")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongOfIceAndFireMind; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5
MAX_RETRIES = 4

DISAMBIG = ["Aegon Targaryen", "Byron", "Elwood", "Grazdan", "Leo Tyrell",
            "Lew", "Lyonel", "Maris", "Owen", "Walton"]
ACCEPTED = ["Yezzan zo Qaggaz", "Torwynd", "Battle at the burning septry", "Pate (ranger)"]
SEARCH_ONLY = ["Elder Brother", "Lamprey", "Squirrel", "Blane", "Myles"]


#%%
def api_get(params):
    resp = requests.get(API, params={**params, "format": "json"}, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_page(title):
    params = {
        "action": "query",
        "prop": "extracts|links|categories|info",
        "explaintext": 1,
        "exsectionformat": "wiki",
        "pllimit": "max",
        "plnamespace": 0,
        "cllimit": "max",
        "inprop": "url",
        "titles": title,
        "redirects": 1,
    }
    record = None
    while True:
        data = api_get(params)
        page = next(iter(data["query"]["pages"].values()))
        if "missing" in page or "invalid" in page:
            return None
        if record is None:
            record = {
                "title": page["title"],
                "pageid": page["pageid"],
                "url": page.get("fullurl"),
                "text_wiki": page.get("extract", ""),
                "links": [],
                "categories": [],
            }
        record["links"] += [l["title"] for l in page.get("links", [])]
        record["categories"] += [c["title"] for c in page.get("categories", [])]
        if "continue" not in data:
            record["links"] = sorted(set(record["links"]))
            record["categories"] = sorted(set(record["categories"]))
            return record
        params.update(data["continue"])
        time.sleep(DELAY)


def search_titles(term):
    data = api_get({
        "action": "query",
        "list": "search",
        "srsearch": term,
        "srnamespace": 0,
        "srlimit": 5,
    })
    return [hit["title"] for hit in data["query"]["search"]]


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


#%%
pages = {}
for fname in ("pages.jsonl", "pages_extra.jsonl", "pages_missing.jsonl"):
    for row in read_jsonl(os.path.join(RAW, fname)):
        pages[row["title"]] = row
        pages[row["requested_title"]] = row

targets = list(ACCEPTED)
for name in DISAMBIG:
    targets += [l for l in pages[name]["links"] if name.lower() in l.lower()]

targets = [t for t in dict.fromkeys(targets) if t not in pages]
done_pages = {r["requested_title"] for r in read_jsonl(OUT_PATH)}
pending = [t for t in targets if t not in done_pages]

print(len(targets), len(pending))


#%%
found = 0

with open(OUT_PATH, "a", encoding="utf-8") as out_file:
    for title in pending:
        record, error = with_retries(fetch_page, title)
        if record is None:
            print("missing", title, error)
        else:
            record["requested_title"] = title
            record["kind"] = "fix"
            record["chars"] = len(record["text_wiki"])
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            found += 1
        time.sleep(DELAY)

print("pages", found)


#%%
done_hints = {r["name"] for r in read_jsonl(HINTS_PATH)}

with open(HINTS_PATH, "a", encoding="utf-8") as hint_file:
    for name in SEARCH_ONLY:
        if name in done_hints:
            continue
        hits, error = with_retries(search_titles, name)
        hint_file.write(json.dumps({"name": name, "hits": hits or [], "error": error},
                                   ensure_ascii=False) + "\n")
        hint_file.flush()
        print(name, hits, error)
        time.sleep(DELAY)
