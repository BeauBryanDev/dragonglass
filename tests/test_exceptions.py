
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exceptions import (DragonglassError, LLMServiceError, NodeNotFoundError,
                                 register_exception_handlers)
from app.main import app as main_app

INTERNAL = "private path /home/ubuntu/data"


@pytest.fixture
def client():

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/node")
    def node():
        raise NodeNotFoundError("Azor Ahai")

    @app.get("/llm")
    def llm():
        raise LLMServiceError()

    @app.get("/teapot")
    def teapot():
        raise HTTPException(status_code=418, detail="short and stout")

    @app.get("/boom")
    def boom():
        raise RuntimeError(INTERNAL)

    @app.get("/typed")
    def typed(book: int):
        return {"book": book}

    return TestClient(app)


def test_domain_error_shape(client):

    response = client.get("/node")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "node_not_found",
                                         "message": "No graph node titled 'Azor Ahai'"}}


def test_upstream_error_is_503(client):

    response = client.get("/llm")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"


def test_http_exception_uses_same_shape(client):

    response = client.get("/teapot")

    assert response.status_code == 418
    assert response.json()["error"] == {"code": "http_418", "message": "short and stout"}


def test_unknown_route_uses_same_shape(client):

    assert client.get("/nope").json()["error"]["code"] == "http_404"


def test_validation_error_uses_same_shape(client):

    response = client.get("/typed", params={"book": "five"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"][0]["loc"] == ["query", "book"]


def test_unhandled_error_hides_internals(client):

    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == DragonglassError.code
    assert INTERNAL not in response.text


def test_unhandled_error_keeps_cors_headers():

    def boom():
        raise RuntimeError(INTERNAL)

    main_app.add_api_route("/__boom", boom)

    try:
        response = TestClient(main_app).get("/__boom",
                                            headers={"Origin": "http://localhost:5173"})
    finally:
        main_app.router.routes.pop()

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.json()["error"]["code"] == DragonglassError.code
