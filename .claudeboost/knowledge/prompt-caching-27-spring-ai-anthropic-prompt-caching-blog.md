<!-- Source: https://spring.io/blog/2025/10/27/spring-ai-anthropic-prompt-caching-blog/ | Tier: B | Topic: prompt-caching | Fetched: 2026-06-23 -->

Skip to main content

[Learn more about Day 0 access to security patches via Enterprise support.](https://enterprise.spring.io)

[](/ "Home")

Why Spring

  * [Overview](/why-spring)
  * Trending

  * [Generative AI](/ai)
  * [Cloud](/cloud)
  * Architecture Patterns

  * [Microservices](/microservices)
  * [Reactive](/reactive)
  * [Event Driven](/event-driven)
  * Application Types

  * [Web Applications](/web-applications)
  * [Serverless](/serverless)
  * [Batch](/batch)



Learn

  * Getting Started

  * [Quickstart](/quickstart)
  * [Guides](/guides)
  * Academy

  * [Courses](https://spring.academy/courses)
  * [Get Certified](https://spring.academy/learning-path)



Projects

  * [Overview](/projects)
  * Projects

  * [Spring Boot](/projects/spring-boot)
  * [Spring Framework](/projects/spring-framework)
  * [Spring Cloud](/projects/spring-cloud)
  * [Spring AI](/projects/spring-ai)
  * [Spring Data](/projects/spring-data)
  * [Spring Integration](/projects/spring-integration)
  * [Spring Batch](/projects/spring-batch)
  * [Spring Security](/projects/spring-security)
  * Foundational Projects

  * [Micrometer](https://micrometer.io)
  * [Reactor](https://projectreactor.io)
  * Development Tools

  * [Spring Tools](/tools)
  * [Spring Initializr](https://start.spring.io/)



Resources

  * [Blog](/blog)
  * [Release Calendar](/projects#release-calendar)
  * [Version Mappings](/projects/generations)
  * [Release Highlights](/projects/release-highlights)
  * [Security Advisories](/security)
  * GitHub Orgs

  * [Spring Projects](https://github.com/spring-projects)
  * [Spring Cloud](https://github.com/spring-cloud)



Community

  * [Overview](/community)
  * [Events](/events)
  * [Authors](/authors)



Enterprise

  * [Overview](https://enterprise.spring.io/)
  * [Long-term Support](https://enterprise.spring.io/lts-releases)
  * [Automated Upgrades](https://enterprise.spring.io/spring-application-advisor)
  * [Governance and Compliance](https://enterprise.spring.io/enterprise-extensions)
  * [Modern App Development](https://enterprise.spring.io/enterprise-components)



[](/ "Logo")

# [Spring Blog](/blog)

RSS feeds

[ All Posts](/blog.atom)

[ Engineering](/blog/category/engineering.atom)

[ Releases](/blog/category/releases.atom)

[ News & Events](/blog/category/news.atom)

# Prompt Caching Support in Spring AI with Anthropic Claude

[Engineering](/blog/category/engineering) | [Soby Chacko](/authors/sobychacko) |  October 27, 2025 |  12 min read | [...](/blog/2025/10/27/spring-ai-anthropic-prompt-caching-blog#disqus_thread)

Large language model API costs can accumulate quickly when applications repeatedly send the same prompt content. A typical scenario: you're building a document analyzer that includes a 3,000-token document in every request. Five questions about that document means processing 15,000 tokens of identical content at full price.

Anthropic's prompt caching addresses this by allowing you to reuse previously processed prompt segments. Spring AI provides comprehensive support through strategic caching patterns that handle cache breakpoint placement and management automatically.

In this blog post, we explain how prompt caching works, when to use it, and how Spring AI simplifies its implementation for you.

## Understanding Prompt Caching

Prompt caching allows you to mark portions of your prompt for reuse across multiple API requests. When you enable it, Anthropic caches the specified content and charges reduced rates for cached segments in subsequent requests.

### How It Works

The cache operates on exact prefix matching. Consider this sequence:
    
    
    Request 1: [System Prompt] + [User: "Question 1"]
               └─ Cached ──┘
    
    Request 2: [System Prompt] + [User: "Question 2"]
               └─ Cache Hit ─┘    (Only this part incurs full cost)
    

The system generates cache keys using cryptographic hashes of prompt content up to designated cache control points. Only requests with identical content achieve cache hits—even a single character change creates a new cache entry.
    
    
    Request 1: "You are a helpful assistant."    → Cache created
    Request 2: "You are a helpful assistant."    → Cache hit
    Request 3: "You are a helpful assistant "    → Cache miss (extra space)
    Request 4: "You are a Helpful assistant."    → Cache miss (capitalization)
    

On a cache miss, the system processes content at standard rates and creates a new cache entry. This is why maintaining consistent prompt templates becomes important for effective caching.

**Performance Impact:** Beyond cost savings, Anthropic reports latency reductions of up to 85% for long prompts. In their [announcement](https://www.anthropic.com/news/prompt-caching), a 100K-token book example showed response time dropping from 11.5s to 2.4s with caching enabled. Note that actual latency improvements depend on how much content you're caching and your cache hit rate.

**Cache Lifecycle:** Entries refresh on each use within the TTL window (5 minutes default, 1 hour optional). After TTL expiration, the next request creates a new cache entry.

### Cost Structure

Pricing varies significantly by model tier:

Model | Base Input | Cache Write | Cache Read | Savings  
---|---|---|---|---  
**Claude Sonnet 4.5** | $3/MTok | $3.75/MTok (+25%) | $0.30/MTok | **90%**  
**Claude Sonnet 4** | $3/MTok | $3.75/MTok (+25%) | $0.30/MTok | **90%**  
**Claude Opus 4.1** | $15/MTok | $18.75/MTok (+25%) | $1.50/MTok | **90%**  
**Claude Opus 4** | $15/MTok | $18.75/MTok (+25%) | $1.50/MTok | **90%**  
**Claude Haiku 4.5** | $1/MTok | $1.25/MTok (+25%) | $0.10/MTok | **90%**  
**Claude Haiku 3.5** | $0.80/MTok | $1/MTok (+25%) | $0.08/MTok | **90%**  
**Claude Haiku 3** | $0.25/MTok | $0.30/MTok (+25%) | $0.03/MTok | **90%**  
  
_All code examples in this blog use Claude Sonnet 4.5 pricing unless otherwise specified._

For more on pricing, see - [Anthropic pricing on prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching#pricing)

**Example calculation (Claude 3.5 Sonnet, 5,000 tokens):**

  * First request: 5,000 tokens × $3.75/M = **$0.01875** (cache write)
  * Subsequent requests: 5,000 tokens × $0.30/M = **$0.00150** (cache read)
  * **Savings:** 90% reduction on cached content
  * **Breakeven:** 2nd request (the 25% write premium is recovered immediately)



### Requirements and Limitations

**Minimum token thresholds vary by model:**

Model | Minimum Cacheable Tokens  
---|---  
Claude Sonnet 4.5, , Claude Sonnet 4, Claude Opus 4.1, Claude Opus 4 | 1,024  
Claude Haiku 3.5, Claude Haiku 3 | 2,048  
Claude Haiku 4.5 | **4,096**  
  
Prompts below these thresholds cannot be cached, even when you mark them with cache control directives. Note that Claude Haiku 4.5 requires significantly more tokens (4,096) compared to other models.

For more on this, see [Anthropic's cacheable prompt length limitations](https://docs.claude.com/en/docs/build-with-claude/prompt-caching#cache-limitations).

**Additional constraints:**

  * Maximum 4 cache breakpoints per request
  * Cache TTL: 5 minutes default, 1 hour optional (at higher write cost)
  * Cache refreshes on each use within TTL window
  * Cache entries become available after the first response begins (not available for concurrent parallel requests)



## Cache Hierarchy and Cascade Invalidation

Anthropic processes request components in a specific order, and this order determines how cache invalidation works.
    
    
    ┌─────────────────────────────────────────┐
    │  Request Processing Order:              │
    │                                         │
    │  1. Tools                               │
    │     ↓                                   │
    │  2. System Message                      │
    │     ↓                                   │
    │  3. Message History                     │
    └─────────────────────────────────────────┘
    

Changes cascade downward through this hierarchy:
    
    
    ┌──────────────────────────────────────────────────────┐
    │  Cascade Invalidation:                               │
    │                                                      │
    │  Change Tools    → Invalidates: Tools, System, Msgs  │
    │  Change System   → Invalidates: System, Msgs         │
    │  Change Messages → Invalidates: Msgs only            │
    └──────────────────────────────────────────────────────┘
    

Understanding this behavior is essential when choosing your caching strategy. Changes to components higher in the hierarchy invalidate all downstream caches, which directly impacts your cache hit rates.

## Spring AI Cache Strategies

Rather than requiring you to manually place cache breakpoints (which can be error-prone and tedious), Spring AI provides five strategic patterns through the `AnthropicCacheStrategy` enum. Each strategy handles cache control directive placement automatically while respecting Anthropic's 4-breakpoint limit.

### Strategy Overview

Strategy | Breakpoints | Cached Content | Typical Use Case  
---|---|---|---  
`NONE` | 0 | Nothing | One-off requests, testing  
`SYSTEM_ONLY` | 1 | System message | Stable system prompts, <20 tools  
`TOOLS_ONLY` | 1 | Tool definitions | Large tools, dynamic system prompts  
`SYSTEM_AND_TOOLS` | 2 | Tools + System | 20+ tools, both stable  
`CONVERSATION_HISTORY` | 1-4 | Full conversation | Multi-turn conversations  
  
Let's take a look at each strategy with practical examples.

## SYSTEM_ONLY Strategy

This strategy caches the system message content. Since tools appear before the system message in Anthropic's request hierarchy (Tools → System → Messages), they automatically become part of the cache prefix when you place a cache breakpoint on the system message.

**Important:** Changing any tool definition will invalidate the system cache due to the cache hierarchy.
    
    
    String systemPrompt = """
        You are an expert software architect specializing in distributed systems.
        You have deep knowledge of microservices, event-driven architecture, and cloud-native patterns.
        When analyzing systems, consider scalability, resilience, and maintainability.
        [... additional context ...]
        """;
    
    ChatResponse response = chatModel.call(
        new Prompt(
            List.of(
                new SystemMessage(systemPrompt),
                new UserMessage("What is microservices architecture?")
            ),
            AnthropicChatOptions.builder()
                .model(AnthropicApi.ChatModel.CLAUDE_3_5_SONNET)
                .cacheOptions(AnthropicCacheOptions.builder()
                    .strategy(AnthropicCacheStrategy.SYSTEM_ONLY)
                    .build())
                .maxTokens(500)
                .build()
        )
    );
    
    // Access cache metrics
    AnthropicApi.Usage usage = (AnthropicApi.Usage) response.getMetadata()
    		.getUsage().getNativeUsage();
    
    if (usage != null) {
    	System.out.println("Cache creation: " + usage.cacheCreationInputTokens());
    	System.out.println("Cache read: " + usage.cacheReadInputTokens());
    }
    

On the first request, `cacheCreationInputTokens` will be greater than zero and `cacheReadInputTokens` will be zero. Subsequent requests with the same system prompt will show zero for `cacheCreationInputTokens` and a positive value for `cacheReadInputTokens`. This is how you can verify that caching is working as expected in your application.

Use this strategy when your system prompt is large (meeting the minimum token threshold) and stable, but user questions vary.

## TOOLS_ONLY Strategy

This strategy caches tool definitions while processing the system message fresh on each request. The use case becomes clear in multi-tenant scenarios where tools are shared but system prompts need customization.

Consider a SaaS application serving multiple organizations:
    
    
    @Service
    public class MultiTenantAIService {
    
        private final List<FunctionCallback> sharedTools = List.of(
            weatherTool,       // 500 tokens
            calendarTool,      // 800 tokens
            emailTool,         // 700 tokens
            analyticsTool,     // 600 tokens
            reportingTool,     // 900 tokens
            // ... 15 more tools totaling 5,000+ tokens
        );
    
        public String handleRequest(String tenantId, String userQuery) {
            TenantConfig config = tenantRepository.findById(tenantId);
    
            // Each tenant requires a unique system prompt
            String systemPrompt = """
                You are %s's AI assistant.
                Company values: [custom data]
                Brand voice: [custom data]
                Compliance requirements: [custom data]
                """;
    
            ChatResponse response = chatModel.call(
                new Prompt(
                    List.of(
                        new SystemMessage(systemPrompt),
                        new UserMessage(userQuery)
                    ),
                    AnthropicChatOptions.builder()
                        .model(AnthropicApi.ChatModel.CLAUDE_3_5_SONNET)
                        .cacheOptions(AnthropicCacheOptions.builder()
                            .strategy(AnthropicCacheStrategy.TOOLS_ONLY)
                            .build())
                        .toolCallbacks(sharedTools)
                        .maxTokens(800)
                        .build()
                )
            );
    
            return response.getResult().getOutput().getText();
        }
    }
    

Here's what happens:

  * **First request (any tenant)** : Tools cached at 1.25x cost
  * **All subsequent requests (all tenants)** : Tools read from cache at 0.1x cost
  * **Each tenant's system prompt** : Processed fresh at 1.0x cost (by design)



All tenants share the same cached tool definitions, while each receives their customized system prompt. For the 5,000-token tool set, this means paying `$0.01875` once to create the cache, then `$0.0015` per request for cache reads—regardless of which tenant is making the request.

## SYSTEM_AND_TOOLS Strategy

This strategy creates two independent cache breakpoints: one for tools (breakpoint 1) and one for the system message (breakpoint 2). This separation matters when you have more than 20 tools or when you need deterministic caching of both components.

The key advantage: changing the system message does not invalidate the tool cache.
    
    
    ChatResponse response = chatModel.call(
        new Prompt(
            List.of(
                new SystemMessage(systemPrompt),
                new UserMessage(userQuery)
            ),
            AnthropicChatOptions.builder()
                .model(AnthropicApi.ChatModel.CLAUDE_3_5_SONNET)
                .cacheOptions(AnthropicCacheOptions.builder()
                    .strategy(AnthropicCacheStrategy.SYSTEM_AND_TOOLS)
                    .build())
                .toolCallbacks(toolCallbacks)
                .maxTokens(500)
                .build()
        )
    );
    

The cache keys work as follows:

  * **Breakpoint 1 (tools)** : `hash(tools)`
  * **Breakpoint 2 (system)** : `hash(tools + system)`



**Cascade Behavior:**

  * **System changes only:** Tool cache (breakpoint 1) remains valid, system cache (breakpoint 2) invalidated
  * **Tool changes:** Both caches invalidated



This makes SYSTEM_AND_TOOLS ideal when your system prompt changes more frequently than your tools, allowing efficient reuse of the tool cache.

## CONVERSATION_HISTORY Strategy

For multi-turn conversations, this strategy caches the entire conversation history incrementally. Spring AI places a cache breakpoint on the last user message in the conversation history. This is particularly useful when building conversational AI applications (such as chatbots, virtual assistants, and customer support systems).
    
    
    ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultSystem("You are a personalized career counselor with 20 years of experience...")
        .defaultAdvisors(MessageChatMemoryAdvisor.builder(chatMemory)
            .conversationId(conversationId)
            .build())
        .build();
    
    String response = chatClient.prompt()
        .user("What career advice would you give me based on our conversation?")
        .options(AnthropicChatOptions.builder()
            .model(AnthropicApi.ChatModel.CLAUDE_3_5_SONNET)
            .cacheOptions(AnthropicCacheOptions.builder()
                .strategy(AnthropicCacheStrategy.CONVERSATION_HISTORY)
                .build())
            .maxTokens(500)
            .build())
        .call()
        .content();
    

The cache grows incrementally as the conversation progresses:
    
    
    Turn 1: Cache [U1]
    Turn 2: Reuse [U1], cache [U1 + A1 + U2]
    Turn 3: Reuse [U1 + A1 + U2], cache [U1 + A1 + U2 + A2 + U3]
    Turn 4: Reuse [U1 + A1 + U2 + A2 + U3], cache [full history + U4]
    

By turn 10 in a conversation, you might have 20,000 tokens of history cached, paying just 10% of the normal cost for that context on each subsequent turn.

**Critical Requirement: Tool and System Stability**

When using `CONVERSATION_HISTORY`, both tools and system prompts must remain stable throughout the conversation. Changes to either invalidate the entire conversation cache.

## Example: Partnership Agreement Analysis

Here's a complete example showing cache efficiency for multi-question document analysis:
    
    
    @Service
    public class ContractAnalyzer {
    
        private final AnthropicChatModel chatModel;
        private final PdfExtractor pdfExtractor;
    
        public AnalysisReport analyzeAgreement(String agreementPdf) {
            // Extract text from PDF (typically 2,000-5,000 tokens)
            String agreementText = pdfExtractor.extract(agreementPdf);
    
            String systemPrompt = """
                You are an expert business analyst specializing in partnership agreements.
                Analyze the following partnership agreement and provide insights about
                collaboration terms, value propositions, and strategic opportunities.
    
                AGREEMENT:
                %s
                """.formatted(agreementText);
    
            String[] questions = {
                "What are the key collaboration opportunities outlined in this agreement?",
                "Summarize the revenue sharing and financial arrangements.",
                "What intellectual property rights and licensing terms are defined?",
                "Identify the strategic value propositions for both parties.",
                "What are the performance milestones and success metrics?"
            };
    
            AnalysisReport report = new AnalysisReport();
    
            AnthropicChatOptions options = AnthropicChatOptions.builder()
                .model(AnthropicApi.ChatModel.CLAUDE_3_5_SONNET)
                .cacheOptions(AnthropicCacheOptions.builder()
                    .strategy(AnthropicCacheStrategy.SYSTEM_ONLY)
                    .messageTypeTtl(MessageType.SYSTEM, AnthropicCacheTtl.ONE_HOUR)
                    .build())
                .maxTokens(1000)
                .build();
    
            for (int i = 0; i < questions.length; i++) {
                ChatResponse response = chatModel.call(
                    new Prompt(
                        List.of(
                            new SystemMessage(systemPrompt),
                            new UserMessage(questions[i])
                        ),
                        options
                    )
                );
    
                String answer = response.getResult().getOutput().getText();
                report.addSection(questions[i], answer);
    
                // Log cache performance
                AnthropicApi.Usage usage = (AnthropicApi.Usage)
                    response.getMetadata().getUsage().getNativeUsage();
    
                if (usage != null) {
                    if (i == 0) {
                        logger.info("First question - Cache created: {} tokens",
                            usage.cacheCreationInputTokens());
                    } else {
                        logger.info("Question {} - Cache read: {} tokens",
                            i + 1, usage.cacheReadInputTokens());
                    }
                }
            }
    
            return report;
        }
    }
    

With a 3,500-token system prompt (agreement + instructions) using Claude 3.5 Sonnet:

  * **First question** : 3,500 tokens × $3.75/M = $0.013 (cache write)
  * **Questions 2-5** : 3,500 tokens × $0.30/M = $0.001 (cache read) each
  * **Total cached content cost** : $0.013 + (4 × $0.001) = $0.017
  * **Without caching** : 5 × (3,500 tokens × $3.00/M) = $0.053



This represents a 68% cost reduction for the cached system prompt portion. The actual total savings will be lower when you factor in the user question tokens and output tokens (which are not cached), but the reduction becomes more significant with more questions or larger documents.

## Getting Started

**Note:** Prompt caching support is available in Spring AI `1.1.0` and later. Try it with the latest `1.1.0-SNAPSHOT` version.

Add the Spring AI Anthropic starter to your project:
    
    
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-anthropic-spring-boot-starter</artifactId>
    </dependency>
    

Configure your API key in your application properties:
    
    
    spring.ai.anthropic.api-key=${ANTHROPIC_API_KEY}
    

Inject and use in your application:
    
    
    @Autowired
    private AnthropicChatModel chatModel;
    
    // Start using caching strategies immediately
    

## Advanced Configuration Options

### Extended Cache TTL

The default cache TTL is 5 minutes. For scenarios where requests arrive less frequently, you can configure a 1-hour cache:
    
    
    AnthropicChatOptions options = AnthropicChatOptions.builder()
        .model(AnthropicApi.ChatModel.CLAUDE_3_5_SONNET)
        .cacheOptions(AnthropicCacheOptions.builder()
            .strategy(AnthropicCacheStrategy.SYSTEM_ONLY)
            .messageTypeTtl(MessageType.SYSTEM, AnthropicCacheTtl.ONE_HOUR)
            .build())
        .maxTokens(500)
        .build();
    

Spring AI automatically adds the required beta header (`anthropic-beta: extended-cache-ttl-2025-04-11`) when you configure 1-hour TTL.

**When to use each TTL:**

  * **5 minutes (default):** Real-time conversations, frequently updated content
  * **1 hour:** Infrequent requests (>5 min apart), stable reference materials, lower traffic



**Trade-off:** 1-hour cache writes cost **2x** vs 5-minute writes ($6/M vs $3.75/M for Claude 3.5 Sonnet). Evaluate your application's request patterns and stability requirements to determine which TTL makes sense.

### Content Length Filtering

You can set minimum content lengths per message type to optimize breakpoint usage:
    
    
    AnthropicCacheOptions cache = AnthropicCacheOptions.builder()
        .strategy(AnthropicCacheStrategy.CONVERSATION_HISTORY)
        .messageTypeMinContentLength(MessageType.SYSTEM, 1024)
        .messageTypeMinContentLength(MessageType.USER, 512)
        .messageTypeMinContentLength(MessageType.ASSISTANT, 512)
        .build();
    

For precise token counting, you can provide a custom length function:
    
    
    AnthropicCacheOptions cache = AnthropicCacheOptions.builder()
        .strategy(AnthropicCacheStrategy.CONVERSATION_HISTORY)
        .contentLengthFunction(text -> customTokenCounter.count(text))
        .build();
    

By default, Spring AI uses string length as a proxy for token count, but for production scenarios, you might want to consider injecting a proper token counter.

## Implementation Details

For those interested in internals, here's how Spring AI handles cache management:
    
    
    ┌─────────────────────────────────────────────────────────┐
    │  Request Flow:                                          │
    │                                                         │
    │  Application                                            │
    │      ↓                                                  │
    │  AnthropicChatModel                                     │
    │      ↓                                                  │
    │  CacheEligibilityResolver                               │
    │    (created from strategy)                              │
    │      ↓                                                  │
    │  For each component:                                    │
    │    - Check strategy eligibility                         │
    │    - Verify minimum content length                      │
    │    - Confirm breakpoint availability (<4)               │
    │    - Add cache_control if eligible                      │
    │      ↓                                                  │
    │  Build request with cache markers                       │
    │      ↓                                                  │
    │  Add beta headers if needed (1h TTL)                    │
    │      ↓                                                  │
    │  Anthropic API                                          │
    │      ↓                                                  │
    │  Response with cache metrics                            │
    └─────────────────────────────────────────────────────────┘
    

The `CacheEligibilityResolver` determines whether each message or tool qualifies for caching based on the chosen strategy, message type eligibility, content length requirements, and available breakpoints. The `CacheBreakpointTracker` enforces Anthropic's 4-breakpoint limit with thread-safe tracking per request.

For `CONVERSATION_HISTORY`, Spring AI uses aggregate eligibility checking—it considers the combined content of all message types (user, assistant, tool) within the last ~20 content blocks when determining cache eligibility. This prevents short user questions (such as "Tell me more") from blocking cache creation when there are substantial assistant responses in the conversation history.

## Practical Considerations

### When Caching Doesn't Help

Avoid caching when:

  * Content changes frequently (cache miss rate >50%)
  * Prompts are below minimum token thresholds for your model
  * Making one-off requests with no reuse patterns
  * Tools or system prompts change more often than content is reused



### Strategy Anti-Patterns

Avoid these common mistakes:

  * **Don't use SYSTEM_ONLY** if your system prompt changes frequently—you'll pay cache write costs without getting cache hits
  * **Don't use TOOLS_ONLY** if your tools change frequently—you'll pay cache write costs without getting cache hits. Note that SYSTEM_ONLY won't help either when tools change frequently, since tool changes invalidate the system cache
  * **Don't use CONVERSATION_HISTORY** if you can't guarantee tool and system stability—changes invalidate the entire conversation cache
  * **Don't use SYSTEM_AND_TOOLS** if you only have a few small tools (<20)—SYSTEM_ONLY's implicit caching is sufficient



### Streaming Support

Caching works seamlessly with both streaming and non-streaming responses. Cache metrics appear in the final response chunk when using streaming. There is no difference in cache behavior between the two modes.

## Conclusion

Prompt caching in Anthropic Claude provides significant cost and latency benefits for applications with reusable prompt content. Spring AI's strategic approach simplifies implementation by automatically handling cache breakpoint placement, breakpoint limits, and TTL configuration.

The five caching strategies cover common usage patterns, from simple system prompt caching to complex multi-turn conversations. For most applications, selecting the appropriate strategy based on content stability patterns is sufficient—Spring AI handles the implementation details.

For additional information, see the [Spring AI Anthropic documentation](https://docs.spring.io/spring-ai/reference/api/chat/anthropic-chat.html#_prompt_caching) and [Anthropic's prompt caching guide](https://docs.claude.com/en/docs/build-with-claude/prompt-caching).

## Get the Spring newsletter

Stay connected with the Spring newsletter

[Subscribe](https://go-vmware.broadcom.com/tnz-spring-newsletter-subscribe)

## Get ahead

VMware offers training and certification to turbo-charge your progress.

[Learn more](https://spring.academy/)

## Get support

Tanzu Spring offers support and binaries for OpenJDK™, Spring, and Apache Tomcat® in one simple subscription.

[Learn more](/support)

## Upcoming events

Check out all the upcoming events in the Spring community.

[View all](/events)

[Why Spring](/why-spring)

[Generative AI](/ai)

[Microservices](/microservices)

[Reactive](/reactive)

[Event Driven](/event-driven)

[Cloud](/cloud)

[Web Applications](/web-applications)

[Serverless](/serverless)

[Batch](/batch)

[Learn](/learn)

[Quickstart](/quickstart)

[Guides](/guides)

[Courses](https://spring.academy/courses)

[Get Certified](https://spring.academy/learning-path)

[Projects](/projects)

Resources

[Blog](/blog)

[Release Calendar](/projects#release-calendar)

[Version Mappings](/projects/generations)

[Release Highlights](/projects/release-highlights)

[Security Advisories](/security)

[Community](/community)

[Events](/events)

[Authors](/authors)

[Enterprise](https://enterprise.spring.io/)

[Long-term Support](https://enterprise.spring.io/lts-releases)

[Automated Upgrades](https://enterprise.spring.io/spring-application-advisor)

[Governance and Compliance](https://enterprise.spring.io/enterprise-extensions)

[Modern App Development](https://enterprise.spring.io/enterprise-components)

[Thank You](/thank-you)

Copyright © 2005 - 2026 Broadcom. All Rights Reserved. The term "Broadcom" refers to Broadcom Inc. and/or its subsidiaries.   
[Terms of Use](https://www.broadcom.com/company/legal/terms-of-use) • [Privacy](https://www.broadcom.com/company/legal/privacy) • [Trademark Guidelines](/trademarks)

Apache®, Apache Tomcat®, Apache Kafka®, Apache Cassandra™, and Apache Geode™ are trademarks or registered trademarks of the Apache Software Foundation in the United States and/or other countries. Java™, Java™ SE, Java™ EE, and OpenJDK™ are trademarks of Oracle and/or its affiliates. Kubernetes® is a registered trademark of the Linux Foundation in the United States and other countries. Linux® is the registered trademark of Linus Torvalds in the United States and other countries. Windows® and Microsoft® Azure are registered trademarks of Microsoft Corporation. “AWS” and “Amazon Web Services” are trademarks or registered trademarks of Amazon.com Inc. or its affiliates. All other trademarks and copyrights are property of their respective owners and are only mentioned for informative purposes. Other names may be trademarks of their respective owners.

[](https://www.youtube.com/user/SpringSourceDev)[](https://github.com/spring-projects)[](https://x.com/springcentral)[](https://bsky.app/profile/spring.io)
