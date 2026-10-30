
#%%
import json
import os
from collections import Counter

import numpy as np

BASE = os.path.expanduser("~/IceAndFire")
PAGES_PATH = os.path.join(BASE, "raw", "pages.jsonl")

with open(PAGES_PATH, encoding="utf-8") as f:
    pages = [json.loads(line) for line in f if line.strip()]

by_title = {}
for p in pages:
    by_title.setdefault(p["title"], []).append(p)

print("rows", len(pages), "unique titles", len(by_title))


#%%
chars = np.array([p["chars"] for p in pages])
print("percentiles 5/25/50/75/95/99:", np.percentile(chars, [5, 25, 50, 75, 95, 99]).astype(int))
print("total chars", chars.sum())
print("under 200 chars:", int((chars < 200).sum()))
print("under 500 chars:", int((chars < 500).sum()))
print("over 20000 chars:", int((chars > 20000).sum()))

for kind in sorted({k for p in pages for k in p["kinds"]}):
    sub = [p["chars"] for p in pages if kind in p["kinds"]]
    print(kind, len(sub), int(np.median(sub)))


#%%
for p in sorted(pages, key=lambda p: p["chars"])[:10]:
    print(p["chars"], p["title"], "|", p["text"][:80].replace("\n", " "))

print()
for p in sorted(pages, key=lambda p: -p["chars"])[:10]:
    print(p["chars"], p["title"])


#%%
must_have = [
    "Red Wedding", "Meereen", "Daenerys Targaryen", "Winterfell", "Dragonstone",
    "Braavos", "Pentos", "Volantis", "Slaver's Bay", "Qarth", "Asshai",
    "Valyria", "Long Night", "Night's Watch", "Arya Stark", "Robb Stark",
]
for t in must_have:
    print(t, "OK" if t in by_title else "MISSING")


#%%
link_counts = [len(p["links"]) for p in pages]
print("links per page median/max/total:", int(np.median(link_counts)), max(link_counts), sum(link_counts))

corpus = set(by_title)
all_links = Counter(l for p in pages for l in p["links"])
inside = sum(c for t, c in all_links.items() if t in corpus)
print("link edges inside corpus", inside, "of", sum(all_links.values()))

print()
print("most linked pages missing from corpus:")
missing = [(t, c) for t, c in all_links.most_common() if t not in corpus]
for t, c in missing[:60]:
    print(c, t)


p = next(p for p in pages if p["title"] == "Daenerys Targaryen")
print(p["text"][:1500])


