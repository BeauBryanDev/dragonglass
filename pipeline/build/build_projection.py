
#%%
import json
import os
import sys
import time

import numpy as np

from app.utils.pca import fit, transform

INDEX = "data/index"
N_COMPONENTS = 3


#%%
embeddings = np.load(os.path.join(INDEX, "chunk_emb.npy"), mmap_mode="r")

with open(os.path.join(INDEX, "chunk_ids.json"), encoding="utf-8") as f:
    n_chunks = len(json.load(f))

if len(embeddings) != n_chunks:
    sys.exit(f"chunk_emb.npy has {len(embeddings)} rows, chunk_ids.json has {n_chunks}")
if not np.asarray(embeddings).any(axis=1).all():
    sys.exit("chunk_emb.npy still has pending rows")


#%%
start = time.time()
mean, components, singular, explained = fit(np.asarray(embeddings), N_COMPONENTS)
xyz = transform(np.asarray(embeddings), mean, components).astype(np.float32)
print("svd seconds", round(time.time() - start, 1))
print("explained variance", [round(float(e), 4) for e in explained], "total", round(float(explained.sum()), 4))
print("xyz", xyz.shape, "min", xyz.min(axis=0).round(3), "max", xyz.max(axis=0).round(3))


#%%
np.save(os.path.join(INDEX, "chunk_xyz.npy"), xyz)
np.save(os.path.join(INDEX, "pca_mean.npy"), mean)
np.save(os.path.join(INDEX, "pca_components.npy"), components)

with open(os.path.join(INDEX, "pca_meta.json"), "w", encoding="utf-8") as f:
    json.dump({"rows": int(xyz.shape[0]),
               "explained": [float(e) for e in explained],
               "singular": [float(s) for s in singular]}, f, indent=1)
