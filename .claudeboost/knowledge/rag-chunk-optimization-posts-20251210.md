<!-- Source: https://nicoloboschi.com/posts/20251210/ | Tier: B | Topic: rag-chunk-optimization | Fetched: 2026-06-23 -->

[Nicolò Boschi](/)

[ ](https://github.com/nicoloboschi "GitHub")[ ](https://x.com/nicoloboschi "X")[ ](https://www.linkedin.com/in/nicoló-boschi-621a1a158/ "LinkedIn")[](mailto:boschi1997@gmail.com "Email")

[ Back](/posts/)

# Token budgets vs top-k: a better way to fill context windows

December 10, 2025 · 3 min read

**TL;DR** : Top-k retrieval returns a fixed number of results regardless of their size. Token budgets fill your context window by actual token count. Hindsight uses greedy packing - iterate through ranked results until adding the next would exceed the budget. You get predictable context consumption and maximum information density.

* * *

## The Top-K Problem

Standard RAG retrieves "top 10 results" or "top 5 chunks." But what does that actually give you?

If each chunk is 200 tokens, you get 2000 tokens. If each is 800 tokens, you get 8000. The LLM's context window doesn't care about chunk counts - it cares about tokens. Top-k gives you unpredictable context consumption.

Worse, top-k treats all results equally. Result #1 might be a short fact ("Alice works at Google") while result #10 is a long paragraph. With a fixed k, you either include both or neither. There's no way to say "give me as much relevant content as fits in 4096 tokens."

## Token Budgets

Hindsight flips the model. Instead of specifying how many results you want, you specify how many tokens you can accommodate:
    
    
    1results = client.recall(
    2    bank_id="my-bank",
    3    query="What do I know about Alice?",
    4    max_tokens=4096
    5)

The system returns memories until the next one would exceed your budget. Simple greedy packing - iterate through relevance-ranked results, include each one, stop when you're full.

This matches how LLMs actually work. Your context window is 128K tokens, not "128K results." Token budgets speak the same language.

## The Selection Algorithm

After Hindsight runs its retrieval (semantic + BM25 + graph + temporal, fused and reranked), it has a ranked list of candidate memories. The selection step is straightforward:

  1. Start with empty result set
  2. Take the next highest-ranked memory
  3. If adding it stays within budget, include it
  4. Repeat until the next memory would exceed the limit



Mathematically: include memories f₁, f₂, …, fₙ where the sum of their tokens ≤ k, but adding fₙ₊₁ would exceed k.

No magic. Just pack as much relevant content as fits.

## Budget vs Max Tokens

Hindsight separates two concerns:

Parameter| Controls| Values  
---|---|---  
`budget`| Search depth| `"low"`, `"mid"`, `"high"`  
`max_tokens`| Result size| Integer (e.g., 4096)  
  
Budget affects how thoroughly the system explores your memory graph. High budget means deeper traversal, more multi-hop reasoning, more candidates considered.

Max tokens affects how much comes back. You can do a deep search but only return the best 2K tokens, or a shallow search and return everything found up to 8K.
    
    
    1# Deep search, compact results
    2client.recall(budget="high", max_tokens=2048)
    3
    4# Quick search, generous context
    5client.recall(budget="low", max_tokens=8192)

These are orthogonal. In my opinion, this separation is cleaner than systems that conflate "search harder" with "return more."

## Practical Token Allocation

Common configurations:

Max Tokens| Roughly| Use Case  
---|---|---  
500| Half a page| Quick lookups, single facts  
2048| ~2 pages| Focused answers, fast processing  
4096| ~4 pages| Balanced (default)  
8192| ~8 pages| Complex reasoning, comprehensive context  
      
    
     1# Simple fact lookup
     2results = client.recall(
     3    bank_id="my-bank",
     4    query="Alice's email",
     5    max_tokens=500
     6)
     7
     8# Standard query
     9results = client.recall(
    10    bank_id="my-bank",
    11    query="What programming languages does Alice like?",
    12    max_tokens=4096
    13)

## Layered Token Budgets

Beyond core memories, you can allocate separate budgets for additional context:
    
    
     1response = client.recall(
     2    bank_id="my-bank",
     3    query="Comprehensive Alice profile",
     4    max_tokens=4096,              # Core memories
     5    include_entities=True,
     6    max_entity_tokens=1000,       # Entity observations
     7    include_chunks=True,
     8    max_chunk_tokens=500          # Original text snippets
     9)
    10# Total potential context: ~5.5K tokens

Three separate budgets, each capped independently:

  * **max_tokens** : The main memory results
  * **max_entity_tokens** : Synthesized entity profiles for mentioned entities
  * **max_chunk_tokens** : Original source text when you need exact phrasing



You control exactly how your context window gets partitioned.

## Why This Matters

**Predictable consumption** : You know exactly how many tokens you're spending on retrieval. No surprises when building prompts.

**Maximum density** : Top-k might return 10 results using only 3K tokens when you had 8K available. Token budgets fill the space.

**Context window integration** : Modern agents juggle system prompts, user messages, tools, and retrieved context. Token budgets let you allocate precisely: "retrieval gets 4K, tools get 2K, leave 2K for response."

**No arbitrary cutoffs** : Top-10 is arbitrary. Why not top-9? Top-11? Token budgets are grounded in the actual constraint - your LLM's context limit.

## CLI Usage
    
    
    1# Default 4K token budget
    2hindsight memory recall my-bank "What does Alice do?"
    3
    4# Custom budget
    5hindsight memory recall my-bank "query" --max-tokens 8192
    6
    7# High search depth, moderate return
    8hindsight memory recall my-bank "query" --budget high --max-tokens 4096

* * *

Top-k is a proxy for what you actually want. Token budgets are the real thing. Specify your context allocation, let the system pack it with the most relevant content.

[Hindsight documentation](https://hindsight.vectorize.io) | [GitHub](https://github.com/vectorize-io/hindsight)

Enjoyed this? Get notified about new posts

Subscribe

Related posts

[Hindsight vs traditional RAG: what you actually get](/posts/20251208/) [Background operations: what happens after retain()](/posts/20251224/) [Beyond vector search: how TEMPR combines 4 retrieval strategies](/posts/20251216/)

[← Hindsight vs traditional RAG: what you actually get](/posts/20251208/) [Drop SQLite: zero-dependency quick starts with pg0 →](/posts/20251212/)

(C) 2026 Nicolò Boschi

[GitHub](https://github.com/nicoloboschi) [X](https://x.com/nicoloboschi) [LinkedIn](https://www.linkedin.com/in/nicoló-boschi-621a1a158/) [Email](mailto:boschi1997@gmail.com)
