
#%%
import json
import math
import os
import re
from collections import Counter, defaultdict

import numpy as np

CLEAN = "data/clean"
RAW = "data/raw"

BOOKS = ["A Game of Thrones", "A Clash of Kings", "A Storm of Swords",
         "A Feast for Crows", "A Dance with Dragons", "The Winds of Winter"]
BOOK_CODES = {"AGOT": 1, "ACOK": 2, "ASOS": 3, "AFFC": 4, "ADWD": 5, "TWOW": 6}
META = {"The World of Ice & Fire", "A World of Ice and Fire", "Fire & Blood", "A Song of Ice and Fire"}
SKIP_PAGES = {"Chapters", "Chapters Table of contents"}
CHAPTER = re.compile(r"^(" + "|".join(map(re.escape, BOOKS[:5])) + r")-(.+)$")

REGIONS = {
    "Westeros", "Essos", "Sothoryos", "Ulthos", "North", "Riverlands", "Vale of Arryn",
    "Westerlands", "Reach", "Stormlands", "Crownlands", "Dorne", "Iron Islands",
    "Beyond the Wall", "Slaver's Bay", "Shadow Lands", "Dothraki sea", "Lhazar", "Valyria",
    "Free Cities", "Dornish Marches",
}
FORCE_TYPE = {
    **dict.fromkeys((
        "Blacks", "Greens", "Caltrops", "Two Betrayers", "Winter Wolves", "Gutter knights",
        "Knights inquisitor", "Citadel", "Iron Bank of Braavos", "Unsullied", "Wise Masters",
        "Good Masters", "Great Masters", "Drogo's khalasar", "King's men",
    ), "Organization"),
    "Years after Aegon's Conquest": "Concept",
    "Years before Aegon's Conquest": "Concept",
    "War for the White Cloaks": "Event",
    "Long Night": "Event",
    "Age of Heroes": "Concept",
    "Faith of the Seven": "Religion",
    "Rhoynar": "Culture",
    "House words": "Concept",
}
WAR_WORDS = re.compile(r"\b(War|Wars|Rebellion|Uprising|Conquest|Dance of the Dragons)\b")
YEAR = re.compile(r"^\d+ (AC|BC)$")
RULER_TITLE = re.compile(r"^(Lord|Lady|King|Queen|Prince|Princess|Master|Knight)s? (Paramount )?of ")

TEMPLATE_TYPE = (
    ("infobox character", "Character"), ("infobox monarch", "Character"),
    ("infobox dragon", "Dragon"), ("infobox animal character", "Character"),
    ("noble house", "House"), ("infobox settlement", "Place"), ("infobox location", "Place"),
    ("infobox polity", "Region"), ("infobox organization", "Organization"),
    ("infobox sellsword company", "Organization"), ("battlebox", "Battle"),
    ("infobox military conflict", "War"), ("infobox conspiracy", "Event"), ("infobox event", "Event"),
    ("infobox title", "Concept"), ("infobox book", "Book"), ("infobox chapter", "Chapter"),
)
CATEGORY_TYPE = (
    (r"^(Titles|Books and scrolls)$", "Concept"),
    (r"^(Members of |Organizations$|Guards$|Sellsword companies$|Mountain clans|Fleets$)", "Organization"),
    (r"^(Nations|Continents|Regions)$", "Region"),
    (r"^(Places |Castles|Islands|Rivers|Cities|Towns|Villages|Ruined cities|Ruins|Hills|Harbors"
     r"|Roads|Halls|Buildings|Towers|Statues|Mountains|Forests|Seas|Lakes|Bays|Holdfasts|Palaces"
     r"|Strongholds|Colloquial locations|Religious buildings|Godswoods|Septs|Valleys|Gates"
     r"|Peninsulas|Mills|Gardens|Libraries|Inns )", "Place"),
    (r"^(Deities|Religions|Faith of the Seven)$", "Religion"),
    (r"^(Cultures|Sentient species)$", "Culture"),
    (r"^Wars$", "War"),
    (r"^(Events|Tourneys|Weddings|Assassinations)$", "Event"),
    (r"^Characters from ", "Character"),
)
KIND_TYPE = (("house", "House"), ("battle", "Battle"), ("place", "Place"), ("event", "Event"))

