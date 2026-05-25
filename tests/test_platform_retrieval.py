from pathlib import Path

from frontier_scout.platform.authz.engine import AuthzEngine
from frontier_scout.platform.memory.store import ingest_directory
from frontier_scout.platform.retrieval.hybrid import HybridRetriever


def test_retrieval_filters_unauthorized_documents():
    store = ingest_directory(Path("examples/incident_change_scout/corpus"))
    authz = AuthzEngine()
    cache_doc = next(doc for doc in store.documents.values() if doc.service == "cache-service")
    authz.add("user:alice", "read", f"document:{cache_doc.id}")

    results = HybridRetriever(store, authz).retrieve("redis cache rollout", actor="user:alice")
    denied = HybridRetriever(store, AuthzEngine()).retrieve("redis cache rollout", actor="user:bob")

    assert results
    assert denied == []
    assert all(result.citations[0].provenance.path for result in results)


def test_graph_edges_capture_dependencies():
    store = ingest_directory(Path("examples/incident_change_scout/corpus"))
    edges = store.graph_neighbors("cache-service")

    assert any(edge.relation == "depends_on" and edge.target == "service:redis-cluster" for edge in edges)

