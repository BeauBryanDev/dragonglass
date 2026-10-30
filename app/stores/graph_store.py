
import json

import numpy as np


class GraphStore:

    def __init__(self, index_dir):

        self.indptr = np.load(index_dir / "csr_indptr.npy")
        self.indices = np.load(index_dir / "csr_indices.npy")
        self.cost = np.load(index_dir / "csr_cost.npy")
        self.spoiler = np.load(index_dir / "csr_spoiler.npy")
        self.kind = np.load(index_dir / "csr_type.npy")
        self.edge_row = np.load(index_dir / "csr_edge.npy")
        self.evidence = np.load(index_dir / "csr_evidence.npy")
        self.forward = np.load(index_dir / "csr_forward.npy")
        self.toll = np.load(index_dir / "node_toll.npy")
        self.first_book = np.load(index_dir / "node_first_book.npy")

        with open(index_dir / "csr_meta.json", encoding="utf-8") as f:
            self.meta = json.load(f)
        with open(index_dir / "node_titles.json", encoding="utf-8") as f:
            self.titles = json.load(f)

        self.node_id = {t: i for i, t in enumerate(self.titles)}
        self.n_nodes = len(self.titles)
        self.starts = self.indptr.tolist()
        self.heads = self.indices.tolist()
        self.weight_lists = {}

    def weights(self, reader_book=None):

        if reader_book not in self.weight_lists:

            weights = (self.cost + self.toll[self.indices]).astype(np.float64)

            if reader_book is not None:
                weights[(self.spoiler != 0) & (self.spoiler > reader_book)] = np.inf

            self.weight_lists[reader_book] = weights.tolist()

        return self.weight_lists[reader_book]
