<!-- Source: https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything | Tier: A | Topic: prompt-caching | Fetched: 2026-06-23 -->

[](https://claude.com)

  * Meet Claude

Products

    * [Claude](/product/overview)
    * [Claude Code](/product/claude-code)
    * [Claude Cowork](/product/cowork)
    * [@Claude](/product/tag)

Features

    * [Claude for Chrome](/claude-for-chrome)
    * [Claude for Microsoft 365](/claude-for-microsoft-365)
    * [Skills](/skills)

Claude apps built for

    * [Design](/product/design)
    * [Security](/product/claude-security)

Models

    * [Mythos](https://www.anthropic.com/claude/mythos)
    * [Fable](https://www.anthropic.com/claude/fable)
    * [Opus](https://www.anthropic.com/claude/opus)
    * [Sonnet](https://www.anthropic.com/claude/sonnet)
    * [Haiku](https://www.anthropic.com/claude/haiku)

  * Platform

    * [Overview](/platform/api)
    * [Developer docs](https://platform.claude.com/docs)
    * [Pricing](http://claude.com/pricing#api)

    * [Console login](https://platform.claude.com/)

  * Solutions

Use cases

    * [AI agents](/solutions/agents)
    * [Coding](/solutions/coding)

Company size

    * [Startups](/programs/startups)
    * [Enterprise](/solutions/enterprise)

Departments

    * [Legal](/solutions/legal)
    * [Security](/solutions/security)

Industries

    * [Customer support](/solutions/customer-support)
    * [Education](/solutions/education)
    * [Financial services](/solutions/financial-services)
    * [Government](/solutions/government)
    * [Healthcare](/solutions/healthcare)
    * [Life sciences](/solutions/life-sciences)
    * [Nonprofits](/solutions/nonprofits)

  * Pricing

    * [Overview](/pricing)
    * [API](/pricing#api)

  * Resources

Insights

    * [Blog](/blog)
    * [Customer stories](/customers)
    * [Anthropic news](https://www.anthropic.com/news)

Learn

    * [Anthropic Academy](https://www.anthropic.com/learn)
    * [Courses](/resources/courses)
    * [Tutorials](/resources/tutorials)
    * [Use cases](/resources/use-cases)

Tools

    * [Connectors](/connectors)
    * [Plugins](/plugins)

Connect

    * [Events](https://www.anthropic.com/events)
    * [Community](/community)

  * [Login](https://claude.ai/login)


  * Contact sales

[Contact sales](/contact-sales)Contact sales

  * Try Claude

[Try Claude](https://claude.ai/)Try Claude

  * Contact sales

[Contact sales](/contact-sales)Contact sales

  * Try Claude

[Try Claude](https://claude.ai/)Try Claude




  * Contact sales

[Contact sales](/contact-sales)Contact sales

  * Try Claude

[Try Claude](https://claude.ai/)Try Claude

  * Contact sales

[Contact sales](/contact-sales)Contact sales

  * Try Claude

[Try Claude](https://claude.ai/)Try Claude




  * Meet Claude

Products

    * [Claude](/product/overview)
    * [Claude Code](/product/claude-code)
    * [Claude Cowork](/product/cowork)
    * [@Claude](/product/tag)

Features

    * [Claude for Chrome](/claude-for-chrome)
    * [Claude for Microsoft 365](/claude-for-microsoft-365)
    * [Skills](/skills)

Claude apps built for

    * [Design](/product/design)
    * [Security](/product/claude-security)

Models

    * [Mythos](https://www.anthropic.com/claude/mythos)
    * [Fable](https://www.anthropic.com/claude/fable)
    * [Opus](https://www.anthropic.com/claude/opus)
    * [Sonnet](https://www.anthropic.com/claude/sonnet)
    * [Haiku](https://www.anthropic.com/claude/haiku)

  * Platform

    * [Overview](/platform/api)
    * [Developer docs](https://platform.claude.com/docs)
    * [Pricing](http://claude.com/pricing#api)

    * [Console login](https://platform.claude.com/)

  * Solutions

Use cases

    * [AI agents](/solutions/agents)
    * [Coding](/solutions/coding)

Company size

    * [Startups](/programs/startups)
    * [Enterprise](/solutions/enterprise)

Departments

    * [Legal](/solutions/legal)
    * [Security](/solutions/security)

Industries

    * [Customer support](/solutions/customer-support)
    * [Education](/solutions/education)
    * [Financial services](/solutions/financial-services)
    * [Government](/solutions/government)
    * [Healthcare](/solutions/healthcare)
    * [Life sciences](/solutions/life-sciences)
    * [Nonprofits](/solutions/nonprofits)

  * Pricing

    * [Overview](/pricing)
    * [API](/pricing#api)

  * Resources

Insights

    * [Blog](/blog)
    * [Customer stories](/customers)
    * [Anthropic news](https://www.anthropic.com/news)

Learn

    * [Anthropic Academy](https://www.anthropic.com/learn)
    * [Courses](/resources/courses)
    * [Tutorials](/resources/tutorials)
    * [Use cases](/resources/use-cases)

Tools

    * [Connectors](/connectors)
    * [Plugins](/plugins)

Connect

    * [Events](https://www.anthropic.com/events)
    * [Community](/community)

  * [Login](https://claude.ai/login)



  * Contact sales

[Contact sales](/contact-sales)Contact sales

  * Try Claude

[Try Claude](https://claude.ai/)Try Claude

  * Contact sales

[Contact sales](/contact-sales)Contact sales

  * Try Claude

[Try Claude](https://claude.ai/)Try Claude




  1. Blog

[Blog](/blog)

/
  2. Lessons from building Claude Code: Prompt caching is everything




Explore here

  * Ask questions about this page
  * Copy as markdown



# Lessons from building Claude Code: Prompt caching is everything

We share best practices for optimizing prompt caching in Claude Code, including how to most effectively structure your prompt, use tools, and layer on compaction.

  * Category

[Claude Code](https://claude.com/blog/category/claude-code)

  * Product

Claude Code

  * Date

April 30, 2026

  * Reading time

5

min

  * Share

Copy link

https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything




It is often said in engineering that "cache rules everything around me", and the same rule holds for agents.

Long running agentic products like Claude Code are made feasible by [**prompt caching** ](https://x.com/RLanceMartin/status/2024573404888911886)which allows us to reuse computation from previous roundtrips and significantly decrease latency and cost.

At Claude Code, we build our entire harness around prompt caching. A high prompt cache hit rate decreases costs and helps us create more generous rate limits for our subscription plans, so we run alerts on our prompt cache hit rate and declare SEVs if they're too low.

These are the (often unintuitive) lessons we've learned from optimizing prompt caching at scale.

## **Lay out your prompt for caching**

Claude Code's system prompt is organized so the stable pieces stay cached and only the conversation itself grows turn by turn.

Prompt caching works by prefix matching—the API caches everything from the start of the request up to each `cache_control `breakpoint. This means the order you put things in matters enormously, you want as many of your requests to share a prefix as possible.

The best way to do this is static content first, dynamic content last. For Claude Code this looks like:

  1. **Static system prompt** & Tools (globally cached)
  2. **CLAUDE.md** (cached within a project)
  3. **Session context** (cached within a session)
  4. **Conversation messages**



This way we maximize how many sessions share cache hits.

But this approach can be surprisingly fragile. We’ve broken this ordering before for a variety of reasons, including: putting an in-depth timestamp in the static system prompt, shuffling tool order definitions non-deterministically, and updating parameters of tools (e.g., what agents the Agent tool can call).

## **Use messages for updates**

There may be times when the information you put in your prompt becomes out of date, for example if you have the time or if the user changes a file. It may be tempting to update the prompt, but that would result in a cache miss and could end up being quite expensive for the user.

Consider if you can pass in this information via messages in the agent’s next turn instead. In Claude Code, we add a <system-reminder> tag in the next user message or tool result with the updated information for the model, which helps preserve the cache.

## **Don 't change models mid-session**

Prompt caches are unique to models and this can make the math of prompt caching quite unintuitive.

For example, if you're 100k tokens into a conversation with Opus and want to ask a question that is fairly easy to answer, it would actually be more expensive to switch to Haiku than to have Opus answer, because we would need to rebuild the prompt cache for Haiku.

If you need to switch models, the best way to do it is with subagents; extending the above example, you could deploy a subagent that prompts Opus to prepare a "hand-off" message to another model on the task that it needs to get done. We do this often with the Claude Code’s Explore agents, which use Haiku.

## **Never add or remove tools mid-session**

Changing the tool set in the middle of a conversation is one of the most common ways people break prompt caching. It seems intuitive—you should only give the model tools you think it needs right now. But because tools are part of the cached prefix, adding or removing a tool invalidates the cache for the entire conversation.

**Using Plan Mode to design around the cache**

[Plan Mode](https://code.claude.com/docs/en/common-workflows) is a great example of designing features around caching constraints. The intuitive approach would be: when the user enters plan mode, swap out the tool set to only include read-only tools, but that would break the cache.

Instead, we keep _all_ tools in the request at all times and use EnterPlanMode and ExitPlanMode as tools themselves. When the user toggles Plan Mode on, the agent gets a system message explaining that it's in Plan Mode and what the instructions are: explore the codebase, don't edit files, and call ExitPlanMode when the plan is complete. The tool definitions never change.

This has a bonus benefit: because EnterPlanMode is a tool the model can call itself, it can autonomously enter plan mode when it detects a hard problem, without any cache break.

**Use tool search to defer instead of remove**

The same principle applies to our [tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool). Claude Code can have dozens of MCP tools loaded, and including all of them in every request would be expensive, but removing them mid-conversation would break the cache.

Our solution: `defer_loading`. Instead of removing tools, we send lightweight stubs ( just the tool name, with `defer_loading: true`) that the model can "discover" via tool search when needed. The full tool schemas are only loaded when the model selects them. This keeps the cached prefix stable because the same stubs are always present in the same order.

You can also use the [tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) through our API to simplify this.

## **Compacting without breaking the cache**

When the context window fills up, Claude Code forks a cached call to summarize the conversation, then resumes with the summary in place of the original messages.

[Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction) is what happens when you run out of the context window. We summarize the conversation so far and continue a new session with that summary.

Compaction interacts with prompt caching in ways that are easy to get wrong. To compact a conversation, you have to send the full conversation to the model so it can write a summary. The simplest way to do that is a separate API call with its own system prompt (something like "summarize this") and no tools attached, but that's exactly where the cost trap is. Prompt caching only applies when a request's prefix matches what's already cached, byte for byte, from the start. Your main conversation is cached under one system prompt and tool set; the summarization call uses a different system prompt and no tools, so the prefixes diverge at the very first token and none of the cache applies. You end up paying the full, uncached input rate for the entire conversation you're sending in — and the longer the conversation (i.e., the more you need compaction in the first place), the more expensive that one call becomes.

**The solution: cache-safe forking**

When we run compaction, we use the _exact same_ system prompt, user context, system context, and tool definitions as the parent conversation. We prepend the parent's conversation messages, then append the compaction prompt as a new user message at the end.

From the API's perspective, this request looks nearly identical to the parent's last request—same prefix, same tools, same history—so the cached prefix is reused. The only new tokens are the compaction prompt itself.

This does mean however that we need to save a "compaction buffer" so that we have enough room in the context window to include the compact message and the summary output tokens.

Compaction is tricky but luckily, you don't need to learn these lessons yourself—based on our learnings from Claude Code we built[ compaction](https://platform.claude.com/docs/en/build-with-claude/compaction#prompt-caching) directly into the API, so you can apply these patterns in your own applications.

## **Lessons learned**

Here are a few patterns we’ve found useful for optimizing prompt caching when building an agent: 

  1. **Prompt caching is a prefix match.** Any change anywhere in the prefix invalidates everything after it. Design your entire system around this constraint. Get the ordering right and most of the caching works for free.
  2. **Use messages instead of system prompt changes**. You may be tempted to edit the system prompt to do things like entering plan mode, changing the date, etc. but it would actually be better to insert these into messages during the conversation.
  3. **Don 't change tools or models mid-conversation.** Use tools to model state transitions (like plan mode) rather than changing the tool set. Defer tool loading instead of removing tools.
  4. **Monitor your cache hit rate like you monitor uptime.** We alert on cache breaks and treat them as incidents. A few percentage points of cache miss rate can dramatically affect cost and latency.
  5. **Fork operations need to share the parent 's prefix.** If you need to run a side computation (compaction, summarization, skill execution), use identical cache-safe parameters so you get cache hits on the parent's prefix.



Claude Code is built around prompt caching from day one; for the best results when building an agent, we suggest you do, too. 

[ _Get started_](https://code.claude.com/docs/en/overview) _with Claude Code today._

_This article was written by Thariq Shihipar, a member of technical staff on the Claude Code team._

‍

No items found.

PrevPrev

0/5

NextNext

eBook

## 

FAQ

No items found.

## Related posts

Explore more product news and best practices for teams building with Claude.

Jun 24, 2026

### Agent identity in Claude Tag: a new access model for autonomous, team-wide AI

Claude Code

Agent identity in Claude Tag: a new access model for autonomous, team-wide AIAgent identity in Claude Tag: a new access model for autonomous, team-wide AI

[Agent identity in Claude Tag: a new access model for autonomous, team-wide AI](/blog/agent-identity-access-model)Agent identity in Claude Tag: a new access model for autonomous, team-wide AI

Jun 3, 2026

### Running an AI-native engineering org

Claude Code

Running an AI-native engineering orgRunning an AI-native engineering org

[Running an AI-native engineering org](/blog/running-an-ai-native-engineering-org)Running an AI-native engineering org

May 12, 2026

### How Anthropic's cybersecurity team built a threat detection platform with Claude Code

Claude Code

How Anthropic's cybersecurity team built a threat detection platform with Claude CodeHow Anthropic's cybersecurity team built a threat detection platform with Claude Code

[How Anthropic's cybersecurity team built a threat detection platform with Claude Code](/blog/how-anthropic-uses-claude-cybersecurity)How Anthropic's cybersecurity team built a threat detection platform with Claude Code

Apr 20, 2026

### Meet the winners of our Built with Opus 4.6 Claude Code hackathon 

Claude Code

Meet the winners of our Built with Opus 4.6 Claude Code hackathon Meet the winners of our Built with Opus 4.6 Claude Code hackathon 

[Meet the winners of our Built with Opus 4.6 Claude Code hackathon ](/blog/meet-the-winners-of-our-built-with-opus-4-6-claude-code-hackathon)Meet the winners of our Built with Opus 4.6 Claude Code hackathon 

## Transform how your organization operates with Claude

See pricing

[See pricing](https://claude.com/pricing#api)See pricing

Contact sales

[Contact sales](https://claude.com/contact-sales)Contact sales

Get the developer newsletter

Product updates, how-tos, community spotlights, and more. Delivered monthly to your inbox.

SubscribeSubscribe

Please provide your email address if you'd like to receive our monthly developer newsletter. You can unsubscribe at any time.

Thank you! You’re subscribed.

Sorry, there was a problem with your submission, please try again later.

[Homepage](https://claude.com)Homepage

NextNext

Thank you! Your submission has been received!

Oops! Something went wrong while submitting the form.

Write

Button TextButton Text

Learn

Button TextButton Text

Code

Button TextButton Text

Write

  * Help me develop a unique voice for an audience

Hi Claude! Could you help me develop a unique voice for an audience? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!

  * Improve my writing style

Hi Claude! Could you improve my writing style? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!

  * Brainstorm creative ideas

Hi Claude! Could you brainstorm creative ideas? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!




Learn

  * Explain a complex topic simply

Hi Claude! Could you explain a complex topic simply? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!

  * Help me make sense of these ideas

Hi Claude! Could you help me make sense of these ideas? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!

  * Prepare for an exam or interview

Hi Claude! Could you prepare for an exam or interview? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!




Code

  * Explain a programming concept

Hi Claude! Could you explain a programming concept? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!

  * Look over my code and give me tips

Hi Claude! Could you look over my code and give me tips? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!

  * Vibe code with me

Hi Claude! Could you vibe code with me? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to— like Google Drive, web search, etc.—if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can—an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!




More

  * Write case studies

This is another test

  * Write grant proposals

Hi Claude! Could you write grant proposals? If you need more information from me, ask me 1-2 key questions right away. If you think I should upload any documents that would help you do a better job, let me know. You can use the tools you have access to — like Google Drive, web search, etc. — if they’ll help you better accomplish this task. Do not use analysis tool. Please keep your responses friendly, brief and conversational.   
  
Please execute the task as soon as you can - an artifact would be great if it makes sense. If using an artifact, consider what kind of artifact (interactive, visual, checklist, etc.) might be most helpful for this specific task. Thanks for your help!

  * Write video scripts

this is a test




[Anthropic](https://www.anthropic.com/)Anthropic

© [year] Anthropic PBC

Products

  * Claude

[Claude](/product/overview)Claude

  * Claude Code

[Claude Code](/product/claude-code)Claude Code

  * Claude Code for Enterprise

[Claude Code for Enterprise](/product/claude-code/enterprise)Claude Code for Enterprise

  * Claude Cowork

[Claude Cowork](/product/cowork)Claude Cowork

  * @Claude

[@Claude](/product/tag)@Claude

  * Claude Design

[Claude Design](/product/design)Claude Design

  * Claude Security

[Claude Security](/product/claude-security)Claude Security

  * Download app

[Download app](/download)Download app

  * Pricing

[Pricing](/pricing)Pricing

  * Log in

[Log in](https://claude.ai/login)Log in




Features

  * Claude for Chrome

[Claude for Chrome](/claude-for-chrome)Claude for Chrome

  * Claude for Microsoft 365

[Claude for Microsoft 365](/claude-for-microsoft-365)Claude for Microsoft 365

  * Skills

[Skills](/skills)Skills




Models

  * Mythos

[Mythos](https://www.anthropic.com/claude/mythos)Mythos

  * Fable

[Fable](https://www.anthropic.com/claude/fable)Fable

  * Opus

[Opus](https://www.anthropic.com/claude/opus)Opus

  * Sonnet

[Sonnet](https://www.anthropic.com/claude/sonnet)Sonnet

  * Haiku

[Haiku](https://www.anthropic.com/claude/haiku)Haiku




Solutions

  * AI agents

[AI agents](/solutions/agents)AI agents

  * Code modernization

[Code modernization](/solutions/code-modernization)Code modernization

  * Coding

[Coding](/solutions/coding)Coding

  * Customer support

[Customer support](/solutions/customer-support)Customer support

  * Education

[Education](/solutions/education)Education

  * Enterprise

[Enterprise](/solutions/enterprise)Enterprise

  * Financial services

[Financial services](/solutions/financial-services)Financial services

  * Government

[Government](/solutions/government)Government

  * Healthcare

[Healthcare](/solutions/healthcare)Healthcare

  * Legal

[Legal](/solutions/legal)Legal

  * Life sciences

[Life sciences](/solutions/life-sciences)Life sciences

  * Nonprofits

[Nonprofits](/solutions/nonprofits)Nonprofits

  * Security

[Security](/solutions/security)Security

  * Small business

[Small business](/solutions/small-business)Small business

  * Startups

[Startups](/programs/startups)Startups




Claude Platform

  * Overview

[Overview](/platform/api)Overview

  * Developer docs

[Developer docs](https://platform.claude.com/docs)Developer docs

  * Pricing

[Pricing](https://claude.com/pricing#api)Pricing

  * Marketplace

[Marketplace](/platform/marketplace)Marketplace

  * Claude on AWS

[Claude on AWS](/partners/claude-on-aws)Claude on AWS

  * Google Cloud

[Google Cloud](/partners/google-cloud)Google Cloud

  * Microsoft Foundry

[Microsoft Foundry](/partners/microsoft-foundry)Microsoft Foundry

  * Regional compliance

[Regional compliance](/regional-compliance)Regional compliance

  * Console login

[Console login](https://platform.claude.com/)Console login




Resources

  * Blog

[Blog](/blog)Blog

  * Claude partner network

[Claude partner network](/partners)Claude partner network

  * Community

[Community](/community)Community

  * Connectors

[Connectors](/connectors)Connectors

  * Courses

[Courses](https://www.anthropic.com/learn)Courses

  * Customer stories

[Customer stories](/customers)Customer stories

  * Engineering at Anthropic

[Engineering at Anthropic](https://www.anthropic.com/engineering)Engineering at Anthropic

  * Events

[Events](https://www.anthropic.com/events)Events

  * Plugins

[Plugins](/plugins)Plugins

  * Powered by Claude

[Powered by Claude](/partners/powered-by-claude)Powered by Claude

  * Service partners

[Service partners](/partners/services)Service partners

  * Tutorials

[Tutorials](/resources/tutorials)Tutorials

  * Use cases

[Use cases](/resources/use-cases)Use cases




Company

  * Anthropic

[Anthropic](https://www.anthropic.com/)Anthropic

  * Careers

[Careers](https://www.anthropic.com/careers)Careers

  * Policy

[Policy](https://www.anthropic.com/policy)Policy

  * Economic Futures

[Economic Futures](https://www.anthropic.com/economic-futures)Economic Futures

  * Research

[Research](https://www.anthropic.com/research)Research

  * News

[News](https://www.anthropic.com/news)News

  * Policy on the AI Exponential

[Policy on the AI Exponential](https://www.anthropic.com/policy-on-the-ai-exponential)Policy on the AI Exponential

  * Responsible Scaling Policy

[Responsible Scaling Policy](https://www.anthropic.com/news/announcing-our-updated-responsible-scaling-policy)Responsible Scaling Policy

  * Security and compliance

[Security and compliance](https://trust.anthropic.com/)Security and compliance

  * Transparency

[Transparency](https://anthropic.com/transparency)Transparency




Help and security

  * Availability

[Availability](https://www.anthropic.com/supported-countries)Availability

  * Status

[Status](https://status.anthropic.com/)Status

  * Support center

[Support center](https://support.claude.com/en/)Support center




Terms and policies

  * Privacy choices

### Cookie settings

We use cookies to deliver and improve our services, analyze site usage, and if you agree, to customize or personalize your experience and market our services to you. You can read our Cookie Policy [here](https://www.anthropic.com/legal/cookies). 

Customize cookie settings Reject all cookies Accept all cookies

###### Necessary

Enables security and basic functionality.

Required

###### Analytics

Enables tracking of site performance.

Off

###### Marketing

Enables ads personalization and tracking.

Off

Save preferences 

  * Privacy policy

[Privacy policy](https://www.anthropic.com/legal/privacy)Privacy policy

  * Responsible disclosure policy

[Responsible disclosure policy](https://www.anthropic.com/responsible-disclosure-policy)Responsible disclosure policy

  * Terms of service: Commercial

[Terms of service: Commercial](https://www.anthropic.com/legal/commercial-terms)Terms of service: Commercial

  * Terms of service: Consumer

[Terms of service: Consumer](https://www.anthropic.com/legal/consumer-terms)Terms of service: Consumer

  * Usage policy

[Usage policy](https://www.anthropic.com/legal/aup)Usage policy




[x.com](https://x.com/claudeai)x.com

[LinkedIn](https://www.linkedin.com/showcase/claude/)LinkedIn

[YouTube](https://www.youtube.com/@anthropic-ai)YouTube

[Instagram](https://www.instagram.com/claudeai)Instagram

English (US)

[English (US)](/blog/lessons-from-building-claude-code-prompt-caching-is-everything)

[日本語 (Japan)](/ja)

[Deutsch (Germany)](/de)

[Français (France)](/fr)

[한국어 (South Korea)](/ko)

[Italian (Italy)](/it)

[](/blog-product/claude-code)

Claude Code

[](/blog-usecases/coding)

Coding
