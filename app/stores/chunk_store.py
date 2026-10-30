
import json

import numpy as np

from app.core.exceptions import IndexAlignmentError


class ChunkStore:

    def __init__(self, clean_dir, index_dir):

        with open(clean_dir / "chunks.jsonl", encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f if line.strip()]
        with open(index_dir / "chunk_ids.json", encoding="utf-8") as f:
            chunk_ids = json.load(f)

        if [c["chunk_id"] for c in self.chunks] != chunk_ids:
            raise IndexAlignmentError()

        self.spoiler = np.load(index_dir / "chunk_spoiler.npy")

    def get(self, row):

        return self.chunks[row]

    def is_visible(self, row, reader_book=None):

        return reader_book is None or self.spoiler[row] <= reader_book
