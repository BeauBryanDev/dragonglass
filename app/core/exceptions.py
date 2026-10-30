
import logging

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class DragonglassError(Exception):

    status_code = 500
    code = "internal_error"
    message = "Something went wrong"

    def __init__(self, message=None):

        self.message = message or self.message
        super().__init__(self.message)


class NodeNotFoundError(DragonglassError):

    status_code = 404
    code = "node_not_found"

    def __init__(self, title):

        super().__init__(f"No graph node titled '{title}'")


class EmbeddingServiceError(DragonglassError):

    status_code = 503
    code = "embedding_unavailable"
    message = "The embedding service is unavailable"


class LLMServiceError(DragonglassError):

    status_code = 503
    code = "llm_unavailable"
    message = "The language model is unavailable"


class IndexAlignmentError(DragonglassError):

    code = "index_misaligned"
    message = "chunks.jsonl no longer aligns with chunk_ids.json"


def error_response(status_code, code, message, details=None, headers=None):

    error = {"code": code, "message": message}

    if details is not None:
        error["details"] = details

    return JSONResponse({"error": error}, status_code=status_code, headers=headers)


async def handle_dragonglass_error(request, exc):

    if exc.status_code >= 500:
        logger.error("%s %s failed: %s", request.method, request.url.path,
                     exc.code, exc_info=exc)

    return error_response(exc.status_code, exc.code, exc.message)


async def handle_validation_error(request, exc):

    return error_response(422, "validation_error", "Invalid request",
                          jsonable_encoder(exc.errors()))


async def handle_http_error(request, exc):

    return error_response(exc.status_code, f"http_{exc.status_code}",
                          str(exc.detail), headers=exc.headers)


class UnhandledErrorMiddleware:

    def __init__(self, app):

        self.app = app

    async def __call__(self, scope, receive, send):

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def track_send(message):

            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, track_send)
        except Exception:
            logger.exception("unhandled error on %s %s", scope["method"], scope["path"])

            if started:
                raise

            response = error_response(DragonglassError.status_code,
                                      DragonglassError.code,
                                      DragonglassError.message)
            await response(scope, receive, send)


def register_exception_handlers(app):

    app.add_exception_handler(DragonglassError, handle_dragonglass_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_middleware(UnhandledErrorMiddleware)