COST = {"infobox": 0.5, "kaggle": 0.5, "structure": 0.5,
        "APPEARS_IN": 1.0, "APPEARS_OR_MENTIONED_IN": 1.25, "MENTIONED_IN": 1.5,
        "LINK_MUTUAL": 1.5, "LINK_ONEWAY": 2.5}
SYMMETRIC = {"SPOUSE_OF", "LOVER_OF"}

CHAR = {"Character"}
PLACE = {"Place", "Region"}
GROUP = {"House", "Organization"}
ANY_ENTITY = {"Character", "House", "Place", "Region", "Organization", "Dragon"}
TITLE = {"Concept", "Organization", "Religion"}
CULTURE = {"Culture", "Region", "Place"}
DEATH_SITE = PLACE | {"Battle", "War", "Event"}
SIDE = GROUP | PLACE | {"Concept", "Culture", "Character"}
CONFLICT = {"War", "Event", "Battle"}

PERSON_RULES = [
    ("allegiance", "MEMBER_OF", "out", GROUP), ("royalhouse", "MEMBER_OF", "out", GROUP),
    ("dynasty", "MEMBER_OF", "out", GROUP),
    ("father", "CHILD_OF", "out", CHAR), ("mother", "CHILD_OF", "out", CHAR),
    ("issue", "CHILD_OF", "in", CHAR),
    ("spouse", "SPOUSE_OF", "out", CHAR), ("spouse1", "SPOUSE_OF", "out", CHAR),
    ("queen", "SPOUSE_OF", "out", CHAR), ("lover", "LOVER_OF", "out", CHAR),
    ("allegiance", "FOLLOWS", "out", {"Religion"}), ("allegiance", "SWORN_TO", "out", CHAR),
    ("title", "HOLDS_TITLE", "out", TITLE), ("othertitles", "HOLDS_TITLE", "out", TITLE),
    ("title", "LORD_OF", "out", PLACE), ("othertitles", "LORD_OF", "out", PLACE),
    ("culture", "OF_CULTURE", "out", CULTURE), ("race", "OF_CULTURE", "out", CULTURE),
    ("place_of_birth", "BORN_AT", "out", PLACE), ("placeofbirth", "BORN_AT", "out", PLACE),
    ("place_of_death", "DIED_AT", "out", DEATH_SITE), ("placeofdeath", "DIED_AT", "out", DEATH_SITE),
    ("place_of_burial", "BURIED_AT", "out", PLACE), ("placeofburial", "BURIED_AT", "out", PLACE),
    ("successor", "SUCCEEDED_BY", "out", CHAR), ("predecessor", "SUCCEEDED_BY", "in", CHAR),
    ("heir", "HEIR_OF", "in", CHAR),
]
ANIMAL_RULES = [
    ("owner", "OWNED_BY", "out", ANY_ENTITY), ("place_of_birth", "BORN_AT", "out", PLACE),
    ("place_of_death", "DIED_AT", "out", DEATH_SITE),
]
RULES = {
    "infobox character": PERSON_RULES,
    "infobox monarch": PERSON_RULES,
    "infobox animal character": ANIMAL_RULES,
    "infobox dragon": ANIMAL_RULES + [("rider", "RIDES", "in", CHAR), ("parent", "CHILD_OF", "out", {"Dragon"})],
    "noble house": [
        ("region", "LOCATED_IN", "out", PLACE), ("overlord", "SWORN_TO", "out", GROUP),
        ("vassal", "SWORN_TO", "in", GROUP), ("seat", "SEAT_OF", "in", PLACE),
        ("current_lord", "LORD_OF", "in", CHAR), ("previous_lord", "LORD_OF", "in", CHAR),
        ("heir", "HEIR_OF", "in", CHAR), ("founder", "FOUNDED", "in", CHAR),
        ("cadet_branch", "CADET_OF", "in", {"House"}),
        ("title", "HOLDS_TITLE", "out", {"Concept", "Organization"}),
        ("ancestral_weapon", "HOLDS_WEAPON", "out", {"Concept"}),
    ],
    "infobox settlement": [
        ("location", "LOCATED_IN", "out", PLACE), ("seat", "SEAT_OF", "out", GROUP),
        ("lord", "LORD_OF", "in", CHAR | GROUP), ("religion", "FOLLOWS", "out", {"Religion"}),
        ("places", "LOCATED_IN", "in", PLACE), ("organizations", "BASED_IN", "in", GROUP),
        ("founder", "FOUNDED", "in", CHAR | GROUP),
    ],
    "infobox location": [("location", "LOCATED_IN", "out", PLACE), ("places", "LOCATED_IN", "in", PLACE)],
    "infobox polity": [
        ("location", "LOCATED_IN", "out", PLACE), ("capital", "CAPITAL_OF", "in", PLACE),
        ("places", "LOCATED_IN", "in", PLACE), ("religion", "FOLLOWS", "out", {"Religion"}),
        ("ruler", "LORD_OF", "in", CHAR), ("organizations", "BASED_IN", "in", GROUP),
    ],
    "infobox title": [
        ("region", "LOCATED_IN", "out", PLACE), ("current_holder", "HOLDS_TITLE", "in", CHAR),
        ("first_holder", "HOLDS_TITLE", "in", CHAR), ("last_holder", "HOLDS_TITLE", "in", CHAR),
        ("last__holder", "HOLDS_TITLE", "in", CHAR), ("creator", "FOUNDED", "in", CHAR),
    ],
    "infobox organization": [
        ("region", "LOCATED_IN", "out", PLACE), ("allegiance", "SWORN_TO", "out", GROUP),
        ("current_leader", "LEADS", "in", CHAR), ("seat", "BASED_IN", "out", PLACE),
        ("founder", "FOUNDED", "in", CHAR),
    ],
    "infobox sellsword company": [
        ("leader", "LEADS", "in", CHAR), ("former_leader", "LEADS", "in", CHAR),
        ("founder", "FOUNDED", "in", CHAR),
    ],
    "infobox conspiracy": [
        ("place", "OCCURRED_AT", "out", PLACE), ("conflict", "PART_OF", "out", CONFLICT),
        ("participants", "PARTICIPATED_IN", "in", CHAR | GROUP),
    ],
    "infobox event": [
        ("place", "OCCURRED_AT", "out", PLACE), ("conflict", "PART_OF", "out", CONFLICT),
        ("participant1", "PARTICIPATED_IN", "in", CHAR | GROUP),
        ("participant2", "PARTICIPATED_IN", "in", CHAR | GROUP),
        ("leader1", "COMMANDED_IN", "in", CHAR), ("leader2", "COMMANDED_IN", "in", CHAR),
    ],
}
BATTLE_RULES = [
    ("place", "OCCURRED_AT", "out", PLACE), ("location", "OCCURRED_AT", "out", PLACE),
    ("conflict", "PART_OF", "out", CONFLICT), ("part_of", "PART_OF", "out", CONFLICT),
    ("battles", "PART_OF", "in", {"Battle"}),
]
SIDE_FIELD = re.compile(r"^(combatant|commander)(\d+)$")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp_path, path)


