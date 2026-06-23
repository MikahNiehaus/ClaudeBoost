<!-- Source: https://dev.to/stklen/how-to-save-90-on-claude-api-costs-3-official-techniques-3d4n | Tier: B | Topic: batch-api-cost | Fetched: 2026-06-23 -->

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

[ Share to X ](https://twitter.com/intent/tweet?text=%22%F0%9F%92%B0%20How%20to%20Save%2090%25%20on%20Claude%20API%20Costs%3A%203%20Official%20Techniques%22%20by%20TK%20Lin%20%23DEVCommunity%20https%3A%2F%2Fdev.to%2Fstklen%2Fhow-to-save-90-on-claude-api-costs-3-official-techniques-3d4n) [ Share to LinkedIn ](https://www.linkedin.com/shareArticle?mini=true&url=https%3A%2F%2Fdev.to%2Fstklen%2Fhow-to-save-90-on-claude-api-costs-3-official-techniques-3d4n&title=%F0%9F%92%B0%20How%20to%20Save%2090%25%20on%20Claude%20API%20Costs%3A%203%20Official%20Techniques&summary=%F0%9F%92%B0%20How%20to%20Save%2090%25%20on%20Claude%20API%20Costs%3A%203%20Official%20Techniques%20You%27re%20Missing%20%20%20Did%20you%20know...&source=DEV%20Community) [ Share to Facebook ](https://www.facebook.com/sharer.php?u=https%3A%2F%2Fdev.to%2Fstklen%2Fhow-to-save-90-on-claude-api-costs-3-official-techniques-3d4n) [ Share to Mastodon ](https://s2f.kytta.dev/?text=https%3A%2F%2Fdev.to%2Fstklen%2Fhow-to-save-90-on-claude-api-costs-3-official-techniques-3d4n)

Share Post via... [Report Abuse](/report-abuse)

[](/stklen)

[TK Lin](/stklen)

Posted on Jan 27

#  💰 How to Save 90% on Claude API Costs: 3 Official Techniques 

[#claude](/t/claude) [#anthropic](/t/anthropic) [#costoptimization](/t/costoptimization) [#ai](/t/ai)

#  💰 How to Save 90% on Claude API Costs: 3 Official Techniques You're Missing 

**Did you know most developers are overpaying for Claude API by 50-90%?**

I discovered this the hard way. Running an AI-powered animal recognition system for 28 cats and dogs at Washin Village (a rural sanctuary in Japan), I was burning through API credits faster than my cats go through treats.

Then I found three official Anthropic techniques that slashed my costs dramatically. No hacks. No workarounds. Just features hiding in plain sight.

Let me show you how to keep more money in your pocket.

* * *

##  📊 The Cost Problem 

Here's what typical Claude API usage looks like:

Model | Input (per 1M tokens) | Output (per 1M tokens)  
---|---|---  
Claude Sonnet 4 | $3.00 | $15.00  
Claude Opus 4 | $15.00 | $75.00  
  
For production apps processing thousands of requests daily, these costs add up **fast**.

But Anthropic offers three official ways to dramatically reduce these costs. Let's dive in.

* * *

##  🥇 Technique 1: Batch API (50% Off) 

**Best for:** Non-urgent tasks, bulk processing, overnight jobs

The Batch API lets you submit up to **100,000 requests** at once and get results within 24 hours—at **half the price**.

###  How It Works 
    
    
    import anthropic
    import json
    
    client = anthropic.Anthropic()
    
    # Create a batch request
    batch = client.batches.create(
        requests=[
            {
                "custom_id": "request-001",
                "params": {
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "user", "content": "Summarize this article..."}
                    ]
                }
            },
            {
                "custom_id": "request-002",
                "params": {
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "user", "content": "Translate this text..."}
                    ]
                }
            }
            # Add up to 100,000 requests!
        ]
    )
    
    print(f"Batch ID: {batch.id}")
    print(f"Status: {batch.processing_status}")
    

Enter fullscreen mode Exit fullscreen mode

###  Check Batch Status 
    
    
    # Poll for completion
    batch_status = client.batches.retrieve(batch.id)
    
    if batch_status.processing_status == "ended":
        # Download results
        results = client.batches.results(batch.id)
        for result in results:
            print(f"{result.custom_id}: {result.result.message.content}")
    

Enter fullscreen mode Exit fullscreen mode

###  When to Use Batch API 

Use Case | Savings  
---|---  
Nightly data processing | 50%  
Bulk content generation | 50%  
Dataset labeling | 50%  
Non-real-time analysis | 50%  
  
**Pro tip:** Queue up your batch jobs during off-peak hours for fastest processing.

* * *

##  🥈 Technique 2: Prompt Caching (Up to 90% Off!) 

