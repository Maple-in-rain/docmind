import importlib

from fastapi.testclient import TestClient


def test_root_and_docmind_prefix_share_routes_assets_and_schema(monkeypatch):
    from app import services
    from types import SimpleNamespace
    fake = {"db": SimpleNamespace(doc_count=lambda: 3),
            "vector_store": SimpleNamespace(count=lambda: 5)}
    monkeypatch.setattr(services, "build_services", lambda: fake)
    module = importlib.import_module("app.main")
    with TestClient(module.app) as client:
        for prefix in ("", "/docmind"):
            health = client.get(prefix + "/api/health")
            assert health.status_code == 200
            assert health.json()["doc_count"] == 3
            page = client.get(prefix + "/")
            assert page.status_code == 200 and "DocMind" in page.text
            assert 'src="paths.js"' in page.text
            assert client.get(prefix + "/paths.js").status_code == 200
            assert client.get(prefix + "/app.js").status_code == 200
            schema = client.get(prefix + "/openapi.json").json()
            assert "/api/agent" in schema["paths"]
            assert prefix + "/openapi.json" in client.get(prefix + "/docs").text
        assert client.get("/docmind", follow_redirects=False).headers["location"] == "/docmind/"
        module.app.state.services = {"db": SimpleNamespace(doc_count=lambda: 7),
                                     "vector_store": SimpleNamespace(count=lambda: 9)}
        assert client.get("/api/health").json()["doc_count"] == 7
        assert client.get("/docmind/api/health").json()["doc_count"] == 7
