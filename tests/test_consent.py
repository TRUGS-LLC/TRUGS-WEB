"""Consent precedes all transport activity; host scope covers redirects too."""

import asyncio
import io
import json

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


@pytest.mark.parametrize("verb", ["crawl", "build"])
@pytest.mark.parametrize("allow", [False, True])
@pytest.mark.parametrize("automatic", [False, True])
def test_navigation_links_preserve_consent_and_host_scope(
    verb, allow, automatic, monkeypatch, capsys, tmp_path
):
    requests = []
    consented = [False]
    tags = ("nav", "header", "footer", "aside")
    expected = {f"https://other.test/{tag}" for tag in tags}

    def handle(request):
        assert consented[0], "transport called before consent"
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        html = "<title>Seed</title><p>Main text</p>"
        if request.url.host == "seed.test":
            html += "".join(
                f'<{tag}><a href="https://other.test/{tag}">Other {tag}</a></{tag}>'
                for tag in tags
            )
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    args = [verb, "https://seed.test/", "--topic", "graphs"]
    output = tmp_path / "navigation.trug.json"
    if verb == "build":
        args += ["--out", str(output)]
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
    if verb == "build":
        graph = json.loads(output.read_text())
        seed = next(
            n
            for n in graph["nodes"]
            if n["properties"].get("url") == "https://seed.test/"
        )
        links = set(seed["properties"]["outbound_links"])
    else:
        text = capsys.readouterr().out
        links = {url for url in expected if url in text}
    assert expected <= links
    other = {url for url in requests if httpx.URL(url).host == "other.test"}
    if allow:
        assert expected | {"https://other.test/robots.txt"} <= other
    else:
        assert other == set()


@pytest.mark.parametrize("allow", [False, True])
def test_navigation_links_survive_text_filtering(allow, monkeypatch):
    original = httpx.AsyncClient
    requests = []

    def handle(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<title>Seed</title><nav><a href="https://other.test/nav">Navigation text</a></nav><p>Main text</p>',
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    sources = asyncio.run(
        SourceDiscoverer(allow_other_hosts=allow).discover(["https://seed.test/"])
    )
    seed = next(source for source in sources if source.url == "https://seed.test/")
    assert "https://other.test/nav" in seed.outbound_links
    assert "Main text" in seed.content and "Navigation text" not in seed.content
    assert ("https://other.test/nav" in requests) == allow
