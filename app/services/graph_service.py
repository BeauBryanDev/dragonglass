
import math

from app.core.exceptions import NodeNotFoundError
from app.utils.dijkstra import shortest, walk_back

GROW = 1.5
MAX_GROW = 8


class GraphService:

    def __init__(self, store, chunks):

        self.store = store
        self.chunks = chunks

    def node_of(self, title):

        if title not in self.store.node_id:
            raise NodeNotFoundError(title)

        return self.store.node_id[title]

    def shortest(self, seed_titles,
                 limit=math.inf,
                 reader_book=None):

        store = self.store
        seeds = [self.node_of(t) for t in seed_titles]

        return shortest(store.starts, store.heads,
                        store.weights(reader_book),
                        seeds, limit)

    def nearest(self, title, k=None,
                reader_book=None):

        store = self.store
        k = store.meta["k"] if k is None else k
        radius = store.meta["radius"]

        for _ in range(MAX_GROW):
            dist, _came_from = self.shortest([title], radius, reader_book)

            if len(dist) > k:
                break

            radius *= GROW

        seed = self.node_of(title)
        reached = sorted((d, node) for node, d in dist.items() if node != seed)

        return [(store.titles[node], d) for d, node in reached[:k]]

    def path_to(self, title, came_from,
                reader_book=None):

        store = self.store
        seed, steps = walk_back(self.node_of(title), came_from)
        visited = [seed] + [step[1] for step in steps]

        if reader_book is not None and any(store.first_book[n] > reader_book for n in visited):
            return None

        path = []

        for parent, child, entry in steps:

            src, dst = (parent, child) if store.forward[entry] else (child, parent)

            path.append({"src": store.titles[src],
                         "type": store.meta["edge_types"][store.kind[entry]],
                         "dst": store.titles[dst],
                         "edge": int(store.edge_row[entry]),
                         "evidence": self.evidence_for(entry, reader_book)}
                        )
        return path

    def evidence_for(self, entry,
                     reader_book=None):

        row = int(self.store.evidence[entry])

        if row < 0 or not self.chunks.is_visible(row, reader_book):
            return None

        chunk = self.chunks.get(row)

        return {"chunk_id": chunk["chunk_id"],
                "path": chunk["path"],
                "text": chunk["text"]}