def clean_template(name):
    return name.split("<!--")[0].strip()


def is_chapter(title):
    return bool(CHAPTER.match(title)) or title.endswith("(The Winds of Winter)")


def book_of(title):
    m = CHAPTER.match(title)
    if m:
        return BOOKS.index(m.group(1)) + 1
    return 6 if title.endswith("(The Winds of Winter)") else None


#%%
corpus = read_jsonl(f"{CLEAN}/corpus.jsonl")
structured = {r["title"]: r for r in read_jsonl(f"{CLEAN}/wiki_structured.jsonl")}
redirects = read_jsonl(f"{RAW}/redirects.jsonl")
chunks = read_jsonl(f"{CLEAN}/chunks.jsonl")
characters = read_jsonl(f"{CLEAN}/characters_linked.jsonl")
battles = read_jsonl(f"{CLEAN}/battles_linked.jsonl")
episodes = read_jsonl(f"{CLEAN}/episodes.jsonl")

pages = {r["title"]: r for r in corpus
         if r["title"] not in SKIP_PAGES
         and not any("Disambiguation" in c for c in r["categories"])}


def infobox_type(title):
    for box in structured[title]["infoboxes"]:
        template = clean_template(box["template"])
        for prefix, node_type in TEMPLATE_TYPE:
            if template.startswith(prefix):
                species = box["fields"].get("species", [])
                if node_type == "Character" and any("dragon" in i["text"].lower() for i in species):
                    return "Dragon"
                return node_type
    return None


def category_type(categories):
    for pattern, node_type in CATEGORY_TYPE:
        if any(re.search(pattern, c) for c in categories):
            return node_type
    return None