**Best for:** Repetitive prompts, long system prompts, RAG applications

This is the **biggest money saver**. If you're sending the same system prompt or context repeatedly, you're literally throwing money away.

###  The Magic Numbers 

Token Type | Cost Reduction  
---|---  
Cache Write | +25% (one-time)  
Cache Read | **-90%**  
  
After the initial cache write, every subsequent read costs just **10% of normal input pricing**.

###  Implementation 
    
    
    import anthropic
    
    client = anthropic.Anthropic()
    
    # Your long system prompt (must be 1,024+ tokens for Sonnet)
    SYSTEM_PROMPT = """
    You are an expert veterinary AI assistant specializing in cat and dog health.
    You have extensive knowledge about:
    - 50+ cat breeds and their specific health concerns
    - 80+ dog breeds and their characteristics
    - Common symptoms and when to seek emergency care
    - Nutrition guidelines for different life stages
    - Behavioral analysis and training tips
    ... [imagine 2000+ more tokens of context]
    """
    
    # First request: Creates the cache (costs +25%)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}  # <-- The magic flag!
            }
        ],
        messages=[
            {"role": "user", "content": "My cat is sneezing. Should I worry?"}
        ]
    )
    
    # Check cache performance
    print(f"Cache created: {response.usage.cache_creation_input_tokens} tokens")
    print(f"Cache read: {response.usage.cache_read_input_tokens} tokens")
    

Enter fullscreen mode Exit fullscreen mode

###  Subsequent Requests (90% Savings!) 
    
    
    # All future requests with the same system prompt
    # automatically use the cache at 90% discount!
    
    response2 = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,  # Same prompt = cache hit!
                "cache_control": {"type": "ephemeral"}
            }
        ],
        messages=[
            {"role": "user", "content": "What vaccines does my puppy need?"}
        ]
    )
    
    # This request costs 90% less for the system prompt!
    

Enter fullscreen mode Exit fullscreen mode

###  Cache Requirements 

Model | Minimum Tokens  
---|---  
Claude Sonnet 4 | 1,024 tokens  
Claude Opus 4 | 2,048 tokens  
Claude Haiku | 2,048 tokens  
  
**Important:** Cache expires after 5 minutes of inactivity. Keep it warm with periodic requests if needed.

* * *

##  🥉 Technique 3: Extended Thinking (~80% Off on "Thinking") 

**Best for:** Complex reasoning, math problems, coding tasks

Claude's Extended Thinking feature lets the model "think" before responding. The brilliant part? **Thinking tokens are heavily discounted**.

###  Cost Comparison 

Token Type | Sonnet Price (per 1M)  
---|---  
Regular Output | $15.00  
Thinking Tokens | $3.00 (same as input!)  
  
That's an **80% discount** on the reasoning process!

###  Implementation 
    
    
    import anthropic
    
    client = anthropic.Anthropic()
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000  # Allow up to 10K thinking tokens
        },
        messages=[
            {
                "role": "user",
                "content": "Analyze this codebase and suggest optimizations..."
            }
        ]
    )
    
    # Access the thinking process
    for block in response.content:
        if block.type == "thinking":
            print(f"💭 Thinking: {block.thinking[:200]}...")
        elif block.type == "text":
            print(f"📝 Response: {block.text}")
    

Enter fullscreen mode Exit fullscreen mode

###  When Extended Thinking Shines 

Task | Benefit  
---|---  
Complex debugging | Better accuracy at lower cost  
Mathematical proofs | Step-by-step reasoning  
Architecture decisions | Thorough analysis  
Code refactoring | Comprehensive review  
  
* * *

##  🚀 Combining Techniques: The Ultimate Savings Stack 

Here's where it gets exciting. **You can combine these techniques!**

