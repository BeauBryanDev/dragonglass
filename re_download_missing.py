
#%%
import time

import requests

API = "https://awoiaf.westeros.org/api.php"
HEADERS = {"User-Agent": "asoiaf-rag-portfolio/0.1 (academic SongOfIceAndFireMind; contact: bryan.beau.186@gmail.com)"}


def intro(title):
    params = {"action": "query", "prop": "extracts", "explaintext": 1, "exintro": 1,
              "titles": title, "redirects": 1, "format": "json"}
    r = requests.get(API, params=params, headers=HEADERS, timeout=60)
    page = next(iter(r.json()["query"]["pages"].values()))
    time.sleep(1.5)
    return page.get("extract", "MISSING")[:220].replace("\n", " ")


for t in ["Pate (ranger)", "Yezzan zo Qaggaz", "Torwynd", "Battle at the burning septry",
          "Invasion of the Arbor", "Siege of Storm's End"]:
    print(t, "->", intro(t))


#%%
def text_of(p):
    return p.get("text_wiki") or p.get("text") or ""


def allegiance_ok(row):
    p = by_title.get(row["name"])
    if p is None or pd.isna(row["allegiance"]):
        return None
    return row["allegiance"] in " ".join(p["categories"]) or row["allegiance"] in text_of(p)[:1500]


chars["ally_ok"] = chars.apply(allegiance_ok, axis=1)
checked = chars["ally_ok"].dropna().astype(bool)
print(len(checked), round(checked.mean(), 3))
print(chars[chars["ally_ok"] == False][["name", "allegiance"]].head(40).to_string())
print(chars[chars["match"] & chars["disambig"]][["name", "allegiance", "first_book"]].to_string())



