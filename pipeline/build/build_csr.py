
#%%
import json
import os

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

CLEAN = "data/clean"
INDEX = "data/index"
LAM = 0.5
LAM_HIGH = 1.0
HIGH_TOLL_TYPES = {"Concept", "Year"}
CHAPTER_TYPES = {"APPEARS_IN", "MENTIONED_IN", "APPEARS_OR_MENTIONED_IN"}
K = 200
SAMPLE_SEEDS = 500


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


nodes = read_jsonl(f"{CLEAN}/graph_nodes.jsonl")
edges = read_jsonl(f"{CLEAN}/graph_edges.jsonl")

with open(os.path.join(INDEX, "chunk_ids.json"), encoding="utf-8") as f:
    chunk_row = {chunk_id: i for i, chunk_id in enumerate(json.load(f))}

index = {n["title"]: n["id"] for n in nodes}
n_nodes = len(nodes)
edge_types = sorted({e["type"] for e in edges})
type_id = {t: i for i, t in enumerate(edge_types)}


#%%
src = np.array([index[e["src"]] for e in edges], dtype=np.int32)
dst = np.array([index[e["dst"]] for e in edges], dtype=np.int32)
cost = np.array([e["cost"] for e in edges], dtype=np.float32)
kind = np.array([type_id[e["type"]] for e in edges], dtype=np.int8)
spoiler = np.array([e["spoiler_book"] or 0 for e in edges], dtype=np.int8)
evidence = np.array([chunk_row.get(e["evidence_chunk_id"], -1) for e in edges], dtype=np.int32)
row = np.arange(len(edges), dtype=np.int32)
is_link = kind == type_id["LINKS_TO"]

rows = np.r_[src, dst]
cols = np.r_[dst, src]
costs = np.r_[cost, cost]
kinds = np.r_[kind, kind]
spoilers = np.r_[spoiler, spoiler]
edge_rows = np.r_[row, row]
evidences = np.r_[evidence, evidence]
links = np.r_[is_link, is_link]
forward = np.r_[np.ones(len(edges), dtype=np.int8), np.zeros(len(edges), dtype=np.int8)]

order = np.lexsort((edge_rows, links, costs, cols, rows))
rows, cols, costs, kinds, spoilers, edge_rows, evidences, forward = (
    a[order] for a in (rows, cols, costs, kinds, spoilers, edge_rows, evidences, forward))

keep = np.r_[True, (rows[1:] != rows[:-1]) | (cols[1:] != cols[:-1])]
blocked = np.flatnonzero(keep)
group = np.cumsum(keep) - 1
open_pair = np.zeros(len(blocked), dtype=bool)
np.logical_or.at(open_pair, group, spoilers == 0)
print("directed", len(rows), "| unique", int(keep.sum()), "| parallel dropped", int((~keep).sum()))
print("kept edge masked though a parallel edge is null:", int((open_pair & (spoilers[blocked] != 0)).sum()))

rows, cols, costs, kinds, spoilers, edge_rows, evidences, forward = (
    a[keep] for a in (rows, cols, costs, kinds, spoilers, edge_rows, evidences, forward))
print("kept entries without evidence:", int((evidences < 0).sum()))


#%%
indptr = np.zeros(n_nodes + 1, dtype=np.int64)
np.add.at(indptr, rows + 1, 1)
indptr = np.cumsum(indptr)

degree = np.diff(indptr)
lam = np.array([LAM_HIGH if n["type"] in HIGH_TOLL_TYPES else LAM for n in nodes], dtype=np.float32)
toll = (lam * np.log1p(degree)).astype(np.float32)

first_book = np.array([n["debut_book"] or 0 for n in nodes], dtype=np.int8)
for e in edges:
    if e["type"] in CHAPTER_TYPES and e["spoiler_book"]:
        i = index[e["src"]]
        first_book[i] = min(first_book[i] or 9, e["spoiler_book"])
print("first_book known on", int((first_book > 0).sum()), "nodes")

weights =(costs + toll[cols]).astype(np.float64)
graph = csr_matrix((weights, cols, indptr), shape=(n_nodes, n_nodes))

rng = np.random.default_rng(0)
seeds = rng.choice(np.flatnonzero(degree > 0), SAMPLE_SEEDS, replace=False)
radii = [np.partition(dijkstra(graph, directed=True, indices=int(s)), K)[K] for s in seeds]
radius = float(np.median(radii))
print("radius of", K, "nearest: median", round(radius, 2), "min", round(float(min(radii)), 2),
      "max", round(float(max(radii)), 2))


#%%
for name, array in (("indptr", indptr), ("indices", cols), ("cost", costs), ("type", kinds),
                    ("spoiler", spoilers), ("edge", edge_rows), ("evidence", evidences), ("forward", forward)):
    np.save(os.path.join(INDEX, f"csr_{name}.npy"), array)
np.save(os.path.join(INDEX, "node_toll.npy"), toll)
np.save(os.path.join(INDEX, "node_first_book.npy"), first_book)

with open(os.path.join(INDEX, "csr_meta.json"), "w", encoding="utf-8") as f:
    json.dump({"edge_types": edge_types, "k": K, "radius": radius, "lam": LAM, "lam_high": LAM_HIGH}, f, indent=1)

with open(os.path.join(INDEX, "node_titles.json"), "w", encoding="utf-8") as f:
    json.dump([n["title"] for n in nodes], f, ensure_ascii=False)

print(n_nodes, "nodes |", len(cols), "entries |",
      round(sum(a.nbytes for a in (indptr, cols, costs, kinds, spoilers, edge_rows, evidences, forward, toll)) / 1e6, 1), "MB")
