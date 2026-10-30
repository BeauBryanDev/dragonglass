
import json

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from app.core.config import settings
from app.core.exceptions import NodeNotFoundError
from app.services.graph_service import GraphService
from app.stores.chunk_store import ChunkStore
from app.stores.graph_store import GraphStore

SEEDS = 40


@pytest.fixture(scope="module")
def store():

    return GraphStore(settings.index_dir)


@pytest.fixture(scope="module")
def service(store):

    return GraphService(store, ChunkStore(settings.clean_dir, settings.index_dir))


def store_path(name):

    return settings.index_dir / name


def oracle(store, reader_book):

    weights = np.array(store.weights(reader_book))

    return csr_matrix((weights, store.indices, store.indptr),
                      shape=(store.n_nodes, store.n_nodes))


def as_array(store, dist):

    mine = np.full(store.n_nodes, np.inf)

    for node, d in dist.items():
        mine[node] = d

    return mine


@pytest.mark.parametrize("reader_book", [None, 1, 3])
def test_distances_match_scipy(store, service, reader_book):

    graph = oracle(store, reader_book)
    limit = store.meta["radius"]
    rng = np.random.default_rng(0)

    for seed in rng.choice(store.n_nodes, SEEDS, replace=False):

        seed = int(seed)
        dist, _ = service.shortest([store.titles[seed]], limit, reader_book)
        expected = dijkstra(graph, directed=True, indices=seed, limit=limit)

        assert np.array_equal(as_array(store, dist), expected)


def test_multi_source_matches_scipy(store, service):

    titles = ["Jon Snow", "Hodor", "Red Wedding"]
    limit = store.meta["radius"]
    dist, _ = service.shortest(titles, limit)
    expected = dijkstra(oracle(store, None), directed=True, min_only=True,
                        indices=[store.node_id[t] for t in titles], limit=limit)

    assert np.array_equal(as_array(store, dist), expected)


def test_path_weights_add_up_to_distance(store, service):

    dist, came_from = service.shortest(["Jon Snow"])
    weight = store.weights()

    for node in list(dist)[:500]:

        total = 0.0
        current = node

        while current in came_from:
            parent, entry = came_from[current]
            total += weight[entry]
            current = parent

        assert current == store.node_id["Jon Snow"]
        assert total == pytest.approx(dist[node])


def test_path_keeps_edge_direction(service):

    _, came_from = service.shortest(["Red Wedding"])
    path = service.path_to("Roose Bolton", came_from)

    assert [(s["src"], s["type"], s["dst"]) for s in path] == [
        ("Roose Bolton", "COMMANDED_IN", "Red Wedding")]


def test_evidence_rows_match_edges(store):

    with open(store_path("chunk_ids.json"), encoding="utf-8") as f:
        chunk_ids = json.load(f)
    with open(settings.data_dir / "clean" / "graph_edges.jsonl", encoding="utf-8") as f:
        edges = [json.loads(line) for line in f if line.strip()]

    rng = np.random.default_rng(0)

    for entry in rng.choice(len(store.evidence), 5000, replace=False):

        row = int(store.evidence[entry])
        expected = edges[int(store.edge_row[entry])]["evidence_chunk_id"]

        assert (chunk_ids[row] if row >= 0 else None) == expected


def test_path_carries_evidence(service):

    _, came_from = service.shortest(["Bran Stark"])
    path = service.path_to("Hodor", came_from)

    assert [s["type"] for s in path] == ["LINKS_TO"]
    assert path[0]["evidence"]["chunk_id"] == "1636-8"
    assert "Hodor" in path[0]["evidence"]["text"]


def test_spoiler_mode_drops_late_evidence_and_keeps_edge(service):

    _, came_from = service.shortest(["Bran Stark"], reader_book=1)
    path = service.path_to("Hodor", came_from, 1)

    assert [s["type"] for s in path] == ["LINKS_TO"]
    assert path[0]["evidence"] is None


def test_spoiler_mode_keeps_evidence_the_reader_has_reached(service):

    _, came_from = service.shortest(["Bran Stark"], reader_book=2)
    path = service.path_to("Hodor", came_from, 2)

    assert path[0]["evidence"]["chunk_id"] == "1636-8"


def test_unlabeled_chunks_always_pass(service):

    unlabeled = int(np.flatnonzero(service.chunks.spoiler == 0)[0])

    assert service.chunks.is_visible(unlabeled, 1)


def test_unknown_title_raises_domain_error(service):

    with pytest.raises(NodeNotFoundError):
        service.shortest(["Azor Ahai the Unknown"])

    with pytest.raises(NodeNotFoundError):
        service.path_to("Azor Ahai the Unknown", {})


def test_spoiler_mode_is_opt_in(service):

    _, came_from = service.shortest(["Jon Snow"])

    assert service.path_to("Tycho Nestoris", came_from) is not None


def test_spoiler_mode_hides_later_nodes(service):

    _, came_from = service.shortest(["Jon Snow"], reader_book=1)

    assert service.path_to("Tycho Nestoris", came_from, 1) is None
    assert service.path_to("Rhaegar Targaryen", came_from, 1) is not None


def test_nearest_ranks_by_distance(store, service):

    found = service.nearest("Iron Bank of Braavos")
    costs = [d for _, d in found]

    assert len(found) == store.meta["k"]
    assert costs == sorted(costs)
    assert "Iron Bank of Braavos" not in [t for t, _ in found]
