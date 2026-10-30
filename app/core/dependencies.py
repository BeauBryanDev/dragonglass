
from fastapi import Request

from app.services.graph_service import GraphService


def get_graph_service(request: Request):

    return GraphService(request.app.state.graph_store,
                        request.app.state.chunk_store)
