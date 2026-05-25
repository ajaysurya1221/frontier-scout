# Reference Stack

Absorb ideas, not code, unless the license is permissive and the dependency is
explicitly added.

| Reference | URL | License / status | Activity | Absorbed ideas | Absorbed code |
|---|---|---|---|---|---|
| Microsoft GraphRAG | https://github.com/microsoft/graphrag | MIT | pushed 2026-05-19 | local/global GraphRAG | no |
| Cost-efficient enterprise GraphRAG | https://arxiv.org/abs/2507.03226 | paper | 2025 paper | deterministic KG construction | no |
| LangGraph | https://github.com/langchain-ai/langgraph | MIT | pushed 2026-05-24 | durable execution, interrupts | no |
| OpenAI Agents SDK | https://github.com/openai/openai-agents-python | MIT | pushed 2026-05-22 | handoffs, guardrails, tracing | no |
| PydanticAI | https://github.com/pydantic/pydantic-ai | MIT | pushed 2026-05-25 | typed contracts | no |
| Semantic Kernel | https://github.com/microsoft/semantic-kernel | MIT | pushed 2026-05-19 | plugin/filter discipline | no |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk | MIT | pushed 2026-05-21 | tool schemas and adapters | no |
| MCP TypeScript SDK | https://github.com/modelcontextprotocol/typescript-sdk | unclear | pushed 2026-05-25 | protocol shape only | no |
| OpenFGA | https://github.com/openfga/openfga | Apache-2.0 | pushed 2026-05-24 | local ReBAC model | no |
| SpiceDB | https://github.com/authzed/spicedb | Apache-2.0 | pushed 2026-05-23 | Zanzibar-style checks | no |
| OpenTelemetry spec | https://github.com/open-telemetry/opentelemetry-specification | Apache-2.0 | pushed 2026-05-25 | spans and attributes | no |
| OTel GenAI semconv | https://opentelemetry.io/docs/specs/semconv/gen-ai/ | spec docs | current May 2026 | GenAI span naming | no |
| Promptfoo | https://github.com/promptfoo/promptfoo | MIT | pushed 2026-05-25 | eval/red-team CLI patterns | no |
| DeepEval | https://github.com/confident-ai/deepeval | Apache-2.0 | pushed 2026-05-25 | grader ergonomics | no |
| MLflow | https://github.com/mlflow/mlflow | Apache-2.0 | pushed 2026-05-25 | eval tracking ideas | no |
| Qdrant | https://github.com/qdrant/qdrant | Apache-2.0 | pushed 2026-05-25 | Docker vector store option | no |
| Chroma | https://github.com/chroma-core/chroma | Apache-2.0 | pushed 2026-05-25 | embedded vector option | no |
| Weaviate | https://github.com/weaviate/weaviate | BSD-3-Clause | pushed 2026-05-25 | hybrid filtering | no |
| Graphiti | https://github.com/getzep/graphiti | Apache-2.0 | pushed 2026-05-21 | temporal KG ideas | no |
| Apache AGE | https://github.com/apache/age | Apache-2.0 | pushed 2026-05-14 | optional graph store | no |
| TerminusDB | https://github.com/terminusdb/terminusdb | Apache-2.0 | pushed 2026-05-23 | versioned data/provenance | no |
| LiteLLM | https://github.com/BerriAI/litellm | unclear | pushed 2026-05-25 | gateway concepts only | no |
| Cloudflare AI Gateway | https://developers.cloudflare.com/ai-gateway/observability/index | docs | current May 2026 | caching, logs, OTel | no |
| Cloudflare audit logs | https://developers.cloudflare.com/api/resources/ai_gateway/subresources/logs/ | docs | current May 2026 | audit record shape | no |
| NIST AI RMF | https://www.nist.gov/itl/ai-risk-management-framework | public standard | current May 2026 | governance mapping | no |
| NIST GenAI Profile | https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf | public standard | current | GAI controls | no |
| OWASP Agentic Top 10 | https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ | public framework | 2026 | threat categories | no |
| OpenAI prompt caching | https://platform.openai.com/docs/guides/prompt-caching/overview | docs | current May 2026 | stable-prefix compiler | no |
| OpenAI prompting | https://platform.openai.com/docs/guides/prompting | docs | current May 2026 | prompt structure/evals | no |

Rejected or downgraded: AutoGen, Neo4j GraphRAG, Kuzu, Memgraph, FalkorDB,
ArangoDB, Langfuse, Phoenix, and LiteLLM are not runtime dependencies in this
release because license/activity metadata needs manual verification or the
project is not suitable as a default local dependency.

