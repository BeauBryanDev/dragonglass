
#%%
import json
import os
import time

import pandas as pd
import requests

BASE = os.path.expanduser("~/IceAndFire")
RAW = os.path.join(BASE, "raw")
CLEAN = os.path.join(BASE, "clean")
OUT_PATH = os.path.join(RAW, "pages_missing.jsonl")
MISS_PATH = os.path.join(RAW, "missing_candidates.jsonl")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongOfIceAndFireMind; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5
MAX_RETRIES = 4


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


def search_candidates(title):
    data = api_get({
        "action": "query",
        "list": "search",
        "srsearch": title,
        "srnamespace": 0,
        "srlimit": 3,
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
have = set()
for name in ("pages.jsonl", "pages_extra.jsonl"):
    for row in read_jsonl(os.path.join(RAW, name)):
        have.add(row["title"])
        have.add(row["requested_title"])

chars = pd.read_json(os.path.join(CLEAN, "characters.jsonl"), lines=True)
battles = pd.read_json(os.path.join(CLEAN, "battles.jsonl"), lines=True)

targets = {}
for kind, names in (("character", chars["name"]), ("battle", battles["name"])):
    for name in names:
        if name not in have:
            targets.setdefault(name, kind)

done = {r["requested_title"] for r in read_jsonl(OUT_PATH) + read_jsonl(MISS_PATH)}
pending = [t for t in targets if t not in done]

print(len(targets), len(done), len(pending))


#%%
start = time.time()
found = 0
missing = 0

with open(OUT_PATH, "a", encoding="utf-8") as out_file, \
     open(MISS_PATH, "a", encoding="utf-8") as miss_file:

    for i, title in enumerate(pending, 1):
        record, error = with_retries(fetch_page, title)

        if record is not None:
            record["requested_title"] = title
            record["kind"] = targets[title]
            record["chars"] = len(record["text_wiki"])
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            found += 1
        else:
            candidates, search_error = [], None
            if error is None:
                time.sleep(DELAY)
                candidates, search_error = with_retries(search_candidates, title)
            miss_file.write(json.dumps({
                "requested_title": title,
                "kind": targets[title],
                "error": error or search_error,
                "candidates": candidates or [],
            }, ensure_ascii=False) + "\n")
            miss_file.flush()
            missing += 1

        if i % 50 == 0:
            left = (time.time() - start) / i * (len(pending) - i) / 60
            print(f"{i}/{len(pending)} found={found} missing={missing} eta_min={left:.1f}")

        time.sleep(DELAY)


print("done", found, "missing", missing)
