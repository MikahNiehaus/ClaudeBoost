<!-- Source: https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/ | Tier: B | Topic: rag-chunk-optimization | Fetched: 2026-06-23 -->

[ ](/ "Home") [DEVELOPER](/ "Home")

  * [Home](/ "Home")
  * [Blog](/blog "Blog")
  * [Forums](https://forums.developer.nvidia.com/ "Forums")
  * [Docs](https://docs.nvidia.com/ "Docs")
  * [Downloads](https://developer.nvidia.com/downloads "Downloads")
  * [Training](https://www.nvidia.com/en-us/training/ "Training")



  * __

  * [ Join ](https://developer.nvidia.com/login)
  * [ ](https://developer.nvidia.com/login)



[Technical Blog](https://developer.nvidia.com/blog)

[ Subscribe  ](https://developer.nvidia.com/email-signup)

Related Resources __

[Agentic AI / Generative AI](https://developer.nvidia.com/blog/category/generative-ai/)

English中文

# Finding the Best Chunking Strategy for Accurate AI Responses

Jun 18, 2025 

By [Steve Han](https://developer.nvidia.com/blog/author/sthan/ "Posts by Steve Han")

__

Like 

__Discuss (1)

  * [L](https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)
  * [T](https://twitter.com/intent/tweet?text=Finding+the+Best+Chunking+Strategy+for+Accurate+AI+Responses+%7C+NVIDIA+Technical+Blog+https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)
  * [F](https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)
  * [R](https://www.reddit.com/submit?url=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F&title=Finding+the+Best+Chunking+Strategy+for+Accurate+AI+Responses+%7C+NVIDIA+Technical+Blog)
  * [E](mailto:?subject=I'd like to share a link with you&body=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)



AI-Generated Summary

Like

Dislike

  * Page-level chunking achieved the highest average accuracy (0.648) across diverse datasets and showed the lowest standard deviation (0.107), indicating consistent performance.
  * The optimal chunking strategy varies depending on the specific dataset and query characteristics, with factoid queries performing well with smaller chunks (256-512 tokens) and complex analytical queries benefiting from larger chunks (1,024 tokens) or page-level chunking using NVIDIA NeMo Retriever extraction.
  * Testing multiple chunking strategies, including page-level, token-based, and section-level chunking, is recommended to determine the best approach for a specific use case and content type.



AI-generated content may summarize information incompletely. Verify important information. [Learn more](https://www.nvidia.com/en-us/agreements/trustworthy-ai/terms/)

A chunking strategy is the method of breaking down large documents into smaller, manageable pieces for AI retrieval. Poor chunking leads to irrelevant results, inefficiency, and reduced business value. It determines how effectively relevant information is fetched for accurate AI responses. With so many options available—page-level, section-level, or token-based chunking with various sizes—how do you determine which approach works best for your specific use case?

This blog post shares insights from our extensive experimentation across diverse datasets to help you optimize your [retrieval-augmented generation (RAG)](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/) system's chunking strategy.

## Introduction __

Chunking is a critical preprocessing step in [RAG pipelines](https://docs.nvidia.com/nemo-framework/user-guide/24.07/rag/ragoverview.html). It involves splitting documents into smaller, manageable pieces that can be efficiently indexed, retrieved, and used as context during response generation. When done poorly, chunking can lead to irrelevant or incomplete responses, frustrating users and undermining trust in the system. It can also increase the computational burden by forcing the retriever or generator to process excessive or unnecessary information.

On the other hand, a smart chunking strategy improves retrieval precision and contextual coherence, which directly enhances the quality of the generated answers. For users, this means faster, more accurate, and more helpful interactions. For businesses, it translates to higher user satisfaction, lower churn, and reduced operational costs due to more efficient resource utilization. In short, chunking isn't just a technical detail—it's a fundamental design choice that shapes the effectiveness of your entire RAG system.

Our research evaluated different chunking strategies across multiple datasets to establish guidelines for selecting the optimal approach based on your specific content and use case.

## Experimental setup __

_Figure 1. Experiment pipeline for evaluation and extraction  _

### Chunking strategies tested __

We tested three primary chunking approaches to understand their impact on retrieval quality and response accuracy:

  1. **Token-based chunking** : Documents are split into fixed-size token chunks using content extracted by NVIDIA NeMo Retriever extraction. 
     * Sizes tested: 128, 256, 512, 1,024, and 2,048 tokens
     * With 15% overlap between chunks (we tested 10%, 15%, and 20% overlap values and found 15% to perform the best on FinanceBench with 1,024 token chunks. While not a full-grid search, this result aligns with the 10–20% overlap commonly seen in industry practices.)
  2. **Page-level chunking** : Each page of a document becomes a separate chunk. 
     * Implemented with both[ ](https://github.com/NVIDIA/nv-ingest)NeMo Retriever extraction and[ nemoretriever-parse](https://build.nvidia.com/nvidia/nemoretriever-parse) to ensure fair comparisons across chunking strategies.
  3. **Section-level chunking** : Documents are split based on structural document layout sections using nemoretriever-parse, following the document's native organization, such as headings, paragraphs, and other formatting elements. 
     * For a fair comparison, we compared page-level and section-level chunking using the same nemoretriever-parse extraction model.



### Datasets __

We evaluated these strategies across diverse datasets:

  * **DigitalCorpora767** : A public dataset of 767 PDFs from [Digital Corpora](https://digitalcorpora.org/) with 991 human-annotated questions across text, tables, charts, and infographics.
  * **Earnings** : An internal collection of 512 PDFs (earnings reports, consulting presentations) containing over 3,000 instances each of charts, tables, and infographics, accompanied by 600+ human-annotated retrieval questions.
  * **FinanceBench** : A benchmark dataset designed to evaluate the performance of [large language models (LLMs)](https://www.nvidia.com/en-us/glossary/large-language-models/) in answering financial questions related to publicly traded companies, using real-world financial documents like 10-K filings and earnings reports.
  * **KG-RAG** : The Docugami KG-RAG dataset is a repository of documents and annotated question-answer pairs designed to evaluate retrieval-augmented generation (RAG) systems, featuring realistic long-form business documents and varying question complexities across single and multiple documents.
  * **RAGBattlePacket** : A collection of tax consulting PDF reports from [Deloitte](https://www.eyelevel.ai/post/most-accurate-rag).



### Evaluation methodology __

We established a comprehensive evaluation framework to systematically compare chunking strategies across different datasets and measure their impact on RAG system performance.

  * **Primary metric** : End-to-end RAG answer accuracy
  * **Evaluation process** : Multiple trials per configuration with many judge models



### Evaluation metrics __

For our evaluation, we used the[ NV Answer Accuracy](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/nvidia_metrics/#answer-accuracy) metric from the RAGAS evaluation framework, which measures the agreement between a model's response and a reference ground truth for a given question.

The Answer Accuracy metric works by:

  1. Using LLM-as-a-judge to evaluate the correctness of generated responses.
  2. Comparing the model's outputs against ground-truth references.
  3. Scoring on a scale of 0-4, where: 
     * **0** : The response is inaccurate or doesn't address the question.
     * **2** : The response partially aligns with the reference.
     * **4** : The response exactly aligns with the reference.



To ensure robustness, each evaluation involves multiple judgment runs with different judge models, and the scores are averaged to produce the final accuracy metric. For our experiments, we used the following powerful models as judges:

  * **Mixtral 8x22B Instruct** (mistralai/mixtral-8x22b-instruct-v0.1)
  * **Llama 3.1 70B Instruct** (meta/llama-3.1-70b-instruct)



Using these large language models as judges provided high-quality assessments, while the multi-judge approach (a.k.a. "council of judges") helped minimize bias from any single evaluator model, resulting in more reliable performance measurements across different chunking strategies.

### **Ingestion framework** __

For our experiments, we used two different document ingestion frameworks to ensure fair comparisons between different chunking strategies:

  1. [**NVIDIA NeMo Retriever**](https://docs.nvidia.com/nemo/retriever/overview/): Used for extracting content for page-level and token-based chunking strategies. This set of microservices is designed for parsing complex, unstructured PDFs and other enterprise documents, enabling us to: 
     * Extract high-quality text while preserving document structure.
     * Capture tables and charts from financial reports and technical documents.
     * Process hundreds of documents efficiently across our diverse datasets.
  2. [**nemoretriever-parse**](https://build.nvidia.com/nvidia/nemoretriever-parse): Model used specifically for section-level chunking, as it can intelligently detect section headers and document structure. For a fair comparison between page-level and section-level chunking, we also used nemoretriever-parse extraction for a version of page-level chunking tests.



This dual-framework approach enabled us to leverage the strengths of each tool while ensuring that our chunking strategy comparisons reflected true performance differences rather than extraction artifacts. When comparing page-level versus section-level chunking, we used the same nemoretriever-parse extraction to eliminate any extraction-based variances, providing a more controlled comparison.

It's important to note that while our chunking strategies (page-level, section-level, and token-based) were applied to the text content of documents, tables, and charts were extracted as separate entities. These elements were not split or chunked, but rather preserved as complete units to maintain their integrity and context. This approach ensures that complex information remains intact during the retrieval process, allowing the RAG system to access complete tables and charts when needed.

### RAG system implementation __

For our experiments, we used components from the[ NVIDIA RAG Blueprint](https://github.com/NVIDIA-AI-Blueprints/rag), which provides a comprehensive reference implementation for enterprise-grade RAG pipelines. This blueprint offers:

  * A modular microservices architecture that enables easy component swapping and evaluation.
  * Support for multimodal data processing (documents with text, images, charts, and tables).
  * Integration with advanced NeMo Retriever microservices for embedding, reranking, and LLM inference
  * Extensive configurability for experimentation with different hyperparameters.



The NVIDIA RAG Blueprint is particularly well-suited for chunking experiments as it provides:

  * Multiple pre-built chunking strategies.
  * Vector database integration for efficient storage and retrieval.
  * Robust evaluation capabilities to measure performance differences.



If you're conducting chunking experiments or building a production RAG system, this blueprint can serve as an excellent starting point, reducing development time while providing the flexibility needed for customization.

To ensure a fair and robust evaluation across chunking strategies, we standardized the following components in our RAG pipeline:

  * **Embedding model** : [nvidia/llama-3.2-nv-embedqa-1b-v2](https://build.nvidia.com/nvidia/llama-3_2-nv-embedqa-1b-v2)
  * **Reranking model** : [nvidia/llama-3.2-nv-rerankqa-1b-v2](https://build.nvidia.com/nvidia/llama-3_2-nv-rerankqa-1b-v2)
  * **Retrieval top-k** : 10 (number of retrieved contexts for generation)
  * **Generator model** : [nvidia/llama-3.1-nemotron-70b-instruct](https://build.nvidia.com/nvidia/llama-3_1-nemotron-70b-instruct)



By keeping these components consistent across all experiments, we ensured that performance differences could be attributed to the chunking strategies rather than variations in other parts of the RAG pipeline. These state-of-the-art models from NVIDIA  provide the foundation for our retrieval and generation capabilities, helping us isolate the impact of different chunking strategies on overall RAG performance.

## Results and analysis __

Our experiments yielded several interesting patterns across datasets.

### Overall performance by chunking strategy __

_Figure 2. Average E2E RAG accuracy with standard deviation for page and token-based chunk size_

This chart shows the average end-to-end RAG accuracy across all datasets for each chunking strategy, with error bars representing standard deviations. Notably, page-level chunking achieved the highest average accuracy (0.648) with the lowest standard deviation (0.107), indicating more consistent performance across datasets. Meanwhile, all token-based approaches maintained consistent performance between 0.603 and 0.645.

_Figure 3. Average E2E RAG accuracy with standard deviation for page and section level chunkin_ g

When directly comparing page-level chunking with section-level chunking using the same nemoretriever-parse extraction, we find that page-level chunking outperforms section-level chunking on average across our test datasets. This reinforces our finding that page-level chunking is generally the most effective strategy.

### **Dataset-specific performance** __

_Figure 4. RAG E2E Accuracy by chunk size (page and token-based chunking) for each dataset_

This chart breaks down RAG accuracy by dataset and chunking strategy, revealing how different content types respond to various chunking approaches. Some datasets, such as FinanceBench and RAGBattlePacket, show optimal performance with medium-sized chunks (512-1024 tokens), while performance drops with large chunks (2,048 tokens). Other datasets, such as KG-RAG, show more variability across chunking strategies, with no clear linear relationship between chunk size and performance.

_Figure 5. RAG E2E accuracy by page and section chunking for each dataset_

Looking at the dataset-specific comparison between page and section chunking strategies, we can see that page-level chunking outperforms section-level chunking in most cases, with only FinanceBench showing slightly better performance with section-level chunking. This indicates that while document structure matters, ‌natural page boundaries typically provide more coherent and effective chunks for retrieval.

#### **Key observations**

  1. **Page-level chunking is the overall winner** : Our experiments clearly show that page-level chunking achieved the highest average accuracy (0.648) across all datasets and the lowest standard deviation (0.107), showing more consistent performance across different content types. Page-level chunking demonstrated superior overall performance when compared to both token-based chunking and section-level chunking.  
  
Looking at the dataset-specific findings, we can see clear evidence of this pattern. Some financial datasets, such as KG-RAG, achieved best performance with page-level chunking (0.520), while others, such as FinanceBench, performed best with 1,024-token chunks (0.579) but still showed strong results with page-level chunking (0.566). The RAGBattlePacket also showed excellent performance with page-level chunking (0.790), very close to its best result with 1,024-token chunks (0.804).  

  2. **Inconsistent patterns even within similar document types** : Even within the same document category, optimal chunking strategies varied significantly.  
  
This observation is particularly evident in financial documents, where we observed three different optimal strategies across three datasets: FinanceBench performed best with 1,024-token chunks (0.579), Earnings with 512-token chunks (0.681), and KG-RAG with page-level chunking (0.520). These variations suggest that, beyond broad content categories, specific document structures, information density, and the nature of queries significantly influence the optimal chunking strategy. This highlights the importance of testing multiple chunking approaches, even when working with‌ similar document types.  

  3. **Extreme chunk sizes show diminishing returns** : Very small (128 tokens) and very large (2,048 tokens) chunks generally underperformed medium-sized chunks.  
  
Across most datasets, the extreme ends of chunk sizes showed lower performance. For KG-RAG, 128-token chunks had the worst performance (0.421), significantly lower than other strategies. Similarly, 2048-token chunks underperformed 1024-token chunks for RAGBattlePacket (0.749 vs 0.804) and FinanceBench (0.506 vs 0.579). This suggests a "sweet spot" in the middle chunk size range for most document types.  

  4. **Performance curves aren 't always linear**: For some datasets, performance didn't increase or decrease linearly with chunk size.  
  
Earnings showed a non-linear pattern where performance peaked at 512 tokens (0.681), declined slightly at 1,024 tokens (0.663), and then declined further at 2,048 tokens (0.651). This contrasts with RAGBattlePacket, which showed a more linear improvement from 128 tokens (0.749) to 1,024 tokens (0.804) before declining at 2,048 tokens (0.749). These different curves highlight the complex relationship between chunk size and retrieval effectiveness.  

  5. **Query characteristics influence optimal chunk size** : The nature of queries in each dataset correlates with the most effective chunking strategies.  
  
DigitalCorpora767 and Earnings datasets, which primarily contain factoid queries seeking specific information, performed well with smaller to medium-sized chunks (256-512 tokens). These datasets showed consistent performance across smaller chunk sizes, with DigitalCorpora767 maintaining relatively stable accuracy from 256 to 1,024 tokens, and Earnings achieving peak performance at 512 tokens (0.681). In contrast, FinanceBench, KG-RAG, and RAGBattlePacket datasets, which feature more complex analytical queries requiring broader context and deeper reasoning, generally benefited from larger chunk sizes (1,024 tokens) or page-level chunking.



## **Guidelines for choosing your chunking strategy** __

Based on our findings, here are practical recommendations for selecting a chunking strategy:

### 1\. Consider page-level chunking first __

Our experiments clearly show that page-level chunking provides the most consistent performance across diverse document types. We recommend:

  * **Start with page-level chunking** as your default strategy (using NeMo Retriever extraction)
  * While not always the absolute best for every dataset, it offers the highest average accuracy and most consistent performance
  * Page-level chunking provides easier citation and reference capabilities since pages are static boundaries, unlike token-based chunking, where chunk indices depend on the chosen chunk size, making references less stable across different configurations



### 2\. Consider your content type for refinement __

If you want to experiment beyond page-level chunking:

  * **Financial documents** : Try 512 or 1,024-token chunks (using NeMo Retriever extraction) if your documents resemble FinanceBench. Section-level chunking can also be effective for financial documents, sometimes outperforming page-level chunking
  * **Diverse documents** : Smaller token-sized chunks (256-512 tokens) performed well for varied content collections



### 3\. Query characteristics impact performance __

  * **Factoid queries** (seeking specific facts): page-level chunking or smaller chunks (256-512 tokens, using NeMo Retriever extraction)
  * **Complex analytical queries** : Page-level chunking or large chunks (1024 tokens, using NeMo Retriever extraction)



We recommend evaluating these strategies on your own data to confirm they work well for your specific use case. Different query patterns and content structures may require different approaches, so testing with your actual data is crucial for optimal performance.

### 4\. Test multiple approaches __

While page-level chunking is our recommended starting point, we still recommend experimenting with multiple chunking strategies for your specific use case:

  1. Start with page-level chunking as your baseline.
  2. Select 1-2 additional chunking strategies based on your content type.
  3. Run a small-scale evaluation on your dataset.
  4. Analyze both quantitative metrics and qualitative response quality.
  5. Iterate and refine based on results.



## Conclusion __

Our comprehensive evaluation across diverse datasets demonstrates that page-level chunking is the most effective chunking strategy for RAG systems, offering the highest average accuracy and most consistent performance. This is true when compared against both token-based chunking and section-level chunking approaches.

While specific content types may occasionally benefit from alternative strategies, page-level chunking provides an excellent default choice that balances performance across document types, query styles, and retrieval scenarios. This suggests that natural page boundaries often encapsulate coherent information units that are well-suited for retrieval tasks.

The optimal chunking strategy for your specific RAG system may still vary depending on your unique use case, content type, and query patterns. By starting with page-level chunking and systematically evaluating alternatives using the guidelines provided in this post, you can optimize your RAG system's performance and deliver more accurate, relevant responses to your users.

Remember that chunking is just one of many hyperparameters in a RAG system. For truly optimal performance, consider exploring other dimensions such as embedding models, reranking strategies, and generation parameters.

## **Get started with the NVIDIA RAG Blueprint** __

We encourage you to try the[ NVIDIA RAG Blueprint](https://github.com/NVIDIA-AI-Blueprints/rag) for yourself. This enterprise-grade reference implementation provides all the components you need to:

  * Experiment with different chunking strategies on your own datasets
  * Leverage state-of-the-art embedding and reranking models
  * Build a production-ready RAG system with minimal development time



[Get started with the NVIDIA RAG Blueprint today.](https://github.com/NVIDIA-AI-Blueprints/rag)

__Discuss (1)

__

Like 

## Tags

[Agentic AI / Generative AI](https://developer.nvidia.com/blog/category/generative-ai/) | [General](https://developer.nvidia.com/blog/recent-posts/?industry=General) | [Blueprint](https://developer.nvidia.com/blog/recent-posts/?products=Blueprint) | [Intermediate Technical](https://developer.nvidia.com/blog/recent-posts/?learning_levels=Intermediate+Technical) | [Best practice](https://developer.nvidia.com/blog/recent-posts/?content_types=Best+practice) | [featured](https://developer.nvidia.com/blog/tag/featured/) | [Retrieval Augmented Generation (RAG)](https://developer.nvidia.com/blog/tag/retrieval-augmented-generation-rag/)

##  About the Authors 

**About Steve Han**   
Steve is a senior software engineer and researcher specializing in retrieval-augmented generation (RAG) and agent systems. His work centers on designing rigorous text- and multimodal evaluation pipelines and developing synthetic data generation methods. With a master’s degree in Electrical Engineering from Stanford University, he brings a strong systems background to AI evaluation and optimization. 

[ View all posts by Steve Han ](https://developer.nvidia.com/blog/author/sthan/)

## Comments

## Related posts

###  How to Enhance RAG Pipelines with Reasoning Using NVIDIA Llama Nemotron Models 

[ How to Enhance RAG Pipelines with Reasoning Using NVIDIA Llama Nemotron Models ](https://developer.nvidia.com/blog/how-to-enhance-rag-pipelines-with-reasoning-using-nvidia-llama-nemotron-models/)

###  Build an Agentic RAG Pipeline with Llama 3.1 and NVIDIA NeMo Retriever NIMs 

[ Build an Agentic RAG Pipeline with Llama 3.1 and NVIDIA NeMo Retriever NIMs ](https://developer.nvidia.com/blog/build-an-agentic-rag-pipeline-with-llama-3-1-and-nvidia-nemo-retriever-nims/)

###  Scaling Enterprise RAG with Accelerated Ethernet Networking and Networked Storage 

[ Scaling Enterprise RAG with Accelerated Ethernet Networking and Networked Storage ](https://developer.nvidia.com/blog/scaling-enterprise-rag-with-accelerated-ethernet-networking-and-networked-storage/)

###  Evaluating Retriever for Enterprise-Grade RAG 

[ Evaluating Retriever for Enterprise-Grade RAG ](https://developer.nvidia.com/blog/evaluating-retriever-for-enterprise-grade-rag/)

###  Build Enterprise Retrieval-Augmented Generation Apps with NVIDIA Retrieval QA Embedding Model 

[ Build Enterprise Retrieval-Augmented Generation Apps with NVIDIA Retrieval QA Embedding Model ](https://developer.nvidia.com/blog/build-enterprise-retrieval-augmented-generation-apps-with-nvidia-retrieval-qa-embedding-model/)

## Related posts

###  Build an AI Scientist for Life Science Discovery with NVIDIA BioNeMo Agent Toolkit 

[ Build an AI Scientist for Life Science Discovery with NVIDIA BioNeMo Agent Toolkit ](https://developer.nvidia.com/blog/build-an-ai-scientist-for-life-science-discovery-with-nvidia-bionemo-agent-toolkit/)

###  Enable Real-Time AI for High-Speed Data Acquisition with DAQIRI 

[ Enable Real-Time AI for High-Speed Data Acquisition with DAQIRI ](https://developer.nvidia.com/blog/enable-real-time-ai-for-high-speed-data-acquisition-with-daqiri/)

###  Build Your Own Transaction Foundation Model for Financial Intelligence 

[ Build Your Own Transaction Foundation Model for Financial Intelligence ](https://developer.nvidia.com/blog/build-your-own-transaction-foundation-model-for-financial-intelligence/)

###  How to Optimize Transformer-Based Models for Low-Precision Training 

[ How to Optimize Transformer-Based Models for Low-Precision Training ](https://developer.nvidia.com/blog/how-to-optimize-transformer-based-models-for-low-precision-training/)

###  NVIDIA Blackwell Tops MLPerf Training 6.0 with Industry-Leading Scale and Performance 

[ NVIDIA Blackwell Tops MLPerf Training 6.0 with Industry-Leading Scale and Performance ](https://developer.nvidia.com/blog/nvidia-blackwell-tops-mlperf-training-6-0-with-industry-leading-scale-and-performance/)

Close Previous

Next

  * [L](https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)
  * [T](https://twitter.com/intent/tweet?text=Finding+the+Best+Chunking+Strategy+for+Accurate+AI+Responses+%7C+NVIDIA+Technical+Blog+https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)
  * [F](https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)
  * [R](https://www.reddit.com/submit?url=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F&title=Finding+the+Best+Chunking+Strategy+for+Accurate+AI+Responses+%7C+NVIDIA+Technical+Blog)
  * [E](mailto:?subject=I'd like to share a link with you&body=https%3A%2F%2Fdeveloper.nvidia.com%2Fblog%2Ffinding-the-best-chunking-strategy-for-accurate-ai-responses%2F)