def page_type(rec):
    title = rec["title"]
    if title in FORCE_TYPE:
        return FORCE_TYPE[title]
    if is_chapter(title):
        return "Chapter"
    if title in BOOKS or title in META:
        return "Book"
    if title in REGIONS:
        return "Region"
    if YEAR.match(title):
        return "Year"
    from_box = infobox_type(title)
    if from_box:
        return from_box
    from_category = category_type([c.removeprefix("Category:") for c in rec["categories"]])
    if from_category:
        return from_category
    if title.startswith("House "):
        return "House"
    for kind, node_type in KIND_TYPE:
        if kind in rec["kinds"]:
            return node_type
    return "Concept"


types = {t: page_type(r) for t, r in pages.items()}
places = {t for t, v in types.items() if v == "Place"}
for title, rec in pages.items():
    if types[title] == "Concept" and not RULER_TITLE.match(title) and any(
            c.removeprefix("Category:") in places for c in rec["categories"]):
        types[title] = "Place"
for title, node_type in types.items():
    is_book = "Category:Books and scrolls" in pages[title]["categories"]
    if node_type in ("Event", "Concept") and title not in FORCE_TYPE and "/" not in title \
            and not is_book and WAR_WORDS.search(title):
        types[title] = "War"
for r in structured.values():
    for box in r["infoboxes"]:
        if clean_template(box["template"]).startswith("battlebox"):
            for item in box["fields"].get("conflict", []):
                for link in item["links"]:
                    if types.get(link) in ("Event", "Concept") and link not in FORCE_TYPE:
                        types[link] = "War"

for title in BOOKS:
    types.setdefault(title, "Book")
episode_titles = {}
for ep in episodes:
    name = f"S{ep['season']:02d}E{ep['episode_in_season']:02d} {ep['title']}"
    episode_titles[(ep["season"], ep["episode_in_season"])] = name
    types[name] = "Episode"

print(Counter(types.values()).most_common())


#%%
alias_to_title = {}
for row in redirects:
    if row["title"] in types:
        for alias in row["aliases"]:
            alias_to_title.setdefault(alias, row["title"])


def resolve(name):
    if not name:
        return None
    name = name.strip().replace("_", " ")
    name = name[0].upper() + name[1:]
    if name in types:
        return name
    return alias_to_title.get(name)


page_chunks = defaultdict(list)
for chunk in chunks:
    page_chunks[chunk["page_title"]].append(chunk)
intro_chunk = {t: rows[0]["chunk_id"] for t, rows in page_chunks.items()}


def evidence(owner, other, also=None):
    needle = re.sub(r"\s*\(.*\)$", "", other)
    for page in (owner, also):
        for chunk in page_chunks.get(page, []):
            if needle in chunk["text"]:
                return chunk["chunk_id"]
    return None


def item_book(item):
    books = [BOOK_CODES[code] for code, _ in item["refs"] if code in BOOK_CODES]
    return min(books) if books else None


edges = {}
dropped = Counter()
unresolved = Counter()


def add_edge(src, dst, edge_type, source, cost, spoiler=None, owner=None, attrs=None):
    if src == dst:
        return
    if edge_type in SYMMETRIC and src > dst:
        src, dst = dst, src
    key = (src, dst, edge_type)
    cur = edges.get(key)
    if cur is None:
        edges[key] = {
            "src": src, "dst": dst, "type": edge_type, "source": source, "cost": cost,
            "spoiler_book": spoiler, "evidence_chunk_id": None, "attrs": attrs or {},
            "_owner": owner or src,
        }
    elif spoiler is not None and (cur["spoiler_book"] is None or spoiler < cur["spoiler_book"]):
        cur["spoiler_book"] = spoiler


def apply_field(title, field, items, edge_type, direction, allowed, attrs=None, accepted=None):
    for item in items:
        for link in item["links"]:
            target = resolve(link)
            if target is None:
                unresolved[link] += 1
                dropped[f"{edge_type}:{field}:unresolved"] += 1
            elif types[target] not in allowed:
                if types[target] not in (accepted or allowed):
                    dropped[f"{edge_type}:{field}:{types[target]}"] += 1
            else:
                src, dst = (title, target) if direction == "out" else (target, title)
                add_edge(src, dst, edge_type, "infobox", COST["infobox"], item_book(item), title, attrs)


