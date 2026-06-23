<!-- Source: https://arxiv.org/html/2407.02485v1 | Tier: A | Topic: rag-reranking | Fetched: 2026-06-23 -->

  1. [1 Introduction](https://arxiv.org/html/2407.02485v1#S1 "In RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
  2. [2 Related Work](https://arxiv.org/html/2407.02485v1#S2 "In RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
     1. [3 Preliminaries](https://arxiv.org/html/2407.02485v1#S3 "In 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
        1. [3.1 Problem Setup](https://arxiv.org/html/2407.02485v1#S3.SS1 "In 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
        2. [3.2 Limitation of Current RAG Pipelines](https://arxiv.org/html/2407.02485v1#S3.SS2 "In 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
           1. [4 RankRAG](https://arxiv.org/html/2407.02485v1#S4 "In 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
              1. [4.1 Stage-I: Supervised Fine-Tuning (SFT)](https://arxiv.org/html/2407.02485v1#S4.SS1 "In 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
              2. [4.2 Stage-II: Unified Instruction-Tuning for Ranking and Generation](https://arxiv.org/html/2407.02485v1#S4.SS2 "In 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
              3. [4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline](https://arxiv.org/html/2407.02485v1#S4.SS3 "In 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                 1. [5 Experiments](https://arxiv.org/html/2407.02485v1#S5 "In 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                    1. [5.1 Experiment Setup](https://arxiv.org/html/2407.02485v1#S5.SS1 "In 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                       1. [Tasks and Datasets.](https://arxiv.org/html/2407.02485v1#S5.SS1.SSS0.Px1 "In 5.1 Experiment Setup ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                    2. [5.2 Main Experiments](https://arxiv.org/html/2407.02485v1#S5.SS2 "In 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                    3. [5.3 Ablation Studies](https://arxiv.org/html/2407.02485v1#S5.SS3 "In 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                       1. [5.4 Experiment on Domain-specific RAG Benchmarks](https://arxiv.org/html/2407.02485v1#S5.SS4 "In 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                          1. [5.5 A Closer Look at the Ranking Module](https://arxiv.org/html/2407.02485v1#S5.SS5 "In 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                             1. [5.6 Case Study](https://arxiv.org/html/2407.02485v1#S5.SS6 "In 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                1. [6 Conclusion](https://arxiv.org/html/2407.02485v1#S6 "In 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                   1. [A Dataset Description](https://arxiv.org/html/2407.02485v1#A1 "In 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      1. [A.1 Main Experiments](https://arxiv.org/html/2407.02485v1#A1.SS1 "In Appendix A Dataset Description ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      2. [A.2 Biomedical Benchmarks](https://arxiv.org/html/2407.02485v1#A1.SS2 "In Appendix A Dataset Description ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                   2. [B Data Blending Details for Ranking-enhanced Instruction Finetuning](https://arxiv.org/html/2407.02485v1#A2 "In 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                   3. [C Prompt Formats of Instruction Tuning](https://arxiv.org/html/2407.02485v1#A3 "In 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      1. [C.1 Stage I: Supervised Fine-tuning](https://arxiv.org/html/2407.02485v1#A3.SS1 "In Appendix C Prompt Formats of Instruction Tuning ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      2. [C.2 Stage-II: Unified Instruction-Tuning for Ranking and Generation](https://arxiv.org/html/2407.02485v1#A3.SS2 "In Appendix C Prompt Formats of Instruction Tuning ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                   4. [D Prompt Formats of Target Tasks](https://arxiv.org/html/2407.02485v1#A4 "In 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      1. [D.1 Context Ranking](https://arxiv.org/html/2407.02485v1#A4.SS1 "In Appendix D Prompt Formats of Target Tasks ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      2. [D.2 RAG](https://arxiv.org/html/2407.02485v1#A4.SS2 "In Appendix D Prompt Formats of Target Tasks ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                   5. [E Additional Experiment Results](https://arxiv.org/html/2407.02485v1#A5 "In 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      1. [E.1 Ranking Performance Using DPR and Contriever as Retrievers ℛ\mathcal{R}](https://arxiv.org/html/2407.02485v1#A5.SS1 "In Appendix E Additional Experiment Results ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                      2. [E.2 RAG Performance with Different kk](https://arxiv.org/html/2407.02485v1#A5.SS2 "In Appendix E Additional Experiment Results ‣ 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                   6. [F Performance of NQ and Trivia QA on DPR Splits](https://arxiv.org/html/2407.02485v1#A6 "In 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")
                                   7. [G Additional Case Studies](https://arxiv.org/html/2407.02485v1#A7 "In 6 Conclusion ‣ 5.6 Case Study ‣ 10\(a\) ‣ 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")



# RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs

Yue Yu   
Georgia Tech   
&Wei Ping ∗   
NVIDIA   
&Zihan Liu   
NVIDIA   
&Boxin Wang   
NVIDIA   
&Jiaxuan You   
NVIDIA   
Chao Zhang   
Georgia Tech   
&Mohammad Shoeybi   
NVIDIA   
&Bryan Catanzaro   
NVIDIA Yue Yu did this work during an internship at NVIDIA. Correspondence to: Yue Yu <yueyu@gatech.edu>, Wei Ping <wping@nvidia.com>.

###### Abstract

Large language models (LLMs) typically utilize the top-_k_ contexts from a retriever in retrieval-augmented generation (RAG). In this work, we propose a novel instruction fine-tuning framework RankRAG, which instruction-tunes a single LLM for the dual purpose of context ranking and answer generation in RAG. In particular, the instruction-tuned LLMs work surprisingly well by adding a small fraction of ranking data into the training blend, and outperform existing expert ranking models, including the same LLM exclusively fine-tuned on a large amount of ranking data. For generation, we compare our model with many strong baselines, including GPT-4-0613, GPT-4-turbo-2024-0409, and ChatQA-1.5, an open-sourced model with the state-of-the-art performance on RAG benchmarks. Specifically, our Llama3-RankRAG significantly outperforms Llama3-ChatQA-1.5 and GPT-4 models on nine knowledge-intensive benchmarks. In addition, it also performs comparably to GPT-4 on five RAG benchmarks in the biomedical domain without instruction fine-tuning on biomedical data, demonstrating its superb capability for generalization to new domains.

##  1 Introduction

Retrieval-augmented generation (RAG) (Lewis et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib46); Izacard & Grave, [2021](https://arxiv.org/html/2407.02485v1#bib.bib25); Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49); Wang et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib82)) is a widely used technique for customizing large language models (LLMs) to handle long-tail knowledge (Mallen et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib55); Asai et al., [2024b](https://arxiv.org/html/2407.02485v1#bib.bib5)), provide up-to-date information (Kasai et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib36)), and adapt to specific domains and tasks (Xiong et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib90)) without modifying the model weights. In general, a dense embedding based retriever (Karpukhin et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib35); Lin et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib48); Wang et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib83)) first retrieves top-_k_ chunked contexts from a collection documents or external database for a given question. Then, LLM reads the top-_k_ contexts to generate the answer.

However, the current RAG pipeline has the following limitations: _i)_ LLMs are not good at reading too many chunked contexts (e.g., top-100) even with the long-context window, not only due to efficiency reasons, but also because a shorter list of top-_k_ (e.g., 5, 10) contexts usually leads to higher accuracy of generation (e.g., see Table 5 in Xu et al., [2024b](https://arxiv.org/html/2407.02485v1#bib.bib92)). _ii)_ Given a small kk, one needs a mechanism to ensure the _high recall_ of relevant contents. Relying solely on a retrieval model may be inadequate due to challenges in learning effective local alignments across the entire embedding space to support accurate matching (Luan et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib52)). In practice, a separate ranking model (Nogueira et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib61); Glass et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib19); Ma et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib54)) that cross-encodes question and candidate context can work better than a dense embedding-based retriever for obtaining the most relevant top-_k_ contexts from top-_N_ candidates (_N_ ≫\gg _k_). _iii)_ However, the zero-shot generalization capability of the expert ranking model can be relatively limited compared to the versatile LLM itself.

Based on the above considerations, our goal is to design an RAG instruction tuning pipeline that uses a single language model to achieve both high-recall context extraction and high-quality content generation. In previous study, instruction-tuned LLMs demonstrate a strong ability to extract answers from relevant context for a given question (e.g., OpenAI, [2023](https://arxiv.org/html/2407.02485v1#bib.bib63); Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50); Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49)). This capability can be viewed as the “dual capability” of determining whether a chunk of context is relevant to the question thus is useful for generating the answer. We hypothesize that these capabilities mutually enhance each other. Motivated by this insight, we propose RankRAG, which intruction-tunes a single LLM for both context ranking and answer generation in RAG framework. Furthermore, RankRAG expands upon existing instruction-tuning data by incorporating context-rich QA, retrieval-augmented QA and ranking datasets, enhancing the LLM’s ability to filter out irrelevant contexts during both the retrieval and generation phases of RAG.

Our contribution can be summarized as follows:

  * •

We propose RankRAG, a novel framework that enhances LLM’s RAG capability through simultaneously instructing the LLM on context ranking and answer generation. During training, we design a specialized task focused on identifying relevant contexts or passages for a given question. This task is structured for ranking and framed as regular question answering with instruction, aligning more effectively with retrieval-augmented generation tasks. At inference, the LLM first reranks the retrieved contexts, then generates answer based on the refined top-_k_ (e.g., 5). This framework is readily applicable to diverse knowledge-intensive NLP tasks.

  * •

Remarkably, we observe that integrating a small fraction of ranking data into the instruction tuning blend of LLM works surprisingly well on the evaluations of ranking associated with the RAG tasks, even surpassing the LLMs fine-tuned with 10×10\times more ranking data. We attribute this success to the transferable design of RankRAG training.

  * •

We extensively compare the proposed RankRAG method with several strong baselines, including the open-sourced ChatQA-1.5. On nine general-domain and five biomedical knowledge-intensive benchmarks for RAG, Llama3-RankRAG-8B and Llama3-RankRAG-70B outperforms Llama3-ChatQA-1.5-8B and Llama3-ChatQA-1.5-70B by a margin, respectively.




In the remainder of the paper, we discuss related work in § [2](https://arxiv.org/html/2407.02485v1#S2 "2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"). We introduce problem setup in § [3](https://arxiv.org/html/2407.02485v1#S3 "3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") and RankRAG method in § [4](https://arxiv.org/html/2407.02485v1#S4 "4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"). We present the experimental setup in § [5](https://arxiv.org/html/2407.02485v1#S5 "5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"), and conclude the paper in § [6](https://arxiv.org/html/2407.02485v1#S6 "6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs").

##  2 Related Work

Retrieval-augumented generation (RAG) has been established for knowledge-intensive NLP tasks (Lewis et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib46); Borgeaud et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib8); Izacard et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib27); Izacard & Grave, [2021](https://arxiv.org/html/2407.02485v1#bib.bib25)). In the standard process, a standalone dense-embedding-based retriever (e.g., Karpukhin et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib35)) first retrieves relevant information from an external corpus, which the LLM then utilizes in the generation process. To improve this pipeline, recent research has focused on aligning retrievers to the needs of LLMs for generation (Shi et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib74); Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49)), designing multi-step retrieval processes (Trivedi et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib80); Jiang et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib30); Jeong et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib28); Shao et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib73)), or filtering irrelevant contexts (Wang et al., [2023c](https://arxiv.org/html/2407.02485v1#bib.bib86); Yoran et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib94); Xu et al., [2024a](https://arxiv.org/html/2407.02485v1#bib.bib91)). To improve generation, several studies have designed instruction-tuning methods dedicated to enhancing the search (Ma et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib54); Zhu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib101); Muennighoff et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib60)) and RAG capability of LLMs (Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50); Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49); Luo et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib53); Asai et al., [2024a](https://arxiv.org/html/2407.02485v1#bib.bib4); Wang et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib82)).

Although strong retrievers have been introduced (e.g., Lin et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib48); Yu et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib98); Wang et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib83), [2023a](https://arxiv.org/html/2407.02485v1#bib.bib84); Lee et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib45)), one potential approach to improve retriever is optimizing it along with LLM in an end-to-end manner (e.g., Guu et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib20); Shi et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib74); Sachan et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib72); Izacard et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib27)). However, this requires surrogate loss for optimization and complicates the training pipeline, especially when the embedding database needs to be re-indexed frequently due to the update of the embedding model (i.e., retriever).

Ranking serves as an intermediate step to improve the quality of information retrieval (Mitra et al., [2018](https://arxiv.org/html/2407.02485v1#bib.bib59)), and has been applied to RAG pipeline for improving generation quality (Glass et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib19); Ram et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib70)). However, these methods still rely on an additional moderate-sized model (e.g. BERT, T5) for ranking, which is often insufficient to capture the relevance between query and contexts and may lack the zero-shot generalization capability. Although recent studies have demonstrated the strong ability of LLMs at ranking tasks (Khalifa et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib37); Qin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib68); Sun et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib75)), how to harvest this ability for the RAG pipeline remains underexplored.

(a) Performance of ChatQA-1.5, one of the strongest RAG model, on different context size kk. We observe a trade-off of selecting top-kk contexts: a smaller kk compromises the recall, while a larger kk could introduce irrelevant or noisy context and mislead the LLM generation. 

##  3 Preliminaries

In this section, we first introduce the preliminaries of retrieval-augmented generation as well as the problem setup. Then we present the limitations in the current RAG pipeline, which motivates the proposed RankRAG method.

###  3.1 Problem Setup

In retrieval-augmented generation, a collection of documents or contexts (e.g. Wikipedia) is given, providing the grounded knowledge. Given a question qq, the retriever ℛ\mathcal{R} (e.g., a parameterized embedding model) first retrieves top-kk contexts 𝒞={c1,⋯,ck}\mathcal{C}=\\{c_{1},\cdots,c_{k}\\} that are most relevant to the question. Subsequently, the language model produces the final answer where the answer can either be a short phrase or a long sentence, depending on the type of the target task. Our focus is on autoregressive language models (OpenAI, [2022](https://arxiv.org/html/2407.02485v1#bib.bib62), [2023](https://arxiv.org/html/2407.02485v1#bib.bib63); Meta-AI, [2024](https://arxiv.org/html/2407.02485v1#bib.bib57)), which is the most common architectures for LLMs.

###  3.2 Limitation of Current RAG Pipelines

Before formally introducing RankRAG, we would like to first pinpoint several limitations of the current “retrieve-then-generate” pipeline with large language models.

Limited Capacity of Retriever. Current RAG systems usually employ sparse retrieval (e.g. BM25 (Robertson et al., [2004](https://arxiv.org/html/2407.02485v1#bib.bib71))) or moderate-size (e.g. BERT-based) embedding model (Karpukhin et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib35); Lin et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib48); Wang et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib83)) as the retriever ℛ\mathcal{R}, mainly due to efficiency consideration as there are often millions of, if not more, documents need to be indexed. These models encode questions and documents _independently_ and calculate the similarity between question and documents using vector similarity metrics. However, the _limited capacity of embedding model_ and _independent processing of query and documents_ constrain the ability to estimate textual relevance between question qq and documents dd, reducing their effectiveness in new tasks or domains, verified by both theoretical (Menon et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib56)) and empirical (Luan et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib52); Thakur et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib76)) studies.

Trade-off of Picking Top-_k_ Contexts. Although the state-of-the-art long-context LLM can take many retrieved contexts as input for answer generation, the performance quickly saturates with increased kk in practice. For example, Xu et al. ([2024b](https://arxiv.org/html/2407.02485v1#bib.bib92)) finds the optimal number of chunked context kk is around 1010 for long document QA tasks. As illurstrated in Figure [4(a)](https://arxiv.org/html/2407.02485v1#S2.F4.sf1 "In 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"), we perform evaluation on ChatQA-1.5 (Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50)), one of the strongest RAG model with open weights, and find the saturation of accuracy when k=10k=10. In general, a smaller kk often fails to capture all relevant information, compromising the _recall_ , given the limited expressibility of retriver. In contrast, a larger kk improves _recall_ but at the cost of introducing irrelevant content that hampers the LLM’s ability to generate accurate answers (Yoran et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib94); Yu et al., [2023b](https://arxiv.org/html/2407.02485v1#bib.bib96)).

##  4 RankRAG

To address the limitations mentioned in the previous section, we propose the RankRAG method to enhance the LLM’s ability for retrieval-augmented generation. Specifically, we instruction-tune the LLM to simultaneously _capture the relevance between the question and context_ and _utilize the retrieved context for answer generation_. The details are introduced as follows.

Figure 4: Two-stage instruction tuning framework for RankRAG. 

###  4.1 Stage-I: Supervised Fine-Tuning (SFT)

It is observed that general instruction-tuning or supervised fine-tuning (SFT) often significantly improves the ability of LLMs to follow instructions, thus improving zero-shot results on various downstream tasks (Wei et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib87); Ouyang et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib65)). As such, we follow existing works (Chung et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib11); Wang et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib82); Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50)) to first leverage SFT on a blend of high quality instruction following datasets, including: _i)_ a _private crowd-sourced conversational dataset_ and _public conversation datasets_ : OpenAssistant (Köpf et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib43)), Dolly (Conover et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib12)), and SODA (Kim et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib39)), _ii)_ _a long-form QA dataset_ ELI5 that requires elaborate answers (Fan et al., [2019](https://arxiv.org/html/2407.02485v1#bib.bib17)), _iii)_ _LLM-generated instructions_ : Self-Instruct (Wang et al., [2023b](https://arxiv.org/html/2407.02485v1#bib.bib85)) and Unnatural Instructions (Honovich et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib23)), _iv)_  _FLAN and Chain-of-thought datasets_ (Chung et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib11)).

There are overall 128K SFT examples in total. We make sure that there is _no overlap_ between SFT data and data from evaluation tasks. For each sample in the instruction-following dataset, we take the multi-turn conversational format, use the previous turns of conversation between the user and the assistant as the context, and compute the loss only at the last response from the assistant.

###  4.2 Stage-II: Unified Instruction-Tuning for Ranking and Generation

The Stage-I SFT enpowers the LLMs with basic instruction-following capabilities; however, their performance on RAG tasks often remains suboptimal, as the LLMs are not optimized for extracting answers from retrieved context for a given question. Although recent studies (Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49); Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50); Zhang et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib99)) enhance the RAG capability of LLM by instruction tuning it on context-rich generation tasks, these approaches can still be ineffective with poor initial retrieval results. RankRAG instruction tunes the LLM for both retrieval-augmented generation and context ranking. In particular, the context ranking capability is crucial to obtain more relevant top-_k_ context with imperfect retriever.

To achieve this goal, the instruction tuning blend of Stage-II consists the following five parts:

1) SFT data from Stage-I. This part is included to maintain LLM’s instruction-following capability.

2) Context-rich QA data. We first follow Liu et al. ([2024](https://arxiv.org/html/2407.02485v1#bib.bib50)) to leverage multiple context-rich QA tasks to enhance the LLM’s capability of using context for generation. The training blend we use consists of: _i_) standard QA and reading comprehension datasets: DROP (Dua et al., [2019](https://arxiv.org/html/2407.02485v1#bib.bib16)), NarrativeQA (Kočiskỳ et al., [2018](https://arxiv.org/html/2407.02485v1#bib.bib41)), Quoref (Dasigi et al., [2019](https://arxiv.org/html/2407.02485v1#bib.bib13)), ROPES (Lin et al., [2019](https://arxiv.org/html/2407.02485v1#bib.bib47)), NewsQA (Trischler et al., [2017](https://arxiv.org/html/2407.02485v1#bib.bib79)), TAT-QA (Zhu et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib100)), which contains a question, a golden context and an answer. _ii_) conversational QA datasets: HumanAnnotatedConvQA and SyntheticConvQA open-sourced by Liu et al. ([2024](https://arxiv.org/html/2407.02485v1#bib.bib50)), which contains a conversation between user and assistant, as well as one background document. The model needs to generate an answer given the conversation history and document.

3) Retrieval-augmented QA data. In addition to the above QA datasets used in Liu et al. ([2024](https://arxiv.org/html/2407.02485v1#bib.bib50)), we add two datasets with not only gold context but also the top-retrieved context using BM25. Note that, it is crucial to improve LLM’s robustness over irrelevant context at generation. Being aware of this, we consider two QA tasks, namely SQuAD (Rajpurkar et al., [2016](https://arxiv.org/html/2407.02485v1#bib.bib69)) and WebQuestions (Berant et al., [2013](https://arxiv.org/html/2407.02485v1#bib.bib7)). For each question with the answer, we combine the gold context with the top-retrieved contexts using BM25, ensuring a total of five contexts. Note that some retrieved contexts may not contain the answer, and could be the “hard-negative” contexts.

4) Context ranking data. To empower LLMs with ranking capabilities, we use the popular MS MARCO passage (context) ranking dataset (Bajaj et al., [2016](https://arxiv.org/html/2407.02485v1#bib.bib6)). We treat the gold query-passage pairs (q,c+)(q,c^{+}) as relevant while using hard negative passages (q,c−)(q,c^{-}) mined via BM25 as irrelevant pairs. The LLM need to generate “True” or “False” given the corresponding query-passage pair, where the question along with the task-specific instruction is “For the question {question}, access whether the passage is relevant to the question.”.

We want to handle ranking in conversational senario as well. While MS MARCO spans various topics, the questions are only single-turn short sentences. However, ranking data are only available, if any, at a small amount for conversation QA. To overcome this limitation, we repurpose the conversational QA pairs to generate pseudo relevance pairs. As each conversation is only associated with _one_ document dd, we cut each document into 150-word chunks (c1,c2,…,cn)(c_{1},c_{2},\ldots,c_{n}). We compute the 4-gram recall score between each chunk cic_{i} and the ground-truth answer aa, considering segments with a recall score above 0.5 as relevant and those below 0.1 as irrelevant for the corresponding conversation. Note that, each sample contains one question-context pair for this ranking dataset. In total, there are around 50k ranking pairs from MS MARCO ranking and synthetic conversations for instruction finetuning.

5) Retrieval-augmented ranking data. We aim to train the LLM with the capability of determining the relevance of multiple contexts simultaneously given a question, which is closer to the test-time behavior of RAG with top-_k_ contexts. As before, we utilize two QA datasets, SQuAD (Rajpurkar et al., [2016](https://arxiv.org/html/2407.02485v1#bib.bib69)) and WebQuestions (Berant et al., [2013](https://arxiv.org/html/2407.02485v1#bib.bib7)). We combine the gold context with the top-retrieved contexts using BM25, ensuring a total of five contexts. The contexts containing the answer are considered relevant, and the LLM is trained to _explicitly_ identify all relevant contexts for the question.

Table 1: The instruction template for Stage-II. It is worth noting that all the tasks can be unified in the (x,c,y)(x,c,y) format, which is able to facilitate effective knowledge transfer across tasks. 

Task |  Question xx |  Context cc |  Answer yy  
---|---|---|---  
Context-rich QA |  Answer the following question from context. {question} |  Passage: {Passage} (1 Psg.) |  A phrase/sentence  
Retrieval-augmented QA |  Answer the following question from context. {question} |  Passage 1: {Passage 1}… |  A phrase/sentence  
Passage 5: {Passage 5} (5 Psg. total)  
Context ranking |  For the question {question}, access whether the passage is relevant to the question. |  Passage: {Passage} (1 Psg.) |  True/False  
Retrieval-augmented ranking |  For the question {question}, find all passages from |  Passage 1: {Passage 1}… |  Passage Indexes  
the context that are relevant to the question. |  Passage 5: {Passage 5} (5 Psg. total)  
  
Unifying RAG and ranking with instruction tuning. It is worth noting that, despite the variety of datasets and tasks described, they can all be cast into a standardized QA format (x,c,y)(x,c,y), where xx is the question, cc is the corresponding context, and yy is the target output answer. For example, for the retrieval-augmented ranking data, the question is “ _For the question <question>, find all the passages from the context that are relevant to the question_.” Table [1](https://arxiv.org/html/2407.02485v1#S4.T1 "Table 1 ‣ 4.2 Stage-II: Unified Instruction-Tuning for Ranking and Generation ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") exhibits how to cast different tasks into a unified format. Despite its simplicity, this approach has the following advantages: _i_) It empowers the LLM with the ranking capability by adding relatively small amount of ranking data. _ii_) By standardizing these tasks into a unified format, they can _mutually enhance_ each other. After that, we obtain the final RankRAG model that can be applied to various knowledge-intensive NLP tasks.

###  4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline

As RankRAG incorporates an additional reranking step, the inference pipeline for each question is modified as a _retrieve-rerank-generate_ pipeline, described as follows: (1) the retriever ℛ\mathcal{R} first retrieves top-NN contexts from the corpus. (2) the RankRAG model calculates the relevance score between the question and retrieved NN contexts as the probability of generating the answer as True using the prompt in Table [1](https://arxiv.org/html/2407.02485v1#S4.T1 "Table 1 ‣ 4.2 Stage-II: Unified Instruction-Tuning for Ranking and Generation ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"), then reranks contexts to only retain top-kk (k≪Nk\ll N) contexts, which are then used as the input for the generation step. (3) The top-kk contexts, along with the question, are concatenated and fed back into the RankRAG model to generate the final answer.

Efficiency Discussion. We are aware that the addition of a reranking step introduces extra processing time. In practice, for each question, denote the time for indexing and retrieval as t1t_{1}, the time for using LLM to calculate the relevance score as t2t_{2} and the time for generation as t3t_{3}, then the ratio of added time overhead is N∗t2t1+t3\frac{N*t_{2}}{t_{1}+t_{3}}. In practice, calculating relevance typically requires generating just one token and involves much shorter inputs compared to the generation step with top-_k_ contexts. We provide efficiency study in §[5.5](https://arxiv.org/html/2407.02485v1#S5.SS5 "5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG BenchmarksIn 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs").

##  5 Experiments

In this section, we conduct comprehensive experiments on a variety of knowledge-intensive NLP tasks to demonstrate the zero-shot capabilities of RankRAG.

###  5.1 Experiment Setup

#### Tasks and Datasets.

We consider 3 types of tasks in experiments: (1) _Open-domain QA_ (OpenQA), which includes NQ (Kwiatkowski et al., [2019](https://arxiv.org/html/2407.02485v1#bib.bib42)), TriviaQA (Joshi et al., [2017](https://arxiv.org/html/2407.02485v1#bib.bib34)), PopQA (Mallen et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib55)), HotpotQA (Yang et al., [2018](https://arxiv.org/html/2407.02485v1#bib.bib93)) and 2WikimQA (Ho et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib22)). The first three are single-hop QA tasks, while the last two are multi-hop QA datasets. For NQ, TriviaQA, and HotpotQA, we use the split from KILT benchmark (Petroni et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib67)) 111The results of NQ and TriviaQA using the split from DPR (Karpukhin et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib35)) are in Appendix [F](https://arxiv.org/html/2407.02485v1#A6 "Appendix F Performance of NQ and Trivia QA on DPR Splits ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs").. (2)  _Fact verification_ , where we use FEVER (Thorne et al., [2018](https://arxiv.org/html/2407.02485v1#bib.bib77)) from KILT benchmark. (3)  _Conversational QA_ (ConvQA), we consider three datasets including Doc2Dial (Feng et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib18)), TopiOCQA (Adlakha et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib1)) and INSCIT (Wu et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib89)), which have long documents that cannot be fitted directly into LLMs thus necessitates retrieval and ranking. The detailed dataset information is in Appendix [A.1](https://arxiv.org/html/2407.02485v1#A1.SS1 "A.1 Main Experiments ‣ Appendix A Dataset Description ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs").

Baselines. We consider the following baselines: (1) _Baseline LLMs without RAG_ , where we consider LLMs trained with proprietary data including InstructGPT (Ouyang et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib65)), PaLM 2 (Anil et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib2)), FLAN-LaMDA (Longpre et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib51)), GLaM (Du et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib15)), Claude 2 (Anthropic, [2023](https://arxiv.org/html/2407.02485v1#bib.bib3)), Mixtral-8x22B-Instruct (Mistral, [2024](https://arxiv.org/html/2407.02485v1#bib.bib58)), DeepSeek-V2 Chat (DeepSeek, [2024](https://arxiv.org/html/2407.02485v1#bib.bib14)) and only use the official reported results. We also consider two ChatGPT-series models, namely GPT-3.5-turbo (gpt-3.5-turbo-0613) (OpenAI, [2022](https://arxiv.org/html/2407.02485v1#bib.bib62)) and GPT-4 (gpt-4-0613) (OpenAI, [2023](https://arxiv.org/html/2407.02485v1#bib.bib63)). (2)  _Baselines with retrieval_ , we evaluate models augmented with retrieval. Specifically, we include Atlas (Izacard et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib27)) and Raven (Huang et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib24)), two RAG models based on encoder-decoder LMs. For decoder-only models, we consider Self-RAG (Asai et al., [2024a](https://arxiv.org/html/2407.02485v1#bib.bib4)), RECOMP (Xu et al., [2024a](https://arxiv.org/html/2407.02485v1#bib.bib91)), InstructRetro (Wang et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib82)), RePlug (Shi et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib74)), RA-DIT (Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49)), Llama-3-instruct (Meta-AI, [2024](https://arxiv.org/html/2407.02485v1#bib.bib57)) and ChatQA-1.5 (Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50)). We also list the result of RAG pipelines using InstructGPT (175B parameters) as the backbone including GenRead (Yu et al., [2023a](https://arxiv.org/html/2407.02485v1#bib.bib95)), Retrieve-read (Lazaridou et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib44)) and ReFeed (Yu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib97)), but mainly for reference. Other reported numbers are directly comparable if they follow the standard zero-shot settings.

Evaluation Metrics. For OpenQA datasets, we use _Exact Match (EM)_ as the main metric but also report Accuracy for TriviaQA and PopQA and F1 score for HotpotQA and 2WikimQA as it is used in several studies (Asai et al., [2024a](https://arxiv.org/html/2407.02485v1#bib.bib4); Mallen et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib55)). For FEVER, we use accuracy as the metric. For ConvQA datasets, we follow (Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50); Wang et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib82)) to use F1 score as the metric.

Implementation Details. We use Llama3 8B and 70B (Meta-AI, [2024](https://arxiv.org/html/2407.02485v1#bib.bib57)) as the backbone in our main experiments. For the two-stage instruction tuning, we set the batch size to 128 and train the model for 1000 steps with learning rate 5e-6 in Stage-I. Then, we reduce the learning rate to 3e-7 for 8B and 2e-7 for 70B model, set the batch size to 64, and train the model for 3300 steps (around 1 epoch). We use the Adam optimizer (Kingma & Ba, [2014](https://arxiv.org/html/2407.02485v1#bib.bib40)) with β1=0.9\beta_{1}=0.9 and β2=0.98\beta_{2}=0.98. During the inference stage, we use the December 2018 Wikidump as the corpus index for NQ, TQA, HotpotQA, 2WikimQA, and use the December 2020 Wikidump for PopQA, following (Asai et al., [2024a](https://arxiv.org/html/2407.02485v1#bib.bib4)). By default, we follow (Wang et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib82); Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49); Liu et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib50)) to use the Dragon retriever (Lin et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib48)) as default and retrieve top-NN (100100 for 8B and 3030 for 70B) documents for ranking, but RankRAG can be adapted to various retrievers and different NN (see § [5.3](https://arxiv.org/html/2407.02485v1#S5.SS3 "5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") and [5.5](https://arxiv.org/html/2407.02485v1#S5.SS5 "5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG BenchmarksIn 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs")). To ensure a fair comparison, we test the performance of k∈{5,10,20}k\in\\{5,10,20\\} and report _the best performance_ for baselines. For generation, we keep temperature T=0T=0 and set the maximum number of generated token to be 32 for OpenQA, 128 for ConvQA and 8 for others. Training RankRAG-8B uses 32 NVIDIA A100 GPUs for 10 hours (4 hours for Stage-I and 6 hours for Stage-II finetuning), while training RankRAG-70B uses 128 NVIDIA A100 GPUs for 16 hours (4 hours for Stage-I and 12 hours for Stage-II Finetuning).

Data Contamination Issues. One possible issue for the zero-shot evaluation is the test set contamination, where some of the task-specific examples overlap with the instruction fine-tuning data (Oren et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib64)). To address this issue, we have performed a string match-based analysis where we do not observe any overlap between the train data and data from target tasks.

Table 2: Results of RankRAG and baselines on 9 datasets. Unless specified, all results are under _zero-shot_ evaluation without additional demonstrations. Results unavailable in public reports are marked as “–”. We use NQ, TriviaQA, and HotpotQA from the KILT benchmark for Llama3-Instruct, Llama3-ChatQA-1.5, and Llama3-RankRAG. Note that†: GPT-4 and GPT-4-turbo may refuse to answer the question when retrieved passages do not contain relevant information, thus the EM / accuracy drops after including RAG on TriviaQA, HotpotQA and 2WikimQA. 

Task (_Zero-shot_) | NQ | TriviaQA | PopQA | HotpotQA | 2WikimQA | FEVER | Doc2Dial | TopiOCQA | Inscit | Avg.  
---|---|---|---|---|---|---|---|---|---|---  
Metric | EM | EM / Acc. | EM / Acc. | EM / F1 | EM / F1 | Acc. | F1 | F1 | F1 | –  
Without Retrieval-Augmented Generation |  |  |  |  |   
InstructGPT ([Ouyang et al.](https://arxiv.org/html/2407.02485v1#bib.bib65)) | 29.9 | 65.8 / 73.2 | – / – | 26.0 / 38.2 | 27.2 / 34.8 | 77.6 | – | – | – | –  
PaLM2 540B (0 shot, [Anil et al.](https://arxiv.org/html/2407.02485v1#bib.bib2)) | 21.2 | 76.9 / – | – / – | – / – | – / – | – | – | – | – | –  
PaLM2 540B (5 shot, [Anil et al.](https://arxiv.org/html/2407.02485v1#bib.bib2)) | 37.1 | 86.1 / – | – / – | – / – | – / – | – | – | – | – | –  
GLaM 64B (0 shot, [Du et al.](https://arxiv.org/html/2407.02485v1#bib.bib15)) | 37.5 | 71.3 / – | – / – | – / – | – / – | – | – | – | – | –  
FLAN-LaMDA 137B ([Wei et al.](https://arxiv.org/html/2407.02485v1#bib.bib87)) | 20.7 | 68.1 / – | – / – | – / – | – / – | – | – | – | – | –  
Claude 2 (5 shot, [Anthropic](https://arxiv.org/html/2407.02485v1#bib.bib3)) | – |  87.5 / – | – / – | – / – | – / – | – | – | – | – | –  
Mixtral-8x22B-Instruct (5 shot, [Mistral](https://arxiv.org/html/2407.02485v1#bib.bib58)) | 40.1 | 82.2 / – | – / – | – / – | – / – | – | – | – | – | –  
DeepSeek-V2 236B (5 shot, [DeepSeek](https://arxiv.org/html/2407.02485v1#bib.bib14)) | 53.4 | 86.7 / – | – / – | – / – | – / – | – | – | – | – | –  
GPT-3.5-turbo-1106 ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib62)) | 38.6 | 82.9 / 91.7 | 28.4 / 32.2 | 29.9 / 42.0 | 23.9 / 30.4 | 82.7 | 20.1 | 28.5 | 27.2 | 38.5  
GPT-4-0613 ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib63)) | 40.3 |  84.8 / 94.5 | 31.3 / 34.8 | 34.5 / 46.9 | 29.8 / 36.6 | 87.7 | 27.6 | 30.1 | 27.0 | 42.0  
GPT-4-turbo-2024-0409 ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib63)) | 41.5 | 80.0 / 94.3 | 25.0 / 33.5 | 26.6 / 43.8 | 24.1 / 35.5 | 87.0 | 27.6 | 26.4 | 24.4 | 38.6  
With Retrieval-Augmented Generation |  |  |  |  |   
Atlas 11B ([Izacard et al.](https://arxiv.org/html/2407.02485v1#bib.bib27)) | 26.7 | 56.9 / – | – / – | 34.7 / – | – / – | 77.0 | – | – | – | –  
Raven 11B ([Huang et al.](https://arxiv.org/html/2407.02485v1#bib.bib24)) | 29.6 | 65.7 / – | – / – | – / – | – / – | – | – | – | – | –  
Self-RAG 7B ([Asai et al.](https://arxiv.org/html/2407.02485v1#bib.bib4)) | – | – / 66.4 | – / 54.9 | – / – | – / – | – | – | – | – | –  
Self-RAG 13B ([Asai et al.](https://arxiv.org/html/2407.02485v1#bib.bib4)) | – | – / 69.3 | – / 55.8 | – / – | – / – | – | – | – | – | –  
RECOMP 20B ([Xu et al.](https://arxiv.org/html/2407.02485v1#bib.bib91)) | 37.0 | 59.0 / – | – / – | 30.4 / 40.1 | – / – | – | – | – | – | –  
InstructRetro 43B ([Wang et al.](https://arxiv.org/html/2407.02485v1#bib.bib82)) | 38.9 | 78.3 / – | – | – / – | – / – | – | 36.0 | – | – | –  
RePlug 65B ([Shi et al.](https://arxiv.org/html/2407.02485v1#bib.bib74)) | 28.8 | 72.6 / – | – / – | 32.0 / – | – / – | 73.3 | – | – | – | –  
RA-DIT 65B ([Lin et al.](https://arxiv.org/html/2407.02485v1#bib.bib49)) | 35.2 | 75.4 / – | – / – | 39.7 / – | – / – | 80.7 | – | – | – | –  
Llama3-Instruct 8B ([Meta-AI](https://arxiv.org/html/2407.02485v1#bib.bib57)) | 30.9 | 70.7 / 80.4 | 34.9 / 55.8 | 26.0 / 35.8 | 9.6 / 25.2 | 88.9 | 33.6 | 44.9 | 32.6 | 40.8  
Llama3-Instruct 70B ([Meta-AI](https://arxiv.org/html/2407.02485v1#bib.bib57)) | 42.7 | 82.4 / 89.3 | 45.3 / 56.4 | 35.5 / 43.3 | 13.5 / 27.9 | 91.4 | 37.9 | 49.7 | 36.2 | 47.1  
Llama3-ChatQA-1.5 8B ([Liu et al.](https://arxiv.org/html/2407.02485v1#bib.bib50)) | 42.4 | 81.0 / 87.6 | 52.6 / 59.8 | 33.4 / 44.6 | 26.8 / 31.9 | 90.9 | 39.3 | 49.9 | 30.1 | 49.6  
Llama3-ChatQA-1.5 70B ([Liu et al.](https://arxiv.org/html/2407.02485v1#bib.bib50)) | 47.0 |  85.6 / 91.4 | 50.9 / 58.3 |  42.2 / 54.4 |  34.9 / 37.4 | 92.7 | 41.3 | 55.6 | 32.3 | 53.6  
Llama3-RankRAG 8B (0 shot) | 50.6 | 82.9 / 89.5 |  57.6 / 64.1 | 35.3 / 46.7 | 31.4 / 36.9 | 92.0 | 40.4 | 50.4 | 33.3 | 52.6  
Llama3-RankRAG 70B (0 shot) | 54.2 | 86.5 / 92.3 | 59.9 / 65.4 | 42.7 / 55.4 | 38.2 / 43.9 | 93.8 | 41.5 | 52.8 | 35.2 | 56.1  
For reference: _Using InstructGPT or CodeX ( ∼\sim175B) (Ouyang et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib65)) as the Backbone LLM._ |   
GenRead ([Yu et al.](https://arxiv.org/html/2407.02485v1#bib.bib95)) | 32.5 | 66.2 / – | 46.0 / – | 36.4 / 39.9 | – / – | 80.4 | – | – | – | –  
Retrieve-Read ([Lazaridou et al.](https://arxiv.org/html/2407.02485v1#bib.bib44)) | 31.7 | 61.4 / – | – / – | 35.2 / 38.0 | 27.7 / – | 82.7 | – | – | – | –  
ReFeed ([Yu et al.](https://arxiv.org/html/2407.02485v1#bib.bib97)) | 39.6 | 68.9 / – | – / – | 41.5 / 45.1 | – / – | – | – | – | – | –  
GPT-3.5-turbo-1106 RAG ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib62)) | 46.7 | 79.7 / 88.0 | 49.9 / 57.0 | 31.2 / 41.2 | 27.2 / 32.2 | 90.8 | 34.8 | 44.3 | 35.3 | 46.8  
GPT-4-0613 RAG† ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib63)) | 40.4 | 75.0 / 88.5 | 44.3 / 61.4 | 27.6 / 38.1 | 14.4 / 17.6 | 92.6 | 34.2 | 45.1 | 36.4 | 43.5  
GPT-4-turbo-2024-0409 RAG† ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib63)) | 40.3 | 70.2 / 91.1 | 39.5 / 58.4 | 8.1 / 17.9 | 22.8 / 39.2 | 92.2 | 35.4 | 48.3 | 33.8 | 41.6  
  
###  5.2 Main Experiments

Table [2](https://arxiv.org/html/2407.02485v1#S5.T2 "Table 2 ‣ Tasks and Datasets. ‣ 5.1 Experiment Setup ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") presents results of RankRAG and baselines. The findings are summarized as follows:

RankRAG outperforms existing RAG methods. With 8B scale, RankRAG consistently outperforms ChatQA-1.5 8B, one of the most recent open-sourced model with state-of-the-art performance on many RAG benchmarks. RankRAG 8B is also competitive when compared with baseline models with much more parameters. For example, it significantly outperforms InstructRetro (5×5\times parameters), RA-DIT 65B (8×8\times paramters), and even outperforms Llama3-instruct 70B (8×8\times parameters) on NQ and TriviaQA tasks. With more parameters, RankRAG 70B outperforms the strong ChatQA-1.5 70B model, and largely outperforms previous RAG baselines with InstructGPT as the underlying LLM.

RankRAG demonstrates larger improvement on more challenging datasets. We observe that the performance gains of RankRAG over baselines are more pronounced for more challenging QA datasets. For example, on long-tailed QA (PopQA) and multi-hop QA (2WikimQA) tasks, we achieve more than 10% improvement over ChatQA-1.5. These findings suggest that in challenging OpenQA datasets where top documents from retrievers are less relevant to the answer, context ranking effectively enhances performance. In this work we focus on improving single-time retrieval for QA tasks. How to effectively combine multi-round RAG pipelines (Jiang et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib30); Khattab et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib38); Jeong et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib28)) with RankRAG is an interesting avenue of future work.

###  5.3 Ablation Studies

Effect of Designed Components. Table [3](https://arxiv.org/html/2407.02485v1#S5.T3 "Table 3 ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") shows the ablations of RankRAG with Llama3 8B as the backbone on nine general-domain datasets. Overall, we observe all of the proposed components contribute to the final performance. Removing context ranking hurts performance on all tasks, justifying its efficacy in selecting the most relevant contexts for the target question. Besides, the retrieval-augmented QA (RQA) and retrieval-augmented ranking (RAR) designed for instruction fine-tuning improve outcomes on most tasks by helping the model explicitly pinpoint relevant contexts. On the contrary, the RAFT method used in (Lin et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib49)) treats each retrieved context separately during instruction finetuning, which yields suboptimal results when compared to RankRAG with the same training data.

Table 3: Ablation study of RankRAG. We use Llama3-8B as the backbone. Where ‘RQA’ and ‘RAR’ stands for retrieval-augmented QA and retrieval-augmented ranking data, respectively. For ‘w/o reranking’, we do not perform ranking in the inference stage. 

Task (Zero-Shot) | NQ | TriviaQA | PopQA | HotpotQA | 2WikimQA | FEVER | Doc2Dial | TopiOCQA | Inscit | Avg.  
---|---|---|---|---|---|---|---|---|---|---  
Metric | EM | EM / Acc. | EM / Acc. | EM / F1 | EM / F1 | Acc. | F1 | F1 | F1 | –  
RankRAG 8B | 50.6 | 82.9 / 89.5 | 57.6 / 64.1 | 35.3 / 46.7 | 31.4 / 36.9 | 92.0 | 40.4 | 50.4 | 33.3 | 52.6  
w/o reranking | 48.0 | 80.3 / 86.8 | 49.3 / 59.0 | 31.3 / 41.6 | 26.4 / 30.5 | 91.1 | 39.7 | 49.4 | 30.9 | 49.8  
w/o RQA | 49.4 | 82.0 / 88.9 | 55.1 / 62.9 |  35.6 / 45.9 | 31.8 / 37.5 | 92.1 | 39.4 | 46.8 | 32.4 | 51.6  
w/o RAR | 48.6 | 82.2 / 89.1 | 56.0 / 62.6 | 35.1 / 45.2 | 31.2 / 35.7 | 91.4 | 39.6 | 48.6 | 33.5 | 51.8  
w/ RAFT ([Lin et al.](https://arxiv.org/html/2407.02485v1#bib.bib49)) | 43.3 | 80.8 / 87.6 | 48.9 / 56.3 | 30.5 / 41.8 | 25.2 / 29.6 | 91.2 | 36.8 | 46.4 | 30.1 | 48.1  
w/ Stage-I SFT Only | 38.3 | 63.7 / 76.6 | 49.8 / 54.6 | 26.5 / 40.3 | 18.0 / 25.9 | 85.7 | 33.3 | 33.7 | 30.5 | 42.2  
  
Performance with Different LLMs.

Table 4: Zero-shot evaluation using Llama2 (Touvron et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib78)) model as the backbone. 

Task (Zero-Shot) | NQ | TriviaQA | PopQA | HotpotQA | 2WikimQA | FEVER | Doc2Dial | TopiOCQA | Inscit | Avg.  
---|---|---|---|---|---|---|---|---|---|---  
Metric | EM | EM / Acc. | EM / Acc. | EM / F1 | EM / F1 | Acc. | F1 | F1 | F1 | –  
Llama2-70B ([Touvron et al.](https://arxiv.org/html/2407.02485v1#bib.bib78)) | 25.3 | 82.4 / – | – / – | – / – | – / – | – | – | – | – | –  
Llama2-ChatQA-1.0 7B ([Liu et al.](https://arxiv.org/html/2407.02485v1#bib.bib50)) | 41.4 | 77.8 / 86.5 | 46.7 / 55.0 | 28.9 / 40.3 | 24.0 / 27.5 | 85.9 | 37.9 | 45.5 | 31.0 | 46.6  
Llama2-ChatQA-1.0 13B ([Liu et al.](https://arxiv.org/html/2407.02485v1#bib.bib50)) | 47.9 | 80.9 / 87.6 | 51.8 / 56.2 | 32.9 / 43.2 | 27.6 / 31.1 | 87.6 | 38.1 | 48.9 | 30.8 | 49.6  
Llama2-ChatQA-1.0 70B ([Liu et al.](https://arxiv.org/html/2407.02485v1#bib.bib50)) | 49.5 | 83.2 / 89.7 | 52.1 / 56.6 | 39.0 / 49.4 | 28.9 / 34.1 | 91.7 | 38.9 | 51.0 | 31.9 | 51.8  
Llama2-RankRAG 7B | 46.9 | 84.0 / 89.6 | 55.9 / 61.3 | 32.2 / 43.2 | 26.8 / 30.7 | 86.6 | 38.6 | 49.2 | 32.3 | 50.3  
Llama2-RankRAG 13B | 50.5 | 84.5 / 91.0 | 58.0 / 63.9 | 36.4 / 47.3 | 29.5 / 34.2 | 91.7 | 39.5 | 49.2 | 33.4 | 52.5  
Llama2-RankRAG 70B | 53.2 | 85.8 / 92.1 | 58.7 / 64.5 | 41.8 / 53.1 | 33.8 / 38.8 | 91.9 | 41.2 | 52.9 | 35.8 | 55.0  
  
Table [4](https://arxiv.org/html/2407.02485v1#S5.T4 "Table 4 ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") reports the performance of RankRAG and the most recent baseline ChatQA using Llama2 with backbone having varying amounts of parameters. Notably, there exist consistent gains in terms of the average performance (7.8%/6.4%/6.3% on 7B/13B/70B variants respectively), justifying the advantage of RankRAG across different LLM types and scales.

(a) Performance with different retrievers. The performance of Recall is in Appendix [E.1](https://arxiv.org/html/2407.02485v1#A5.SS1 "E.1 Ranking Performance Using DPR and Contriever as Retrievers ℛ ‣ Appendix E Additional Experiment Results ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs").

Performance with Different Retrievers. Figure [6(a)](https://arxiv.org/html/2407.02485v1#S5.F6.sf1 "In 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") exhibits the performance of RankRAG and ChatQA-1.5 with different dense retrievers on three representative tasks, where we consider DPR (Karpukhin et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib35)) and Contriever-MS MARCO (Izacard et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib26)) as two variants. We note that although the initial retrieved result is not good enough, RankRAG still surpasses ChatQA-1.5 by more than 10% for both retrievers on average. To summarize, RankRAG is robust to the choice of retrievers.

###  5.4 Experiment on Domain-specific RAG Benchmarks

Table 5: The performance of RankRAG on Mirage, a zero-shot biomedical RAG benchmark. RankRAG and baselines use retrieval by default. Most of numbers are from (Xiong et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib90)).

Datasets | MMLU-med | PubmedQA | BioASQ | MedQA | MedMCQA | Avg.  
---|---|---|---|---|---|---  
GPT-4-0613 ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib63)) | 87.24 | 70.60 | 92.56 | 82.80 | 66.65 | 79.97  
GPT-3.5 ([OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib62)) | 75.48 | 67.40 | 90.29 | 66.61 | 58.04 | 71.56  
Mixtral 8*7B ([Jiang et al.](https://arxiv.org/html/2407.02485v1#bib.bib29)) | 75.85 | 67.60 | 87.54 | 60.02 | 56.42 | 69.49  
Llama2 70B ([Touvron et al.](https://arxiv.org/html/2407.02485v1#bib.bib78)) | 54.55 | 50.40 | 73.95 | 44.93 | 43.08 | 53.38  
Meditron 70B ([Chen et al.](https://arxiv.org/html/2407.02485v1#bib.bib10)) | 65.38 | 56.40 | 76.86 | 49.57 | 52.67 | 60.18  
PMC-llama 13B ([Wu et al.](https://arxiv.org/html/2407.02485v1#bib.bib88)) | 52.53 | 42.58 | 48.29 | 56.00 | 65.21 | 52.92  
Llama3-ChatQA-1.5 8B ([Liu et al.](https://arxiv.org/html/2407.02485v1#bib.bib50)) | 61.40 | 66.40 | 82.69 | 42.36 | 46.97 | 59.96  
Llama3-ChatQA-1.5 70B | 80.51 | 74.80 | 83.17 | 68.89 | 62.54 | 73.98  
Llama3-RankRAG 8B | 64.55 | 65.00 | 84.44 | 48.86 | 56.90 | 63.95  
Llama3-RankRAG 70B | 81.44 | 79.80 | 90.76 | 69.21 | 69.11 | 78.06  
  
To demonstrate that RankRAG can adapt to specialized domains, we conduct experiments on Mirage (Xiong et al., [2024](https://arxiv.org/html/2407.02485v1#bib.bib90)), a recently introduced RAG benchmark for the biomedical field. We follow Xiong et al. ([2024](https://arxiv.org/html/2407.02485v1#bib.bib90)) to employ MedCPT (Jin et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib33)) as the retriever ℛ\mathcal{R} with MedCorp222Link: <https://huggingface.co/MedRAG>. Detailed dataset information is in Appendix [A.2](https://arxiv.org/html/2407.02485v1#A1.SS2 "A.2 Biomedical Benchmarks ‣ Appendix A Dataset Description ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"). as the corpus 𝒟\mathcal{D}.

The experiment results of RankRAG and baselines are shown in Table [5](https://arxiv.org/html/2407.02485v1#S5.T5 "Table 5 ‣ 5.4 Experiment on Domain-specific RAG BenchmarksIn 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"). From the table, we observe that RankRAG, even without fine-tuning on the biomedical domain, excels at medical QA tasks. Notably, RankRAG 8B surpasses Meditron 70B—a leading open-source LLM for the medical domain—by 6.3%. Besides, RankRAG 70B attains more than 98% performance of GPT-4. These results justify RankRAG’s capacity to be readily applied to new domains without extra post-training. 

Table 6: Ranking performance with different ranking models. Unless specified, all baselines are used to rank the top 100 retrieved passages. RankRAG achieves better performance despite using fewer ranking data. ∗ NQ, TriviaQA and HotpotQA are used for training the BGE-Reranker model. †: Our re-implementation. ‡ We only rerank top-30 passages for GPT-4 due to budget constraint. 

Task | # Rank Data | NQ | TriviaQA | PopQA | HotpotQA | Inscit  
---|---|---|---|---|---|---  
Recall | R@5 | R@10 | R@20 | R@5 | R@10 | R@20 | R@5 | R@10 | R@20 | R@5 | R@10 | R@20 | R@5 | R@10 | R@20  
Backbone Retriever |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |   
Dragon ([Lin et al.](https://arxiv.org/html/2407.02485v1#bib.bib48)) | – | 74.9 | 80.3 | 84.3 | 89.0 | 92.9 | 95.3 | 69.6 | 76.9 | 82.6 | 47.5 | 52.4 | 60.1 | 43.4 | 56.0 | 64.9  
Finetuned Baseline Ranking Model |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |   
RankBERT 110M ([Glass et al.](https://arxiv.org/html/2407.02485v1#bib.bib19)) |  ∼\sim503k | 73.5 | 79.3 | 84.0 | 88.4 | 92.0 | 95.5 | 78.7 | 82.8 | 85.5 | 54.6 | 59.8 | 63.7 | 45.6 | 57.1 | 66.7  
monoT5 3B ([Nogueira et al.](https://arxiv.org/html/2407.02485v1#bib.bib61)) |  ∼\sim503k | 75.6 | 80.9 | 84.9 | 90.7 | 93.6 | 95.9 | 81.0 | 83.6 | 85.9 | 54.8 | 60.2 | 63.3 | 48.6 | 59.4 | 68.8  
BGE-Rerank-v2-m3 568M ([Chen et al.](https://arxiv.org/html/2407.02485v1#bib.bib9)) |  ∼\sim1.6M |  78.0∗ |  82.8∗ |  85.6∗ |  91.6∗ |  94.5∗ |  97.1∗ | 79.6 | 84.5 | 86.9 |  58.5∗ |  61.8∗ |  65.0∗ | 51.3 | 59.8 | 69.7  
RankLLaMA 8B† ([Ma et al.](https://arxiv.org/html/2407.02485v1#bib.bib54)) |  ∼\sim503k | 77.8 | 83.1 | 86.0 | 91.2 | 93.1 | 96.4 | 80.1 | 84.3 | 86.8 | 57.1 | 62.1 | 64.8 | 57.8 | 62.1 | 71.3  
ChatQA-1.5 8B ([Liu et al.](https://arxiv.org/html/2407.02485v1#bib.bib50)) | N/A | 68.2 | 75.7 | 82.0 | 85.4 | 91.1 | 94.0 | 67.3 | 76.7 | 83.5 | 37.4 | 45.0 | 53.6 | 32.3 | 42.6 | 54.9  
Off-the-shelf LLM Reranker |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |   
GPT-3.5 (top 100, [OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib62)) | Unk. | 77.8 | 82.5 | 85.7 | 91.1 | 94.4 | 96.7 | 77.4 | 82.0 | 85.5 | 52.1 | 56.6 | 62.4 | 50.2 | 59.1 | 68.6  
GPT-4‡ (top 30, [OpenAI](https://arxiv.org/html/2407.02485v1#bib.bib63)) | Unk. | 79.3 | 83.2 | 85.1 | 92.8 | 95.5 | 96.8 | 79.3 | 83.6 | 86.2 | 53.2 | 57.0 | 61.0 | 52.3 | 61.7 | 70.0  
Our Model |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |   
RankRAG 8B (top 100) |  ∼\sim50k | 80.3 | 84.0 | 86.3 | 93.2 | 95.4 | 97.3 | 81.6 | 84.9 | 87.0 | 57.6 | 61.8 | 65.2 | 60.9 | 65.7 | 73.5  
RankRAG 70B (top 30) |  ∼\sim50k | 80.6 | 84.0 | 85.4 | 93.6 | 95.9 | 97.1 | 81.8 | 84.6 | 86.5 | 56.3 | 59.7 | 62.2 | 61.3 | 66.4 | 74.6  
  
###  5.5 A Closer Look at the Ranking Module

As the context ranking serves as a core step in RankRAG, we take a closer look at this component. All the studies are done using Llama3-8B as the backbone.

RankRAG is Data-efficient. Previous approaches that infuse context ranking into the RAG pipeline usually involve a separate reranking model. To compare our model with these baselines, we evaluate four models (BERT (Glass et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib19))/T5 (Nogueira et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib61))/Llama3 (Ma et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib54))) fine-tuned on the full MS MARCO passage ranking dataset, a strong off-the-shelf reranker model BGE-ranker, and two OpenAI GPT-series models. For the GPT-series models, we use the token probability of ‘True’ as a proxy for the relevance score333<https://platform.openai.com/docs/api-reference/chat/create#chat-create-logprobs>. These models are then used to rerank top-retrieved passages by Dragon, similar to our approach. Surprisingly, as shown in Table [6](https://arxiv.org/html/2407.02485v1#S5.T6 "Table 6 ‣ 5.4 Experiment on Domain-specific RAG BenchmarksIn 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"), RankRAG achieves better recall over dedicated ranking models trained on 10×10\times more ranking data for most cases. Besides, RankRAG can still outperform the BGE-ranker on most tasks, which has been extensively trained on more than 1 million ranking pairs, including some that overlap with our evaluation tasks. This advantage is likely due to the adaptable nature of our model’s training, where the ranking data closely resembles the general RAG fine-tuning data. Directly using ChatQA-1.5 to rank passages _hurts_ the performance, indicating the necessity of incorporating ranking data into instruction fine-tuning.

We further study the relation between the number of context ranking data and final performance. As shown in Figure [5.5](https://arxiv.org/html/2407.02485v1#S5.SS5 "5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG BenchmarksIn 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"), with 5k ranking data only (∼1%\sim 1\% of the MS MARCO dataset), RankRAG can already obtain very compelling results, while further increasing the number of ranking data to 50k yields non-marginal gains. This finding confirms RankRAG’s data efficiency – achieving effective performance with a modest amount of ranking data and maintaining adaptability across various tasks.

Performance v.s. Time-efficiency for RankRAG. One specific caveat for scaling up model size is the increment in the latency overhead — as mentioned in §[4.3](https://arxiv.org/html/2407.02485v1#S4.SS3 "4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"), it requires sample-wise ranking which incurs additional time. To study the relation between the time efficiency and performance, we change the NN used in reranking and plot the relation of NN and final accuracy in Figure [10(a)](https://arxiv.org/html/2407.02485v1#S5.F10.sf1.fig1 "In 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"), from which we observe that even with N=20N=20, RankRAG still improve the baseline model without reranking. While reranking across N=20N=20 to 100100 improves the exact match score by 5.9% to 9.1% across three tasks, it incurs an additional 0.9×0.9\times to 6.0×6.0\times increase in time – _significantly less_ than the 20×20\times to 100×100\times increase one might expect.

(a) Performance w.r.t. # Ranking Data (a) Performance v.s. Efficiency analysis for RankRAG.

Table 7: A case study on the top-retrieved context and predictions on NQ dataset, illustrating the effectiveness of RankRAG-8B over ChatQA-1.5-8B. Red text denotes distractors, while green stands for evidences. RankRAG is able to find the correct answer via extract more evidence with reranking.

Q: who hosted and won the inagural world cup? A: Uruguay  
---  
ChatQA-1.5 |  Passage 1: FIFA World Cup second round on home soil in 1982. England (1966) won its only title while playing as a host nation. Uruguay (1930), Italy (1934), Argentina (1978) and France (1998) won their first titles as host nations but have gone on to win again, while Germany (1974) won their second title on home soil…  
Passage 2: FIFA World Cup hosts country is now chosen in a vote by FIFA’s Congress … Only Mexico, Italy, France, Germany (West Germany) until shortly after the 1990 World Cup) and Brazil have hosted the event on two occasions.  
Passage 3: CONCACAF hosts, beating the bids of Canada and the United States, and thereby became the first nation to host two World Cups. This second World Cup in Mexico came 16 years after the first one in 1970…  
Passage 4: 1998 FIFA World Cup Africa made their first appearances in the finals. France was awarded the 1998 World Cup on 2 July 1992 by the executive committee of FIFA during a general meeting in Zürich, Switzerland. They defeated Morocco by 12 votes to 7.  
Passage 5: 2026 FIFA World Cup be hosted by one of the remaining four confederations: CONCACAF (North America; last hosted in 1994), CAF (Africa; last hosted in 2010), CONMEBOL (South America; last hosted in 2014), or OFC (Oceania, never hosted before)… Prediction: _Germany_ (✘)  
RankRAG |  Passage 1: FIFA World Cup second round on home soil in 1982. England (1966) won its only title while playing as a host nation. Uruguay (1930), Italy (1934), Argentina (1978) and France (1998) won their first titles as host nations but have gone on to win again, while Germany (1974) won their second title on home soil…  
Passage 2: Timeline of association football penalty kicks. Thirteen teams enter the first World Cup, held in Uruguay. The hosts beat Argentina 4–2 in the final. Contested between the top national teams of continental Europe, Dr. Gerö Cup’ first edition is won by Italy.  
Passage 3: The Uruguay national football team represents Uruguay in international association football and is controlled by the Uruguayan Football Association. They have won the Copa América 15 times, the most successful national team in the tournament, the most recent title being the 2011 edition. The team has won the FIFA World Cup twice, including the first World Cup in 1930 as hosts, defeating Argentina 4–2 in the final.  
Passage 4: FIFA World Cup hosts country is now chosen in a vote by FIFA’s Congress. The decision is currently made roughly seven years in advance of the tournament, though the hosts for the 2022 tournament were chosen at the same time as those for the 2018 tournament.  
Passage 5: CONCACAF hosts, beating the bids of Canada and the United States, and thereby became the first nation to host two World Cups. This second World Cup in Mexico came 16 years after the first one in 1970… Prediction: _Uruguay_ (✓)  
  
###  5.6 Case Study

Table [7](https://arxiv.org/html/2407.02485v1#S5.T7 "Table 7In 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") presents a case study on NQ dataset, where we observe that using retriever only yield noisy contexts, as there are several distractors, and some contexts (e.g. Passage 4/5 for ChatQA-1.5) are unhelpful. However, the utilization of reranking uncovers _two additional_ relevant passages, aiding the model in providing the correct answer. More case studies are provided in Appendix [G](https://arxiv.org/html/2407.02485v1#A7 "Appendix G Additional Case Studies ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs").

##  6 Conclusion

In this work, we introduce a new RAG framework, RankRAG, which instruction-tunes a single LLM for both ranking and answer generation. We find that the instruction tuned LLMs can outperform existing expert ranking models by only adding a small fraction of ranking data into the training blend. We compare our RankRAG with the state-of-the-art RAG models on comprehensive knowledge-intensive benchmarks and demonstrate RankRAG significantly outperform all of them on nine general-domain and five biomedical benchmarks for RAG.

## References

  * Adlakha et al. (2022) Adlakha, V., Dhuliawala, S., Suleman, K., de Vries, H., and Reddy, S.  Topiocqa: Open-domain conversational question answering with topic switching.  _TACL_ , 2022. 
  * Anil et al. (2023) Anil, R., Dai, A. M., Firat, O., Johnson, M., Lepikhin, D., Passos, A., Shakeri, S., Taropa, E., Bailey, P., Chen, Z., et al.  Palm 2 technical report.  _arXiv preprint arXiv:2305.10403_ , 2023. 
  * Anthropic (2023) Anthropic.  Model card and evaluations for claude models.  2023\. 
  * Asai et al. (2024a) Asai, A., Wu, Z., Wang, Y., Sil, A., and Hajishirzi, H.  Self-RAG: Learning to retrieve, generate, and critique through self-reflection.  In _ICLR_ , 2024a. 
  * Asai et al. (2024b) Asai, A., Zhong, Z., Chen, D., Koh, P. W., Zettlemoyer, L., Hajishirzi, H., and Yih, W.-t.  Reliable, adaptable, and attributable language models with retrieval.  _arXiv preprint arXiv:2403.03187_ , 2024b. 
  * Bajaj et al. (2016) Bajaj, P., Campos, D., Craswell, N., Deng, L., Gao, J., Liu, X., Majumder, R., McNamara, A., Mitra, B., Nguyen, T., et al.  Ms marco: A human generated machine reading comprehension dataset.  _arXiv preprint arXiv:1611.09268_ , 2016. 
  * Berant et al. (2013) Berant, J., Chou, A., Frostig, R., and Liang, P.  Semantic parsing on freebase from question-answer pairs.  In _EMNLP_ , 2013. 
  * Borgeaud et al. (2022) Borgeaud, S., Mensch, A., Hoffmann, J., Cai, T., Rutherford, E., Millican, K., Van Den Driessche, G. B., Lespiau, J.-B., Damoc, B., Clark, A., et al.  Improving language models by retrieving from trillions of tokens.  In _ICML_. PMLR, 2022. 
  * Chen et al. (2023a) Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., and Liu, Z.  Bge m3-embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation, 2023a. 
  * Chen et al. (2023b) Chen, Z., Cano, A. H., Romanou, A., Bonnet, A., Matoba, K., Salvi, F., Pagliardini, M., Fan, S., Köpf, A., Mohtashami, A., et al.  Meditron-70b: Scaling medical pretraining for large language models.  _arXiv preprint arXiv:2311.16079_ , 2023b. 
  * Chung et al. (2024) Chung, H. W., Hou, L., Longpre, S., Zoph, B., Tay, Y., Fedus, W., Li, Y., Wang, X., Dehghani, M., Brahma, S., et al.  Scaling instruction-finetuned language models.  _JMLR_ , 25(70), 2024. 
  * Conover et al. (2023) Conover, M., Hayes, M., Mathur, A., Xie, J., Wan, J., Shah, S., Ghodsi, A., Wendell, P., Zaharia, M., and Xin, R.  Free Dolly: Introducing the world’s first truly open instruction-tuned llm, 2023. 
  * Dasigi et al. (2019) Dasigi, P., Liu, N. F., Marasović, A., Smith, N. A., and Gardner, M.  Quoref: A reading comprehension dataset with questions requiring coreferential reasoning.  In _EMNLP_ , 2019. 
  * DeepSeek (2024) DeepSeek.  Deepseek-v2: A strong, economical, and efficient mixture-of-experts language model, 2024. 
  * Du et al. (2022) Du, N., Huang, Y., Dai, A. M., Tong, S., Lepikhin, D., Xu, Y., Krikun, M., Zhou, Y., Yu, A. W., Firat, O., et al.  Glam: Efficient scaling of language models with mixture-of-experts.  In _ICML_ , 2022. 
  * Dua et al. (2019) Dua, D., Wang, Y., Dasigi, P., Stanovsky, G., Singh, S., and Gardner, M.  Drop: A reading comprehension benchmark requiring discrete reasoning over paragraphs.  In _NAACL_ , 2019. 
  * Fan et al. (2019) Fan, A., Jernite, Y., Perez, E., Grangier, D., Weston, J., and Auli, M.  Eli5: Long form question answering.  In _ACL_ , 2019. 
  * Feng et al. (2020) Feng, S., Wan, H., Gunasekara, C., Patel, S., Joshi, S., and Lastras, L.  doc2dial: A goal-oriented document-grounded dialogue dataset.  In _EMNLP_ , 2020. 
  * Glass et al. (2022) Glass, M., Rossiello, G., Chowdhury, M. F. M., Naik, A., Cai, P., and Gliozzo, A.  Re2G: Retrieve, rerank, generate.  In _NAACL_ , 2022. 
  * Guu et al. (2020) Guu, K., Lee, K., Tung, Z., Pasupat, P., and Chang, M.  Retrieval augmented language model pre-training.  In _ICML_ , 2020. 
  * Hendrycks et al. (2021) Hendrycks, D., Burns, C., Basart, S., Zou, A., Mazeika, M., Song, D., and Steinhardt, J.  Measuring massive multitask language understanding.  In _ICLR_ , 2021. 
  * Ho et al. (2020) Ho, X., Nguyen, A.-K. D., Sugawara, S., and Aizawa, A.  Constructing a multi-hop qa dataset for comprehensive evaluation of reasoning steps.  In _COLING_ , 2020. 
  * Honovich et al. (2023) Honovich, O., Scialom, T., Levy, O., and Schick, T.  Unnatural instructions: Tuning language models with (almost) no human labor.  In _ACL_ , 2023. 
  * Huang et al. (2023) Huang, J., Ping, W., Xu, P., Shoeybi, M., Chang, K. C.-C., and Catanzaro, B.  Raven: In-context learning with retrieval augmented encoder-decoder language models.  _arXiv preprint arXiv:2308.07922_ , 2023. 
  * Izacard & Grave (2021) Izacard, G. and Grave, E.  Leveraging passage retrieval with generative models for open domain question answering.  In _EACL_ , 2021. 
  * Izacard et al. (2022) Izacard, G., Caron, M., Hosseini, L., Riedel, S., Bojanowski, P., Joulin, A., and Grave, E.  Unsupervised dense information retrieval with contrastive learning.  _TMLR_ , 2022. 
  * Izacard et al. (2023) Izacard, G., Lewis, P., Lomeli, M., Hosseini, L., Petroni, F., Schick, T., Dwivedi-Yu, J., Joulin, A., Riedel, S., and Grave, E.  Atlas: Few-shot learning with retrieval augmented language models.  _JMLR_ , 24(251):1–43, 2023. 
  * Jeong et al. (2024) Jeong, S., Baek, J., Cho, S., Hwang, S. J., and Park, J. C.  Adaptive-rag: Learning to adapt retrieval-augmented large language models through question complexity.  In _NAACL_ , 2024. 
  * Jiang et al. (2024) Jiang, A. Q., Sablayrolles, A., Roux, A., Mensch, A., Savary, B., Bamford, C., Chaplot, D. S., Casas, D. d. l., Hanna, E. B., et al.  Mixtral of experts.  _arXiv preprint arXiv:2401.04088_ , 2024. 
  * Jiang et al. (2023) Jiang, Z., Xu, F. F., Gao, L., Sun, Z., Liu, Q., Dwivedi-Yu, J., Yang, Y., Callan, J., and Neubig, G.  Active retrieval augmented generation.  In _EMNLP_ , 2023. 
  * Jin et al. (2021) Jin, D., Pan, E., Oufattole, N., Weng, W.-H., Fang, H., and Szolovits, P.  What disease does this patient have? a large-scale open domain question answering dataset from medical exams.  _Applied Sciences_ , 11(14):6421, 2021. 
  * Jin et al. (2019) Jin, Q., Dhingra, B., Liu, Z., Cohen, W., and Lu, X.  Pubmedqa: A dataset for biomedical research question answering.  In _EMNLP_ , 2019. 
  * Jin et al. (2023) Jin, Q., Kim, W., Chen, Q., Comeau, D. C., Yeganova, L., Wilbur, W. J., and Lu, Z.  Medcpt: Contrastive pre-trained transformers with large-scale pubmed search logs for zero-shot biomedical information retrieval.  _Bioinformatics_ , 39(11), 2023. 
  * Joshi et al. (2017) Joshi, M., Choi, E., Weld, D., and Zettlemoyer, L.  TriviaQA: A large scale distantly supervised challenge dataset for reading comprehension.  In _ACL_ , 2017. 
  * Karpukhin et al. (2020) Karpukhin, V., Oguz, B., Min, S., Lewis, P., Wu, L., Edunov, S., Chen, D., and Yih, W.-t.  Dense passage retrieval for open-domain question answering.  In _EMNLP_ , 2020. 
  * Kasai et al. (2023) Kasai, J., Sakaguchi, K., yoichi takahashi, Bras, R. L., Asai, A., Yu, X. V., Radev, D., Smith, N. A., Choi, Y., and Inui, K.  Realtime QA: What’s the answer right now?  In _NeurIPS_ , 2023. 
  * Khalifa et al. (2023) Khalifa, M., Logeswaran, L., Lee, M., Lee, H., and Wang, L.  Few-shot reranking for multi-hop QA via language model prompting.  In _ACL_ , 2023. 
  * Khattab et al. (2022) Khattab, O., Santhanam, K., Li, X. L., Hall, D., Liang, P., Potts, C., and Zaharia, M.  Demonstrate-search-predict: Composing retrieval and language models for knowledge-intensive nlp.  _arXiv preprint arXiv:2212.14024_ , 2022. 
  * Kim et al. (2023) Kim, H., Hessel, J., Jiang, L., Lu, X., Yu, Y., Zhou, P., Bras, R. L., Alikhani, M., Kim, G., Sap, M., et al.  Soda: Million-scale dialogue distillation with social commonsense contextualization.  In _EMNLP_ , 2023. 
  * Kingma & Ba (2014) Kingma, D. P. and Ba, J.  Adam: A method for stochastic optimization.  _arXiv preprint arXiv:1412.6980_ , 2014. 
  * Kočiskỳ et al. (2018) Kočiskỳ, T., Schwarz, J., Blunsom, P., Dyer, C., Hermann, K. M., Melis, G., and Grefenstette, E.  The narrativeqa reading comprehension challenge.  _TACL_ , 2018. 
  * Kwiatkowski et al. (2019) Kwiatkowski, T., Palomaki, J., Redfield, O., Collins, M., Parikh, A., Alberti, C., Epstein, D., Polosukhin, I., Devlin, J., Lee, K., et al.  Natural questions: a benchmark for question answering research.  _TACL_ , 2019. 
  * Köpf et al. (2023) Köpf, A., Kilcher, Y., von Rütte, D., Anagnostidis, S., Tam, Z.-R., Stevens, K., Barhoum, A., Duc, N. M., Stanley, O., Nagyfi, R., ES, S., Suri, S., Glushkov, D., Dantuluri, A., Maguire, A., Schuhmann, C., Nguyen, H., and Mattick, A.  Openassistant conversations - democratizing large language model alignment.  _arXiv preprint arXiv: 2304.07327_ , 2023. 
  * Lazaridou et al. (2022) Lazaridou, A., Gribovskaya, E., Stokowiec, W., and Grigorev, N.  Internet-augmented language models through few-shot prompting for open-domain question answering.  _arXiv preprint arXiv:2203.05115_ , 2022. 
  * Lee et al. (2024) Lee, C., Roy, R., Xu, M., Raiman, J., Shoeybi, M., Catanzaro, B., and Ping, W.  Nv-embed: Improved techniques for training llms as generalist embedding models.  _arXiv preprint arXiv:2405.17428_ , 2024. 
  * Lewis et al. (2020) Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-t., Rocktäschel, T., et al.  Retrieval-augmented generation for knowledge-intensive nlp tasks.  _NeurIPS_ , 33, 2020. 
  * Lin et al. (2019) Lin, K., Tafjord, O., Clark, P., and Gardner, M.  Reasoning over paragraph effects in situations.  In _Workshop on Machine Reading for Question Answering_ , 2019. 
  * Lin et al. (2023) Lin, S.-C., Asai, A., Li, M., Oguz, B., Lin, J., Mehdad, Y., Yih, W.-t., and Chen, X.  How to train your dragon: Diverse augmentation towards generalizable dense retrieval.  In _Findings of EMNLP_ , 2023. 
  * Lin et al. (2024) Lin, X. V., Chen, X., Chen, M., Shi, W., Lomeli, M., James, R., Rodriguez, P., Kahn, J., Szilvasy, G., Lewis, M., Zettlemoyer, L., and tau Yih, W.  RA-DIT: Retrieval-augmented dual instruction tuning.  In _ICLR_ , 2024. 
  * Liu et al. (2024) Liu, Z., Ping, W., Roy, R., Xu, P., Shoeybi, M., and Catanzaro, B.  Chatqa: Surpassing gpt-4 on conversational qa and rag.  _arXiv preprint arXiv:2401.10225_ , 2024. 
  * Longpre et al. (2023) Longpre, S., Hou, L., Vu, T., Webson, A., Chung, H. W., Tay, Y., Zhou, D., Le, Q. V., et al.  The flan collection: Designing data and methods for effective instruction tuning.  In _ICML_ , 2023. 
  * Luan et al. (2021) Luan, Y., Eisenstein, J., Toutanova, K., and Collins, M.  Sparse, dense, and attentional representations for text retrieval.  _TACL_ , 2021. 
  * Luo et al. (2023) Luo, H., Chuang, Y.-S., Gong, Y., Zhang, T., Kim, Y., Wu, X., Fox, D., Meng, H., and Glass, J.  Sail: Search-augmented instruction learning.  _arXiv preprint arXiv:2305.15225_ , 2023. 
  * Ma et al. (2023) Ma, X., Wang, L., Yang, N., Wei, F., and Lin, J.  Fine-tuning llama for multi-stage text retrieval.  _arXiv preprint arXiv:2310.08319_ , 2023. 
  * Mallen et al. (2023) Mallen, A., Asai, A., Zhong, V., Das, R., Khashabi, D., and Hajishirzi, H.  When not to trust language models: Investigating effectiveness of parametric and non-parametric memories.  In _ACL_ , 2023. 
  * Menon et al. (2022) Menon, A., Jayasumana, S., Rawat, A. S., Kim, S., Reddi, S., and Kumar, S.  In defense of dual-encoders for neural ranking.  In _ICML_ , 2022. 
  * Meta-AI (2024) Meta-AI.  Llama 3 model card.  2024\. 
  * Mistral (2024) Mistral.  Mixtral 8x22b.  2024\.  URL <https://mistral.ai/news/mixtral-8x22b/>. 
  * Mitra et al. (2018) Mitra, B., Craswell, N., et al.  An introduction to neural information retrieval.  _Foundations and Trends® in Information Retrieval_ , 2018. 
  * Muennighoff et al. (2024) Muennighoff, N., Su, H., Wang, L., Yang, N., Wei, F., Yu, T., Singh, A., and Kiela, D.  Generative representational instruction tuning.  _arXiv preprint arXiv:2402.09906_ , 2024. 
  * Nogueira et al. (2020) Nogueira, R., Jiang, Z., Pradeep, R., and Lin, J.  Document ranking with a pretrained sequence-to-sequence model.  In _Findings of EMNLP_ , 2020. 
  * OpenAI (2022) OpenAI.  Introducing ChatGPT, 2022. 
  * OpenAI (2023) OpenAI.  GPT-4, 2023. 
  * Oren et al. (2024) Oren, Y., Meister, N., Chatterji, N. S., Ladhak, F., and Hashimoto, T.  Proving test set contamination in black-box language models.  In _ICLR_ , 2024. 
  * Ouyang et al. (2022) Ouyang, L., Wu, J., Jiang, X., Almeida, D., Wainwright, C., Mishkin, P., Zhang, C., Agarwal, S., Slama, K., Ray, A., et al.  Training language models to follow instructions with human feedback.  _NeurIPS_ , 35, 2022. 
  * Pal et al. (2022) Pal, A., Umapathi, L. K., and Sankarasubbu, M.  Medmcqa: A large-scale multi-subject multi-choice dataset for medical domain question answering.  In _CHIL_ , 2022. 
  * Petroni et al. (2021) Petroni, F., Piktus, A., Fan, A., Lewis, P., Yazdani, M., De Cao, N., Thorne, J., Jernite, Y., Karpukhin, V., Maillard, J., Plachouras, V., Rocktäschel, T., and Riedel, S.  KILT: a benchmark for knowledge intensive language tasks.  In _NAACL_ , 2021. 
  * Qin et al. (2024) Qin, Z., Jagerman, R., Hui, K., Zhuang, H., Wu, J., Shen, J., Liu, T., Liu, J., Metzler, D., Wang, X., et al.  Large language models are effective text rankers with pairwise ranking prompting.  In _Findings of NAACL_ , 2024. 
  * Rajpurkar et al. (2016) Rajpurkar, P., Zhang, J., Lopyrev, K., and Liang, P.  Squad: 100,000+ questions for machine comprehension of text.  In _EMNLP_ , 2016. 
  * Ram et al. (2023) Ram, O., Levine, Y., Dalmedigos, I., Muhlgay, D., Shashua, A., Leyton-Brown, K., and Shoham, Y.  In-context retrieval-augmented language models.  _TACL_ , 2023. 
  * Robertson et al. (2004) Robertson, S., Zaragoza, H., and Taylor, M.  Simple bm25 extension to multiple weighted fields.  In _CIKM_ , 2004. 
  * Sachan et al. (2021) Sachan, D. S., Reddy, S., Hamilton, W. L., Dyer, C., and Yogatama, D.  End-to-end training of multi-document reader and retriever for open-domain question answering.  In _NeurIPS_ , 2021. 
  * Shao et al. (2023) Shao, Z., Gong, Y., Shen, Y., Huang, M., Duan, N., and Chen, W.  Enhancing retrieval-augmented large language models with iterative retrieval-generation synergy.  In _Findings of EMNLP_ , 2023. 
  * Shi et al. (2024) Shi, W., Min, S., Yasunaga, M., Seo, M., James, R., Lewis, M., Zettlemoyer, L., and Yih, W.-t.  Replug: Retrieval-augmented black-box language models.  In _NAACL_ , 2024. 
  * Sun et al. (2023) Sun, W., Yan, L., Ma, X., Wang, S., Ren, P., Chen, Z., Yin, D., and Ren, Z.  Is ChatGPT good at search? investigating large language models as re-ranking agents.  In _EMNLP_ , 2023. 
  * Thakur et al. (2021) Thakur, N., Reimers, N., Rücklé, A., Srivastava, A., and Gurevych, I.  Beir: A heterogeneous benchmark for zero-shot evaluation of information retrieval models.  In _NeurIPS_ , 2021. 
  * Thorne et al. (2018) Thorne, J., Vlachos, A., Christodoulopoulos, C., and Mittal, A.  Fever: A large-scale dataset for fact extraction and verification.  In _NAACL_ , 2018. 
  * Touvron et al. (2023) Touvron, H., Martin, L., Stone, K., Albert, P., Almahairi, A., Babaei, Y., Bashlykov, N., Batra, S., Bhargava, P., Bhosale, S., et al.  Llama 2: Open foundation and fine-tuned chat models.  _arXiv preprint arXiv:2307.09288_ , 2023. 
  * Trischler et al. (2017) Trischler, A., Wang, T., Yuan, X., Harris, J., Sordoni, A., Bachman, P., and Suleman, K.  Newsqa: A machine comprehension dataset.  In _RepL4NLP Workshop at ACL_ , 2017. 
  * Trivedi et al. (2023) Trivedi, H., Balasubramanian, N., Khot, T., and Sabharwal, A.  Interleaving retrieval with chain-of-thought reasoning for knowledge-intensive multi-step questions.  In _ACL_ , 2023. 
  * Tsatsaronis et al. (2015) Tsatsaronis, G., Balikas, G., Malakasiotis, P., Partalas, I., Zschunke, M., Alvers, M. R., Weissenborn, D., Krithara, A., Petridis, S., Polychronopoulos, D., et al.  An overview of the bioasq large-scale biomedical semantic indexing and question answering competition.  _BMC bioinformatics_ , 2015. 
  * Wang et al. (2024) Wang, B., Ping, W., McAfee, L., Xu, P., Li, B., Shoeybi, M., and Catanzaro, B.  Instructretro: Instruction tuning post retrieval-augmented pretraining.  In _ICML_ , 2024. 
  * Wang et al. (2022) Wang, L., Yang, N., Huang, X., Jiao, B., Yang, L., Jiang, D., Majumder, R., and Wei, F.  Text embeddings by weakly-supervised contrastive pre-training.  _arXiv preprint arXiv:2212.03533_ , 2022. 
  * Wang et al. (2023a) Wang, L., Yang, N., Huang, X., Yang, L., Majumder, R., and Wei, F.  Improving text embeddings with large language models.  _arXiv preprint arXiv:2401.00368_ , 2023a. 
  * Wang et al. (2023b) Wang, Y., Kordi, Y., Mishra, S., Liu, A., Smith, N. A., Khashabi, D., and Hajishirzi, H.  Self-instruct: Aligning language models with self-generated instructions.  In _ACL_ , 2023b. 
  * Wang et al. (2023c) Wang, Z., Araki, J., Jiang, Z., Parvez, M. R., and Neubig, G.  Learning to filter context for retrieval-augmented generation.  _arXiv preprint arXiv:2311.08377_ , 2023c. 
  * Wei et al. (2022) Wei, J., Bosma, M., Zhao, V. Y., Guu, K., Yu, A. W., Lester, B., Du, N., Dai, A. M., and Le, Q. V.  Finetuned language models are zero-shot learners.  In _ICLR_ , 2022. 
  * Wu et al. (2024) Wu, C., Lin, W., Zhang, X., Zhang, Y., Xie, W., and Wang, Y.  Pmc-llama: toward building open-source language models for medicine.  _JAMIA_ , 2024. 
  * Wu et al. (2023) Wu, Z., Parish, R., Cheng, H., Min, S., Ammanabrolu, P., Ostendorf, M., and Hajishirzi, H.  Inscit: Information-seeking conversations with mixed-initiative interactions.  _TACL_ , 2023. 
  * Xiong et al. (2024) Xiong, G., Jin, Q., Lu, Z., and Zhang, A.  Benchmarking retrieval-augmented generation for medicine.  _arXiv preprint arXiv:2402.13178_ , 2024. 
  * Xu et al. (2024a) Xu, F., Shi, W., and Choi, E.  RECOMP: Improving retrieval-augmented LMs with context compression and selective augmentation.  In _ICLR_ , 2024a. 
  * Xu et al. (2024b) Xu, P., Ping, W., Wu, X., McAfee, L., Zhu, C., Liu, Z., Subramanian, S., Bakhturina, E., Shoeybi, M., and Catanzaro, B.  Retrieval meets long context large language models.  In _ICLR_ , 2024b. 
  * Yang et al. (2018) Yang, Z., Qi, P., Zhang, S., Bengio, Y., Cohen, W. W., Salakhutdinov, R., and Manning, C. D.  HotpotQA: A dataset for diverse, explainable multi-hop question answering.  In _EMNLP_ , 2018. 
  * Yoran et al. (2024) Yoran, O., Wolfson, T., Ram, O., and Berant, J.  Making retrieval-augmented language models robust to irrelevant context.  In _ICLR_ , 2024. 
  * Yu et al. (2023a) Yu, W., Iter, D., Wang, S., Xu, Y., Ju, M., Sanyal, S., Zhu, C., Zeng, M., and Jiang, M.  Generate rather than retrieve: Large language models are strong context generators.  In _ICLR_ , 2023a. 
  * Yu et al. (2023b) Yu, W., Zhang, H., Pan, X., Ma, K., Wang, H., and Yu, D.  Chain-of-note: Enhancing robustness in retrieval-augmented language models.  _arXiv preprint arXiv:2311.09210_ , 2023b. 
  * Yu et al. (2024) Yu, W., Zhang, Z., Liang, Z., Jiang, M., and Sabharwal, A.  Improving language models via plug-and-play retrieval feedback, 2024. 
  * Yu et al. (2022) Yu, Y., Xiong, C., Sun, S., Zhang, C., and Overwijk, A.  Coco-dr: Combating distribution shift in zero-shot dense retrieval with contrastive and distributionally robust learning.  In _EMNLP_ , 2022. 
  * Zhang et al. (2024) Zhang, T., Patil, S. G., Jain, N., Shen, S., Zaharia, M., Stoica, I., and Gonzalez, J. E.  Raft: Adapting language model to domain specific rag.  _arXiv preprint arXiv:2403.10131_ , 2024. 
  * Zhu et al. (2021) Zhu, F., Lei, W., Huang, Y., Wang, C., Zhang, S., Lv, J., Feng, F., and Chua, T.-S.  Tat-qa: A question answering benchmark on a hybrid of tabular and textual content in finance.  In _ACL_ , 2021. 
  * Zhu et al. (2024) Zhu, Y., Zhang, P., Zhang, C., Chen, Y., Xie, B., Dou, Z., Liu, Z., and Wen, J.-R.  Inters: Unlocking the power of large language models in search with instruction tuning.  In _ACL_ , 2024. 



##  Appendix A Dataset Description

The information for 14 datasets used in RankRAG is listed as follows.

###  A.1 Main Experiments

  * •

NQ (Kwiatkowski et al., [2019](https://arxiv.org/html/2407.02485v1#bib.bib42)) is a widely used question-answering dataset constructed with Wikipedia. The questions are constructed from the Google search engine, and the answers are identified as text spans in the Wikipedia article.

  * •

TriviaQA (Joshi et al., [2017](https://arxiv.org/html/2407.02485v1#bib.bib34)) is a challenging QA dataset containing question-answer pairs from trivia enthusiasts and independently gathered evidence documents.

  * •

PopQA (Mallen et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib55)) is an entity-centric QA dataset concentrated on long-tail entities. For PopQA, we follow (Asai et al., [2024a](https://arxiv.org/html/2407.02485v1#bib.bib4)) to use the long-tail subset, consisting of questions on 1399 rare entities whose monthly Wikipedia page views are less than 100.

  * •

HotpotQA (Yang et al., [2018](https://arxiv.org/html/2407.02485v1#bib.bib93)) is a multi-hop QA dataset, where the goal is to answer complex questions that require understanding and linking information from multiple documents.

  * •

2WikimQA (Ho et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib22)) is also a multi-hop QA designed to test machine understanding across two different Wikipedia entities, evaluating the ability of systems to handle cross-lingual and cross-cultural retrieval and question answering.

  * •

FEVER (Thorne et al., [2018](https://arxiv.org/html/2407.02485v1#bib.bib77)) is a fact verification dataset aimed at supporting research into the automatic verification of factual claims. It consists of claims that are manually verified against evidence from Wikipedia, providing a benchmark for fact-checking systems. 

  * •

Doc2Dial (Feng et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib18)) is a document-grounded conversational QA dataset covering four domains: DMV, SSA, VA, and Student Aid. Each sample comprises a dialogue where a user poses queries regarding the document, and an agent responds those questions. The average document length is around 101K words.

  * •

TopiOCQA (Adlakha et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib1)) is grounded on the whole Wikipedia. It incorporates topic switching and requires the agent to search the entire Wikipedia for answers to user questions. 

  * •

INSCIT (Wu et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib89)) is also grounded on the whole Wikipedia. It studies the case where user questions are under-specified and require clarification.




###  A.2 Biomedical Benchmarks

  * •

MMLU-med (Hendrycks et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib21)) is a subset of six tasks related to biomedicine, including anatomy, clinical knowledge, professional medicine, human genetics, college medicine, and college biology. It contains 1089 questions in total.

  * •

MedQA (Jin et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib31)) is collected from the US Medical Licensing Examination, contaiing 1273 four-option multiple-choice questions focused on real-world scenarios from professional medical board exams.

  * •

MedMCQA (Pal et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib66)) includes multiple-choice questions derived from Indian medical entrance exams, covering 2400 healthcare topics across 21 medical subjects. We use the 4,183-question development set from MedMCQA, as the test set lacks provided ground truths.

  * •

PubmedQA (Jin et al., [2019](https://arxiv.org/html/2407.02485v1#bib.bib32)) is a biomedical research QA dataset consisting of 1000 manually annotated questions based on PubMed abstracts. Answers in PubMedQA are structured as yes/no/maybe to reflect the validity of the questions.

  * •

BioASQ (Tsatsaronis et al., [2015](https://arxiv.org/html/2407.02485v1#bib.bib81)) includes 618 questions constructed from biomedical literature without providing the ground truth snippets, challenging RAG systems to infer answers independently.




##  Appendix B Data Blending Details for Ranking-enhanced Instruction Finetuning

The dataset blending ratio for Stage-II is as follows:

  * •

Drop: 0.069

  * •

narrativeqa: 0.09

  * •

quoref: 0.026

  * •

ropes: 0.026

  * •

Squad (Retrieval-augmented QA): 0.09

  * •

Squad (Retrieval-augmented Ranking): 0.02

  * •

WebQuestions (Retrieval-augmented QA): 0.09

  * •

WebQuestions (Retrieval-augmented Ranking): 0.02

  * •

newsqa: 0.09

  * •

tatqa-arithmetic: 0.15

  * •

tatqa-others: 0.08

  * •

ConvQA: 0.2

  * •

MS MARCO ranking: 0.15

  * •

ConvQA ranking: 0.03

  * •

SFT: 0.2




The ratio for each dataset is further normalized to ensure the total ratio equals to 1.

##  Appendix C Prompt Formats of Instruction Tuning

###  C.1 Stage I: Supervised Fine-tuning

The format template of LLM inputs in stage-I is as follows:
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    User: {Question 1}
    
    Assistant: {Answer 1}
    
    ...
    
    User: {Latest Question}
    
    Assistant:
    

###  C.2 Stage-II: Unified Instruction-Tuning for Ranking and Generation

The format template of LLM inputs in stage-II are as follows:

1) Context-rich QA data
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage: {(Gold) Passage containing relevant context for QA}
    
    User: {Question 1}
    
    Assistant: {Answer 1}
    
    ...
    
    User: {Latest Question}
    
    Assistant:
    

We tailor specific user instructions for various dataset types. For instance:

For datasets requiring short answers (such as DROP, NarrativeQA, Quoref, ROPES, SQuAD1.1, SQuAD2.0, NewsQA), we use: "Answer the following question with a short span."

For datasets that necessitate long answers (such as Synthetic_ConvQA), we instruct: "Please give a full and complete answer for the question."

For datasets involving arithmetic calculations or number extraction from the context (such as TAT-QA), we specify: "Answer the following question with a number from the context or through math arithmetic."

For datasets that may require both short and long answers (such as TAT-QA-Others), we direct: "Answer the following question with a short span, or a full and complete answer."

2) Retrieval-augmented QA data
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage 1: {(Shuffled) Passage 1}
    
    Passage 2: {(Shuffled) Passage 2}
    
    Passage 3: {(Shuffled) Passage 3}
    
    Passage 4: {(Shuffled) Passage 4}
    
    Passage 5: {(Shuffled) Passage 5}
    
    ...
    
    User: {Question}
    
    Assistant:
    

3) Context ranking data
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage: {Passage 1}
    
    User: {For the question <question>, access whether the passage is relevant to the
    question. Return True if relevant, otherwise False. }
    
    Assistant:
    

4) Retrieval-augmented ranking data
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage 1: {(Shuffled) Passage 1}
    
    Passage 2: {(Shuffled) Passage 2}
    
    Passage 3: {(Shuffled) Passage 3}
    
    Passage 4: {(Shuffled) Passage 4}
    
    Passage 5: {(Shuffled) Passage 5}
    
    User: {For the question <question>, access whether the above passages are relevant
    to the question. Return all the relevant passage id. }
    
    Assistant:
    

##  Appendix D Prompt Formats of Target Tasks

###  D.1 Context Ranking

NQ/TriviaQA/HotpotQA/PopQA:
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage: {Passage}
    
    User: {For the question <question>, access whether the passage is relevant to the
    question. Return True if relevant, otherwise False. }
    
    Assistant:
    

FEVER:
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage: {Passage}
    
    User: {For the claim <claim>, access whether the passage is relevant to the
    claim. Return True if relevant, otherwise False. }
    
    Assistant:
    

Doc2dial, Inscit, TopiocQA:
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage: {Passage}
    
    User: {Question 1}
    
    Assistant: {Answer 1}
    
    ...
    
    User: {For the question <latest question>, access whether the passage is relevant
    to the question. Return True if relevant, otherwise False. }
    
    Assistant:
    

###  D.2 RAG

NQ/TriviaQA/HotpotQA/PopQA:
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage 1: {Rerank Top Passage 1}
    
    Passage 2: {Rerank Top Passage 2}
    
    Passage 3: {Rerank Top Passage 3}
    
    Passage 4: {Rerank Top Passage 4}
    
    Passage 5: {Rerank Top Passage 5}
    
    ...
    
    User: {Question}. Answer the above question with a short phrase.
    
    Assistant:
    

Fever:
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage 1: {Rerank Top Passage 1}
    
    Passage 2: {Rerank Top Passage 2}
    
    Passage 3: {Rerank Top Passage 3}
    
    Passage 4: {Rerank Top Passage 4}
    
    Passage 5: {Rerank Top Passage 5}
    
    ...
    
    User: Answer the following question with True or False. Is the claim ’<claim>’ correct?
    
    Assistant:
    

Doc2dial, Inscit, TopiOCQA:
    
    
    System: This is a chat between a user and an artificial intelligence assistant.
    The assistant gives helpful, detailed, and polite answers to the user’s questions
    based on the context. The assistant should also indicate when the answer cannot be
    found in the context.
    
    Passage 1: {Rerank Top Passage 1}
    
    Passage 2: {Rerank Top Passage 2}
    
    Passage 3: {Rerank Top Passage 3}
    
    Passage 4: {Rerank Top Passage 4}
    
    Passage 5: {Rerank Top Passage 5}
    
    User: {Question 1}
    
    Assistant: {Answer 1}
    
    ...
    User: {Latest Question}
    
    Assistant:
    

##  Appendix E Additional Experiment Results

###  E.1 Ranking Performance Using DPR and Contriever as Retrievers ℛ\mathcal{R}

Table [8](https://arxiv.org/html/2407.02485v1#A5.T8 "Table 8 ‣ E.1 Ranking Performance Using DPR and Contriever as Retrievers ℛ ‣ Appendix E Additional Experiment Results ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") shows the ranking performance of RankRAG-8B using DPR (Karpukhin et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib35)) and Contriever (Izacard et al., [2022](https://arxiv.org/html/2407.02485v1#bib.bib26)) on three datasets. There are consistent performance gains for all tasks, indicating that RankRAG can apply to many popular retrieval models to improve the quality of retrieved contents.

Table 8: Answer Recall Comparison Before and After Ranking on 3 Representative Datasets.

NQ | DPR | Contriever  
---|---|---  
R@5 | R@10 | R@20 | R@5 | R@10 | R@20  
Before Ranking | 69.50% | 76.20% | 81.00% | 67.60% | 75.24% | 80.67%  
w/ RankRAG | 77.95% | 81.70% | 84.56% | 75.32% | 80.18% | 84.70%  
TriviaQA | DPR | Contriever  
R@5 | R@10 | R@20 | R@5 | R@10 | R@20  
Before Ranking | 67.80% | 74.20% | 80.30% | 81.95% | 86.76% | 90.08%  
w/ RankRAG | 77.73% | 79.40% | 84.74% | 88.71% | 90.05% | 92.59%  
PopQA | DPR | Contriever  
R@5 | R@10 | R@20 | R@5 | R@10 | R@20  
Before Ranking | 43.60% | 48.90% | 54.25% | 60.61% | 65.54% | 69.90%  
w/ RankRAG | 50.32% | 53.75% | 57.76% | 65.11% | 68.41% | 71.77%  
  
###  E.2 RAG Performance with Different kk

We also show the performance of RankRAG with different context size kk in figure [10](https://arxiv.org/html/2407.02485v1#S5.F10 "Figure 10 ‣ E.2 RAG Performance with Different 𝑘 ‣ Appendix E Additional Experiment Results ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"). From the result, we observe that different from the trend of vanilla RAG approaches (without ranking), k=5k=5 already works well for most datasets. This effectiveness stems from the reranking step, which prioritizes the most relevant contexts at the top, reducing the necessity to include additional contexts.

Figure 10: Performance of RankRAG on different context size kk.

##  Appendix F Performance of NQ and Trivia QA on DPR Splits

We observe that the NQ and TriviaQA datasets exist in two versions: one used by the DPR (Karpukhin et al., [2020](https://arxiv.org/html/2407.02485v1#bib.bib35)) and FiD (Izacard & Grave, [2021](https://arxiv.org/html/2407.02485v1#bib.bib25)) papers, which include 3610 and 11316 questions for NQ and TriviaQA, respectively. In contrast, the KILT benchmark (Petroni et al., [2021](https://arxiv.org/html/2407.02485v1#bib.bib67)) utilizes only subsets of these, comprising 2837 and 5355 examples for NQ and TriviaQA, respectively. It is noteworthy that many recent studies report performance metrics on these datasets without clarifying which version was employed for evaluation.

To facilitate an _honest_ and _fair_ comparison, we present the performance of RankRAG on both datasets using the DPR splits in Table [9](https://arxiv.org/html/2407.02485v1#A6.T9 "Table 9 ‣ Appendix F Performance of NQ and Trivia QA on DPR Splits ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs"). Notably, regardless of the subset used, RankRAG consistently outperforms both ChatQA and Llama-3-instruct, our direct competitors, as well as other methods utilizing InstructGPT as backbones. We aim for these results to assist the community in making accurate comparisons when referring to the performance of RankRAG.

Table 9: Performance Across Models. 

Model | Model Configuration | NQ EM (%) | TriviaQA EM / Acc. (%)  
---|---|---|---  
_Representative Baselines_ |   
OpenAI GPT | GPT-3.5-0613 | 35.2 | 70.1 / 81.3  
GPT-3.5-0613 RAG | 42.3 | 65.8 / 76.7  
GPT-4-0613 | 37.2 | 72.6 / 85.1  
GPT-4-0613 RAG | 36.2 | 61.2 / 75.9  
GPT-4-turbo-2024-0409 | 38.3 | 68.0 / 84.5  
GPT-4-turbo-2024-0409 RAG | 36.3 | 57.6 / 79.2  
_Using Llama-2(Touvron et al., [2023](https://arxiv.org/html/2407.02485v1#bib.bib78)) as the backbone LLM_ |   
Llama-2-Chat | Llama-2 RAG 70B | 37.7 | 65.6 / –  
ChatQA-1.0 | Llama-2 7B | 37.0 | 62.4 / 74.3  
Llama-2 13B | 43.9 | 66.6 / 76.9  
Llama-2 70B | 45.0 | 69.8 / 80.2  
RankRAG | Llama-2 7B | 42.4 | 68.3 / 78.9  
Llama-2 13B | 46.2 | 69.5 / 80.0  
Llama-2 70B | 48.7 | 72.3 / 82.6  
_Using Llama-3(Meta-AI, [2024](https://arxiv.org/html/2407.02485v1#bib.bib57)) as the backbone LLM_ |   
Llama-3-Instruct | Llama-3-Instruct RAG 8B | 27.6 | 57.1 / 74.6  
Llama-3-Instruct RAG 70B | 37.3 | 67.6 / 79.6  
ChatQA-1.5 | Llama-3 8B | 44.1 | 65.4 / 75.8  
Llama-3 70B | 46.0 | 69.0 / 80.4  
RankRAG | Llama-3 8B | 46.1 | 68.8 / 79.9  
Llama-3 70B | 50.0 |  72.6 / 82.9  
  
##  Appendix G Additional Case Studies

Tables [10](https://arxiv.org/html/2407.02485v1#A7.T10 "Table 10 ‣ Appendix G Additional Case Studies ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") and [11](https://arxiv.org/html/2407.02485v1#A7.T11 "Table 11 ‣ Appendix G Additional Case Studies ‣ 6 Conclusion ‣ 5.6 Case StudyIn 5.5 A Closer Look at the Ranking Module ‣ 5.4 Experiment on Domain-specific RAG Benchmarks ‣ 6\(a\) ‣ 5.3 Ablation Studies ‣ 5 Experiments ‣ 4.3 RankRAG Inference: Retrieve-Rerank-Generate Pipeline ‣ 4 RankRAG ‣ 3.2 Limitation of Current RAG Pipelines ‣ 3 Preliminaries ‣ 2 Related Work ‣ RankRAG: Unifying Context Ranking with Retrieval-Augmented Generation in LLMs") provide additional examples from the PopQA and HotpotQA datasets, which focus on long-tailed and multi-hop QA. These tasks are particularly challenging for retrievers, making it difficult to obtain relevant context from the corpus. Consequently, ChatQA-1.5 often struggles to produce the correct answers. However, the reranking step in RankRAG helps counteract poor initial retrieval by finding more pertinent evidence. Coupled with RAG-oriented finetuning, RankRAG effectively filters out distracting entities and pinpoints the correct answers.

Table 10: A case study on the top-retrieved context and predictions on PopQA dataset, illustrating the effectiveness of RankRAG-8B over ChatQA-1.5-8B. Red text denotes distractors, while green stands for evidences. 

Q: Who is the author of The Universe Around Us? A: James Hopwood Jeans / James Jeans / Sir James Jeans / Sir James Hopwood Jeans  
---  
ChatQA-1.5 |  Passage 1: Hooper is the author of two books published by Smithsonian Books/HarperCollins. The first, Dark Cosmos: In Search of our Universe’s Missing Mass and Energy (2006) was named a notable book by Seed Magazine. His second book, Nature’s Blueprint: Supersymmetry and the Search for a Unified Theory of Matter and Force (2008), was called "essential reading" by New Scientist…  
Passage 2: Fraknoi is the author or co-author of 14 books in the field of astronomy. He was the lead author of Voyages through the Universe, an introductory college astronomy textbook published by Brooks-Cole, which went through three editions. In the 1980s, he co-edited with Byron Preiss two collections of science articles and science fiction stories, "The Universe" and "The Planets." With Sidney Wolff, Fraknoi founded and was co-editor of the first on-line journal devoted to astronomy education, "Astronomy Education Review"…  
Passage 3: The Universe" and "The Planets." With Sidney Wolff, Fraknoi founded and was co-editor of the first on-line journal devoted to astronomy education, "Astronomy Education Review". He edited two collections of resources for K-12 teachers, The Universe at Your Fingertips and More Universe at Your Fingertips published through the Astronomical Society of…  
Passage 4: Lincoln Kinnear Barnett (1909–1979) was an editor and author, most notably at Life Magazine for many years. Lincoln Barnett wrote a number of books, including "The Universe and Doctor Einstein"  
Passage 5: The Universe Maker is a science fiction novel by American author A.E. van Vogt, published in 1953 by Ace Books as an Ace Double with The World of Null-A. It is based on the authorś "The Shadow Men" (Startling Stories, 1950). Set 400 years into the future, the main character is Morton Cargill, a U.S. Army officer who served in the Korean War… Prediction: Lincoln Barnett (✘)  
RankRAG |  Passage 1: The Universe Around Us is a science book written by English astrophysicist Sir James Jeans, first published in 1929 by the Syndics of the Cambridge University Press….  
Passage 2: These books made Jeans fairly well known as an expositor of the revolutionary scientific discoveries of his day, especially in relativity and physical cosmology. In 1939, the Journal of the British Astronomical Association reported that Jeans was going to stand as a candidate for  
Passage 3: James Jeans books for the lay public, including "The Stars in Their Courses" (1931), "The Universe Around Us", "Through Space and Time" (1934), "The New Background of Science" (1933), and "The Mysterious Universe.  
Passage 4: The Universe Around Us no special scientific knowledge. Parts of the book cover the same ground as various lectures I have recently delivered to University and other audiences, including a course of wireless talks I gave last autumn. It has been found necessary to rewrite these almost in their entirety, so that very few sentences remain in their original form, but those who have asked me to publish my lectures and wireless talks will find the substance of them in the present book.  
Passage 5:Lincoln Barnett Lincoln Kinnear Barnett (1909–1979) was an editor and author, most notably at Life Magazine for many years. Lincoln Barnett wrote a number of books, including "The Universe and Doctor Einstein", "The World We Live In", and "The Treasure of Our Tongue". The Universe and Doctor Einstein is a laymanś introduction to the theory of relativity. It includes a foreword by Albert Einstein, and has been reprinted several times… Prediction: Sir James Jeans (✓)  
  
Table 11: A case study on the top-retrieved context and predictions on HotpotQA dataset, illustrating the effectiveness of RankRAG-8B over ChatQA-1.5-8B. Red text denotes distractors, while green stands for evidences. 

Q: Which song did Eminem and Rihanna collaborate on after their other collaboration song in studio album "Unapologetic?" A: The Monster  
---  
ChatQA-1.5 |  Passage 1: Unapologetic is the seventh studio album by Barbadian singer Rihanna. It was released on November 19, 2012, by Def Jam Recordings and SRP Records. It was recorded between June and November 2012, during promotion of her sixth album, "Talk That Talk" (2011). As executive producer, Rihanna enlisted previous collaborators The-Dream, David Guetta, Chase & Status, and StarGate to work alongside new collaborators such as Parker Ighile, Mike Will Made-It, and Labrinth…  
Passage 2: Def Jam France announced via Twitter that Rihanna would release a new single the upcoming week while her seventh studio album was scheduled to be released in November 2012. On October 11, 2012, in one of her tweets revealed that the title of her new album is "Unapologetic" alongside with its cover. "What Now" was written by British singer-songwriter Livvi Franc together with Rihanna, Parker Ighile and Nathan Cassells, while the production of the song was done by the latter two. Ighile and Cassells…  
Passage 3: Justin then went on to co write "Stay" with Mikky Ekko and recorded by Barbadian singer Rihanna for her seventh studio album, "Unapologetic" (2012). It features guest vocals by Mikky Ekko, and was released as the second single from the album on 7 January 2013. The song reached the top five of twenty-four countries worldwide including number four in the UK and number three on the US Billboard Hot 100, becoming Rihanna’s twenty-fourth top ten on the latter chart…  
Passage 4: Via her official Twitter account, Rihanna posted series of "teasing" tweets announcing her seventh studio album. On October 11, 2012, in one of her tweets revealed that the title of her new album is "Unapologetic" alongside with its cover. "Jump" is the overall seventh and final single off Unapologetic. It was written by Kevin Cossom and M. B. Williams together with its producers StarGate (Mikkel S. Eriksen and Tor Erik Hermansen) and Chase & Status (Saul Milton  
Passage 5: copies of the song were sold in the UK, making "Love the Way You Lie" the country’s biggest-selling song of 2010. The same year, a sequel to the single, titled "Love the Way You Lie (Part II)" was released as part of Rihanna’s fifth studio album "Loud"; it mainly views matters from the female protagonist perspective. In November 2012, Eminem and Rihanna collaborated again on "Numb", which was included on Rihanna’s seventh album "Unapologetic"… Prediction: Love the Way You Lie (✘)  
RankRAG |  Passage 1: The Monster (song). Copies of the song were sold in the UK, making "Love the Way You Lie" the country’s biggest-selling song of 2010. The same year, a sequel to the single, titled "Love the Way You Lie (Part II)" was released as part of Rihanna’s fifth studio album "Loud"; it mainly views matters from the female protagonist perspective. In November 2012, Eminem and Rihanna collaborated again on "Numb", which was included on Rihanna’s seventh album "Unapologetic"….  
Passage 2: "Numb" is a song by Barbadian singer Rihanna from her seventh studio album "Unapologetic" (2012). It features guest vocals by American rapper Eminem, making it the pair’s third collaboration since the two official versions of "Love the Way You Lie". Following the album’s release, "Numb" charted on multiple charts worldwide including in Canada, the United Kingdom and the United States. "Numb" lasts for a duration of .  
Passage 3: Eminem also wanted to experiment with "retro, vintage" sounds such as beatbreaks and scratches, and he felt that Rubin could help him "take that to another level." Rihanna, with whom Eminem previously collaborated on "Love the Way You Lie" from Eminem’s previous studio effort, "Recovery" (2010), was featured on the song "The Monster". On September 11, 2013, she hinted at the…  
Passage 4: together with Jay-Z, Bono and The Edge for the same campaign to alleviate the 2010 Haiti earthquake. In summer 2010, Rihanna collaborated with rapper Eminem on "Love the Way You Lie", which was a major worldwide success, reaching No. 1 in over 20 countries. Reaching number 2, the song became the biggest-selling song of 2010 in the UK and the first of Rihanna’s singles to sell over a million copies in the country. In October 2010, Rihanna switched managers …  
Passage 5: Eminem asked for more tracks and subsequently heard "Love the Way You Lie". He chose it and told his manager Paul Rosenberg he wanted to collaborate with the Barbadian singer Rihanna. Eminem told Skyrock, "It’s one of those tracks that I felt like only she could pull it off." Rosenberg sent the track to Rihanna, who accepted Eminem’s request "at the last moment." Eminem then wrote the rapped verses. Prediction: The Monster (✓)  
  
Generated on Wed Sep 17 17:55:42 2025 by [LaTeXML](http://dlmf.nist.gov/LaTeXML/)
