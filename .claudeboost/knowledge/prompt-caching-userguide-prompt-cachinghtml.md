<!-- Source: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html | Tier: A | Topic: prompt-caching | Fetched: 2026-06-23 -->

[View a markdown version of this page](prompt-caching.md)

[](/pdfs/bedrock/latest/userguide/bedrock-ug.pdf#prompt-caching "Open PDF")

[Documentation](/index.html)[Amazon Bedrock](/bedrock/index.html)[User Guide](what-is-bedrock.html)

How it worksSupported models, Regions, and limitsSimplified Cache Management for Claude ModelsHow to effectively use prompt cachingGetting started

# Prompt caching for faster model inference

Prompt caching is an optional feature that you can use with supported models on Amazon Bedrock to reduce inference response latency and input token costs. By adding portions of your context to a cache, the model can use the cache to skip recomputation of inputs, allowing Bedrock to share in the compute savings and lower your response latencies.

Prompt caching can help when you have workloads with long and repeated contexts that are frequently reused for multiple queries. For example, if you have a chatbot where users can upload documents and ask questions about them, it can be time consuming for the model to process the document every time the user provides input. With prompt caching, you can cache the document so that future queries containing the document don't need to reprocess it.

When using prompt caching, you're charged at a reduced rate for tokens read from cache. Depending on the model, tokens written to cache may be charged at a rate that is higher than that of uncached input tokens. Any tokens not read from or written to cache, are charged at the standard input token rate for that model. For more information, see the [Amazon Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/).

## How it works

If you opt to use prompt caching, Amazon Bedrock creates a cache composed of _cache checkpoints_. These are markers that define the contiguous subsection of your prompt that you wish to cache (often referred to as a prompt prefix). These prompt prefixes should be static between requests, alterations to the prompt prefix in subsequent requests will result in cache misses.

Cache checkpoints have a minimum and maximum number of tokens, dependent on the specific model you're using. You can only create a cache checkpoint if your total prompt prefix meets the minimum number of tokens. For example, Claude 3.7 Sonnet requires at least 1,024 tokens per cache checkpoint, while Claude Opus 4.5, Claude Opus 4.6, Claude Haiku 4.5, and Claude Sonnet 4.5 require at least 4,096 tokens per cache checkpoint. That means that for a model with a 1,024-token minimum, your first cache checkpoint can be defined after 1,024 tokens and your second cache checkpoint can be defined after 2,048 tokens. If you try to add a cache checkpoint before meeting the minimum number of tokens, your inference will still succeed, but your prefix will not be cached. The cache has a Time To Live (TTL), which resets with each successful cache hit. During this period, the context in the cache is preserved. If no cache hits occur within the TTL window, your cache expires. Most models support a 5-minute TTL, while Claude Opus 4.5, Claude Haiku 4.5, and Claude Sonnet 4.5 also support an extended 1-hour TTL option.

You can use prompt caching anytime you get model inference in Amazon Bedrock for supported models. Prompt caching is supported by the following Amazon Bedrock features:

**Converse and ConverseStream APIs**
    

You can carry on a conversation with a model where you specify cache checkpoints in your prompts.

**InvokeModel and InvokeModelWithResponseStream APIs**
    

You can submit single prompt requests in which you enable prompt caching and specify your cache checkpoints.

**Prompt Caching with Cross-region Inference**
    

Prompt caching can be used in conjunction with cross region inference. Cross-region inference automatically selects the optimal AWS Region within your geography to serve your inference request, thereby maximizing available resources and model availability. At times of high demand, these optimizations may lead to increased cache writes.

**Amazon Bedrock Prompt management**
    

When you [create](./prompt-management-create.html) or [modify](./prompt-management-modify.html) a prompt, you can choose to enable prompt caching. Depending on the model, you can cache system prompts, system instructions, and messages (user and assistant). You can also choose to disable prompt caching.

###### Note

Prompt caching is only supported for on-demand inference endpoints. It is not supported with the batch inference API.

The APIs provide you with the most flexibility and granular control over the prompt cache. You can set an individual cache checkpoint within your prompts. You can add to the cache by creating more cache checkpoints, up to the maximum number of cache checkpoints allowed for the specific model. For more information, see Supported models, Regions, and limits.

## Supported models, Regions, and limits

Prompt caching is available in all AWS Regions where the supported models are available. To check model availability by Region, see [Regional availability by models](./models-region-compatibility.html).

The following table lists the supported models along with their token minimums, maximum number of cache checkpoints, and fields that allow cache checkpoints.

To see which models support prompt caching, please refer to [Models at a glance](./model-cards.html) and then choose the model you are interested in. The following table shows prompt caching for models that are not present in models-at-a-glance.

Model name | Model ID | Release Type | Minimum number of tokens per cache checkpoint | Maximum number of cache checkpoints per request | Supported TTL | Fields that accept prompt cache checkpoints  
---|---|---|---|---|---|---  
Claude Opus 4.5 | anthropic.claude-opus-4-5-20251101-v1:0 | Generally Available | 4,096 | 4 | 5 minutes, 1 hour | `system`, `messages`, and `tools`  
Claude Opus 4.6 | anthropic.claude-opus-4-6-v1 | Generally Available | 4,096 | 4 | 5 minutes | `system`, `messages`, and `tools`  
Claude Sonnet 4.5 | anthropic.claude-sonnet-4-5-20250929-v1:0 | Generally Available | 4,096 | 4 | 5 minutes, 1 hour | `system`, `messages`, and `tools`  
Claude Sonnet 4.6 | anthropic.claude-sonnet-4-6 | Generally Available | 1,024 | 4 | 5 minutes | `system`, `messages`, and `tools`  
Claude Haiku 4.5 | anthropic.claude-haiku-4-5-20251001-v1:0 | Generally Available | 4,096 | 4 | 5 minutes, 1 hour | `system`, `messages`, and `tools`  
Claude Opus 4 | anthropic.claude-opus-4-20250514-v1:0 | Generally Available | 1,024 | 4 | 5 minutes | `system`, `messages`, and `tools`  
Claude 3.7 Sonnet | anthropic.claude-3-7-sonnet-20250219-v1:0 | Generally Available | 1,024 | 4 | 5 minutes | `system`, `messages`, and `tools`  
Claude 3.5 Sonnet v2 | anthropic.claude-3-5-sonnet-20241022-v2:0 | Preview | 1,024 | 4 | 5 minutes | `system`, `messages`, and `tools`  
  
To use the 1-hour TTL option with supported models (Claude Opus 4.5, Claude Haiku 4.5, and Claude Sonnet 4.5), specify the `ttl` field in your cache checkpoint. In the Converse API, add `"ttl": "1h"` to your `cachePoint` object. In the InvokeModel API for Claude models, add `"ttl": "1h"` to your `cache_control` object. If no `ttl` value is provided, the default 5-minute caching behavior applies. The 1-hour TTL is useful for longer-running sessions or batch processing scenarios where you want to maintain the cache across extended periods.

Amazon Nova offers automatic prompt caching for all text prompts, including `User` and `System` messages. This mechanism can provide latency benefits when prompts begin with repetitive parts, even without explicit configuration. However, to unlock cost savings and ensure more consistent performance benefits, we recommend opting in to **Explicit Prompt Caching**.

## Simplified Cache Management for Claude Models

For Claude models, Amazon Bedrock offers a simplified approach to cache management that reduces the complexity of manually placing cache checkpoints. Instead of requiring you to specify exact cache checkpoint locations, you can use automatic cache management with a single breakpoint at the end of your static content.

When you enable simplified cache management, the system automatically checks for cache hits at previous content block boundaries, looking back up to approximately 20 content blocks from your specified breakpoint. This allows the model to find the longest matching prefix from your cache without requiring you to predict the optimal checkpoint locations. To use this, place a single cache checkpoint at the end of your static content, before any dynamic or variable content. The system will automatically find the best cache match.

For more granular control, you can still use multiple cache checkpoints (up to 4 for Claude models) to specify exact cache boundaries. You should use multipled cache checkpoints if you are caching sections that change at different frequencies or want more control over exactly what gets cached.

###### Important

The automatic prefix checking only looks back approximately 20 content blocks from your cache checkpoint. If your static content extends beyond this range, consider using multiple cache checkpoints or restructuring your prompt to place the most frequently reused content within this range.

## How to effectively use prompt caching

If you have prompts that are used at a regular cadence (i.e., system prompts that are used more frequently than every 5 minutes), continue to use the 5-minute cache, since this will continue to be refreshed at no additional charge.

The 1-hour cache is best used in the following scenarios:

  * When you have prompts that are likely used less frequently than 5 minutes, but more frequently than every hour. For example, when an agentic side-agent will take longer than 5 minutes, or when storing a long chat conversation with a user and you generally expect that user may not respond in the next 5 minutes.

  * When latency is important and your follow-up prompts may be sent beyond 5 minutes.

  * When you want to improve your rate limit use, since cache hits are not deducted against your rate limit.




You can use both 1-hour and 5-minute cache controls in the same request, but with an important constraint: Cache entries with longer TTL must appear before shorter TTLs (i.e., a 1-hour cache entry must appear before any 5-minute cache entries).

## Getting started

The following sections show you a brief overview of how to use the prompt caching feature for each method of interacting with models through Amazon Bedrock.

The [Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html) API provides advanced and flexible options for implementing prompt caching in multi-turn conversations. For more information about the prompt requirements for each model, see the preceding section Supported models, Regions, and limits.

**Example request**

The following examples show a cache checkpoint set in the `messages`, `system`, or `tools` fields of a request to the Converse API. You can place checkpoints in any of these locations for a given request. For example, if sending a request to the Claude 3.5 Sonnet v2 model, you could place two cache checkpoints in `messages`, one cache checkpoint in `system`, and one in `tools`. For more detailed information and examples of structuring and sending Converse API requests, see [Inference using Converse API](./conversation-inference.html).

###### Important

Cache checkpoints are processed in this order: `tools` → `system` → `messages`. The minimum cache size is evaluated against the cumulative tokens across all three sections combined, not each section individually. Because the sections are chained, changing content in an earlier section invalidates the cache for later sections (for example, modifying `tools` invalidates the `system` and `messages` caches). For best cache hit rates, place stable content (`tools`, `system`) before variable content (`messages`), and place cache checkpoints after the stable content.

Specify the desired ttl value as below, when ttl value not specified the default behavior of 5 minutes caching applies.
    
    
    "cachePoint" : {
        "type": "default",
        "ttl" : "5m | 1h"
    }
    

messages checkpoints
    

In this example, the first `image` field provides an image to the model, and the second `text` field asks the model to analyze the image. As long as the number of tokens preceding the `cachePoint` in the `content` object meets the minimum token count for the model, a cache checkpoint is created.
    
    
    ...
    "messages": [
       {
            "role": "user",
            "content": [
                {
                    "image": {
                        "bytes": "asfb14tscve..."
                    }
                },
                {
                    "text": "What's in this image?"
                },
                {
                    "cachePoint": {
                        "type": "default"
                    }
                }
          ]
      }
    ]
    ...

system checkpoints
    

In this example, you provide your system prompt in the `text` field. Additionally, you can add a `cachePoint` field to cache the system prompt.
    
    
    ...
      "system": [ 
        {
            "text": "You are an app that creates play lists for a radio station that plays rock and pop music. Only return song names and the artist. "
        },
        {
            "cachePoint": {
                "type": "default"
            }
        }
      ],
    ...

tools checkpoints
    

In this example, you provide your tool definition in the `toolSpec` field. (Alternatively, you can call a tool that you’ve previously defined. For more information, see [Use a tool to complete an Amazon Bedrock model response](./tool-use.html).) Afterward, you can add a `cachePoint` field to cache the tool.
    
    
    ...
    toolConfig={
        "tools": [
            {
                "toolSpec": {
                    "name": "top_song",
                    "description": "Get the most popular song played on a radio station.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "sign": {
                                    "type": "string",
                                    "description": "The call sign for the radio station for which you want the most popular song. Example calls signs are WZPZ and WKRP."
                                }
                            },
                            "required": [
                                "sign"
                            ]
                        }
                    }
                }
            },
            {
                    "cachePoint": {
                        "type": "default"
                    }
            }
        ]
    }
    ...

