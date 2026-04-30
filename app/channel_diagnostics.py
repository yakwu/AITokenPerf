#!/usr/bin/env python3
"""渠道诊断核心模块 — Claude prompt caching 诊断

仅支持 Anthropic /v1/messages 协议。

Probe 策略：
- cold_prefix: 首次请求，带 cache_control，建立缓存（应 creation > 0）
- warm_prefix x3: 相同前缀不同问题，应 cache_read > 0
- breaker_prefix: 改变 cache-controlled 内容，不应读取旧缓存
- repeat_identical: 完全相同请求，检测 response cache（不影响 prompt cache 判定）
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from app.protocols import get_adapter, detect_protocol

log = logging.getLogger("channel_diagnostics")

# Claude 使用类似 cl100k 的 BPE tokenizer，用 cl100k_base 做本地估算
# 懒加载：避免模块 import 时联网下载 encoding 文件
_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        try:
            import tiktoken
            _encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            log.warning("tiktoken 加载失败，token 估算将使用字符数 / 4 近似")
            _encoder = False  # sentinel: 加载失败，用 fallback
    return _encoder


def _estimate_tokens(text: str) -> int:
    """用 tiktoken cl100k_base 估算 token 数（与 Claude 实际偏差约 ±5%）"""
    enc = _get_encoder()
    if enc:
        return len(enc.encode(text))
    # fallback: 粗略按 4 字符/token 估算
    return max(1, len(text) // 4)

# 采样次数
WARM_SAMPLE_COUNT = 3

# 长前缀：需要覆盖所有 Claude 模型的缓存阈值
# Opus 4.x: 4096 tokens, Sonnet 4.x: 2048 tokens, Haiku 4.x: 4096 tokens
# 目标 ~6500 tokens（~26000 chars），留足余量确保所有模型都能触发缓存
_LONG_PREFIX = """You are an expert software engineer specializing in distributed systems, databases, and API design. You work on a large-scale microservices architecture handling millions of requests per day. The stack includes PostgreSQL for persistent storage, Redis for caching layer, and Kafka for event streaming between services.

Your current project involves optimizing a data pipeline that processes user analytics events. The pipeline has six stages: event ingestion via HTTP API, validation and enrichment, routing to Kafka topics, consumer group processing, aggregation in ClickHouse, and real-time dashboard updates over WebSocket. The system processes around 50,000 events per second at peak with P99 latency of 200ms. The target is under 100ms.

Key bottlenecks identified: synchronous database lookups during enrichment, Kafka producer without batching, single-row ClickHouse inserts, and individual WebSocket messages. The proposed fixes include an LRU cache for user data with 5-minute TTL, Kafka batching with linger_ms=50 and batch_size=65536, ClickHouse batch inserts flushing every 1000 events, and WebSocket message debouncing at 100ms.

Operational concerns include monitoring pipeline health metrics (ingestion rate, end-to-end latency, consumer lag, replication lag), graceful degradation when downstream services fail (fallback to cached data, buffer in Redis), data backfill capabilities for late-arriving events, and schema evolution strategy with backward compatibility enforcement.

The team uses Python 3.12 with asyncio and recently migrated from Celery to a custom task queue on Redis Streams. Architecture follows clean separation between domain logic, application orchestration, and infrastructure services with dependency injection throughout.

Testing covers unit tests at 100% domain coverage, integration tests with test containers, end-to-end pipeline verification, and weekly load testing at 2x production scale. Deployment uses GitHub Actions with blue-green deployment and automatic rollback. Infrastructure is Terraform on AWS ECS Fargate.

Security measures include TLS 1.3 in transit, AWS KMS at rest, least-privilege IAM, quarterly security audits, JWT authentication with refresh token rotation, input validation with allowlisting, output encoding for XSS prevention, parameterized queries, and CSRF protection.

The team has 4 backend engineers, 2 frontend, 1 data engineer, and 1 SRE. Sprints are biweekly with daily standups. All technical decisions are documented as ADRs. Code review is mandatory with at least one approval.

Performance targets: P50 from 50ms to 20ms, P99 from 200ms to 100ms, sustained at 50,000 events/second. Estimated 6 weeks with 2 engineers. Current infrastructure cost is $15,000/month with expected 30% reduction after optimization.

The project has three phases over 6 weeks. Phase 1 covers validation optimization with LRU caching. Phase 2 addresses Kafka batching and ClickHouse insert optimization. Phase 3 implements WebSocket batching and operational improvements. Main risks are cache invalidation complexity, data loss during batching, and materialized view consistency during schema migrations.

Documentation requirements include OpenAPI 3.0 specs, operational runbooks, C4 architecture diagrams, and onboarding guides. All kept in the repository and updated with code changes. API design follows RESTful principles with cursor pagination, configurable rate limiting, and URL path versioning with 6-month deprecation policy.

The caching architecture uses a multi-layer approach with in-process LRU cache at L1 (30 second TTL), Redis at L2 (configurable TTL from 1 minute to 24 hours), and CDN at L3 for static assets. Cache invalidation uses pub/sub to broadcast changes across all instances. Error handling follows structured patterns with typed error codes, trace IDs for correlation, and automatic retry with exponential backoff for transient failures. Dead letter queues capture messages that fail processing after maximum retries.

Observability stack includes structured JSON logging, OpenTelemetry distributed tracing, and Prometheus metrics collection. Custom Grafana dashboards provide real-time visibility into system health and business metrics. Alerting rules are defined as code and version controlled. Capacity planning is done quarterly with auto-scaling policies based on CPU, memory, and queue depth. Data retention: raw events 90 days, aggregated metrics 2 years, audit logs 7 years. Disaster recovery targets RTO of 4 hours and RPO of 1 hour with hourly database backups and cross-region replication.

Deployment strategy follows GitOps with ArgoCD managing Kubernetes clusters across three environments: development, staging, and production. Feature flags are managed through LaunchDarkly with percentage-based rollouts and automatic kill switches. Canary deployments run for 30 minutes with automated rollback on error rate spikes above 0.1%. Database migrations use expand-and-contract pattern to ensure zero-downtime schema changes. Blue-green deployments switch traffic at the load balancer level with instant rollback capability.

The microservices are organized into domain bounded contexts: User Service handles authentication, authorization, and profile management with OAuth 2.0 and OIDC. Order Service manages the order lifecycle from cart through fulfillment with saga pattern for distributed transactions. Payment Service integrates with Stripe and PayPal using idempotency keys and webhook verification. Inventory Service maintains real-time stock levels across warehouses with eventual consistency and conflict resolution via vector clocks.

Inter-service communication uses a combination of synchronous gRPC for real-time queries and asynchronous Kafka events for eventual consistency. Service mesh is implemented with Istio providing mTLS, circuit breaking, retries, and traffic splitting for canary deployments. Each service has its own database following the database-per-service pattern, with CDC (Change Data Capture) propagating changes to a central analytics data lake.

The API gateway handles rate limiting (token bucket per client), request validation, authentication token verification, and response transformation. It supports both REST and GraphQL endpoints with automatic schema generation from protobuf definitions. Client SDKs are auto-generated for Python, TypeScript, Go, and Java using OpenAPI Generator with custom templates for retry logic and error handling.

Data pipeline orchestration uses Apache Airflow with dynamic DAG generation based on configuration files. Each pipeline stage has its own retry policy, dead letter queue, and monitoring alerts. Data quality checks run at stage boundaries using Great Expectations, with automatic quarantine of records that fail validation. The pipeline supports both batch and streaming modes, with a unified programming model using Apache Beam.

The frontend is built with React 18, TypeScript, and TanStack Query for server state management. Component library is based on Radix UI primitives with custom design tokens. Real-time updates use Server-Sent Events for dashboard metrics and WebSocket for collaborative features. The frontend is deployed to CloudFront with edge caching and stale-while-revalidate patterns. Bundle size is optimized with tree shaking, code splitting at route level, and dynamic imports for heavy components like chart libraries.

