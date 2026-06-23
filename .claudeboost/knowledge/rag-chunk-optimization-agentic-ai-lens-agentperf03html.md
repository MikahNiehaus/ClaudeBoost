<!-- Source: https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf03.html | Tier: B | Topic: rag-chunk-optimization | Fetched: 2026-06-23 -->

[View a markdown version of this page](agentperf03.md)

[](/pdfs/wellarchitected/latest/agentic-ai-lens/agentic-ai-lens.pdf#agentperf03 "Open PDF")

[Documentation](/index.html)[AWS Well-Architected](/wellarchitected/index.html)[AWS Well-Architected Framework](agentic-ai-lens.html)

Capability intentMaturity levelsCommon issues to watch for

# Memory, context, and RAG optimization

Agentic AI systems depend on efficient access to contextual information through short-term conversational memory, long-term knowledge stores, retrieval-augmented generation pipelines, and LLM context windows to produce accurate, relevant responses. Memory and context management directly impacts both performance and quality. Overstuffing context windows increases inference latency and cost, and insufficient context leads to poor reasoning and hallucination. Optimizing this layer requires implementing tiered memory architectures that match storage and retrieval characteristics to access patterns, managing context windows to maximize information density without exceeding token limits, designing RAG pipelines that retrieve relevant information with minimal latency, and establishing caching strategies that reduce redundant retrievals. These optimizations matter because memory and context operations occur on every reasoning iteration, making their efficiency a multiplier across the agent lifecycle. 

AGENTPERF03: How do you optimize memory management, context windows, and retrieval-augmented generation?   
---  
  
## Capability intent

  * Agent memory is organized into tiers that match storage technology to access pattern, so session reads and long-term semantic queries don't compete on the same hot path. 

  * Context windows are composed from discrete, budgeted components (system instructions, conversation history, retrieved knowledge, and tool schemas), with summarization, dynamic tool selection, and relevance-filtered retrieval keeping prompt size decoupled from session length. 

  * Retrieval-augmented generation pipelines combine semantic chunking, hybrid search, query transformation, and re-ranking so the agent receives precise context with sub-second latency on the first retrieval. 

  * Multi-layer caching (prompt prefixes, retrieval results, tool outputs) reduces redundant work across iterations and sessions, with TTLs and keys tuned per layer against measured hit rates and staleness tolerance. 

  * Retrieval is expressed as a set of agent-invoked tools with bounded iteration, sufficiency checks, and parallel sub-query execution so complex questions converge within the workload's latency budget. 




## Maturity levels

These levels summarize what each stage of maturity looks like for memory, context, and RAG optimization as a whole. 

Level  |  Name  |  What it looks like   
---|---|---  
1  |  Initial  |  Memory, context, and retrieval are treated as single-tier concerns. Full conversation history and the entire tool catalog flow into every prompt, RAG chunks are fixed-size with no relevance filtering, and no caching exists beyond what individual services provide by default. Token consumption and retrieval latency are reviewed only after a cost spike or a user-reported slowdown.   
2  |  Emerging  |  Teams have separated short-term from long-term memory and adopted basic summarization of conversation history. RAG is running through a managed service such as [Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html), and prompts are structured so that system instructions and stable tool definitions sit in a reusable prefix. Per-component token usage and retrieval latency are measured for production agents but tuning is still manual and reactive.   
3  |  Defined  |  Memory tiers use storage matched to access pattern, with [Amazon Bedrock AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html) or [Amazon ElastiCache](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.html) serving short-term state and [AgentCore Memory long-term strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-configuring-built-in-strategies.html) or [Amazon OpenSearch Service](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/application-agentic-memory.html) serving cross-session knowledge. RAG pipelines use semantic chunking, hybrid search, and a re-ranking stage, with top-k caps and per-passage thresholds enforced. Prompts compose with [Amazon Bedrock prompt caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html), and prompt templates are versioned in [Amazon Bedrock Prompt management](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management-create.html) with per-component token budgets.   
4  |  Proactive  |  Retrieval is expressed as a set of agent tools through [Amazon Bedrock AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html) with sufficiency evaluation, bounded iteration, and parallel sub-query execution for complex questions. Multi-layer caching is active across prompt prefixes, semantic retrieval keys, and tool outputs, with per-layer hit rates monitored against floors. Memory extraction, eviction, and prompt-template promotion run through automated pipelines, and per-tier latency and cache hit rate feed continuous tuning in [Amazon CloudWatch generative AI observability](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/GenAI-observability.html).   
5  |  Optimized  |  Memory tier sizing, retrieval budgets, and cache TTLs are recalibrated continuously from production telemetry rather than by scheduled review. Prompt components, tool selection, and retrieval routing are evaluated through [Amazon Bedrock AgentCore Evaluations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html) gated in CI/CD, and optimization patterns flow back to internal communities of practice. The organization contributes memory and retrieval patterns to the broader agentic AI community.   
  
## Common issues to watch for

  * Teams store all agent memory in a single database regardless of access pattern, which forces sub-millisecond session reads and large-scale semantic searches to compete on the same backend and degrades both. 

  * Conversation history and the full tool catalog are included in every prompt without summarization or dynamic selection, so prompt size and latency grow linearly with session length even after the information stops being useful. 

  * RAG pipelines rely on fixed-size chunking and raw top-k passages without a re-ranking stage or per-passage relevance thresholds, diluting useful context with low-signal chunks that crowd out higher-signal passages. 

  * Caching is either absent or applied at a single layer with a single TTL, missing the stacked savings available when prompt prefixes, semantic retrieval keys, and tool outputs are cached independently with data-type-specific policies. 

  * Agentic retrieval loops run without iteration caps, sufficiency evaluation, or parallel sub-query execution, which either cuts off complex questions prematurely or lets iterations grow unbounded and consume the workload's latency budget. 




###### Best practices

  * [AGENTPERF03-BP01 Implement tiered memory management systems](./agentperf03-bp01.html)

  * [AGENTPERF03-BP02 Optimize context window utilization and prompt management](./agentperf03-bp02.html)

  * [AGENTPERF03-BP03 Optimize RAG retrieval pipelines for latency and precision](./agentperf03-bp03.html)

  * [AGENTPERF03-BP04 Establish efficient agent caching and data access patterns](./agentperf03-bp04.html)

  * [AGENTPERF03-BP05 Implement agentic retrieval patterns for dynamic, agent-driven knowledge access](./agentperf03-bp05.html)




**Javascript is disabled or is unavailable in your browser.**

To use the Amazon Web Services Documentation, Javascript must be enabled. Please refer to your browser's Help pages for instructions.

[Document Conventions](/general/latest/gr/docconventions.html)

AGENTPERF02-BP04 Optimize streaming responses and time-to-first-token for agent interactions

AGENTPERF03-BP01 Implement tiered memory management systems

Did this page help you? - Yes

Thanks for letting us know we're doing a good job!

If you've got a moment, please tell us what we did right so we can do more of it.

Did this page help you? - No

Thanks for letting us know this page needs work. We're sorry we let you down.

If you've got a moment, please tell us how we can make the documentation better.
