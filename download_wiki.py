#%%
import json
import os
import time

import requests

BASE = os.path.expanduser("~/IceAndFire")
RAW = os.path.join(BASE, "raw")
PAGES_PATH = os.path.join(RAW, "pages.jsonl")
OUT_PATH = os.path.join(RAW, "pages_wiki.jsonl")
FAILED_PATH = os.path.join(RAW, "failed_wiki.jsonl")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongOfIceAndFireMind; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5
MAX_RETRIES = 4


#%%
def load_done(path):
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                done.add(json.loads(line)["requested_title"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def fetch_text(title):
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "exsectionformat": "wiki",
        "titles": title,
        "redirects": 1,
        "format": "json",
    }
    resp = requests.get(API, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    page = next(iter(resp.json()["query"]["pages"].values()))
    if "missing" in page:
        return None
    return {"title": page["title"], "text_wiki": page.get("extract", "")}


def fetch_with_retries(title):
    delay = DELAY
    for attempt in range(MAX_RETRIES):
        try:
            return fetch_text(title), None
        except Exception as exc:
            if attempt == MAX_RETRIES - 1:
                return None, repr(exc)
            time.sleep(delay)
            delay *= 3
    return None, "unreachable"


#%%
with open(PAGES_PATH, encoding="utf-8") as f:
    requested = [json.loads(line)["requested_title"] for line in f if line.strip()]

requested = list(dict.fromkeys(requested))
done = load_done(OUT_PATH) | load_done(FAILED_PATH)
pending = [t for t in requested if t not in done]

print(len(requested), len(done), len(pending))


#%%
start = time.time()
saved = 0
failed = 0

with open(OUT_PATH, "a", encoding="utf-8") as out_file, \
     open(FAILED_PATH, "a", encoding="utf-8") as fail_file:

    for i, title in enumerate(pending, 1):
        record, error = fetch_with_retries(title)

        if record is None:
            fail_file.write(json.dumps({"requested_title": title, "error": error or "missing"}) + "\n")
            fail_file.flush()
            failed += 1
        else:
            record["requested_title"] = title
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            saved += 1

        if i % 50 == 0:
            left = (time.time() - start) / i * (len(pending) - i) / 60
            print(f"{i}/{len(pending)} saved={saved} failed={failed} eta_min={left:.1f}")

        time.sleep(DELAY)

print("done", saved, "failed", failed)