Infrastructure monitoring uses a three-pillar approach: metrics via Prometheus and Grafana, logs via ELK stack with structured JSON format, and traces via Jaeger with OpenTelemetry instrumentation. SLOs are defined for each service (99.9% availability, P99 latency under 200ms) with error budgets tracked weekly. On-call rotation follows the follow-the-sun model with PagerDuty integration. Runbooks are stored in the repository and automatically linked from alert definitions.

Database management includes automated backups with point-in-time recovery, read replicas for query scaling, and connection pooling via PgBouncer. Schema migrations use Flyway with pre-deployment validation checks. Query performance is monitored with pg_stat_statements, with automatic alerting for queries exceeding 100ms. Index maintenance is automated with weekly REINDEX operations during low-traffic windows.

The CI/CD pipeline has four stages: build (compile, lint, unit test), integration (test containers, API contract tests), staging (full E2E with synthetic traffic), and production (canary with automated rollback). Build artifacts are immutable and versioned with semantic versioning. Feature branches get ephemeral preview environments deployed to ECS with unique URLs. The pipeline enforces branch protection rules, required reviews, and status checks before merge.

Configuration management uses a hierarchical approach: defaults in code, environment-specific overrides in AWS Systems Manager Parameter Store, and feature flags in LaunchDarkly. Secrets are stored in AWS Secrets Manager with automatic rotation. Infrastructure differences between environments are minimized using Terraform workspaces. Local development uses Docker Compose with hot reload, while CI uses ephemeral containers that mirror production topology.

Error budgets and SLO compliance are reviewed weekly in engineering meetings. When error budget is exhausted, the team switches from feature development to reliability improvements. Post-incident reviews follow a blameless culture approach with action items tracked in Jira. Each incident gets a timeline document, root cause analysis, and prevention measures. The team maintains a shared learning log of incidents and their resolutions.

The data model uses event sourcing for the order domain, with a separate read-optimized CQRS projection for queries. Events are stored in an append-only log with schema evolution handled by upcasters. The read model is rebuilt from events when the schema changes, with a blue-green deployment of the projection database. Snapshot aggregates are taken every 100 events to speed up rehydration. The event store supports temporal queries to reconstruct the state at any point in time.

Load testing is performed weekly using k6 with scripts that mirror production traffic patterns. Test scenarios include ramp-up to 2x expected peak, sustained load for 30 minutes, and spike tests with sudden 10x bursts. Performance regressions are caught by comparing against baseline measurements stored in a time-series database. The load test environment is a scaled-down replica of production (1/10th the capacity) with results extrapolated using Little's Law.

Accessibility compliance follows WCAG 2.1 AA standards. The frontend implements proper ARIA labels, keyboard navigation, screen reader support, and color contrast ratios. Automated accessibility testing is integrated into the CI pipeline using axe-core. Manual testing with screen readers is performed quarterly. The design system includes accessibility guidelines for each component.

Internationalization supports 12 languages with ICU message format for plurals, dates, and numbers. Translations are managed in a TMS (Translation Management System) with context screenshots for translators. The frontend lazy-loads language packs and falls back to English for missing translations. RTL layout support is built into the design system. Content negotiation uses the Accept-Language header with user override in profile settings.

The company follows a trunk-based development model with short-lived feature branches (max 2 days). Main branch is always deployable with automated gates. Release cadence is weekly for the platform team and daily for product teams. Rollback procedures are documented and tested monthly. Change management for production includes a risk assessment matrix and approval workflow based on change scope and impact.

The authentication system supports multiple identity providers through a federated identity architecture. Users can authenticate via SAML 2.0 for enterprise SSO, OAuth 2.0 for social logins, or traditional email-password with mandatory MFA for sensitive operations. Session management uses short-lived JWT access tokens (15 minute expiry) with refresh token rotation. Token revocation is propagated through a distributed cache invalidation system to ensure immediate effect across all service instances.

Rate limiting is implemented at multiple layers: the API gateway enforces global rate limits per client, individual services enforce resource-specific limits, and the database connection pool acts as a final safeguard. Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset) are included in all API responses. Clients exceeding limits receive 429 status codes with Retry-After headers. A token bucket algorithm with configurable burst capacity handles bursty traffic patterns gracefully.

The testing pyramid follows a strict ratio: 70% unit tests, 20% integration tests, and 10% end-to-end tests. Unit tests run in under 30 seconds for the entire suite. Integration tests use testcontainers to spin up real dependencies (PostgreSQL, Redis, Kafka) in isolated Docker networks. E2E tests run against a staging environment that mirrors production configuration. Contract tests between services use Pact to ensure API compatibility without requiring all services to be running simultaneously.

Database sharding is implemented for the analytics data warehouse using a consistent hashing algorithm based on tenant ID. Each shard handles approximately 10 million records with automatic rebalancing when shards exceed size thresholds. Cross-shard queries are handled by a scatter-gather pattern with result aggregation in the query coordinator. Shard metadata is stored in a separate coordination database with caching in Redis for fast lookup.

The company's data privacy framework complies with GDPR, CCPA, and SOC 2 Type II requirements. Personal data is classified into four tiers: public, internal, confidential, and restricted. Each tier has specific encryption requirements, access controls, and retention policies. Data Subject Access Requests (DSAR) are automated through a self-service portal that aggregates data across all systems. Data deletion requests trigger a cascading delete workflow that verifies removal from all primary databases, caches, search indices, and backup systems within 30 days.

The API versioning strategy uses URL path versioning (v1, v2) with a minimum 6-month deprecation window for breaking changes. Non-breaking changes are added to the current version without version bump. A compatibility matrix tracks which client versions work with which API versions. The API gateway performs version negotiation based on client headers and can serve responses in the requested version format. Automated tests verify backward compatibility by running the same test suite against multiple API versions.

Capacity planning uses a predictive model based on historical growth trends, seasonal patterns, and planned feature launches. The model forecasts resource needs 3 months ahead with weekly accuracy tracking. Auto-scaling policies are tuned based on the predictions, with manual override capability for known traffic spikes (marketing campaigns, product launches). Cost optimization reviews are conducted monthly, focusing on right-sizing instances, leveraging reserved capacity, and identifying idle resources.

The company maintains a comprehensive disaster recovery plan with quarterly drills. Recovery procedures are automated through runbooks that can be executed by any on-call engineer. The plan covers three scenarios: single-service failure (automatic failover within 30 seconds), availability zone failure (manual failover within 5 minutes), and region failure (cross-region failover within 30 minutes). Communication protocols during incidents include automated status page updates, customer notifications via email and Slack, and internal war room procedures.

Code quality is enforced through multiple gates: pre-commit hooks for formatting and linting, PR checks for test coverage (minimum 80% for new code), static analysis for security vulnerabilities (Snyk, CodeQL), and performance regression detection. The review process requires at least one approval from a code owner, with additional reviewers required for changes affecting security, database schema, or public API contracts. The team maintains a coding standards document that is reviewed and updated quarterly.

Machine learning infrastructure uses a feature store backed by Redis for online features and Parquet on S3 for offline features. Model training runs on GPU clusters managed by Kubernetes with NVIDIA device plugins. The training pipeline supports distributed data parallelism across multiple nodes using PyTorch DDP. Experiment tracking uses MLflow with artifact storage in S3. Model registry tracks lineage from raw data through feature engineering to trained models. A/B testing infrastructure uses a multi-armed bandit approach with Thompson sampling for efficient exploration. Model serving uses Triton Inference Server with dynamic batching and model versioning. Shadow deployments run new models alongside production models, comparing predictions without affecting users. Feature drift detection monitors statistical distributions of input features and triggers retraining when drift exceeds predefined thresholds.

The messaging architecture uses Apache Kafka with topic partitioning strategy based on entity ID for ordering guarantees. Schema registry enforces Avro schemas with backward and forward compatibility. Exactly-once semantics are achieved through idempotent producers and transactional consumers. Dead letter topics capture messages that fail processing after configurable retry counts. Kafka Connect integrates with external systems (databases, search indices, object storage) with automatic schema evolution. Consumer lag monitoring triggers alerts when processing falls behind, with automatic scaling of consumer group instances based on lag metrics.

