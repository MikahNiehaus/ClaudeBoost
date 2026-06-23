<!-- Source: https://www.microsoft.com/en-us/research/blog/llmlingua-innovating-llm-efficiency-with-prompt-compression/ | Tier: A | Topic: context-compression | Fetched: 2026-06-23 -->

[Skip to main content]() [ ](https://www.microsoft.com) [ Research ](/en-us/research/) [Publications](/en-us/research/publications/) [Code & data](/en-us/research/tools/) [People](/en-us/research/people/) [Microsoft Research blog](/en-us/research/blog/) [Artificial intelligence](/en-us/research/focus-area/ai-and-microsoft-research/) [Audio & acoustics](/en-us/research/research-area/audio-acoustics/) [Computer vision](/en-us/research/research-area/computer-vision/) [Graphics & multimedia](/en-us/research/research-area/graphics-and-multimedia/) [Human-computer interaction](/en-us/research/research-area/human-computer-interaction/) [Human language technologies](/en-us/research/research-area/human-language-technologies/) [Search & information retrieval](/en-us/research/research-area/search-information-retrieval/) [Data platforms and analytics](/en-us/research/research-area/data-platform-analytics/) [Hardware & devices](/en-us/research/research-area/hardware-devices/) [Programming languages & software engineering](/en-us/research/research-area/programming-languages-software-engineering/) [Quantum computing](/en-us/research/research-area/quantum/) [Security, privacy & cryptography](/en-us/research/research-area/security-privacy-cryptography/) [Systems & networking](/en-us/research/research-area/systems-and-networking/) [Algorithms](/en-us/research/research-area/algorithms/) [Mathematics](/en-us/research/research-area/computational-sciences-mathematics/) [Ecology & environment](/en-us/research/research-area/ecology-environment/) [Economics](/en-us/research/research-area/economics/) [Medical, health & genomics](/en-us/research/research-area/medical-health-genomics/) [Social sciences](/en-us/research/research-area/social-sciences/) [Technology for emerging markets](/en-us/research/research-area/technology-for-emerging-markets/) [Academic programs](/en-us/research/academic-programs/) [Events & academic conferences](/en-us/research/events-conferences/) [Microsoft Research Forum](https://researchforum.microsoft.com) [Behind the Tech podcast](https://www.microsoft.com/en-us/behind-the-tech ) [Microsoft Research blog](/en-us/research/blog) [Microsoft Research Forum](https://researchforum.microsoft.com) [Microsoft Research podcast](/en-us/research/podcast/) [About Microsoft Research](/en-us/research/about-microsoft-research/) [Careers & internships](/en-us/research/careers/) [People](/en-us/research/people/) [Emeritus program](/en-us/research/microsoft-research-emeritus-program/) [News & awards](/en-us/research/news-and-awards/) [Microsoft Research newsletter](https://info.microsoft.com/ww-landing-microsoft-research-newsletter.html?wt.mc_id=S-webpage_msr-homepage) [Africa](/en-us/research/lab/microsoft-research-lab-africa-nairobi/) [AI for Science](/en-us/research/lab/microsoft-research-ai-for-science/) [AI Frontiers](/en-us/research/lab/ai-frontiers/) [Asia-Pacific](/en-us/research/lab/microsoft-research-asia/) [Cambridge](/en-us/research/lab/microsoft-research-cambridge/) [Health Futures](/en-us/research/lab/microsoft-health-futures/) [India](/en-us/research/lab/microsoft-research-india/) [Montreal](/en-us/research/lab/microsoft-research-montreal/) [New England](/en-us/research/lab/microsoft-research-new-england/) [New York City](/en-us/research/lab/microsoft-research-new-york/) [Redmond](/en-us/research/lab/microsoft-research-redmond/) [Applied Sciences](/en-us/research/lab/applied-sciences-group/) [Mixed Reality & AI - Cambridge](/en-us/research/lab/mixed-reality-ai-lab-cambridge/) [Mixed Reality & AI - Zurich](/en-us/research/lab/mixed-reality-ai-zurich/) [ Register: Research Forum ](https://researchforum.microsoft.com) [Microsoft Security](https://www.microsoft.com/en-us/security) [Azure](https://azure.microsoft.com/en-us/) [Dynamics 365](https://dynamics.microsoft.com/en-us/) [Microsoft 365](https://www.microsoft.com/en-us/microsoft-365/business/) [Microsoft Teams](https://www.microsoft.com/en-us/microsoft-teams/group-chat-software) [Windows 365](https://www.microsoft.com/en-us/windows-365) [Microsoft AI](https://www.microsoft.com/en-us/ai?icid=DSM_AllCommercial_AI) [Azure Space](https://azure.microsoft.com/en-us/solutions/space/) [Mixed reality](https://www.microsoft.com/en-us/mixed-reality/windows-mixed-reality) [Microsoft HoloLens](https://www.microsoft.com/en-us/hololens) [Microsoft Viva](https://www.microsoft.com/en-us/microsoft-viva) [Quantum computing](https://azure.microsoft.com/en-us/solutions/quantum-computing/) [Sustainability](https://www.microsoft.com/en-us/corporate-responsibility/sustainability?icid=DSM_AllCommercial_Sustainability) [Education](https://www.microsoft.com/en-us/education) [Automotive](https://www.microsoft.com/en-us/industry/automotive) [Financial services](https://www.microsoft.com/en-us/industry/financial-services/banking) [Government](https://www.microsoft.com/en-us/industry/government) [Healthcare](https://www.microsoft.com/en-us/industry/health/microsoft-cloud-for-healthcare) [Manufacturing](https://www.microsoft.com/en-us/industry/manufacturing/microsoft-cloud-for-manufacturing) [Retail](https://www.microsoft.com/en-us/industry/consumer-goods) [Find a partner](https://partner.microsoft.com/en-US/) [Become a partner](https://partner.microsoft.com/en-US/membership/cloud-solution-provider) [Partner Network](https://partner.microsoft.com/en-us/membership) [Microsoft Marketplace](https://marketplace.microsoft.com?icid=DSM_AllCommercial_Marketplace&ocid=cmm3c8ee9bs) [Software companies](https://www.microsoft.com/software-development-companies?icid=DSM_AllCommercial_SoftwareCompanies&ocid=cmm3c8ee9bs) [Blog](https://blogs.microsoft.com/) [Microsoft Advertising](https://about.ads.microsoft.com/en-us?s_cid=dig-src_uhfcomm) [Developer Center](https://developer.microsoft.com/en-us/) [Documentation](https://learn.microsoft.com/docs/) [Events](https://www.microsoft.com/en-us/events) [Licensing](https://www.microsoft.com/en-us/licensing/) [Microsoft Learn](https://learn.microsoft.com/) [Microsoft Research](https://www.microsoft.com/en-us/research/) [View Sitemap](https://www.microsoft.com/en-us/sitemap)

[ Return to Blog Home ](https://www.microsoft.com/en-us/research/blog/)

## Microsoft Research Blog

#  LLMLingua: Innovating LLM efficiency with prompt compression 

Published  December 7, 2023 

By  Huiqiang Jiang , Research SDE 2  [ Qianhui Wu  ](https://www.microsoft.com/en-us/research/people/qianhuiwu/) , Senior Researcher  [ Chin-Yew Lin  ](https://www.microsoft.com/en-us/research/people/cyl/) , Senior Principal Research Manager  [ Yuqing Yang  ](https://www.microsoft.com/en-us/research/people/yuqyang/) , Principal Research SDE Manager  Lili Qiu , Assistant Managing Director 

Share this page

  * [ Share on Facebook ](https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F "Share on Facebook")
  * [ Share on X ](
			https://x.com/intent/tweet?text=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&url=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F			 "Share on X")
  * [ Share on LinkedIn ](
			https://www.linkedin.com/shareArticle?mini=true&url=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F&title=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&summary=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&source=Microsoft%20Research			 "Share on LinkedIn")
  * [ Share on Reddit ](
			http://www.reddit.com/submit?title=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&url=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F			 "Share on Reddit")
  * [ Subscribe to our RSS feed ](https://www.microsoft.com/en-us/research/feed/ "Subscribe to our RSS feed")



**_This research paper was presented at the_**[**2023 Conference on Empirical Methods in Natural Language Processing** (opens in new tab)](https://2023.emnlp.org/)**_(EMNLP 2023), the premier conference on natural language processing and artificial intelligence._**

As large language models (LLMs) models advance and their potential becomes increasingly apparent, an understanding is emerging that the quality of their output is directly related to the nature of the prompt that is given to them. This has resulted in the rise of prompting technologies, such as chain-of-thought (CoT) and in-context-learning (ICL), which facilitate an increase in prompt length. In some instances, prompts now extend to tens of thousands of tokens, or units of text, and beyond. While longer prompts hold considerable potential, they also introduce a host of issues, such as the need to exceed the chat window’s maximum limit, a reduced capacity for retaining contextual information, and an increase in API costs, both in monetary terms and computational resources.

To address these challenges, we introduce a prompt-compression method in our paper, “[LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models](https://www.microsoft.com/en-us/research/publication/llmlingua-compressing-prompts-for-accelerated-inference-of-large-language-models/),” presented at [EMNLP 2023 (opens in new tab)](https://2023.emnlp.org/). Using a well-trained small language model, such as GPT2-small or LLaMA-7B, LLMLingua identifies and removes unimportant tokens from prompts. This compression technique enables closed LLMs to make inferences from the compressed prompt. Although the token-level compressed prompts may be difficult for humans to understand, they prove highly effective for LLMs. This is illustrated in Figure 1.

Figure 1. LLMLingua’s framework

## LLMLingua’s method and evaluation

video series

[ ](https://www.microsoft.com/en-us/research/story/on-second-thought/)

## On Second Thought

A video series with Sinead Bovell built around the questions everyone’s asking about AI. With expert voices from across Microsoft, we break down the tension and promise of this rapidly changing technology, exploring what’s evolving and what’s possible.

[ Explore the series ](https://www.microsoft.com/en-us/research/story/on-second-thought/)

Opens in a new tab

To develop LLMLingua’s framework, we employed a budget controller to balance the sensitivities of different modules in the prompt, preserving the language's integrity. Our two-stage process involved course-grained prompt compression. We first streamlined the prompt by eliminating certain sentences and then individually compressed the remaining tokens. To preserve coherence, we employed an iterative token-level compression approach, refining the individual relationships between tokens. Additionally, we fine-tuned the smaller model to capture the distribution information from different closed LLMs by aligning it with the patterns in the LLMs’ generated data. We did this through instruction tuning.

To assess LLMLingua’s performance, we tested compressed prompts on four different datasets, GSM8K, BBH, ShareGPT, and Arxiv-March23, encompassing ICL, reasoning, summarization, and conversation. Our approach achieved impressive results, achieving up to 20x compression while preserving the original prompt's capabilities, particularly in ICL and reasoning. LLMLingua also significantly reduced system latency.

During our test, we used LLaMA-7B as the small language model and GPT-3.5-Turbo-0301, one of OpenAI’s LLMs, as the closed LLM. The results show that LLMLingua maintains the original reasoning, summarization, and dialogue capabilities of the prompt, even at a maximum compression ratio of 20x, as reflected in the evaluation metric (EM) columns in Tables 1 and 2. At the same time, other compression methods failed to retain key semantic information in prompts, especially in logical reasoning details. For a more in-depth discussion of these results, refer to section 5.2 of the [paper](https://www.microsoft.com/en-us/research/publication/llmlingua-compressing-prompts-for-accelerated-inference-of-large-language-models/).

Table 1. Performance of different methods at different target compression ratios on the GSM8K and BBH datasets. Table 2. Performance of different methods at different target compression ratios for conversation and summarization tasks.

## LLMLingua is robust, cost-effective, efficient, and recoverable

LLMLingua also showed impressive results across various small language models and different closed LLMs. When using GPT-2-small, LLMLingua achieved a strong performance score of 76.27 under the ¼-shot constraint, close to the LLaMA-7B's result of 77.33 and surpassing the standard prompt results of 74.9. Similarly, even without aligning Claude-v1.3, one of the post powerful LLMs, LLMLingua’s score was 82.61 under the ½-shot constraint, outperforming the standard prompt result of 81.8.

LLMLingua also proved effective in reducing response length, leading to significant reductions in latency in the LLM’s generation process, with reductions ranging between 20 to 30 percent, as shown in Figure 2.

Figure 2. The distribution of token lengths generated at varying compression ratios.

What makes LLMLingua even more impressive is its recoverability feature. When we used GPT-4 to restore the compressed prompts, it successfully recovered all key reasoning information from the full nine-step chain-of-thought (CoT) prompting, which enables LLMs to address problems through sequential intermediate steps. The recovered prompt was almost identical to the original, and its meaning was retained. This is shown in Tables 3 and 4.

Table 3. Latency comparison on GSM8K. LLMLingua can accelerate LLMs' end-to-end inference by a factor of 1.7–5.7x.  Table 4. Recovering the compressed prompt from GSM8K using GPT-4.

## Enhancing the user experience and looking ahead

LLMLingua is already proving its value through practical application. It has been integrated into [LlamaIndex (opens in new tab)](https://github.com/run-llama/llama_index/blob/main/llama_index/indices/postprocessor/longllmlingua.py), a widely adopted retrieval-augmented generation (RAG) framework. Currently, we are collaborating with product teams to reduce the number of tokens required in LLM calls, particularly for tasks like multi-document question-answering. Here, our goal is to significantly improve the user experience with LLMs. 

For the long-term, we have proposed [LongLLMLingua](https://www.microsoft.com/en-us/research/publication/longllmlingua-accelerating-and-enhancing-llms-in-long-context-scenarios-via-prompt-compression/), a prompt-compression technique designed for long-context scenarios, such as retrieval-augmented question-answering tasks in applications like chatbots, useful when information evolves dynamically over time. It's also geared for tasks like summarizing online meetings. LongLLMLingua’s primary objective is to enhance LLMs' ability to perceive key information, making it suitable for numerous real-world applications, notably information-based chatbots. We’re hopeful that this innovation paves the way for more sophisticated and user-friendly interactions with LLMs.

Learn more about our work on the [LLMLingua (opens in new tab)](https://llmlingua.com/) page.

Opens in a new tab

## Related publications

###  [LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models ](https://www.microsoft.com/en-us/research/publication/llmlingua-compressing-prompts-for-accelerated-inference-of-large-language-models/)

###  [LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression ](https://www.microsoft.com/en-us/research/publication/longllmlingua-accelerating-and-enhancing-llms-in-long-context-scenarios-via-prompt-compression/)

## Meet the authors

### Huiqiang Jiang

Research SDE 2

### Qianhui Wu

Senior Researcher

[Learn more](https://www.microsoft.com/en-us/research/people/qianhuiwu/)

### Chin-Yew Lin

Senior Principal Research Manager

[Learn more](https://www.microsoft.com/en-us/research/people/cyl/)

### Yuqing Yang

Principal Research SDE Manager

[Learn more](https://www.microsoft.com/en-us/research/people/yuqyang/)

### Lili Qiu

Assistant Managing Director

##  Research Areas 

  * [ Artificial intelligence ](https://www.microsoft.com/en-us/research/research-area/artificial-intelligence/)
  * [ Human language technologies ](https://www.microsoft.com/en-us/research/research-area/human-language-technologies/)



##  Research Groups 

  * [ M365 Research ](https://www.microsoft.com/en-us/research/group/m365-research/)
  * [ Microsoft Research Asia - Shanghai ](https://www.microsoft.com/en-us/research/group/msr-asia-shanghai/)



##  Related projects 

  * [ LLMLingua Series ](https://www.microsoft.com/en-us/research/project/llmlingua/)



##  Related labs 

  * [ Microsoft Research Lab - Asia ](https://www.microsoft.com/en-us/research/lab/microsoft-research-asia/)



Follow us: 

  * [ Follow on X ](https://x.com/intent/follow?original_referrer=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F&screen_name=MSFTResearch)
  * [ Like on Facebook ](https://www.facebook.com/microsoftresearch/)
  * [ Follow on LinkedIn ](https://www.linkedin.com/showcase/microsoftresearch/)
  * [ Subscribe on Youtube ](https://www.youtube.com/user/MicrosoftResearch)
  * [ Follow on Instagram ](https://www.instagram.com/msft_research/)
  * [ Subscribe to our RSS feed ](https://www.microsoft.com/en-us/research/feed/)



Share this page: 

  * [ Share on X ](https://x.com/intent/tweet?text=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&url=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F)
  * [ Share on Facebook ](https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F)
  * [ Share on LinkedIn ](
									https://www.linkedin.com/shareArticle?mini=true&url=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F&title=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&summary=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&source=Microsoft%20Research									)
  * [ Share on Reddit ](
									http://www.reddit.com/submit?title=LLMLingua%3A%20Innovating%20LLM%20efficiency%20with%20prompt%20compression&url=https%3A%2F%2Fwww.microsoft.com%2Fen-us%2Fresearch%2Fblog%2Fllmlingua-innovating-llm-efficiency-with-prompt-compression%2F									)



[Surface Pro](https://www.microsoft.com/surface/devices/surface-pro) [Surface Laptop](https://www.microsoft.com/surface/devices/surface-laptop) [Surface Laptop Ultra](https://www.microsoft.com/en-us/surface/devices/surface-laptop-ultra?icid=DSM_Footer_WhatsNew_SurfaceLaptopUltra) [Surface RTX Spark Dev Box](https://www.microsoft.com/en-us/surface/devices/surface-rtx-spark-dev-box?icid=DSM_Footer_WhatsNew_SurfaceRTXSparkDevBox) [Copilot for organizations](https://www.microsoft.com/en-us/microsoft-copilot/organizations?icid=DSM_Footer_CopilotOrganizations) [Copilot for personal use](https://www.microsoft.com/en-us/microsoft-copilot/for-individuals?form=MY02PT&OCID=GE_web_Copilot_Free_868g3t5nj) [Explore Microsoft products](https://www.microsoft.com/en-us/microsoft-products-and-apps) [Windows 11 apps](https://www.microsoft.com/en-us/windows/apps-for-windows?icid=DSM_Footer_WhatsNew_Windows11apps) [Account profile](https://account.microsoft.com/) [Download Center](https://www.microsoft.com/en-us/download) [Microsoft Store support](https://go.microsoft.com/fwlink/?linkid=2139749) [Returns](https://www.microsoft.com/en-us/store/b/returns) [Order tracking](https://www.microsoft.com/en-us/store/b/order-tracking) [Certified Refurbished](https://www.microsoft.com/en-us/store/b/certified-refurbished-products) [Microsoft Store Promise](https://www.microsoft.com/en-us/store/b/why-microsoft-store?icid=footer_why-msft-store_7102020) [Flexible Payments](https://www.microsoft.com/en-us/store/b/payment-financing-options?icid=footer_financing_vcc) [Microsoft in education](https://www.microsoft.com/en-us/education) [Devices for education](https://www.microsoft.com/en-us/education/devices/overview) [Microsoft Teams for Education](https://www.microsoft.com/en-us/education/products/teams) [Microsoft 365 Education](https://www.microsoft.com/en-us/education/products/microsoft-365) [How to buy for your school](https://www.microsoft.com/education/how-to-buy) [Educator training and development](https://education.microsoft.com/) [Deals for students and parents](https://www.microsoft.com/en-us/store/b/education) [AI for education](https://www.microsoft.com/en-us/education/ai-in-education)

[Microsoft AI](https://www.microsoft.com/en-us/ai?icid=DSM_Footer_AI) [Microsoft Security](https://www.microsoft.com/en-us/security) [Dynamics 365](https://www.microsoft.com/en-us/dynamics-365) [Microsoft 365](https://www.microsoft.com/en-us/microsoft-365/business) [Microsoft Power Platform](https://www.microsoft.com/en-us/power-platform) [Microsoft Teams](https://www.microsoft.com/en-us/microsoft-teams/group-chat-software) [Microsoft 365 Copilot](https://www.microsoft.com/en-us/microsoft-365-copilot?icid=DSM_Footer_Microsoft365Copilot) [Small Business](https://www.microsoft.com/en-us/store/b/business?icid=CNavBusinessStore) [Azure](https://azure.microsoft.com/en-us/) [Microsoft Developer](https://developer.microsoft.com/en-us/) [Microsoft Learn](https://learn.microsoft.com/) [Support for AI marketplace apps](https://www.microsoft.com/software-development-companies/offers-benefits/isv-success?icid=DSM_Footer_SupportAIMarketplace&ocid=cmm3atxvn98) [Microsoft Tech Community](https://techcommunity.microsoft.com/) [Microsoft Marketplace](https://marketplace.microsoft.com?icid=DSM_Footer_Marketplace&ocid=cmm3atxvn98) [Software companies](https://www.microsoft.com/software-development-companies?icid=DSM_Footer_SoftwareCompanies&ocid=cmm3atxvn98) [Visual Studio](https://visualstudio.microsoft.com/) [Careers](https://careers.microsoft.com/) [About Microsoft](https://www.microsoft.com/about) [Company news](https://news.microsoft.com/source/?icid=DSM_Footer_Company_CompanyNews) [Privacy at Microsoft](https://www.microsoft.com/en-us/privacy?icid=DSM_Footer_Company_Privacy) [Investors](https://www.microsoft.com/investor/default.aspx) [Diversity and inclusion](https://www.microsoft.com/en-us/diversity/default?icid=DSM_Footer_Company_Diversity) [Accessibility](https://www.microsoft.com/en-us/accessibility) [Sustainability](https://www.microsoft.com/en-us/corporate-responsibility/sustainability?icid=DSM_Footer_Sustainability)

[ Your Privacy Choices Opt-Out Icon Your Privacy Choices ](https://aka.ms/yourcaliforniaprivacychoices) [ Your Privacy Choices Opt-Out Icon Your Privacy Choices ](https://aka.ms/yourcaliforniaprivacychoices)

[Consumer Health Privacy](https://go.microsoft.com/fwlink/?linkid=2259814) [Sitemap](https://www.microsoft.com/en-us/sitemap1.aspx) [Contact Microsoft](https://support.microsoft.com/contactus) [Privacy ](https://go.microsoft.com/fwlink/?LinkId=521839) Manage cookies [Terms of use](https://go.microsoft.com/fwlink/?LinkID=206977) [Trademarks](https://go.microsoft.com/fwlink/?linkid=2196228) [Safety & eco](https://go.microsoft.com/fwlink/?linkid=2196227) [Recycling](https://www.microsoft.com/en-us/legal/compliance/recycling) [About our ads](https://choice.microsoft.com)
