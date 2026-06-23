<!-- Source: https://dev.to/dohkoai/claude-code-in-production-12-tips-after-10000-api-calls-ae5 | Tier: B | Topic: batch-api-cost | Fetched: 2026-06-23 -->

Skip to content

Navigation menu [ ](/)

Search [ Powered by Algolia Search ](https://www.algolia.com/developers/?utm_source=devto&utm_medium=referral)

[ Log in ](https://dev.to/enter?signup_subforem=1) [ Create account ](https://dev.to/enter?signup_subforem=1&state=new-user)

## DEV Community

Close

Add reaction 

Like  Unicorn  Exploding Head  Raised Hands  Fire 

Jump to Comments  Save  Boost 

More...

Copy link Copy link

Copied to Clipboard

[ Share to X ](https://twitter.com/intent/tweet?text=%22Claude%20Code%20in%20Production%3A%2012%20Tips%20After%2010%2C000%2B%20API%20Calls%22%20by%20dohko%20%23DEVCommunity%20https%3A%2F%2Fdev.to%2Fdohkoai%2Fclaude-code-in-production-12-tips-after-10000-api-calls-ae5) [ Share to LinkedIn ](https://www.linkedin.com/shareArticle?mini=true&url=https%3A%2F%2Fdev.to%2Fdohkoai%2Fclaude-code-in-production-12-tips-after-10000-api-calls-ae5&title=Claude%20Code%20in%20Production%3A%2012%20Tips%20After%2010%2C000%2B%20API%20Calls&summary=Hard-won%20lessons%20from%20running%20Claude%20Code%20at%20scale.%20Context%20management%2C%20cost%20control%2C%20MCP%20integration%2C%20and%20the%20mistakes%20that%20cost%20me%20real%20money.&source=DEV%20Community) [ Share to Facebook ](https://www.facebook.com/sharer.php?u=https%3A%2F%2Fdev.to%2Fdohkoai%2Fclaude-code-in-production-12-tips-after-10000-api-calls-ae5) [ Share to Mastodon ](https://s2f.kytta.dev/?text=https%3A%2F%2Fdev.to%2Fdohkoai%2Fclaude-code-in-production-12-tips-after-10000-api-calls-ae5)

Share Post via... [Report Abuse](/report-abuse)

[](/dohkoai)

[dohko](/dohkoai)

Posted on Mar 24

         

#  Claude Code in Production: 12 Tips After 10,000+ API Calls 

[#claudecode](/t/claudecode) [#ai](/t/ai) [#productivity](/t/productivity) [#webdev](/t/webdev)

##  [AI Engineering in Practice (28 Part Series)](/dohkoai/series/37423)

[ 1 Claude Code in Production: 12 Tips After 10,000+ API Calls ](/dohkoai/claude-code-in-production-12-tips-after-10000-api-calls-ae5 "Published Mar 24") [ 2 5 Vibe Coding Workflows That Actually Ship Production Code in 2026 ](/dohkoai/5-vibe-coding-workflows-that-actually-ship-production-code-in-2026-1nmn "Published Mar 24") [ ... 24 more parts... ](/dohkoai/agentsmd-the-file-every-ai-assisted-project-needs-and-how-to-write-a-great-one-2ej9 "View more") [ 3 AGENTS.md: The File Every AI-Assisted Project Needs (And How to Write a Great One) ](/dohkoai/agentsmd-the-file-every-ai-assisted-project-needs-and-how-to-write-a-great-one-2ej9 "Published Mar 24") [ 4 I Cut My AI Coding Costs by 73% Without Losing Quality — Here's the Exact Setup ](/dohkoai/i-cut-my-ai-coding-costs-by-73-without-losing-quality-heres-the-exact-setup-51d7 "Published Mar 24") [ 5 How to Build a Multi-Model AI Router in 50 Lines of Python ](/dohkoai/how-to-build-a-multi-model-ai-router-in-50-lines-of-python-725 "Published Mar 25") [ 6 5 AGENTS.md Patterns That 10x Your AI Coding Workflow (With Templates) ](/dohkoai/5-agentsmd-patterns-that-10x-your-ai-coding-workflow-with-templates-5ln "Published Mar 25") [ 7 Multi-Agent Architecture in Practice: How to Split Work Across AI Agents Without Chaos ](/dohkoai/multi-agent-architecture-in-practice-how-to-split-work-across-ai-agents-without-chaos-5efe "Published Mar 25") [ 8 Prompt Caching for AI Coding: The $0 Optimization That Saves 60% on Every Call ](/dohkoai/prompt-caching-for-ai-coding-the-0-optimization-that-saves-60-on-every-call-24eo "Published Mar 25") [ 9 5 AI Agent Memory Patterns That Actually Work (With Python Code) ](/dohkoai/5-ai-agent-memory-patterns-that-actually-work-with-python-code-4i1o "Published Mar 27") [ 10 Build Your First MCP Server in 10 Minutes — Copy-Paste TypeScript Tutorial ](/dohkoai/build-your-first-mcp-server-in-10-minutes-copy-paste-typescript-tutorial-2dda "Published Mar 27") [ 11 Build Your First MCP Server in 10 Minutes — Copy-Paste TypeScript Tutorial ](/dohkoai/build-your-first-mcp-server-in-10-minutes-copy-paste-typescript-tutorial-ao7 "Published Mar 27") [ 12 7 Agentic Coding Patterns That Replace Manual Dev Workflows (2026 Edition) ](/dohkoai/7-agentic-coding-patterns-that-replace-manual-dev-workflows-2026-edition-2k0i "Published Mar 28") [ 13 How to Pick the Right AI Coding Tool in 2026 (Decision Framework + Benchmark Data) ](/dohkoai/how-to-pick-the-right-ai-coding-tool-in-2026-decision-framework-benchmark-data-3h6l "Published Mar 28") [ 14 7 Lessons from the LiteLLM Supply Chain Attack Every AI Developer Must Learn (With Defense Code) ](/dohkoai/7-lessons-from-the-litellm-supply-chain-attack-every-ai-developer-must-learn-with-defense-code-2mo5 "Published Mar 29") [ 15 5 AI Workflow Orchestration Patterns with n8n, Dify, and Ollama (Production-Ready Code) ](/dohkoai/5-ai-workflow-orchestration-patterns-with-n8n-dify-and-ollama-production-ready-code-4hle "Published Mar 29") [ 16 7 AI Agent Observability Patterns Every Developer Needs in Production (With Code) ](/dohkoai/7-ai-agent-observability-patterns-every-developer-needs-in-production-with-code-3e40 "Published Mar 30") [ 17 8 Agentic Coding Patterns That Ship 10x Faster (Cursor, Windsurf, Claude Code) ](/dohkoai/8-agentic-coding-patterns-that-ship-10x-faster-cursor-windsurf-claude-code-2h0j "Published Mar 30") [ 18 7 AI Agent Evaluation Patterns That Catch Failures Before Production ](/dohkoai/7-ai-agent-evaluation-patterns-that-catch-failures-before-production-480j "Published Mar 31") [ 19 5 AI-Powered Code Review Pipelines You Can Build This Weekend ](/dohkoai/5-ai-powered-code-review-pipelines-you-can-build-this-weekend-2683 "Published Mar 31") [ 20 9 MCP Production Patterns That Actually Scale Multi-Agent Systems (2026) ](/dohkoai/9-mcp-production-patterns-that-actually-scale-multi-agent-systems-2026-4ap3 "Published Apr 1") [ 21 8 AI Agent Memory Patterns for Production Systems (Beyond Basic RAG) ](/dohkoai/8-ai-agent-memory-patterns-for-production-systems-beyond-basic-rag-5795 "Published Apr 1") [ 22 9 MCP Production Patterns That Actually Scale Multi-Agent Systems (2026) ](/dohkoai/9-mcp-production-patterns-that-actually-scale-multi-agent-systems-2026-3o5j "Published Apr 1") [ 23 8 AI Agent Memory Patterns for Production Systems (Beyond Basic RAG) ](/dohkoai/8-ai-agent-memory-patterns-for-production-systems-beyond-basic-rag-89c "Published Apr 1") [ 24 7 AI Agent Orchestration Patterns That Actually Scale Beyond a Single Demo ](/dohkoai/7-ai-agent-orchestration-patterns-that-actually-scale-beyond-a-single-demo-5bkk "Published Apr 2") [ 25 9 MCP Sandboxing and Resilience Patterns That Stop AI Agents From Breaking in Production ](/dohkoai/9-mcp-sandboxing-and-resilience-patterns-that-stop-ai-agents-from-breaking-in-production-5h09 "Published Apr 3") [ 26 From Demo to Production: 7 AI Agent SDK Patterns That Actually Scale Multi-Agent Systems ](/dohkoai/from-demo-to-production-7-ai-agent-sdk-patterns-that-actually-scale-multi-agent-systems-14jp "Published Apr 3") [ 27 7 AI Agent Orchestration Patterns for Scaling Concurrent Systems (With Production Code) ](/dohkoai/7-ai-agent-orchestration-patterns-for-scaling-concurrent-systems-with-production-code-1onc "Published Apr 4") [ 28 9 MCP Resilience Patterns That Keep AI Agents Alive in Production (With Code) ](/dohkoai/9-mcp-resilience-patterns-that-keep-ai-agents-alive-in-production-with-code-2ohi "Published Apr 4")

#  Claude Code in Production: 12 Tips After 10,000+ API Calls 

I've run Claude Code for thousands of tasks building 264 AI engineering frameworks. Here's what I wish I knew on day one — the stuff that isn't in the docs.

* * *

##  Context Management (Tips 1-4) 

###  1\. Front-Load Context, Not Instructions 

❌ Bad:  

    
    
    Refactor the auth module to use JWT refresh tokens with rotation, 
    implement PKCE flow, add rate limiting per user...
    

Enter fullscreen mode Exit fullscreen mode

✅ Good:  

    
    
    Here's the current auth module: [paste code]
    Here's the failing test: [paste test]
    Here's our security requirements doc: [paste doc]
    
    The refresh token implementation has a race condition under load. 
    Fix it while maintaining the existing API contract.
    

Enter fullscreen mode Exit fullscreen mode

**Why:** Claude Code performs dramatically better when it understands the codebase first, then gets a focused task. Long instruction lists lead to partial implementations.

###  2\. Use AGENTS.md as Your Session Primer 

Create an `AGENTS.md` at project root:  

    
    
    # AGENTS.md
    ## Stack: Next.js 15 + TypeScript + Prisma + PostgreSQL  
    ## Style: Functional, no classes, Result<T,E> error handling
    ## Testing: Vitest, test files colocated with source
    ## Current sprint: Payment integration (Stripe)
    ## Known debt: WebSocket handler leaks memory (#142)
    

Enter fullscreen mode Exit fullscreen mode

Claude Code reads this automatically. One file eliminates repeated context-setting across sessions.

###  3\. The 200K Context Trap 

Claude's 200K context window is amazing. It's also a cost trap.

**The rule:** Only load files the AI needs to MODIFY or UNDERSTAND for the current task. Not "everything just in case."  

    
    
    # ❌ Loading everything
    claude "fix the bug" --include "src/**/*"
    
    # ✅ Loading what matters  
    claude "fix the auth bug" --include "src/auth/**" "src/middleware/auth.ts" "tests/auth.test.ts"
    

Enter fullscreen mode Exit fullscreen mode

**Cost impact:** A 200K context call costs ~10x more than a 20K context call. Be surgical.

###  4\. The Plan-Then-Execute Pattern 

For complex tasks, always split into two calls:

**Call 1 (cheap — Sonnet):**  

    
    
    Given this codebase context, create a step-by-step plan 
    for implementing [feature]. List files to modify, 
    approach for each, and potential risks.
    

Enter fullscreen mode Exit fullscreen mode

**Call 2 (powerful — Opus):**  

    
    
    Execute this plan: [paste plan from Call 1]
    Here are the files: [only the ones the plan identified]
    

Enter fullscreen mode Exit fullscreen mode

This catches bad approaches at $0.10 instead of $5.00.

* * *

##  Cost Control (Tips 5-8) 

###  5\. Track Costs Per Task Category 

After a month of tracking, here are real cost ranges:

Task Type | Avg Cost | Model  
---|---|---  
Bug fix (single file) | $0.15 | Sonnet  
Feature (multi-file) | $1.50 | Opus  
Architecture refactor | $4.00 | Opus  
Test generation | $0.08 | Sonnet/Mini  
Code review | $0.20 | Sonnet  
Documentation | $0.05 | Mini  
  
**Lesson:** 60% of coding tasks can use Sonnet or Mini. Reserve Opus for the 20% that actually needs deep reasoning.

###  6\. Set Hard Budget Limits 
    
    
    # In your shell config
    export CLAUDE_MAX_COST_PER_SESSION=10.00
    export CLAUDE_WARN_AT=5.00
    

Enter fullscreen mode Exit fullscreen mode

Without limits, a single runaway session (recursive debugging loop) can burn $20+.

###  7\. Cache Repeated Context 

If you're running multiple tasks against the same codebase:  

    
    
    # Generate context once
    cat src/auth/**/*.ts > /tmp/auth-context.txt
    
    # Reuse across calls
    claude "Task 1..." --context /tmp/auth-context.txt
    claude "Task 2..." --context /tmp/auth-context.txt
    

Enter fullscreen mode Exit fullscreen mode

Some API providers offer prompt caching (up to 90% savings on repeated prefixes). Use it.

###  8\. The 3-Attempt Rule 

If Claude hasn't solved it in 3 attempts with different approaches, stop. Either:

  * The problem needs human insight the AI lacks
  * Your context is missing critical information
  * The task needs decomposition into smaller pieces



Throwing more tokens at a stuck AI is the #1 cost waste.

* * *

##  MCP Integration (Tips 9-10) 

###  9\. MCP Servers Are Game-Changers (When Used Right) 

Model Context Protocol lets Claude Code access external tools. The highest-value MCP servers:  

    
    
    {
      "mcpServers": {
        "filesystem": {
          "command": "npx",
          "args": ["@anthropic/mcp-fs", "--root", "./src"]
        },
        "github": {
          "command": "npx", 
          "args": ["@anthropic/mcp-github"]
        },
        "postgres": {
          "command": "npx",
          "args": ["@anthropic/mcp-postgres", "--connection-string", "$DATABASE_URL"]
        }
      }
    }
    

Enter fullscreen mode Exit fullscreen mode

**Best practice:** Start with filesystem + one integration (GitHub or DB). Don't add 10 MCP servers — each adds latency and token cost.

###  10\. Progressive Disclosure for MCP 

Don't expose all tools at once. Configure MCP servers to reveal capabilities progressively:  

    
    
    # Level 1: Read-only (default)
    tools: [read_file, list_directory, search]
    
    # Level 2: After confirmation
    tools: [write_file, create_directory]
    
    # Level 3: Explicit approval only
    tools: [delete_file, run_command, database_write]
    

Enter fullscreen mode Exit fullscreen mode

This prevents expensive mistakes. An AI with unrestricted write access WILL eventually corrupt something.

* * *

##  Production Patterns (Tips 11-12) 

###  11\. The Review Gate 

Never ship AI-generated code without review. But make the review efficient:  

    
    
    # Generate a diff summary
    claude "Summarize the changes you made and flag anything 
    that touches security, performance, or external APIs"
    

Enter fullscreen mode Exit fullscreen mode

Focus your human review on:

  1. Security boundaries (auth, input validation)
  2. Error handling (is every failure path covered?)
  3. Performance (O(n²) hiding in innocent-looking code?)
  4. Side effects (unexpected state mutations?)



Skip reviewing: formatting, import ordering, variable naming.

###  12\. Build Your Own Feedback Loop 

The most valuable pattern I've found:  

    
    
    1. AI generates code
    2. Tests run automatically  
    3. Test results feed back to AI
    4. AI fixes failures
    5. Repeat until green (max 3 cycles)
    6. Human reviews final diff
    

Enter fullscreen mode Exit fullscreen mode

This closes the loop between generation and validation. The AI learns from its own test failures within a session.

* * *

##  The Honest Truth 

Claude Code (and all AI coding tools) are incredible for:

  * Reducing boilerplate drudgery by 80%
  * Exploring unfamiliar codebases fast
  * Generating comprehensive test suites
  * Maintaining consistency across large codebases



They're still unreliable for:

  * Novel algorithm design
  * Security-critical code
  * Performance optimization
  * Complex distributed systems reasoning



The developers getting the most value treat AI tools as a powerful junior developer — fast, eager, occasionally wrong, always needs review.

* * *

##  Want More? 

These tips come from the [AI Dev Toolkit](https://ai-dev-toolkit-five.vercel.app) — 264 production frameworks including Claude Code workflows, MCP server configs, multi-agent setups, and cost optimization pipelines. 168 samples are free on [GitHub](https://github.com/dohko04/awesome-ai-prompts-for-devs).

* * *

_Which tip surprised you most? What's your Claude Code workflow? Let me know in the comments._

##  [AI Engineering in Practice (28 Part Series)](/dohkoai/series/37423)

[ 1 Claude Code in Production: 12 Tips After 10,000+ API Calls ](/dohkoai/claude-code-in-production-12-tips-after-10000-api-calls-ae5 "Published Mar 24") [ 2 5 Vibe Coding Workflows That Actually Ship Production Code in 2026 ](/dohkoai/5-vibe-coding-workflows-that-actually-ship-production-code-in-2026-1nmn "Published Mar 24") [ ... 24 more parts... ](/dohkoai/agentsmd-the-file-every-ai-assisted-project-needs-and-how-to-write-a-great-one-2ej9 "View more") [ 3 AGENTS.md: The File Every AI-Assisted Project Needs (And How to Write a Great One) ](/dohkoai/agentsmd-the-file-every-ai-assisted-project-needs-and-how-to-write-a-great-one-2ej9 "Published Mar 24") [ 4 I Cut My AI Coding Costs by 73% Without Losing Quality — Here's the Exact Setup ](/dohkoai/i-cut-my-ai-coding-costs-by-73-without-losing-quality-heres-the-exact-setup-51d7 "Published Mar 24") [ 5 How to Build a Multi-Model AI Router in 50 Lines of Python ](/dohkoai/how-to-build-a-multi-model-ai-router-in-50-lines-of-python-725 "Published Mar 25") [ 6 5 AGENTS.md Patterns That 10x Your AI Coding Workflow (With Templates) ](/dohkoai/5-agentsmd-patterns-that-10x-your-ai-coding-workflow-with-templates-5ln "Published Mar 25") [ 7 Multi-Agent Architecture in Practice: How to Split Work Across AI Agents Without Chaos ](/dohkoai/multi-agent-architecture-in-practice-how-to-split-work-across-ai-agents-without-chaos-5efe "Published Mar 25") [ 8 Prompt Caching for AI Coding: The $0 Optimization That Saves 60% on Every Call ](/dohkoai/prompt-caching-for-ai-coding-the-0-optimization-that-saves-60-on-every-call-24eo "Published Mar 25") [ 9 5 AI Agent Memory Patterns That Actually Work (With Python Code) ](/dohkoai/5-ai-agent-memory-patterns-that-actually-work-with-python-code-4i1o "Published Mar 27") [ 10 Build Your First MCP Server in 10 Minutes — Copy-Paste TypeScript Tutorial ](/dohkoai/build-your-first-mcp-server-in-10-minutes-copy-paste-typescript-tutorial-2dda "Published Mar 27") [ 11 Build Your First MCP Server in 10 Minutes — Copy-Paste TypeScript Tutorial ](/dohkoai/build-your-first-mcp-server-in-10-minutes-copy-paste-typescript-tutorial-ao7 "Published Mar 27") [ 12 7 Agentic Coding Patterns That Replace Manual Dev Workflows (2026 Edition) ](/dohkoai/7-agentic-coding-patterns-that-replace-manual-dev-workflows-2026-edition-2k0i "Published Mar 28") [ 13 How to Pick the Right AI Coding Tool in 2026 (Decision Framework + Benchmark Data) ](/dohkoai/how-to-pick-the-right-ai-coding-tool-in-2026-decision-framework-benchmark-data-3h6l "Published Mar 28") [ 14 7 Lessons from the LiteLLM Supply Chain Attack Every AI Developer Must Learn (With Defense Code) ](/dohkoai/7-lessons-from-the-litellm-supply-chain-attack-every-ai-developer-must-learn-with-defense-code-2mo5 "Published Mar 29") [ 15 5 AI Workflow Orchestration Patterns with n8n, Dify, and Ollama (Production-Ready Code) ](/dohkoai/5-ai-workflow-orchestration-patterns-with-n8n-dify-and-ollama-production-ready-code-4hle "Published Mar 29") [ 16 7 AI Agent Observability Patterns Every Developer Needs in Production (With Code) ](/dohkoai/7-ai-agent-observability-patterns-every-developer-needs-in-production-with-code-3e40 "Published Mar 30") [ 17 8 Agentic Coding Patterns That Ship 10x Faster (Cursor, Windsurf, Claude Code) ](/dohkoai/8-agentic-coding-patterns-that-ship-10x-faster-cursor-windsurf-claude-code-2h0j "Published Mar 30") [ 18 7 AI Agent Evaluation Patterns That Catch Failures Before Production ](/dohkoai/7-ai-agent-evaluation-patterns-that-catch-failures-before-production-480j "Published Mar 31") [ 19 5 AI-Powered Code Review Pipelines You Can Build This Weekend ](/dohkoai/5-ai-powered-code-review-pipelines-you-can-build-this-weekend-2683 "Published Mar 31") [ 20 9 MCP Production Patterns That Actually Scale Multi-Agent Systems (2026) ](/dohkoai/9-mcp-production-patterns-that-actually-scale-multi-agent-systems-2026-4ap3 "Published Apr 1") [ 21 8 AI Agent Memory Patterns for Production Systems (Beyond Basic RAG) ](/dohkoai/8-ai-agent-memory-patterns-for-production-systems-beyond-basic-rag-5795 "Published Apr 1") [ 22 9 MCP Production Patterns That Actually Scale Multi-Agent Systems (2026) ](/dohkoai/9-mcp-production-patterns-that-actually-scale-multi-agent-systems-2026-3o5j "Published Apr 1") [ 23 8 AI Agent Memory Patterns for Production Systems (Beyond Basic RAG) ](/dohkoai/8-ai-agent-memory-patterns-for-production-systems-beyond-basic-rag-89c "Published Apr 1") [ 24 7 AI Agent Orchestration Patterns That Actually Scale Beyond a Single Demo ](/dohkoai/7-ai-agent-orchestration-patterns-that-actually-scale-beyond-a-single-demo-5bkk "Published Apr 2") [ 25 9 MCP Sandboxing and Resilience Patterns That Stop AI Agents From Breaking in Production ](/dohkoai/9-mcp-sandboxing-and-resilience-patterns-that-stop-ai-agents-from-breaking-in-production-5h09 "Published Apr 3") [ 26 From Demo to Production: 7 AI Agent SDK Patterns That Actually Scale Multi-Agent Systems ](/dohkoai/from-demo-to-production-7-ai-agent-sdk-patterns-that-actually-scale-multi-agent-systems-14jp "Published Apr 3") [ 27 7 AI Agent Orchestration Patterns for Scaling Concurrent Systems (With Production Code) ](/dohkoai/7-ai-agent-orchestration-patterns-for-scaling-concurrent-systems-with-production-code-1onc "Published Apr 4") [ 28 9 MCP Resilience Patterns That Keep AI Agents Alive in Production (With Code) ](/dohkoai/9-mcp-resilience-patterns-that-keep-ai-agents-alive-in-production-with-code-2ohi "Published Apr 4")

##  Top comments (0)

Subscribe

Personal Trusted User

[ Create template ](/settings/response-templates)

Templates let you quickly answer FAQs or store snippets for re-use.

Submit Preview [Dismiss](/404.html)

[Code of Conduct](/code-of-conduct) • [Report abuse](/report-abuse)

Are you sure you want to hide this comment? It will become hidden in your post, but will still be visible via the comment's permalink. 

Hide child comments as well

Confirm 

For further actions, you may consider blocking this person and/or [reporting abuse](/report-abuse)

[ dohko  ](/dohkoai)

Follow

  * Joined 

Mar 23, 2026




###  More from [dohko](/dohkoai)

[ 9 MCP Resilience Patterns That Keep AI Agents Alive in Production (With Code)  #ai #mcp #python #typescript ](/dohkoai/9-mcp-resilience-patterns-that-keep-ai-agents-alive-in-production-with-code-2ohi) [ 7 AI Agent Orchestration Patterns for Scaling Concurrent Systems (With Production Code)  #ai #agents #python #architecture ](/dohkoai/7-ai-agent-orchestration-patterns-for-scaling-concurrent-systems-with-production-code-1onc) [ 90% of Devs Use AI at Work — But Here's the Trust Problem Nobody's Solving  #ai #productivity #devops #programming ](/dohkoai/90-of-devs-use-ai-at-work-but-heres-the-trust-problem-nobodys-solving-5h89)

💎 DEV Diamond Sponsors 

Thank you to our Diamond Sponsors for supporting the DEV Community 

[ ](https://aistudio.google.com/?utm_source=partner&utm_medium=partner&utm_campaign=FY25-Global-DEVpartnership-sponsorship-AIS&utm_content=-&utm_term=-&bb=146443)

Google AI is the official AI Model and Platform Partner of DEV

[ ](https://neon.tech/?ref=devto&bb=146443)

Neon is the official database partner of DEV

[ ](https://www.algolia.com/developers/?utm_source=devto&utm_medium=referral&bb=146443)

Algolia is the official search partner of DEV

[DEV Community](/) — A space to discuss and keep up software development and manage your software career 



* [ Home ](/)
* [ About ](/about)
* [ Contact ](/contact)
* [ MLH ](https://mlh.io/)



* [ Code of Conduct ](/code-of-conduct)
* [ Privacy Policy ](/privacy)
* [ Terms of Use ](/terms)

Built on [Forem](https://www.forem.com) — the [open source](https://dev.to/t/opensource) software that powers [DEV](https://dev.to) and other inclusive communities.

Made with love and [Ruby on Rails](https://dev.to/t/rails). DEV Community (C) 2016 - 2026.

We're a place where coders share, stay up-to-date and grow their careers. 

[ Log in ](https://dev.to/enter?signup_subforem=1) [ Create account ](https://dev.to/enter?signup_subforem=1&state=new-user)
