
#%%
import csv
import json
import os
import re
import time
from collections import Counter

import requests

RAW = "data/raw"
CLEAN = "data/clean"
CORPUS_PATH = os.path.join(CLEAN, "corpus.jsonl")
REVIEW_PATH = os.path.join(RAW, "missing_pages_review.tsv")
OUT_PATH = os.path.join(RAW, "pages_expansion.jsonl")
FAILED_PATH = os.path.join(RAW, "failed_expansion.jsonl")
WIKI_PATH = os.path.join(RAW, "wikitext.jsonl")
REDIRECTS_PATH = os.path.join(RAW, "redirects.jsonl")

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongOfIceAndFireMind; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5
MAX_RETRIES = 4

EXTRA_CATEGORIES = [
    "Braavos", "Places in Braavos", "Characters from Braavos",
    "Places beyond the Wall", "Places in Essos",
]
FORCE = ["Unmasking of Uthero", "House Zalyne", "Beyond the Wall"]

NOISE_PATTERN = re.compile(
    r"\((comics|game|board game|card game|book)\)$|-Map of |/Theories$|/Family Trees$"
)
NOISE_META = {
    "10,000 Ships", "A Feast of Ice and Fire", "A Game of Groans", "A Game of Thrones: Genesis",
    "A Song of Ice and Fire Calendar", "A Song of Ice and Fire Campaign Guide",
    "A Song of Ice and Fire Roleplaying", "A Song of Ice and Fire: Tactics", "Arms of the Kraken",
    "Battles of Westeros", "Blood & Fire", "Blood of Dragons", "Blood of the Dragon",
    "Derived works", "Dunk and Egg", "Houses of Westeros", "Inside HBO's Game of Thrones",
    "Not A Blog", "POV character", "Path of the Dragon",
    "The Art of George R. R. Martin's A Song of Ice and Fire", "The She-Wolves of Winterfell",
    "Timeline of major events",
}
NOISE_EVERYDAY = {
    "Alcoholic beverages", "Archer", "Armament", "Assassin", "Astronomy", "Bastard sword", "Beer",
    "Bone", "Brass", "Chamber pot", "Chestnut", "Cider", "Cobalt", "Column", "Courtyard", "Crown",
    "Cutpurse", "Damask", "Dice", "Dove", "Drum", "Feather", "Fermented milk", "Flint", "Flute",
    "Fungi", "Gargoyle", "Granite", "Greatsword", "Hair shirt", "Harbormaster", "Harp", "Herald",
    "Hippocras", "Hook", "Horn", "Hound", "Juggler", "Lance", "Lead", "Longsword", "Lute", "Maiden",
    "Marble", "Mead", "Medicine", "Morningstar", "Mushroom", "Paymaster", "Peach", "Pewter",
    "Platinum", "Poacher", "Reed pipes", "Rum", "Samite", "Sandstone (material)", "Satin (fabric)",
    "Seal", "Shark", "Shortsword", "Skull", "Sky", "Slate", "Smith", "Smuggler", "Stone",
    "Strongwine", "Swordfish", "Tiles", "Tin", "Trebuchet", "Trumpet", "Turtle (siege engine)",
    "Velvet", "Wax", "Wench", "Whipping", "Wineseller",
}


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
        time.sleep(DELAY)
        titles += [m["title"] for m in data["query"]["categorymembers"]]
        if "continue" not in data:
            return titles
        params.update(data["continue"])


def is_noise(title):
    return title in NOISE_META or title in NOISE_EVERYDAY or bool(NOISE_PATTERN.search(title))