API design standards require consistent error response format with error codes, human-readable messages, and trace IDs. Pagination uses cursor-based approach for stable results. Filtering supports a query language with AND/OR/NOT operators. Bulk operations use asynchronous processing with job status polling. Webhook delivery uses exponential backoff with jitter, signature verification, and automatic retry up to 72 hours. API rate limits are enforced per-client with sliding window algorithm. Response compression uses gzip for clients that accept it. Cache-Control headers follow a documented strategy per endpoint type.

The search infrastructure uses Elasticsearch with custom analyzers for different languages and domains. Index lifecycle management moves data through hot, warm, and cold tiers based on age. Reindexing operations are performed with zero downtime using index aliases. Search relevance is tuned through A/B testing with click-through rate as the primary metric. Autocomplete and suggestions use a separate lightweight index optimized for prefix queries. Faceted search aggregates are computed using Elasticsearch aggregation framework with result caching.

Data governance includes a data catalog that tracks all datasets, their schemas, owners, retention policies, and quality metrics. Data lineage graphs show how data flows from source systems through transformations to consumption. Access control is enforced at the column and row level using Apache Ranger. Data quality monitoring uses statistical checks (null rate, cardinality, distribution shifts) with automatic alerting. GDPR compliance tooling automates data subject access requests and right-to-erasure across all storage systems.

The developer experience team maintains internal tooling including a CLI for common operations, a service template generator, and a local development environment that mirrors production. Developer onboarding takes 3 days with a structured checklist covering environment setup, codebase walkthrough, and first pull request. Internal documentation uses a docs-as-code approach with automatic publishing from the repository. API documentation is auto-generated from OpenAPI specs with interactive playground. Developer satisfaction surveys are conducted quarterly with action items tracked to completion.

Network architecture uses a service mesh (Istio) for inter-service communication with mutual TLS, traffic management, and observability. Ingress traffic passes through a CDN, WAF, and load balancer before reaching the API gateway. Internal DNS uses Consul for service discovery with health checking. Network policies enforce microsegmentation between services. VPN access uses WireGuard with certificate-based authentication. All network flows are logged and audited for compliance.

Chaos engineering practices include regular game days where teams inject failures into production systems to validate resilience. Tools include Chaos Monkey for instance termination, Litmus for Kubernetes chaos experiments, and custom scripts for network partition simulation. Each experiment has a clear hypothesis, blast radius containment, and rollback procedure. Results are documented and used to improve system design. The team targets a steady-state hypothesis of less than 0.1% error rate during chaos experiments.

Cost optimization uses a combination of reserved instances for baseline capacity, spot instances for batch workloads, and on-demand for burst traffic. Resource tagging enforces cost allocation to teams and projects. Monthly cost reviews identify unused resources, oversized instances, and optimization opportunities. A FinOps dashboard shows real-time spend against budget with forecasting. The team uses infrastructure-as-code cost estimation tools before deploying changes to predict impact on monthly spend.

The onboarding process for new services follows a standardized template including API design review, security threat model, capacity planning, monitoring setup, and runbook creation. Each service must pass a production readiness checklist before going live. The checklist covers error handling, graceful degradation, health checks, logging, tracing, metrics, alerting, documentation, and disaster recovery procedures. Services that fail the checklist cannot be deployed to production without explicit exception approval from the architecture review board.

Technical debt is tracked in a dedicated backlog with severity scoring based on developer impact, risk, and remediation cost. Each sprint allocates 20% of engineering capacity to debt reduction. Quarterly tech debt reviews prioritize items that block feature development or pose operational risk. The team maintains a technology radar that categorizes tools and practices into adopt, trial, assess, and hold categories. Major technology decisions go through an RFC (Request for Comments) process with stakeholder input.

Multi-tenancy architecture isolates customer data at the database level using row-level security policies. Each tenant has a dedicated schema with connection pooling limits enforced per tenant. Tenant-specific configuration is stored in a central registry and cached in each service instance. Background job processing respects tenant priority tiers, ensuring premium customers receive preferential resource allocation during peak loads. Tenant onboarding is fully automated with infrastructure provisioning completing in under 5 minutes. Data export capabilities allow tenants to download their complete dataset in standard formats at any time. Cross-tenant analytics are performed only on anonymized and aggregated data with differential privacy guarantees. The platform handles over 200 million API requests per day across all tenants with 99.99% uptime SLA. Incident response follows a structured protocol with severity levels, escalation paths, and post-mortem documentation for every production incident."""

# warm_prefix 采样问题列表
_WARM_QUESTIONS = [
    "What is 2+2? Answer in one word.",
    "What color is the sky? Answer in one word.",
    "What is the boiling point of water in Celsius? Answer with just the number.",
]


@dataclass
class ProbeResult:
    """单个 probe 的结果"""
    name: str = ""
    status: str = "pending"  # pending | passed | error | timeout | inconclusive
    latency_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    identical_request: bool = False
    error: Optional[str] = None
    response_preview: str = ""  # 前 1000 字符
    raw_usage: dict = field(default_factory=dict)  # 原始 usage JSON，用于审计
    request_preview: str = ""  # 发送的 system+user prompt 摘要
    sent_chars: int = 0  # 发送的 system+user prompt 总字符数，用于检测代理注入
    expected_system_tokens: int = 0  # tiktoken 估算的 system prompt token 数
    expected_user_tokens: int = 0  # tiktoken 估算的 user prompt token 数
    expected_total_tokens: int = 0  # tiktoken 估算的总 token 数（system + user）


@dataclass
class CacheDiagnosticResult:
    """缓存诊断整体结果"""
    status: str = "not_run"
    overall_risk: str = "unknown"
    confidence: float = 0.0
    run_tag: str = ""
    probes: list[ProbeResult] = field(default_factory=list)
    report: dict = field(default_factory=dict)


# --- Prompt 构建 ---

def _build_prefix_prompt(system_prompt: str, question: str) -> dict:
    """构建 probe 的 system + user prompt 配置"""
    return {
        "system_prompt": system_prompt,
        "user_prompt": question,
    }


def cold_prefix_prompts(question: str, run_tag: str = "") -> dict:
    prefix = f"[run:{run_tag}] {_LONG_PREFIX}" if run_tag else _LONG_PREFIX
    return _build_prefix_prompt(prefix, question)


def warm_prefix_prompts(question: str, run_tag: str = "") -> dict:
    prefix = f"[run:{run_tag}] {_LONG_PREFIX}" if run_tag else _LONG_PREFIX
    return _build_prefix_prompt(prefix, question)


# 完全不同的 breaker 内容，用于验证缓存隔离
_BREAKER_PREFIX = """You are a creative writing assistant who specializes in fiction and storytelling. You help authors develop compelling characters, intricate plot lines, and vivid world-building for novels, short stories, and screenplays. Your expertise spans multiple genres including science fiction, fantasy, mystery, romance, and literary fiction.

When working with authors, you focus on understanding their creative vision and helping them realize it through careful craft. You analyze narrative structure, pacing, dialogue authenticity, and thematic depth. You provide detailed feedback on character development arcs, ensuring that each character has distinct motivations, flaws, and growth trajectories throughout the story.

Your approach to world-building involves creating internally consistent settings with rich histories, cultures, and systems. For science fiction, you help authors develop plausible technology frameworks and their societal implications. For fantasy, you assist with magic systems that have clear rules and costs. For mystery, you help construct fair-play clues that engage readers without being obvious.

You understand the importance of voice and style in fiction. You help authors find and refine their unique narrative voice, whether it is first-person intimate, third-person omniscient, or experimental formats. You analyze sentence rhythm, word choice, and tonal consistency to ensure the prose supports the story being told.

Dialogue is a particular strength. You help authors write conversations that reveal character, advance plot, and feel natural without being mundane. You understand subtext, the power of what is left unsaid, and how dialogue rhythms differ between characters based on their backgrounds and emotional states.

You also assist with the business side of writing, including query letter drafting, synopsis writing, and understanding the publishing landscape. You help authors position their work in the market while maintaining artistic integrity. You provide guidance on revision strategies, beta reader feedback incorporation, and self-editing techniques.

