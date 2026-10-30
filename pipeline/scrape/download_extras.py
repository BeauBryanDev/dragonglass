
#%%
import json
import os
import time
from collections import Counter

import requests

BASE = "data"
RAW = os.path.join(BASE, "raw")
PAGES_PATH = os.path.join(RAW, "pages.jsonl")
EXTRA_PATH = os.path.join(RAW, "pages_extra.jsonl")
EXTRA_FAILED = os.path.join(RAW, "failed_extra.jsonl")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic project; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5
MAX_RETRIES = 4
MIN_INBOUND = 100

EXPLICIT = [
    "Red Wedding", "Valyria", "Slaver's Bay", "Night's Watch", "Astapor", "Yunkai",
    "Doom of Valyria", "Age of Heroes", "Others", "Children of the Forest", "Giants","The Wall","Dorne","Old Town","Asshay","Summer Sea",
]
BLOCK = {"So Spake Martin", "George R. R. Martin", "Gold", "The Winds of Winter", "Game of Thrones"}


#%%
def api_get(params):
    resp = requests.get(API, params={**params, "format": "json"}, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def category_titles(category):
    titles = []
    params = {
        "action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}",
        "cmnamespace": 0, "cmlimit": 500,
    }
    while True:
        data = api_get(params)
        titles += [m["title"] for m in data["query"]["categorymembers"]]
        time.sleep(DELAY)
        if "continue" not in data:
            return titles
        params["cmcontinue"] = data["continue"]["cmcontinue"]


def load_done(path):
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            done.add(rec.get("requested_title") or rec["title"])
    return done


def fetch_page(title):
    params = {
        "action": "query", "prop": "extracts|links|categories|info",
        "explaintext": 1, "exsectionformat": "wiki",
        "pllimit": "max", "plnamespace": 0, "cllimit": "max",
        "inprop": "url", "titles": title, "redirects": 1,
    }
    record = None
    while True:
        data = api_get(params)
        page = next(iter(data["query"]["pages"].values()))
        if "missing" in page:
            return None
        if record is None:
            record = {
                "title": page["title"], "pageid": page["pageid"], "url": page.get("fullurl"),
                "text": page.get("extract", ""), "links": [], "categories": [],
            }
        record["links"] += [l["title"] for l in page.get("links", [])]
        record["categories"] += [c["title"] for c in page.get("categories", [])]
        if "continue" not in data:
            record["links"] = sorted(set(record["links"]))
            record["categories"] = sorted(set(record["categories"]))
            return record
        params.update(data["continue"])
        time.sleep(DELAY)


def fetch_with_retries(title):
    delay = DELAY
    for attempt in range(MAX_RETRIES):
        try:
            return fetch_page(title), None
        except Exception as exc:
            if attempt == MAX_RETRIES - 1:
                return None, repr(exc)
            time.sleep(delay)
            delay *= 3
    return None, "unreachable"


#%%
with open(PAGES_PATH, encoding="utf-8") as f:
    existing = [json.loads(line) for line in f if line.strip()]

have = {p["title"] for p in existing} | {p.get("requested_title") for p in existing}
inbound = Counter(l for p in existing for l in p["links"])
targets = {}


def add(title, kind):
    if title in have or title in BLOCK or title.endswith("-Appendix"):
        return
    targets.setdefault(title, set()).add(kind)


for title in EXPLICIT:
    add(title, "hub")
for title, n in inbound.items():
    if n >= MIN_INBOUND:
        add(title, "hub")
for title in category_titles("A Song of Ice And Fire chapters"):
    add(title, "chapter")

done = load_done(EXTRA_PATH) | load_done(EXTRA_FAILED)
pending = sorted(t for t in targets if t not in done)
print(len(targets), len(done), len(pending))


#%%
start = time.time()
saved = 0

with open(EXTRA_PATH, "a", encoding="utf-8") as out_file, \
     open(EXTRA_FAILED, "a", encoding="utf-8") as fail_file:

    for i, title in enumerate(pending, 1):
        record, error = fetch_with_retries(title)

        if record is None:
            fail_file.write(json.dumps({"title": title, "requested_title": title,
                                        "error": error or "missing"}) + "\n")
            fail_file.flush()
        else:
            record["kinds"] = sorted(targets[title])
            record["seed_categories"] = []
            record["requested_title"] = title
            record["chars"] = len(record["text"])
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            saved += 1

        if i % 25 == 0:
            left = (time.time() - start) / i * (len(pending) - i) / 60
            print(f"{i}/{len(pending)} saved={saved} eta_min={left:.1f}")

        time.sleep(DELAY)

print("done", saved)



#%%
import os
with open(os.path.join(BASE, "raw", "pages_extra.jsonl"), encoding="utf-8") as f:
    extra = [json.loads(line) for line in f if line.strip()]

titles = {p["title"] for p in extra}
for t in ["Red Wedding", "Valyria", "Slaver's Bay", "Night's Watch", "Iron Throne"]:
    print(t, "OK" if t in titles else "MISSING")

chapters = [p for p in extra if "chapter" in p["kinds"]]
print(len(extra), "pages,", len(chapters), "chapters")