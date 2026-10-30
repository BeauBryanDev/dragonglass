
import heapq
import math


def shortest(starts, heads, 
             weight, seeds,
             limit=math.inf):

    dist = {node: 0.0 for node in seeds}
    came_from = {}
    heap = [(0.0, node) for node in dist]
    heapq.heapify(heap)

    while heap:
        d, node = heapq.heappop(heap)

        if d > dist[node]:
            continue

        for entry in range(starts[node], starts[node + 1]):

            next_node = heads[entry]
            next_dist = d + weight[entry]

            if next_dist <= limit and next_dist < dist.get(next_node, math.inf):
                dist[next_node] = next_dist
                came_from[next_node] = (node, entry)
                heapq.heappush(heap, (next_dist, next_node))

    return dist, came_from


def walk_back(target, came_from):

    node = target
    steps = []

    while node in came_from:

        parent, entry = came_from[node]
        steps.append((parent, node, entry))
        node = parent

    steps.reverse()

    return node, steps
