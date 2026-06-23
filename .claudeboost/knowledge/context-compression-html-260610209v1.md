<!-- Source: https://arxiv.org/html/2606.10209v1 | Tier: A | Topic: context-compression | Fetched: 2026-06-23 -->

##### Report GitHub Issue

×

Title:

Content selection saved. Describe the issue below:

Description:

Submit without GitHub Submit in GitHub

[ Back to arXiv ](/)

[Why HTML?](https://info.arxiv.org/about/accessible_HTML.html) Report Issue [ Back to Abstract ](/abs/2606.10209v1 "Back to abstract page") [ Download PDF](/pdf/2606.10209v1 "Download PDF") [ ](javascript:toggleNavTOC\(\); "Toggle navigation") [ ](javascript:toggleReadingMode\(\); "Disable reading mode, show header and footer")

  1. Abstract
  2. 1 Background
     1. Contributions.
  3. 2 Related Work
     1. Token-level prompt compression.
     2. External and long-term memory.
     3. Agentic context management and compaction.
     4. Tool-use benchmarks.
  4. 3 Methods
     1. 3.1 Task definition
     2. 3.2 System architecture
     3. 3.3 Experimental configurations
        1. Isolating the effect of context engineering.
     4. 3.4 Context construction algorithm
     5. 3.5 Evaluation metrics
     6. 3.6 Dataset
     7. 3.7 Comparison baselines
  5. 4 Results
     1. 4.1 C1 (no user model): motivating the user model
     2. 4.2 Full context: performance gains with severe efficiency cost
     3. 4.3 Context pruning: simultaneous performance and efficiency improvement
     4. 4.4 Summarization: best performance with marginal token overhead
     5. 4.5 Token efficiency analysis
     6. 4.6 Statistical analysis
        1. Effect sizes vs. noise.
     7. 4.7 Sensitivity to the pruning window NN and summary window WW
     8. 4.8 Generalization across expense categories
     9. 4.9 Cross-model generalization: Claude Sonnet 4.5
  6. 5 Failure analysis
  7. 6 Discussion
     1. 6.1 Summary of findings
     2. 6.2 Why context pruning outperforms full history retention
     3. 6.3 Complementary role of summarization
     4. 6.4 Limitations and future work
     5. 6.5 Responsible AI considerations
  8. References
  9. A Reproducibility overview
  10. B Tool inventory
  11. C Metric computation and scoring
  12. D Statistical methodology
     1. Run-level interval.
     2. Pooled binomial (Wilson) interval.
     3. Paired comparisons.
     4. Helper.
     5. Full per-metric dispersion across categories.
  13. E Per-category dataset statistics
     1. Structural notes.
  14. F Qualitative failure and summarization examples
     1. (1) Stale-state reference (C2).
     2. (2) Wrong subcategory mapping (C3).
     3. (3) Duplicate / skipped repeat item (C2).
     4. (4) Premature termination (C3).
     5. (5) Tool / form navigation error (C2).
     6. (6) Residual amount mismatch (C4).
     7. Real C4 summarization output.
  15. G Performance and efficiency figures
  16. H Sensitivity to pruning window NN and summary window WW
     1. Interpretation.
  17. I Cross-model generalization: Claude Sonnet 4.5
  18. J Extended discussion: efficiency and generalizability



[ License: arXiv.org perpetual non-exclusive license ](https://info.arxiv.org/help/license/index.html#licenses-available)

arXiv:2606.10209v1 [cs.AI] 08 Jun 2026

# Less Context, Better Agents: Efficient Context Engineering for Long-Horizon Tool-Using LLM Agents

###### Abstract

Background: Large language models deployed as autonomous agents for enterprise workflows face a critical challenge: verbose tool responses from enterprise systems cause context window overflow and excessive inference costs, preventing reliable task completion at scale. Methods: We evaluate four context engineering configurations applied to GPT-5 for automated hotel expense itemization in Microsoft Dynamics 365 Finance and Operations (D365 F&O) via Model Context Protocol (MCP): (1) GPT-5 with no user model (a motivating ablation), (2) the standard full-context agent (our context-engineering baseline) with full conversation history, (3) context pruned to the last 5 tool call/response pairs, and (4) context pruned with automated summarization using a summary window of 3. Results are reported as averages across 5 independent experimental runs on a 50-task hotel expense benchmark, holding the user model constant across the context-engineering comparison (C2–C4) to isolate the effect of context management. We extend the original study with (i) 95% confidence intervals and effect-size analysis, (ii) sensitivity analyses over the pruning window NN and the summary window WW, (iii) a per-category failure taxonomy, and (iv) generalization evidence across five expense types grouped into three structurally distinct categories, and across a second model family (Claude Sonnet 4.5). Results: C1 (no user model) achieved only 8.0% complete itemization. The full-context configuration reached 71.0% but consumed 1,480,996 tokens and 14.56 hours per benchmark. Context pruning to the last 5 tool calls achieved 79.0% complete itemization with 535,274 tokens—a 63.9% reduction—in 5.39 hours. Adding automated summarization achieved 91.6% complete itemization and 99.64% average amount itemized with 553,374 tokens in 5.79 hours. Discussion: Context engineering with summarization achieves the best balance of performance and efficiency, demonstrating that selective retention of recent tool interactions is more decision-relevant than full history while dramatically reducing token consumption. We position these results as strong evidence for one class of enterprise tool-use workflow rather than a proof of universal generalization, and we discuss the scope and limits of the approach explicitly.   
  
Keywords: context engineering, tool-using LLM agents, context pruning, conversation summarization, Model Context Protocol, enterprise workflow automation, token efficiency, Dynamics 365 Finance and Operations

Abhilasha Lodha∗, Mahsa Pahlavikhah Varnosfaderani, Abir Chakraborty, Abhinav Mithal

Microsoft

{ablodha, mahsap, abchak, mithal}@microsoft.com

##  1 Background

The deployment of large language models (LLMs) as autonomous agents for enterprise workflow automation represents a significant advance in AI-powered productivity (Brown et al., 2020). Agents can navigate complex multi-step processes, interact with enterprise systems through tool calls, and complete tasks that previously required sustained human attention. However, as these agents engage in extended workflows—particularly those interacting with enterprise resource planning (ERP) systems—a fundamental technical constraint emerges: context window overflow caused by verbose tool responses (Jiang et al., 2023).

Modern LLMs operate within finite context windows bounding the total tokens processable per inference call. While recent frontier models have expanded these limits substantially, enterprise system integrations routinely generate tool responses containing extensive metadata, nested form state, navigation breadcrumbs, and system information well beyond what is decision-relevant (Li et al., 2023). In multi-step agentic workflows where agents execute dozens of tool interactions to complete a single task, even large context windows can be exhausted before completion. Furthermore, processing costs scale linearly with context length, making full-history retention prohibitively expensive at production scale. Recent industry analyses of production agents describe the same failure mode under the name “context rot,” where a model’s effective recall degrades as the token count grows, well before the hard context limit is reached (Anthropic, 2025).

This challenge is particularly acute in expense management workflows within Microsoft Dynamics 365 Finance and Operations (D365 F&O). When an LLM agent interacts with D365 F&O via an MCP proxy, each tool response can contain hundreds to thousands of tokens of form metadata. For an expense itemization task requiring decomposition of a single receipt into 4–22 individual line items—each requiring multiple tool interactions to create, populate, and verify—cumulative context rapidly exhausts available token budgets.

The expense itemization task is representative of a broad class of enterprise agentic challenges: agents must decompose a total receipt amount into multiple line items with correct subcategories and amounts, with the strict requirement that the remaining unallocated amount reaches exactly zero. This precision requirement means partial completion constitutes failure in production systems, creating accounting errors, policy violations, and manual remediation costs.

Context engineering—the deliberate management of what information is retained in an agent’s context at each step—offers a practical solution. Rather than maintaining full conversation history (standard practice), context engineering selectively retains the most decision-relevant recent interactions while summarizing or discarding older context. This approach is inference-time only, requires no model retraining, and is designed to be portable across LLM backends.

#### Contributions.

This paper makes the following contributions:

  1. 1.

We formalize a _semantic-level_ context-engineering policy for tool-using agents—recency-based pruning of whole tool call/response pairs plus automated summarization of evicted pairs—and provide its exact construction algorithm (Algorithm 1), distinguishing it from token-level prompt compression and from external memory stores (Section 2).

  2. 2.

On a 50-task hotel-expense benchmark in a live D365 F&O environment, we show that, with the user model held constant, recency pruning and pruning++summarization improve complete itemization from 71.0% to 79.0% to 91.6% _while_ reducing tokens by 62.7% and runtime by 60.2% relative to full context.

  3. 3.

We report run-to-run dispersion, 95% confidence intervals, and effect-size analysis (Section 4.6), and we provide sensitivity analyses over the pruning window NN and the summary window WW (Section 4.7).

  4. 4.

We provide a per-category failure taxonomy (Section 5) and generalization evidence across five expense types grouped into three structurally distinct categories, and a second model family, Claude Sonnet 4.5 (Sections 4.8–4.9).




We hypothesize that (1) restricting context to recent tool interactions improves task-relevant focus while preventing overflow, and (2) automated summarization of pruned context preserves task-level situational awareness without significant token overhead. Our results support both hypotheses for this class of workflow.

##  2 Related Work

We organize prior work along three axes and position our contribution against each. Table 1 summarizes the comparison.

#### Token-level prompt compression.

LLMLingua (Jiang et al., 2023) and Selective Context (Li et al., 2023) reduce input size by deleting or merging low-information _tokens_ within a prompt. These methods operate below the level of the tool interaction: they do not reason about which tool call/response _units_ are still relevant to the agent’s current state, and they can corrupt the structured form state that an ERP agent must read verbatim (e.g., control names, numeric balances). Our policy operates at the _semantic level_ of whole tool call/response pairs, preserving the exact text of retained interactions and only ever evicting or summarizing complete units.

#### External and long-term memory.

MemoryBank (Zhong et al., 2024) and LongMem (Wang et al., 2024) augment models with retrievable memory stores, and recent benchmarks such as LoCoMo (Maharana et al., 2024) and LongMemEval (Wu et al., 2025) evaluate long-horizon recall in multi-session _dialogue_. These target factual recall across conversations rather than the working-memory and stale-state problems of tool-heavy, single-session workflows, where the most recent form state—not a retrieved fact—is the decision-relevant signal. We show that for this regime a lightweight recency window plus a compact running summary is sufficient, with no external store or retriever.

#### Agentic context management and compaction.

The closest contemporary line of work studies context management for long-horizon agents directly. ACON (Kang and others, 2025) learns a failure-driven compression _guideline_ and distills it into a smaller compressor; concurrent work studies context management for long-horizon software-engineering agents (Liu et al., 2025); and provider platforms now ship native “compaction” and tool-result-clearing features (Anthropic, 2025). Our work is complementary and deliberately simpler: a fixed-recency eviction policy with optional single-pass summarization, evaluated end-to-end in a _live enterprise ERP_ with a hard, business-defined success criterion (zero residual), rather than on QA or coding benchmarks.

#### Tool-use benchmarks.

MCP-Bench (Wang and others, 2025) and related MCP agent benchmarks evaluate breadth of tool use across many servers and domains. Our study is narrower but deeper: a single high-stakes workflow with a strict completion criterion, measured for both task success _and_ cost (tokens, wall-clock), which surfaces the efficiency–accuracy trade-off that breadth-oriented benchmarks do not isolate.

Agentic reasoning frameworks such as ReAct (Yao et al., 2023) established the value of interleaving reasoning and action but do not prescribe a context policy for extended workflows with verbose tool responses—the gap this paper addresses.

Approach |  Unit |  Relation to this work  
---|---|---  
LLMLingua (Jiang et al., 2023), Sel. Context (Li et al., 2023) |  Token |  Compress within a prompt; risks corrupting form state  
MemoryBank (Zhong et al., 2024), LongMem (Wang et al., 2024) |  Memory |  External store for dialogue recall; not stale tool state  
ACON (Kang and others, 2025) |  Trajectory |  Learned compressor; we use fixed-recency ++ summary  
This work |  Tool pair |  Recency eviction ++ summary of evicted pairs  
Table 1: Positioning relative to prior context-management approaches. Our policy operates on whole tool call/response pairs (the semantic unit of an agentic workflow).

##  3 Methods

###  3.1 Task definition

The expense itemization task in D365 F&O requires an autonomous LLM agent to: (1) navigate to an existing expense report containing a receipt with a known total amount; (2) create individual line items corresponding to each purchased item; (3) assign the correct expense subcategory (e.g., room charge, city tax, resort fee, breakfast) to each line item; (4) enter the correct dollar amount; and (5) continue until the remaining unallocated amount equals exactly $0.00. The task is complete only when the remaining amount reaches zero. Any nonzero residual constitutes failure in production ERP workflows, preventing expense report finalization and triggering compliance review.

###  3.2 System architecture

The evaluation system consists of four components:

  * •

GPT-5 agent: The primary LLM (GPT-5) executing the autonomous itemization workflow, guided by a detailed agent system prompt covering the full itemization workflow, valid expense subcategories, and subcategory mappings.

  * •

User model (C2–C4 only): A secondary LLM (GPT-4.1) that participates in the agentic conversation as the “user”, responding to any follow-up questions or confirmation requests the GPT-5 agent raises during execution. Absent in C1.

  * •

D365 F&O MCP server: A Model Context Protocol proxy exposing D365 F&O form interactions as discrete tools (form navigation, field reading, field value setting, button clicking). The agent is exposed to a fixed inventory of tools covering UI-level form interaction, entity-level data access, and action invocation; a capability-level description is given in Appendix B.

  * •

Internal evaluation harness: A non-interactive orchestration framework managing agent-tool interaction loops, context engineering logic, and metric collection. No human is present during execution.




MCP tool responses from D365 F&O are verbose by design, containing full form state snapshots including field values, metadata, navigation breadcrumbs, and system state. A single tool response can contain 500–3,000 tokens, with full conversation history for a complex itemization task accumulating to 50,000–150,000+ tokens across 15–30 tool interactions.

###  3.3 Experimental configurations

We evaluated four configurations representing a progression from minimal to optimally engineered context management:

C1 — GPT-5, No User Model (Motivating Ablation): GPT-5 equipped with the full agent system prompt, which provides detailed step-by-step itemization workflow instructions, a complete list of valid D365 F&O expense subcategories, subcategory mapping rules (e.g., “Hotel Tax” →\rightarrow Room tax; “Room Service & Meals” →\rightarrow Room service), and explicit directives to continue itemizing without interruption until the remaining amount reaches zero. Despite these instructions, GPT-5 in practice occasionally departs from fully autonomous execution—pausing mid-task to ask clarifying questions or request confirmation before proceeding. Because the evaluation harness is a non-interactive framework with no human in the loop, these unanswered queries stall the agentic workflow entirely, resulting in incomplete tasks. C1 thus establishes a lower performance bound and, as we make explicit below, serves as a _motivating ablation_ for the user model rather than as a step in the context-engineering ladder.

C2 — GPT-5 + User Model (Full Context): To address the non-interactive framework limitation observed in C1, a user model (gpt-4.1) is introduced as a conversational participant. Rather than receiving a single static prompt, the GPT-5 agent can now ask questions mid-task and receive meaningful responses that keep the workflow moving. The user model is guided by a user_context that defines a strict completion protocol: the task is considered complete only when the expense line is saved, the itemization remaining amount is 0.00, _and_ the form is closed. The user model is further instructed to handle common agent queries—confirming that missing itemizations should be added, declining unnecessary receipt or expense report attachment requests, and prompting the agent to verify completion after each itemization pass. Full conversation history is retained throughout execution. This configuration represents standard agentic practice with the user model present and serves as the primary full-context baseline for the context-engineering comparison.

C3 — GPT-5 + User Model (Last 5 Tool Calls): Standard agent configuration with context pruned to retain only the 5 most recent tool call/response pairs. All earlier interactions are discarded without summarization. The selection of N=5N{=}5 was motivated by task structure analysis: a single itemization line requires 2–3 tool calls (creating the line via a form control, setting field values, and optionally verifying state). Five tool calls thus provide working memory for approximately two complete itemization cycles. We test the robustness of this choice in Section 4.7.

C4 — GPT-5 + User Model (Last 5 + Summarization, Window = 3): Standard agent configuration with context pruned to the last 5 tool call/response pairs, augmented with automated summarization of earlier conversation history. A summary window of 3 is applied, meaning the 3 most recent interactions prior to the pruning boundary inform the generated summary. The compact summary captures the forms opened, controls interacted with, buttons clicked, and data entered by the agent. This provides task-level situational awareness without the token cost of full history retention.

#### Isolating the effect of context engineering.

C1 differs from C2–C4 in _two_ respects at once—it removes both the user model and any context policy—so the C1→\toC2 jump alone cannot be attributed to context engineering. We therefore make the design explicit: the user model is held _constant and present_ across C2, C3, and C4, and all of our context-engineering claims rest on the C2 (full context) →\rightarrow C3 (pruning) →\rightarrow C4 (pruning ++ summarization) comparison, which varies _only_ the context policy. C1 is reported solely as a motivating ablation that quantifies why the user model is needed in a non-interactive harness for GPT-5. Notably, this necessity is model-specific: in our cross-model study (Section 4.9), Claude Sonnet 4.5 does not stall without the user model, so its C1 already reaches high completion—direct evidence that the large C1→\toC2 gap for GPT-5 reflects a model-specific stalling behavior, not the value of context engineering.

###  3.4 Context construction algorithm

Algorithm 1 specifies exactly how the retained context is constructed before each agent inference call. Let HH be the full message history, NN the number of recent tool call/response pairs to keep (the pruning window), and WW the summary window. The policy counts tool messages, evicts the oldest max⁡(0,#​tool−N)\max(0,\\#\text{tool}-N) of them _together with_ their preceding assistant tool-call message. When W≠0W\neq 0 and at least one pair is evicted, the policy summarizes the WW most recently evicted messages (or all evicted messages if W=−1W{=}{-1}) and re-inserts a single summary message at the earliest evicted position. C2 corresponds to N=∞N{=}\infty (no eviction); C3 to N=5,W=0N{=}5,W{=}0; C4 to N=5,W=3N{=}5,W{=}3. The summarization in C4 costs exactly one additional LLM call per eviction event.

Algorithm 1 ConstructContext

1: Input: history HH; keep window NN; summary window WW

2: c←c\leftarrow number of tool messages in HH

3: d←max⁡(0,c−N)d\leftarrow\max(0,\;c-N) {# pairs to evict} 

4: if d=0d=0 then

5: return HH

6: end if

7: K←[]K\leftarrow[\,]; E←[]E\leftarrow[\,]

8: for each message mm in HH (in order) do

9: if mm is a tool message and d>0d>0 then

10: d←d−1d\leftarrow d-1; append mm to EE

11: if last​(K)\mathrm{last}(K) is an assistant tool-call msg then

12: move last​(K)\mathrm{last}(K) from KK to EE

13: end if

14: else

15: append mm to KK

16: end if

17: end for

18: if W≠0W\neq 0 and E≠[]E\neq[\,] then

19: EW←EE_{W}\leftarrow E if W=−1W{=}{-}1, else last WW of EE

20: s←Summarize​(EW)s\leftarrow\textsc{Summarize}(E_{W})

21: insert “Summary of previous tool calls: ss” at earliest evicted position in KK

22: end if

23: return KK

###  3.5 Evaluation metrics

The following metrics were collected per configuration and averaged across 5 independent runs:

  * •

Completely Itemized: Percentage of tasks where remaining amount reached exactly $0.00 _(primary metric)_.

  * •

Less Than 10% Remaining: Percentage of tasks where ≤10%{\leq}10\% of total receipt amount remained unallocated.

  * •

At Least One Itemized: Percentage of tasks where at least one line item was successfully created.

  * •

Percentage Amount Itemized: Average percentage of total receipt amount correctly allocated across all tasks.

  * •

Total Token Usage: Total tokens (input + output) consumed across the 50-task benchmark.

  * •

Execution Time: Total wall-clock time to complete all 50 tasks.




Completely Itemized is designated the primary metric because it reflects genuine business task completion: in production ERP systems, any nonzero remaining amount prevents expense report finalization regardless of how much was correctly allocated. Metrics are computed by an independent read-back of the saved form state in D365 F&O (not from the agent’s self-report); the exact extraction and scoring logic, including the remaining_amount / itemized_amount comparison against the ground-truth PurchasedItems, is given in Appendix C.

###  3.6 Dataset

The benchmark consists of 50 hotel expense itemization tasks executed in D365 F&O via the MCP proxy. Hotel receipts represent an intentionally challenging evaluation domain: they frequently contain multiple line items sharing the same subcategory name but carrying different amounts (e.g., two “Hotel Tax” charges at different rates), non-trivial subcategory mappings to D365 F&O’s fixed vocabulary (a 23-entry subcategory catalog), and a strict zero-residual completion requirement. Tasks range from 4 to 23 itemization lines (median: 8), and the same 50-task benchmark was used identically across all four configurations to ensure fair comparison. Per-category dataset statistics and structural notes are given in Appendix E.

Each task is issued to the GPT-5 agent as a two-part prompt. The #Task section specifies the D365 F&O action (creating an expense line under TrvExpenseLines), and the #Data section provides a structured receipt payload—company, merchant, date, total, expense category, and a PurchasedItems list that serves as ground truth for evaluation. For C2–C4, the user model additionally receives a user_context defining the completion protocol (Section 3.3). Figure 1 shows a representative task drawn directly from the benchmark.

#Task: Create a new expense line in the USMF company under TrvExpenseLines in Dynamics 365 F&O. Add the itemizations listed in PurchasedItems under the itemize section properly. #Data: Company: USMF Merchant: Kimpton Syracuse University Hill Date: 2021-04-07 Total: $333.05 Category: Hotel PurchasedItems: Item Amount Daily Room Rate $138.10 Hotel Tax $06.82 Hotel Tax $010.23 Entertainment External $101.58 Room Service & Meals $076.32 Total $333.05

Figure 1: Representative task from the 50-task hotel expense benchmark. The agent must create five itemization lines in D365 F&O and achieve remaining = $0.00. Two challenge patterns are visible: (1) “Hotel Tax” appears twice with different amounts, and (2) items require subcategory mapping — “Entertainment External” →\rightarrow Business entertainment; “Room Service & Meals” →\rightarrow Room service.

These two patterns—repeated subcategory names with distinct amounts, and indirect item-to-subcategory mappings—are the primary sources of agent failure across the benchmark. An agent that skips the second “Hotel Tax” entry because it recognises the subcategory as already present leaves $10.23 unallocated; one that maps “Entertainment External” to the wrong subcategory introduces an incorrect line that cannot reconcile to zero.

###  3.7 Comparison baselines

Within the controlled C2–C4 comparison, C2 (full conversation history) serves as the standard-practice baseline and C3 (recency pruning without summarization) is the ablation that isolates the contribution of summarization. To situate our recency-plus-summarization policy against an alternative class of context-management strategy, we additionally evaluate a _full-history summarization_ policy that compacts _all_ evicted context without a fixed recency window—the compaction style of (Anthropic, 2025; Kang and others, 2025). This policy is reported in the sensitivity analysis (Section 4.7) as the W=−1W{=}{-}1 configuration. An orthogonal direction— _importance-pruning_ that retains the NN tool pairs most recently _referenced_ by the agent rather than the NN most recent in time—is discussed qualitatively in Section 6 as a candidate for future work.

##  4 Results

Table 2 presents performance and efficiency metrics for all four configurations. All values are averages across 5 independent experimental runs on the 50-task benchmark. Section 4.6 reports dispersion, confidence intervals, and effect-size analysis; Sections 4.7–4.9 report sensitivity, multi-category, and cross-model results; and Section 5 gives the failure taxonomy.

Configuration | Comp. |  <<10% |  ≥\geq1 | %Amt | Total | Input | Output | Time  
---|---|---|---|---|---|---|---|---  
Item. | Rem. | Item. | Item. | Tok.(K) | Tok.(K) | Tok.(K) | (hrs)  
C1: GPT-5 only (no user) | 8.0% | 37.2% | 99.6% | 58.89% | 532.6 | 531.3 | 1.3 | 3.08  
C2: GPT-5 + User (Full Context) | 71.0% | 74.0% | 100.0% | 92.03% | 1,481.0 | 1,478.5 | 2.5 | 14.56  
C3: GPT-5 + User (Last 5 TC) | 79.0% | 87.0% | 100.0% | 96.92% | 535.3 | 532.8 | 2.5 | 5.39  
C4: GPT-5 + User (Last 5 + Sum.) | 91.6% | 99.6% | 100.0% | 99.64% | 553.4 | 550.8 | 2.6 | 5.79  
Table 2: Performance and efficiency metrics across four GPT-5 context engineering configurations on the 50-task hotel expense benchmark, averaged across 5 independent runs. Comp. Item. = Completely Itemized (primary metric); <<10% Rem. = Less than 10% Remaining; ≥\geq1 Item. = At Least One Itemized; %Amt Item. = Percentage Amount Itemized; Total/Input/Output Tok. = token counts in thousands; Time = benchmark wall-clock time in hours. TC = tool calls; Sum. = Summarization. Bold indicates best performance per metric. Per-run dispersion and 95% CIs for the primary metric are in Table 3; full per-metric mean ±\pm SD across all categories and configurations is in Table 4.

Per-metric performance bar charts and token/time efficiency panels are visualized in Appendix Figures 2 and 3.

###  4.1 C1 (no user model): motivating the user model

C1 (no user model) achieved only 8.0% complete itemization and 58.89% average amount itemized, despite 99.6% of tasks having at least one line item created. This stark gap between at-least-one-itemized (99.6%) and completely-itemized (8.0%) reveals that GPT-5 can initiate itemization actions from MCP tool descriptions and the agent prompt, but in the non-interactive harness it does not reliably drive the workflow to completion without a user-model participant to answer follow-up questions and reinforce the completion protocol. Agents frequently terminate after creating one or two line items, uncertain of the next required action or stopping condition. Token usage (532,600 total; 1,331 output) reflects abbreviated task executions resulting from early termination. As emphasized in Section 3.3, C1 removes both the user model and any context policy and is therefore reported only as motivation; the context-engineering claims below rest on C2–C4.

###  4.2 Full context: performance gains with severe efficiency cost

Adding the user model with full task instructions and complete conversation history (C2) dramatically improved performance: complete itemization rose to 71.0% and average amount itemized to 92.03%. The at-least-one-itemized rate reached 100%, confirming that task instructions reliably orient the agent.

However, full-context retention introduced severe efficiency costs. Total tokens increased to 1,480,996—a 177.9% increase over baseline—driven almost entirely by input tokens (1,478,509), reflecting the cumulative growth of conversation history as verbose tool responses accumulate. Execution time rose to 14.56 hours for the 50-task benchmark (4.73×\times the baseline), making this configuration impractical for production deployment at scale. The input-to-output token ratio of 594.7:1 confirms that context management strategies targeting input reduction will yield the greatest efficiency gains.

###  4.3 Context pruning: simultaneous performance and efficiency improvement

Pruning context to the last 5 tool call/response pairs (C3) simultaneously improved both performance and efficiency relative to full context. Complete itemization rose to 79.0%—an 8 percentage-point absolute improvement over C2 (11.3% relative)—and average amount itemized improved to 96.92%.

Total tokens dropped to 535,274—a 63.9% reduction from full context, essentially equivalent to the baseline token budget—while execution time fell to 5.39 hours (63.0% reduction from C2). The finding that context-pruned configurations outperform full-context retention on _both_ performance and efficiency is counterintuitive but interpretable: older tool interactions describe superseded form states. Retaining stale form state introduces noise that degrades the agent’s understanding of current system state, leading to incorrect field assignments or navigation errors. Restricting context to the last 5 tool calls directs agent attention to the current form state and recent actions—the information most relevant to the next decision.

Output tokens (2,515) are substantially higher than the baseline (1,331), reflecting more complete task execution and richer agent reasoning when clear task context is provided.

###  4.4 Summarization: best performance with marginal token overhead

Configuration C4 (last 5 tool calls + summarization, window = 3) achieved the best performance across all metrics: 91.6% complete itemization, 99.6% less-than-10%-remaining, 100.0% at-least-one-itemized, and 99.64% average amount itemized. This represents a 12.6 percentage-point improvement over context pruning alone (79.0%) and a 20.6 percentage-point improvement over full context (71.0%).

Total tokens (553,374) increased only 3.4% over C3 (535,274), while execution time increased marginally to 5.79 hours (+7.4% over C3). The compact summary of earlier task progress adds minimal overhead while preserving the situational awareness the agent needs: which forms have been opened, which controls were interacted with, and what data was entered into the expense report. By condensing this history into a short assistant message, the agent retains awareness of prior actions even after their full tool-response payloads have been pruned—reducing the premature-termination failures observed in C3 without re-introducing the verbose form snapshots that drive stale-state errors in C2.

The near-perfect less-than-10%-remaining rate (99.6%) is particularly notable: summarization virtually eliminates cases of substantial task abandonment. Only one task in 50 exceeded 10% remaining, compared to six tasks (13%) in C3 and thirteen tasks (26%) in C2.

###  4.5 Token efficiency analysis

Across all configurations, input tokens represent 99.75%–99.87% of total token usage, confirming that context management strategies targeting input reduction yield the greatest efficiency gains. Output tokens remain relatively stable across C2–C4 (2,486–2,567), indicating consistent reasoning depth regardless of context management approach.

Full-context C2 consumes 2.68×\times the tokens of the best-performing C4 while achieving lower task completion—demonstrating that more context does not necessarily improve performance in tool-heavy agentic workflows. C3 and C4 achieve comparable token budgets to the baseline (535K–553K vs. 533K) while improving complete itemization by 71–83 percentage points.

###  4.6 Statistical analysis

We treat each task outcome on the primary metric as a Bernoulli trial and report dispersion in two complementary ways (full methodology in Appendix D). First, treating each of the 5 runs as one observation of the benchmark-level success rate, we report the mean and sample standard deviation across runs and a 95% confidence interval using Student’s tt with 4 degrees of freedom (t0.975,4=2.776t_{0.975,4}=2.776). Second, pooling all 50×5=25050\times 5=250 task-runs, we report a Wilson score interval for the binomial proportion, which—unlike the normal (Wald) approximation—remains valid for the near-boundary rates observed here (e.g., 8% and 91.6%).

Table 3 reports both for the primary metric.

Config | Mean ±\pm SD (5 runs) | Wilson 95% CI  
---|---|---  
C2 | 71.0±4.471.0\pm 4.4 | [ 65.1, 76.3][\,65.1,\ 76.3\,]  
C3 | 79.0±8.279.0\pm 8.2 | [ 73.5, 83.6][\,73.5,\ 83.6\,]  
C4 | 91.6±1.791.6\pm 1.7 | [ 87.5, 94.4][\,87.5,\ 94.4\,]  
Table 3: Primary metric (Completely Itemized, %) with run-level mean±\pmSD and pooled Wilson 95% confidence intervals.

The Wilson interval for C4 is cleanly separated from C3 ([87.5,94.4][87.5,94.4] vs. [73.5,83.6][73.5,83.6]), giving strong pooled-trial evidence that summarization improves over pruning alone. The C2 and C3 intervals ([65.1,76.3][65.1,76.3] vs. [73.5,83.6][73.5,83.6]) overlap slightly, so the pooled-binomial lens alone is conservative on this step; the +8-point gap in run-level means together with the run-level dispersion below nonetheless points consistently in the same direction. C2’s full-context runs are moderately variable (±4.4\pm 4.4), C3 shows the widest spread under aggressive pruning (±8.2\pm 8.2), and C4’s pruning+summarization is by far the most stable (±1.7\pm 1.7)—consistent with summarization absorbing the variance that pruning alone exposes.

#### Effect sizes vs. noise.

Because the same 50 tasks are used in every configuration, comparisons are naturally paired. We do not rely on a paired hypothesis test here: the effect sizes (71.0% →\to 79.0% →\to 91.6%, i.e. +8 and +12.6 percentage points) are large relative to the per-run dispersion in Table 3, and the C3→\toC4 Wilson intervals are cleanly separated on the pooled 250 task-runs. Together these make it unlikely that the headline ordering is attributable to run-to-run noise.

###  4.7 Sensitivity to the pruning window NN and summary window WW

A central question is whether the headline result depends on the specific choices N=5N{=}5 and W=3W{=}3. Appendix H reports a hyperparameter sweep over NN and WW; results plateau beyond N=5N{=}5 and show no accuracy gain for W>3W{>}3 at non-trivial token cost, supporting the chosen operating point.

###  4.8 Generalization across expense categories

To test whether the policy generalizes beyond hotel receipts, we replicate the full C1/C2/C3/C4 comparison on two additional grouped D365 F&O expense categories that differ in structural complexity: _Travel_ (car rental + flight; transportation receipts with base fare, taxes/fees, and ancillary charges) and _Meals & Gifts_ (business meal + gift; discretionary social-spend receipts with simpler line-item structure). Hotel remains the most structurally complex category (room + nightly taxes + resort fees + incidentals). Table 4 reports all performance and efficiency metrics across all four configurations for each grouped category, ordered by structural complexity.

|  |  | Quality (mean ±\pm SD) | Efficiency (mean)  
---|---|---|---|---  
Category | Configuration | 𝒏\boldsymbol{n} | Comp. |  <<10% |  ≥\geq1 | %Amt | Total | Input | Output | Time  
Item. | Rem. | Item. | Item. | Tok.(K) | Tok.(K) | Tok.(K) | (hrs)  
Hotel | C1: GPT-5 only (no user) | 50 |  8.0 ±\pm 2.5 |  37.2 ±\pm 8.4 |  99.6 ±\pm 0.9 |  58.89 ±\pm 3.0 | 532.6 | 531.3 | 1.3 | 3.08  
C2: GPT-5 + User (Full Context) |  71.0 ±\pm 4.4 |  74.0 ±\pm 3.7 |  100.0 ±\pm 0.0 |  92.03 ±\pm 1.1 | 1,481.0 | 1,478.5 | 2.5 | 14.56  
C3: GPT-5 + User (Last 5 TC) |  79.0 ±\pm 8.2 |  87.0 ±\pm 6.1 |  100.0 ±\pm 0.0 |  96.92 ±\pm 1.5 | 535.3 | 532.8 | 2.5 | 5.39  
C4: GPT-5 + User (Last 5 + Sum.) |  91.6 ±\pm 1.7 |  99.6 ±\pm 0.9 |  100.0 ±\pm 0.0 |  99.64 ±\pm 0.1 | 553.4 | 550.8 | 2.6 | 5.79  
Travel | C1: GPT-5 only (no user) | 30 |  20.0 ±\pm 14.3 |  30.7 ±\pm 9.5 |  50.7 ±\pm 9.2 |  45.67 ±\pm 7.8 | 390.0 | 388.8 | 1.2 | 0.71  
C2: GPT-5 + User (Full Context) |  76.0 ±\pm 7.6 |  93.3 ±\pm 4.1 |  100.0 ±\pm 0.0 |  97.49 ±\pm 1.3 | 1,050.0 | 1,047.8 | 2.2 | 4.42  
C3: GPT-5 + User (Last 5 TC) |  86.6 ±\pm 7.0 |  94.0 ±\pm 4.3 |  100.0 ±\pm 0.0 |  98.62 ±\pm 1.0 | 367.0 | 365.4 | 1.6 | 1.63  
C4: GPT-5 + User (Last 5 + Sum.) |  95.0 ±\pm 1.9 |  98.3 ±\pm 1.6 |  100.0 ±\pm 0.0 |  99.53 ±\pm 0.3 | 403.0 | 401.5 | 1.5 | 1.75  
Meals & Gifts | C1: GPT-5 only (no user) | 32 |  26.9 ±\pm 15.1 |  40.6 ±\pm 13.9 |  50.6 ±\pm 11.9 |  47.57 ±\pm 12.9 | 280.0 | 279.0 | 1.0 | 1.67  
C2: GPT-5 + User (Full Context) |  75.6 ±\pm 6.8 |  95.0 ±\pm 2.8 |  100.0 ±\pm 0.0 |  97.70 ±\pm 0.7 | 750.0 | 748.0 | 2.0 | 3.32  
C3: GPT-5 + User (Last 5 TC) |  89.4 ±\pm 6.4 |  95.0 ±\pm 5.6 |  100.0 ±\pm 0.0 |  98.90 ±\pm 0.7 | 285.0 | 283.5 | 1.5 | 1.23  
C4: GPT-5 + User (Last 5 + Sum.) |  96.1 ±\pm 1.4 |  99.2 ±\pm 1.3 |  100.0 ±\pm 0.0 |  99.67 ±\pm 0.2 | 295.0 | 293.5 | 1.5 | 1.42  
  
Table 4: Run-level results across 5 independent runs for three grouped D365 F&O expense categories. _Travel_ pools car rental and flight receipts (n=30n=30); _Meals & Gifts_ pools business meal and gift receipts (n=32n=32); Hotel remains the standalone primary benchmark (n=50n=50). Categories are ordered by structural complexity (Hotel >> Travel >> Meals & Gifts). For the four quality metrics (all reported in %) we report mean ±\pm standard deviation across the 5 runs; for the four efficiency metrics—input/output/total tokens in thousands (K) and wall-clock time in hours—we report the mean only, as run-to-run variance on these is negligible. Hotel means reproduce Table 2; SDs and all non-Hotel cells are computed from the per-run JSONL result files. Column definitions follow Table 2.

The C1→\toC2→\toC3→\toC4 ordering predicted by our context-engineering hypothesis holds in every category. Complete itemization rises monotonically across configurations in all three settings, with the C2→\toC4 improvement remarkably consistent across categories (Hotel: 71.0→91.671.0\to 91.6, +20.6+20.6 pts; Travel: 76.0→95.076.0\to 95.0, +19.0+19.0 pts; Meals & Gifts: 75.6→96.175.6\to 96.1, +20.5+20.5 pts). The efficiency story is similarly stable: pruning-plus-summarization reduces total tokens by 60–63% relative to full context and cuts wall-clock time by 57–60% across all three categories. As predicted by the structural gradient (Appendix E), the magnitude of the C1→\toC2 gap shrinks with receipt complexity—from +63.0+63.0 pts on Hotel to +56.0+56.0 pts on Travel and +48.7+48.7 pts on Meals & Gifts—because simpler receipts give the no-user-model agent fewer opportunities to stall, but the context-engineering ordering above C2 is preserved. These results indicate that the policy is not specific to multi-night hotel itemization but generalizes to the broader class of D365 F&O expense workflows with verbose MCP tool responses.

###  4.9 Cross-model generalization: Claude Sonnet 4.5

To test whether the policy is model-agnostic, we repeat the comparison with Claude Sonnet 4.5 as the agent on the 50-task hotel benchmark; full results are in Appendix I. Two findings stand out. First, Sonnet 4.5 does _not_ stall in the non-interactive harness, so its no-context-engineering baseline already reaches 88.0% complete itemization—in sharp contrast to GPT-5’s 8.0%. This supports our claim (Section 3.3) that the large GPT-5 C1→\toC2 gap reflects a model-specific stalling behavior rather than the value of context engineering. Second, the context-engineering ordering still holds: adding summarization on top of pruning improves complete itemization from 92.0% to 94.5% at a ∼\sim5.6% wall-clock premium, mirroring the small time overhead observed for GPT-5 (+7.4%+7.4\%).

##  5 Failure analysis

We categorized every non-completing task across the C2–C4 runs on the 50-task hotel benchmark into one of six failure modes, derived from the tool-call error logs and the read-back discrepancy between the saved form state and the ground-truth PurchasedItems (Appendix C). Representative transcripts for each mode are in Appendix F.

Failure mode | C2 | C3 | C4  
---|---|---|---  
Stale-state reference | 34 | 6 | 4  
Wrong subcategory mapping | 8 | 9 | 6  
Duplicate / skipped repeat item | 12 | 11 | 5  
Premature termination | 9 | 18 | 3  
Tool / form navigation error | 6 | 5 | 2  
Residual amount mismatch | 4 | 4 | 1  
Total non-completions | 73 | 53 | 21  
Table 5: Failure modes by configuration (count of task-runs, pooled over 5 runs on the 50-task hotel benchmark).

The taxonomy makes distinct predictions: C2 should over-represent _stale-state references_ (the agent acts on a superseded form snapshot); C3 should reduce stale-state errors but introduce _premature termination_ (the running balance is no longer visible); and C4 should suppress premature termination by reinjecting a condensed history. Table 5 confirms both predictions: stale-state references drop from 34/73 (47%) under C2 to 6/53 (11%) under C3, while premature termination triples (9→\to18) and becomes C3’s dominant mode; C4 cuts premature termination six-fold (18→\to3) without re-introducing stale-state errors, yielding a 71% overall reduction in non-completions (73→\to21). The remaining modes—wrong subcategory mapping, duplicate or skipped repeats, tool/form navigation errors, and residual mismatches—are largely policy-invariant and reflect model-level reasoning and tool-binding errors that context engineering does not directly target; wrong subcategory mapping in particular is amplified by the 23-entry hotel subcategory catalog (Appendix E), where near-synonyms such as Room tax vs. Non-Room tax and Restaurant vs. Room service vs. Loungebar create genuine label ambiguity independent of the context policy. These residual modes bound the headroom for recency- and summarization-based policies and motivate the complementary techniques discussed in Section 6.

##  6 Discussion

###  6.1 Summary of findings

This study demonstrates that context engineering—selective retention of recent tool interactions combined with automated summarization—substantially improves both performance and efficiency for GPT-5 agents in long-context agentic workflows with verbose tool responses. On the 50-task hotel expense benchmark averaged across 5 runs, C4 (last-5-tool-calls pruning + summarization) achieved 91.6% complete itemization and 99.64% average amount itemized, compared to 71.0% and 92.03% with full-context retention (C2), while consuming 62.7% fewer tokens and completing the benchmark in 60.2% less time.

Holding the user model constant across C2–C4, the comparison isolates the context policy: (i) recency pruning provides noise reduction and efficiency gains (C2→\toC3: +8+8 pp and −64%-64\% tokens); and (ii) summarization provides residual task-level awareness for near-complete performance (C3→\toC4: +12.6+12.6 pp at <4%<4\% token overhead). C1 is reported only to quantify why the user model is needed for GPT-5 in a non-interactive harness, a need that is model-specific (Section 4.9).

###  6.2 Why context pruning outperforms full history retention

The finding that context-pruned configurations outperform full-context retention on both performance and efficiency reveals an important characteristic of LLM agents in tool-heavy workflows: older context can be actively detrimental rather than merely redundant. In D365 F&O expense itemization, early tool responses describe form states superseded as the workflow progresses. An agent retaining full history may reference stale form values when making current decisions, leading to incorrect field assignments or erroneous navigation. The failure taxonomy (Section 5) is designed to test this mechanism directly via the relative frequency of stale-state errors.

Restricting context to the last 5 tool calls ensures agent attention is focused on current form state and recent actions—the information required for the next decision. This aligns with the task’s working memory requirements: the agent needs to know what was just done, whether it succeeded, and the current remaining balance. Five tool calls provide this working memory for approximately two complete itemization cycles, covering the immediate task horizon without accumulating irrelevant historical state.

###  6.3 Complementary role of summarization

The performance gap between C3 (79.0%) and C4 (91.6%) reveals a complementary role for summarization that addresses the limitation of pure context pruning. While pruning provides noise reduction and recent-state focus, it can cause agents to lose task-level awareness: how many items have been successfully itemized, what the total allocated amount is, and whether overall reconciliation is near completion. Without this awareness, agents in C3 occasionally exhibit premature termination.

The automated summarization in C4, using a window of 3 prior interactions to generate a compact progress report, bridges this gap at minimal token cost (+3.4% over C3). The summary provides two complementary information channels: recent tool calls supply current local state, while the summary supplies global task progress. Together, they provide everything needed for reliable task completion.

###  6.4 Limitations and future work

The core study focuses on hotel expense itemization in D365 F&O—an intentionally challenging tool-use workflow with repeated subcategories, non-trivial mappings, and a strict zero-residual completion criterion—and we extend it with multi-category coverage across five expense types grouped into three structurally distinct categories and cross-model evidence on Claude Sonnet 4.5. Within this scope, the (N=5,W=3)(N{=}5,\,W{=}3) operating point was selected for clarity of comparison; the sensitivity sweep in Appendix H confirms robustness across nearby values of NN and WW, and joint tuning and adaptive (per-task) window sizing are natural next steps. Our summarizer is a single free-form LLM pass, which establishes a clean baseline against which structured or learned compressors (Kang and others, 2025) and provider-native compaction APIs (Anthropic, 2025) can be benchmarked head-to-head. Broader generalization—to additional ERP domains beyond expense management, and across further model families, deployments, and decoding settings—constitutes a promising line of follow-up work. Production-deployment economics and the precise scope of our generalizability claims are discussed further in Appendix J.

###  6.5 Responsible AI considerations

Context engineering improves task reliability from 8.0% to 91.6% complete itemization; the residual 8.4% incomplete rate means production deployments should retain human review for flagged cases. The approach is interpretable by construction—explicitly retained tool calls and human-readable summaries support debugging and auditing—and this work uses synthetic test cases and anonymized internal test data, so no privacy exposure is incurred.

## References

  * Anthropic (2025) Effective context engineering for AI agents.  Note: <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents> Cited by: §1, §2, §3.7, §6.4. 
  * T. B. Brown, B. Mann, N. Ryder, M. Subbiah, J. D. Kaplan, P. Dhariwal, A. Neelakantan, P. Shyam, G. Sastry, A. Askell, S. Agarwal, A. Herbert-Voss, G. Krueger, T. Henighan, R. Child, A. Ramesh, D. M. Ziegler, J. Wu, C. Winter, C. Hesse, M. Chen, E. Sigler, M. Litwin, S. Gray, B. Chess, J. Clark, C. Berner, S. McCandlish, A. Radford, I. Sutskever, and D. Amodei (2020) Language models are few-shot learners.  Advances in Neural Information Processing Systems 33,  pp. 1877–1901.  Cited by: §1. 
  * H. Jiang, Q. Wu, C.-Y. Lin, Y. Yang, and L. Qiu (2023) LLMLingua: compressing prompts for accelerated inference of large language models.  arXiv preprint arXiv:2310.05736.  Cited by: §1, §2, Table 1. 
  * M. Kang et al. (2025) ACON: optimizing context compression for long-horizon LLM agents.  arXiv preprint arXiv:2510.00615.  Cited by: §2, Table 1, §3.7, §6.4. 
  * Y. Li, Y. Zhang, and L. Sun (2023) Selective context: on-demand context compression for long-context language models.  arXiv preprint arXiv:2304.12102.  Cited by: §1, §2, Table 1. 
  * S. Liu, J. Yang, B. Jiang, Y. Li, J. Guo, X. Liu, and B. Dai (2025) Context as a tool: context management for long-horizon SWE-agents.  arXiv preprint arXiv:2512.22087.  Cited by: §2. 
  * A. Maharana, D.-H. Lee, S. Tulyakov, M. Bansal, F. Barbieri, and Y. Fung (2024) Evaluating very long-term conversational memory of LLM agents.  arXiv preprint arXiv:2402.17753.  Cited by: §2. 
  * Y. Wang, Y. Dong, D. Zeng, Z. Li, and M. Sun (2024) LongMem: augmenting large language models with memory mechanism for long-context understanding.  arXiv preprint arXiv:2407.01917.  Cited by: §2, Table 1. 
  * Z. Wang et al. (2025) MCP-Bench: benchmarking tool-using LLM agents with complex real-world tasks via MCP servers.  arXiv preprint arXiv:2508.20453.  Cited by: §2. 
  * D. Wu, H. Wang, W. Yu, Y. Zhang, K.-W. Chang, and D. Yu (2025) LongMemEval: benchmarking chat assistants on long-term interactive memory.  arXiv preprint arXiv:2410.10813.  Cited by: §2. 
  * S. Yao, J. Zhao, D. Yu, N. Du, I. Shafran, K. Narasimhan, and Y. Cao (2023) ReAct: synergizing reasoning and acting in language models.  In Proceedings of the International Conference on Learning Representations (ICLR),  Cited by: §2. 
  * W. Zhong, L. Guo, Q. Gao, H. Ye, and Y. Wang (2024) MemoryBank: enhancing large language models with long-term memory.  In Proceedings of the AAAI Conference on Artificial Intelligence,  Cited by: §2, Table 1. 



Appendix

##  Appendix A Reproducibility overview

This appendix collects the following artifacts: the tool inventory (B), the metric-computation/scoring logic (C), the statistical methodology with a runnable helper (D), per-category dataset statistics (E), and qualitative failure and summarization examples (F), performance and efficiency figures (G), sensitivity analysis for the pruning window NN and summary window WW (H), cross-model generalization results on Claude Sonnet 4.5 (I), and an extended discussion of efficiency and generalizability (J).

##  Appendix B Tool inventory

The agent is exposed to 21 D365 F&O MCP tools, organized into three categories by capability: (i)  _form tools_ (13), providing UI-level interaction with the F&O client—form and tab navigation, menu-item and control discovery, reading and setting control values, opening lookups, grid filtering, sorting and row selection, clicking controls, and saving forms; (ii)  _data tools_ (6), providing entity-level OData access—entity-type discovery, metadata retrieval, and find/create/update/delete operations against F&O entities; and (iii)  _API tools_ (2), used to discover and invoke custom server-side action menu items.

##  Appendix C Metric computation and scoring

Metrics are computed by an independent read-back: after the itemization run, the saved expense line in D365 F&O is read and reduced to four values— total_amount, itemized_amount, remaining_amount, and num_itemized—which are compared against the ground-truth PurchasedItems total. The per-task metrics are then:

| CompletelyItemized | =𝟙​[remaining_amount=0.00]\displaystyle=\mathds{1}[\,\texttt{remaining\\_amount}=0.00\,] |   
---|---|---|---  
| LessThan10% | =𝟙​[remaining_amounttotal_amount≤0.1]\displaystyle=\mathds{1}\\!\left[\tfrac{\texttt{remaining\\_amount}}{\texttt{total\\_amount}}\leq 0.1\right] |   
| AtLeastOne | =𝟙​[num_itemized>0]\displaystyle=\mathds{1}[\,\texttt{num\\_itemized}>0\,] |   
| %AmountItemized | =100⋅itemized_amounttotal_amount\displaystyle=100\cdot\tfrac{\texttt{itemized\\_amount}}{\texttt{total\\_amount}} |   
  
Amounts are normalized (currency symbols/commas stripped, cast to float) before comparison. Benchmark-level numbers are the mean of the per-task values over the 50 tasks, averaged again over the 5 runs. Token totals sum agent and user-model usage; execution time is the run wall-clock.

##  Appendix D Statistical methodology

#### Run-level interval.

For each configuration let p1,…,p5p_{1},\dots,p_{5} be the per-run success rates on a binary metric. Report p¯=15​∑ipi\bar{p}=\frac{1}{5}\sum_{i}p_{i} and s=14​∑i(pi−p¯)2s=\sqrt{\frac{1}{4}\sum_{i}(p_{i}-\bar{p})^{2}}, with 95% CI p¯±t0.975,4​s5\bar{p}\pm t_{0.975,4}\,\frac{s}{\sqrt{5}}, t0.975,4=2.776t_{0.975,4}=2.776.

#### Pooled binomial (Wilson) interval.

Pooling n=250n=250 task-runs with p^\hat{p} successes, the Wilson score interval (preferred over Wald near 0/1) is

| p^+z22​n±z​p^​(1−p^)n+z24​n21+z2n,z=1.96.\frac{\hat{p}+\frac{z^{2}}{2n}\pm z\sqrt{\frac{\hat{p}(1-\hat{p})}{n}+\frac{z^{2}}{4n^{2}}}}{1+\frac{z^{2}}{n}},\quad z=1.96. |   
---|---|---  
  
#### Paired comparisons.

Because the same 50 tasks are used in every configuration, comparisons are naturally paired. We do not rely on a hypothesis-test pp-value: the headline-metric effect sizes (+8 and +12.6 percentage points) are large relative to the per-run SDs in Table 3, and the C3→\toC4 Wilson intervals are non-overlapping. We report the run-level tt-interval and the pooled Wilson interval as the two primary inferential statistics.

#### Helper.

The following computes every value in Table 3 from the per-run JSONL result files.

[⬇](data:text/plain;base64,aW1wb3J0IGpzb24sIG1hdGgKZnJvbSBzdGF0aXN0aWNzIGltcG9ydCBtZWFuLCBzdGRldgoKZGVmIHBlcl9ydW5fcmF0ZXMocnVuX2ZpbGVzLCBrZXk9ImNvbXBsZXRlbHlfb3B0aW1pemVkIik6CiAgICByYXRlcyA9IFtdCiAgICBmb3IgZiBpbiBydW5fZmlsZXM6ICAgICAgICAgICAgICAgICAgICAgICAjIG9uZSBKU09OTCBwZXIgcnVuCiAgICAgICAgeXMgPSBbanNvbi5sb2FkcyhsKVtrZXldIGZvciBsIGluIG9wZW4oZikgaWYgbC5zdHJpcCgpXQogICAgICAgIHJhdGVzLmFwcGVuZCgxMDAqc3VtKHlzKS9sZW4oeXMpKQogICAgcmV0dXJuIHJhdGVzCgpkZWYgdF9pbnRlcnZhbChyYXRlcyk6ICAgICAgICAgICAgICAgICAgICAgICAgICMgcnVuLWxldmVsIDk1JSBDSQogICAgbSwgcywgbiA9IG1lYW4ocmF0ZXMpLCBzdGRldihyYXRlcyksIGxlbihyYXRlcykKICAgIGggPSAyLjc3NiAqIHMvbWF0aC5zcXJ0KG4pICAgICAgICAgICAgICAgICAjIHRfey45NzUsNH09Mi43NzYgZm9yIG49NQogICAgcmV0dXJuIG0sIHMsIChtLWgsIG0raCkKCmRlZiB3aWxzb24oc3VjY2Vzc2VzLCBuLCB6PTEuOTYpOiAgICAgICAgICAgICAgIyBwb29sZWQgYmlub21pYWwgQ0kKICAgIHAgPSBzdWNjZXNzZXMvbgogICAgZCA9IDEgKyB6KnovbgogICAgYyA9IHAgKyB6KnovKDIqbikKICAgIGhhbGYgPSB6Km1hdGguc3FydChwKigxLXApL24gKyB6KnovKDQqbipuKSkKICAgIHJldHVybiAoMTAwKihjLWhhbGYpL2QsIDEwMCooYytoYWxmKS9kKQ==)

import json, math

from statistics import mean, stdev

def per_run_rates(run_files, key="completely_optimized"):

rates = []

for f in run_files: # one JSONL per run

ys = [json.loads(l)[key] for l in open(f) if l.strip()]

rates.append(100*sum(ys)/len(ys))

return rates

def t_interval(rates): # run-level 95% CI

m, s, n = mean(rates), stdev(rates), len(rates)

h = 2.776 * s/math.sqrt(n) # t_{.975,4}=2.776 for n=5

return m, s, (m-h, m+h)

def wilson(successes, n, z=1.96): # pooled binomial CI

p = successes/n

d = 1 + z*z/n

c = p + z*z/(2*n)

half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))

return (100*(c-half)/d, 100*(c+half)/d)

#### Full per-metric dispersion across categories.

The mega per-metric mean ±\pm SD table covering all three grouped categories and all four configurations is reported in the main paper as Table 4; the helper above is the script used to compute SDs and the non-Hotel cells from the per-run JSONL files.

##  Appendix E Per-category dataset statistics

Category | nn | Median | Range | F&O | Repeat  
---|---|---|---|---|---  
|  | lines | (min–max) | subcats | subcats?  
Hotel | 50 | 8 | 4–23 | 23 | Yes (nightly)  
Car rental | 15 | 3 | 2–5 | 10 | Rare  
Flight | 15 | 3 | 2–6 | 4 | Rare  
Business meal | 20 | 2 | 1–4 | 3 | No  
Gift | 12 | 2 | 1–3 | 4 | No  
Table 6: Per-category dataset characteristics. The F&O subcats column reports the number of valid expense subcategories the agent must choose among in the D365 F&O catalog for that category. Hotel is by far the most structurally complex: a 23-entry subcategory catalog (with near-synonyms such as Room tax vs. Non-Room tax, Restaurant vs. Room service vs. Loungebar, Gift shop vs. Gift certificates) combined with multi-night receipts that repeat the same subcategory per night. Travel (car rental: 10, flight: 4) and Meals & Gifts (3 and 4) have much smaller catalogs and rarely repeat subcategories, which is why GPT-5 with no user model achieves higher CIR on those categories (∼\sim27–40%) than on hotel (8%). This structural gradient—Hotel >> Travel >> Meals & Gifts—motivates our choice of hotel as the primary benchmark.

#### Structural notes.

  * •

Hotel receipts span multi-night stays with per-night charges (room, tax, resort fee, parking, breakfast). The same subcategory recurs nn times for an nn-night stay, which is what makes line-by-line itemization hard: the agent must track _which night_ each entry corresponds to and avoid duplicate/skipped repeats.

  * •

Car rental receipts have a single primary line (daily rate ×\times days) plus optional add-ons (insurance, fuel, GPS). Repeated subcategories are rare because totals are typically pre-aggregated by the rental agency.

  * •

Flight receipts contain a base fare, taxes/fees, and optional seat/baggage upgrades—structurally flat, no repeats.

  * •

Business meal and Gift receipts are the simplest: typically 1–3 line items, single subcategory each, no repeats.




##  Appendix F Qualitative failure and summarization examples

We provide one short trimmed transcript per failure mode from Table 5, followed by one summarization string emitted by the C4 summarizer. Speaker labels: A = agent, T = tool response (truncated to the relevant fragment).

#### (1) Stale-state reference (C2).

[⬇](data:text/plain;base64,QTogZ2V0X2Zvcm1fc3RhdGUoKQpUOiB7bGluZXM6IFt7Um9vbSwgJDE4MH1dLCB0b3RhbF9hZGRlZDogJDE4MCwgcmVtYWluaW5nOiAkNDIwfQpBOiBhZGRfbGluZShSb29tVGF4LCAkNDApClQ6IHtvaywgbGluZV9pZDogN30KQTogZ2V0X2Zvcm1fc3RhdGUoKQpUOiB7bGluZXM6IFt7Um9vbSwgJDE4MH0se1Jvb21UYXgsICQ0MH1dLCB0b3RhbF9hZGRlZDogJDIyMCwgcmVtYWluaW5nOiAkMzgwfQouLi4gKDUgbW9yZSB0b29sIGNhbGxzKSAuLi4KQTogIyByZWZlcmVuY2VzIHRoZSBGSVJTVCBzbmFwc2hvdApBOiBhZGRfbGluZShSb29tLCAkMTgwKSAgICMgZHVwbGljYXRlIC0tIGZvcm0gYWxyZWFkeSBoYXMgaXQKVDoge29rLCBsaW5lX2lkOiAxMn0KQTogc3VibWl0X2Zvcm0oKQo9PiBSZXNpZHVhbDogLSQxODAgKG92ZXJzaG9vdCwgZHVwbGljYXRlIFJvb20gbGluZSk=)

A: get_form_state()

T: {lines: [{Room, $180}], total_added: $180, remaining: $420}

A: add_line(RoomTax, $40)

T: {ok, line_id: 7}

A: get_form_state()

T: {lines: [{Room, $180},{RoomTax, $40}], total_added: $220, remaining: $380}

... (5 more tool calls) ...

A: # references the FIRST snapshot

A: add_line(Room, $180) # duplicate \-- form already has it

T: {ok, line_id: 12}

A: submit_form()

=> Residual: -$180 (overshoot, duplicate Room line)

#### (2) Wrong subcategory mapping (C3).

[⬇](data:text/plain;base64,QTogIyByZWNlaXB0IGxpbmUgIlJvb20gc2VydmljZSAtIGJyZWFrZmFzdCAkMjgiCkE6IGFkZF9saW5lKGNhdGVnb3J5PU1lYWxzLUNsaWVudCwgYW1vdW50PTI4KQpUOiB7b2t9Cj0+IEdyb3VuZCB0cnV0aDogSG90ZWwtQnJlYWtmYXN0LiBNaXNjbGFzc2lmaWVkLg==)

A: # receipt line "Room service - breakfast $28"

A: add_line(category=Meals-Client, amount=28)

T: {ok}

=> Ground truth: Hotel-Breakfast. Misclassified.

#### (3) Duplicate / skipped repeat item (C2).

[⬇](data:text/plain;base64,QTogIyAzLW5pZ2h0IHN0YXksIHJlY2VpcHQgc2hvd3MgUm9vbSAkMTgwIHggMwpBOiBhZGRfbGluZShSb29tLCAkMTgwKSAgICMgbmlnaHQgMQpBOiBhZGRfbGluZShSb29tLCAkMTgwKSAgICMgbmlnaHQgMgpBOiBzdWJtaXRfZm9ybSgpICAgICAgICAgICAjIHNraXBwZWQgbmlnaHQgMwo9PiBSZXNpZHVhbDogJDE4MCB1bmFjY291bnRlZCAoMSBvZiAzIHJvb20gbmlnaHRzIG1pc3Npbmcp)

A: # 3-night stay, receipt shows Room $180 x 3

A: add_line(Room, $180) # night 1

A: add_line(Room, $180) # night 2

A: submit_form() # skipped night 3

=> Residual: $180 unaccounted (1 of 3 room nights missing)

#### (4) Premature termination (C3).

[⬇](data:text/plain;base64,QTogZ2V0X2Zvcm1fc3RhdGUoKQpUOiB7dG90YWxfYWRkZWQ6ICQzNDAsIHJlbWFpbmluZzogJDI0MH0KQTogYWRkX2xpbmUoUGFya2luZywgJDQ1KQpUOiB7b2t9CiMgcHJ1bmluZyB3aW5kb3cgZHJvcHMgdGhlIGVhcmxpZXIgInJlbWFpbmluZzogJDI0MCIgbGluZQpBOiAjIGFnZW50IG5vIGxvbmdlciBzZWVzIHRoZSBydW5uaW5nIGJhbGFuY2UKQTogc3VibWl0X2Zvcm0oKQo9PiBSZXNpZHVhbDogJDE5NSBzdGlsbCBvd2VkLiBGb3JtIHN1Ym1pdHRlZCBpbmNvbXBsZXRlLg==)

A: get_form_state()

T: {total_added: $340, remaining: $240}

A: add_line(Parking, $45)

T: {ok}

# pruning window drops the earlier "remaining: $240" line

A: # agent no longer sees the running balance

A: submit_form()

=> Residual: $195 still owed. Form submitted incomplete.

#### (5) Tool / form navigation error (C2).

[⬇](data:text/plain;base64,QTogYWRkX2xpbmUoY2F0ZWdvcnk9SG90ZWwtUmVzb3J0X0ZlZSwgYW1vdW50PTI1KQpUOiBFUlJPUjogaW52YWxpZCBjYXRlZ29yeSBlbnVtICdIb3RlbC1SZXNvcnRfRmVlJwogICAoZXhwZWN0ZWQgb25lIG9mOiBIb3RlbC1SZXNvcnRGZWUsIEhvdGVsLVBhcmtpbmcsIC4uLikKQTogYWRkX2xpbmUoY2F0ZWdvcnk9UmVzb3J0IEZlZSwgYW1vdW50PTI1KQpUOiBFUlJPUjogaW52YWxpZCBjYXRlZ29yeSBlbnVtICdSZXNvcnQgRmVlJwpBOiBzdWJtaXRfZm9ybSgpCj0+IFJlc2lkdWFsOiAkMjUuIEFnZW50IGNvdWxkIG5vdCByZWNvdmVyIGZyb20gZW51bSBtaXNtYXRjaC4=)

A: add_line(category=Hotel-Resort_Fee, amount=25)

T: ERROR: invalid category enum ’Hotel-Resort_Fee’

(expected one of: Hotel-ResortFee, Hotel-Parking, ...)

A: add_line(category=Resort Fee, amount=25)

T: ERROR: invalid category enum ’Resort Fee’

A: submit_form()

=> Residual: $25. Agent could not recover from enum mismatch.

#### (6) Residual amount mismatch (C4).

[⬇](data:text/plain;base64,QTogIyByZWNlaXB0IHRvdGFsICQ1ODAuNDIKQTogYWRkX2xpbmUoUm9vbSwgJDQ4MCkKQTogYWRkX2xpbmUoVGF4LCAkNzIuMDUpCkE6IGFkZF9saW5lKFBhcmtpbmcsICQyOCkKQTogc3VibWl0X2Zvcm0oKQo9PiBSZXNpZHVhbDogJDAuMzcgKHJvdW5kaW5nL3RheCBsaW5lIGVycm9yIC0tIGFyaXRobWV0aWMgb2ZmKQ==)

A: # receipt total $580.42

A: add_line(Room, $480)

A: add_line(Tax, $72.05)

A: add_line(Parking, $28)

A: submit_form()

=> Residual: $0.37 (rounding/tax line error \-- arithmetic off)

#### Real C4 summarization output.

The following is a representative summary string emitted by the C4 summarizer after the first summarization window of 3 tool calls during a hotel run:

[⬇](data:text/plain;base64,U3VtbWFyeSBvZiBwcmV2aW91cyB0b29sIGNhbGxzOgotIE9wZW5lZCB0aGUgRXhwZW5zZSByZXBvcnQgZm9ybSBhbmQgbmF2aWdhdGVkIHRvIGV4cGVuc2UKICByZXBvcnQgRVItMDAxODQgKGhvdGVsIGNhdGVnb3J5LCByZWNlaXB0IHRvdGFsICQ2MTIuNDApLgotIENsaWNrZWQgdGhlICJJdGVtaXplIiBidXR0b24gYW5kIG9wZW5lZCB0aGUgaXRlbWl6YXRpb24KICBzdWItZm9ybSBmb3IgdGhlIGhvdGVsIGxpbmUuCi0gQWRkZWQgYSBIb3RlbC1Sb29tIGxpbmUgd2l0aCBhbW91bnQgJDE4MC4wMCB2aWEgdGhlCiAgYWRkX2xpbmUgY29udHJvbC4KLSBBZGRlZCBhIEhvdGVsLVRheCBsaW5lIHdpdGggYW1vdW50ICQxNC40MCB2aWEgdGhlCiAgYWRkX2xpbmUgY29udHJvbC4=)

Summary of previous tool calls:

- Opened the Expense report form and navigated to expense

report ER-00184 (hotel category, receipt total $612.40).

- Clicked the "Itemize" button and opened the itemization

sub-form for the hotel line.

- Added a Hotel-Room line with amount $180.00 via the

add_line control.

- Added a Hotel-Tax line with amount $14.40 via the

add_line control.

This is the mechanism by which C4 suppresses premature termination: by condensing prior actions into a short assistant message, the agent retains awareness of which lines have already been added and roughly how much of the receipt has been accounted for, even after the verbose raw tool responses have been pruned. The summarizer is intentionally generic (it describes forms, controls, buttons, and entered data) rather than computing a running balance explicitly—yet this is still enough signal to push the agent past the premature-termination threshold observed in C3.

##  Appendix G Performance and efficiency figures

C1: No userC2: Full ContextC3: Last 5 TCC4: Last 5+Sum.02020404060608080100100Percentage (%)Completely Itemized (primary)<<10% Remaining% Amount Itemized Figure 2: Performance metrics across four context engineering configurations, averaged over 5 independent runs on the 50-task hotel expense benchmark. C1 = GPT-5 only (no user model); C2 = Full conversation history; C3 = Last 5 tool calls (TC); C4 = Last 5 TC + Summarization (window = 3). C4 achieves the best performance across all three metrics. Completely Itemized (blue) is the primary metric, reflecting genuine business task completion (remaining amount = $0.00).

C1C2C3C405005001,0001{,}0001,5001{,}500532.6532.61,4811{,}481535.3535.3553.4553.4Total Tokens (K) (a) Total token usage per benchmark (thousands of tokens). C2 (Full Context) consumes 2.68×\times more tokens than C4 while achieving lower task completion.

C1C2C3C4055101015153.083.0814.5614.565.395.395.795.79Execution Time (hours) (b) Benchmark wall-clock execution time (hours). C4 completes the 50-task benchmark 2.51×\times faster than C2 while achieving higher task completion.

Figure 3: Efficiency metrics across the four configurations (averaged over 5 runs, 50-task benchmark). C1 = GPT-5 only (no user); C2 = Full Context; C3 = Last 5 Tool Calls; C4 = Last 5 + Summarization. Left panel: total token usage in thousands; input tokens dominate in all configurations (>>99.7% of total). Right panel: wall-clock benchmark completion time in hours. C3 and C4 achieve comparable token budgets to the C1 token budget while dramatically improving task completion.

##  Appendix H Sensitivity to pruning window NN and summary window WW

We sweep each hyperparameter while holding the other fixed (all with the user model present) to test whether the headline result depends on the specific choices N=5N{=}5 and W=3W{=}3. Table 7 reports the primary metric and total tokens.

Sweep | Setting | Comp. Item. (%) | Tok. (K)  
---|---|---|---  
Pruning NN | N=3,W=0N{=}3,\ W{=}0 | 74.0 | 425  
N=5,W=0N{=}5,\ W{=}0 | 79.0 | 535.3  
N=10,W=0N{=}10,\ W{=}0 | 80.0 | 820  
N=∞N{=}\infty (C2) | 71.0 | 1,481.0  
Summary WW | N=5,W=1N{=}5,\ W{=}1 | 86.4 | 540  
N=5,W=3N{=}5,\ W{=}3 | 91.6 | 553.4  
N=5,W=5N{=}5,\ W{=}5 | 92.0 | 575  
full-hist. summ. (W=−1W{=}{-}1) | 92.0 | 615  
Table 7: Sensitivity of the primary metric and token cost to the pruning window NN (top) and summary window WW (bottom). Bold rows in the original study are N=5,W=0N{=}5,W{=}0 (C3) and N=5,W=3N{=}5,W{=}3 (C4).

#### Interpretation.

The pruning sweep shows that complete itemization plateaus around N=5N{=}5: dropping to N=3N{=}3 costs ∼\sim5 pts of accuracy, while extending to N=10N{=}10 buys less than 1 pt at the cost of ∼\sim53% more tokens, and the unbounded variant (N=∞N{=}\infty, C2) is strictly worse than N=5N{=}5 on both axes. The summary sweep is similarly flat above W=3W{=}3: W=5W{=}5 and full-history summarization add 4–11% token cost over W=3W{=}3 without a meaningful accuracy gain, while W=1W{=}1 underperforms by ∼\sim5 pts. Together these confirm that (N=5,W=3)(N{=}5,W{=}3) sits at the knee of both curves—further context buys diminishing returns and tighter windows lose the bookkeeping that prevents premature termination.

##  Appendix I Cross-model generalization: Claude Sonnet 4.5

Config (Sonnet 4.5) | Comp. |  <<10% |  ≥\geq1 | %Amt | Tok. (K) | Time  
---|---|---|---|---|---|---  
No CE (full context) | 88.0 | 96.0 | 100.0 | 98.23 | 3,562 | 6.20  
Pruning (Last 5 TC) | 92.0 | 96.5 | 100.0 | 98.78 | 2,161 | 10.70  
Pruning + Summ. | 94.5 | 97.5 | 100.0 | 99.20 | 2,235 | 11.30  
  
Table 8: Claude Sonnet 4.5 on the 50-task hotel benchmark. All three configurations are run _without_ a user model: Sonnet does not stall in the non-interactive harness, so the user-model rescue required for GPT-5 is unnecessary. No CE is the no-context-engineering baseline (full history); Pruning applies last-5 tool-call pruning; Pruning \+ Summ. adds summarization on top of pruning. We use descriptive labels rather than C-numbers to avoid implying a one-to-one correspondence with GPT-5’s configurations in Table 4. Time in hours; Tokens reported as total (K=K= thousands).

As shown in Table 8, summarization buys accuracy at a consistent ∼\sim6–7% time premium relative to pure pruning across both models—evidence that the per-step summarization LLM call cost is model-stable.

##  Appendix J Extended discussion: efficiency and generalizability

### Efficiency implications for production deployment

The token efficiency results have direct implications for production deployment economics. Full-context agents (C2) consume 1,480,996 tokens per 50-task benchmark versus 553,374 for C4—a 2.68×\times difference translating directly to inference cost. At scale across thousands of expense reports monthly, this gap represents substantial operational savings. The 14.56-hour versus 5.79-hour execution time difference further impacts throughput and user-facing latency.

C3 (pruning without summarization) represents a secondary operating point for cost-sensitive deployments: 79.0% task completion at baseline-equivalent token cost, compared to 71.0% for full context at 2.77×\times the cost.

### Generalizability and scope

We deliberately scope our claims. The evidence here is strong for one class of enterprise tool-use workflow: structured, single-session, form-driven tasks with verbose tool responses and a hard completion criterion. The context engineering techniques evaluated here are inference-time only and require no modification to the underlying LLM, and our cross-model (Appendix I) and multi-category (Section 4.8) results test how far the policy carries. The same principles are expected to extend to other frontier models and to enterprise agentic domains with similarly verbose tool responses—CRM, supply chain automation, IT service management, healthcare administration—and characterizing the per-domain optimal window size, including adaptive sizing driven by task complexity or error signals, is a natural next step.

Experimental support, please [view the build logs](./2606.10209v1/__stdout.txt) for errors. Generated by [ L A T E xml ](https://math.nist.gov/~BMiller/LaTeXML/). 

## Instructions for reporting errors

We are continuing to improve HTML versions of papers, and your feedback helps enhance accessibility and mobile support. To report errors in the HTML that will help us improve conversion and rendering, choose any of the methods listed below:

  * Click the "Report Issue" ( ) button, located in the page header.



**Tip:** You can select the relevant text first, to include it in your report.

Our team has already identified [the following issues](https://github.com/arXiv/html_feedback/issues). We appreciate your time reviewing and reporting rendering errors we may not have found yet. Your efforts will help us improve the HTML versions for all readers, because disability should not be a barrier to accessing research. Thank you for your continued support in championing open access for all.

Have a free development cycle? Help support accessibility at arXiv! Our collaborators at LaTeXML maintain a [list of packages that need conversion](https://github.com/brucemiller/LaTeXML/wiki/Porting-LaTeX-packages-for-LaTeXML), and welcome [developer contributions](https://github.com/brucemiller/LaTeXML/issues).

BETA

[ ](javascript:toggleReadingMode\(\); "Disable reading mode, show header and footer")
