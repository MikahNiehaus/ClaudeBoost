<!-- Source: https://arxiv.org/html/2606.11700v1 | Tier: A | Topic: rag-reranking | Fetched: 2026-06-23 -->

##### Report GitHub Issue

×

Title:

Content selection saved. Describe the issue below:

Description:

Submit without GitHub Submit in GitHub

[ Back to arXiv ](/)

[Why HTML?](https://info.arxiv.org/about/accessible_HTML.html) Report Issue [ Back to Abstract ](/abs/2606.11700v1 "Back to abstract page") [ Download PDF](/pdf/2606.11700v1 "Download PDF") [ ](javascript:toggleNavTOC\(\); "Toggle navigation") [ ](javascript:toggleReadingMode\(\); "Disable reading mode, show header and footer")

  1. Abstract
  2. 1 Introduction
  3. 2 Related Work
     1. LLMs for Reranking
     2. Efficient Rerankers
  4. 3 CompRank
     1. 3.1 Problem Formulation: Scoring via Attention Mass
     2. 3.2 Document Representation Decoupling and Positional Invariance
     3. 3.3 Token-Level Compression
     4. 3.4 CopyNet-Based Learning Objective
  5. 4 Experiments
     1. 4.1 Experiment Setup
     2. 4.2 Main Results
        1. Comparison of Token Compression Strategies
        2. Comparison with Reranking Baselines
  6. 5 Analysis
     1. 5.1 Efficiency Analysis
     2. 5.2 Scaling and Extrapolation
        1. Latency breakdown.
     3. 5.3 Effect of CopyNet Supervision
  7. 6 Conclusion
  8. References
  9. A Implementation Details
     1. A.1 CompRank Training Details
     2. A.2 CompRank Input Prompt
     3. A.3 Direct-List Prompt and Decoding Setup
  10. B Additional Efficiency Analysis
     1. Structural sparsity via block decoupling.
     2. Token-level compression.
     3. Decoding-free scoring.
     4. Reusable document representations.
  11. C Complete Baseline Results
  12. D Ablation on Layer Selection and Decision Token Selection
     1. D.1 Ablation on Transformer Layer Selection
     2. D.2 Ablation on Decision Token Selection
  13. E Analysis of Decoding Errors in Direct-List
  14. F Limitations



[ License: CC BY-NC-ND 4.0 ](https://info.arxiv.org/help/license/index.html#licenses-available)

arXiv:2606.11700v1 [cs.IR] 10 Jun 2026

# CompRank: Efficient LLM Reranking via Token-Level Compression and Decoding-Free Scoring

Xuan Lu1,2,3, Haohang Huang3, Yingqi Fan3, Junlong Tong1,2,3, Yuxuan Zhang4,   
Ping Nie5, Rui Meng, Xiaoyu Shen2,3‡   
1Shanghai Jiao Tong University   
2Ningbo Key Laboratory of Spatial Intelligence and Digital Derivative   
3Institute of Digital Twin, Eastern Institute of Technology, Ningbo   
4University of British Columbia 5University of Waterloo   
lux1997@sjtu.edu.cn xyshen@eitech.edu.cn   
Working at Google Cloud AI Research. ‡\ddagger Corresponding author.

###### Abstract

Large language model (LLM) rerankers have become an important component of modern retrieval and retrieval-augmented generation pipelines, but their high computational cost limits their applicability to long candidate lists. In this paper, we propose CompRank, a token-efficient reranking framework that reduces redundant computation by aligning reranker design with the sparsity of ranking signals. CompRank decouples document representations from candidate order and query context, enabling reusable document-side states; applies segment-wise token compression to reduce query–document interaction cost; and introduces a CopyNet-style objective that directly aligns attention-based document scoring with training supervision. Experiments on seven BEIR datasets show that CompRank achieves strong reranking performance while retaining only 10.2% of document tokens, reaching an average NDCG@10 of 39.2 compared with 39.7 under full-token attention. Further scaling experiments on TREC-COVID show that CompRank remains stable when evaluated on candidate lists of up to 500 documents after training on 30-document lists, while achieving 4.9×4.9\times–9.5×9.5\times end-to-end speedup over generation-based listwise reranking and approximately 1.3×1.3\times speedup over the full-token CompRank variant. These results suggest that token-level compression and decoding-free attention scoring provide an effective path toward scalable LLM-based reranking.

##  1 Introduction

Reranking has become an important component of modern Information Retrieval (IR) and Retrieval-Augmented Generation (RAG) pipelines Lewis et al. (2020); Lu et al. (2025). By applying fine-grained relevance modeling to candidates retrieved by first-stage models, rerankers, especially those based on Large Language Models (LLMs), can improve retrieval precision and support downstream agentic decision-making Lu et al. (2026b); Huang et al. (2026). However, these gains often come with substantial computational cost. In long-list scenarios, such as reranking the top-100 retrieved documents, LLM-based rerankers must process long input contexts and perform expensive attention computation, making latency and memory consumption major bottlenecks. Recent studies have explored several ways to improve the efficiency of LLM-based reranking. Direct-Rank Lu et al. (2026a) shows that ranking does not necessarily require lengthy Chain-of-Thought reasoning, and that direct ranking sequence modeling can achieve strong performance. To reduce decoding overhead, ICR Chen et al. (2025) and QRHead Zhang et al. (2025) infer relevance scores from internal attention patterns, avoiding expensive autoregressive generation. BlockRank Gupta et al. (2025) and LongRanker Zhou et al. (2026) further observe redundancy in long-context reranking and exploit structured attention to reduce unnecessary interactions. These methods improve efficiency from different perspectives, but many of them still process dense token-level representations, leaving substantial redundancy in document-side computation and query–document interaction.

In this work, we revisit reranking from the perspective of token-level sparsity and representation reuse. Our motivation is that relevance estimation often depends on a relatively small subset of informative document tokens, while the remaining tokens contribute limited signal for ranking. At the same time, candidate documents are frequently recomputed in different contexts, even when their representations need not depend on the current query or candidate ordering. This issue is particularly relevant in agentic search and RAG systems, where agents may revisit the same documents, maintain long interaction histories, and repeatedly invoke retrieval tools across multi-step reasoning trajectories. In such settings, reusable document-side KV states provide a natural way to amortize repeated document encoding and reduce online computation. This creates a mismatch between dense computation and sparse ranking signals. We hypothesize that reranking can be made more efficient by decoupling document representations and reducing the number of document tokens involved in query-side scoring. To this end, we propose CompRank, a token-efficient reranking framework for long candidate lists. CompRank introduces a document representation decoupling mechanism that reduces dependence on candidate order and query context, making reusable document representations possible. It then applies structured token compression to reduce the number of document tokens exposed to query–document attention. Finally, CompRank uses a CopyNet-style objective to align training with attention-based inference: the same attention-derived document scores are optimized during training and directly used for decoding-free reranking at inference time.

This design provides both efficiency and robustness benefits. Since CompRank avoids autoregressive decoding of document identifiers, it reduces decoding latency and avoids common generation failures such as duplicated or out-of-range document IDs. Since document tokens are compressed before query-side scoring, it further reduces the effective attention cost. Moreover, because ranking is performed over input candidates rather than generated output sequences, CompRank can better extrapolate from shorter training lists to longer inference-time candidate lists. We evaluate CompRank on seven BEIR datasets. With Segment-10 compression, CompRank retains only 10.2% of document tokens while achieving an average NDCG@10 of 39.2, close to the full-token setting of 39.7. In scaling experiments on TREC-COVID, CompRank generalizes from 30-document training lists to 500-document inference lists and achieves 4.9×4.9\times–9.5×9.5\times end-to-end speedup over a generation-based listwise reranker, as well as approximately 1.3×1.3\times speedup over the full-token CompRank variant.

Our contributions are summarized as follows:

  * •

We propose CompRank, a token-efficient reranking framework that decouples document representations and reduces redundant computation through structured token compression.

  * •

We align attention-based inference with CopyNet-style supervision, directly optimizing the same attention-derived document scores used for decoding-free reranking.

  * •

We show that CompRank remains more stable than decode-ID reranking in our TREC-COVID scaling experiment when evaluated on longer candidate lists.

  * •

We provide complexity and latency analyses, showing reduced attention cost and practical end-to-end speedups over generation-based and full-token reranking baselines.




##  2 Related Work

#### LLMs for Reranking

Recent advances have established large language models (LLMs) as a dominant paradigm for reranking (Yin et al., 2026; Lu et al., 2026c; Fan et al., 2026). Existing approaches can be broadly categorized into pointwise (Lu et al., 2026a), pairwise (Qin et al., 2024), setwise (Zhuang et al., 2024), and listwise methods (Pradeep et al., 2023a). Pointwise methods evaluate each query–document pair independently by generating relevance scores, with representative models including MonoBERT (Nogueira et al., 2019), MonoT5 (Nogueira et al., 2020), and RankLLaMA (Ma et al., 2024). While effective, this paradigm incurs substantial redundant computation on large candidate sets. Pairwise and setwise methods model relative preferences among documents (Zhuang et al., 2024; Qin et al., 2024), but introduce additional overhead due to repeated comparisons. Listwise and in-context ranking approaches jointly process multiple candidates within a single context, enabling richer inter-document interactions. Early work demonstrated strong zero-shot performance using GPT-based rerankers (Sun et al., 2023), followed by adaptations to open-source LLMs such as Vicuna, Zephyr, and Mistral (Pradeep et al., 2023a, b), as well as structured frameworks like RankLLM (Sharifymoghaddam et al., 2025). To scale to long candidate lists, these methods often employ sliding windows or hierarchical strategies (Zhou et al., 2026), which reduce context length but introduce redundant computation across windows.

#### Efficient Rerankers

Improving the efficiency of long-context reranking has attracted increasing attention. One line of work reduces decoding cost. Attention-based rerankers infer relevance directly from internal attention patterns without explicit generation (Chen et al., 2025; Zhang et al., 2025; Wang et al., 2026; Tran et al., 2026), while FIRST reduces listwise reranking to single-token decoding (Reddy et al., 2024). These methods avoid or shorten autoregressive ranking outputs, thereby reducing inference overhead. Another line of work reduces input or attention computation. BlockRank (Gupta et al., 2025) shows that inter-document attention is largely redundant and proposes block-wise attention for scalable in-context ranking. LongRanker (Zhou et al., 2026) studies efficient one-pass reranking under long-context settings. General long-context models also explore sparse attention patterns such as sliding-window or global-local attention (Beltagy et al., 2020; Zaheer et al., 2020), and recent KV-level compression methods reduce the number of tokens participating in attention (DeepSeek-AI, 2025, 2026). A complementary direction compresses or reuses document representations. HyperRAG (An et al., 2025), CompressedDoc (Déjean and Clinchant, 2025), and BlockDoc (Li et al., 2026) precompute or compress document representations for reuse. More closely related, Compress-then-Rank applies ranking-aware passage compression before listwise reranking (Zhi et al., 2026), and PE-Rank uses passage embeddings as compact surrogates for efficient listwise reranking (Liu et al., 2025). In contrast, CompRank preserves token-level document representations, compresses the subset of document tokens exposed to attention-based scoring, and performs decoding-free reranking by directly sorting attention-derived document scores.

Figure 1: Overview of CompRank. (a) Document blocks are decoupled by inter-document masking and shared positional offsets, enabling reusable document representations. (b) Token-level compression reduces the number of document tokens exposed to query-side attention. (c) CopyNet-style supervision directly optimizes attention-derived document scores for decoding-free reranking.

##  3 CompRank

In this section, we present CompRank, an efficient framework for long-list reranking. Our design is motivated by three objectives: (i) avoiding the latency of autoregressive decoding through attention-based scoring; (ii) reducing sensitivity to candidate order and enabling document-side pre-computation through representation decoupling; and (iii) reducing query–document interaction cost through token-level compression.

###  3.1 Problem Formulation: Scoring via Attention Mass

Recent work Chen et al. (2025); Zhang et al. (2025) shows that reranking can be performed directly from the contextual encoding stage of LLMs, without relying on autoregressive generation. In particular, in-context reranking (ICR) is based on the observation that, when processing a query together with candidate documents, LLMs often allocate more attention mass to tokens belonging to relevant documents. This suggests that relevance can be estimated by aggregating attention weights from query-side tokens to document-side tokens.

Formally, given a query qq and a candidate document set 𝒟={d1,d2,…,dN}\mathcal{D}=\\{d_{1},d_{2},\ldots,d_{N}\\}, the goal is to assign a relevance score to each document and produce a ranked list. Building on ICR, CompRank formulates reranking as a discriminative attention aggregation problem, where relevance scores are derived directly from attention distributions without decoding document identifiers.

Let BqB_{q} denote the query or decision block, and let TiT_{i} be the token sequence of document did_{i}. After optional token compression (Sec. 3.3), the visible token subset is denoted as Ti′⊆TiT_{i}^{\prime}\subseteq T_{i}. For a scoring layer ℓ∗\ell^{*} and attention head hh, the masked attention logit from a query-side decision token u∈Bqu\in B_{q} to a document token t∈Ti′t\in T_{i}^{\prime} is:

| au,t(ℓ∗,h)=Qu(ℓ∗,h)​(Kt(ℓ∗,h))⊤dh+mu,t,a^{(\ell^{*},h)}_{u,t}=\frac{Q^{(\ell^{*},h)}_{u}\left(K^{(\ell^{*},h)}_{t}\right)^{\top}}{\sqrt{d_{h}}}+m_{u,t}, |   
---|---|---  
  
where QQ and KK are query and key representations, dhd_{h} is the head dimension, and mu,tm_{u,t} denotes the attention mask. We normalize attention over all retained document tokens:

| pu,t(h)=exp⁡(au,t(ℓ∗,h))∑j=1N∑t′∈Tj′exp⁡(au,t′(ℓ∗,h)).p^{(h)}_{u,t}=\frac{\exp(a^{(\ell^{*},h)}_{u,t})}{\sum_{j=1}^{N}\sum_{t^{\prime}\in T_{j}^{\prime}}\exp(a^{(\ell^{*},h)}_{u,t^{\prime}})}. |   
---|---|---  
  
The document-level score for did_{i} is obtained by aggregating attention mass over its retained tokens:

| si=Aggu∈U⁡[1H​∑h=1H∑t∈Ti′pu,t(h)],s_{i}=\operatorname{Agg}_{u\in U}\left[\frac{1}{H}\sum_{h=1}^{H}\sum_{t\in T_{i}^{\prime}}p^{(h)}_{u,t}\right], |   
---|---|---  
  
where U⊆BqU\subseteq B_{q} is the set of decision tokens, HH is the number of heads, and Agg⁡(⋅)\operatorname{Agg}(\cdot) is an aggregation operator such as mean or max. The final ranking π\pi is obtained by sorting documents in descending order of sis_{i}. Unless otherwise specified, the scoring layer, decision-token set, and aggregation operator are fixed across all datasets; implementation details are provided in Appendix A.

###  3.2 Document Representation Decoupling and Positional Invariance

A key challenge in in-context reranking is the sensitivity of LLMs to the order of candidate documents. Since candidate lists are dynamically constructed and may vary across queries, reducing order sensitivity is important for robust reranking. CompRank addresses this by organizing the input as independent document blocks followed by a query or decision block:

| X=[D1;D2;…;DN;Bq].X=[D_{1};D_{2};\dots;D_{N};B_{q}]. |   
---|---|---  
  
To reduce dependence on candidate ordering, we use a shared positional bias across document blocks. Specifically, for a token xi,tx_{i,t} at local position tt in document block DiD_{i}, we assign:

| pos⁡(xi,t)=t,\operatorname{pos}(x_{i,t})=t, |   
---|---|---  
  
independent of the document index ii. For the query block BqB_{q}, we apply a constant offset CC:

| pos⁡(Bq,t)=C+t.\operatorname{pos}(B_{q},t)=C+t. |   
---|---|---  
  
This removes document-index-dependent positional offsets and reduces one major source of order sensitivity in document representations.

Following the block-structured attention design in BlockRank Gupta et al. (2025), we further impose a structured attention mask to decouple candidate documents. Tokens within each document block perform causal self-attention, while attention across different document blocks is prohibited. The query block BqB_{q} attends to all document blocks, maintaining a global view over the candidate set for relevance estimation.

Under this design, document representations are computed independently of other candidates and do not depend on the query block. This makes document-side pre-encoding possible in principle:

| Ki,Vi=fθ​(Di),K_{i},V_{i}=f_{\theta}(D_{i}), |   
---|---|---  
  
where the resulting key-value states can be reused across different queries or candidate permutations. This decoupling reduces repeated document-side computation and provides a path toward more efficient query-time reranking with reusable document states.

###  3.3 Token-Level Compression

Although document representation decoupling removes document–document interactions, query-side attention still scales with the total number of document tokens. CompRank therefore applies token-level compression to the document-side KV states by selecting a subset Ti′⊆TiT_{i}^{\prime}\subseteq T_{i} of visible document tokens. Importantly, compression is applied only to query-to-document attention in the final block, while document-side representations remain unchanged.

We consider three token selection strategies:

  * •

Last-kk Compression: Retains the final kk valid tokens of each document, motivated by the observation that later positions in decoder-only LLMs may aggregate preceding context.

  * •

Segment-wise Compression: Retains one token every kk positions, either start-anchored or end-anchored. This provides uniform coverage across the document while reducing the visible KV size by approximately a factor of kk.

  * •

Intrinsic Importance Selection: Uses document-internal attention to select salient tokens. Specifically, the final token of document did_{i} is used as a summary query to compute token importance:

| αi,t=1H​∑h=1HQi,Li(h)​(Ki,t(h))⊤dh.\alpha_{i,t}=\frac{1}{H}\sum_{h=1}^{H}\frac{Q^{(h)}_{i,L_{i}}\left(K^{(h)}_{i,t}\right)^{\top}}{\sqrt{d_{h}}}. |  | (1)  
---|---|---|---  
  
We then define Ti′T_{i}^{\prime} as the union of the top-kk tokens according to αi,t\alpha_{i,t} and a small set of anchor tokens, such as the last token, to preserve structural information.




###  3.4 CopyNet-Based Learning Objective

Standard supervised fine-tuning for LLM reranking often trains the language modeling head to generate document identifiers. This formulation is inefficient for reranking because probability mass is assigned over the full vocabulary, including invalid or irrelevant tokens. It also introduces autoregressive decoding overhead and may generalize poorly when the candidate set size changes.

CompRank instead performs reranking directly using attention-derived document scores. We adopt a CopyNet-style objective Gu et al. (2016), where the model selects from existing input candidates rather than generating unseen labels. Given document scores {si}i=1N\\{s_{i}\\}_{i=1}^{N}, we define a pointer distribution over candidates:

| Pcopy​(i∣q,𝒟)=exp⁡(si/τ)∑j=1Nexp⁡(sj/τ),P_{\mathrm{copy}}(i\mid q,\mathcal{D})=\frac{\exp(s_{i}/\tau)}{\sum_{j=1}^{N}\exp(s_{j}/\tau)}, |   
---|---|---  
  
where τ\tau is a temperature parameter. For a query with ground-truth document index yy, the training objective is:

| ℒcopy=−log⁡Pcopy​(y∣q,𝒟).\mathcal{L}_{\mathrm{copy}}=-\log P_{\mathrm{copy}}(y\mid q,\mathcal{D}). |   
---|---|---  
  
This objective directly supervises the same attention-derived scores used at inference time. As a result, training and inference are aligned: the model learns to allocate probability mass over candidate documents, and reranking is performed by sorting these scores without autoregressive decoding. This candidate-level formulation also avoids invalid document identifier generation and supports more stable extrapolation to candidate set sizes beyond those seen during training.

##  4 Experiments

This section presents the experimental setup, the main results of CompRank, and the comparison of different token compression strategies.

###  4.1 Experiment Setup

We evaluate CompRank on seven datasets from the BEIR benchmark Thakur et al. (2021), covering diverse retrieval tasks and domains: FiQA, SciFact, TREC-COVID, DBPedia, Climate FEVER, NF Corpus, and SciDocs. For comparison, we consider representative retrieval and reranking baselines, including the sparse retriever BM25, generation-based listwise rerankers such as RankGPT Sun et al. (2024), and attention-based in-context reranking methods including ICR Chen et al. (2025) and Corehead Tran et al. (2026). For evaluation, BM25 is used to retrieve the top-100 candidate documents for each query, and all reranking methods reorder the same candidate set. We report NDCG@10 as the primary evaluation metric.

CompRank uses Mistral-7B as the backbone model and is trained with full-parameter fine-tuning. We directly adopt the training data constructed by BlockRank Gupta et al. (2025), which provides query–document candidate sets with annotated positive instances and is derived from the MS MARCO corpus by sampling 10% of the original training split. During training, each query is paired with 30 candidate passages retrieved by a first-stage retriever. Unless otherwise specified, we use segment-wise compression with Step-10 as the default compression strategy. We train CompRank with a learning rate of 3.0×10−63.0\times 10^{-6}, and all training and evaluation experiments are conducted on 8 NVIDIA H20 GPUs.

###  4.2 Main Results

#### Comparison of Token Compression Strategies

We conduct an ablation study to examine how different token compression strategies affect reranking performance. Table 1 reports NDCG@10 on BEIR datasets, together with token retention ratios during inference. The full-token setting achieves the highest average score of 39.7, serving as the upper-bound reference, but requires attending to all document tokens. In contrast, compressed variants substantially reduce the token budget while maintaining competitive performance, indicating considerable token-level redundancy in reranking. Overall, segment-wise compression provides the best effectiveness–efficiency trade-off. Among all compressed variants, Step-10 achieves the highest average score of 39.2, only 0.5 points below full-token attention, while retaining merely 10.2% of document tokens. This suggests that a small uniformly sampled subset can preserve most ranking signals. Increasing the budget to Step-5 (20.0%) does not yield further gains, while stronger compression with Step-20 and Step-30 gradually degrades performance, showing a clear trade-off between coverage and compression strength. By contrast, last-kk compression exhibits a consistent gap. Although increasing kk improves the average score from 36.3 to 38.0, even Last-32 with 14.1% retained tokens remains below Step-10 with 10.2%. This indicates that relying only on final tokens introduces positional bias and may discard evidence appearing earlier in the document. Attention-based Top-kk selection shows similar limitations: pure Top-kk variants obtain 35.8–36.8 on average, and hybrid variants provide limited improvements. These results suggest that document-internal saliency does not reliably align with query-specific relevance.

Strategy | Token Ratio | Climate | DBPedia | FiQA | NFCorpus | SciDocs | SciFact | COVID | Avg.  
---|---|---|---|---|---|---|---|---|---  
No Compression  
\rowcolor[rgb] .949, .949, .949 Full Tokens | 100% | 16.9 | 35.8 | 33.1 | 32.7 | 13.7 | 67.2 | 78.4 | 39.7  
Last-kk Token Compression  
Last-1 | 0.4% | 16.7 | 34.4 | 29.4 | 30.1 | 12.8 | 52.1 | 78.8 | 36.3  
Last-2 | 0.9% | 17.2 | 34.8 | 30.8 | 29.9 | 13.0 | 53.5 | 78.8 | 36.9  
Last-4 | 1.8% | 17.4 | 36.1 | 28.6 | 30.4 | 13.4 | 55.4 | 79.7 | 37.3  
Last-8 | 3.5% | 16.2 | 35.4 | 31.5 | 31.3 | 12.9 | 55.8 | 79.9 | 37.6  
Last-16 | 7.0% | 16.0 | 35.2 | 31.5 | 31.4 | 12.9 | 57.4 | 79.6 | 37.7  
Last-32 | 14.1% | 15.6 | 35.3 | 32.5 | 31.0 | 13.4 | 59.5 | 78.9 | 38.0  
Attention-based Top-kk Compression  
Top-4 | 1.8% | 16.8 | 32.5 | 28.0 | 29.1 | 12.8 | 54.7 | 76.9 | 35.8  
Top-8 | 3.5% | 16.6 | 33.2 | 28.8 | 29.7 | 12.9 | 56.0 | 77.4 | 36.3  
Top-16 | 7.0% | 16.2 | 33.6 | 29.6 | 30.1 | 13.0 | 57.6 | 77.7 | 36.8  
Last-4 + Top-4 | 3.5% | 19.1 | 32.5 | 27.3 | 29.3 | 13.5 | 53.7 | 77.0 | 36.1  
Last-8 + Top-8 | 7.0% | 15.6 | 34.6 | 28.6 | 28.9 | 13.4 | 55.3 | 77.4 | 36.3  
Segment-wise Compression  
Step-5 | 20.0% | 16.8 | 34.2 | 31.2 | 32.1 | 14.2 | 65.5 | 79.7 | 39.1  
Step-10 | 10.2% | 16.6 | 34.8 | 31.7 | 31.7 | 14.3 | 64.2 | 81.2 | 39.2  
Step-20 | 5.2% | 16.1 | 34.5 | 32.0 | 31.3 | 14.0 | 61.9 | 79.2 | 38.4  
Step-30 | 3.5% | 18.1 | 34.0 | 29.3 | 30.4 | 13.1 | 59.8 | 78.7 | 37.6  
  
Table 1: Results of different token compression strategies on seven BEIR datasets. We report NDCG@10 and the corresponding token retention ratio during inference.

#### Comparison with Reranking Baselines

We further compare CompRank with representative retrieval and reranking baselines. Full results are provided in Appendix C. BM25 and RankGPT obtain average NDCG@10 scores of 35.4 and 35.1. Attention-based rerankers achieve stronger results, with ICR (Mistral-7B), ICR (Qwen2.5-7B), and Corehead (Qwen2.5-7B) reaching 38.4, 38.3, and 38.1 average NDCG@10, respectively. CompRank achieves the best average score of 39.2 using the same Mistral-7B backbone as RankGPT and ICR, while also retaining only 10.2% of document tokens. This shows that CompRank not only improves the efficiency of attention-based reranking, but also maintains competitive or better effectiveness compared with existing reranking methods.

##  5 Analysis

###  5.1 Efficiency Analysis

We analyze the efficiency of CompRank from three aspects: block-level sparsity, token-level compression, and decoding-free scoring. First, CompRank removes document–document attention by encoding each document block independently and allowing the query block to attend to document blocks only during scoring. Compared with full attention over NN document blocks of length LL, whose complexity scales as O​((N​L)2​d)O((NL)^{2}d), block decoupling reduces the document-side attention cost to: O​(N​L2​d)O(NL^{2}d), changing the scaling with respect to the number of candidate documents from quadratic to linear. Second, CompRank further reduces the query–document interaction cost by compressing the document-side KV states exposed to query-side attention. Let ρ∈(0,1]\rho\in(0,1] denote the retained fraction of document tokens. Under a simplified setting where instruction, query, and document blocks have comparable length, an uncompressed block-wise reranker attends to instruction, query, and document tokens, with interaction cost proportional to 3​L23L^{2}. With token compression, only ρ​|D|\rho|D| document tokens are exposed to query-side attention, reducing the cost to approximately (2+ρ)​L2(2+\rho)L^{2}. The resulting attention-level speedup is:

| 𝒮≈32+ρ.\mathcal{S}\approx\frac{3}{2+\rho}. |   
---|---|---  
  
With Segment-10 compression, ρ≈0.1\rho\approx 0.1, giving an estimated attention-level speedup of 1.43×1.43\times. Empirically, Sec. 5.2 shows that Segment-10 achieves approximately 1.3×1.3\times end-to-end speedup over the full-token CompRank variant. Third, CompRank avoids autoregressive identifier generation by directly deriving document scores from attention distributions. This converts reranking from a sequential decoding process into a parallelizable scoring problem. As shown in Sec. 5.2, this decoding-free design achieves 4.9×4.9\times–9.5×9.5\times end-to-end speedup over a decode-ID listwise reranker when scaling from 30 to 500 candidate documents. Finally, CompRank enables reusable document-side representations in principle. Since document blocks neither attend to other documents nor to the query block, their KV states can be pre-encoded or cached across repeated retrieval calls. This property is particularly useful in RAG and agentic search scenarios, where the same evidence documents may be revisited across multiple reasoning steps. Our current evaluation still recomputes document blocks, so the reported latency is a conservative end-to-end measurement without optimized KV caching. We provide a more detailed complexity and caching discussion in Appendix B.

###  5.2 Scaling and Extrapolation

We analyze the scalability and extrapolation behavior of CompRank under long candidate lists on the TREC-COVID dataset. Specifically, we compare CompRank with a generation-based Direct-List baseline that autoregressively decodes document identifiers. To separate the effect of token compression from attention-based scoring, we also include a full-token variant of CompRank. All models are trained on 30-document candidate lists and evaluated on larger candidate sets, ranging from 30 to 500 documents, without further fine-tuning. All experiments are conducted on a single A100 80GB GPU with batch size 1. Figure 2 reports both NDCG@10 and end-to-end latency per query, showing a clear difference in extrapolation behavior.

Figure 2: Scaling performance and end-to-end latency on TREC-COVID as the number of candidate documents increases. All models are trained on 30-document lists and evaluated up to 500 documents.

Direct-List suffers a substantial performance drop as the candidate set grows, decreasing from 75.8 NDCG@10 at 30 documents to 59.7 at 500 documents. In contrast, both CompRank variants remain more stable. The full-token variant maintains competitive performance, while CompRank with Segment-10 reaches 79.5 NDCG@10 at 500 documents. This suggests that attention-based scoring is more robust than decode-ID generation in this long-list setting.

The degradation of Direct-List is likely related to its reliance on autoregressive decoding of document identifiers. Since the model is trained to generate identifiers within a limited range, increasing the number of candidates introduces distribution shift in the output space and may lead to invalid predictions, such as missing identifiers, duplicated identifiers, or out-of-range indices. A more detailed decoding error analysis is provided in Appendix E, where we observe that the model can maintain nearly error-free decoding when trained and evaluated on 30-document candidate sets, but the decoding error rate increases substantially when generalizing to larger candidate spaces (50–500 documents). This suggests that identifier-based autoregressive ranking struggles to generalize to unseen decoding sequences and larger output spaces. CompRank also demonstrates substantially lower end-to-end latency. Direct-List becomes increasingly expensive as the candidate set grows, reaching 114.5s per query at 500 documents. In comparison, CompRank (Segment-10) requires only 12.0s, corresponding to a 9.5×9.5\times speedup. Across different candidate sizes, CompRank achieves 4.9×4.9\times–9.5×9.5\times speedup over Direct-List. Token-level compression further improves efficiency: compared with CompRank (Full-token), Segment-10 reduces latency from 16.22s to 12.0s at 500 documents, yielding approximately 1.3×1.3\times additional speedup while maintaining stronger ranking performance.

#### Latency breakdown.

To further understand the source of efficiency gains, we decompose the latency of CompRank (Segment-10) into three components: end-to-end latency, full-forward latency, and query-block-forward latency. End-to-end latency measures the complete evaluation pipeline. Full-forward latency measures model forward computation when document blocks are recomputed for each query. Query-block-forward latency simulates a document pre-encoding setting, where document-side KV states are assumed to be cached and online computation only performs query-side forward computation and query-to-document scoring.

# Docs | End-to-End | Full-Forward | Query-Forward  
---|---|---|---  
30 | 0.96s | 0.82s | 0.016s  
50 | 1.18s | 1.02s | 0.017s  
100 | 2.92s | 2.71s | 0.022s  
200 | 5.02s | 4.76s | 0.029s  
300 | 7.28s | 7.01s | 0.037s  
500 | 12.00s | 11.72s | 0.050s  
  
Table 2: Latency breakdown of CompRank (Segment-10) on TREC-COVID. Query-forward simulates online computation with pre-encoded document-side KV states.

As shown in Table 2, end-to-end latency is dominated by full model forward computation. When the number of candidate documents increases from 30 to 500, end-to-end latency grows from 0.96s/query to 12.00s/query, closely tracking full-forward latency, which grows from 0.82s/query to 11.72s/query. By contrast, the non-model overhead remains small, increasing only from roughly 0.14s/query to 0.28s/query. This indicates that the observed scaling cost mainly comes from recomputing document blocks rather than dataloading, padding, parsing, or metric computation. Query-block-forward latency grows much more slowly, from 0.016s/query at 30 candidates to only 0.050s/query at 500 candidates. This highlights the potential benefit of document-side pre-encoding: if document KV states can be computed offline and reused during online reranking, the remaining online forward computation becomes substantially smaller. At 500 candidates, query-block-forward latency is 234×234\times lower than full-forward latency. We emphasize that this is a simulated pre-encoding analysis rather than a fully optimized serving implementation, since a real system must also account for KV-cache storage, loading, and memory-transfer overhead. Nevertheless, the breakdown suggests that CompRank’s document-decoupled design provides a practical path toward low-latency online reranking when paired with system-level KV caching.

###  5.3 Effect of CopyNet Supervision

Figure 3: Training dynamics of CopyNet and SFT supervision. CopyNet accuracy measures whether the positive document receives the highest attention-derived score, while decode accuracy measures whether SFT decoding predicts the positive identifier.

We analyze whether CopyNet-style supervision provides an effective training signal for attention-based reranking, and compare it with a standard SFT objective that learns to generate the positive document identifier. The two objectives optimize different output spaces: SFT performs token-level language modeling over the full vocabulary, whereas CopyNet optimizes a pointer distribution over the input candidate documents using attention-derived scores. Therefore, the loss magnitudes are not directly comparable, but their training trends and the corresponding selection accuracies reveal how easily each objective aligns with document-level relevance.

Figure 3 shows the training dynamics of both objectives. For CopyNet, we define accuracy as the proportion of training examples where the ground-truth positive document receives the highest attention-derived score among all candidates. For SFT, decode accuracy measures whether the decoded document identifier matches the ground-truth positive document. We observe that both CopyNet loss and SFT loss decrease steadily, suggesting that both objectives are learnable under the same training setting. However, CopyNet achieves consistently higher selection accuracy than SFT decoding, with CopyNet accuracy rising to around 70%70\% while decode accuracy remains slightly lower. This behavior supports the use of CopyNet as an effective supervision signal for attention-based reranking. By restricting the prediction space to the input candidate documents, CopyNet directly supervises document-level scores rather than requiring the model to generate identifiers through the language modeling head. Since the same attention-derived scores are used for inference-time ranking, this objective naturally aligns training with the decoding-free scoring mechanism of CompRank. Overall, the results suggest that CopyNet supervision helps the model allocate attention-based scores toward relevant candidates and provides a direct training signal for document-level reranking.

##  6 Conclusion

We presented CompRank, a token-efficient reranking framework for long-list LLM-based reranking. CompRank reduces redundant computation by decoupling document representations, applying segment-wise token compression, and replacing autoregressive identifier decoding with attention-based scoring trained via a CopyNet-style objective. Experiments on seven BEIR datasets show that segment-wise compression preserves most of the full-token reranking performance while retaining only 10.2% of document tokens. The comparison across compression strategies further suggests that maintaining global document coverage is more effective than relying solely on final tokens or document-internal saliency estimates. Additional scaling experiments show that CompRank remains stable when evaluated on candidate lists up to 500 documents after training on 30-document lists, while substantially reducing end-to-end latency compared with generation-based listwise reranking. Overall, our results suggest that token-level compression, document representation decoupling, and training–inference alignment provide a practical direction for scalable decoding-free LLM reranking. Future work includes implementing fully optimized document-side KV caching and exploring adaptive query-conditioned token selection.

## References

  * [1] Y. An, Y. Cheng, S. J. Park, and J. Jiang (2025) HyperRAG: enhancing quality-efficiency tradeoffs in retrieval-augmented generation with reranker kv-cache reuse.  External Links: 2504.02921, [Link](https://arxiv.org/abs/2504.02921) Cited by: §2. 
  * [2] I. Beltagy, M. E. Peters, and A. Cohan (2020) Longformer: the long-document transformer.  External Links: 2004.05150, [Link](https://arxiv.org/abs/2004.05150) Cited by: §2. 
  * [3] S. Chen, B. J. Gutierrez, and Y. Su (2025) Attention in large language models yields efficient zero-shot re-rankers.  In The Thirteenth International Conference on Learning Representations,  External Links: [Link](https://openreview.net/forum?id=yzloNYH3QN) Cited by: §1, §2, §3.1, §4.1. 
  * [4] DeepSeek-AI (2025) DeepSeek-v3.2-exp: boosting long-context efficiency with deepseek sparse attention.  Cited by: §2. 
  * [5] DeepSeek-AI (2026) DeepSeek-v4: towards highly efficient million-token context intelligence.  Cited by: §2. 
  * [6] H. Déjean and S. Clinchant (2025) Reranking with compressed document representation.  External Links: 2505.15394, [Link](https://arxiv.org/abs/2505.15394) Cited by: §2. 
  * [7] Y. Fan, X. Lu, A. Zhao, J. Tong, P. Nie, K. Zou, Y. Ma, W. Zhang, and X. Shen (2026) MiniReranker: efficient multimodal reranking through visual cache reuse and interaction sparsity.  External Links: 2606.10759, [Link](https://arxiv.org/abs/2606.10759) Cited by: §2. 
  * [8] J. Gu, Z. Lu, H. Li, and V. O.K. Li (2016-08) Incorporating copying mechanism in sequence-to-sequence learning.  In Proceedings of the 54th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers), K. Erk and N. A. Smith (Eds.),  Berlin, Germany,  pp. 1631–1640.  External Links: [Link](https://aclanthology.org/P16-1154/), [Document](https://dx.doi.org/10.18653/v1/P16-1154) Cited by: §3.4. 
  * [9] N. Gupta, C. You, S. Bhojanapalli, S. Kumar, I. S. Dhillon, and F. X. Yu (2025) Scalable in-context ranking with generative models.  In The Thirty-ninth Annual Conference on Neural Information Processing Systems,  External Links: [Link](https://openreview.net/forum?id=zj45hoQhjD) Cited by: §1, §2, §3.2, §4.1. 
  * [10] H. Huang, X. Lu, M. Su, X. Zhang, Z. Jiang, P. Nie, K. Zou, T. Pfister, W. Chen, W. Zhang, et al. (2026) MMEB-v3: measuring the performance gaps of omni-modality embedding models.  arXiv preprint arXiv:2604.23321.  Cited by: §1. 
  * [11] P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, H. Küttler, M. Lewis, W. Yih, T. Rocktäschel, et al. (2020) Retrieval-augmented generation for knowledge-intensive nlp tasks.  Advances in neural information processing systems 33,  pp. 9459–9474.  Cited by: §1. 
  * [12] M. Li, E. Gaussier, and G. Zhou (2026) Efficient long-document reranking via block-level embeddings and top-k interaction refinement.  External Links: 2501.17039, [Link](https://arxiv.org/abs/2501.17039) Cited by: §2. 
  * [13] Q. Liu, B. Wang, N. Wang, and J. Mao (2025) Leveraging passage embeddings for efficient listwise reranking with large language models.  In Proceedings of the ACM on Web Conference 2025,  pp. 4274–4283.  Cited by: §2. 
  * [14] X. Lu, H. Huang, R. Meng, Y. Jin, W. Zeng, and X. Shen (2026) Rethinking reasoning in document ranking: why chain-of-thought falls short.  In The Fourteenth International Conference on Learning Representations,  External Links: [Link](https://openreview.net/forum?id=txmqENuRcc) Cited by: §1, §2. 
  * [15] X. Lu, H. Huang, R. Meng, Y. Jin, W. Zeng, and X. Shen (2026) Tools are under-documented: simple document expansion boosts tool retrieval.  In The Fourteenth International Conference on Learning Representations,  External Links: [Link](https://openreview.net/forum?id=g9D9MgG7iW) Cited by: §1. 
  * [16] X. Lu, K. Li, H. Huang, R. Meng, W. Zeng, and X. Shen (2026) Beyond global similarity: multi-conditional retrieval for fine-grained cross-modal understanding.  In Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition,  pp. 9699–9709.  Cited by: §2. 
  * [17] X. Lu, S. Liu, B. Yin, Y. Li, X. Chen, H. Su, Y. Jin, W. Zeng, and X. Shen (2025-11) MultiConIR: towards multi-condition information retrieval.  In Findings of the Association for Computational Linguistics: EMNLP 2025, C. Christodoulopoulos, T. Chakraborty, C. Rose, and V. Peng (Eds.),  Suzhou, China,  pp. 13471–13494.  External Links: [Link](https://aclanthology.org/2025.findings-emnlp.726/), ISBN 979-8-89176-335-7 Cited by: §1. 
  * [18] X. Ma, L. Wang, N. Yang, F. Wei, and J. Lin (2024) Fine-tuning llama for multi-stage text retrieval.  In Proceedings of the 47th International ACM SIGIR Conference on Research and Development in Information Retrieval,  pp. 2421–2425.  Cited by: §2. 
  * [19] R. F. Nogueira, Z. Jiang, R. Pradeep, and J. Lin (2020) Document ranking with a pretrained sequence-to-sequence model.  In EMNLP (Findings),  Cited by: §2. 
  * [20] R. Nogueira, W. Yang, K. Cho, and J. Lin (2019) Multi-stage document ranking with bert.  External Links: 1910.14424, [Link](https://arxiv.org/abs/1910.14424) Cited by: §2. 
  * [21] R. Pradeep, S. Sharifymoghaddam, and J. Lin (2023) RankVicuna: zero-shot listwise document reranking with open-source large language models.  External Links: 2309.15088, [Link](https://arxiv.org/abs/2309.15088) Cited by: §2. 
  * [22] R. Pradeep, S. Sharifymoghaddam, and J. Lin (2023) RankZephyr: effective and robust zero-shot listwise reranking is a breeze!.  External Links: 2312.02724, [Link](https://arxiv.org/abs/2312.02724) Cited by: §2. 
  * [23] Z. Qin, R. Jagerman, K. Hui, H. Zhuang, J. Wu, L. Yan, J. Shen, T. Liu, J. Liu, D. Metzler, X. Wang, and M. Bendersky (2024-06) Large language models are effective text rankers with pairwise ranking prompting.  In Findings of the Association for Computational Linguistics: NAACL 2024, K. Duh, H. Gomez, and S. Bethard (Eds.),  Mexico City, Mexico,  pp. 1504–1518.  External Links: [Link](https://aclanthology.org/2024.findings-naacl.97/), [Document](https://dx.doi.org/10.18653/v1/2024.findings-naacl.97) Cited by: §2. 
  * [24] R. G. Reddy, J. Doo, Y. Xu, M. A. Sultan, D. Swain, A. Sil, and H. Ji (2024) FIRST: faster improved listwise reranking with single token decoding.  In Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing,  pp. 8642–8652.  Cited by: §2. 
  * [25] S. Sharifymoghaddam, R. Pradeep, A. Slavescu, R. Nguyen, A. Xu, Z. Chen, Y. Zhang, Y. Chen, J. Xian, and J. Lin (2025) RankLLM: a python package for reranking with llms.  In Proceedings of the 48th International ACM SIGIR Conference on Research and Development in Information Retrieval,  pp. 3681–3690.  Cited by: §2. 
  * [26] W. Sun, L. Yan, X. Ma, S. Wang, P. Ren, Z. Chen, D. Yin, and Z. Ren (2023) Is chatgpt good at search? investigating large language models as re-ranking agents.  In Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing,  pp. 14918–14937.  Cited by: §2. 
  * [27] W. Sun, L. Yan, X. Ma, S. Wang, P. Ren, Z. Chen, D. Yin, and Z. Ren (2024) Is chatgpt good at search? investigating large language models as re-ranking agents.  External Links: 2304.09542, [Link](https://arxiv.org/abs/2304.09542) Cited by: §4.1. 
  * [28] N. Thakur, N. Reimers, A. Rücklé, A. Srivastava, and I. Gurevych (2021) BEIR: a heterogeneous benchmark for zero-shot evaluation of information retrieval models.  In Thirty-fifth Conference on Neural Information Processing Systems Datasets and Benchmarks Track (Round 2),  External Links: [Link](https://openreview.net/forum?id=wCu6T5xFjeJ) Cited by: §4.1. 
  * [29] L. Tran, Y. Li, R. Florian, and W. Sun (2026) Contrastive retrieval heads improve attention-based re-ranking.  External Links: 2510.02219, [Link](https://arxiv.org/abs/2510.02219) Cited by: §2, §4.1. 
  * [30] J. Wang, C. Wang, Y. Fang, H. Hu, J. Du, A. Li, H. Wu, J. Xu, L. Liu, and D. Liao (2026) HeadRank: decoding-free passage reranking via preference-aligned attention heads.  External Links: 2604.17237, [Link](https://arxiv.org/abs/2604.17237) Cited by: §2. 
  * [31] B. Yin, X. Lu, Z. Qi, and X. Shen (2026) When should queries be decomposed? a stage-aware study of query decomposition for multi-condition retrieval.  External Links: 2606.08577, [Link](https://arxiv.org/abs/2606.08577) Cited by: §2. 
  * [32] M. Zaheer, G. Guruganesh, K. A. Dubey, J. Ainslie, C. Alberti, S. Ontanon, P. Pham, A. Ravula, Q. Wang, L. Yang, et al. (2020) Big bird: transformers for longer sequences.  Advances in neural information processing systems 33,  pp. 17283–17297.  Cited by: §2. 
  * [33] W. Zhang, F. Yin, H. Yen, D. Chen, and X. Ye (2025-11) Query-focused retrieval heads improve long-context reasoning and re-ranking.  In Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing, C. Christodoulopoulos, T. Chakraborty, C. Rose, and V. Peng (Eds.),  Suzhou, China,  pp. 23791–23805.  External Links: [Link](https://aclanthology.org/2025.emnlp-main.1214/), [Document](https://dx.doi.org/10.18653/v1/2025.emnlp-main.1214), ISBN 979-8-89176-332-6 Cited by: §1, §2, §3.1. 
  * [34] Z. Zhi, Y. Zhang, Y. Jing, X. Li, J. Liu, H. Liu, and Y. Ding (2026) Compress-then-rank: faster and better listwise reranking with large language models via ranking-aware passage compression.  Cited by: §2. 
  * [35] C. Zhou, R. Zhang, J. Guo, M. de Rijke, F. Yixing, and X. Cheng (2026) LongRanker: efficient one-pass document reranking with long-context large language models.  In Proceedings of the ACM Web Conference 2026,  pp. 2004–2013.  Cited by: §1, §2, §2. 
  * [36] S. Zhuang, H. Zhuang, B. Koopman, and G. Zuccon (2024) A setwise approach for effective and highly efficient zero-shot ranking with large language models.  In Proceedings of the 47th International ACM SIGIR Conference on Research and Development in Information Retrieval,  pp. 38–47.  Cited by: §2. 



##  Appendix A Implementation Details

###  A.1 CompRank Training Details

We provide the implementation details used in our main CompRank experiments. The main results use Mistral-7B as the backbone model, with 30 candidate documents per query. CompRank derives document scores from attention logits at a fixed Transformer layer. In the Mistral-7B experiments, we use zero-based layer index 20, corresponding to the 21st Transformer block, as the scoring layer. The attention-based score is computed from the query positions in the final block. In our main setting, the effective decision-token set UU contains a single decision token, corresponding to the first supervised token in the completion, i.e., the token at the beginning of the answer sequence. For each candidate document, CompRank first aggregates the softmax-normalized attention mass over the selected document tokens, and then averages the scores across attention heads. Since the main experiments use a single decision token, the aggregation operator Agg\operatorname{Agg} reduces to taking the score of this token. Our implementation also supports aggregation over multiple decision tokens using mean aggregation or log-sum-exp aggregation.

We train CompRank with a temperature-scaled CopyNet objective over candidate documents, using temperature τ=0.05\tau=0.05. The training objective is the CopyNet-style cross-entropy loss defined over attention-derived document scores, and no autoregressive SFT loss is used in the main experiments. Optimization uses AdamW 8-bit with a learning rate of 3.0×10−63.0\times 10^{-6}, weight decay 0, cosine learning-rate scheduling, and a warmup ratio of 0.03. Training is performed in bf16 precision with gradient checkpointing enabled for one epoch. The training set contains 50,000 examples derived from the MS MARCO training split following the BlockRank data construction pipeline. We use a train–validation split ratio of 0.99, resulting in approximately 49,500 training examples and 500 validation examples. The per-device training batch size is 1 and the gradient accumulation step is 4, giving an effective batch size of 4×G4\times G, where GG is the number of GPUs. Each candidate document block is truncated to at most 256 tokens, and each training instance contains 30 candidate documents.

###  A.2 CompRank Input Prompt

Fig. 4 shows the prompt template for CompRank. Unlike Direct-List, CompRank does not require the model to autoregressively generate a complete ranked list of document identifiers. Instead, the prompt places candidate documents before the query and uses the beginning of the answer sequence as the decision position for attention-based scoring.

Input Prompt Template for CompRank Prompt: You will be given a query and a list of documents. Each document will be formatted as CONTENT: <content> | END. Rank passages based on their relevance to the query.   
Documents:   
CONTENT: {document_0} | END   
CONTENT: {document_1} | END   
...   
CONTENT: {document_N-1} | END   
====== Now let’s start! ======   
Find the most relevant document position.   
Query: {query}   
The following document(s) can help answer the query:   
Final Answer:   
[

Figure 4: Input prompt template used for CompRank. The decision token after Final Answer: is used for attention-based document scoring.

###  A.3 Direct-List Prompt and Decoding Setup

Fig. 5 shows the prompt template for the Direct-List baseline. The model is instructed to generate a ranked list of document identifiers in descending order of relevance.

Prompt Template for Direct-List System prompt: You are RankLLM, an intelligent assistant that can rank passages based on their relevance to the query. User prompt: I will provide you with {n} passages, each indicated by a numerical identifier []. Rank the passages based on their relevance to the search query: {query}.   
[1] {passage_1} [2] {passage_2} ... [n] {passage_n}   
Search Query: {query}.   
Rank the {n} passages above based on their relevance to the search query. All the passages should be included and listed using identifiers, in descending order of relevance. The output format should be [] >> [], e.g., [2] >> [1]. Only respond with the ranking results, do not say any word or explain.

Figure 5: Prompt template used for the Direct-List baseline.

##  Appendix B Additional Efficiency Analysis

We provide a more detailed analysis of the efficiency properties of CompRank. The overall efficiency gain comes from four complementary design choices: block-level document decoupling, token-level compression, decoding-free scoring, and reusable document-side representations.

#### Structural sparsity via block decoupling.

Standard listwise rerankers typically concatenate all candidate documents and apply full attention over the entire sequence. Let NN be the number of candidate documents, LL the document block length, and dd the hidden dimension. Full attention over the concatenated document sequence has complexity:

| O​((N​L)2​d).O((NL)^{2}d). |   
---|---|---  
  
CompRank adopts a block-structured attention pattern that removes document–document interactions. Each document block is encoded independently, and the query block interacts with document blocks only during scoring. This reduces the document-side attention complexity to:

| O​(N​L2​d),O(NL^{2}d), |   
---|---|---  
  
which changes the scaling with respect to the number of documents from quadratic to linear. This structural sparsity is the basis for both more efficient computation and reusable document-side states.

#### Token-level compression.

CompRank further reduces the query–document interaction cost by compressing document-side KV states. Let ρ∈(0,1]\rho\in(0,1] denote the retained fraction of document tokens. For an uncompressed block-wise reranker, the query-side computation attends to instruction, query, and document tokens. Assuming for simplicity that |I|≈|Q|≈|D|≈L|I|\approx|Q|\approx|D|\approx L, the interaction cost is proportional to:

| 3​L2.3L^{2}. |   
---|---|---  
  
With token compression, only ρ​|D|\rho|D| document tokens are exposed to query-side attention, reducing the cost to approximately:

| (2+ρ)​L2.(2+\rho)L^{2}. |   
---|---|---  
  
The resulting attention-level speedup is:

| 𝒮=|I|+|Q|+|D||I|+|Q|+ρ​|D|≈32+ρ.\mathcal{S}=\frac{|I|+|Q|+|D|}{|I|+|Q|+\rho|D|}\approx\frac{3}{2+\rho}. |   
---|---|---  
  
With our default Segment-10 setting, ρ≈0.1\rho\approx 0.1, which gives:

| 32.1≈1.43×.\frac{3}{2.1}\approx 1.43\times. |   
---|---|---  
  
This analysis estimates the reduction in attention-level computation. In practice, the observed wall-clock speedup can be smaller because the implementation may still include non-attention computation, kernel overhead, memory movement, and other evaluation overheads. In Sec. 5.2, Segment-10 yields approximately 1.3×1.3\times end-to-end speedup over the full-token CompRank variant, which is consistent with this theoretical estimate.

#### Decoding-free scoring.

Generation-based listwise rerankers require autoregressive decoding to output ranked document identifiers. This introduces sequential generation overhead and may also lead to invalid outputs when the candidate list grows beyond the training setting. In contrast, CompRank derives document scores directly from attention distributions in a single forward pass and sorts the candidate documents according to these scores. This converts reranking from a generative decoding problem into a parallelizable scoring problem. As shown in Sec. 5.2, CompRank achieves 4.9×4.9\times–9.5×9.5\times end-to-end speedup over a decode-ID listwise reranker when scaling from 30 to 500 candidate documents.

#### Reusable document representations.

CompRank also decouples document representations from both candidate order and query context. Since document blocks neither attend to other documents nor to the query block, their KV states can in principle be pre-encoded and reused:

| Ki,Vi=fθ​(Di).K_{i},V_{i}=f_{\theta}(D_{i}). |   
---|---|---  
  
This enables a serving scenario where document-side computation is performed offline or cached across repeated retrieval calls, leaving only query-side computation and query-to-document attention on the online path. Such a design is particularly relevant for RAG and agentic search systems, where the same evidence documents may be retrieved or revisited across multiple reasoning steps.

We emphasize that our current evaluation pipeline still recomputes document blocks for each query. Therefore, the reported latency in Sec. 5.2 should be interpreted as a conservative end-to-end measurement without optimized document-side KV caching. A production implementation with physical KV caching, token gathering, and efficient cache loading could further reduce online reranking cost by removing repeated document encoding from the critical path. At the same time, such a system would need to account for KV-cache storage, memory transfer, and cache lookup overhead, which we leave for future work.

##  Appendix C Complete Baseline Results

Table 3 presents the complete per-dataset results for all retrieval and reranking baselines.

Model | FEVER | DBPedia | FiQA | NFCorpus | SciDocs | SciFact | COVID | Avg.  
---|---|---|---|---|---|---|---|---  
BM25 | 16.5 | 31.8 | 23.6 | 33.8 | 14.9 | 67.9 | 59.5 | 35.4  
RankGPT (Mistral-7B) | 16.7 | 32.9 | 24.1 | 31.0 | 14.7 | 65.5 | 60.6 | 35.1  
ICR (Mistral-7B) | 20.6 | 31.4 | 31.0 | 33.2 | 16.2 | 72.4 | 63.9 | 38.4  
ICR (Qwen2.5-7B) | 19.6 | 35.3 | 27.0 | 32.7 | 16.4 | 71.1 | 66.1 | 38.3  
Corehead (Qwen2.5-7B) | 19.3 | 32.4 | 30.6 | 32.5 | 14.5 | 70.0 | 67.7 | 38.1  
CompRank (Mistral-7B) | 16.6 | 34.8 | 31.7 | 31.7 | 14.3 | 64.2 | 81.2 | 39.2  
  
Table 3: Complete reranking results on seven BEIR datasets. We report NDCG@10.

##  Appendix D Ablation on Layer Selection and Decision Token Selection

###  D.1 Ablation on Transformer Layer Selection

CompRank relies on the internal attention weights of the language model to score documents. Since different Transformer layers capture different levels of abstraction, the choice of layer significantly impacts the ranking performance. We evaluate the Attention Accuracy across all 32 layers of the Mistral-7B model, fixing the decision token to ’[’.

Figure 6: Attention Accuracy across all 32 Transformer layers of Mistral-7B. The metric measures the proportion of queries where the highest attention score is assigned to the positive document. The shaded region marks early layers with near-random performance.

As illustrated in Figure 6, the early layers (layers 0 to 13) exhibit very low Attention Accuracy (approximately 10–20%), indicating that these layers have not yet aggregated sufficient semantic information to distinguish document relevance. Performance rises sharply around layer 14 and remains generally strong throughout the middle-to-late layers (layers 15 to 31), with natural oscillation. We observe the highest peak at zero-based layer index 20, corresponding to the 21st Transformer block, which achieves 68.5% Attention Accuracy. Consequently, we select zero-based layer index 20, corresponding to the 21st Transformer block, as the default scoring layer for all Mistral-7B experiments.

###  D.2 Ablation on Decision Token Selection

The second critical design choice is determining which token(s) in the prompt or generation sequence should be used to aggregate the attention scores over candidate documents. We compare the following five configurations, all evaluated at layer 20:

  * •

Query Token Aggregation: Attention scores are aggregated over the individual query token positions only (excluding non-query tokens).

  * •

Query Block Aggregation: Attention scores are averaged over all tokens in the entire query block.

  * •

’Final’, ’Answer’: Individual tokens from the answer-prefix template are used as the decision token.

  * •

’[’: The first generated token of the output sequence, which opens the listwise ranking output.




Figure 7: Attention Accuracy under different decision token and aggregation strategies (CompRank, Mistral-7B, Layer 20). Query Token Aggregation and Query Block Aggregation aggregate attention over multiple positions, while the remaining three use a single token as the decision point.

Figure 7 shows the Attention Accuracy for each configuration. Query Token Aggregation and Query Block Aggregation achieve 57.2% and 61.4% respectively, demonstrating that aggregating over query-side positions provides a reasonable signal. However, the answer-prefix tokens ’Final’ and ’Answer’ perform substantially worse (29.8% and 31.3%), suggesting that these positions do not concentrate relevance-discriminative attention. The highest Attention Accuracy of 68.1% is achieved by using the first generated token ’[’ as the sole decision token. This token marks the exact moment the model begins producing its ranking output, and its attention distribution appears to be the most focused and informative for document relevance scoring. We therefore adopt ’[’ as the default decision token in all CompRank experiments.

##  Appendix E Analysis of Decoding Errors in Direct-List

In Section 5.2, we observe that the generation-based Direct-List baseline degrades as the candidate list becomes longer. To better understand this behavior, we analyze its decoded identifier sequences on TREC-COVID when the number of candidate documents increases from 30 to 500. Since the Direct-List model is trained with 30-document candidate lists, we first examine whether it can correctly produce valid identifier sequences under the same list size, and then evaluate how the decoding behavior changes under longer candidate lists. We consider four types of decoding errors:

  * •

Duplicate IDs: occur when the same document identifier is generated multiple times within a single ranked list.

  * •

Out-of-range IDs: occur when the model generates an identifier outside the valid candidate range.

  * •

Missing IDs: refer to valid candidate identifiers that are not generated in the output sequence.

  * •

Truncated Output: occurs when the model terminates generation before producing the expected number of identifiers.




These errors directly affect listwise ranking quality because the generated sequence no longer corresponds to a valid permutation of the candidate set.

Table 4: Decoding error statistics of Direct-List on TREC-COVID (50 queries). Percentages indicate the proportion of queries exhibiting each error type.

List Size | Any Error | Duplicate IDs | Out-of-Range IDs | Missing IDs | Truncated Output  
---|---|---|---|---|---  
30 | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%)  
50 | 46 (92.0%) | 17 (34.0%) | 0 (0.0%) | 43 (86.0%) | 32 (64.0%)  
100 | 47 (94.0%) | 21 (42.0%) | 3 (6.0%) | 46 (92.0%) | 33 (66.0%)  
200 | 50 (100.0%) | 29 (58.0%) | 0 (0.0%) | 49 (98.0%) | 36 (72.0%)  
300 | 50 (100.0%) | 31 (62.0%) | 2 (4.0%) | 48 (96.0%) | 43 (86.0%)  
400 | 50 (100.0%) | 39 (78.0%) | 0 (0.0%) | 50 (100.0%) | 36 (72.0%)  
500 | 50 (100.0%) | 33 (66.0%) | 0 (0.0%) | 50 (100.0%) | 41 (82.0%)  
  
Figure 8: Average number of decoding errors per query for Direct-List on TREC-COVID as the number of candidate documents increases. The model produces valid identifier sequences under the 30-document setting seen during training, but decoding errors increase when evaluated on longer candidate lists.

Table 4 reports the proportion of queries affected by each error type, while Figure 8 shows the average number of errors per query. When evaluated with 30 candidates, which matches the training list size, Direct-List produces valid outputs without duplicate, out-of-range, missing, or truncated identifiers. However, once the candidate list grows beyond the training setting, decoding errors appear rapidly. At 50 candidates, 92.0% of queries already contain at least one error; from 200 candidates onward, all queries exhibit decoding errors. Missing identifiers are the dominant failure mode. As shown in Table 4, the proportion of queries with missing IDs increases from 86.0% at 50 candidates to 100.0% at 400 and 500 candidates. Figure 8 further shows that the average number of missing IDs per query grows substantially, reaching 78.2 under the 500-document setting. Duplicate IDs also become frequent, affecting 66.0% of queries at 500 candidates, indicating that the model struggles to maintain a valid one-to-one mapping between generation steps and candidate identifiers. Out-of-range IDs occur less frequently, but their presence shows that the generated sequence is not always constrained to the valid candidate space. Overall, these results suggest that decode-ID listwise reranking has limited extrapolation ability when the inference-time candidate list is substantially longer than the training-time list. Although the model can generate valid identifier sequences for the 30-document setting it was trained on, extending this pattern to 50–500 documents introduces a distribution shift in the output sequence space. As a result, the model increasingly fails to produce a valid permutation of candidate identifiers, providing additional motivation for CompRank’s decoding-free attention-based scoring paradigm.

Case Study: Duplicate and Missing IDs in Decode-ID Reranking Dataset: TREC-COVID Query: How does the coronavirus differ from seasonal flu? Candidate List Size: 50 Expected Output Length: 50 Actual Output Length: 56 Duplicate IDs: [3, 4, 12, 13, 17, 19, 26, 27, 35] Missing IDs: [29, 33, 39] Raw Output Snippet: [1] >> [21] >> [22] >> [20] >> [5] >> [13] >> [26] >> [27] >> [35] >> [4] >> [17] >> [19] >> [3] >> [12] >> [24] >> [18] >> [6] >> [16] >> [25] >> [42] >> [43] >> [7] >> [9] >> [14] >> [8] >> [31] >> [32] >> [28] >> [34] >> [44] >> [48] >> [10] >> [11] >> [15] >> [23] >> [30] >> [36] >> [37] >> [38] >> [40] >> [41] >> [45] >> [46] >> [47] >> [49] >> [50] >> [2] >> [13] >> [26] >> [27] >> [35] >> [4] >> [17] >> [19] >> [3] >> [12] <|im_end|> Observation: The model initially generates many valid identifiers, but later repeats a block of previously generated IDs. This creates both duplicate IDs and missing candidate IDs, so the output no longer forms a valid permutation of the 50 candidate documents.

Figure 9: Qualitative example of decode-ID failure in Direct-List. The model repeats previously generated identifiers and omits several valid candidates when evaluated beyond its 30-document training setting.

Case Study: Severe Coverage Failure under Long Candidate Lists Dataset: TREC-COVID Query: What are the mortality rates overall and in specific populations? Candidate List Size: 300 Expected Output Length: 300 Actual Output Length: 295 Duplicate IDs: [192, 193, 194, ..., 201] Missing IDs: [16, 17, 18, 19, 21, 22, 23, 24, 26, 27, ...] Observation: The model omits a large number of valid identifiers and repeatedly generates a subset of IDs. This indicates that identifier generation becomes increasingly unstable when the output sequence is much longer than those seen during training.

Figure 10: Qualitative example of severe coverage failure for Direct-List under a 300-document candidate list.

##  Appendix F Limitations

CompRank has several limitations. First, our main experiments use Mistral-7B as the primary backbone, and broader validation across more model families remains future work. Second, although document representation decoupling enables reusable document-side KV states in principle, our current evaluation pipeline still recomputes document blocks and does not implement a fully optimized KV-caching system. Third, static segment-wise compression may be suboptimal when relevance evidence is sparse or highly localized, where adaptive query-conditioned token selection could be more effective. Finally, our results are based on single-run experiments due to computational constraints, and future work should include more extensive statistical evaluation.

Experimental support, please [view the build logs](./2606.11700v1/__stdout.txt) for errors. Generated by [ L A T E xml ](https://math.nist.gov/~BMiller/LaTeXML/). 

## Instructions for reporting errors

We are continuing to improve HTML versions of papers, and your feedback helps enhance accessibility and mobile support. To report errors in the HTML that will help us improve conversion and rendering, choose any of the methods listed below:

  * Click the "Report Issue" ( ) button, located in the page header.



**Tip:** You can select the relevant text first, to include it in your report.

Our team has already identified [the following issues](https://github.com/arXiv/html_feedback/issues). We appreciate your time reviewing and reporting rendering errors we may not have found yet. Your efforts will help us improve the HTML versions for all readers, because disability should not be a barrier to accessing research. Thank you for your continued support in championing open access for all.

Have a free development cycle? Help support accessibility at arXiv! Our collaborators at LaTeXML maintain a [list of packages that need conversion](https://github.com/brucemiller/LaTeXML/wiki/Porting-LaTeX-packages-for-LaTeXML), and welcome [developer contributions](https://github.com/brucemiller/LaTeXML/issues).

BETA

[ ](javascript:toggleReadingMode\(\); "Disable reading mode, show header and footer")