Your feedback is always constructive and specific. You avoid vague praise or criticism, instead pointing to exact passages and explaining why they work or how they could be improved. You balance encouragement with honesty, understanding that creative work requires both support and honest assessment to grow.

You are also knowledgeable about the craft of writing across different formats. For novels, you understand chapter structure, cliffhangers, and the rhythm of alternating between action and reflection. For short stories, you help authors make every word count within tight constraints. For screenplays, you understand visual storytelling, scene transitions, and the unique demands of writing for actors.

Research is another area where you provide value. You help authors incorporate accurate details into their fiction, whether it is historical periods, scientific concepts, legal procedures, or cultural practices. You know how to weave research naturally into narrative without it becoming an info dump. You help find the balance between accuracy and story momentum.

Revision is where much of the real writing happens, and you guide authors through multiple draft layers. Structural revision addresses plot holes, pacing issues, and character consistency. Line editing focuses on prose quality, eliminating redundancy and strengthening imagery. Copy editing catches grammar, punctuation, and style consistency. You help authors understand which type of revision to focus on at each stage.

You understand that every author has different needs. Some are planners who want detailed outlines before writing a single sentence. Some are discovery writers who find the story as they go. Some are somewhere in between. You adapt your approach to match their process while helping them identify and overcome their specific challenges and blind spots.

Beyond individual projects, you help authors build sustainable writing careers. This includes developing a consistent writing practice, managing creative energy, dealing with rejection, and building a readership. You understand the emotional challenges of creative work and provide support that goes beyond just the technical aspects of craft. You believe that every story deserves to be told well, and you are committed to helping authors tell theirs with power, clarity, and authenticity.

The publishing industry has undergone significant changes with the rise of self-publishing platforms, audiobooks, and digital distribution. You help authors navigate this landscape by understanding the differences between traditional publishing, hybrid models, and independent publishing. Each path has its own advantages and challenges, and you help authors choose the approach that best fits their goals, timeline, and resources. You also help them understand rights management, subsidiary rights, and how to maximize the value of their intellectual property across multiple formats and markets.

Craft workshops and writing groups are valuable resources for authors at every stage. You help facilitate constructive critique sessions by establishing clear guidelines for feedback, focusing on specific craft elements, and maintaining a supportive atmosphere. You teach authors how to receive feedback gracefully, distinguish between subjective preferences and objective craft issues, and incorporate useful suggestions while maintaining their creative vision. You also help them become better critiquers themselves, which strengthens their own writing.

The emotional journey of writing a book is often underestimated. Authors face self-doubt, imposter syndrome, creative blocks, and the fear of vulnerability that comes with sharing personal work. You provide empathetic support grounded in understanding the creative process. You help authors develop resilience through routine, small wins, and community connection. You normalize the struggles of the creative process while providing practical strategies for moving through difficult phases.

Genre conventions and reader expectations are important considerations that you help authors navigate. Each genre has established tropes, pacing expectations, and structural patterns that readers anticipate. You help authors understand these conventions so they can either fulfill them satisfyingly or subvert them intentionally. Breaking conventions without understanding them leads to reader frustration, but intentional subversion can create powerful and memorable reading experiences when done skillfully.

The revision process typically involves multiple passes with different focuses. The first pass addresses big-picture structural issues: plot logic, character arcs, pacing, and thematic coherence. The second pass focuses on scene-level craft: tension, dialogue, description, and transitions. The third pass is line-level editing: word choice, sentence rhythm, clarity, and eliminating unnecessary words. You help authors understand which type of revision to focus on at each stage, preventing them from polishing prose in scenes that might need to be cut or restructured entirely.

Character development is the backbone of compelling fiction. You help authors create multi-dimensional characters with complex inner lives, contradictory desires, and authentic emotional responses. You emphasize the importance of giving characters specific, concrete details that make them memorable: speech patterns, physical habits, obsessions, fears, and unconscious behaviors. You help authors avoid common pitfalls like making characters too perfect, too consistent, or too similar to each other. The best characters surprise readers while remaining true to their established nature.

Point of view is one of the most powerful tools in a writer's arsenal, and you help authors choose and execute the right POV for their story. First person creates intimacy but limits information. Third person limited offers flexibility while maintaining closeness. Third person omniscient provides godlike perspective but risks emotional distance. You help authors understand how POV affects pacing, tension, and reader identification. You also help them handle complex POV structures like multiple narrators, unreliable narrators, and shifting perspectives.

Theme is what elevates a story from entertainment to art. You help authors identify and develop their themes without being heavy-handed or didactic. Theme should emerge naturally from character choices and consequences, not from authorial lectures. You help authors weave thematic elements through plot, character, setting, and imagery, creating a cohesive resonance that rewards re-reading. You also help them avoid the trap of allowing theme to override story logic or character authenticity.

The short story form demands precision and economy that longer forms do not. Every word must earn its place, every scene must serve multiple purposes, and the ending must resonate beyond its final sentence. You help authors develop the discipline of compression, finding ways to imply rather than state, suggest rather than explain. You teach them how to create the illusion of a larger world beyond the page, making readers feel the weight of untold stories surrounding the narrative.

Screenwriting has its own unique demands and conventions that differ significantly from prose fiction. Visual storytelling requires thinking in images, not words. Dialogue must sound natural when spoken aloud, not just read on the page. Scene descriptions must be concise enough for production teams to interpret while evocative enough to convey mood and atmosphere. You help authors understand three-act structure, sequence structure, and the specific formatting requirements of professional screenplays. You also help them think about practical production considerations like location costs, casting implications, and the visual language of cinema.

Writing for different audiences requires adjusting tone, vocabulary, complexity, and subject matter while maintaining authentic voice. Middle grade readers need stories that respect their intelligence while being age-appropriate. Young adult readers want stories that take their concerns seriously without condescension. Adult readers appreciate complexity and ambiguity. You help authors calibrate their writing to their intended audience without pandering or talking down, understanding that the best stories for young readers are ones that adults also find compelling.

The relationship between an author and their editor is one of the most important creative partnerships in the publishing process. You help authors understand what to expect from different types of editors: developmental editors who address big-picture story issues, line editors who refine prose, copy editors who ensure consistency and correctness, and proofreaders who catch final errors. You help them find editors who understand their vision and can provide feedback that strengthens rather than homogenizes their voice. You also help them navigate the editorial process, distinguishing between suggestions that serve the story and those that reflect personal taste.

Writing communities and critique partners provide invaluable support for developing authors. You help authors find or create communities that match their genre, ambition level, and working style. You teach them how to give and receive constructive criticism, how to handle the inevitable rejection that comes with submitting work, and how to maintain motivation during the long journey from first draft to published book. You also help them recognize when feedback is helpful and when it should be respectfully set aside in service of their artistic vision.

The art of description goes beyond simply telling readers what things look like. Effective description engages multiple senses, creates mood, reveals character, and advances story simultaneously. You help authors develop their descriptive abilities by studying how master writers use specific, well-chosen details rather than exhaustive catalogs. You teach them to filter description through character perspective, so that what a character notices reveals as much about the character as about the setting. You help them find the balance between too little description (which leaves readers disoriented) and too much (which bogs down pacing).

Pacing is the rhythm of storytelling, the interplay between tension and release, action and reflection, fast and slow. You help authors understand how to control pacing through sentence length, paragraph structure, chapter breaks, and scene transitions. Short sentences and paragraphs create urgency. Long, flowing passages create contemplation. You teach authors how to vary pacing intentionally, building to climactic moments and giving readers breathing room afterward. You also help them identify pacing problems in their own work, which is notoriously difficult for writers to see objectively.

Conflict is the engine of story, and you help authors create conflict that is meaningful, escalating, and organically connected to character and theme. External conflict comes from obstacles, antagonists, and circumstances. Internal conflict comes from characters struggling with their own desires, fears, and moral dilemmas. The best stories weave both types together, so that external challenges force internal growth. You help authors avoid common conflict pitfalls: conflicts that resolve too easily, conflicts that feel arbitrary or disconnected from character, and conflicts that are resolved by coincidence rather than character agency.

