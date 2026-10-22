"""Consent precedes all transport activity; host scope covers redirects too."""

import asyncio
import io

import httpx
import pytest

from trugs_web.cli import main
from trugs_web.crawler import SourceDiscoverer


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def transport(monkeypatch):
    requests = []
    consented = [False]

    def handle(request):
        assert consented[0], "transport called before consent"
        requests.append(str(request.url))
        host = request.url.host
        path = request.url.path
        if path == "/robots.txt" and host == "seed.test":
            return httpx.Response(
                302, headers={"location": "https://other.test/robots.txt"}
            )
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if path == "/redirect":
            return httpx.Response(
                302, headers={"location": "https://other.test/target"}
            )
        html = "<title>Sources</title>"
        if host == "seed.test" and path == "/":
            html += '<a href="https://other.test/linked">External</a><a href="/redirect">Redirect</a>'
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    original = httpx.AsyncClient

    def client(**kwargs):
        return original(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return requests, consented


@pytest.mark.parametrize("verb", ["crawl", "build"])
@pytest.mark.parametrize("mode", ["no", "eof", "pipe"])
def test_refusals_make_no_request(verb, mode, transport, monkeypatch, capsys):
    requests, _ = transport
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO("yes\n")
        if mode == "pipe"
        else Terminal("no\n" if mode == "no" else ""),
    )
    assert (
        main([verb, "https://seed.test", "https://second.test", "--topic", "graphs"])
        != 0
    )
    prompt = capsys.readouterr().err
    assert (
        "seed.test" in prompt
        and "second.test" in prompt
        and "--allow-other-hosts" in prompt
    )
    assert requests == []


@pytest.mark.parametrize("verb", ["crawl", "build"])
@pytest.mark.parametrize("allow", [False, True])
@pytest.mark.parametrize("automatic", [False, True])
def test_cli_consent_and_host_boundaries(
    verb, allow, automatic, transport, monkeypatch, capsys
):
    requests, consented = transport
    args = [verb, "https://seed.test/", "--topic", "graphs"]
    if allow:
        args.append("--allow-other-hosts")
    if automatic:
        args.append("--yes")
        consented[0] = True
    else:
        monkeypatch.setattr("sys.stdin", Terminal())

        def approve():
            assert requests == []
            prompt = capsys.readouterr().err
            assert "seed.test" in prompt and "--allow-other-hosts" in prompt
            consented[0] = True
            return "yes"

        monkeypatch.setattr("builtins.input", approve)
    assert main(args) == 0
    assert requests
    other = [url for url in requests if "other.test" in url]
    if allow:
        assert "https://other.test/robots.txt" in other
        assert "https://other.test/linked" in other
        assert "https://other.test/target" in other
    else:
        assert other == []
    if verb == "crawl":
        assert "https://other.test/linked" in capsys.readouterr().out


@pytest.mark.parametrize("allow", [False, True])
def test_record_external_links_and_redirect_targets(allow, transport):
    requests, consented = transport
    consented[0] = True
    sources = asyncio.run(
        SourceDiscoverer(allow_other_hosts=allow).discover(["https://seed.test/"])
    )
    links = {link for source in sources for link in source.outbound_links}
    assert "https://other.test/linked" in links
    if not allow:
        assert "https://other.test/target" in links
        assert all(httpx.URL(url).host == "seed.test" for url in requests)


def test_invalid_seed_does_not_request(transport, capsys):
    assert main(["crawl", "file:///example", "--yes"]) == 1
    assert transport[0] == []
    assert "HTTP" in capsys.readouterr().err
