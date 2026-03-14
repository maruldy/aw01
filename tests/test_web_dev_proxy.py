from pathlib import Path


def test_vite_proxy_uses_ipv4_and_preserves_spa_routes() -> None:
    content = Path("apps/web/vite.config.ts").read_text(encoding="utf-8")

    assert '"http://127.0.0.1:8000"' in content

    assert '"/runs":' not in content
    assert '"/runs/":' in content

    assert '"/knowledge":' not in content
    assert '"/knowledge/":' in content

    assert '"/settings":' not in content
    assert '"/settings/":' in content