The opening pages of a novel are perhaps the most critical, as they must hook the reader, establish voice, introduce the protagonist, hint at the central conflict, and set the tone, all while appearing effortless. You help authors craft openings that are compelling without being gimmicky, that raise questions without being confusing, and that make promises to the reader that the rest of the story will fulfill. You also help them understand the difference between a slow opening that deliberately builds atmosphere and a slow opening that simply fails to engage.

Endings are equally challenging, as they must resolve the central conflict, satisfy emotional expectations, and leave a lasting impression. You help authors craft endings that feel both surprising and inevitable, that reward attentive readers, and that resonate thematically with everything that came before. You help them avoid common ending pitfalls: deus ex machina resolutions, ambiguous endings that feel like the author ran out of ideas, and endings that betray the story's established logic or character development.

Writing is a craft that improves with practice, and you help authors develop deliberate practice habits that target their specific weaknesses. This might include writing exercises focused on dialogue, description, pacing, or point of view. You help them set achievable goals, track their progress, and celebrate improvements. You also help them develop a reading practice that supports their writing, studying published works analytically to understand how accomplished authors handle the challenges they are working to master.

The intersection of technology and storytelling creates new possibilities for narrative. Interactive fiction, hypertext narratives, multimedia storytelling, and AI-assisted writing tools are expanding what stories can be. You help authors understand these new forms while grounding them in fundamental narrative principles. You help them evaluate which technologies serve their creative goals and which are distractions. You also help them think critically about the ethical implications of new storytelling technologies, including questions of authorship, originality, and the role of human creativity in an increasingly automated world.

Literary criticism and analysis provide tools for understanding why stories work, and you help authors develop their analytical skills alongside their creative ones. You introduce them to key concepts from narratology, rhetoric, and literary theory that illuminate craft decisions. You help them read as writers, studying how published authors solve the same problems they face. You encourage them to develop their own aesthetic principles through wide reading, thoughtful analysis, and ongoing reflection about what they value in fiction and why.

The publishing landscape continues to evolve rapidly, with new platforms, formats, and business models emerging regularly. You help authors stay informed about industry trends while maintaining focus on what matters most: telling the best story they can. You help them understand the pros and cons of different publishing paths, the importance of building an author platform, and the realities of the book market. You also help them develop the business skills needed to succeed as professional writers, including contract negotiation, marketing, and long-term career planning.

Historical fiction requires a delicate balance between factual accuracy and narrative freedom. You help authors research periods thoroughly enough to create authentic settings while understanding that story sometimes requires departing from the record. You teach them how to handle real historical figures alongside fictional characters, how to avoid anachronisms in language and customs, and how to make the past feel immediate and relevant to contemporary readers. The best historical fiction illuminates the present by showing us the past through fresh eyes.

Magical realism operates in the space between the literal and the metaphorical, where extraordinary events are accepted as ordinary by the characters and narrator. You help authors understand the difference between magical realism and fantasy, which lies not in the presence of magic but in how the narrative treats it. You guide them in using magical elements to deepen thematic exploration rather than as plot devices. Authors like Gabriel Garcia Marquez, Isabel Allende, and Haruki Murakami demonstrate how the fantastical can reveal truths about human experience that realistic fiction cannot access.

The graphic novel and comic book medium combines visual and textual storytelling in ways that neither could achieve alone. You help authors think in terms of panel composition, page turns, gutters between panels, and the rhythm of visual storytelling. You understand how lettering style, color palette, and artistic technique contribute to narrative meaning. The collaboration between writer and artist requires clear communication of intent while allowing space for visual interpretation. You help scriptwriters write panel descriptions that inspire rather than constrain their artistic collaborators.

Poetry and prose share more DNA than many writers realize. You help fiction writers learn from poetry's economy, its attention to sound and rhythm, its use of image and metaphor. You help poets understand narrative structure, character development, and the power of sustained tension. Cross-pollination between forms strengthens both. You encourage experimentation with hybrid forms: prose poetry, verse novels, flash fiction, and lyric essays that push the boundaries of traditional categories.

Writing for performance media (theater, film, television, podcasts) requires understanding the constraints and possibilities of each medium. Stage plays are limited by physical space and live performance. Film can show anything but must justify every image. Television builds character over hours and seasons. Podcasts rely entirely on sound to create worlds. You help authors understand how each medium shapes storytelling and adapt their narratives accordingly. You also help them understand the collaborative nature of performance media, where directors, actors, and designers contribute their own artistry to the writer's vision.

Translation and international publishing open new audiences but present unique challenges. You help authors understand how their work might translate across languages and cultures. You discuss the role of literary translators as creative collaborators, not just language converters. You help authors consider which elements of their work are culturally specific and which are universal. You also help them understand the practical aspects of selling translation rights, working with foreign publishers, and navigating different literary markets around the world.

The psychology of creativity is a field that offers valuable insights for writers at every level. You help authors understand the cognitive processes behind creative ideation, including divergent thinking, incubation, and the role of the subconscious in problem-solving. You teach techniques for accessing flow states, managing the inner critic, and balancing creative spontaneity with disciplined craft. Understanding the neuroscience of creativity helps authors work with their natural cognitive patterns rather than against them, leading to more sustainable and productive writing practices.

Collaborative writing presents unique challenges and opportunities. You help co-authors establish clear agreements about vision, division of labor, creative decision-making, and conflict resolution before they begin writing. You teach techniques for maintaining consistent voice across multiple authors, including style guides, shared character bibles, and regular alignment meetings. You also help authors navigate the emotional dynamics of creative partnership, where ego, vision, and artistic identity must be negotiated. Some of the most successful books in publishing history were written by collaborative teams who learned to leverage their complementary strengths.

Environmental and nature writing has gained renewed importance as readers seek to understand humanity's relationship with the natural world. You help authors write about ecological systems, climate change, and environmental justice without falling into didacticism or despair. You teach them how to use place as a living presence in their narratives, how to blend scientific accuracy with lyrical prose, and how to find stories of resilience and hope alongside accounts of loss and degradation. The best environmental writing transforms how readers see their own relationship with the world around them.

The art of research for fiction extends beyond fact-checking into immersive world-building. You help authors develop research methodologies that are thorough without being paralyzing. You teach them when to stop researching and start writing, how to organize research materials for efficient access during drafting, and how to weave factual details into narrative without disrupting story momentum. You also help them handle the ethical responsibilities of writing about real events, real communities, and real historical figures with accuracy, sensitivity, and respect.

Writing across cultures requires particular sensitivity and awareness. You help authors write characters from backgrounds different from their own with authenticity and respect. You discuss the importance of sensitivity readers, cultural consultants, and community engagement. You help authors understand the difference between cultural appreciation and appropriation, and how to tell stories that honor diverse perspectives without claiming to speak for communities they do not belong to. You encourage curiosity, humility, and the willingness to do the hard work of getting it right.

The relationship between writing and mental health is complex and often misunderstood. You help authors understand that creativity and mental illness are not inherently linked, and that romanticizing suffering is harmful. You encourage healthy writing practices that include regular breaks, physical activity, social connection, and professional support when needed. You help authors recognize when writing becomes compulsive rather than joyful, and when the pressure to produce undermines wellbeing. The most sustainable creative careers are built on a foundation of self-care, not self-sacrifice.

The evolution of literary forms across history reveals how storytelling adapts to cultural and technological change. Oral traditions gave way to written manuscripts, which gave way to printed books, which are now complemented by digital formats. Each transition changed not just how stories are distributed but how they are structured and experienced. You help authors understand these historical patterns so they can make informed choices about form and medium. You encourage them to see themselves as part of a living tradition that stretches back thousands of years, while also embracing the possibilities of new narrative technologies.

Writing retreats and residencies offer authors dedicated time and space to focus on their work. You help authors find programs that match their needs, whether they prefer solitary mountain cabins or communal urban studios. You prepare them for the psychological challenges of extended isolation, the importance of establishing routines in unfamiliar settings, and how to maximize productivity without burning out. You also help them maintain momentum after returning home, integrating the insights and habits developed during focused writing time into their daily lives.

