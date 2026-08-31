"""Change 166: _backend_image_digest — Digest-Quelle für den ETA-Learner."""

from app import docker_proxy, service


def test_backend_image_digest_via_proxy(monkeypatch):
    class FakeClient:
        def list_containers(self):
            return [
                {"Labels": {"com.docker.compose.service": "ps-pk-onnx"},
                 "ImageID": "sha256:aaa111"},
                {"Labels": {"com.docker.compose.service": "crispr-sep"},
                 "ImageID": "sha256:bbb222"},
                {"Labels": {"other": "x"}, "ImageID": "sha256:ccc333"},
            ]

    monkeypatch.setattr(docker_proxy, "get_docker_client", lambda: FakeClient())
    assert service._backend_image_digest("ps-pk-onnx") == "sha256:aaa111"
    assert service._backend_image_digest("crispr-sep") == "sha256:bbb222"
    assert service._backend_image_digest("unbekannt") is None
    assert service._backend_image_digest("") is None
    assert service._backend_image_digest(None) is None


def test_backend_image_digest_ohne_imageid(monkeypatch):
    class FakeClient:
        def list_containers(self):
            return [{"Labels": {"com.docker.compose.service": "ps-pk-onnx"}}]

    monkeypatch.setattr(docker_proxy, "get_docker_client", lambda: FakeClient())
    assert service._backend_image_digest("ps-pk-onnx") is None


def test_backend_image_digest_proxy_fehler(monkeypatch):
    def boom():
        raise RuntimeError("proxy down")

    monkeypatch.setattr(docker_proxy, "get_docker_client", boom)
    assert service._backend_image_digest("ps-pk-onnx") is None
