"""JWTs are exchanged once before k6, concurrently and in roster order; a refusal stops."""
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
import jwt_tenants


class Server(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        Server.seen.append((self.headers['Host'], self.path))
        token = self.path.rsplit('/', 1)[1]
        if token == 'refused':
            self.send_response(401); self.end_headers(); return
        body = json.dumps({'token': 'jwt-' + token}).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body)

    def log_message(self, *args):
        pass


class JwtTenants(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Server)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:%d' % self.server.server_port

    def test_roster_gains_jwts_in_order_and_file_is_private(self):
        rows = [{'id': str(i), 'host': 't%d.test' % i, 'token': 'token%d' % i} for i in range(9)]
        result = jwt_tenants.attach(rows, self.base, 4)
        self.assertEqual([r['jwt'] for r in result], ['jwt-token%d' % i for i in range(9)])
        self.assertEqual({h for h, _ in Server.seen if h.startswith('t')}, {'t%d.test' % i for i in range(9)})
        with tempfile.TemporaryDirectory() as tmp:
            path = jwt_tenants.write(Path(tmp) / 'k6-tenants.private.json', result)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), result)

    def test_roster_jwt_is_used_only_when_it_covers_the_run(self):
        Server.seen.clear()
        rows = [{'id': 'a', 'host': 'a.test', 'token': 'ta', 'jwt': 'roster-a', 'jwtExpiresAt': 2000},
                {'id': 'b', 'host': 'b.test', 'token': 'tb', 'jwt': 'roster-b', 'jwtExpiresAt': 999},
                {'id': 'c', 'host': 'c.test', 'token': 'tc'}]
        result = jwt_tenants.attach(rows, self.base, 2, covers_until=1000)
        self.assertEqual([r['jwt'] for r in result], ['roster-a', 'jwt-tb', 'jwt-tc'])
        self.assertEqual(sorted(h for h, _ in Server.seen), ['b.test', 'c.test'])
        # Without a run bound every row exchanges, as before.
        self.assertEqual([r['jwt'] for r in jwt_tenants.attach(rows, self.base, 2)], ['jwt-ta', 'jwt-tb', 'jwt-tc'])

    def test_refusal_stops_before_load(self):
        with self.assertRaisesRegex(RuntimeError, 'M7_JWT_EXCHANGE_REFUSED:401'):
            jwt_tenants.attach([{'id': 'x', 'host': 'x.test', 'token': 'refused'}], self.base, 1)


if __name__ == '__main__':
    unittest.main()
