from __future__ import annotations

import threading
import time
from http.server import HTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from frontier_scout.report import (
    _DEMO_SERVED_PATHS,
    _demo_request_handler,
    write_demo,
)


def test_demo_briefing_links_to_generated_artifacts(tmp_path):
    paths = write_demo(tmp_path)
    html = paths["html"].read_text()

    assert 'href="briefing.md"' in html
    assert 'href="verdicts.json"' in html
    assert 'href="cost-breakdown.md"' in html
    assert 'href="judge-trace.md"' in html
    assert 'href="quality-log.jsonl"' in html


def _ready_fetch(url: str, *, retries: int = 20, delay: float = 0.05):
    """CodeRabbit #4 — server.serve_forever races against the test;
    retry a few times so we don't flake under CI scheduler pressure."""

    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            return urlopen(url, timeout=2)
        except URLError as exc:
            last_exc = exc
            time.sleep(delay)
    raise AssertionError(f"Demo server did not become ready: {last_exc}")


def test_demo_server_root_serves_briefing_html(tmp_path):
    write_demo(tmp_path)
    server = HTTPServer(
        ("127.0.0.1", 0),
        _demo_request_handler(tmp_path.resolve(), _DEMO_SERVED_PATHS),
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_address[1]
        with _ready_fetch(f"http://127.0.0.1:{port}/") as response:
            status = response.status
            body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert status == 200
    assert "<title>Frontier Scout Radar" in body
    assert "Directory listing" not in body


def test_demo_server_blocks_unlisted_paths(tmp_path):
    """CodeRabbit #2 — only the allowlisted paths return 200. A
    stray file in the same directory must NOT be served, otherwise
    a caller reusing an existing dir could leak local files."""

    write_demo(tmp_path)
    # Drop a "secret" file alongside the demo artifacts.
    (tmp_path / "secret.txt").write_text("don't leak me")

    server = HTTPServer(
        ("127.0.0.1", 0),
        _demo_request_handler(tmp_path.resolve(), _DEMO_SERVED_PATHS),
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_address[1]
        # Warm-up — ensure the server is up.
        _ready_fetch(f"http://127.0.0.1:{port}/").close()
        try:
            urlopen(f"http://127.0.0.1:{port}/secret.txt", timeout=2)
        except HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError(
                "expected 404 for un-allowlisted /secret.txt"
            )
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
