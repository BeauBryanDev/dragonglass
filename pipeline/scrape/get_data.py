
#%%
import json

TARGETS = {
    "character": [
        "House Stark", "House Lannister", "House Targaryen", "House Baratheon",
        "House Greyjoy", "House Martell", "House Tyrell", "House Arryn",
        "House Tully", "House Bolton", "Hands of the King",
    ],
    "house": ["Houses with COA", "Houses without COA"],
    "place": ["Castles", "Cities", "Harbors", "Halls"],
    "battle": ["Battles"],
    "event": ["Events", "Dance of the Dragons"],
    "dragon": ["Dragons"],
    "culture": ["Cultures", "Culture"],
    "religion": ["Deities", "Faith of the Seven"],
}


#%%
def category_titles(category):
    titles = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmnamespace": 0,
        "cmlimit": 500,
    }
    while True:
        data = api_get(params)
        titles += [m["title"] for m in data["query"]["categorymembers"]]
        if "continue" not in data:
            return titles
        params["cmcontinue"] = data["continue"]["cmcontinue"]


#%%
pages = {}
for kind, categories in TARGETS.items():
    for category in categories:
        titles = category_titles(category)
        print(kind, category, len(titles))
        for title in titles:
            entry = pages.setdefault(title, {"kinds": set(), "categories": set()})
            entry["kinds"].add(kind)
            entry["categories"].add(category)

print(len(pages))


#%%
out = [
    {"title": t, "kinds": sorted(v["kinds"]), "categories": sorted(v["categories"])}
    for t, v in sorted(pages.items())
]
with open("data/raw/titles.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

#%%
import json
import os
import time
import requests

BASE = "data"
RAW = os.path.join(BASE, "raw")
PAGES_PATH = os.path.join(RAW, "pages.jsonl")
FAILED_PATH = os.path.join(RAW, "failed.jsonl")
TITLES_PATH = os.path.join(RAW, "titles.json")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic Song0fIceAndFore; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5
MAX_RETRIES = 4

os.makedirs(RAW, exist_ok=True)



def api_get(params):
    params = {**params, "format": "json"}
    resp = requests.get(API, params=params, headers=HEADERS, timeout=30)
    print(resp.status_code)
    resp.raise_for_status()
    time.sleep(DELAY)
    return resp.json()


#%%
data = api_get({
    "action": "query",
    "list": "allcategories",
    "acmin": 40,
    "aclimit": 200,
    "acprop": "size",
})

cats = data["query"]["allcategories"]
for c in sorted(cats, key=lambda c: -c["pages"]):
    print(c["pages"], c["*"])


#%%
test = api_get({
    "action": "query",
    "prop": "extracts",
    "explaintext": 1,
    "titles": "Winterfell",
})

page = next(iter(test["query"]["pages"].values()))
print(page.get("extract", "NO EXTRACT")[:300])

#%%
EXTRA_TARGETS = {
    "place": ["Buildings"],
    "culture": ["Ghiscari"],
    "house": ["Extinct houses"],
}

for kind, categories in EXTRA_TARGETS.items():
    for category in categories:
        titles = category_titles(category)
        print(kind, category, len(titles))
        for title in titles:
            entry = pages.setdefault(title, {"kinds": set(), "categories": set()})
            entry["kinds"].add(kind)
            entry["categories"].add(category)

out = [
    {"title": t, "kinds": sorted(v["kinds"]), "categories": sorted(v["categories"])}
    for t, v in sorted(pages.items())
]
with open(TITLES_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print(len(out))


#%%
def load_done(path):
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["title"])
            except json.JSONDecodeError:
                continue
    return done


def fetch_page(title):
    params = {
        "action": "query",
        "prop": "extracts|links|categories|info",
        "explaintext": 1,
        "exsectionformat": "plain",
        "pllimit": "max",
        "plnamespace": 0,
        "cllimit": "max",
        "inprop": "url",
        "titles": title,
        "redirects": 1,
        "format": "json",
    }
    record = None
    while True:
        resp = requests.get(API, params=params, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        page = next(iter(data["query"]["pages"].values()))
        if "missing" in page:
            return None
        if record is None:
            record = {
                "title": page["title"],
                "pageid": page["pageid"],
                "url": page.get("fullurl"),
                "text": page.get("extract", ""),
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
with open(TITLES_PATH, encoding="utf-8") as f:
    targets = json.load(f)

meta_by_title = {t["title"]: t for t in targets}
done = load_done(PAGES_PATH) | load_done(FAILED_PATH)
pending = [t["title"] for t in targets if t["title"] not in done]

print(len(targets), len(done), len(pending))


#%%
start = time.time()
saved = 0

with open(PAGES_PATH, "a", encoding="utf-8") as out_file, \
     open(FAILED_PATH, "a", encoding="utf-8") as fail_file:

    for i, title in enumerate(pending, 1):
        record, error = fetch_with_retries(title)

        if record is None:
            fail_file.write(json.dumps({"title": title, "error": error or "missing"}) + "\n")
            fail_file.flush()
        else:
            meta = meta_by_title.get(title, {})
            record["kinds"] = meta.get("kinds", [])
            record["seed_categories"] = meta.get("categories", [])
            record["requested_title"] = title
            record["chars"] = len(record["text"])
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            saved += 1

        if i % 25 == 0:
            elapsed = time.time() - start
            rate = elapsed / i
            left = rate * (len(pending) - i) / 60
            print(f"{i}/{len(pending)} saved={saved} eta_min={left:.1f}")

        time.sleep(DELAY)

print("done", saved)
