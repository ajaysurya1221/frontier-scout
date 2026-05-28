from __future__ import annotations

import threading
from http.server import HTTPServer
from urllib.request import urlopen

from frontier_scout.report import _demo_request_handler, write_demo


def test_demo_briefing_links_to_generated_artifacts(tmp_path):
    paths = write_demo(tmp_path)
    html = paths["html"].read_text()

    assert 'href="briefing.md"' in html
    assert 'href="verdicts.json"' in html
    assert 'href="cost-breakdown.md"' in html
    assert 'href="judge-trace.md"' in html
    assert 'href="quality-log.jsonl"' in html


def test_demo_server_root_serves_briefing_html(tmp_path):
    write_demo(tmp_path)
    server = HTTPServer(("127.0.0.1", 0), _demo_request_handler(tmp_path.resolve()))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert response.status == 200
    assert "<title>Frontier Scout Radar" in body
    assert "Directory listing" not in body