#%%
for title, rec in structured.items():
    if title not in types:
        continue
    for box in rec["infoboxes"]:
        template = clean_template(box["template"])
        rules = RULES.get(template, [])
        if template.startswith(("battlebox", "infobox military conflict")):
            rules = BATTLE_RULES
            for field, items in box["fields"].items():
                m = SIDE_FIELD.match(field)
                if m and m.group(1) == "combatant":
                    apply_field(title, field, items, "COMBATANT_IN", "in", SIDE, {"side": int(m.group(2))})
                elif m:
                    apply_field(title, field, items, "COMMANDED_IN", "in", CHAR, {"side": int(m.group(2))})
        for field, edge_type, direction, allowed in rules:
            if field in box["fields"]:
                accepted = set().union(*(rule[3] for rule in rules if rule[0] == field))
                apply_field(title, field, box["fields"][field], edge_type, direction, allowed, accepted=accepted)


#%%
for ep in episodes:
    name = episode_titles[(ep["season"], ep["episode_in_season"])]
    for book in ep["books"] or []:
        add_edge(BOOKS[book - 1], name, "ADAPTED_AS", "kaggle", COST["kaggle"])

for char in characters:
    title = resolve(char["page_title"])
    if title is None:
        continue
    allegiance = char["allegiance"]
    if allegiance:
        for name in (f"House {allegiance}", allegiance, f"{allegiance}s"):
            house = resolve(name)
            if house and types[house] in GROUP:
                add_edge(title, house, "MEMBER_OF", "kaggle", COST["kaggle"])
                break
    if char["death_book"]:
        book = int(char["death_book"])
        add_edge(title, BOOKS[book - 1], "DIED_IN", "kaggle", COST["kaggle"], book, title,
                 {"chapter": char["death_chapter"], "year": char["death_year"]})

for battle in battles:
    title = resolve(battle["page_title"])
    if title is None:
        continue
    size = {"attacker_size": battle["attacker_size"], "defender_size": battle["defender_size"]}
    for side, edge_type in (("attackers", "ATTACKED_IN"), ("defenders", "DEFENDED_IN")):
        for name in battle[side]:
            house = resolve(f"House {name}") or resolve(name)
            if house and types[house] in GROUP:
                add_edge(house, title, edge_type, "kaggle", COST["kaggle"], owner=title, attrs=size)
    for side in ("attacker", "defender"):
        for name in battle[f"{side}_commanders"]:
            person = resolve(name)
            if person and types[person] == "Character":
                add_edge(person, title, "COMMANDED_IN", "kaggle", COST["kaggle"], owner=title,
                         attrs={"side": side})
        king = battle[f"{side}_king"]
        parts = [p.strip() for p in king.split("/")] if king else []
        if len(parts) == 2:
            parts[0] = f"{parts[0]} {parts[1].split()[-1]}"
        for name in parts:
            person = resolve(name)
            if person and types[person] == "Character":
                add_edge(person, title, "KING_IN", "kaggle", COST["kaggle"], owner=title, attrs={"side": side})
    place = resolve(battle["location"])
    if place and types[place] in PLACE:
        add_edge(title, place, "OCCURRED_AT", "kaggle", COST["kaggle"], owner=title)


#%%
appearances = defaultdict(set)
debut = {}
for char in characters:
    title = resolve(char["page_title"])
    if title and char["first_book"]:
        debut[title] = min(debut.get(title, 9), int(char["first_book"]))

for title, node_type in types.items():
    if node_type not in ("Chapter", "Book") or title not in structured:
        continue
    rec = structured[title]
    book = book_of(title)
    if book:
        add_edge(title, BOOKS[book - 1], "IN_BOOK", "structure", COST["structure"], book)
    pov = {link for box in rec["infoboxes"] for item in box["fields"].get("pov", []) for link in item["links"]}
    pov = {resolve(link) for link in pov}
    for box in rec["infoboxes"]:
        for item in box["fields"].get("place", []):
            for link in item["links"]:
                target = resolve(link)
                if target and types[target] in PLACE:
                    add_edge(title, target, "SET_IN", "infobox", COST["infobox"], book, title)
    ranked = sorted(rec["lists"].items(), key=lambda kv: (kv[0] != "appearing", kv[0] != "cast_unsplit"))
    seen = set()
    for label, links in ranked:
        edge_type = {"appearing": "APPEARS_IN", "cast_unsplit": "APPEARS_OR_MENTIONED_IN"}.get(label, "MENTIONED_IN")
        attrs = {"dream": True} if "dream" in label else {}
        for link in links:
            target = resolve(link)
            if target is None:
                unresolved[link] += 1
                dropped[f"{edge_type}:unresolved"] += 1
                continue
            if target in seen or types[target] in ("Chapter", "Book", "Episode"):
                continue
            seen.add(target)
            node_attrs = {"pov": True, **attrs} if target in pov else attrs
            add_edge(target, title, edge_type, "chapter_list", COST[edge_type], book, title, node_attrs)
            appearances[target].add(title)
            if edge_type == "APPEARS_IN" and book:
                debut[target] = min(debut.get(target, 9), book)