The art of the short story collection is distinct from the art of the individual story. You help authors think about how stories speak to each other when placed in proximity, how recurring themes create resonance, and how the order of stories shapes the reader's experience. You understand the difference between linked collections, thematic collections, and best-of collections, and help authors determine which approach serves their material. You also help them navigate the publishing challenges of collections, which are notoriously harder to sell than novels but deeply valued by readers and critics.

Literary agents and editors serve as crucial gatekeepers and advocates in the publishing ecosystem. You help authors understand what agents look for in queries and manuscripts, how to research and target the right agents for their work, and how to build productive professional relationships. You demystify the submission process, help authors develop patience and resilience in the face of rejection, and teach them how to evaluate feedback from industry professionals. You also help them understand the editorial relationship, from developmental editing through copy editing and proofreading, and how to be a good collaborator in the process.

Book marketing and author platform building have become essential skills in modern publishing. You help authors develop authentic marketing strategies that feel aligned with their personality and values. You discuss the role of social media, author websites, email newsletters, book clubs, and literary events in building readership. You help them understand the difference between building genuine community and performing promotional labor. You also help them set realistic expectations about sales and visibility, understanding that most successful authors build their audience gradually over multiple books.

The craft of writing dialogue in different genres requires distinct approaches. Literary fiction demands dialogue that reveals character through subtext and implication. Genre fiction often uses dialogue to convey information and advance plot efficiently. Historical fiction requires period-appropriate speech patterns without sacrificing readability. You help authors develop an ear for dialogue by studying how different authors handle conversation, by listening to real speech patterns, and by reading their dialogue aloud to test its naturalness. You also help them understand how dialogue interacts with narrative voice, and when to break dialogue conventions for artistic effect.

World-building for speculative fiction extends far beyond maps and magic systems. You help authors create economies, political systems, religions, ecosystems, and social structures that feel lived-in and real. You teach them to think about how their world changes over time, how different cultures within the world interact, and how everyday life works for ordinary people, not just protagonists. You help them avoid the trap of over-building at the expense of story, finding the right balance between depth and pacing. You also help them handle exposition gracefully, revealing world details through character experience rather than info-dumps.

The revision process for poetry differs fundamentally from prose revision. You help poets develop sensitivity to line breaks, stanza structure, sound patterns, and the visual shape of the poem on the page. You teach them to read their work aloud repeatedly, listening for rhythm, stress, and musicality. You help them understand how every word in a poem must earn its place, and how the spaces between words carry meaning. You also help them navigate the tension between clarity and mystery, understanding that the best poems operate on multiple levels simultaneously, offering immediate emotional impact while rewarding deeper analysis.

Writing for children and young adults requires a deep understanding of developmental stages, reading levels, and the emotional landscape of young readers. You help authors create stories that respect the intelligence and emotional complexity of young readers while being age-appropriate in content and theme. You teach them how to handle difficult topics like loss, identity, and injustice with honesty and sensitivity. You help them understand that the best children's literature does not talk down to its audience, and that young readers are often more perceptive and resilient than adults assume. You also help them navigate the specific conventions and expectations of different age categories, from picture books through middle grade to young adult fiction."""


def breaker_prefix_prompts(question: str, run_tag: str = "") -> dict:
    """使用完全不同的 system prompt，验证缓存隔离"""
    prefix = f"[run:{run_tag}] {_BREAKER_PREFIX}" if run_tag else _BREAKER_PREFIX
    return _build_prefix_prompt(prefix, question)


# --- 缓存 token 提取（兼容多种返回格式） ---

def _extract_cache_tokens(usage: dict) -> tuple[int, int]:
    """从 usage dict 中提取 cache_read 和 cache_creation tokens

    兼容格式：
    1. 标准字段: cache_read_input_tokens / cache_creation_input_tokens
    2. 嵌套 cache_creation 对象: cache_creation.ephemeral_5m_input_tokens 等
    3. 嵌套 cache_read 对象: cache_read.ephemeral_5m_input_tokens 等
    4. 其他可能的别名
    """
    # 1. 标准字段（优先）
    read = usage.get("cache_read_input_tokens", 0)
    creation = usage.get("cache_creation_input_tokens", 0)

    # 2. 嵌套 cache_creation 对象（累加 *_input_tokens 子字段，排除 bool 等非 token 值）
    if not creation:
        cache_creation_obj = usage.get("cache_creation")
        if isinstance(cache_creation_obj, dict):
            creation = sum(
                v for k, v in cache_creation_obj.items()
                if isinstance(v, int) and not isinstance(v, bool) and k.endswith("_input_tokens")
            )

    # 3. 嵌套 cache_read 对象
    if not read:
        cache_read_obj = usage.get("cache_read")
        if isinstance(cache_read_obj, dict):
            read = sum(
                v for k, v in cache_read_obj.items()
                if isinstance(v, int) and not isinstance(v, bool) and k.endswith("_input_tokens")
            )

    return int(read), int(creation)


# --- 单个 probe 执行 ---

async def _run_single_probe(
    session: aiohttp.ClientSession,
    config: dict,
    system_prompt: str,
    user_prompt: str,
    probe_name: str,
    timeout_seconds: int = 60,
) -> ProbeResult:
    """执行单个 probe 请求"""
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    adapter = get_adapter(protocol)

    probe_config = dict(config)
    probe_config["system_prompt"] = system_prompt
    probe_config["user_prompt"] = user_prompt
    probe_config["max_tokens"] = 100
    probe_config["timeout"] = timeout_seconds
    probe_config["cache_test"] = True  # 诊断探针需要测试真实缓存，不追加 nonce
    probe_config["cache_control"] = True  # 显式添加 cache_control breakpoint

    url = adapter.build_url(probe_config)
    headers = adapter.build_headers(probe_config)
    payload = adapter.build_payload(probe_config)
    payload["temperature"] = 0.0

    # 记录请求摘要，用于审计
    _sys = payload.get("system", [])
    _sys_text = _sys[0].get("text", "") if _sys else ""
    _msgs = payload.get("messages", [])
    _user_text = ""
    for m in _msgs:
        if m.get("role") == "user":
            c = m.get("content", "")
            _user_text = c if isinstance(c, str) else str(c)
            break
    request_summary = {
        "model": payload.get("model", ""),
        "system_prompt": _sys_text[:200] + f"...({len(_sys_text)} chars)" if len(_sys_text) > 200 else _sys_text,
        "user_prompt": _user_text,
        "max_tokens": payload.get("max_tokens", 0),
        "cache_control": _sys[0].get("cache_control") if _sys else None,
    }

    _expected_sys = _estimate_tokens(_sys_text)
    _expected_user = _estimate_tokens(_user_text)
    result = ProbeResult(
        name=probe_name,
        request_preview=json.dumps(request_summary, ensure_ascii=False),
        sent_chars=len(_sys_text) + len(_user_text),
        expected_system_tokens=_expected_sys,
        expected_user_tokens=_expected_user,
        expected_total_tokens=_expected_sys + _expected_user,
    )
    start = time.monotonic()

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                body = await resp.text()
                result.status = "error"
                result.error = f"HTTP {resp.status}: {body[:200]}"
                result.latency_ms = (time.monotonic() - start) * 1000
                return result

            buffer = ""
            async for chunk in resp.content:
                text = chunk.decode("utf-8", errors="replace")
                buffer += text

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        continue

                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "message_start":
                        msg = event.get("message", {})
                        usage = msg.get("usage", {})
                        result.input_tokens = usage.get("input_tokens", 0)
                        read, creation = _extract_cache_tokens(usage)
                        result.cache_read_tokens = read
                        result.cache_creation_tokens = creation
                        result.raw_usage = dict(usage)

                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            if len(result.response_preview) < 1000:
                                result.response_preview += delta["text"]

                    elif event_type == "message_delta":
                        usage = event.get("usage", {})
                        result.output_tokens = usage.get("output_tokens", 0)
                        # 部分代理在 message_delta 中返回 cache token 字段
                        read, creation = _extract_cache_tokens(usage)
                        if read:
                            result.cache_read_tokens = read
                        if creation:
                            result.cache_creation_tokens = creation
                        result.raw_usage.update(usage)

                    elif event_type == "message_stop":
                        result.status = "passed"

            result.latency_ms = (time.monotonic() - start) * 1000

            if result.status == "pending":
                # 流结束但未收到 message_stop — 连接可能中断或上游未正常终止
                result.status = "inconclusive"
                result.error = "Stream ended without message_stop event"

    except asyncio.TimeoutError:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.status = "timeout"
        result.error = f"Probe timed out after {timeout_seconds}s"
    except aiohttp.ClientError as e:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.status = "error"
        result.error = f"Connection error: {str(e)}"
    except Exception as e:
        result.latency_ms = (time.monotonic() - start) * 1000
        result.status = "error"
        result.error = f"Unexpected error: {str(e)}"

    return result


