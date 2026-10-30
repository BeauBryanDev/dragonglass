
#%%
import json
import os
import sys
import time

import numpy as np
import requests

CLEAN = "data/clean"
INDEX = "data/index"
CHUNKS_PATH = os.path.join(CLEAN, "chunks.jsonl")
NODES_PATH = os.path.join(CLEAN, "graph_nodes.jsonl")
EPISODES_PATH = os.path.join(CLEAN, "episodes.jsonl")
CHUNK_EMB_PATH = os.path.join(INDEX, "chunk_emb.npy")
NODE_EMB_PATH = os.path.join(INDEX, "node_emb.npy")
CHUNK_IDS_PATH = os.path.join(INDEX, "chunk_ids.json")
NODE_IDS_PATH = os.path.join(INDEX, "node_titles.json")
SPOILER_PATH = os.path.join(INDEX, "chunk_spoiler.npy")

MODEL = "gemini-embedding-001"
API = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"
TASK = "RETRIEVAL_DOCUMENT"
DIM = 1536
BATCH = 100
DELAY = 0.5
MAX_RETRIES = 6
FIRST_WAIT = 5
LIMIT = int(os.environ.get("EMBED_LIMIT", 0))


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_key(path=".env", name="Google_APi_KEY"):
    with open(path, encoding="utf-8") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("'\"")
    raise KeyError(name)


API_KEY = read_key()


#%%
def embed_batch(texts):
    body = {"requests": [{
        "model": f"models/{MODEL}",
        "content": {"parts": [{"text": text}]},
        "taskType": TASK,
        "outputDimensionality": DIM,
    } for text in texts]}
    wait = FIRST_WAIT
    for attempt in range(MAX_RETRIES):
        resp = requests.post(API, json=body, headers={"x-goog-api-key": API_KEY}, timeout=120)
        if resp.status_code == 200:
            rows = np.array([e["values"] for e in resp.json()["embeddings"]], dtype=np.float32)
            if rows.shape != (len(texts), DIM):
                raise RuntimeError(f"unexpected shape {rows.shape}")
            return rows / np.linalg.norm(rows, axis=1, keepdims=True)
        if resp.status_code != 429 and resp.status_code < 500:
            raise RuntimeError(f"{resp.status_code} {resp.text[:400]}")
        print(f"status {resp.status_code}, waiting {wait}s", flush=True)
        if attempt < MAX_RETRIES - 1:
            time.sleep(wait)
            wait *= 3
    raise RuntimeError("retries exhausted, rerun to resume")


def pending_rows(matrix):
    return np.flatnonzero(~np.asarray(matrix).any(axis=1))


def fill(matrix, texts, label):
    pending = pending_rows(matrix)
    if LIMIT:
        pending = pending[:LIMIT]
    print(label, "pending", len(pending), "of", len(matrix), flush=True)
    start = time.time()
    for done, i in enumerate(range(0, len(pending), BATCH), 1):
        rows = pending[i:i + BATCH]
        matrix[rows] = embed_batch([texts[r] for r in rows])
        matrix.flush()
        if done % 10 == 0:
            sent = min(i + BATCH, len(pending))
            left = (time.time() - start) / sent * (len(pending) - sent) / 60
            print(f"{sent}/{len(pending)} eta_min={left:.1f}", flush=True)
        time.sleep(DELAY)


def open_matrix(path, rows):
    if os.path.exists(path):
        matrix = np.lib.format.open_memmap(path, mode="r+")
        if matrix.shape != (rows, DIM):
            sys.exit(f"{path} has shape {matrix.shape}, expected {(rows, DIM)}")
        return matrix
    return np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(rows, DIM))


#%%
os.makedirs(INDEX, exist_ok=True)
chunks = read_jsonl(CHUNKS_PATH)
chunk_ids = [c["chunk_id"] for c in chunks]

if os.path.exists(CHUNK_IDS_PATH):
    with open(CHUNK_IDS_PATH, encoding="utf-8") as f:
        if json.load(f) != chunk_ids:
            sys.exit("chunks.jsonl changed since embedding started: rows no longer align")
else:
    with open(CHUNK_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f)

chunk_emb = open_matrix(CHUNK_EMB_PATH, len(chunks))
fill(chunk_emb, [f"{c['path']}\n{c['text']}" for c in chunks], "chunks")
if LIMIT:
    sys.exit(0)
if len(pending_rows(chunk_emb)):
    sys.exit("chunks still pending, rerun to resume")


#%%
nodes = read_jsonl(NODES_PATH)
row_of = {cid: i for i, cid in enumerate(chunk_ids)}
synopsis = {f"S{e['season']:02d}E{e['episode_in_season']:02d} {e['title']}": e["synopsis"]
            for e in read_jsonl(EPISODES_PATH)}

node_emb = open_matrix(NODE_EMB_PATH, len(nodes))
node_texts = []
for n, node in enumerate(nodes):
    if node["intro_chunk_id"]:
        node_emb[n] = chunk_emb[row_of[node["intro_chunk_id"]]]
    title = node["title"]
    node_texts.append(f"{title}\n{synopsis[title]}" if synopsis.get(title) else title)
node_emb.flush()
fill(node_emb, node_texts, "nodes")

with open(NODE_IDS_PATH, "w", encoding="utf-8") as f:
    json.dump([n["title"] for n in nodes], f, ensure_ascii=False)
np.save(SPOILER_PATH, np.array([c["spoiler_book"] or 0 for c in chunks], dtype=np.int8))


#%%
for name, matrix in (("chunk_emb", chunk_emb), ("node_emb", node_emb)):
    norms = np.linalg.norm(matrix, axis=1)
    print(name, matrix.shape, matrix.dtype, "norm", round(float(norms.min()), 4), round(float(norms.max()), 4),
          "pending", len(pending_rows(matrix)), "nan", int(np.isnan(matrix).sum()))
print("spoiler counts", dict(zip(*np.unique(np.load(SPOILER_PATH), return_counts=True))))