###  Batch + Caching = 95% Savings 
    
    
    # Batch API (50% off) + Prompt Caching (90% off on cached portion)
    # Result: Massive savings on bulk processing with repeated context
    
    batch_requests = []
    
    for i, user_query in enumerate(thousands_of_queries):
        batch_requests.append({
            "custom_id": f"query-{i}",
            "params": {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": [
                    {
                        "type": "text",
                        "text": LONG_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                "messages": [
                    {"role": "user", "content": user_query}
                ]
            }
        })
    
    # Submit batch with caching enabled
    batch = client.batches.create(requests=batch_requests)
    

Enter fullscreen mode Exit fullscreen mode

###  Real-World Savings Calculator 

Scenario | Standard Cost | With Optimizations | Savings  
---|---|---|---  
10K requests, 2K system prompt | $60 | $9 | **85%**  
Batch processing 100K items | $500 | $50 | **90%**  
RAG with 5K context | $150 | $22.50 | **85%**  
  
* * *

##  📋 Quick Reference Cheat Sheet 
    
    
    ┌─────────────────────────────────────────────────────────┐
    │           CLAUDE API COST OPTIMIZATION                  │
    ├─────────────────────────────────────────────────────────┤
    │                                                         │
    │  🕐 Can wait 24 hours?                                  │
    │     └─→ Use BATCH API (50% off)                        │
    │                                                         │
    │  🔄 Repeating same prompt?                              │
    │     └─→ Use PROMPT CACHING (90% off reads)             │
    │                                                         │
    │  🧠 Need complex reasoning?                             │
    │     └─→ Use EXTENDED THINKING (80% off thinking)       │
    │                                                         │
    │  💡 Combine them all for maximum savings!               │
    │                                                         │
    └─────────────────────────────────────────────────────────┘
    

Enter fullscreen mode Exit fullscreen mode

* * *

##  🎯 Action Items 

  1. **Audit your current usage** \- Check which requests could be batched
  2. **Identify repeated prompts** \- System prompts over 1K tokens are caching candidates
  3. **Enable extended thinking** \- For complex tasks, let Claude think cheaply
  4. **Monitor your savings** \- Track `cache_read_input_tokens` in responses



* * *

##  🐾 Our Story 

At [Washin Village](https://washinmura.jp), we run AI-powered recognition for **28 cats and dogs** living in our rural Japanese sanctuary. These cost optimization techniques help us:

  * Process thousands of animal photos daily
  * Generate personalized content for each pet
  * Keep our AI services running sustainably



Every yen saved goes back to caring for our furry friends!

* * *

##  📚 Resources 

  * [Anthropic Batch API Documentation](https://docs.anthropic.com/en/docs/build-with-claude/batch-processing)
  * [Prompt Caching Guide](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
  * [Extended Thinking Documentation](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)



* * *

##  💬 Let's Connect 

Found this helpful? I'd love to hear how much you've saved!

  * Drop a comment below with your results
  * Share your own optimization tips
  * Follow for more AI cost-saving strategies



* * *

Made with 💰 by **Washin Village** (washinmura.jp) - Where 28 cats & dogs inspire better AI

* * *

#  claude #anthropic #api #costoptimization #llm #ai #machinelearning #python #developers #programming #tech #savings #tips #claudeapi #aitools #devops #backend #startup #buildinpublic #opensource 

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

[ TK Lin  ](/stklen)

Follow

  * Joined 

Jan 22, 2026




###  More from [TK Lin](/stklen)

[ 112 Battle-Tested Claude Code Skills — Every Bug Fix That Cost Me Hours So It Won't Cost You  #claudecode #ai #programming #webdev ](/stklen/112-battle-tested-claude-code-skills-every-bug-fix-that-cost-me-hours-so-it-wont-cost-you-252e) [ 実戦で鍛えた 112 の Claude Code Skills — 何時間もかけたバグ修正を、あなたは繰り返さなくていい  #claudecode #ai #programming #webdev ](/stklen/shi-zhan-deduan-eta-112-no-claude-code-skills-he-shi-jian-mokaketabaguxiu-zheng-wo-anatahazao-rifan-sanakuteii-19ei) [ 112 個實戰淬煉的 Claude Code Skills — 每個讓我踩坑數小時的 Bug 修復，讓你不必再踩  #claudecode #ai #programming #webdev ](/stklen/112-ge-shi-zhan-cui-lian-de-claude-code-skills-mei-ge-rang-wo-cai-keng-shu-xiao-shi-de-bug-xiu-fu-rang-ni-bu-bi-zai-cai-2dcn)

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
* [ DEV Challenges ](/challenges)
* [ DEV++ ](/++)
* [ Videos ](/videos)
* [ DEV Education Tracks ](/deved)
* [ DEV Help ](/help)
* [ Advertise on DEV ](/advertise)
* [ Organization Accounts ](/organizations)
* [ DEV Showcase ](/showcase)
* [ About ](/about)
* [ Contact ](/contact)
* [ Free Postgres Database ](/free-postgres-database-tier)
* [ DEV Shop ](https://shop.forem.com/)
* [ MLH ](https://mlh.io/)



* [ Code of Conduct ](/code-of-conduct)
* [ Privacy Policy ](/privacy)
* [ Terms of Use ](/terms)

Built on [Forem](https://www.forem.com) — the [open source](https://dev.to/t/opensource) software that powers [DEV](https://dev.to) and other inclusive communities.

Made with love and [Ruby on Rails](https://dev.to/t/rails). DEV Community (C) 2016 - 2026.

We're a place where coders share, stay up-to-date and grow their careers. 

[ Log in ](https://dev.to/enter?signup_subforem=1) [ Create account ](https://dev.to/enter?signup_subforem=1&state=new-user)
