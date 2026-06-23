<!-- Source: https://arxiv.org/html/2310.06839v2 | Tier: A | Topic: context-compression | Fetched: 2026-06-23 -->

  1. [1 Introduction](https://arxiv.org/html/2310.06839v2#S1 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  2. [2 Problem Formulation](https://arxiv.org/html/2310.06839v2#S2 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  3. [3 Preliminary: LLMLingua](https://arxiv.org/html/2310.06839v2#S3 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  4. [4 LongLLMLingua](https://arxiv.org/html/2310.06839v2#S4 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     1. [4.1 How to improve key information density in the prompt?](https://arxiv.org/html/2310.06839v2#S4.SS1 "In 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
        1. [Question-Aware Coarse-Grained Compression](https://arxiv.org/html/2310.06839v2#S4.SS1.SSS0.Px1 "In 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
        2. [Question-Aware Fine-Grained Compression](https://arxiv.org/html/2310.06839v2#S4.SS1.SSS0.Px2 "In 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     2. [4.2 How to reduce information loss in the middle?](https://arxiv.org/html/2310.06839v2#S4.SS2 "In 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     3. [4.3 How to achieve adaptive granular control during compression?](https://arxiv.org/html/2310.06839v2#S4.SS3 "In 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     4. [4.4 How to improve the integrity of key information?](https://arxiv.org/html/2310.06839v2#S4.SS4 "In 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  5. [5 Experiments](https://arxiv.org/html/2310.06839v2#S5 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     1. [Implementation details](https://arxiv.org/html/2310.06839v2#S5.SS0.SSS0.Px1 "In 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     2. [Dataset & evaluation metric](https://arxiv.org/html/2310.06839v2#S5.SS0.SSS0.Px2 "In 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     3. [Baselines](https://arxiv.org/html/2310.06839v2#S5.SS0.SSS0.Px3 "In 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     4. [Main results](https://arxiv.org/html/2310.06839v2#S5.SS0.SSS0.Px4 "In 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     5. [Ablation study](https://arxiv.org/html/2310.06839v2#S5.SS0.SSS0.Px5 "In 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     6. [Latency evaluation](https://arxiv.org/html/2310.06839v2#S5.SS0.SSS0.Px6 "In 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  6. [6 Related Works](https://arxiv.org/html/2310.06839v2#S6 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  7. [7 Conclusion](https://arxiv.org/html/2310.06839v2#S7 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  8. [A Derivation Of Question-Aware Fine-Grained Compression](https://arxiv.org/html/2310.06839v2#A1 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  9. [B Experiment Details](https://arxiv.org/html/2310.06839v2#A2 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     1. [B.1 Dataset Details](https://arxiv.org/html/2310.06839v2#A2.SS1 "In Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
        1. [NaturalQuestions multi-document QA](https://arxiv.org/html/2310.06839v2#A2.SS1.SSS0.Px1 "In B.1 Dataset Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
        2. [LongBench](https://arxiv.org/html/2310.06839v2#A2.SS1.SSS0.Px2 "In B.1 Dataset Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
        3. [ZeroSCROLLS](https://arxiv.org/html/2310.06839v2#A2.SS1.SSS0.Px3 "In B.1 Dataset Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
        4. [MuSiQue](https://arxiv.org/html/2310.06839v2#A2.SS1.SSS0.Px4 "In B.1 Dataset Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
        5. [LooGLE](https://arxiv.org/html/2310.06839v2#A2.SS1.SSS0.Px5 "In B.1 Dataset Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     2. [B.2 Other Implementation Details](https://arxiv.org/html/2310.06839v2#A2.SS2 "In Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  10. [C Additional Experimental Results](https://arxiv.org/html/2310.06839v2#A3 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     1. [C.1 Empirical Study of Question-aware Fine-grained Compression](https://arxiv.org/html/2310.06839v2#A3.SS1 "In Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     2. [C.2 Ablation in LongBench](https://arxiv.org/html/2310.06839v2#A3.SS2 "In Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     3. [C.3 LongBench Using LongChat-13b-16k](https://arxiv.org/html/2310.06839v2#A3.SS3 "In Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     4. [C.4 ZeroSCROLLS](https://arxiv.org/html/2310.06839v2#A3.SS4 "In Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     5. [C.5 MuSiQue](https://arxiv.org/html/2310.06839v2#A3.SS5 "In Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
     6. [C.6 LooGLE](https://arxiv.org/html/2310.06839v2#A3.SS6 "In Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  11. [D Economic Cost](https://arxiv.org/html/2310.06839v2#A4 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  12. [E Ablation Analysis](https://arxiv.org/html/2310.06839v2#A5 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")
  13. [F Cases Study](https://arxiv.org/html/2310.06839v2#A6 "In LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")



#  LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression

Huiqiang Jiang, Qianhui Wu, Xufang Luo,   
Dongsheng Li, Chin-Yew Lin, Yuqing Yang, Lili Qiu   
Microsoft Corporation   
{hjiang,qianhuiwu,xufluo,dongsli,cyl,yuqyang,liliqiu}@microsoft.com   


###### Abstract

In long context scenarios, large language models (LLMs) face three main challenges: higher computational cost, performance reduction, and position bias. Research indicates that LLM performance hinges on the density and position of key information in the input prompt. Inspired by these findings, we propose LongLLMLingua for prompt compression towards improving LLMs’ perception of the key information to simultaneously address the three challenges. Our extensive evaluation across various long context scenarios demonstrates that LongLLMLingua not only enhances performance but also significantly reduces costs and latency. For instance, in the NaturalQuestions benchmark, LongLLMLingua boosts performance by up to 21.4% with around 4x fewer tokens in GPT-3.5-Turbo, leading to substantial cost savings. It achieves a 94.0% cost reduction in the LooGLE benchmark. Moreover, when compressing prompts of about 10k tokens at ratios of 2x-6x, LongLLMLingua can accelerate end-to-end latency by 1.4x-2.6x.111Access our code at <https://aka.ms/LongLLMLingua>.

LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression

  


Huiqiang Jiang, Qianhui Wu, Xufang Luo, Dongsheng Li, Chin-Yew Lin, Yuqing Yang, Lili Qiu Microsoft Corporation {hjiang,qianhuiwu,xufluo,dongsli,cyl,yuqyang,liliqiu}@microsoft.com

  


##  1 Introduction

Large language models (LLMs) have revolutionized user-oriented language technologies and are serving as crucial components in more and more applications. Carefully designing prompts is necessary to achieve better performance in specific downstream tasks. The commonly used technologies such as In-Context Learning (ICL) (Min et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib26); Dong et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib11)), Retrieval Augment Generation (RAG) (Lewis et al., [2020](https://arxiv.org/html/2310.06839v2#bib.bib21); Asai et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib1)), and Multi-turn Agent (Shen et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib35); Park et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib30); Wu et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib40)) are driving prompts to be increasingly longer, even reaching thousands of tokens. Scenarios such as multi-document question answering, code completion, and document summarization also necessitate the processing of long contexts.

There are three main challenges when LLMs are used in long context scenarios: (1) Higher computational costs, encompassing both financial and latency expenses. (2) Longer prompts introduce irrelevant and redundant information, which can weaken LLMs’ performance (Shi et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib36)), as illustrated in Figure [1a](https://arxiv.org/html/2310.06839v2#S1.F1.sf1 "In Figure 1 ‣ 1 Introduction ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). (3) LLMs exhibit position bias Kamradt ([2023](https://arxiv.org/html/2310.06839v2#bib.bib18)), also known as the "lost in the middle" issue (Liu et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib25)), suggesting that the placement of key information within the prompt significantly affects LLMs’ performance. This is demonstrated by the purple curve in Figure [1b](https://arxiv.org/html/2310.06839v2#S1.F1.sf2 "In Figure 1 ‣ 1 Introduction ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression").

(a) Performance v.s. Document Number

(b) Performance v.s. Key Information Position

Figure 1: (a) LLMs’ performance in downstream tasks decreases with increased noise in prompts. In this case, we keep k𝑘kitalic_k most relevant documents/paragraphs based on the ground-truth or LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT. A larger k𝑘kitalic_k implies more noise introduced into the prompt. To improve the key information density in the prompt, we present question-aware coarse-to-fine compression. (b) LLMs’ ability to capture the relevant information depends on their positions in the prompt. To reduce information loss in the middle, we introduce a document reordering mechanism. 

Inspired by these observations, we propose LongLLMLingua to address the three challenges. Specifically, we use LLMLingua (Jiang et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib16)) as the backbone for prompt compression to address the first challenge, i.e., reduce cost and latency. However, in the case of long contexts, the distribution of question-relevant key information in the prompt is generally dynamic and sparse. Existing prompt compression methods like LLMLingua (Jiang et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib16)) and Selective-Context (Li et al., [2023c](https://arxiv.org/html/2310.06839v2#bib.bib24)) that often fail to consider question during compression, resulting in retention of excessive noise and decreased performance. LongLLMLingua aims to improve LLMs’ perception of key information pertinent to the question, thereby overcoming the noise and position bias issues in long contexts, shown in Figure [1b](https://arxiv.org/html/2310.06839v2#S1.F1.sf2 "In Figure 1 ‣ 1 Introduction ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). The underlying principle of LongLLMLingua is that small LM are inherently capable of capturing the distribution of key information relevant to a given question.

Our main contributions are five-fold: (1) We propose a question-aware coarse-to-fine compression method to improve the key information density in the prompt (Sec. [4.1](https://arxiv.org/html/2310.06839v2#S4.SS1 "4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")); (2) We introduce a document reordering strategy to minimize position bias in LLMs. (Sec. [4.2](https://arxiv.org/html/2310.06839v2#S4.SS2 "4.2 How to reduce information loss in the middle? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")); (3) We establish dynamic compression ratios for precise control between coarse and fine compression levels (Sec. [4.3](https://arxiv.org/html/2310.06839v2#S4.SS3 "4.3 How to achieve adaptive granular control during compression? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")); (4) We propose a post-compression subsequence recovery strategy to improve the integrity of the key information ([4.4](https://arxiv.org/html/2310.06839v2#S4.SS4 "4.4 How to improve the integrity of key information? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")). (5) We evaluate LongLLMLingua across five benchmarks, i.e., NaturalQuestions (Liu et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib25)), LongBench (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2)), ZeroSCROLLS (Shaham et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib34)), MuSicQue (Trivedi et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib38)), and LooGLE (Li et al., [2023b](https://arxiv.org/html/2310.06839v2#bib.bib23)), covering a variety of long context scenarios. Experimental results reveal that LongLLMLingua’s compressed prompts outperform original prompts in terms of performance, cost efficiency, and system latency.

##  2 Problem Formulation

Following LLMLingua (Jiang et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib16)), we use 𝐱=(𝐱ins,𝐱1doc,⋯,𝐱Kdoc,𝐱que)𝐱superscript𝐱inssubscriptsuperscript𝐱doc1⋯subscriptsuperscript𝐱doc𝐾superscript𝐱que\mathbf{x}=(\mathbf{x}^{\text{ins}},\mathbf{x}^{\text{doc}}_{1},\cdots,\mathbf% {x}^{\text{doc}}_{K},\mathbf{x}^{\text{que}})bold_x = ( bold_x start_POSTSUPERSCRIPT ins end_POSTSUPERSCRIPT , bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT 1 end_POSTSUBSCRIPT , ⋯ , bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_K end_POSTSUBSCRIPT , bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT ) to represent a prompt, including the instruction 𝐱inssuperscript𝐱ins\mathbf{x}^{\text{ins}}bold_x start_POSTSUPERSCRIPT ins end_POSTSUPERSCRIPT, K𝐾Kitalic_K documents 𝐱idocsubscriptsuperscript𝐱doc𝑖\mathbf{x}^{\text{doc}}_{i}bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT, and the question 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT. However, this definition can be adjusted for specific scenarios. The objective of a prompt compression system can be formulated as:

| min𝐱~⁡Dϕ⁢(𝐲,𝐲~)+λ⁢∥𝐱~∥0,subscript~𝐱subscript𝐷italic-ϕ𝐲~𝐲𝜆subscriptdelimited-∥∥~𝐱0\min_{\widetilde{\mathbf{x}}}D_{\phi}\left(\mathbf{y},\widetilde{\mathbf{y}}% \right)+\lambda\lVert\widetilde{\mathbf{x}}\rVert_{0},roman_min start_POSTSUBSCRIPT over~ start_ARG bold_x end_ARG end_POSTSUBSCRIPT italic_D start_POSTSUBSCRIPT italic_ϕ end_POSTSUBSCRIPT ( bold_y , over~ start_ARG bold_y end_ARG ) + italic_λ ∥ over~ start_ARG bold_x end_ARG ∥ start_POSTSUBSCRIPT 0 end_POSTSUBSCRIPT , |  | (1)  
---|---|---|---  
  
where 𝐱~~𝐱\widetilde{\mathbf{x}}over~ start_ARG bold_x end_ARG represents the compressed prompt, a token-level subsequence of 𝐱𝐱\mathbf{x}bold_x. 𝐲𝐲\mathbf{y}bold_y and 𝐲~~𝐲\widetilde{\mathbf{y}}over~ start_ARG bold_y end_ARG represent the LLM-generated results from 𝐱𝐱\mathbf{x}bold_x and 𝐱~~𝐱\widetilde{\mathbf{x}}over~ start_ARG bold_x end_ARG, respectively. Dϕsubscript𝐷italic-ϕD_{\phi}italic_D start_POSTSUBSCRIPT italic_ϕ end_POSTSUBSCRIPT measures the distance function, such as KL divergence. λ𝜆\lambdaitalic_λ serves as a hyper-parameter balancing the compression ratio. Additionally, this study explores a permutation operation space over the K𝐾Kitalic_K documents (𝐱1doc,⋯,𝐱Kdoc)subscriptsuperscript𝐱doc1⋯subscriptsuperscript𝐱doc𝐾(\mathbf{x}^{\text{doc}}_{1},\cdots,\mathbf{x}^{\text{doc}}_{K})( bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT 1 end_POSTSUBSCRIPT , ⋯ , bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_K end_POSTSUBSCRIPT ) for joint optimization.

Figure 2: Framework of LongLLMLingua. Gray Italic content: As in LLMLingua.

##  3 Preliminary: LLMLingua

LLMLingua (Jiang et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib16)) utilizes a small language model ℳSsubscriptℳ𝑆\mathcal{M}_{S}caligraphic_M start_POSTSUBSCRIPT italic_S end_POSTSUBSCRIPT to evaluate the perplexity of each prompt token, removing those with lower perplexities. This method is premised on the idea that tokens with lower perplexities have a negligible effect on the language model’s overall entropy gain, implying their removal slightly impacts the LLMs’ contextual understanding. This process is viewed as an application of "LM is Compression" (Delétang et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib9)). LLMLingua include three key components: budget controller, iterative token-level prompt compression, and distribution alignment, highlighted by italic text in Figure [2](https://arxiv.org/html/2310.06839v2#S2.F2 "Figure 2 ‣ 2 Problem Formulation ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). The budget controller assigns varying compression ratios to different parts of the prompt (i.e., instruction, demonstrations, question), implementing coarse-level prompt compression. Subsequent steps involve dividing intermediate results into segments and applying token-level compression iteratively, where each token’s perplexity based on preceding compressed segments. To aware different target LLMs, LLMLingua fine-tunes ℳSsubscriptℳ𝑆\mathcal{M}_{S}caligraphic_M start_POSTSUBSCRIPT italic_S end_POSTSUBSCRIPT using data from the target LLM.

##  4 LongLLMLingua

LongLLMLingua builds on LLMLingua to better compress prompts in long context scenorias. It tackles three main issues in handling lengthy contexts, as introduced in Sec. [1](https://arxiv.org/html/2310.06839v2#S1 "1 Introduction ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). This approach focuses on making LLMs more effective at recognizing key information related to the question in the prompt. It encompasses three perspectives and further incorporates a subsequence recovery strategy, as shown in Figure [2](https://arxiv.org/html/2310.06839v2#S2.F2 "Figure 2 ‣ 2 Problem Formulation ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), to enhance the accuracy and reliability of the information provided to users. In this section, we detail how each part of LongLLMLingua works to improve the LLMs deal with long context.

###  4.1 How to improve key information density in the prompt?

#### Question-Aware Coarse-Grained Compression

(a) Recall Distribution

(b) Perplexity Distribution (5th)

Figure 3: (a) Comparison of recall on NaturalQuestions Multi-documemnt QA dataset, which increases from top to bottom in terms of Recall@1. Different colors represent different types of methods. Among them, yellow represents traditional relevance methods, green signifies embedding-based methods, and red denotes rerank-based methods. (b) Comparison between perplexities and contrastive perplexities of tokens in the prompt from Multi-documemnt QA dataset. The document containing the ground-truth information is located in the 5th position. More results on position can be found in the Appendix [C.1](https://arxiv.org/html/2310.06839v2#A3.SS1 "C.1 Empirical Study of Question-aware Fine-grained Compression ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). 

In coarse-grained compression, we aim to figure out a metric rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT to evaluate the importance of each document 𝐱kdoc={xk,idoc}i=1Nksubscriptsuperscript𝐱doc𝑘superscriptsubscriptsuperscriptsubscript𝑥𝑘𝑖doc𝑖1subscript𝑁𝑘\mathbf{x}^{\text{doc}}_{k}=\\{x_{k,i}^{\text{doc}}\\}_{i=1}^{N_{k}}bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT = { italic_x start_POSTSUBSCRIPT italic_k , italic_i end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT } start_POSTSUBSCRIPT italic_i = 1 end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_N start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT end_POSTSUPERSCRIPT, where Nksubscript𝑁𝑘N_{k}italic_N start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT is the number of tokens in 𝐱kdocsubscriptsuperscript𝐱doc𝑘\mathbf{x}^{\text{doc}}_{k}bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT. We only keep 𝐱kdocsubscriptsuperscript𝐱doc𝑘\mathbf{x}^{\text{doc}}_{k}bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT with higher rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT as the intermediate compressed results. One approach to improve key information density in the compressed prompts is to calculate document-level perplexity conditioned on the question p⁢(𝐱kdoc|𝐱que)𝑝conditionalsuperscriptsubscript𝐱𝑘docsuperscript𝐱quep(\mathbf{x}_{k}^{\text{doc}}|\mathbf{x}^{\text{que}})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT ). However, this method may not be effective because documents often contain a significant amount of irrelevant information. Even when conditioned on 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT, the perplexity scores computed for entire documents may not be sufficiently distinct, rendering them an inadequate metric for document-level compression.

We propose to use the perplexity of the question 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT conditioned on different contexts 𝐱kdocsubscriptsuperscript𝐱doc𝑘\mathbf{x}^{\text{doc}}_{k}bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT p⁢(𝐱que|𝐱kdoc)𝑝conditionalsuperscript𝐱quesuperscriptsubscript𝐱𝑘docp(\mathbf{x}^{\text{que}}|\mathbf{x}_{k}^{\text{doc}})italic_p ( bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT | bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT ) to represent the association between them. We also append a restrictive statement222Specifically, ”We can get the answer to this question in the given documents”.  𝐱restrictsuperscript𝐱restrict\mathbf{x}^{\text{restrict}}bold_x start_POSTSUPERSCRIPT restrict end_POSTSUPERSCRIPT after 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT to strengthen the interconnection of 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT and 𝐱kdocsubscriptsuperscript𝐱doc𝑘\mathbf{x}^{\text{doc}}_{k}bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT. It can be regarded as a regularization term that mitigates the impact of hallucinations. This can be formulated as:

| rk=−1Nc⁢∑iNclog⁡p⁢(xique,restrict|𝐱kdoc)subscript𝑟𝑘1subscript𝑁𝑐superscriptsubscript𝑖subscript𝑁𝑐𝑝conditionalsubscriptsuperscript𝑥querestrict𝑖superscriptsubscript𝐱𝑘doc\displaystyle r_{k}=-\frac{1}{N_{c}}\sum_{i}^{N_{c}}\log p(x^{\text{que},\text% {restrict}}_{i}|\mathbf{x}_{k}^{\text{doc}})italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT = - divide start_ARG 1 end_ARG start_ARG italic_N start_POSTSUBSCRIPT italic_c end_POSTSUBSCRIPT end_ARG ∑ start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_N start_POSTSUBSCRIPT italic_c end_POSTSUBSCRIPT end_POSTSUPERSCRIPT roman_log italic_p ( italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT ) | , |  | (2)  
---|---|---|---|---  
| k∈{1,2,⋯,K}𝑘12⋯𝐾\displaystyle k\in\\{1,2,\cdots,K\\}italic_k ∈ { 1 , 2 , ⋯ , italic_K } | , |   
  
where xique,restrictsubscriptsuperscript𝑥querestrict𝑖x^{\text{que},\text{restrict}}_{i}italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT is the i𝑖iitalic_i-th token in the concatenated sequence of 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT and 𝐱restrictsuperscript𝐱restrict\mathbf{x}^{\text{restrict}}bold_x start_POSTSUPERSCRIPT restrict end_POSTSUPERSCRIPT and Ncsubscript𝑁𝑐N_{c}italic_N start_POSTSUBSCRIPT italic_c end_POSTSUBSCRIPT in the number of tokens.

Figure [3a](https://arxiv.org/html/2310.06839v2#S4.F3.sf1 "In Figure 3 ‣ Question-Aware Coarse-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") displays the recall distribution of different retrieval methods, including traditional relevance methos (BM25, Gzip (Jiang et al., [2023b](https://arxiv.org/html/2310.06839v2#bib.bib17))), embedding-based methods (OpenAI-embedding, Voyageai333https://www.voyageai.com/, BGE-large-en v1.5 (Xiao et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib42)), Sentence-BERT (Reimers and Gurevych, [2019](https://arxiv.org/html/2310.06839v2#bib.bib33)), Jina (Günther et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib14))), and reranker methods (Cohere-Rerank444https://cohere.com/rerank, BGE-llmembeder, BGE-Ranker-large), which demonstrates that our coarse-level compression approach achieves the highest recall with different numbers of retained documents, suggesting that it preserves the most key information from the contexts in the compressed results.

#### Question-Aware Fine-Grained Compression

In fine-grained compression, we assess the importance of each token in the instruction 𝐱inssuperscript𝐱ins\mathbf{x}^{\text{ins}}bold_x start_POSTSUPERSCRIPT ins end_POSTSUPERSCRIPT, the question 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT, and K′superscript𝐾′K^{\prime}italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT documents {𝐱idoc}i=1K′superscriptsubscriptsubscriptsuperscript𝐱doc𝑖𝑖1superscript𝐾′\\{\mathbf{x}^{\text{doc}}_{i}\\}_{i=1}^{K^{\prime}}{ bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT } start_POSTSUBSCRIPT italic_i = 1 end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUPERSCRIPT retained after coarse-grained compression. We incorporate the iterative compression mechanism following LLMLingua and directly calculate token perplexities to compress 𝐱inssuperscript𝐱ins\mathbf{x}^{\text{ins}}bold_x start_POSTSUPERSCRIPT ins end_POSTSUPERSCRIPT and 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT. In this section, we investigate how to make the fine-grained token-level compression over {𝐱kdoc}k=1K′superscriptsubscriptsubscriptsuperscript𝐱doc𝑘𝑘1superscript𝐾′\\{\mathbf{x}^{\text{doc}}_{k}\\}_{k=1}^{K^{\prime}}{ bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT } start_POSTSUBSCRIPT italic_k = 1 end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUPERSCRIPT aware of the question 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT, so that the compressed results could contain more question-relevant key information.

A straightforward solution for the awareness of 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT is to simply concatenate it at the beginning of the whole context. However, this will result in low perplexities of relevant tokens in the context following the condition of question 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT, further reducing their differentiation from other tokens.

In this paper, we propose contrastive perplexity, i.e., the distribution shift caused by the condition of the question, to represent the association between the token and the question. The contrastive perplexity based importance metric sisubscript𝑠𝑖s_{i}italic_s start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT for each token xisubscript𝑥𝑖x_{i}italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT in {𝐱kdoc}k=1K′superscriptsubscriptsubscriptsuperscript𝐱doc𝑘𝑘1superscript𝐾′\\{\mathbf{x}^{\text{doc}}_{k}\\}_{k=1}^{K^{\prime}}{ bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT } start_POSTSUBSCRIPT italic_k = 1 end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUPERSCRIPT can be formulated as:

| si=perplexity⁢(xi|x<i)−perplexity⁢(xi|xque,x<i).subscript𝑠𝑖perplexityconditionalsubscript𝑥𝑖subscript𝑥absent𝑖perplexityconditionalsubscript𝑥𝑖superscript𝑥quesubscript𝑥absent𝑖s_{i}=\text{perplexity}(x_{i}|x_{<i})-\text{perplexity}(x_{i}|x^{\text{que}},x% _{<i}).italic_s start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT = perplexity ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) - perplexity ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) . |  | (3)  
---|---|---|---  
  
Additionally, we provide the derivation of its mathematical significance in the Appendix [A](https://arxiv.org/html/2310.06839v2#A1 "Appendix A Derivation Of Question-Aware Fine-Grained Compression ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), concluding that it is equivalent to conditional pointwise mutual information (Church and Hanks, [1989](https://arxiv.org/html/2310.06839v2#bib.bib8)).

Figure [3b](https://arxiv.org/html/2310.06839v2#S4.F3.sf2 "In Figure 3 ‣ Question-Aware Coarse-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") illustrates the difference between perplexities and contrastive perplexities. The distribution of perplexities appears random, making it challenging to extract information related to the question. However, tokens with high contrastive perplexities tend to cluster near the ground-truth document, which contains information relevant to the question. This suggests that the proposed contrastive perplexity can better distinguish tokens relevant to the question, thus improving the key information density in the compressed results.

###  4.2 How to reduce information loss in the middle?

Figure 4: The example of Subsequence Recovery, the red text represents the original text, and the blue text is the result after using the LLaMA 2-7B tokenizer.

As demonstrated in Figure [1b](https://arxiv.org/html/2310.06839v2#S1.F1.sf2 "In Figure 1 ‣ 1 Introduction ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), LLM achieves the highest performance when relevant information occurs at the beginning and significantly degrades if relevant information is located in the middle of long contexts. After the coarse-grained compression, we have obtained a set of documents {𝐱kdoc}k=1K′superscriptsubscriptsubscriptsuperscript𝐱doc𝑘𝑘1superscript𝐾′\\{\mathbf{x}^{\text{doc}}_{k}\\}_{k=1}^{K^{\prime}}{ bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT } start_POSTSUBSCRIPT italic_k = 1 end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUPERSCRIPT with their corresponding importance scores {rk}k=1K′superscriptsubscriptsubscript𝑟𝑘𝑘1superscript𝐾′\\{r_{k}\\}_{k=1}^{K^{\prime}}{ italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT } start_POSTSUBSCRIPT italic_k = 1 end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUPERSCRIPT indicating their association with the question 𝐱quesuperscript𝐱que\mathbf{x}^{\text{que}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT. Therefore, we reorder documents using their importance scores to better leverage LLMs’ information perception difference in positions:

| (𝐱ins,𝐱1doc,⋯,𝐱K′doc,\displaystyle(\mathbf{x}^{\text{ins}},\mathbf{x}^{\text{doc}}_{1},\cdots,% \mathbf{x}^{\text{doc}}_{K^{\prime}},( bold_x start_POSTSUPERSCRIPT ins end_POSTSUPERSCRIPT , bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT 1 end_POSTSUBSCRIPT , ⋯ , bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUBSCRIPT , | 𝐱que)⟶rk\displaystyle\mathbf{x}^{\text{que}})\stackrel{{\scriptstyle r_{k}}}{{% \longrightarrow}}bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT ) start_RELOP SUPERSCRIPTOP start_ARG ⟶ end_ARG start_ARG italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT end_ARG end_RELOP |  | (4)  
---|---|---|---|---  
| (𝐱ins,\displaystyle(\mathbf{x}^{\text{ins}},( bold_x start_POSTSUPERSCRIPT ins end_POSTSUPERSCRIPT , | 𝐱r⁢1doc,⋯,𝐱r⁢K′doc,𝐱que)\displaystyle\mathbf{x}^{\text{doc}}_{r1},\cdots,\mathbf{x}^{\text{doc}}_{rK^{% \prime}},\mathbf{x}^{\text{que}})bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_r 1 end_POSTSUBSCRIPT , ⋯ , bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_r italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUBSCRIPT , bold_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT ) |   
  
###  4.3 How to achieve adaptive granular control during compression?

In fine-grained compression, LLMLingua applies the same compression ratio over all documents obtained from budget controller. However, the key information density of different documents is different. The more relevant to the question a document is, the more budget (i.e., lower compression ratio) we should allocate to it. Therefore, we bridge coarse-grained compression to fine-grained compression and use the importance scores {rk}k=1K′superscriptsubscriptsubscript𝑟𝑘𝑘1superscript𝐾′\\{r_{k}\\}_{k=1}^{K^{\prime}}{ italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT } start_POSTSUBSCRIPT italic_k = 1 end_POSTSUBSCRIPT start_POSTSUPERSCRIPT italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_POSTSUPERSCRIPT obtained from coarse-grained compression to guide the budget allocation in fine-grained compression. In this way, we can achieve adaptive granular control on the whole.

Specifically, we first determine the initial budget for the retained documents555In LLMLingua, it is τdemssuperscript𝜏dems\tau^{\text{dems}}italic_τ start_POSTSUPERSCRIPT dems end_POSTSUPERSCRIPT for demonstrations. τdocsuperscript𝜏doc\tau^{\text{doc}}italic_τ start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT using the budget controller of LLMLingua. During fine-grained compression, we follow the iterative token-level compression algorithm in LLMLingua but dynamically assign the compression budget τkdocsuperscriptsubscript𝜏𝑘doc\tau_{k}^{\text{doc}}italic_τ start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT to each document 𝐱kdocsuperscriptsubscript𝐱𝑘doc\mathbf{x}_{k}^{\text{doc}}bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT according to the ranking index I⁢(rk)𝐼subscript𝑟𝑘I(r_{k})italic_I ( italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT ) (e.g., 0, 1) of its importance score from the coarse-grained compression. In this paper, we employ a linear scheduler for the adaptive allocation. Budget of each token xisubscript𝑥𝑖x_{i}italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT can be formulated as:

| τisubscript𝜏𝑖\displaystyle\tau_{i}italic_τ start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | =τkdoc,∀xi∈𝐱kdoc,formulae-sequenceabsentsuperscriptsubscript𝜏𝑘docfor-allsubscript𝑥𝑖subscriptsuperscript𝐱doc𝑘\displaystyle=\tau_{k}^{\text{doc}},\quad\forall x_{i}\in\mathbf{x}^{\text{doc% }}_{k},= italic_τ start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT , ∀ italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ∈ bold_x start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT , |  | (5)  
---|---|---|---|---  
| τkdocsuperscriptsubscript𝜏𝑘doc\displaystyle\tau_{k}^{\text{doc}}italic_τ start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | =max⁡(min⁡((1−2⁢I⁢(rk)K′)⁢δ⁢τ+τdoc,1),0),absent12𝐼subscript𝑟𝑘superscript𝐾′𝛿𝜏superscript𝜏doc10\displaystyle=\max(\min((1-\frac{2I(r_{k})}{K^{\prime}})\delta\tau+\tau^{\text% {doc}},1),0),= roman_max ( roman_min ( ( 1 - divide start_ARG 2 italic_I ( italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT ) end_ARG start_ARG italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT end_ARG ) italic_δ italic_τ + italic_τ start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT , 1 ) , 0 ) , |   
  
where i𝑖iitalic_i and k𝑘kitalic_k is the index of token and document, K′superscript𝐾′K^{\prime}italic_K start_POSTSUPERSCRIPT ′ end_POSTSUPERSCRIPT denotes the number of documents, and δ⁢τ𝛿𝜏\delta\tauitalic_δ italic_τ is a hyper-parameter that controls the overall budget for dynamic allocation.

###  4.4 How to improve the integrity of key information?

During the generation process, LLMs tend to replicate entities found in the prompt, such as names, places, and organizations. Compressing these entities at the token level doesn’t affect the LLMs’ understanding of semantic content but can lead to errors in the generated content.

Therefore, we propose a subsequence recovery method to restore the original content in LLMs’ responses. This method relies on the subsequence relationship among tokens in the original prompt, compressed prompt, and LLMs’ response, as shown in Figure [4](https://arxiv.org/html/2310.06839v2#S4.F4 "Figure 4 ‣ 4.2 How to reduce information loss in the middle? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression").

The overall procedure includes: i) Iterate through tokens ylsubscript𝑦𝑙y_{l}italic_y start_POSTSUBSCRIPT italic_l end_POSTSUBSCRIPT in LLMs’ response and select the longest substring 𝒚~key,l={yl,yl+1,…,yr}subscriptbold-~𝒚key𝑙subscript𝑦𝑙subscript𝑦𝑙1…subscript𝑦𝑟\bm{\widetilde{y}}_{\text{key},l}=\\{y_{l},y_{l+1},...,y_{r}\\}overbold_~ start_ARG bold_italic_y end_ARG start_POSTSUBSCRIPT key , italic_l end_POSTSUBSCRIPT = { italic_y start_POSTSUBSCRIPT italic_l end_POSTSUBSCRIPT , italic_y start_POSTSUBSCRIPT italic_l + 1 end_POSTSUBSCRIPT , … , italic_y start_POSTSUBSCRIPT italic_r end_POSTSUBSCRIPT } that appears in the compressed prompt 𝒙~bold-~𝒙\bm{\widetilde{x}}overbold_~ start_ARG bold_italic_x end_ARG. ii) Find the maximum common shortest subsequence 𝒙i,j={xi,xi+1,…,xj}subscript𝒙𝑖𝑗subscript𝑥𝑖subscript𝑥𝑖1…subscript𝑥𝑗\bm{{x}}_{i,j}=\\{x_{i},x_{i+1},...,x_{j}\\}bold_italic_x start_POSTSUBSCRIPT italic_i , italic_j end_POSTSUBSCRIPT = { italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT , italic_x start_POSTSUBSCRIPT italic_i + 1 end_POSTSUBSCRIPT , … , italic_x start_POSTSUBSCRIPT italic_j end_POSTSUBSCRIPT } in the original prompt 𝒙𝒙\bm{x}bold_italic_x, corresponding to the representation 𝒚~key,lsubscriptbold-~𝒚key𝑙\bm{\widetilde{y}}_{\text{key},l}overbold_~ start_ARG bold_italic_y end_ARG start_POSTSUBSCRIPT key , italic_l end_POSTSUBSCRIPT in the original prompt (accelerated using prefix trees or sequence automata). iii) Replace the matched tokens 𝒚~key,lsubscriptbold-~𝒚key𝑙\bm{\widetilde{y}}_{\text{key},l}overbold_~ start_ARG bold_italic_y end_ARG start_POSTSUBSCRIPT key , italic_l end_POSTSUBSCRIPT in LLMs’ response with the corresponding subsequence 𝒙i,jsubscript𝒙𝑖𝑗\bm{{x}}_{i,j}bold_italic_x start_POSTSUBSCRIPT italic_i , italic_j end_POSTSUBSCRIPT from the original prompt. For more details, please refer to Algorithm [1](https://arxiv.org/html/2310.06839v2#alg1 "Algorithm 1 ‣ 4.4 How to improve the integrity of key information? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression").

Algorithm 1 Token-level Subsquence Recovery Algorithm

Input: The original prompt 𝒙𝒙\bm{x}bold_italic_x; the compressed prompt 𝒙~bold-~𝒙\bm{\widetilde{x}}overbold_~ start_ARG bold_italic_x end_ARG; the generation response of LLMs 𝒚𝒚\bm{y}bold_italic_y.

1:Set the final response list 𝒚rec=ϕsubscript𝒚recitalic-ϕ\bm{y}_{\text{rec}}=\phibold_italic_y start_POSTSUBSCRIPT rec end_POSTSUBSCRIPT = italic_ϕ, the left token index of subsquence l𝑙litalic_l to 0. 

2:while l<𝒚.l⁢e⁢n⁢()formulae-sequence𝑙𝒚𝑙𝑒𝑛l<\bm{y}.len()italic_l < bold_italic_y . italic_l italic_e italic_n ( ) do

3: if Substring yl∈𝒙~subscript𝑦𝑙bold-~𝒙{y_{l}}\in\bm{\widetilde{x}}italic_y start_POSTSUBSCRIPT italic_l end_POSTSUBSCRIPT ∈ overbold_~ start_ARG bold_italic_x end_ARG then

4: Find the longer substring 𝒚~key,l={yl,yl+1,\bm{\widetilde{y}}_{\text{key},l}=\\{y_{l},y_{l+1},overbold_~ start_ARG bold_italic_y end_ARG start_POSTSUBSCRIPT key , italic_l end_POSTSUBSCRIPT = { italic_y start_POSTSUBSCRIPT italic_l end_POSTSUBSCRIPT , italic_y start_POSTSUBSCRIPT italic_l + 1 end_POSTSUBSCRIPT , …,yr}∈𝒙~...,y_{r}\\}\in\bm{\widetilde{x}}… , italic_y start_POSTSUBSCRIPT italic_r end_POSTSUBSCRIPT } ∈ overbold_~ start_ARG bold_italic_x end_ARG. 

5: Find the maximum common shortest subsequence 𝒙i,j={xi,xi+1,…,xj}subscript𝒙𝑖𝑗subscript𝑥𝑖subscript𝑥𝑖1…subscript𝑥𝑗\bm{{x}}_{i,j}=\\{x_{i},x_{i+1},...,x_{j}\\}bold_italic_x start_POSTSUBSCRIPT italic_i , italic_j end_POSTSUBSCRIPT = { italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT , italic_x start_POSTSUBSCRIPT italic_i + 1 end_POSTSUBSCRIPT , … , italic_x start_POSTSUBSCRIPT italic_j end_POSTSUBSCRIPT } in the original prompt 𝒙𝒙\bm{x}bold_italic_x. 

6: Add the subsequence 𝒙i,j={xi,xi+1,…,xj}subscript𝒙𝑖𝑗subscript𝑥𝑖subscript𝑥𝑖1…subscript𝑥𝑗\bm{{x}}_{i,j}=\\{x_{i},x_{i+1},...,x_{j}\\}bold_italic_x start_POSTSUBSCRIPT italic_i , italic_j end_POSTSUBSCRIPT = { italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT , italic_x start_POSTSUBSCRIPT italic_i + 1 end_POSTSUBSCRIPT , … , italic_x start_POSTSUBSCRIPT italic_j end_POSTSUBSCRIPT } to the response 𝒚recsubscript𝒚rec\bm{y}_{\text{rec}}bold_italic_y start_POSTSUBSCRIPT rec end_POSTSUBSCRIPT. 

7: Set the left index l𝑙litalic_l to r+1𝑟1r+1italic_r + 1. 

8: else

9: Add the token ylsubscript𝑦𝑙y_{l}italic_y start_POSTSUBSCRIPT italic_l end_POSTSUBSCRIPT to the response 𝒚recsubscript𝒚rec\bm{y}_{\text{rec}}bold_italic_y start_POSTSUBSCRIPT rec end_POSTSUBSCRIPT. 

10: Set the left index l𝑙litalic_l to l+1𝑙1l+1italic_l + 1. 

11: end if

12:end while

Output: The final response list 𝒚recsubscript𝒚rec\bm{y}_{\text{rec}}bold_italic_y start_POSTSUBSCRIPT rec end_POSTSUBSCRIPT.

##  5 Experiments

Here, we investigate: (1) How effective is LongLLMLingua? (2) How efficient is LongLLMLingua?

#### Implementation details

In this paper, we use GPT-3.5-Turbo-0613666For experiments with original prompts exceeding 4k tokens, we utilize GPT-3.5-Turbo-16k-0613. and LongChat-13B-16k as the target LLMs, both accessible via OpenAI777https://platform.openai.com and HuggingFace888https://huggingface.co/lmsys/longchat-13b-16k. To ensure stable and reproducible results, we employ greedy decoding and set the temperature to 0 in all experiments. For the small language models used for compression, we apply LLaMA-2-7B-Chat999https://ai.meta.com/llama/, which has been aligned by supervised fine-tuning and RLHF. We implement our approach with PyTorch 1.13.1 and HuggingFace Transformers. We set up hyperparameters following LLMLingua except for the segment size used in iterative token-level compression set to 200 here. More details are provided in Appendix [B](https://arxiv.org/html/2310.06839v2#A2 "Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression").

Methods | GPT3.5-Turbo | LongChat-13b | Length | Latency  
---|---|---|---|---  
1st | 5th | 10th | 15th | 20th | Reorder | 1st | 5th | 10th | 15th | 20th | Reorder | Tokens | 1/τ1𝜏1/\tau1 / italic_τ | Latency | Speedup  
2x constraint |  |  |  |  |  |  |   
Retrieval-based Methods |  |  |   
BM25 | 53.7 | 49.3 | 47.9 | 49.9 | 46.9 | 50.3 | 50.9 | 44.9 | 44.1 | 42.9 | 43.2 | 46.0 | 1,545 | 1.9x | 2.1 | 1.9x  
Gzip | 64.6 | 63.8 | 60.5 | 58.3 | 57.3 | 64.4 | 61.9 | 55.7 | 52.7 | 50.8 | 50.9 | 59.3 | 1,567 | 1.9x | 2.1 | 1.9x  
SBERT | 72.5 | 67.9 | 63.3 | 65.0 | 66.2 | 68.7 | 65.8 | 57.5 | 54.9 | 53.4 | 55.7 | 61.4 | 1,549 | 1.9x | 2.2 | 1.9x  
OpenAI | 73.0 | 65.6 | 66.5 | 65.4 | 65.5 | 69.9 | 65.9 | 57.5 | 56.2 | 54.2 | 55.7 | 61.7 | 1,550 | 1.9x | 4.9 | 0.8x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 73.9 | 67.7 | 68.7 | 66.0 | 65.6 | 74.3 | 68.5 | 59.1 | 56.8 | 55.3 | 56.9 | 65.2 | 1,548 | 1.9x | 2.3 | 1.8x  
Compression-based Methods |  |  |  |  |  |  |  |  |  |   
Selective-Context | 45.4 | 39.0 | 33.8 | 33.5 | 41.5 | - | 53.2 | 26.3 | 25.4 | 24.2 | 33.3 | - | 1,478 | 2.0x | 7.4 | 0.6x  
LLMLingua | 39.7 | 39.5 | 40.4 | 37.1 | 42.3 | 41.5 | 38.7 | 37.3 | 35.7 | 34.1 | 37.5 | 37.1 | 1,410 | 2.1x | 2.8 | 1.5x  
LongLLMLingua | 77.2 | 72.9 | 70.8 | 70.5 | 70.6 | 76.2 | 68.7 | 59.4 | 57.3 | 55.9 | 58.4 | 66.1 | 1,429 | 2.1x | 2.9 | 1.4x  
4x constraint |  |  |  |  |  |  |   
Retrieval-based Methods |  |   
BM25 | 40.6 | 38.6 | 38.2 | 37.4 | 36.6 | 36.3 | 39.5 | 37.5 | 36.8 | 36.4 | 35.5 | 37.7 | 798 | 3.7x | 1.5 | 2.7x  
Gzip | 63.1 | 61.0 | 59.8 | 61.1 | 60.1 | 62.3 | 57.6 | 52.9 | 51.0 | 50.1 | 50.4 | 57.2 | 824 | 3.6x | 1.5 | 2.7x  
SBERT | 66.9 | 61.1 | 59.0 | 61.2 | 60.3 | 64.4 | 62.6 | 56.6 | 55.1 | 53.9 | 55.0 | 59.1 | 808 | 3.6x | 1.6 | 2.5x  
OpenAI | 63.8 | 64.6 | 65.4 | 64.1 | 63.7 | 63.7 | 61.2 | 56.0 | 55.1 | 54.4 | 55.0 | 58.8 | 804 | 3.7x | 4.3 | 1.0x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 71.1 | 70.7 | 69.3 | 68.7 | 68.5 | 71.5 | 67.8 | 59.4 | 57.7 | 57.7 | 58.6 | 64.0 | 807 | 3.7x | 1.7 | 2.4x  
Compression-based Methods |  |  |  |  |  |  |  |  |  |   
Selective-Context | 31.4 | 19.5 | 24.7 | 24.1 | 43.8 | - | 38.2 | 17.2 | 15.9 | 16.0 | 27.3 | - | 791 | 3.7x | 6.8 | 0.6x  
LLMLingua | 25.5 | 27.5 | 23.5 | 26.5 | 30.0 | 27.0 | 32.1 | 30.8 | 29.9 | 28.9 | 32.4 | 30.5 | 775 | 3.8x | 1.8 | 2.2x  
LongLLMLingua | 75.0 | 71.8 | 71.2 | 71.2 | 74.7 | 75.5 | 68.7 | 60.5 | 59.3 | 58.3 | 61.3 | 66.7 | 748 | 3.9x | 2.1 | 2.0x  
Original Prompt | 75.7 | 57.3 | 54.1 | 55.4 | 63.1 | - | 68.6 | 57.4 | 55.3 | 52.5 | 55.0 | - | 2,946 | - | 4.1 | -  
Zero-shot |  |  | 56.1 |  |  |  |  | 35.0 |  |  | 15 | 196x | 1.1 | 3.7x  
  
Table 1: Performance of different methods with different compression ratios (raw size / compressed size = 1/τ1𝜏1/\tau1 / italic_τ) on NaturalQuestions (20 documents) (Liu et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib25)). Reorder: we reorder the documents with relevance metrics of different baselines as our document reordering strategy described in Sec. [4.2](https://arxiv.org/html/2310.06839v2#S4.SS2 "4.2 How to reduce information loss in the middle? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). In the case of OpenAI, it corresponds to LongContextReorder9 in the LangChain framework (Chase, [2022](https://arxiv.org/html/2310.06839v2#bib.bib5)). For results reported under 1st to 20th, we do not use the reordering strategy for all methods. 

#### Dataset & evaluation metric

We use NaturalQuestions for the multi-document QA task, and use LongBench and ZeroSCROLLS for general long context scenarios. We also test on multi-hop QA tasks using MuSiQue dataset (Trivedi et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib38)), and long dependency QA tasks using LooGLE benchmark (Li et al., [2023b](https://arxiv.org/html/2310.06839v2#bib.bib23)). Please refer to Appendix [C](https://arxiv.org/html/2310.06839v2#A3 "Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") for more details on datasets.

Methods | SingleDoc | MultiDoc | Summ. | FewShot | Synth. | Code | AVG | Tokens | 1/τ1𝜏1/\tau1 / italic_τ | Latency | Speedup  
---|---|---|---|---|---|---|---|---|---|---|---  
3,000 tokens constraint |  |  |  |  |  |   
Retrieval-based Methods  
BM25 | 32.3 | 34.3 | 25.3 | 57.9 | 45.1 | 48.9 | 40.6 | 3,417 | 3x | 7.5 | 2.1x  
SBERT | 35.3 | 37.4 | 26.7 | 63.4 | 51.0 | 34.5 | 41.4 | 3,399 | 3x | 7.7 | 2.0x  
OpenAI | 34.5 | 38.6 | 26.8 | 63.4 | 49.6 | 37.6 | 41.7 | 3,421 | 3x | 13.3 | 1.2x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 37.6 | 42.9 | 26.9 | 68.2 | 49.9 | 53.4 | 46.5 | 3,424 | 3x | 8.2 | 1.9x  
Compression-based Methods |  |  |  |  |   
Selective-Context | 23.3 | 39.2 | 25.0 | 23.8 | 27.5 | 53.1 | 32.0 | 3,328 | 3x | 50.6 | 0.3x  
LLMLingua | 31.8 | 37.5 | 26.2 | 67.2 | 8.3 | 53.2 | 37.4 | 3,421 | 3x | 9.2 | 1.7x  
LongLLMLingua | 40.7 | 46.2 | 27.2 | 70.6 | 53.0 | 55.2 | 48.8 | 3,283 | 3x | 10.0 | 1.6x  
2,000 tokens constraint |  |  |  |  |  |   
Retrieval-based Methods  
BM25 | 30.1 | 29.4 | 21.2 | 19.5 | 12.4 | 29.1 | 23.6 | 1,985 | 5x | 4.6 | 3.4x  
SBERT | 33.8 | 35.9 | 25.9 | 23.5 | 18.0 | 17.8 | 25.8 | 1,947 | 5x | 4.8 | 3.4x  
OpenAI | 34.3 | 36.3 | 24.7 | 32.4 | 26.3 | 24.8 | 29.8 | 1,991 | 5x | 10.4 | 1.5x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 37.8 | 41.7 | 26.9 | 66.3 | 53.0 | 52.4 | 46.3 | 1,960 | 5x | 4.7 | 3.3x  
Compression-based Methods |  |  |  |  |   
Selective-Context | 16.2 | 34.8 | 24.4 | 15.7 | 8.4 | 49.2 | 24.8 | 1,925 | 5x | 47.1 | 0.3x  
LLMLingua | 22.4 | 32.1 | 24.5 | 61.2 | 10.4 | 56.8 | 34.6 | 1,950 | 5x | 5.9 | 2.6x  
LongLLMLingua | 39.9 | 43.2 | 27.4 | 69.8 | 53.0 | 56.7 | 48.3 | 1,822 | 6x | 6.1 | 2.6x  
Original Prompt | 39.7 | 38.7 | 26.5 | 67.0 | 37.8 | 54.2 | 44.0 | 10,295 | - | 15.6 | -  
Zero-shot | 15.6 | 31.3 | 15.6 | 40.7 | 1.6 | 36.2 | 23.5 | 214 | 48x | 1.6 | 9.8x  
  
Table 2: Performance of different methods under different compression ratios on LongBench (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2)) using GPT-3.5-Turbo in 2,000 tokens constraint.

| 1st | 5th | 10th | 15th | 20th  
---|---|---|---|---|---  
LongLLMLingua | 77.2 | 72.9 | 70.8 | 70.5 | 70.6  
Question-aware Coarse-grained |   
\- w/o Question-awareness | 42.1 | 40.3 | 39.7 | 40.1 | 40.3  
\- w/ SBERT | 73.2 | 68.5 | 65.7 | 66.1 | 66.7  
\- w/ p⁢(𝐱kdoc|xique,restrict)𝑝conditionalsuperscriptsubscript𝐱𝑘docsubscriptsuperscript𝑥querestrict𝑖p(\mathbf{x}_{k}^{\text{doc}}|x^{\text{que},\text{restrict}}_{i})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) | 56.0 | 52.6 | 53.4 | 51.6 | 51.1  
\- w/o restrict | 75.1 | 72.2 | 70.3 | 70.3 | 70.2  
\- w/o Question-aware Fine-grained | 75.8 | 71.0 | 68.9 | 68.4 | 69.3  
\- w/o Dynamic Compression Ratio | 74.4 | 70.7 | 68.7 | 67.9 | 68.1  
\- w/o Subsequence Recovery | 76.7 | 71.7 | 69.4 | 69.3 | 69.7  
\- w/ Document Reordering | 76.2 | 76.2 | 76.2 | 76.2 | 76.2  
\- w/ GPT2-small | 74.6 | 71.7 | 70.1 | 69.8 | 68.5  
LLMLingua | 39.7 | 39.5 | 40.4 | 37.1 | 42.3  
\- w/ Subsequence Recovery | 43.8 | 44.1 | 43.5 | 43.3 | 44.4  
  
Table 3: Ablation study on NaturalQuestions with 2x constraint using GPT-3.5-Turbo.

#### Baselines

We include two sets of baselines in following experiments:

(i) Retrieval-based Methods. We assess the question-document association in the prompt using five SoTA retrieval methods: BM25, Gzip (Jiang et al., [2023b](https://arxiv.org/html/2310.06839v2#bib.bib17)), SentenceBERT (Reimers and Gurevych, [2019](https://arxiv.org/html/2310.06839v2#bib.bib33)), OpenAI Embedding, and the LongLLMLingua ranker’s important metric rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT for coarse-grained compression. Notably, embedding model-based compression mirrors the method in Xu et al. ([2024](https://arxiv.org/html/2310.06839v2#bib.bib43)). We remove low-relevance sentences or paragraphs to meet compression limits, maintaining the original document sequence.

(ii) Compression-based Methods. We compare our approach with two state-of-art methods for prompt compression, i.e., Selective Context (Li et al., [2023c](https://arxiv.org/html/2310.06839v2#bib.bib24)) and LLMLingua (Jiang et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib16)). Both methods employ LLaMA-2-7B-Chat as the small language model for compression. In LLMLingua, a coarse-to-fine approach is used to handle constraints of compression ratio: the original prompt is first compressed to k𝑘kitalic_k times the constraint at a coarse level, where k𝑘kitalic_k is the granular control coefficient; token-level is then performed to reach the overall constraint. Our method follows the same coarse-to-fine logic to achieve the constraint.

99footnotetext: https://python.langchain.com/docs/modules/data_connecti on/document_transformers/post_retrieval/long_context_reorder

#### Main results

Table [1](https://arxiv.org/html/2310.06839v2#S5.T1 "Table 1 ‣ Implementation details ‣ 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") and [2](https://arxiv.org/html/2310.06839v2#S5.T2 "Table 2 ‣ Dataset & evaluation metric ‣ 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") present the performance of various methods under different compression constraints. There are multiple observations and conclusions: (1) Our LongLLMLingua achieves the best performance across different tasks and constraints of compression ratios. Compared to the original prompt, our compressed prompt can derive higher performance with much lower cost. For example, LongLLMLingua gains a performance boost of 21.4% on NaturalQuestions with the ground-truth document at the 10th position, while the number of tokens input to GPT3.5-Turbo is ∼similar-to\sim∼4x less. (2) Compression-based methods like Selective Context (Li et al., [2023c](https://arxiv.org/html/2310.06839v2#bib.bib24)) and LLMLingua (Jiang et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib16)) perform poorly on most tasks, especially those with abundant irrelevant information in the original prompt. This is due to their pure information entropy based compression mechanism, which includes too much noise in the compressed results and even leads to performance worse than the zero-shot setting, e.g., on NaturalQuestions. (3) Retrieval-based methods work well with low compression ratios. However, their performance declines as the compression progresses, e.g., 2⁢x→4⁢x→2𝑥4𝑥2x\rightarrow 4x2 italic_x → 4 italic_x; 3000 tokens →→\rightarrow→ 2000 tokens. This may be caused by the decreased recall. Figure [3a](https://arxiv.org/html/2310.06839v2#S4.F3.sf1 "In Figure 3 ‣ Question-Aware Coarse-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") is the illustration of cases on NaturalQuestions. (4) LongLLMLingua as well as our coarse-grained compression metric rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT only is much more robust than all other baselines under different tasks and compression constraints. With the increase of the compression ratio, e.g., 2⁢x→4⁢x→2𝑥4𝑥2x\rightarrow 4x2 italic_x → 4 italic_x, LongLLMLingua even achieves a little performance gain. We mainly owe this to the question-aware coarse-to-fine compression, which can better figure out the key information and reach a higher key information density with a higher compression ratio. (5) The proposed reordering method helps in not only our approach but also other baselines, well demonstrating its effectiveness. (6) Compared to the results with a 2,000 tokens constraint, overall performance of 3,000 tokens has improved. LongLLMLingua sees an increase of 1.2 points in average score and a 1.6x speedup in end-to-end latency. In this scenario, the recall rates of retrieval-based methods have increased, leading to a significant improvement in their accuracy. For example, BM25 achieves an average score of 48.9.

In addition, we also present experimental results on datasets such as MuSicQue, LooGLE, ZEROSCROLLS, etc., in Appendix [C](https://arxiv.org/html/2310.06839v2#A3 "Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression").

#### Ablation study

To evaluate the contributions of different components in LongLLMLingua, we introduce following variants of it for ablation study. (1) Variants about Question-aware Coarse-grained Compression, include: ours w/o Question-awareness, which calculates question-text relevance rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT using information entropy in LLMLingua, ours w/ SBERT, which employs SBERT to compute rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT, ours w/ p⁢(𝐱kdoc|xique,restrict)𝑝conditionalsuperscriptsubscript𝐱𝑘docsubscriptsuperscript𝑥querestrict𝑖p(\mathbf{x}_{k}^{\text{doc}}|x^{\text{que},\text{restrict}}_{i})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ), which replace p⁢(xique,restrict|𝐱kdoc)𝑝conditionalsubscriptsuperscript𝑥querestrict𝑖superscriptsubscript𝐱𝑘docp(x^{\text{que},\text{restrict}}_{i}|\mathbf{x}_{k}^{\text{doc}})italic_p ( italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT ) with p⁢(𝐱kdoc|xique,restrict)𝑝conditionalsuperscriptsubscript𝐱𝑘docsubscriptsuperscript𝑥querestrict𝑖p(\mathbf{x}_{k}^{\text{doc}}|x^{\text{que},\text{restrict}}_{i})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) in Eq. ([2](https://arxiv.org/html/2310.06839v2#S4.E2 "In Question-Aware Coarse-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")), and ours w/o restrict, which only calculates the conditional probability corresponding to xquesuperscript𝑥quex^{\text{que}}italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT. (2) Ours w/o Question-aware Fine-grained, which disregards Eq. ([3](https://arxiv.org/html/2310.06839v2#S4.E3 "In Question-Aware Fine-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")) and only applies Iterative Token-level Prompt Compression as LLMLingua. (3) Ours w/o Dynamic Compression Ratio, where all documents share the same compression ratio in fine-grained compression. (4) Ours w/o and (5) LLMLingua w/ Subsequence Recovery, which either removes or adds the post-processing subsequence recovery strategy. (6) Ours w/ GPT2-small, which uses the GPT2-small model as the ℳSsubscriptℳ𝑆\mathcal{M}_{S}caligraphic_M start_POSTSUBSCRIPT italic_S end_POSTSUBSCRIPT.

Table [3](https://arxiv.org/html/2310.06839v2#S5.T3 "Table 3 ‣ Dataset & evaluation metric ‣ 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), [4](https://arxiv.org/html/2310.06839v2#A2.T4 "Table 4 ‣ B.2 Other Implementation Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), and [7](https://arxiv.org/html/2310.06839v2#A3.T7 "Table 7 ‣ C.2 Ablation in LongBench ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") shows the results of the ablation study in difference tasks. In summary, removing any component proposed for LongLLMLingua will lead to a performance drop regardless of the position of the ground-truth answer. This well validates the necessity and effectiveness of the proposed question-aware mechanism during coarse-to-fine compression, the dynamic compression ratio, and the subsequence recovery strategy. It also shows that applying SBERT for coarse-grained compression will result in inferior performance, which implies the superiority of our question-aware importance metric in Eq. ([2](https://arxiv.org/html/2310.06839v2#S4.E2 "In Question-Aware Coarse-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")) over SBERT. In addition, replacing p⁢(xique,restrict|𝐱kdoc)𝑝conditionalsubscriptsuperscript𝑥querestrict𝑖superscriptsubscript𝐱𝑘docp(x^{\text{que},\text{restrict}}_{i}|\mathbf{x}_{k}^{\text{doc}})italic_p ( italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT ) with p⁢(𝐱kdoc|xique,restrict)𝑝conditionalsuperscriptsubscript𝐱𝑘docsubscriptsuperscript𝑥querestrict𝑖p(\mathbf{x}_{k}^{\text{doc}}|x^{\text{que},\text{restrict}}_{i})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) can greatly affect performance due to the large noise in calculating p⁢(𝐱kdoc)𝑝superscriptsubscript𝐱𝑘docp(\mathbf{x}_{k}^{\text{doc}})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT ) since the perplexity of document depends on many other information besides the question. Removing the restrictive statement can increase the hallucination of small language models, leading to a decrease in performance. Moreover, our subsequence recovery strategy can also bring performance gains for LLMLingua. However, without our question-aware mechanism, results from LLMLingua are still less satisfactory. For more detailed cases, please go to Appendix [E](https://arxiv.org/html/2310.06839v2#A5 "Appendix E Ablation Analysis ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression").

#### Latency evaluation

We conducte end-to-end latency testing on a V100-32G, using the prompts from Multi-document QA, LongBench, and ZeroSCROLLS in the API call, and results are shown in Table [1](https://arxiv.org/html/2310.06839v2#S5.T1 "Table 1 ‣ Implementation details ‣ 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), [2](https://arxiv.org/html/2310.06839v2#S5.T2 "Table 2 ‣ Dataset & evaluation metric ‣ 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") and [6](https://arxiv.org/html/2310.06839v2#A3.T6 "Table 6 ‣ C.2 Ablation in LongBench ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). The latency includes the time cost for prompt compression and the request time for LLMs, with multiple measurements taken and averaged over. Results demonstrate that LongLLMLingua does indeed speed up the overall inference under different compression ratios and scenarios. Moreover, with the compression ratio increasing, the acceleration effect becomes more pronounced up to 2.6x. However, the OpenAI embedding and Selective-Context results in longer latency time, due to repeated API calls and the sequential entropy calculation of semantic units, respectively.

##  6 Related Works

Long context for LLMs. Recent research has focused on expanding the window size of LLMs. Main approaches include: (1) Staged pre-training (Nijkamp et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib29)) which gradually increases the context window; (2) Modifying (Press et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib32)) or interpolating position embeddings (Chen et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib6); Peng et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib31)); (3) Using linear or sparse attention mechanisms (Ding et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib10); Sun et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib37)); (4) Utilizing external memory modules for context storage (Bertsch et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib3); Tworkowski et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib39)). While these methods address context window expansion, their impact on downstream task performance has yet to be discussed.

Information distribution in prompt. Recent empirical experiments have shown that LLM performance decreases with less effective information in a prompt (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2); Li et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib22); Shi et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib36)). Moreover, the position of relevant information in a prompt has a significant impact on performance (Wu et al., [2023b](https://arxiv.org/html/2310.06839v2#bib.bib41)). Liu et al. ([2024](https://arxiv.org/html/2310.06839v2#bib.bib25)) suggests that LLMs have more difficulty comprehending information located in the middle of a prompt compared to those at the edges.

Retrieval methods can be categorized as dense or sparse retrieval methods. Sparse retrieval methods, like BM25, determine the relevance between queries and documents based on n-gram information. Conversely, dense retrieval methods assess the relevance between queries and documents in latent space using embedding model (Reimers and Gurevych, [2019](https://arxiv.org/html/2310.06839v2#bib.bib33); Xiao et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib42); Günther et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib14)) and reranker model (Xiao et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib42)). Recently, Jiang et al. ([2023b](https://arxiv.org/html/2310.06839v2#bib.bib17)) proposed an unsupervised dense retrieval method that leverages traditional compression algorithms, such as gzip, and k-nearest neighbors.

Prompt compression methods can be grouped into three main categories: (1) Token pruning (Goyal et al., [2020](https://arxiv.org/html/2310.06839v2#bib.bib13); Kim and Cho, [2021](https://arxiv.org/html/2310.06839v2#bib.bib19); Modarressi et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib27)) and token merging (Bolya et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib4)), which need model fine-tuning or intermediate results during inference and have been used with BERT-scale models. (2) Soft prompt tuning methods like GIST (Mu et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib28)), AutoCompressor (Chevalier et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib7)), and ICAE (Ge et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib12)), which require LLMs’ parameter fine-tuning, making them suitable for specific domains but not directly applicable to black-box LLMs. (3) Information-entropy-based approaches such as Selective Context (Li et al., [2023c](https://arxiv.org/html/2310.06839v2#bib.bib24)) and LLMLingua (Jiang et al., [2023a](https://arxiv.org/html/2310.06839v2#bib.bib16)), which use a small language model to calculate the self-information or perplexity of each token in the original prompt and then remove tokens with lower perplexities.

##  7 Conclusion

We propose LongLLMLingua to address the three challenges, i.e., higher computational cost, performance reduction, and position bias for LLMs in long context scenarios. We develop LongLLMLingua from the perspective of efficient prompt compression, thus reducing computational cost. We further design four components, i.e., a question-aware coarse-to-fine compression method, a document reordering mechanism, dynamic compression ratios, and a subsequence recovery strategy to improve LLMs’ perception of the key information, with which LongLLMLingua demonstrate superior performance. Experiments on the multi-document QA, multi-hop QA, and long context benchmarks demonstrate that LongLLMLingua compressed prompt can derive higher performance than original prompts while both API costs for inference and the end-to-end system latency are largely reduced.

## Limitation

Although previous experiments demonstrate LongLLMLingua’s effectiveness and efficiency across a broad range of tasks, the method still has the following limitations: 1) LongLLMLingua is a question-aware approach, meaning it requires re-compression for different questions, even with the same context, preventing caching of the context. Moreover, in terms of computational cost, LongLLMLingua increases the computation by twice as much as LLMLingua. This can lead to greater overhead in real-world applications. However, this issue can be mitigated by extending the question-aware approach to a task-aware approach, allowing for reuse and caching. 2) While the effectiveness of LongLLMLingua has been tested on a wide range of tasks, especially on the multi-hop QA dataset MuSicQue (Trivedi et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib38)), its effectiveness might be impacted when the relationship between context and prompt is more complex and subtle due to the coarse-level question-aware approach.

## References

  * Asai et al. (2024) Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, and Hannaneh Hajishirzi. 2024.  [Self-RAG: Learning to retrieve, generate, and critique through self-reflection](https://openreview.net/forum?id=hSyW5go0v8).  In _The Twelfth International Conference on Learning Representations_. 
  * Bai et al. (2023) Yushi Bai, Xin Lv, Jiajie Zhang, Hongchang Lyu, Jiankai Tang, Zhidian Huang, Zhengxiao Du, Xiao Liu, Aohan Zeng, Lei Hou, et al. 2023.  [Longbench: A bilingual, multitask benchmark for long context understanding](https://arxiv.org/abs/2308.14508).  _ArXiv preprint_ , abs/2308.14508. 
  * Bertsch et al. (2023) Amanda Bertsch, Uri Alon, Graham Neubig, and Matthew R. Gormley. 2023.  [Unlimiformer: Long-range transformers with unlimited length input](https://openreview.net/forum?id=lJWUJWLCJo).  In _Thirty-seventh Conference on Neural Information Processing Systems_. 
  * Bolya et al. (2023) Daniel Bolya, Cheng-Yang Fu, Xiaoliang Dai, Peizhao Zhang, Christoph Feichtenhofer, and Judy Hoffman. 2023.  [Token merging: Your vit but faster](https://openreview.net/forum?id=JroZRaRw7Eu).  In _The Eleventh International Conference on Learning Representations_. 
  * Chase (2022) Harrison Chase. 2022.  [LangChain](https://github.com/hwchase17/langchain). 
  * Chen et al. (2023) Shouyuan Chen, Sherman Wong, Liangjian Chen, and Yuandong Tian. 2023.  [Extending context window of large language models via positional interpolation](https://arxiv.org/abs/2306.15595).  _ArXiv preprint_ , abs/2306.15595. 
  * Chevalier et al. (2023) Alexis Chevalier, Alexander Wettig, Anirudh Ajith, and Danqi Chen. 2023.  [Adapting language models to compress contexts](https://doi.org/10.18653/v1/2023.emnlp-main.232).  In _Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing_ , pages 3829–3846, Singapore. Association for Computational Linguistics. 
  * Church and Hanks (1989) Kenneth Ward Church and Patrick Hanks. 1989.  [Word association norms, mutual information, and lexicography](https://doi.org/10.3115/981623.981633).  In _27th Annual Meeting of the Association for Computational Linguistics_ , pages 76–83, Vancouver, British Columbia, Canada. Association for Computational Linguistics. 
  * Delétang et al. (2023) Grégoire Delétang, Anian Ruoss, Paul-Ambroise Duquenne, Elliot Catt, Tim Genewein, Christopher Mattern, Jordi Grau-Moya, Li Kevin Wenliang, Matthew Aitchison, Laurent Orseau, et al. 2023.  [Language modeling is compression](https://arxiv.org/abs/2309.10668).  _ArXiv preprint_ , abs/2309.10668. 
  * Ding et al. (2023) Jiayu Ding, Shuming Ma, Li Dong, Xingxing Zhang, Shaohan Huang, Wenhui Wang, and Furu Wei. 2023.  [Longnet: Scaling transformers to 1,000,000,000 tokens](https://arxiv.org/abs/2307.02486).  _ArXiv preprint_ , abs/2307.02486. 
  * Dong et al. (2023) Qingxiu Dong, Lei Li, Damai Dai, Ce Zheng, Zhiyong Wu, Baobao Chang, Xu Sun, Jingjing Xu, and Zhifang Sui. 2023.  [A survey for in-context learning](https://arxiv.org/abs/2301.00234).  _ArXiv preprint_ , abs/2301.00234. 
  * Ge et al. (2024) Tao Ge, Hu Jing, Lei Wang, Xun Wang, Si-Qing Chen, and Furu Wei. 2024.  [In-context autoencoder for context compression in a large language model](https://openreview.net/forum?id=uREj4ZuGJE).  In _The Twelfth International Conference on Learning Representations_. 
  * Goyal et al. (2020) Saurabh Goyal, Anamitra Roy Choudhury, Saurabh Raje, Venkatesan T. Chakaravarthy, Yogish Sabharwal, and Ashish Verma. 2020.  [Power-bert: Accelerating BERT inference via progressive word-vector elimination](http://proceedings.mlr.press/v119/goyal20a.html).  In _Proceedings of the 37th International Conference on Machine Learning, ICML 2020, 13-18 July 2020, Virtual Event_ , volume 119 of _Proceedings of Machine Learning Research_ , pages 3690–3699. PMLR. 
  * Günther et al. (2023) Michael Günther, Jackmin Ong, Isabelle Mohr, Alaeddine Abdessalem, Tanguy Abel, Mohammad Kalim Akram, Susana Guzman, Georgios Mastrapas, Saba Sturua, Bo Wang, Maximilian Werk, Nan Wang, and Han Xiao. 2023.  [Jina embeddings 2: 8192-token general-purpose text embeddings for long documents](https://arxiv.org/abs/2310.19923).  _ArXiv preprint_ , abs/2310.19923. 
  * Izacard et al. (2022) Gautier Izacard, Mathilde Caron, Lucas Hosseini, Sebastian Riedel, Piotr Bojanowski, Armand Joulin, and Edouard Grave. 2022.  [Unsupervised dense information retrieval with contrastive learning](https://openreview.net/forum?id=jKN1pXi7b0).  _Transactions on Machine Learning Research_. 
  * Jiang et al. (2023a) Huiqiang Jiang, Qianhui Wu, Chin-Yew Lin, Yuqing Yang, and Lili Qiu. 2023a.  [LLMLingua: Compressing prompts for accelerated inference of large language models](https://doi.org/10.18653/v1/2023.emnlp-main.825).  In _Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing_ , pages 13358–13376. Association for Computational Linguistics. 
  * Jiang et al. (2023b) Zhiying Jiang, Matthew Yang, Mikhail Tsirlin, Raphael Tang, Yiqin Dai, and Jimmy Lin. 2023b.  [“low-resource” text classification: A parameter-free classification method with compressors](https://doi.org/10.18653/v1/2023.findings-acl.426).  In _Findings of the Association for Computational Linguistics: ACL 2023_ , pages 6810–6828, Toronto, Canada. Association for Computational Linguistics. 
  * Kamradt (2023) Greg Kamradt. 2023.  [Needle In A Haystack - Pressure Testing LLMs](https://github.com/gkamradt/LLMTest_NeedleInAHaystack). 
  * Kim and Cho (2021) Gyuwan Kim and Kyunghyun Cho. 2021.  [Length-adaptive transformer: Train once with length drop, use anytime with search](https://doi.org/10.18653/v1/2021.acl-long.508).  In _Proceedings of the 59th Annual Meeting of the Association for Computational Linguistics and the 11th International Joint Conference on Natural Language Processing (Volume 1: Long Papers)_ , pages 6501–6511, Online. Association for Computational Linguistics. 
  * Kwiatkowski et al. (2019) Tom Kwiatkowski, Jennimaria Palomaki, Olivia Redfield, Michael Collins, Ankur Parikh, Chris Alberti, Danielle Epstein, Illia Polosukhin, Jacob Devlin, Kenton Lee, Kristina Toutanova, Llion Jones, Matthew Kelcey, Ming-Wei Chang, Andrew M. Dai, Jakob Uszkoreit, Quoc Le, and Slav Petrov. 2019.  [Natural questions: A benchmark for question answering research](https://doi.org/10.1162/tacl_a_00276).  _Transactions of the Association for Computational Linguistics_ , 7:452–466. 
  * Lewis et al. (2020) Patrick S. H. Lewis, Ethan Perez, Aleksandra Piktus, Fabio Petroni, Vladimir Karpukhin, Naman Goyal, Heinrich Küttler, Mike Lewis, Wen-tau Yih, Tim Rocktäschel, Sebastian Riedel, and Douwe Kiela. 2020.  [Retrieval-augmented generation for knowledge-intensive NLP tasks](https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html).  In _Advances in Neural Information Processing Systems 33: Annual Conference on Neural Information Processing Systems 2020, NeurIPS 2020, December 6-12, 2020, virtual_. 
  * Li et al. (2023a) Dacheng Li, Rulin Shao, Anze Xie, Ying Sheng, Lianmin Zheng, Joseph E. Gonzalez, Ion Stoica, Xuezhe Ma, and Hao Zhang. 2023a.  [How long can open-source llms truly promise on context length?](https://lmsys.org/blog/2023-06-29-longchat)
  * Li et al. (2023b) Jiaqi Li, Mengmeng Wang, Zilong Zheng, and Muhan Zhang. 2023b.  [Loogle: Can long-context language models understand long contexts?](https://arxiv.org/abs/2311.04939) _ArXiv preprint_ , abs/2311.04939. 
  * Li et al. (2023c) Yucheng Li, Bo Dong, Frank Guerin, and Chenghua Lin. 2023c.  [Compressing context to enhance inference efficiency of large language models](https://doi.org/10.18653/v1/2023.emnlp-main.391).  In _Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing_ , pages 6342–6353, Singapore. Association for Computational Linguistics. 
  * Liu et al. (2024) Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio Petroni, and Percy Liang. 2024.  [Lost in the Middle: How Language Models Use Long Contexts](https://doi.org/10.1162/tacl_a_00638).  _Transactions of the Association for Computational Linguistics_ , 12:157–173. 
  * Min et al. (2022) Sewon Min, Mike Lewis, Luke Zettlemoyer, and Hannaneh Hajishirzi. 2022.  [MetaICL: Learning to learn in context](https://doi.org/10.18653/v1/2022.naacl-main.201).  In _Proceedings of the 2022 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies_ , pages 2791–2809, Seattle, United States. Association for Computational Linguistics. 
  * Modarressi et al. (2022) Ali Modarressi, Hosein Mohebbi, and Mohammad Taher Pilehvar. 2022.  [AdapLeR: Speeding up inference by adaptive length reduction](https://doi.org/10.18653/v1/2022.acl-long.1).  In _Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)_ , pages 1–15, Dublin, Ireland. Association for Computational Linguistics. 
  * Mu et al. (2023) Jesse Mu, Xiang Lisa Li, and Noah Goodman. 2023.  [Learning to compress prompts with gist tokens](https://openreview.net/forum?id=2DtxPCL3T5).  In _Thirty-seventh Conference on Neural Information Processing Systems_. 
  * Nijkamp et al. (2023) Erik Nijkamp, Tian Xie, Hiroaki Hayashi, Bo Pang, Congying Xia, Chen Xing, Jesse Vig, Semih Yavuz, Philippe Laban, Ben Krause, Senthil Purushwalkam, Tong Niu, Wojciech Kryściński, Lidiya Murakhovs’ka, Prafulla Kumar Choubey, Alex Fabbri, Ye Liu, Rui Meng, Lifu Tu, Meghana Bhat, Chien-Sheng Wu, Silvio Savarese, Yingbo Zhou, Shafiq Joty, and Caiming Xiong. 2023.  [Xgen-7b technical report](https://arxiv.org/abs/2309.03450).  _ArXiv preprint_ , abs/2309.03450. 
  * Park et al. (2023) Joon Sung Park, Joseph O’Brien, Carrie Jun Cai, Meredith Ringel Morris, Percy Liang, and Michael S. Bernstein. 2023.  [Generative agents: Interactive simulacra of human behavior](https://doi.org/10.1145/3586183.3606763).  In _Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology_ , UIST ’23, New York, NY, USA. Association for Computing Machinery. 
  * Peng et al. (2024) Bowen Peng, Jeffrey Quesnelle, Honglu Fan, and Enrico Shippole. 2024.  [YaRN: Efficient context window extension of large language models](https://openreview.net/forum?id=wHBfxhZu1u).  In _The Twelfth International Conference on Learning Representations_. 
  * Press et al. (2022) Ofir Press, Noah A. Smith, and Mike Lewis. 2022.  [Train short, test long: Attention with linear biases enables input length extrapolation](https://openreview.net/forum?id=R8sQPpGCv0).  In _The Tenth International Conference on Learning Representations, ICLR 2022, Virtual Event, April 25-29, 2022_. OpenReview.net. 
  * Reimers and Gurevych (2019) Nils Reimers and Iryna Gurevych. 2019.  [Sentence-BERT: Sentence embeddings using Siamese BERT-networks](https://doi.org/10.18653/v1/D19-1410).  In _Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing and the 9th International Joint Conference on Natural Language Processing (EMNLP-IJCNLP)_ , pages 3982–3992, Hong Kong, China. Association for Computational Linguistics. 
  * Shaham et al. (2023) Uri Shaham, Maor Ivgi, Avia Efrat, Jonathan Berant, and Omer Levy. 2023.  [ZeroSCROLLS: A zero-shot benchmark for long text understanding](https://doi.org/10.18653/v1/2023.findings-emnlp.536).  In _Findings of the Association for Computational Linguistics: EMNLP 2023_ , pages 7977–7989, Singapore. Association for Computational Linguistics. 
  * Shen et al. (2024) Yongliang Shen, Kaitao Song, Xu Tan, Dongsheng Li, Weiming Lu, and Yueting Zhuang. 2024.  Hugginggpt: Solving ai tasks with chatgpt and its friends in hugging face.  _Advances in Neural Information Processing Systems_ , 36. 
  * Shi et al. (2023) Freda Shi, Xinyun Chen, Kanishka Misra, Nathan Scales, David Dohan, Ed H Chi, Nathanael Schärli, and Denny Zhou. 2023.  Large language models can be easily distracted by irrelevant context.  In _International Conference on Machine Learning_ , pages 31210–31227. PMLR. 
  * Sun et al. (2023) Yutao Sun, Li Dong, Shaohan Huang, Shuming Ma, Yuqing Xia, Jilong Xue, Jianyong Wang, and Furu Wei. 2023.  [Retentive network: A successor to transformer for large language models](https://arxiv.org/abs/2307.08621).  _ArXiv preprint_ , abs/2307.08621. 
  * Trivedi et al. (2022) Harsh Trivedi, Niranjan Balasubramanian, Tushar Khot, and Ashish Sabharwal. 2022.  [MuSiQue: Multihop questions via single-hop question composition](https://doi.org/10.1162/tacl_a_00475).  _Transactions of the Association for Computational Linguistics_ , 10:539–554. 
  * Tworkowski et al. (2023) Szymon Tworkowski, Konrad Staniszewski, Mikołaj Pacek, Yuhuai Wu, Henryk Michalewski, and Piotr Miłoś. 2023.  [Focused transformer: Contrastive training for context scaling](https://openreview.net/forum?id=s1FjXzJ0jy).  In _Thirty-seventh Conference on Neural Information Processing Systems_. 
  * Wu et al. (2023a) Qingyun Wu, Gagan Bansal, Jieyu Zhang, Yiran Wu, Beibin Li, Erkang Zhu, Li Jiang, Xiaoyun Zhang, Shaokun Zhang, Jiale Liu, Ahmed Hassan Awadallah, Ryen W White, Doug Burger, and Chi Wang. 2023a.  [Autogen: Enabling next-gen llm applications via multi-agent conversation framework](https://arxiv.org/abs/2308.08155).  _ArXiv preprint_ , abs/2308.08155. 
  * Wu et al. (2023b) Zhiyong Wu, Yaoxiang Wang, Jiacheng Ye, and Lingpeng Kong. 2023b.  [Self-adaptive in-context learning: An information compression perspective for in-context example selection and ordering](https://doi.org/10.18653/v1/2023.acl-long.79).  In _Proceedings of the 61st Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)_ , pages 1423–1436, Toronto, Canada. Association for Computational Linguistics. 
  * Xiao et al. (2023) Shitao Xiao, Zheng Liu, Peitian Zhang, and Niklas Muennighoff. 2023.  [C-pack: Packaged resources to advance general chinese embedding](https://arxiv.org/abs/2309.07597).  _ArXiv preprint_ , abs/2309.07597. 
  * Xu et al. (2024) Peng Xu, Wei Ping, Xianchao Wu, Lawrence McAfee, Chen Zhu, Zihan Liu, Sandeep Subramanian, Evelina Bakhturina, Mohammad Shoeybi, and Bryan Catanzaro. 2024.  [Retrieval meets long context large language models](https://openreview.net/forum?id=xw5nxFWMlo).  In _The Twelfth International Conference on Learning Representations_. 



##  Appendix A Derivation Of Question-Aware Fine-Grained Compression

Based on the definition of Eq. ([3](https://arxiv.org/html/2310.06839v2#S4.E3 "In Question-Aware Fine-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")), we can derive that,

| sisubscript𝑠𝑖\displaystyle s_{i}italic_s start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | =perplexity⁢(xi|x<i)−perplexity⁢(xi|xque,x<i)absentperplexityconditionalsubscript𝑥𝑖subscript𝑥absent𝑖perplexityconditionalsubscript𝑥𝑖superscript𝑥quesubscript𝑥absent𝑖\displaystyle=\text{perplexity}(x_{i}|x_{<i})-\text{perplexity}(x_{i}|x^{\text% {que}},x_{<i})= perplexity ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) - perplexity ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) |  | (6)  
---|---|---|---|---  
|  | =q⁢(xi)⁢log⁡p⁢(xi|xque,x<i)−q⁢(xi)⁢log⁡p⁢(xi|x<i)absent𝑞subscript𝑥𝑖𝑝conditionalsubscript𝑥𝑖superscript𝑥quesubscript𝑥absent𝑖𝑞subscript𝑥𝑖𝑝conditionalsubscript𝑥𝑖subscript𝑥absent𝑖\displaystyle=q(x_{i})\log p(x_{i}|x^{\text{que}},x_{<i})-q(x_{i})\log p(x_{i}% |x_{<i})= italic_q ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) roman_log italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) - italic_q ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) roman_log italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) |   
|  | =q⁢(xi)⁢log⁡p⁢(xi|xque,x<i)p⁢(xi|x<i)absent𝑞subscript𝑥𝑖𝑝conditionalsubscript𝑥𝑖superscript𝑥quesubscript𝑥absent𝑖𝑝conditionalsubscript𝑥𝑖subscript𝑥absent𝑖\displaystyle=q(x_{i})\log\frac{p(x_{i}|x^{\text{que}},x_{<i})}{p(x_{i}|x_{<i})}= italic_q ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) roman_log divide start_ARG italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) end_ARG start_ARG italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) end_ARG |   
  
In the actual calculation of perplexity, a log operation is performed to avoid overflow, and q⁢(xi)𝑞subscript𝑥𝑖q(x_{i})italic_q ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) represents the probability distribution of the ground-truth.

At the same time, we can derive the following expanded expression based on Bayes’ theorem.

| p⁢(xque|xi,x<i)𝑝conditionalsuperscript𝑥quesubscript𝑥𝑖subscript𝑥absent𝑖\displaystyle p(x^{\text{que}}|x_{i},x_{<i})italic_p ( italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT | italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) | =p⁢(xi|xque,x<i)⁢p⁢(xque)p⁢(xi|x<i)absent𝑝conditionalsubscript𝑥𝑖superscript𝑥quesubscript𝑥absent𝑖𝑝superscript𝑥que𝑝conditionalsubscript𝑥𝑖subscript𝑥absent𝑖\displaystyle=\frac{p(x_{i}|x^{\text{que}},x_{<i})p(x^{\text{que}})}{p(x_{i}|x% _{<i})}= divide start_ARG italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) italic_p ( italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT ) end_ARG start_ARG italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) end_ARG |  | (7)  
---|---|---|---|---  
|  | =p⁢(xque)⁢p⁢(xi|xque,x<i)p⁢(xi|x<i)absent𝑝superscript𝑥que𝑝conditionalsubscript𝑥𝑖superscript𝑥quesubscript𝑥absent𝑖𝑝conditionalsubscript𝑥𝑖subscript𝑥absent𝑖\displaystyle=p(x^{\text{que}})\frac{p(x_{i}|x^{\text{que}},x_{<i})}{p(x_{i}|x% _{<i})}= italic_p ( italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT ) divide start_ARG italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) end_ARG start_ARG italic_p ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT | italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) end_ARG |   
  
The probability distribution p⁢(xque)𝑝superscript𝑥quep(x^{\text{que}})italic_p ( italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT ) of the question and the ground-truth distribution q⁢(xi)𝑞subscript𝑥𝑖q(x_{i})italic_q ( italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) of xisubscript𝑥𝑖x_{i}italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT are constants, hence sisubscript𝑠𝑖s_{i}italic_s start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT can be considered as the representation of Eq. ([7](https://arxiv.org/html/2310.06839v2#A1.E7 "In Appendix A Derivation Of Question-Aware Fine-Grained Compression ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")).

| si∝p⁢(xque|xi,x<i)proportional-tosubscript𝑠𝑖𝑝conditionalsuperscript𝑥quesubscript𝑥𝑖subscript𝑥absent𝑖s_{i}\propto p(x^{\text{que}}|x_{i},x_{<i})italic_s start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ∝ italic_p ( italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT | italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ) |  | (8)  
---|---|---|---  
  
So we can utilize Eq. ([3](https://arxiv.org/html/2310.06839v2#S4.E3 "In Question-Aware Fine-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")) to represent the probability distribution p⁢(xque|xi,x<i)𝑝conditionalsuperscript𝑥quesubscript𝑥𝑖subscript𝑥absent𝑖p(x^{\text{que}}|x_{i},x_{<i})italic_p ( italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT | italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT , italic_x start_POSTSUBSCRIPT < italic_i end_POSTSUBSCRIPT ), which represents the condition likelihood of generating xquesuperscript𝑥quex^{\text{que}}italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT given the token xisubscript𝑥𝑖x_{i}italic_x start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT. Therefore, we can represent the token-level sensitive distribution for the question xquesuperscript𝑥quex^{\text{que}}italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT using just a single inference. For tokens that are unrelated to xquesuperscript𝑥quex^{\text{que}}italic_x start_POSTSUPERSCRIPT que end_POSTSUPERSCRIPT, such as the tokens on the right side of Figure [3b](https://arxiv.org/html/2310.06839v2#S4.F3.sf2 "In Figure 3 ‣ Question-Aware Coarse-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), their original amount of information may be high, but the contrastive perplexity remains at a relatively low level. Finally, we observe that the form of contrastive perplexity is equivalent to conditional pointwise mutual information (Church and Hanks, [1989](https://arxiv.org/html/2310.06839v2#bib.bib8)).

##  Appendix B Experiment Details

###  B.1 Dataset Details

We use NaturalQuestions (Liu et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib25)) for the multi-document QA task, MuSicQue (Trivedi et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib38)) for the multi-hop QA task, and use LongBench (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2)), ZeroSCROLLS (Shaham et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib34)), LooGLE (Li et al., [2023b](https://arxiv.org/html/2310.06839v2#bib.bib23)) for general long context scenarios. The specific details of the dataset are as follows:

#### NaturalQuestions multi-document QA

A multi-document question-answering dataset, comprising 2,655 problems, was built by Liu et al. ([2024](https://arxiv.org/html/2310.06839v2#bib.bib25)) based on the NaturalQuestions dataset (Kwiatkowski et al., [2019](https://arxiv.org/html/2310.06839v2#bib.bib20)). This dataset provides a realistic retrieval-augmented generation setup that closely resembles commercial search and question-answering applications (e.g., Bing Chat). Each example in the dataset contains a question and k related documents, utilizing the Contriever retrieval system (Izacard et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib15)), one of which includes a document with the correct answer. To perform this task, the model must access the document containing the answer within its input context and use it to answer the question. The dataset’s data is sourced from the NaturalQuestions dataset, which contains historical queries issued to the Google search engine and human-annotated answers extracted from Wikipedia. The average prompt token length in this benchmark is 2,946. For our experiments, we used the version provided by Liu et al. ([2024](https://arxiv.org/html/2310.06839v2#bib.bib25)) that includes 20 documents101010https://github.com/nelson-liu/lost-in-the-middle. The dataset comprises five different ground truth document position settings in the prompt: 1st, 5th, 10th, 15th, and 20th.

#### LongBench

A multi-task long context benchmark consists of 3,750 problems in English and includes six categories with a total of 16 tasks. These tasks encompass key long-text application scenarios, such as single-document QA, multi-document QA, summarization, few-shot learning, synthetic tasks, and code completion. The average prompt token length in this benchmark is 10,289. For our experiments, we used the English dataset and evaluation scripts provided by Bai et al. ([2023](https://arxiv.org/html/2310.06839v2#bib.bib2)) for this benchmark111111https://github.com/THUDM/LongBench.

#### ZeroSCROLLS

The multi-task long context benchmark consists of 4,378 problems, including four categories with a total of 10 tasks. These tasks cover summarization, question answering, aggregated sentiment classification, and information reordering. The average prompt token length in this benchmark is 9,788. For our experiments, we used the validation set and evaluation scripts provided by Shaham et al. ([2023](https://arxiv.org/html/2310.06839v2#bib.bib34)) for this dataset121212https://www.zero.scrolls-benchmark.com/.

#### MuSiQue

The multi-hop question-answer dataset is composed of 39,876, 4,834, and 4,918 problems in the training, validation, and testing datasets, respectively. This dataset requires the language model to conduct multiple inferences based on the content of several documents and provide corresponding answers, thereby necessitating a certain capability for global information processing. The average token length for prompts in this dataset is 2,477. For our experiments, we utilized the validation set and evaluation scripts provided by Trivedi et al. ([2022](https://arxiv.org/html/2310.06839v2#bib.bib38)) for this dataset131313https://github.com/stonybrooknlp/musique.

#### LooGLE

The multi-task long context benchmark comprises 6,448 problems, divided into three categories: summarization, short dependency question answering, and long dependency question answering. The average prompt token length in this benchmark stands at 24,005. For our experiments, we focused on the long dependency question answering subset, which includes four types of tasks: information retrieval, timeline reordering, computation, and comprehension. This subset contains 1,101 problems. We utilized the evaluation scripts provided by Li et al. ([2023b](https://arxiv.org/html/2310.06839v2#bib.bib23)) for this dataset141414https://github.com/bigai-nlco/LooGLE.

###  B.2 Other Implementation Details

All experiments were conducted using a Tesla V100 (32GB). We use tiktoken151515https://github.com/openai/tiktoken and GPT-3.5-Turbo model to count all the tokens. We set the granular control coefficient k𝑘kitalic_k to 2222. We use the pre-defined compression rates τins=0.85subscript𝜏ins0.85\tau_{\text{ins}}=0.85italic_τ start_POSTSUBSCRIPT ins end_POSTSUBSCRIPT = 0.85 and τque=0.9subscript𝜏que0.9\tau_{\text{que}}=0.9italic_τ start_POSTSUBSCRIPT que end_POSTSUBSCRIPT = 0.9 for instructions and questions. The segment size used in the iterative token-level compression is set to 200200200200. The δ⁢τ𝛿𝜏\delta\tauitalic_δ italic_τ used in dynamic compression ratio is set to 0.3. For a fair comparison, we only used reordering in the NaturalQuestions Multi-document QA and noted this in Table [1](https://arxiv.org/html/2310.06839v2#S5.T1 "Table 1 ‣ Implementation details ‣ 5 Experiments ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"). We use “We can get the answer to this question in the given documents." as the guideline sentence in Eq. ([3](https://arxiv.org/html/2310.06839v2#S4.E3 "In Question-Aware Fine-Grained Compression ‣ 4.1 How to improve key information density in the prompt? ‣ 4 LongLLMLingua ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")).

(a) 1st

(b) 10th

(c) 15th

Figure 5: The distribution of document-level average perplexity when the ground-truth document is in different positions.

Methods | SingleDoc | MultiDoc | Summ. | FewShot | Synth. | Code | AVG | Tokens | 1/τ1𝜏1/\tau1 / italic_τ  
---|---|---|---|---|---|---|---|---|---  
LongLLMLingua | 39.9 | 43.2 | 27.4 | 69.8 | 53.0 | 56.7 | 48.3 | 1,822 | 6x  
Question-aware Coarse-grained |  |  |  |  |   
\- w/o Question-awareness | 27.1 | 38.7 | 25.4 | 62.0 | 18.0 | 53.3 | 37.4 | 1,945 | 5x  
\- w/ SBERT | 34.0 | 38.7 | 24.1 | 57.9 | 32.5 | 31.1 | 36.4 | 1,790 | 6x  
\- w/ p⁢(𝐱kdoc|xique,restrict)𝑝conditionalsuperscriptsubscript𝐱𝑘docsubscriptsuperscript𝑥querestrict𝑖p(\mathbf{x}_{k}^{\text{doc}}|x^{\text{que},\text{restrict}}_{i})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) | 22.5 | 28.9 | 23.2 | 53.0 | 22.5 | 33.3 | 30.6 | 1,794 | 6x  
\- w/o restrict | 37.8 | 39.5 | 26.4 | 64.8 | 52.5 | 55.8 | 46.1 | 1,834 | 6x  
\- w/o Question-aware Fine-grained | 35.7 | 41.1 | 26.4 | 62.9 | 44.5 | 54.8 | 44.2 | 1,807 | 6x  
\- w/o Dynamic Compression Ratio | 36.1 | 40.6 | 26.9 | 67.2 | 48.0 | 55.8 | 45.7 | 1,851 | 6x  
\- w/o Subsequence Recovery | 38.6 | 41.8 | 27.3 | 69.0 | 53.8 | 56.6 | 47.8 | 1,809 | 6x  
\- w/o Document Reordering | 39.0 | 42.2 | 27.4 | 69.3 | 53.8 | 56.6 | 48.0 | 1,809 | 6x  
\- w/ GPT2-small | 35.9 | 39.4 | 25.0 | 60.6 | 42.0 | 55.4 | 43.0 | 1,892 | 5x  
  
Table 4: Ablation on LongBench (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2)) using GPT-3.5-Turbo in 2,000 tokens constraint.

For the baselines experiment, we use the currently recommended strongest model, all-mpnet-base-v2161616https://www.sbert.net/docs/pretrained_models.html, as the dense representation model for SentenceBERT. We use the recommended “text-embedding-ada-002" as the embedding model for OpenAI Embedding171717https://platform.openai.com/docs/guides/embeddings/. We use the GPT2-dolly181818https://huggingface.co/lgaalves/gpt2-dolly as the small language model in w/ GPT2-small ablation experiments.

##  Appendix C Additional Experimental Results

###  C.1 Empirical Study of Question-aware Fine-grained Compression

Figure [5](https://arxiv.org/html/2310.06839v2#A2.F5 "Figure 5 ‣ B.2 Other Implementation Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") shows the distribution of the document’s average perplexity when the ground-truth is located at more positions within the prompt. As can be observed, as the context length increases, the original perplexity curve remains relatively stable. In unrelated documents, a higher perplexity is still retained, making it easier to remove relevant tokens from the related documents in the prompt compression process, thereby damaging the corresponding semantic information. Contrarily, contrastive perplexity shows an increase in perplexity in documents related to the question. According to the theoretical derivation in Appendix [A](https://arxiv.org/html/2310.06839v2#A1 "Appendix A Derivation Of Question-Aware Fine-Grained Compression ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), it’s known that contrastive perplexity characterizes the conditional probability of tokens corresponding to the question. The higher the relevance, the higher the contrastive perplexity, thereby retaining key information in the prompt compression process.

###  C.2 Ablation in LongBench

Methods | SingleDoc | MultiDoc | Summ. | FewShot | Synth. | Code | AVG | Tokens | 1/τ1𝜏1/\tau1 / italic_τ  
---|---|---|---|---|---|---|---|---|---  
Original Prompt | 27.4 | 30.3 | 20.3 | 49.9 | 12.5 | 42.5 | 30.5 | 10,295 | -  
Retrieval-based Methods  
BM25 | 2.4 | 2.6 | 16.4 | 8.7 | 0.0 | 44.7 | 12.5 | 1,985 | 5x  
SBERT | 11.6 | 13.7 | 21.1 | 16.2 | 7.5 | 30.0 | 16.7 | 1,947 | 5x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 30.3 | 32.4 | 24.5 | 41.0 | 27.5 | 38.1 | 32.3 | 1,960 | 5x  
Compression-based Methods |  |  |   
Selective-Context | 16.1 | 23.5 | 21.8 | 21.4 | 2.5 | 35.9 | 20.2 | 1,925 | 5x  
LLMLingua | 20.6 | 22.3 | 22.4 | 35.6 | 0.0 | 35.4 | 22.7 | 1,950 | 5x  
LongLLMLingua | 31.3 | 34.6 | 24.6 | 46.1 | 27.8 | 48.8 | 35.5 | 1,822 | 6x  
  
Table 5: Performance of different methods under different compression ratios on LongBench (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2)) using LongChat-13b in 2,000 tokens constraint. 

Methods | GvRp | SSFD | QMsm | SQAL | QALT | Nrtv | Qspr | MuSQ | SpDg | BkSS | AVG | Tokens | 1/τ1𝜏1/\tau1 / italic_τ | Latency | Speedup  
---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---  
3,000 tokens constraint  
Retrieval-based Methods |  |  |  |  |  |   
BM25 | 9.7 | 3.4 | 11.7 | 14.3 | 57.1 | 5.9 | 25.7 | 11.2 | 29.6 | 29.6 | 19.8 | 3,379 | 3x | 5.5 | 2.2x  
SBERT | 16.5 | 9.8 | 12.3 | 15.2 | 60.0 | 14.6 | 23.4 | 12.1 | 39.4 | 36.4 | 24.0 | 3,340 | 3x | 5.9 | 2.1x  
OpenAI | 14.3 | 8.3 | 12.0 | 15.3 | 66.7 | 13.3 | 24.3 | 11.7 | 31.2 | 26.4 | 22.4 | 3,362 | 3x | 11.7 | 1.0x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 19.5 | 11.6 | 14.7 | 15.5 | 66.7 | 20.5 | 27.6 | 13.0 | 60.8 | 43.4 | 29.3 | 3,350 | 3x | 6.2 | 2.0x  
Compression-based Methods |  |  |  |  |  |  |  |  |   
Selective-Context | 20.8 | 9.1 | 11.7 | 13.4 | 50.0 | 9.8 | 26.1 | 11.0 | 46.0 | 9.5 | 20.7 | 3,460 | 3x | 54.2 | 0.2x  
LLMLingua | 18.7 | 10.0 | 14.9 | 16.8 | 61.9 | 26.9 | 27.2 | 23.4 | 62.9 | 44.5 | 30.7 | 3,366 | 3x | 7.4 | 1.7x  
LongLLMLingua | 22.1 | 12.8 | 15.9 | 17.1 | 67.0 | 27.8 | 31.3 | 23.9 | 65.8 | 46.5 | 33.0 | 3,431 | 3x | 8.2 | 1.5x  
2,000 tokens constraint  
Retrieval-based Methods |  |  |  |  |  |   
BM25 | 8.8 | 2.5 | 11.1 | 13.5 | 60.0 | 7.0 | 4.9 | 20.3 | 39.9 | 32.9 | 20.1 | 1,799 | 5x | 3.8 | 3.2x  
SBERT | 10.2 | 7.9 | 13.7 | 13.2 | 60.0 | 8.1 | 10.8 | 1.7 | 37.2 | 42.8 | 20.5 | 1,773 | 6x | 4.1 | 3.0x  
OpenAI | 11.1 | 8.0 | 11.8 | 13.6 | 60.0 | 7.1 | 13.2 | 4.0 | 33.6 | 43.6 | 20.6 | 1,784 | 5x | 9.9 | 1.2x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 18.2 | 9.8 | 12.3 | 15.9 | 57.1 | 10.1 | 17.8 | 7.3 | 57.7 | 42.3 | 24.9 | 1,771 | 6x | 4.7 | 2.6x  
Compression-based Methods |  |  |  |  |  |  |  |  |   
Selective-Context | 19.0 | 8.4 | 9.7 | 12.4 | 47.0 | 12.5 | 21.6 | 11.5 | 41.2 | 11.0 | 19.4 | 1,865 | 5x | 47.5 | 0.3x  
LLMLingua | 19.4 | 11.9 | 13.1 | 16.0 | 62.1 | 23.7 | 24.0 | 22.4 | 33.9 | 44.9 | 27.2 | 1,862 | 5x | 4.8 | 0.3x  
LongLLMLingua | 20.1 | 12.4 | 14.9 | 16.5 | 65.1 | 27.7 | 30.7 | 23.6 | 68.5 | 47.2 | 32.7 | 1,826 | 6x | 5.2 | 2.3x  
Original Prompt | 21.8 | 12.1 | 17.9 | 17.4 | 66.7 | 25.3 | 29.8 | 20.0 | 69.7 | 44.1 | 32.5 | 9,788 | - | 12.2 | -  
Zero-shot | 9.4 | 3.0 | 8.6 | 11.4 | 42.9 | 10.6 | 12.4 | 5.5 | 4.2 | 0.0 | 12.8 | 32 | 306x | 1.0 | 12.2x  
  
Table 6: Performance breakdown of different methods under different compression ratios on ZeroSCROLLS (Shaham et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib34)) using GPT-3.5-Turbo.

Methods | F1 | Tokens | 1/τ1𝜏1/\tau1 / italic_τ  
---|---|---|---  
Original Prompt | 45.8 | 2,427 | -  
BM25 | 28.5 | 1,295 | 1.9x  
SBERT | 36.2 | 1,288 | 1.9x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 46.3 | 1,295 | 1.9x  
Selective-Context | 19.6 | 1,141 | 2.1x  
LLMLingua | 40.1 | 1,110 | 2.2x  
LongLLMLingua | 51.2 | 1,077 | 2.3x  
Question-aware Coarse-grained  
\- w/o Question-awareness | 43.2 | 1,076 | 2.3x  
\- w/ SBERT | 47.3 | 1,070 | 2.3x  
\- w/ p⁢(𝐱kdoc|xique,restrict)𝑝conditionalsuperscriptsubscript𝐱𝑘docsubscriptsuperscript𝑥querestrict𝑖p(\mathbf{x}_{k}^{\text{doc}}|x^{\text{que},\text{restrict}}_{i})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) | 44.0 | 1,066 | 2.3x  
\- w/o restrict | 49.2 | 1,078 | 2.3x  
\- w/o Question-aware Fine-grained | 48.4 | 1,118 | 2.2x  
\- w/o Dynamic Compression Ratio | 48.2 | 1,090 | 2.2x  
\- w/o Subsequence Recovery | 50.7 | 1,077 | 2.3x  
\- w/o Document Reordering | 49.2 | 1,077 | 2.3x  
\- w/ GPT2-small | 48.4 | 1,095 | 2.2x  
  
Table 7: Performance of different methods and ablation study on MuSicQue (Trivedi et al., [2022](https://arxiv.org/html/2310.06839v2#bib.bib38)) with 2x constraint using GPT-3.5-Turbo.

Methods | Retrieval | Timeline Reorder | Computation | Reasoning | AVG | Tokens | 1/τ1𝜏1/\tau1 / italic_τ  
---|---|---|---|---|---|---|---  
Retrieval-based Methods  
BM25 | 20.4 | 21.7 | 8.2 | 26.3 | 19.2 | 3,185 | 10x  
SBERT | 28.9 | 21.1 | 10.7 | 27.2 | 22.0 | 3,169 | 10x  
LongLLMLingua rksubscript𝑟𝑘r_{k}italic_r start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT | 38.6 | 32.2 | 16.2 | 26.3 | 28.3 | 3,158 | 10x  
Compression-based Methods  
Selective-Context | 16.7 | 5.0 | 2.3 | 17.6 | 10.4 | 3,710 | 8x  
LLMLingua | 10.0 | 25.0 | 13.3 | 21.1 | 17.3 | 3,404 | 9x  
LongLLMLingua | 40.0 | 35.0 | 19.7 | 33.6 | 32.1 | 3,121 | 10x  
LongLLMLingua w/o Reorder | 39.3 | 33.8 | 18.7 | 31.6 | 30.9 | 3,119 | 10x  
Original Prompt | 24.1 | 20.9 | 13.5 | 32.1 | 22.6 | 30,546 | -  
Zero-shot | 8.7 | 6.3 | 1.2 | 14.5 | 7.7 | 43 | 710x  
  
Table 8: Performance of different methods on LooGLE (Li et al., [2023b](https://arxiv.org/html/2310.06839v2#bib.bib23)) long dependency QA.

Table [4](https://arxiv.org/html/2310.06839v2#A2.T4 "Table 4 ‣ B.2 Other Implementation Details ‣ Appendix B Experiment Details ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") presents the results from the ablation experiment in the LongBench long context benchmark. It can be observed that in various long context tasks: 1) Removing the question-aware coarse-grained, question-aware fine-grained, dynamic compression ratio, document reordering, and subsequence recovery proposed by LongLLMLingua all result in different degrees of performance drop. 2) Among these, question-aware coarse-grained is particularly important for document-based QA and synthetic tasks, with the maximum drop being 35.8 points; its impact on summarization and code tasks is relatively smaller. 3) The design of the conditional probability in the question-aware coarse-grained module improves the results in all tasks, including code completion, single-document question-answer, and synthetic tasks. Changing the order of conditional probabilities or removing the restrict prompt both lead to varying degrees of performance decline. 4) Removing question-aware fine-grained, dynamic compression ratio has a more significant impact on document-based QA and synthetic tasks. 5) The subsequence recovery module can enhance reference-based tasks, but its improvement on tasks like summarization, code, synthetic, etc., is relatively smaller. 6) Document reordering is effective for all types of tasks. Reordering at the document level does not affect LLMs’ understanding of context information, even for timeline-related tasks (see timeline reorder in LooGLE, Table [8](https://arxiv.org/html/2310.06839v2#A3.T8 "Table 8 ‣ C.2 Ablation in LongBench ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression")). On the contrary, reordering can effectively alleviate the "lost in the middle" issue, thereby improving LLMs performance. 7) Using GPT2-small reduces the capture of effective tokens, but it can still achieve results close to or even slightly better than the original prompt.

###  C.3 LongBench Using LongChat-13b-16k

Table [5](https://arxiv.org/html/2310.06839v2#A3.T5 "Table 5 ‣ C.2 Ablation in LongBench ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") presents the experiment results in the LongBench long context benchmark using LongChat-13b-16k. It can be seen that the compressed prompt can also achieve good results on other LLMs, such as LongChat-13b-16k. Specifically, 1) there is a maximum improvement of 15.5 points in synthetic tasks. Except for a slight drop in few-shot Learning, there is an improvement of 3-5 points in other tasks. 2) The performance trends of retrieval-based and compressed-based baselines are similar to the results in GPT-3.5-Turbo.

###  C.4 ZeroSCROLLS

| Multi-document QA | LongBench | ZeroScolls | MuSicQue | LooGLE  
---|---|---|---|---|---  
Original | 4.6 | 31.5 | 30.6 | 3.8 | 93.6  
Ours | 1.3 (↓↓\downarrow↓71.7%) | 3.0 (↓↓\downarrow↓90.5%) | 3.2 (↓↓\downarrow↓89.5%) | 1.8 (↓↓\downarrow↓52.6%) | 5.6 (↓↓\downarrow↓94.0%)  
  
Table 9: The inference costs $ (per 1,000 samples) for various datasets using GPT-3.5-Turbo.

Table [6](https://arxiv.org/html/2310.06839v2#A3.T6 "Table 6 ‣ C.2 Ablation in LongBench ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") presents a detailed performance breakdown on the ZeroSCROLLS benchmark. It can be observed that in the four summarization tasks - GvRp, SSFD, QMsm, SQAL, LongLLMLingua closely matches or slightly surpasses the original results under two compression constraints. Meanwhile, in the four long context QA tasks - Qsqr, Nrtv, QALT, MuSQ, there is a significant improvement. Notably, in the MuSiQue task, which is based on a question-answering dataset from books and movie scripts, there is a 2.1 point increase even under a 2,000 tokens constraint. It’s worth mentioning that MuSiQue is a multi-hop question-answering dataset that requires LLMs to utilize global information for long dependency QA. LongLLMLingua can also improve by 3.5 points under a 6x compression ratio. In the two ordering tasks, SpDg and BkSS, LongLLMLingua can better retain globally sensitive information, resulting in a 3.0 point improvement in BkSS after prompt compression.

It’s important to note that although the ZeroScrolls validation dataset is relatively small, it still demonstrates conclusions similar to previous experimental observations across various methods and tasks. Furthermore, this study conducted an in-depth analysis of the multi-hop QA task - MuSiQue, and another long context benchmark - LooGLE. The results can be found in Appendix [C.5](https://arxiv.org/html/2310.06839v2#A3.SS5 "C.5 MuSiQue ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") and Appendix [C.6](https://arxiv.org/html/2310.06839v2#A3.SS6 "C.6 LooGLE ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression").

###  C.5 MuSiQue

Table [7](https://arxiv.org/html/2310.06839v2#A3.T7 "Table 7 ‣ C.2 Ablation in LongBench ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") presents the results from the MuSiQue multi-hop question-answer dataset. From the table, it can be observed that in the multi-hop QA task, requiring global information: 1) LongLLMLingua can reduce noise in the prompt by eliminating irrelevant information and putting more related information at the beginning or end of the prompt, thereby improving performance by 5.4 points. 2) The performance drop is more pronounced for retrieval-based methods, particularly for n-gram-based methods like BM25. Due to long dependencies, direct matching information is lost, resulting in less relevant information being recalled. 3) The performance of compression-based methods is slightly different. Selective-Context does not distinguish between different modules’ sensitivity, resulting in a loss of question and instruction-related information, thereby leading to poorer performance. However, LLMLingua can still retain relevant key information at around a 2x compression ratio. 4) The ablation experiments show that every module designed in LongLLMLingua plays a role in the multi-hop task. The removal of the question-aware coarse-grained and w/ p⁢(𝐱kdoc|xique,restrict)𝑝conditionalsuperscriptsubscript𝐱𝑘docsubscriptsuperscript𝑥querestrict𝑖p(\mathbf{x}_{k}^{\text{doc}}|x^{\text{que},\text{restrict}}_{i})italic_p ( bold_x start_POSTSUBSCRIPT italic_k end_POSTSUBSCRIPT start_POSTSUPERSCRIPT doc end_POSTSUPERSCRIPT | italic_x start_POSTSUPERSCRIPT que , restrict end_POSTSUPERSCRIPT start_POSTSUBSCRIPT italic_i end_POSTSUBSCRIPT ) modules, which have difficulty in perceiving the importance distribution of corresponding questions, can cause a drop of up to 8 points. Removing the restrict prompt in the question-aware coarse module can also cause a 2-point drop due to the hallucination issue of small LLM. In addition, removing question-aware fine-grained, dynamic compression ratio, and document reordering can all cause a drop of 0.5-2.8 points. 5) Moreover, if the small language model in LongLLMLingua is replaced with GPT2-small, it can further improve the acceleration ratio and still achieve a result that is 2.6 points better than the original prompt.

###  C.6 LooGLE

Table [8](https://arxiv.org/html/2310.06839v2#A3.T8 "Table 8 ‣ C.2 Ablation in LongBench ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") presents the experiment results in the LooGLE long dependency benchmark, which features longer prompts (∼similar-to\sim∼30k) and more global dependencies. From the table, we can observe that: 1) LongLLMLingua can effectively improve the performance of long context tasks by compressing prompts, even for long dependency tasks. The results show that LongLLMLingua significantly improves performance in tasks such as retrieval, timeline reorder, and computation, with the maximum improvement reaching 15.9 points. 2) The document reorder in LongLLMLingua is effective in all types of tasks, even in tasks highly related to the timeline, it can effectively improve performance by alleviating the "lost in the middle" issue. 3) Retrieval-based methods tend to lose performance in tasks that have longer dependencies, such as computation and reasoning. 4) For compression-based methods, due to the difficulty in perceiving question information, there tends to be a larger performance loss in retrieval tasks within long contexts.

##  Appendix D Economic Cost

Table [9](https://arxiv.org/html/2310.06839v2#A3.T9 "Table 9 ‣ C.4 ZeroSCROLLS ‣ Appendix C Additional Experimental Results ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") presents the estimated per 1,000 samples inference costs for various datasets, encompassing input prompts and generated output text, based on GPT-3.5-Turbo pricing191919https://openai.com/pricing. Our approach demonstrates substantial savings in computational resources and monetary expenses, particularly in long context situations. Cost reductions of $3.3 (71.7%), $28.5 (90.5%), $27.4 (89.5%), $2.0 (52.6%), and $88.0 (94.0%) per 1,000 samples are observed for Multi-document QA, LongBench, ZeroScrolls, MuSiQue, and LooGLE, respectively.

Ours w/o Token-level Question-aware: Compressed Prompt: Write a high-quality answer for the given question using only the provided search results (some of which might be irrelevant).   
Document [1](: Physics)gen,, who received2K, which is ,73,0 in0. Johnen only to twice6. Mariaie won, for.g was, until1estate he. Two:Mayer (1963). As of 2017, the prize has been awarded Question: who got the first nobel prize in physics   
Answer:   
LLMs’ Response: No answer found in the given search results. Ours w/ Token-level Question-aware: Compressed Prompt: Write a high-quality answer for the given question using only the provided search results (some of which might be irrelevant).   
1Title: List of Nobelates in The first Nobel Prize was1 to Wilhelmrad, of who received 1582 which,70 in0 en the prize. Skska also won two Nobeles for physics3g01, theate he women prize:ertMayer (1963). As of 2017, the prize has been awarded Question: who got the first nobel prize in physics   
Answer:   
LLMs’ Response: Wilhelmrad LLMs’ Response after Subsquence Recovery: Wilhelm Conrad Röntgen Ground Truth: Wilhelm Conrad Röntgen Figure 6: Comparing the compressed prompt and LLMs’ response before and after using Question-aware Fine-grained Compression and Subsequence Recovery(1/τ1𝜏1/\tau1 / italic_τ = 30x, high compression ratio setting) from NaturalQuestions Multi-document QA (Liu et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib25)) using GPT-3.5-Turbo.

##  Appendix E Ablation Analysis

Figure [6](https://arxiv.org/html/2310.06839v2#A4.F6 "Figure 6 ‣ Appendix D Economic Cost ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") illustrates the compressed prompts from the Multi-document QA dataset, comparing the use of contrastive perplexity at a high compression ratio (30x). It shows that without question-aware token-level prompt compression, LongLLMLingua tends to compress key information, a tendency that becomes more pronounced at higher compression ratios. Conversely, employing contrastive perplexity allows for better detection of key information related to the question within the context, thus preserving key information within the compressed prompt.

##  Appendix F Cases Study

Figures [7](https://arxiv.org/html/2310.06839v2#A6.F7 "Figure 7 ‣ Appendix F Cases Study ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), [8](https://arxiv.org/html/2310.06839v2#A6.F8 "Figure 8 ‣ Appendix F Cases Study ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression"), and [9](https://arxiv.org/html/2310.06839v2#A6.F9 "Figure 9 ‣ Appendix F Cases Study ‣ LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression") display the outcomes before and after compression, as well as the LLMs’ responses in various scenarios.

Original Prompt: … Document [1](Title: Dancing on Ice) It was confirmed on 25 January 2018, that Dancing on Ice had been recommissioned for an eleventh series to air in 2019. … Compressed Prompt: Write a high-quality answer for the given question using only the provided search results (some of which might be irrelevant).   
1Title: Dancing on was confirmed on 2 January 2018 that Dancing on had been recommissioned for an eleventh series air in 209. Document [2Title: Dan on) Dan on Ice Dancing on British presented by Phillip Schof alongside Holly Willough from 26 to 2011, and Christine Bleakley from 2012 to 204 The show consists of celebrit and professional partners figure skating in front of a panel of judges The, broadcast on ITV, started on January 2006 and ended on 9 March 2014 after showćontract not renewed by ITV On 4 September 2017, it was announced that rev series would on I 7 January 201 Sch and Willby returning as a 5(: on ( on () The third series of a from January to168TV. The from Saturdays, with Holby present Kar,y Sliner Robin Cins returned to Panel", with Ruth H joining the panel as replacement for Natalia Bestova. The commission of the was confirmed by at the07 announcedova depart the series Robinen Bar,ater and Jasoniner announced 7( on ( )) Dan 2 second of Dan on a from January to1207 ITV It presented Phillip Sch Holly Willough, and judged the "I P consisting Nicky Slater, Nataliaian Karenres Jason Gardiner Karen Barber and Robin Cousins Jaynevill and Christopher Dean co and trained the contestants In this series, cele to ten in first series. The series was won former Kyran Bracken, with Mel Lambert the winner. It announced thatenresge Document []( on Ice on 08 on TV edition started 8 TV2 The Russian version "анду) being on channel0, and renamed in8 to " Ice" (). Its counterpart called "Ice Age (, "Stars on Ice on Channel Oneak IceHviezdyľJ. The Turkish version" is called Dans" ("ance on Document1 on Ice its, all,é () and Sje Chris de In series.2 edition ](: on Ice world) Dan Ice is a made competition world format, and been subsequently Italy Chile where titled after series There have a, the show was broadcast on Channel 13 as a Document [17](Title: Dancing on Ice) the insight to the training of the celebrities over the last week. It was presented by television presenter Ben Shephard and former contestant and "Loose Women" star Coleen Nolan. The show was broadcast from 8 pm to 8.30 pm on Friday evenings on ITV throughout the duration of the main shows season. STV who broadcast the main show did not broadcast this on the Friday evening but after repeating the previous weekś main show on the following Saturday afternoon. Due to poor ratings, "Dancing on Ice Friday" was axed prior to the 2011 series. The show was based in the Question: when is dancing on ice on the tv   
Answer:   
LLMs’ Response: 209 LLMs’ Response after Subsquence Recovery: 2019 Ground Truth: 2019 Figure 7: Cases study on NaturalQuestions Multi-document QA dataset (Liu et al., [2024](https://arxiv.org/html/2310.06839v2#bib.bib25)) in 4x constraint using GPT-3.5-Turbo. Compressed Prompt: Please complete the code given below.
    
    
    public class MessageArchiveManagement
        private static final long MILLISECONDS_IN_DAY = 24 * 00 *0;
        public static final long_CUP = MCON_DAY
        /.../
              .("",.getStart
              add
     ifget() >0
               Node end("
                end.("
                endNode.Value("", Util.getTimestamp(query.getEnd
    addNode
            }        if (.withid null && contact null && !isference
               Node with("           .with
               .Value("valuewith
               .(
            //    queryMessageive(connection, nextQuery
                final(connectionProtocol(), query
                synchronized (eries)
                //    queries.add(nextQuery } }
        public boolean queryInProgress( contact, OnLoaded
        moreMessagesLoadedListener)
           ized (eries)
                (Query query : queries)
                    if(query.getWith().equals(contact.getUserId()))
        if (query.onMoreMessagesLoaded == null &&MessagesListener
        null) query.setOnMoreMessagesLoaded(Listener}
                        return true;}} return false;}}
        private void finalizeQuery(Protocol protocol, Query query) {
            synchronized (queries) {
                .remove(query); }
            Contact contact = null;
            if (query.getWith() != null) {
                contact = protocol.getItemByUID(query.getWith()); }
            if (contact != null) {
        
    

Next line of code:   
LLMs’ Response:
    
    
            contact.setLastMessageTransmitted(query.getEnd());\n
        
    

Ground Truth:
    
    
            if (contact.setLastMessageTransmitted(query.getEnd())) {
        
    

Zero-shot LLMs’ Response:
    
    
            contact.removeQuery(query);\n
        
    

Figure 8: Cases study on lcc code completion task in LongBench benchmark (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2)) in 2,000 constraint using GPT-3.5-Turbo. Compressed Prompt: Please determine the Type of the question below. Here are some examples of questions.   
Question: How is energy created ? Type Manner of an action Question: What is chocolate ? Type: Definition of something Question: What is a bone marrow transplant ? Type: Definition of something Question: What is fear of odors , body , ? Type Disease and medicine Question: What was the Vietnam War ? Type: Definition of something Question: was education system in 16s ? Type: Other entity Question: What is IP address ? Type: Definition of something Question: are the differences in Catholic Methodist religions ? Type of something … Question: When was San fire ? : Date Question: CNN began broadcasting in what year ? Type: Date Type: Manner of an action Question: What the l behind the ir in the eye called ? Type Equ term Type: Date Question: What the former name of Zimbabwe ? Type: termType something Question: What is troilism ? Type: Definition of something : What is origin of the word , Type: of something : do you name to social security number ? Type Manner of an action : that of an employee Universal and Export ? Type Individual : anesthetic did Queen Victoria allow to be for the birth of her seventh , in 183 ? Type: Disease and medicine : Where isyer ’s rock ? Type location Question: What isymnophobia ? Type: Definition of something … Type burns the most calories ? Type Sport : In what book I find story of Aladdin ? Type In, book and piece an have sex ? Type: Manner of an action: What is the acron for rating forer ? Type Abbreviation : are the Baltic States ? Type: Definition of something : What is appearance , that violates the standards of sexual mor ? Type : Where did the May people live ? : location : What population Kansas ? Type number : was the hurr ? Type: Event : ’s a score aymnast exercise ? Type: number : year become a state ? Type: Date do go school ? Type Reason … Question: What is a fuel cell ?   
Type:   
LLMs’ Response: Definition of something LLMs’ Response after Subsquence Recovery: Definition of something Ground Truth: Definition of something Figure 9: Cases study on trec few-show learning in LongBench benchmark (Bai et al., [2023](https://arxiv.org/html/2310.06839v2#bib.bib2)) in 2,000 constraint using GPT-3.5-Turbo.

Generated on Mon Aug 12 03:50:07 2024 by [LaTeXML](http://dlmf.nist.gov/LaTeXML/)