#%%
typed_pairs = {frozenset((e["src"], e["dst"])) for e in edges.values()}
no_links = {"Chapter", "Book", "Episode"}
resolved_links = {}
for title, rec in pages.items():
    if types[title] in no_links:
        continue
    targets = {resolve(link) for link in rec["links"]}
    resolved_links[title] = {t for t in targets if t and t != title and types[t] not in no_links}

for title, targets in resolved_links.items():
    for target in targets:
        if frozenset((title, target)) in typed_pairs:
            continue
        kind = "LINK_MUTUAL" if title in resolved_links.get(target, ()) else "LINK_ONEWAY"
        add_edge(title, target, "LINKS_TO", "wiki_link", COST[kind])

for edge in edges.values():
    if edge["spoiler_book"] is None:
        shared = appearances[edge["src"]] & appearances[edge["dst"]]
        books = [book_of(c) for c in shared if book_of(c)]
        if books:
            edge["spoiler_book"] = min(books)
    owner = edge.pop("_owner")
    other = edge["dst"] if owner == edge["src"] else edge["src"]
    edge["evidence_chunk_id"] = evidence(owner, other, other)


#%%
titles = sorted(types)
index = {t: i for i, t in enumerate(titles)}
n = len(titles)
src = np.array([index[e["src"]] for e in edges.values()])
dst = np.array([index[e["dst"]] for e in edges.values()])
weight = 1.0 / np.array([e["cost"] for e in edges.values()])
both_src, both_dst, both_w = np.r_[src, dst], np.r_[dst, src], np.r_[weight, weight]
out_weight = np.bincount(both_src, weights=both_w, minlength=n)
step = both_w / out_weight[both_src]

rank = np.full(n, 1.0 / n)
for _ in range(50):
    rank = 0.15 / n + 0.85 * np.bincount(both_dst, weights=rank[both_src] * step, minlength=n)

degree = Counter()
for pair in {frozenset((e["src"], e["dst"])) for e in edges.values()}:
    for title in pair:
        degree[title] += 1

nodes = [{
    "id": index[t],
    "title": t,
    "type": types[t],
    "kinds": pages[t]["kinds"] if t in pages else [],
    "url": pages[t]["url"] if t in pages else None,
    "debut_book": debut.get(t),
    "degree": degree[t],
    "pagerank_global": float(rank[index[t]]),
    "intro_chunk_id": intro_chunk.get(t),
} for t in titles]

aliases = {(row["alias"], index[row["title"]]) for row in (
    {"alias": alias, "title": title} for alias, title in alias_to_title.items())}
for title, rec in structured.items():
    if title in index:
        for box in rec["infoboxes"]:
            for field in ("alias", "epithet", "nickname"):
                for item in box["fields"].get(field, []):
                    if item["text"]:
                        aliases.add((item["text"], index[title]))

write_jsonl(f"{CLEAN}/graph_nodes.jsonl", nodes)
write_jsonl(f"{CLEAN}/graph_edges.jsonl", edges.values())
write_jsonl(f"{CLEAN}/aliases.jsonl", [{"alias": a, "node_id": i} for a, i in sorted(aliases)])


#%%
rows = list(edges.values())
print(len(nodes), "nodes |", len(rows), "edges |", len(aliases), "aliases")
print(Counter(r["type"] for r in nodes).most_common())
print(Counter(e["type"] for e in rows).most_common())
print(Counter(e["source"] for e in rows).most_common())
print("spoiler on edges", round(sum(e["spoiler_book"] is not None for e in rows) / len(rows), 3))
print("evidence on edges", round(sum(e["evidence_chunk_id"] is not None for e in rows) / len(rows), 3))
print("debut_book on nodes", sum(r["debut_book"] is not None for r in nodes))
print("isolated", sum(r["degree"] == 0 for r in nodes))
print("dropped", dropped.most_common(40))
print("unresolved", unresolved.most_common(30))