def fetch_page(title):
    params = {
        "action": "query",
        "prop": "extracts|info|categories|links|revisions|redirects",
        "explaintext": 1,
        "exsectionformat": "wiki",
        "inprop": "url",
        "cllimit": "max",
        "pllimit": "max",
        "plnamespace": 0,
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "rdprop": "title",
        "rdnamespace": 0,
        "rdlimit": "max",
        "titles": title,
        "redirects": 1,
    }
    record = None
    
    while True:
        data = api_get(params)
        page = data["query"]["pages"][0]
        if page.get("missing") or page.get("invalid"):
            return None
        if record is None:
            record = {
                "title": page["title"],
                "pageid": page["pageid"],
                "url": page.get("fullurl"),
                "text_wiki": "",
                "wikitext": "",
                "revid": None,
                "timestamp": None,
                "links": [],
                "categories": [],
                "aliases": [],
            }
        record["text_wiki"] = page.get("extract") or record["text_wiki"]
        
        if page.get("revisions"):
            
            rev = page["revisions"][0]
            record["revid"] = rev["revid"]
            record["timestamp"] = rev["timestamp"]
            record["wikitext"] = rev["slots"]["main"]["content"]
            
        record["links"] += [l["title"] for l in page.get("links", [])]
        record["categories"] += [c["title"] for c in page.get("categories", [])]
        record["aliases"] += [r["title"] for r in page.get("redirects", [])]
        
        if "continue" not in data:
            for key in ("links", "categories", "aliases"):
                record[key] = sorted(set(record[key]))
                
            return record
        
        params.update(data["continue"])
        time.sleep(DELAY)


#%%
with open(CORPUS_PATH, encoding="utf-8") as f:
    corpus_titles = {json.loads(line)["title"] for line in f if line.strip()}
known = corpus_titles | {a for r in read_jsonl(REDIRECTS_PATH) for a in r["aliases"]}

with open(REVIEW_PATH, encoding="utf-8", newline="") as f:
    review = list(csv.DictReader(f, delimiter="\t"))

targets = {r["title"]: r["group"] for r in review if not r["group"].startswith("Noise")}
for category in EXTRA_CATEGORIES:
    for title in category_titles(category):
        targets.setdefault(title, f"category: {category}")
        
for title in FORCE:
    targets.setdefault(title, "forced")

targets = {t: g for t, g in targets.items() if t not in known and not is_noise(t)}
done = {r["requested_title"] for r in read_jsonl(OUT_PATH) + read_jsonl(FAILED_PATH)}
pending = [t for t in targets if t not in done]

print(len(targets), len(done), len(pending))
print(Counter(targets.values()).most_common())


#%%
start = time.time()
saved = failed = 0

with open(OUT_PATH, "a", encoding="utf-8") as out_file, \
     open(FAILED_PATH, "a", encoding="utf-8") as fail_file:

    for i, title in enumerate(pending, 1):
        record, error = with_retries(fetch_page, title)

        if record is None:
            fail_file.write(json.dumps({"requested_title": title, 
                                        "error": error or "missing"}) + "\n")
            fail_file.flush()
            failed += 1
        else:
            record["requested_title"] = title
            record["kind"] = "expansion"
            record["review_group"] = targets[title]
            record["chars"] = len(record["text_wiki"])
            
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            saved += 1

        if i % 25 == 0:
            left = (time.time() - start) / i * (len(pending) - i) / 60
            print(f"{i}/{len(pending)} saved={saved} failed={failed} eta_min={left:.1f}")

        time.sleep(DELAY)

print("done", saved, "failed", failed)


#%%
pages = read_jsonl(OUT_PATH)
have_wiki = {r["title"] for r in read_jsonl(WIKI_PATH)}
have_redirects = {r["title"] for r in read_jsonl(REDIRECTS_PATH)}
added = 0

with open(WIKI_PATH, "a", encoding="utf-8") as wiki_file, \
     open(REDIRECTS_PATH, "a", encoding="utf-8") as redirect_file:

    for page in pages:
        title = page["title"]
        if title in have_wiki:
            continue
        wiki_file.write(json.dumps({
            "title": title,
            "requested_title": page["requested_title"],
            "pageid": page["pageid"],
            "revid": page["revid"],
            "timestamp": page["timestamp"],
            "wikitext": page["wikitext"],
        }, ensure_ascii=False) + "\n")
        have_wiki.add(title)
        added += 1
        if title not in have_redirects:
            redirect_file.write(json.dumps({"title": title, 
                                            "aliases": page["aliases"]},
                                           ensure_ascii=False) + "\n")
            have_redirects.add(title)

print(len(pages), "expansion pages |", added, "added to", WIKI_PATH)
print("empty text:", [p["title"] for p in pages if not p["text_wiki"]][:30])
print("empty wikitext:", [p["title"] for p in pages if not p["wikitext"]][:30])
print("total chars", sum(p["chars"] for p in pages))
print(Counter(p["review_group"] for p in pages).most_common())
