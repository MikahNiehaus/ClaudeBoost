<!-- Source: https://www.anthropic.com/news/token-saving-updates | Tier: A | Topic: prompt-caching | Fetched: 2026-06-23 -->

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
  2. Token-saving updates on the Anthropic API




Explore here

  * Ask questions about this page
  * Copy as markdown



# Token-saving updates on the Anthropic API

Claude now offers cache-aware rate limits, simplified prompt caching, and token-efficient tool use to help developers increase throughput and cut costs.

  * Category

[Product announcements](https://claude.com/blog/category/announcements)

  * Product

Claude Platform

  * Date

March 13, 2025

  * Reading time

5

min

  * Share

Copy link

https://claude.com/blog/token-saving-updates




We've made several updates to the Anthropic API that let developers significantly increase throughput and reduce token usage with Claude 3.7 Sonnet. These include: cache-aware rate limits, simpler prompt caching, and token-efficient tool use.

Together, these updates will help you process more requests within your existing rate limits and reduce costs with minimal code changes.

### Increase your throughput with prompt caching

[Prompt caching](https://www.anthropic.com/news/prompt-caching) allows developers to store and reuse frequently accessed context between API calls. This lets Claude maintain knowledge of large documents, instructions, or examples without sending the same information with each request—reducing costs by up to 90% and latency by up to 85% for long prompts. We’ve released two improvements to prompt caching for Claude 3.7 Sonnet that work together to help you scale more efficiently.

#### Cache-aware rate limits

Prompt cache read tokens no longer count against your Input Tokens Per Minute (ITPM) limit for Claude 3.7 Sonnet on the Anthropic API. This means you can now optimize your prompt caching usage to increase throughput and get more out of your existing ITPM rate limits. Your Output Tokens Per Minute (OTPM) rate limit remains the same.

This makes Claude 3.7 Sonnet particularly powerful for applications that benefit from extensive context while requiring high throughput, such as:

  * Document analysis platforms that need to maintain large knowledge bases in context
  * Coding assistants that reference extensive codebases
  * Customer support systems that leverage detailed product documentation



[Cache-aware ITPM limits](https://docs.anthropic.com/en/api/rate-limits#rate-limits) are available for Claude 3.7 Sonnet on the Anthropic API.

#### Simpler cache management

We've updated prompt caching to be easier to use. Now, when you set a cache breakpoint, Claude automatically reads from your longest previously cached prefix.

You no longer need to manually track and specify which cached segments to use as we automatically identify and use the most relevant cached content. This not only reduces your workload, but also frees up more tokens.

This feature is available on the Anthropic API and Google Cloud’s Vertex AI. Explore our [documentation](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) to learn more.

### Token-efficient tool use

Claude is already capable of interacting with external client-side tools and functions. This update lets you equip Claude with your own custom tools to perform tasks—like extracting structured data from unstructured text or automating simple tasks via APIs. Claude 3.7 Sonnet now supports [calling tools in a token-efficient manner](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/token-efficient-tool-use), reducing output token consumption by up to 70%. On average, early users have seen a reduction of 14%.

To use this feature, simply add the beta header****_token-efficient-tools-2025-02-19_ to a tool use request with Claude 3.7 Sonnet. If you are using the SDK, ensure that you are using the beta SDK with _anthropic.beta.messages_.

Token-efficient tool use is currently available in beta on the Anthropic API, Amazon Bedrock, and Google Cloud’s Vertex AI.

#### Text_editor tool

We also introduced a new _text_editor_ tool, designed for applications where users collaborate with Claude on documents. With the new tool, Claude can make targeted edits to specific portions of text within source code, documents, or research reports. This reduces token consumption and latency, all while increasing accuracy.

Developers can easily implement this tool in their applications by providing it in their API requests and handling the tool use responses. 

The _text_editor_ tool is available on the Anthropic API, Amazon Bedrock, and Google Cloud's Vertex AI. See our [documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/text-editor-tool) to get started.

### Customer Spotlight: Cognition

Early users, like Cognition, are leveraging these updates to improve token efficiency and response quality. Cognition is an applied AI lab and the maker of Devin, a collaborative AI teammate that helps ambitious engineering teams achieve more.

“Prompt caching allows us to provide more context about the codebase to get higher quality results while reducing cost and latency. With cache-aware ITPM limits, we are further optimizing our prompt caching usage to increase our throughput and get more out of our existing rate limits,” said Scott Wu, Co-founder and CEO at Cognition.

### Get started now

These features are available today to all Anthropic API customers. You can implement them immediately with minimal code changes:

  1. **Take advantage of cache-aware rate limits:** Use [prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) with Claude 3.7 Sonnet.
  2. **Implement token-efficient tool use:** Add the beta header _token-efficient-tools-2025-02-19_ to your requests and start saving tokens.
  3. **Try the _text_editor_ tool:** Integrate it into your applications for more efficient document editing workflows.



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

Jun 17, 2026

### Secure access to the Claude Platform with Workload Identity Federation

Product announcements

Secure access to the Claude Platform with Workload Identity FederationSecure access to the Claude Platform with Workload Identity Federation

[Secure access to the Claude Platform with Workload Identity Federation](/blog/workload-identity-federation)Secure access to the Claude Platform with Workload Identity Federation

May 7, 2026

### Collaborate with Claude across Excel, PowerPoint, Word and Outlook 

Product announcements

Collaborate with Claude across Excel, PowerPoint, Word and Outlook Collaborate with Claude across Excel, PowerPoint, Word and Outlook 

[Collaborate with Claude across Excel, PowerPoint, Word and Outlook ](/blog/collaborate-with-claude-across-excel-powerpoint-word-and-outlook)Collaborate with Claude across Excel, PowerPoint, Word and Outlook 

May 19, 2026

### New in Claude Managed Agents: dreaming, outcomes, and multiagent orchestration

Product announcements

New in Claude Managed Agents: dreaming, outcomes, and multiagent orchestrationNew in Claude Managed Agents: dreaming, outcomes, and multiagent orchestration

[New in Claude Managed Agents: dreaming, outcomes, and multiagent orchestration](/blog/new-in-claude-managed-agents)New in Claude Managed Agents: dreaming, outcomes, and multiagent orchestration

Apr 30, 2026

### Claude Security is now in public beta

Product announcements

Claude Security is now in public betaClaude Security is now in public beta

[Claude Security is now in public beta](/blog/claude-security-public-beta)Claude Security is now in public beta

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

[English (US)](/blog/token-saving-updates)

[日本語 (Japan)](/ja)

[Deutsch (Germany)](/de)

[Français (France)](/fr)

[한국어 (South Korea)](/ko)

[Italian (Italy)](/it)

[](/blog-product/claude-platform)

Claude Platform

[](/blog-usecases/coding)

Coding
