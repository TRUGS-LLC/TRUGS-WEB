"""Delivered examples, query schema, core TRL and packaged data agree."""

import json
from pathlib import Path
import re
import subprocess

import jsonschema
import pytest
from trugs_tools.trl import compile, decompile
from trugs_tools.validator import validate_trug

from trugs_web.cli import main
from trugs_web.map import map_folder
from trugs_web.query import load_graph
from trugs_web.query.output import result_object
from trugs_web.query.traverse import GraphTraverser

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "hubs/semantic-and-executable-graphs"
DATA = ROOT / "src/trugs_web/data"


def public_files():
    output = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-co", "--exclude-standard", "-z"]
    )
    return sorted(
        {
            ROOT / name.decode()
            for name in output.split(b"\0")
            if name and (ROOT / name.decode()).is_file()
        }
    )


def test_every_markdown_trl_fence_round_trips():
    count = 0
    for path in public_files():
        if path.suffix != ".md":
            continue
        for text in re.findall(r"^```trl\s*\n(.*?)^```", path.read_text(), re.M | re.S):
            graph = compile(text)
            assert validate_trug(graph).valid, path
            normal = decompile(graph)
            assert decompile(compile(normal)) == normal, path
            count += 1
    assert count >= 3


def test_all_delivered_graphs_validate():
    graphs = [
        p
        for p in public_files()
        if p.name.endswith(".trug.json") and "tests" not in p.relative_to(ROOT).parts
    ]
    assert graphs
    for path in graphs:
        assert validate_trug(json.loads(path.read_text())).valid, path


def test_packaged_copies_match():
    for folder in ["examples", "hubs", "schema"]:
        source = ROOT / folder
        originals = {
            p.relative_to(source): p.read_bytes()
            for p in source.rglob("*")
            if p.is_file()
        }
        copies = {
            p.relative_to(DATA / folder): p.read_bytes()
            for p in (DATA / folder).rglob("*")
            if p.is_file()
        }
        assert originals == copies


@pytest.mark.parametrize("name", ["sample", "hub", "original"])
def test_query_formats_schema(name, tmp_path, capsys):
    paths = {"hub": HUB / "graph.trug.json", "original": ROOT / "example.trug.json"}
    if name == "sample":
        path = tmp_path / "sample.trug.json"
        path.write_text(json.dumps(map_folder(ROOT / "examples")))
    else:
        path = paths[name]
    args = ["query", str(path), "--q", "best sources"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    schema = json.loads((ROOT / "schema/query-result.schema.json").read_text())
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    validator(schema).validate(result)
    assert result["nodes"]
    assert main(args + ["--format", "text"]) == 0
    text = capsys.readouterr().out
    assert text.strip()
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


def test_path_projection_matches_schema():
    graph = load_graph(str(HUB / "graph.trug.json"))
    result = GraphTraverser(graph).citation_chain("owl", "rdf")
    assert result.paths
    jsonschema.validate(
        json.loads(json.dumps(result_object(result))),
        json.loads((ROOT / "schema/query-result.schema.json").read_text()),
    )


def test_hub_bindings_project_into_core_graph():
    graph = json.loads((HUB / "graph.trug.json").read_text())
    bindings = json.loads((HUB / "bindings.json").read_text())
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert bindings["unsigned"]
    assert decompile(graph) == decompile(compile((HUB / "hub.trl").read_text()))
    for key, binding in bindings["resources"].items():
        assert (
            binding["title"]
            and binding["address"]
            and binding["bibliography_entry"] == key
        )
        assert by_id[key]["properties"]["title"] == binding["title"]
    for key, binding in bindings["systems"].items():
        assert binding["strength"] and binding["gap"]
        assert by_id[key]["properties"]["strength"] == binding["strength"]
