
from fastapi import APIRouter, Request

from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request):

    return HealthResponse(status="ok",
                          nodes=request.app.state.graph_store.n_nodes)