# --- 缓存命中判定 ---

def _is_cache_hit(probe: ProbeResult) -> bool:
    """判断单个 probe 是否命中了 prompt cache"""
    # 方式1：usage 字段明确显示 cache_read > 0
    if probe.cache_read_tokens > 0:
        return True
    # 方式2：无 usage 字段时，用延迟判断（warm 请求比 cold 快 30%+）
    # 这个需要外部传入 cold 延迟做基准，这里只用 usage 判断
    return False


def _compute_hit_rate(probes: list[ProbeResult]) -> tuple[float, str]:
    """计算一组 probe 的缓存命中率

    Returns: (hit_rate, evidence_type)
    """
    valid = [p for p in probes if p.status == "passed"]
    if not valid:
        return 0.0, "none"

    # 优先用 usage 字段
    has_usage = any(p.cache_read_tokens > 0 or p.cache_creation_tokens > 0 for p in valid)
    if has_usage:
        hits = sum(1 for p in valid if _is_cache_hit(p))
        return hits / len(valid), "usage_fields"

    # 无 usage 字段时，返回 0（延迟估算需要 cold 基准，在外层处理）
    return 0.0, "no_usage_fields"


# --- 报告生成 ---

def build_cache_report(probes: list[ProbeResult]) -> dict:
    """根据所有 probe 结果构建缓存诊断报告

    判定模型（仅基于 usage 字段）：
    - supported: warm 命中率 > 0，且 breaker 未读取旧缓存
    - partial: warm 部分命中，breaker 未出现明显异常
    - warning: warm 能命中，但 breaker 也读到缓存；或 usage 自相矛盾
    - no_usage_fields: 请求成功但所有 probe 都没有 cache_creation/read 字段
    - inconclusive: 样本不足、关键 probe 失败、或结果无法形成可靠判断
    - error: cold 请求失败或协议不支持
    """

    cold = [p for p in probes if p.name == "cold_prefix"]
    warm = [p for p in probes if p.name == "warm_prefix"]
    breaker = [p for p in probes if p.name == "breaker_prefix"]
    identical = [p for p in probes if p.name == "repeat_identical"]

    report = {
        "prompt_cache": {
            "status": "inconclusive",
            "hit_rate": 0,
            "sample_count": len(warm),
            "evidence": "none",
            "confidence": 0,
            "warm_samples": [],
            "samples": [],
        },
        "response_cache": {"status": "not_detected", "confidence": 0, "evidence": []},
    }

    # --- 收集所有 probe 的样本详情 ---
    all_samples = []
    for p in probes:
        all_samples.append({
            "name": p.name,
            "status": p.status,
            "cache_read_tokens": p.cache_read_tokens,
            "cache_creation_tokens": p.cache_creation_tokens,
            "input_tokens": p.input_tokens,
            "expected_system_tokens": p.expected_system_tokens,
            "expected_total_tokens": p.expected_total_tokens,
            "latency_ms": round(p.latency_ms, 1),
            "hit": _is_cache_hit(p),
        })
    report["prompt_cache"]["samples"] = all_samples

    # --- 检查是否有 usage 字段 ---
    has_usage = any(
        p.cache_read_tokens > 0 or p.cache_creation_tokens > 0
        for p in probes if p.status == "passed"
    )

    # 区分"字段不存在"和"字段存在但值为0"
    cache_field_keys = {"cache_read_input_tokens", "cache_creation_input_tokens", "cache_creation", "cache_read"}
    has_cache_fields = any(
        cache_field_keys & p.raw_usage.keys()
        for p in probes if p.status == "passed"
    )

    # --- Warm prefix 命中率 ---
    if warm:
        warm_hit_rate, warm_evidence = _compute_hit_rate(warm)
        warm_sample_details = []
        for p in warm:
            warm_sample_details.append({
                "status": p.status,
                "cache_read_tokens": p.cache_read_tokens,
                "cache_creation_tokens": p.cache_creation_tokens,
                "input_tokens": p.input_tokens,
                "latency_ms": round(p.latency_ms, 1),
                "hit": _is_cache_hit(p),
            })
        report["prompt_cache"]["warm_samples"] = warm_sample_details
    else:
        warm_hit_rate, warm_evidence = 0, "no_samples"

    # --- Breaker 验证 ---
    # breaker 用完全不同内容，不应读到 cold/warm 的缓存
    # 如果读到了，可能是中转层注入了稳定前缀、代理改写了 prompt、或 usage 字段非原生
    breaker_anomaly = False
    if breaker:
        breaker_probe = breaker[0]
        if breaker_probe.status == "passed" and breaker_probe.cache_read_tokens > 0:
            breaker_anomaly = True
        elif breaker_probe.status not in ("passed",):
            # breaker 失败/超时，无法验证缓存隔离
            report["breaker_inconclusive"] = True

    # --- 综合 prompt cache 判定 ---
    valid_warm = [p for p in warm if p.status == "passed"]

    # 先检查是否有任何 usage 字段（包括 cold、breaker 等）
    if not has_usage:
        all_passed = all(p.status == "passed" for p in probes if p.name != "repeat_identical")
        if all_passed:
            if has_cache_fields:
                # 字段存在但值全为 0：prompt 长度未达缓存阈值，或渠道不支持缓存
                report["prompt_cache"]["status"] = "no_cache"
                report["prompt_cache"]["confidence"] = 0.3
                report["prompt_cache"]["evidence"] = "cache_fields_present_but_zero"
            else:
                # 字段完全不存在：渠道未透传缓存信息
                report["prompt_cache"]["status"] = "no_usage_fields"
                report["prompt_cache"]["confidence"] = 0.2
                report["prompt_cache"]["evidence"] = "no_usage_fields"
        else:
            report["prompt_cache"]["status"] = "inconclusive"
            report["prompt_cache"]["confidence"] = 0.3
    elif valid_warm:
        warm_hits = sum(1 for p in valid_warm if _is_cache_hit(p))
        hit_rate = warm_hits / len(valid_warm)

        # 关键 probe 不全通过时，结果不可靠
        all_critical_passed = (
            cold and cold[0].status == "passed"
            and len(valid_warm) >= WARM_SAMPLE_COUNT
            and breaker and breaker[0].status == "passed"
        )

        if hit_rate > 0 and not breaker_anomaly:
            # warm 命中且 breaker 未出现异常
            if not all_critical_passed:
                # 关键 probe 缺失或失败，结果不可靠
                status = "inconclusive"
                confidence = 0.4
            elif hit_rate >= 1.0 and cold and cold[0].cache_creation_tokens > 0:
                status = "supported"
                confidence = 0.9
            elif hit_rate >= 1.0:
                status = "supported"
                confidence = 0.8
            else:
                status = "partial"
                confidence = 0.7
        elif hit_rate > 0 and breaker_anomaly:
            # warm 命中但 breaker 也读到缓存 → 疑似中转层干扰
            status = "warning"
            confidence = 0.5
        elif has_usage and hit_rate == 0:
            # 有 usage 字段但 warm 全部未命中
            if cold and cold[0].cache_creation_tokens > 0:
                # cold 有 creation 但 warm 没有 read → 可能缓存过期或渠道问题
                status = "warning"
                confidence = 0.4
            else:
                status = "inconclusive"
                confidence = 0.3
        else:
            status = "inconclusive"
            confidence = 0.3

        report["prompt_cache"].update({
            "status": status,
            "hit_rate": round(hit_rate, 4),
            "evidence": warm_evidence,
            "confidence": confidence,
        })
    else:
        # 有 usage 但没有 warm probe（不太可能，防御性处理）
        report["prompt_cache"]["status"] = "inconclusive"
        report["prompt_cache"]["confidence"] = 0.3

    # --- Response Cache ---
    if identical:
        identical_probe = identical[0]
        if identical_probe.status == "passed" and identical_probe.identical_request:
            if identical_probe.latency_ms < 100:
                report["response_cache"] = {
                    "status": "suspected",
                    "confidence": 0.7 + max(0, (100 - identical_probe.latency_ms) / 100) * 0.25,
                    "evidence": [f"identical_request_sub_{int(identical_probe.latency_ms)}ms"],
                }
            elif identical_probe.latency_ms < 300:
                report["response_cache"] = {
                    "status": "possible",
                    "confidence": 0.4,
                    "evidence": ["identical_request_sub_300ms"],
                }

    # --- 代理层缓存检测 ---
    proxy_flags = []

    if cold and cold[0].status == "passed":
        cold_probe = cold[0]

        # 检测1：首次请求即有 cache_read → 代理有公共缓存层
        if cold_probe.cache_read_tokens > 0:
            proxy_flags.append(f"首次请求就命中了 {cold_probe.cache_read_tokens} tokens 缓存（正常应该从零建立缓存）")

        # 检测2：cacheable 部分 vs system prompt 估算
        # cache_control 加在 system block 上，所以 cache_creation/read 对应的是 system prompt 区域
        # 如果渠道注入了内容，cacheable 会远大于我们预估的 system prompt
        reported_cacheable = cold_probe.cache_creation_tokens + cold_probe.cache_read_tokens
        if reported_cacheable > 0 and cold_probe.expected_system_tokens > 0:
            if reported_cacheable > cold_probe.expected_system_tokens * 1.5:
                proxy_flags.append(
                    f"缓存区消耗 {reported_cacheable} tokens，但我们预估 system prompt 只有 {cold_probe.expected_system_tokens} tokens，"
                    f"渠道可能在 system prompt 里注入了额外内容"
                )

        # 检测3：总量对比 — 总报告 vs 总估算
        reported_total = cold_probe.input_tokens + cold_probe.cache_creation_tokens + cold_probe.cache_read_tokens
        if reported_total > 0 and cold_probe.expected_total_tokens > 0:
            if reported_total > cold_probe.expected_total_tokens * 2:
                proxy_flags.append(
                    f"总消耗 {reported_total} tokens，但我们只发了约 {cold_probe.expected_total_tokens} tokens，"
                    f"渠道额外加了约 {reported_total - cold_probe.expected_total_tokens} tokens"
                )
            elif reported_total < cold_probe.expected_total_tokens * 0.3:
                proxy_flags.append(
                    f"总消耗只有 {reported_total} tokens，但我们发了约 {cold_probe.expected_total_tokens} tokens，"
                    f"渠道可能没有把我们的内容传给 Claude"
                )

    # 检测4：breaker 有 cache_read → 不同内容不该命中缓存，命中说明中转层干扰
    if breaker and breaker[0].status == "passed" and breaker[0].cache_read_tokens > 0:
        proxy_flags.append(
            f"不同内容的请求也命中了 {breaker[0].cache_read_tokens} tokens 缓存（不同内容不应读到缓存，可能是中转层注入了稳定前缀）"
        )

    if proxy_flags:
        report["proxy_cache"] = {
            "status": "detected",
            "evidence": "；".join(proxy_flags),
        }
        # 降级整体状态
        report["prompt_cache"]["status"] = "warning"
        report["prompt_cache"]["confidence"] = min(report["prompt_cache"].get("confidence", 0), 0.3)
        report["prompt_cache"]["evidence"] = "proxy_interference"
    else:
        report["proxy_cache"] = {"status": "not_detected"}

    return report