The model response from the Converse API includes three new fields that are specific to prompt caching. The `cacheReadInputTokens` and `cacheWriteInputTokens` values tell you how many tokens were read from the cache and how many tokens were written to the cache because of your previous request. The `cacheDetails` values tell you the ttl used for the number of token written to cache. These are values that you're charged for by Amazon Bedrock, at a rate that's lower than the cost of full model inference.

###### Important

When prompt caching is enabled, the `inputTokens` field represents only the non-cached input tokens (tokens that were not read from or written to the cache). To calculate the total input tokens sent in a request, use the following formula:

`total input tokens = inputTokens + cacheReadInputTokens + cacheWriteInputTokens`

Prompt caching is enabled by default when you call the [InvokeModel](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html) API. You can set cache checkpoints at any point in your request body, similar to the previous example for the Converse API.

Anthropic Claude
    

The following example shows how to structure the body of your InvokeModel request for the Anthropic Claude 3.5 Sonnet v2 model. Note that the exact format and fields of the body for InvokeModel requests may vary depending on the model you choose. To see the format and content of the request and response bodies for different models, see [Inference request parameters and response fields for foundation models](./model-parameters.html).

Specify the desired ttl value as below, when ttl value not specified the default behavior of 5 minutes caching applies.
    
    
    "cache_control" : {
        "type": "ephemeral",
        "ttl" : "5m | 1h"
    }
    
    
    
    body={
            "anthropic_version": "bedrock-2023-05-31",
            "system":"Reply concisely",
            "messages": [
                {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe the best way to learn programming."
                    },
                    {
                        "type": "text",
                        "text": "Add additional context here for the prompt that meets the minimum token requirement for your chosen model.",
                        "cache_control": {
                            "type": "ephemeral"
                        }
                    }
                ]
                }
            ],
            "max_tokens": 2048,
            "temperature": 0.5,
            "top_p": 0.8,
            "stop_sequences": [
                "stop"
            ],
            "top_k": 250
    }

