
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.routers import health
from app.stores.chunk_store import ChunkStore
from app.stores.graph_store import GraphStore


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):

    setup_logging()

    app.state.graph_store = GraphStore(settings.index_dir)
    logger.info("graph store loaded: %d nodes", app.state.graph_store.n_nodes)

    app.state.chunk_store = ChunkStore(settings.clean_dir, settings.index_dir)
    logger.info("chunk store loaded: %d chunks", len(app.state.chunk_store.chunks))

    yield

    logger.info("shutting down")


app = FastAPI(title=settings.app_name, lifespan=lifespan)

register_exception_handlers(app)

app.add_middleware(CORSMiddleware,
                   allow_origins=settings.cors_origins,
                   allow_methods=["*"],
                   allow_headers=["*"])

app.include_router(health.router)
