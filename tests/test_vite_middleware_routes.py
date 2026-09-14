"""gods-eye-view loaded with zero API routes in Strata. Its whole API is Vite dev-server middleware in
one 342 KB vite.config.js, and route extraction (a) skipped any file over 200 KB and (b) had no
pattern for `server.middlewares.use('/api/x', handler)`."""

from pathlib import Path

from backend.repository.intent import extract_routes

VITE_CONFIG = """
import { defineConfig } from 'vite';

function radioPlugin() {
  const middleware = async (req, res) => { res.end('ok'); };
  return {
    name: 'radio',
    configureServer(server) {
      server.middlewares.use('/api/radio', middleware);
    },
  };
}

function cctvPlugin() {
  return {
    name: 'cctv',
    configureServer(server) {
      server.middlewares.use('/api/cctv', async (req, res) => {
        const url = new URL(req.url || '/', 'http://localhost');
        if (url.pathname === '/sources') { res.end('[]'); return; }
        if (url.pathname === '/health') { res.end('ok'); return; }
        const upstream = 'https://example.com/json/servers';
        res.end(upstream);
      });
    },
  };
}

export default defineConfig({ plugins: [radioPlugin(), cctvPlugin()] });
"""


def _routes(tmp_path: Path, padding: int = 0):
    (tmp_path / "vite.config.js").write_text(VITE_CONFIG + ("// pad\n" * padding), encoding="utf-8")
    return {(r.method, r.path): r for r in extract_routes(tmp_path, ["vite.config.js"])}


def test_middleware_mounts_are_routes(tmp_path):
    routes = _routes(tmp_path)
    assert ("ANY", "/api/radio") in routes
    assert ("ANY", "/api/cctv") in routes
    assert routes[("ANY", "/api/radio")].handler == "middleware"
    assert routes[("ANY", "/api/cctv")].handler is None  # inline `async (req, res) =>`, not a name


def test_sub_paths_a_mount_dispatches_on_are_routes(tmp_path):
    routes = _routes(tmp_path)
    assert ("ANY", "/api/cctv/sources") in routes
    assert ("ANY", "/api/cctv/health") in routes
    # An upstream URL the handler fetches is not one of this app's routes.
    assert not any("json/servers" in path for _, path in routes)


def test_a_config_over_200kb_is_still_read(tmp_path):
    routes = _routes(tmp_path, padding=40_000)  # ~280 KB
    assert (tmp_path / "vite.config.js").stat().st_size > 200_000
    assert ("ANY", "/api/cctv") in routes


def test_an_http_client_call_is_still_not_a_route(tmp_path):
    (tmp_path / "client.js").write_text("axios.get('/api/users'); fetch('/api/items');\n", encoding="utf-8")
    assert extract_routes(tmp_path, ["client.js"]) == []
