
#%%
import json
import os
from collections import Counter

CLEAN = "data/clean"
CHUNKS_PATH = os.path.join(CLEAN, "chunks.jsonl")
STRUCTURED_PATH = os.path.join(CLEAN, "wiki_structured.jsonl")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


#%%
structured = {r["title"]: r for r in read_jsonl(STRUCTURED_PATH)}
chunks = read_jsonl(CHUNKS_PATH)


def wiki_label(chunk):
    page = structured.get(chunk["page_title"])
    if page is None:
        return None, "unlabeled"
    path = chunk["path"].split(" > ")[1:]
    for section in page["sections"]:
        if section["path"] == path and section["max_book"] is not None:
            return section["max_book"], "section_ref"
    return None, "unlabeled"


#%%
for chunk in chunks:
    if chunk["label_source"] == "unlabeled":
        chunk["spoiler_book"], chunk["label_source"] = wiki_label(chunk)

tmp_path = CHUNKS_PATH + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    for chunk in chunks:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
os.replace(tmp_path, CHUNKS_PATH)

print(len(chunks), Counter(c["label_source"] for c in chunks).most_common())
print(sorted(Counter(c["spoiler_book"] for c in chunks).items(), key=lambda kv: kv[0] or 0))