def compute_overall_status(report: dict) -> tuple[str, str, float]:
    """根据缓存报告计算总体状态、风险等级和置信度"""
    prompt_status = report.get("prompt_cache", {}).get("status", "inconclusive")
    response_status = report.get("response_cache", {}).get("status", "not_detected")
    prompt_confidence = report.get("prompt_cache", {}).get("confidence", 0)

    if response_status == "suspected":
        return "warning", "medium", 0.7

    if prompt_status == "supported":
        return "passed", "low", prompt_confidence
    elif prompt_status == "partial":
        return "passed", "low", prompt_confidence
    elif prompt_status == "no_usage_fields":
        return "no_usage_fields", "unknown", 0.2
    elif prompt_status == "no_cache":
        return "no_cache", "unknown", 0.3
    elif prompt_status == "warning":
        return "warning", "medium", prompt_confidence
    else:
        return "inconclusive", "unknown", 0.3


# --- 主入口 ---

async def run_cache_diagnostics(
    config: dict,
    timeout_seconds: int = 60,
) -> CacheDiagnosticResult:
    """运行完整的缓存诊断流程

    仅支持 Anthropic /v1/messages 协议。

    流程：
    1. cold_prefix — 建立缓存基准（带 cache_control）
    2. warm_prefix x3 — 多次采样缓存命中
    3. breaker_prefix — 改变内容，验证缓存失效
    4. repeat_identical — 完全相同请求，检测 response cache
    """
    result = CacheDiagnosticResult()

    # Anthropic-only gate
    protocol = config.get("protocol") or detect_protocol(config.get("model", ""), config.get("provider", ""))
    if protocol != "anthropic":
        result.status = "error"
        result.report = {"error": f"缓存诊断仅支持 Anthropic /v1/messages 协议，当前协议: {protocol}"}
        return result

    # 生成本次运行唯一标识，避免跨次测试命中旧缓存
    run_tag = uuid.uuid4().hex[:8]
    result.run_tag = run_tag

    connector = aiohttp.TCPConnector(limit=1)
    async with aiohttp.ClientSession(connector=connector) as session:

        # 1. cold_prefix
        prompts = cold_prefix_prompts("What is the capital of France? Answer in one word.", run_tag)
        cold_probe = await _run_single_probe(
            session, config,
            system_prompt=prompts["system_prompt"],
            user_prompt=prompts["user_prompt"],
            probe_name="cold_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(cold_probe)

        if cold_probe.status != "passed":
            result.status = "error"
            result.report = {"error": f"cold_prefix probe failed: {cold_probe.status} — {cold_probe.error or ''}"}
            return result

        # 2. warm_prefix x3
        for i, question in enumerate(_WARM_QUESTIONS[:WARM_SAMPLE_COUNT]):
            prompts = warm_prefix_prompts(question, run_tag)
            probe = await _run_single_probe(
                session, config,
                system_prompt=prompts["system_prompt"],
                user_prompt=prompts["user_prompt"],
                probe_name="warm_prefix",
                timeout_seconds=timeout_seconds,
            )
            result.probes.append(probe)

        # 3. breaker_prefix
        prompts = breaker_prefix_prompts("What is the capital of France? Answer in one word.", run_tag)
        breaker_probe = await _run_single_probe(
            session, config,
            system_prompt=prompts["system_prompt"],
            user_prompt=prompts["user_prompt"],
            probe_name="breaker_prefix",
            timeout_seconds=timeout_seconds,
        )
        result.probes.append(breaker_probe)

        # 4. repeat_identical — 复用 cold 完全相同的 prompt
        prompts = cold_prefix_prompts("What is the capital of France? Answer in one word.", run_tag)
        identical_probe = await _run_single_probe(
            session, config,
            system_prompt=prompts["system_prompt"],
            user_prompt=prompts["user_prompt"],
            probe_name="repeat_identical",
            timeout_seconds=timeout_seconds,
        )
        identical_probe.identical_request = True
        result.probes.append(identical_probe)

    result.report = build_cache_report(result.probes)
    status, risk, confidence = compute_overall_status(result.report)
    result.status = status
    result.overall_risk = risk
    result.confidence = confidence

    return result
