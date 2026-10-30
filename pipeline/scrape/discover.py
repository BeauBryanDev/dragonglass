
#%%
import time
import requests

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongIcrandFireProject; contact: bryan.beau.186@gmail.com)"}
DELAY = 1.5


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