Amazon Nova
    

The following example shows how to structure the body of your InvokeModel request for the Amazon Nova model. Note that the exact format and fields of the body for InvokeModel requests may vary depending on the model you choose. To see the format and content of the request and response bodies for different models, see [Inference request parameters and response fields for foundation models](./model-parameters.html).
    
    
    {
        "system": [{
            "text": "Reply Concisely"
        }],
        "messages": [{
            "role": "user",
            "content": [{
                "text": "Describe the best way to learn programming"
            },
            {
                "text": "Add additional context here for the prompt that meets the minimum token requirement for your chosen model.",
                "cachePoint": {
                    "type": "default"
                }
            }]
        }],
        "inferenceConfig": {
            "maxTokens": 300,
            "topP": 0.1,
            "topK": 20,
            "temperature": 0.3
        }
    }

For more information about sending an InvokeModel request, see [Submit a single prompt with InvokeModel](./inference-invoke.html).

In a chat playground in the Amazon Bedrock console, you can turn on the prompt caching option, and Amazon Bedrock automatically creates cache checkpoints for you.

Follow the instructions in [Generate responses in the console using playgrounds](./playgrounds.html) to get started with prompting in an Amazon Bedrock playground. For supported models, prompt caching is automatically turned on in the playground. However, if it’s not, then do the following to turn on prompt caching:

  1. Open the **Configurations** menu.

  2. Turn on the **Prompt caching** toggle.

  3. Run your prompts.




After your combined input and model responses reach the minimum required number of tokens for a checkpoint (which varies by model), Amazon Bedrock automatically creates the first cache checkpoint for you. As you continue chatting, each subsequent reach of the minimum number of tokens creates a new checkpoint, up to the maximum number of checkpoints allowed for the model. You can view your cache checkpoints at any time by choosing **View cache checkpoints** next to the **Prompt caching** toggle, as shown in the following screenshot.

You can view how many tokens are being read from and written to the cache due to each interaction with the model by viewing the **Caching metrics** pop-up ( ) in the playground responses.

If you turn off the prompt caching toggle while in the middle of a conversation, you can continue chatting with the model.

**Javascript is disabled or is unavailable in your browser.**

To use the Amazon Web Services Documentation, Javascript must be enabled. Please refer to your browser's Help pages for instructions.

[Document Conventions](/general/latest/gr/docconventions.html)

Request a quota increase

Best practices

Did this page help you? - Yes

Thanks for letting us know we're doing a good job!

If you've got a moment, please tell us what we did right so we can do more of it.

Did this page help you? - No

Thanks for letting us know this page needs work. We're sorry we let you down.

If you've got a moment, please tell us how we can make the documentation better.
