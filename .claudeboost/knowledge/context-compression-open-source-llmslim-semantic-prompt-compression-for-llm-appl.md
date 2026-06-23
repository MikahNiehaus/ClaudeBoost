<!-- Source: https://discuss.huggingface.co/t/open-source-llmslim-semantic-prompt-compression-for-llm-applications/176833 | Tier: B | Topic: context-compression | Fetched: 2026-06-23 -->

[Hugging Face Forums](/)

#  [Open Source: llmslim – Semantic Prompt Compression for LLM Applications](/t/open-source-llmslim-semantic-prompt-compression-for-llm-applications/176833)

[ Show and Tell ](/c/show-and-tell/65)

[yvt94](https://discuss.huggingface.co/u/yvt94) June 15, 2026, 11:20pm  1

Published my first open-source Python package: llmslim.

It compresses prompts, chat histories, and RAG contexts using semantic chunking + extractive ranking before sending them to an LLM.

Example:

2847 tokens → 1138 tokens (60% reduction)

Looking for feedback from the HF community on:

  * Evaluation methodology
  * Embedding model choices
  * Retrieval + compression workflows
  * Long-context benchmarking



[GitHub - Thanatos9404/llmslim: Shrink LLM prompts by 40-70% while preserving meaning, semantic chunking + extractive summarization · GitHub](https://github.com/Thanatos9404/llmslim)

[PyPI](https://pypi.org/project/llmslim/)

### [llmslim](https://pypi.org/project/llmslim/)

Cut your LLM prompt size by 40-70% in one line of code -- semantic chunking + extractive summarization that preserves meaning, instructions, and key entities.

Contributions and criticism welcome.

[davidwarner234t](https://discuss.huggingface.co/u/davidwarner234t) June 22, 2026, 5:53am  2

Congrats! I’d also compare task accuracy before vs. after compression—token savings are great, but preserving output quality is what really matters. Looks promising.

###  Related topics 

Topic |  | Replies | Views | Activity  
---|---|---|---|---  
[[Tool] Open-source prompt compressor for LLMs – 22% avg savings with spaCy + rules](https://discuss.huggingface.co/t/tool-open-source-prompt-compressor-for-llms-22-avg-savings-with-spacy-rules/150483) [ Show and Tell ](/c/show-and-tell/65) |  2 |  242 |  May 19, 2026   
[I've built a LLM pre-processing toolbox and would love to hear your feedback](https://discuss.huggingface.co/t/ive-built-a-llm-pre-processing-toolbox-and-would-love-to-hear-your-feedback/165445) [ Models ](/c/models/13) |  1 |  69 |  August 3, 2025   
[RAG LLM Generating the Prompt also at the response](https://discuss.huggingface.co/t/rag-llm-generating-the-prompt-also-at-the-response/75221) [ Beginners ](/c/beginners/5) |  8 |  4478 |  September 25, 2024   
[LayerBrake — Full Transparency Release ⚡ I’ve been working on making LLMs more efficient. Here’s the honest update: Original Results (with optimized prompt): 61% fewer tokens ~2.6x faster 75-85% less VRAM Cache & Power Much cleaner answers](https://discuss.huggingface.co/t/layerbrake-full-transparency-release-i-ve-been-working-on-making-llms-more-efficient-here-s-the-honest-update-original-results-with-optimized-prompt-61-fewer-tokens-2-6x-faster-75-85-less-vram-cache-power-much-cleaner-answers/176442) [ Research ](/c/research/7) |  3 |  71 |  June 15, 2026   
[Llama-2 7B-hf repeats context of question directly from input prompt, cuts off with newlines](https://discuss.huggingface.co/t/llama-2-7b-hf-repeats-context-of-question-directly-from-input-prompt-cuts-off-with-newlines/48250) [ 🤗Transformers ](/c/transformers/9) |  16 |  29550 |  January 10, 2025   
  
  * [Home ](/)
  * [Categories ](/categories)
  * [Guidelines ](/guidelines)
  * [Terms of Service ](/tos)
  * [Privacy Policy ](/privacy)



Powered by [Discourse](https://www.discourse.org), best viewed with JavaScript enabled
