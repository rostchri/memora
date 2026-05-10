import asyncio

import memora.storage as storage
import memora.server as server


def _new_memory(*args, content="Repeat memory text", tags=["task"], **kwargs):
    return asyncio.run(
        server.memory_create(*args, content=content, tags=tags, **kwargs)
    )


def _raw_memory(*, content, tags, metadata=None):
    with storage.connect() as conn:
        return storage.add_memory(conn, content=content, tags=tags, metadata=metadata)


def test_memory_create_minimal_response_returns_id_only(local_db):
    r2 = _new_memory(content="Standalone memory", response_mode="minimal")

    assert r2 == {"memory": {"id": r2["memory"]["id"]}}


def test_memory_create_minimal_response_includes_similar_memory_info(local_db):
    _new_memory(content="Unique project memory for similarity coverage")
    response = _new_memory(
        content="Unique project memory for similarity coverage",
        response_mode="minimal",
    )

    assert response["memory"] == {"id": response["memory"]["id"]}
    assert response["similar_memories"]
    assert response["consolidation_hint"].startswith("Found 1 similar memories.")
    assert "warnings" in response
    assert set(response["warnings"]) == {"duplicate_warning"}


def test_memory_create_minimal_response_omits_similar_info_when_disabled(local_db):
    _new_memory(content="Another repeated memory")
    response = _new_memory(
        content="Another repeated memory",
        response_mode="minimal",
        suggest_similar=False,
    )

    assert response == {"memory": {"id": response["memory"]["id"]}}


def test_memory_digest_returns_deterministic_aggregation(local_db):
    old = _new_memory(
        content="Agent routing old design used manual pane addressing",
        tags=["clmux", "agent-routing"],
    )["memory"]
    current = _new_memory(
        content="Agent routing current design uses role-based MCP delivery",
        tags=["clmux", "agent-routing"],
    )["memory"]
    related = _new_memory(
        content="Worker registration keeps live agent role metadata available",
        tags=["clmux", "agent-routing"],
    )["memory"]
    todo = _new_memory(
        content="TODO: improve agent routing diagnostics",
        tags=["clmux", "agent-routing", "memora/todos"],
        metadata={"type": "todo", "status": "open"},
    )["memory"]
    issue = _new_memory(
        content="Issue: agent routing multiline injected asks may not wake panes",
        tags=["clmux", "agent-routing", "memora/issues"],
        metadata={"type": "issue", "status": "open"},
    )["memory"]
    issue_by_type = _raw_memory(
        content="Issue: agent routing prompt hang stored without issue tag",
        tags=["clmux", "agent-routing"],
        metadata={"type": "issue", "status": "open"},
    )
    todo_by_type = _raw_memory(
        content="Agent routing diagnostic followup stored without todo tag",
        tags=["clmux", "agent-routing"],
        metadata={"type": "todo", "status": "open"},
    )

    asyncio.run(server.memory_link(current["id"], old["id"], "supersedes"))
    asyncio.run(server.memory_link(current["id"], related["id"], "related_to"))

    digest = asyncio.run(server.memory_digest("agent routing", k=10))

    assert digest["topic"] == "agent routing"
    assert current["id"] in digest["memory_ids"]
    assert old["id"] not in digest["memory_ids"]
    assert any(
        chain["ids"] == [old["id"], current["id"]]
        for chain in digest["lineage_chains"]
    )
    assert related["id"] in digest["related_ids"]
    assert digest["todos"]
    assert digest["issues"]
    assert any(item["id"] == todo["id"] for item in digest["todos"])
    assert any(item["id"] == todo_by_type["id"] for item in digest["todos"])
    assert any(item["id"] == issue["id"] for item in digest["issues"])
    assert any(item["id"] == issue_by_type["id"] for item in digest["issues"])
    assert current["id"] in digest["source_ids"]
    assert old["id"] in digest["source_ids"]
    assert related["id"] in digest["source_ids"]


def test_memory_digest_filters_seeds_and_debug(local_db):
    filtered = _new_memory(
        content="Filtered digest target topic current plan",
        tags=["alpha", "digest"],
        metadata={"project": "target"},
    )["memory"]
    excluded = _new_memory(
        content="Filtered digest target topic excluded plan",
        tags=["beta", "digest"],
        metadata={"project": "other"},
    )["memory"]
    seed = _new_memory(
        content="Explicit seed unrelated to target query",
        tags=["seed-only"],
        metadata={"project": "seed"},
    )["memory"]
    related = _new_memory(
        content="Seed related expansion target",
        tags=["seed-only"],
    )["memory"]
    issue = _new_memory(
        content="Filtered digest target topic issue",
        tags=["alpha", "memora/issues"],
        metadata={"project": "target", "type": "issue", "status": "open"},
    )["memory"]
    other_issue = _new_memory(
        content="Filtered digest target topic other issue",
        tags=["beta", "memora/issues"],
        metadata={"project": "other", "type": "issue", "status": "open"},
    )["memory"]
    asyncio.run(server.memory_link(seed["id"], related["id"], "related_to"))

    digest = asyncio.run(
        server.memory_digest(
            "target topic",
            k=10,
            tags_all=["alpha"],
            metadata_filters={"project": "target"},
            seed_ids=[seed["id"], 999999],
            debug=True,
        )
    )

    assert filtered["id"] in digest["memory_ids"]
    assert excluded["id"] not in digest["memory_ids"]
    assert seed["id"] in digest["memory_ids"]
    assert related["id"] in digest["related_ids"]
    assert any(item["id"] == issue["id"] for item in digest["issues"])
    assert all(item["id"] != other_issue["id"] for item in digest["issues"])
    assert digest["parameters"]["tags_all"] == ["alpha"]
    assert digest["parameters"]["metadata_filters"] == {"project": "target"}
    assert digest["parameters"]["seed_ids"] == [seed["id"], 999999]
    assert digest["debug"]["missing_seed_ids"] == [999999]
    assert digest["debug"]["ranked_candidates"]
    assert "seed_ids are included explicitly" in digest["debug"]["filter_note"]


def test_memory_digest_synthesize_is_warning_only(local_db):
    _new_memory(content="Digest topic memory", tags=["digest"])

    digest = asyncio.run(server.memory_digest("digest topic", synthesize=True))

    assert "warnings" in digest
    assert digest["parameters"]["synthesize"] is True
