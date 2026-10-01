import io
import tempfile
import unittest
from contextlib import ExitStack
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from src.config import Config
from src.webapp import serve_web


class ScanRouteTests(unittest.TestCase):
    def setUp(self):
        self.stack = self.enterContext(ExitStack())
        root = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.dict("os.environ", {"JOB_RADAR_SKIP_STARTUP_GITHUB_SYNC": "1"}))
        server = self.stack.enter_context(patch("src.webapp.make_server"))
        self.thread = self.stack.enter_context(patch("src.webapp.threading.Thread"))
        self.select_db = self.stack.enter_context(patch("src.webapp._select_dashboard_db"))
        serve_web(Config(), Mock(), repo_root=root)
        self.app = server.call_args.args[2]

    def request(self, path="/scan", method="GET", query="", body=b""):
        response = Mock()
        result = self.app({
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }, response)
        status, headers = response.call_args.args
        return status, dict(headers), b"".join(result)

    def test_opening_scan_redirects_without_scanning_or_merging(self):
        for path in ("/scan", "/scan/"):
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertEqual(status, "303 See Other")
                self.assertEqual(headers["Location"], "/?dataset=merged")
                self.assertEqual(body, b"")
        self.thread.assert_not_called()
        self.select_db.assert_not_called()

    def test_scan_redirect_keeps_filters_and_safely_encodes_values(self):
        status, headers, _ = self.request(query="dataset=merged-all&days=1&min_score=60&source=a%26b")
        self.assertEqual(status, "303 See Other")
        location = urlsplit(headers["Location"])
        self.assertEqual(location.path, "/")
        self.assertEqual(parse_qs(location.query), {
            "dataset": ["merged-all"], "days": ["1"],
            "min_score": ["60"], "source": ["a&b"],
        })
        self.thread.assert_not_called()

    def test_confirmed_sweep_link_does_not_start_scan_via_get(self):
        status, _, _ = self.request(query="scan_mode=all&confirm_full_sweep=1")
        self.assertEqual(status, "303 See Other")
        self.thread.assert_not_called()

    def test_post_starts_one_scan_and_rejects_a_second(self):
        status, _, _ = self.request(method="POST", body=b"scan_mode=main")
        self.assertEqual(status, "303 See Other")
        self.thread.assert_called_once()
        self.thread.return_value.start.assert_called_once()
        status, _, _ = self.request(method="POST", body=b"scan_mode=broad_all&confirm_broad_sweep=1")
        self.assertEqual(status, "303 See Other")
        self.thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
