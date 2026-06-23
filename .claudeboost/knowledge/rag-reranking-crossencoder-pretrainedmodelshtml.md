<!-- Source: https://sbert.net/docs/cross_encoder/pretrained_models.html | Tier: A | Topic: rag-reranking | Fetched: 2026-06-23 -->

[ ](../../index.html)

Getting Started

  * [Installation](../installation.html)
    * [Install with uv](../installation.html#install-with-uv)
    * [Install with pip](../installation.html#install-with-pip)
    * [Install with Conda](../installation.html#install-with-conda)
    * [Install from Source](../installation.html#install-from-source)
    * [Editable Install](../installation.html#editable-install)
    * [Install PyTorch with CUDA support](../installation.html#install-pytorch-with-cuda-support)
  * [Quickstart](../quickstart.html)
    * [Sentence Transformer](../quickstart.html#sentence-transformer)
    * [Cross Encoder](../quickstart.html#cross-encoder)
    * [Sparse Encoder](../quickstart.html#sparse-encoder)
    * [Next Steps](../quickstart.html#next-steps)
  * [Migration Guide](../migration_guide.html)
    * [Migrating from v5.x to v5.4+](../migration_guide.html#migrating-from-v5-x-to-v5-4)
      * [Updated import paths](../migration_guide.html#updated-import-paths)
      * [Renamed methods and parameters](../migration_guide.html#renamed-methods-and-parameters)
      * [`CrossEncoder.max_length` property renamed to `max_seq_length`](../migration_guide.html#crossencoder-max-length-property-renamed-to-max-seq-length)
      * [Trainer `tokenizer` parameter renamed to `processing_class`](../migration_guide.html#trainer-tokenizer-parameter-renamed-to-processing-class)
      * [`tokenizer_kwargs` renamed to `processor_kwargs`](../migration_guide.html#tokenizer-kwargs-renamed-to-processor-kwargs)
      * [CrossEncoder API changes](../migration_guide.html#crossencoder-api-changes)
      * [Removed `tags` parameter from `push_to_hub`](../migration_guide.html#removed-tags-parameter-from-push-to-hub)
      * [Default pooling for CausalLM models](../migration_guide.html#default-pooling-for-causallm-models)
      * [Changes for custom module and loss authors](../migration_guide.html#changes-for-custom-module-and-loss-authors)
    * [Migrating from v4.x to v5.x](../migration_guide.html#migrating-from-v4-x-to-v5-x)
      * [Migration for model.encode](../migration_guide.html#migration-for-model-encode)
      * [Migration for Asym to Router](../migration_guide.html#migration-for-asym-to-router)
      * [Migration of advanced usage](../migration_guide.html#migration-of-advanced-usage)
    * [Migrating from v3.x to v4.x](../migration_guide.html#migrating-from-v3-x-to-v4-x)
      * [Migration for parameters on `CrossEncoder` initialization and methods](../migration_guide.html#migration-for-parameters-on-crossencoder-initialization-and-methods)
      * [Migration for specific parameters from `CrossEncoder.fit`](../migration_guide.html#migration-for-specific-parameters-from-crossencoder-fit)
      * [Migration for CrossEncoder evaluators](../migration_guide.html#migration-for-crossencoder-evaluators)
    * [Migrating from v2.x to v3.x](../migration_guide.html#migrating-from-v2-x-to-v3-x)
      * [Migration for specific parameters from `SentenceTransformer.fit`](../migration_guide.html#migration-for-specific-parameters-from-sentencetransformer-fit)
      * [Migration for custom Datasets and DataLoaders used in `SentenceTransformer.fit`](../migration_guide.html#migration-for-custom-datasets-and-dataloaders-used-in-sentencetransformer-fit)



Sentence Transformer

  * [Usage](../sentence_transformer/usage/usage.html)
    * [Computing Embeddings](../../examples/sentence_transformer/applications/computing-embeddings/README.html)
      * [Initializing a Sentence Transformer Model](../../examples/sentence_transformer/applications/computing-embeddings/README.html#initializing-a-sentence-transformer-model)
      * [Calculating Embeddings](../../examples/sentence_transformer/applications/computing-embeddings/README.html#calculating-embeddings)
      * [Prompt Templates](../../examples/sentence_transformer/applications/computing-embeddings/README.html#prompt-templates)
      * [Input Sequence Length](../../examples/sentence_transformer/applications/computing-embeddings/README.html#input-sequence-length)
      * [Multi-Process / Multi-GPU Encoding](../../examples/sentence_transformer/applications/computing-embeddings/README.html#multi-process-multi-gpu-encoding)
    * [Semantic Textual Similarity](../sentence_transformer/usage/semantic_textual_similarity.html)
      * [Similarity Calculation](../sentence_transformer/usage/semantic_textual_similarity.html#similarity-calculation)
    * [Semantic Search](../../examples/sentence_transformer/applications/semantic-search/README.html)
      * [Background](../../examples/sentence_transformer/applications/semantic-search/README.html#background)
      * [Symmetric vs. Asymmetric Semantic Search](../../examples/sentence_transformer/applications/semantic-search/README.html#symmetric-vs-asymmetric-semantic-search)
      * [Manual Implementation](../../examples/sentence_transformer/applications/semantic-search/README.html#manual-implementation)
      * [Optimized Implementation](../../examples/sentence_transformer/applications/semantic-search/README.html#optimized-implementation)
      * [Speed Optimization](../../examples/sentence_transformer/applications/semantic-search/README.html#speed-optimization)
      * [Elasticsearch](../../examples/sentence_transformer/applications/semantic-search/README.html#elasticsearch)
      * [OpenSearch](../../examples/sentence_transformer/applications/semantic-search/README.html#opensearch)
      * [Approximate Nearest Neighbor](../../examples/sentence_transformer/applications/semantic-search/README.html#approximate-nearest-neighbor)
      * [Retrieve & Re-Rank](../../examples/sentence_transformer/applications/semantic-search/README.html#retrieve-re-rank)
      * [Examples](../../examples/sentence_transformer/applications/semantic-search/README.html#examples)
    * [Retrieve & Re-Rank](../../examples/sentence_transformer/applications/retrieve_rerank/README.html)
      * [Retrieve & Re-Rank Pipeline](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#retrieve-re-rank-pipeline)
      * [Retrieval: Bi-Encoder](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#retrieval-bi-encoder)
      * [Re-Ranker: Cross-Encoder](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#re-ranker-cross-encoder)
      * [Example Scripts](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#example-scripts)
      * [Pre-trained Bi-Encoders (Retrieval)](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#pre-trained-bi-encoders-retrieval)
      * [Pre-trained Cross-Encoders (Re-Ranker)](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#pre-trained-cross-encoders-re-ranker)
    * [Clustering](../../examples/sentence_transformer/applications/clustering/README.html)
      * [k-Means](../../examples/sentence_transformer/applications/clustering/README.html#k-means)
      * [Agglomerative Clustering](../../examples/sentence_transformer/applications/clustering/README.html#agglomerative-clustering)
      * [Fast Clustering](../../examples/sentence_transformer/applications/clustering/README.html#fast-clustering)
      * [Topic Modeling](../../examples/sentence_transformer/applications/clustering/README.html#topic-modeling)
    * [Paraphrase Mining](../../examples/sentence_transformer/applications/paraphrase-mining/README.html)
      * [`paraphrase_mining()`](../../examples/sentence_transformer/applications/paraphrase-mining/README.html#sentence_transformers.util.paraphrase_mining)
    * [Translated Sentence Mining](../../examples/sentence_transformer/applications/parallel-sentence-mining/README.html)
      * [Margin Based Mining](../../examples/sentence_transformer/applications/parallel-sentence-mining/README.html#margin-based-mining)
      * [Examples](../../examples/sentence_transformer/applications/parallel-sentence-mining/README.html#examples)
    * [Image Search](../../examples/sentence_transformer/applications/image-search/README.html)
      * [Installation](../../examples/sentence_transformer/applications/image-search/README.html#installation)
      * [Usage](../../examples/sentence_transformer/applications/image-search/README.html#usage)
      * [Examples](../../examples/sentence_transformer/applications/image-search/README.html#examples)
    * [Embedding Quantization](../../examples/sentence_transformer/applications/embedding-quantization/README.html)
      * [Binary Quantization](../../examples/sentence_transformer/applications/embedding-quantization/README.html#binary-quantization)
      * [Scalar (int8) Quantization](../../examples/sentence_transformer/applications/embedding-quantization/README.html#scalar-int8-quantization)
      * [Additional extensions](../../examples/sentence_transformer/applications/embedding-quantization/README.html#additional-extensions)
      * [Demo](../../examples/sentence_transformer/applications/embedding-quantization/README.html#demo)
      * [Try it yourself](../../examples/sentence_transformer/applications/embedding-quantization/README.html#try-it-yourself)
    * [Creating Custom Models](../sentence_transformer/usage/custom_models.html)
      * [Modular Architecture](../sentence_transformer/usage/custom_models.html#modular-architecture)
      * [Sentence Transformer Model from a Transformers Model](../sentence_transformer/usage/custom_models.html#sentence-transformer-model-from-a-transformers-model)
      * [Advanced: Custom Modules](../sentence_transformer/usage/custom_models.html#advanced-custom-modules)
    * [Evaluation with MTEB](../sentence_transformer/usage/mteb_evaluation.html)
      * [Installation](../sentence_transformer/usage/mteb_evaluation.html#installation)
      * [Evaluation](../sentence_transformer/usage/mteb_evaluation.html#evaluation)
      * [Additional Arguments](../sentence_transformer/usage/mteb_evaluation.html#additional-arguments)
      * [Results Handling](../sentence_transformer/usage/mteb_evaluation.html#results-handling)
      * [Leaderboard Submission](../sentence_transformer/usage/mteb_evaluation.html#leaderboard-submission)
    * [Speeding up Inference](../sentence_transformer/usage/efficiency.html)
      * [PyTorch](../sentence_transformer/usage/efficiency.html#pytorch)
      * [ONNX](../sentence_transformer/usage/efficiency.html#onnx)
      * [OpenVINO](../sentence_transformer/usage/efficiency.html#openvino)
      * [Benchmarks](../sentence_transformer/usage/efficiency.html#benchmarks)
  * [Pretrained Models](../sentence_transformer/pretrained_models.html)
    * [Original Models](../sentence_transformer/pretrained_models.html#original-models)
    * [Semantic Search Models](../sentence_transformer/pretrained_models.html#semantic-search-models)
      * [Multi-QA Models](../sentence_transformer/pretrained_models.html#multi-qa-models)
      * [MSMARCO Passage Models](../sentence_transformer/pretrained_models.html#msmarco-passage-models)
    * [Multilingual Models](../sentence_transformer/pretrained_models.html#multilingual-models)
      * [Semantic Similarity Models](../sentence_transformer/pretrained_models.html#semantic-similarity-models)
      * [Bitext Mining](../sentence_transformer/pretrained_models.html#bitext-mining)
    * [Multimodal Models](../sentence_transformer/pretrained_models.html#multimodal-models)
      * [Image & Text Models](../sentence_transformer/pretrained_models.html#image-text-models)
      * [Audio & Video Models](../sentence_transformer/pretrained_models.html#audio-video-models)
    * [INSTRUCTOR models](../sentence_transformer/pretrained_models.html#instructor-models)
    * [Scientific Similarity Models](../sentence_transformer/pretrained_models.html#scientific-similarity-models)
  * [Training Overview](../sentence_transformer/training_overview.html)
    * [Why Finetune?](../sentence_transformer/training_overview.html#why-finetune)
    * [Training Components](../sentence_transformer/training_overview.html#training-components)
    * [Model](../sentence_transformer/training_overview.html#model)
    * [Dataset](../sentence_transformer/training_overview.html#dataset)
      * [Dataset Format](../sentence_transformer/training_overview.html#dataset-format)
      * [Multimodal Datasets](../sentence_transformer/training_overview.html#multimodal-datasets)
    * [Loss Function](../sentence_transformer/training_overview.html#loss-function)
    * [Training Arguments](../sentence_transformer/training_overview.html#training-arguments)
    * [Evaluator](../sentence_transformer/training_overview.html#evaluator)
    * [Trainer](../sentence_transformer/training_overview.html#trainer)
      * [Callbacks](../sentence_transformer/training_overview.html#callbacks)
    * [Multi-Dataset Training](../sentence_transformer/training_overview.html#multi-dataset-training)
    * [Deprecated Training](../sentence_transformer/training_overview.html#deprecated-training)
    * [Best Base Embedding Models](../sentence_transformer/training_overview.html#best-base-embedding-models)
    * [Comparisons with CrossEncoder Training](../sentence_transformer/training_overview.html#comparisons-with-crossencoder-training)
    * [End-to-End Example](../sentence_transformer/training_overview.html#end-to-end-example)
  * [Dataset Overview](../sentence_transformer/dataset_overview.html)
    * [Multimodal Datasets](../sentence_transformer/dataset_overview.html#multimodal-datasets)
      * [Accepted column types](../sentence_transformer/dataset_overview.html#accepted-column-types)
      * [Cross-modal dataset example](../sentence_transformer/dataset_overview.html#cross-modal-dataset-example)
      * [Automatic preprocessing](../sentence_transformer/dataset_overview.html#automatic-preprocessing)
    * [Datasets on the Hugging Face Hub](../sentence_transformer/dataset_overview.html#datasets-on-the-hugging-face-hub)
    * [Pre-existing Datasets](../sentence_transformer/dataset_overview.html#pre-existing-datasets)
  * [Loss Overview](../sentence_transformer/loss_overview.html)
    * [Loss Table](../sentence_transformer/loss_overview.html#loss-table)
    * [Loss modifiers](../sentence_transformer/loss_overview.html#loss-modifiers)
    * [Regularization](../sentence_transformer/loss_overview.html#regularization)
    * [Distillation](../sentence_transformer/loss_overview.html#distillation)
    * [Commonly used Loss Functions](../sentence_transformer/loss_overview.html#commonly-used-loss-functions)
    * [Custom Loss Functions](../sentence_transformer/loss_overview.html#custom-loss-functions)
  * [Training Examples](../sentence_transformer/training/examples.html)
    * [Semantic Textual Similarity](../../examples/sentence_transformer/training/sts/README.html)
      * [Training data](../../examples/sentence_transformer/training/sts/README.html#training-data)
      * [Loss Function](../../examples/sentence_transformer/training/sts/README.html#loss-function)
    * [Natural Language Inference](../../examples/sentence_transformer/training/nli/README.html)
      * [Data](../../examples/sentence_transformer/training/nli/README.html#data)
      * [SoftmaxLoss](../../examples/sentence_transformer/training/nli/README.html#softmaxloss)
      * [MultipleNegativesRankingLoss](../../examples/sentence_transformer/training/nli/README.html#multiplenegativesrankingloss)
    * [Paraphrase Data](../../examples/sentence_transformer/training/paraphrases/README.html)
      * [Pre-Trained Models](../../examples/sentence_transformer/training/paraphrases/README.html#pre-trained-models)
    * [Quora Duplicate Questions](../../examples/sentence_transformer/training/quora_duplicate_questions/README.html)
      * [Training](../../examples/sentence_transformer/training/quora_duplicate_questions/README.html#training)
      * [MultipleNegativesRankingLoss](../../examples/sentence_transformer/training/quora_duplicate_questions/README.html#multiplenegativesrankingloss)
      * [Pretrained Models](../../examples/sentence_transformer/training/quora_duplicate_questions/README.html#pretrained-models)
    * [MS MARCO](../../examples/sentence_transformer/training/ms_marco/README.html)
      * [Bi-Encoder](../../examples/sentence_transformer/training/ms_marco/README.html#bi-encoder)
    * [Matryoshka Embeddings](../../examples/sentence_transformer/training/matryoshka/README.html)
      * [Use Cases](../../examples/sentence_transformer/training/matryoshka/README.html#use-cases)
      * [Results](../../examples/sentence_transformer/training/matryoshka/README.html#results)
      * [Training](../../examples/sentence_transformer/training/matryoshka/README.html#training)
      * [Inference](../../examples/sentence_transformer/training/matryoshka/README.html#inference)
      * [Code Examples](../../examples/sentence_transformer/training/matryoshka/README.html#code-examples)
    * [Adaptive Layers](../../examples/sentence_transformer/training/adaptive_layer/README.html)
      * [Use Cases](../../examples/sentence_transformer/training/adaptive_layer/README.html#use-cases)
      * [Results](../../examples/sentence_transformer/training/adaptive_layer/README.html#results)
      * [Training](../../examples/sentence_transformer/training/adaptive_layer/README.html#training)
      * [Inference](../../examples/sentence_transformer/training/adaptive_layer/README.html#inference)
      * [Code Examples](../../examples/sentence_transformer/training/adaptive_layer/README.html#code-examples)
    * [Multilingual Models](../../examples/sentence_transformer/training/multilingual/README.html)
      * [Extend your own models](../../examples/sentence_transformer/training/multilingual/README.html#extend-your-own-models)
      * [Training](../../examples/sentence_transformer/training/multilingual/README.html#training)
      * [Datasets](../../examples/sentence_transformer/training/multilingual/README.html#datasets)
      * [Sources for Training Data](../../examples/sentence_transformer/training/multilingual/README.html#sources-for-training-data)
      * [Evaluation](../../examples/sentence_transformer/training/multilingual/README.html#evaluation)
      * [Available Pre-trained Models](../../examples/sentence_transformer/training/multilingual/README.html#available-pre-trained-models)
      * [Usage](../../examples/sentence_transformer/training/multilingual/README.html#usage)
      * [Performance](../../examples/sentence_transformer/training/multilingual/README.html#performance)
      * [Citation](../../examples/sentence_transformer/training/multilingual/README.html#citation)
    * [Model Distillation](../../examples/sentence_transformer/training/distillation/README.html)
      * [Knowledge Distillation](../../examples/sentence_transformer/training/distillation/README.html#knowledge-distillation)
      * [Speed - Performance Trade-Off](../../examples/sentence_transformer/training/distillation/README.html#speed-performance-trade-off)
      * [Dimensionality Reduction](../../examples/sentence_transformer/training/distillation/README.html#dimensionality-reduction)
      * [Quantization](../../examples/sentence_transformer/training/distillation/README.html#quantization)
    * [Augmented SBERT](../../examples/sentence_transformer/training/data_augmentation/README.html)
      * [Motivation](../../examples/sentence_transformer/training/data_augmentation/README.html#motivation)
      * [Extend to your own datasets](../../examples/sentence_transformer/training/data_augmentation/README.html#extend-to-your-own-datasets)
      * [Methodology](../../examples/sentence_transformer/training/data_augmentation/README.html#methodology)
      * [Scenario 1: Limited or small annotated datasets (few labeled sentence-pairs)](../../examples/sentence_transformer/training/data_augmentation/README.html#scenario-1-limited-or-small-annotated-datasets-few-labeled-sentence-pairs)
      * [Scenario 2: No annotated datasets (Only unlabeled sentence-pairs)](../../examples/sentence_transformer/training/data_augmentation/README.html#scenario-2-no-annotated-datasets-only-unlabeled-sentence-pairs)
      * [Training](../../examples/sentence_transformer/training/data_augmentation/README.html#training)
      * [Citation](../../examples/sentence_transformer/training/data_augmentation/README.html#citation)
    * [Training with Prompts](../../examples/sentence_transformer/training/prompts/README.html)
      * [What are Prompts?](../../examples/sentence_transformer/training/prompts/README.html#what-are-prompts)
      * [Why would we train with Prompts?](../../examples/sentence_transformer/training/prompts/README.html#why-would-we-train-with-prompts)
      * [How do we train with Prompts?](../../examples/sentence_transformer/training/prompts/README.html#how-do-we-train-with-prompts)
    * [Training with PEFT Adapters](../../examples/sentence_transformer/training/peft/README.html)
      * [Compatibility Methods](../../examples/sentence_transformer/training/peft/README.html#compatibility-methods)
      * [Adding a New Adapter](../../examples/sentence_transformer/training/peft/README.html#adding-a-new-adapter)
      * [Loading a Pretrained Adapter](../../examples/sentence_transformer/training/peft/README.html#loading-a-pretrained-adapter)
      * [Training Script](../../examples/sentence_transformer/training/peft/README.html#training-script)
    * [Training with Unsloth](../../examples/sentence_transformer/training/unsloth/README.html)
      * [Examples in this repository](../../examples/sentence_transformer/training/unsloth/README.html#examples-in-this-repository)
      * [Unsloth Colab notebooks](../../examples/sentence_transformer/training/unsloth/README.html#unsloth-colab-notebooks)
      * [Fine-tuning via FastSentenceTransformer](../../examples/sentence_transformer/training/unsloth/README.html#fine-tuning-via-fastsentencetransformer)
      * [Inference and deployment](../../examples/sentence_transformer/training/unsloth/README.html#inference-and-deployment)
      * [Benchmarks](../../examples/sentence_transformer/training/unsloth/README.html#benchmarks)
    * [Multimodal Training](../../examples/sentence_transformer/training/multimodal/README.html)
      * [Supported Input Types](../../examples/sentence_transformer/training/multimodal/README.html#supported-input-types)
      * [Training](../../examples/sentence_transformer/training/multimodal/README.html#training)
      * [References](../../examples/sentence_transformer/training/multimodal/README.html#references)
    * [Unsupervised Learning](../../examples/sentence_transformer/unsupervised_learning/README.html)
      * [TSDAE](../../examples/sentence_transformer/unsupervised_learning/README.html#tsdae)
      * [SimCSE](../../examples/sentence_transformer/unsupervised_learning/README.html#simcse)
      * [CT](../../examples/sentence_transformer/unsupervised_learning/README.html#ct)
      * [CT (In-Batch Negative Sampling)](../../examples/sentence_transformer/unsupervised_learning/README.html#ct-in-batch-negative-sampling)
      * [Masked Language Model (MLM)](../../examples/sentence_transformer/unsupervised_learning/README.html#masked-language-model-mlm)
      * [GenQ](../../examples/sentence_transformer/unsupervised_learning/README.html#genq)
      * [GPL](../../examples/sentence_transformer/unsupervised_learning/README.html#gpl)
      * [Performance Comparison](../../examples/sentence_transformer/unsupervised_learning/README.html#performance-comparison)
    * [Domain Adaptation](../../examples/sentence_transformer/domain_adaptation/README.html)
      * [Domain Adaptation vs. Unsupervised Learning](../../examples/sentence_transformer/domain_adaptation/README.html#domain-adaptation-vs-unsupervised-learning)
      * [Adaptive Pre-Training](../../examples/sentence_transformer/domain_adaptation/README.html#adaptive-pre-training)
      * [GPL: Generative Pseudo-Labeling](../../examples/sentence_transformer/domain_adaptation/README.html#gpl-generative-pseudo-labeling)
    * [Hyperparameter Optimization](../../examples/sentence_transformer/training/hpo/README.html)
      * [HPO Components](../../examples/sentence_transformer/training/hpo/README.html#hpo-components)
      * [Putting It All Together](../../examples/sentence_transformer/training/hpo/README.html#putting-it-all-together)
      * [Example Scripts](../../examples/sentence_transformer/training/hpo/README.html#example-scripts)
    * [Distributed Training](../sentence_transformer/training/distributed.html)
      * [Comparison](../sentence_transformer/training/distributed.html#comparison)
      * [FSDP](../sentence_transformer/training/distributed.html#fsdp)



Cross Encoder

  * [Usage](usage/usage.html)
    * [Cross-Encoder vs Bi-Encoder](../../examples/cross_encoder/applications/README.html)
      * [Cross-Encoder vs. Bi-Encoder](../../examples/cross_encoder/applications/README.html#cross-encoder-vs-bi-encoder)
      * [When to use Cross- / Bi-Encoders?](../../examples/cross_encoder/applications/README.html#when-to-use-cross-bi-encoders)
      * [Cross-Encoders Usage](../../examples/cross_encoder/applications/README.html#cross-encoders-usage)
      * [Combining Bi- and Cross-Encoders](../../examples/cross_encoder/applications/README.html#combining-bi-and-cross-encoders)
      * [Training Cross-Encoders](../../examples/cross_encoder/applications/README.html#training-cross-encoders)
    * [Retrieve & Re-Rank](../../examples/sentence_transformer/applications/retrieve_rerank/README.html)
      * [Retrieve & Re-Rank Pipeline](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#retrieve-re-rank-pipeline)
      * [Retrieval: Bi-Encoder](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#retrieval-bi-encoder)
      * [Re-Ranker: Cross-Encoder](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#re-ranker-cross-encoder)
      * [Example Scripts](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#example-scripts)
      * [Pre-trained Bi-Encoders (Retrieval)](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#pre-trained-bi-encoders-retrieval)
      * [Pre-trained Cross-Encoders (Re-Ranker)](../../examples/sentence_transformer/applications/retrieve_rerank/README.html#pre-trained-cross-encoders-re-ranker)
    * [Creating Custom Models](usage/custom_models.html)
      * [Modular Architecture](usage/custom_models.html#modular-architecture)
      * [Advanced: Custom Modules](usage/custom_models.html#advanced-custom-modules)
    * [Speeding up Inference](usage/efficiency.html)
      * [PyTorch](usage/efficiency.html#pytorch)
      * [ONNX](usage/efficiency.html#onnx)
      * [OpenVINO](usage/efficiency.html#openvino)
      * [Benchmarks](usage/efficiency.html#benchmarks)
  * Pretrained Models
    * MS MARCO
    * SQuAD (QNLI)
    * STSbenchmark
    * Quora Duplicate Questions
    * NLI
    * Multimodal Rerankers
    * Community Models
  * [Training Overview](training_overview.html)
    * [Why Finetune?](training_overview.html#why-finetune)
    * [Training Components](training_overview.html#training-components)
    * [Model](training_overview.html#model)
    * [Dataset](training_overview.html#dataset)
      * [Dataset Format](training_overview.html#dataset-format)
      * [Multimodal Datasets](training_overview.html#multimodal-datasets)
      * [Hard Negatives Mining](training_overview.html#hard-negatives-mining)
    * [Loss Function](training_overview.html#loss-function)
    * [Training Arguments](training_overview.html#training-arguments)
    * [Evaluator](training_overview.html#evaluator)
    * [Trainer](training_overview.html#trainer)
      * [Callbacks](training_overview.html#callbacks)
    * [Multi-Dataset Training](training_overview.html#multi-dataset-training)
    * [Training Tips](training_overview.html#training-tips)
    * [Deprecated Training](training_overview.html#deprecated-training)
    * [Comparisons with SentenceTransformer Training](training_overview.html#comparisons-with-sentencetransformer-training)
    * [End-to-End Example](training_overview.html#end-to-end-example)
  * [Dataset Overview](../sentence_transformer/dataset_overview.html)
    * [Multimodal Datasets](../sentence_transformer/dataset_overview.html#multimodal-datasets)
      * [Accepted column types](../sentence_transformer/dataset_overview.html#accepted-column-types)
      * [Cross-modal dataset example](../sentence_transformer/dataset_overview.html#cross-modal-dataset-example)
      * [Automatic preprocessing](../sentence_transformer/dataset_overview.html#automatic-preprocessing)
    * [Datasets on the Hugging Face Hub](../sentence_transformer/dataset_overview.html#datasets-on-the-hugging-face-hub)
    * [Pre-existing Datasets](../sentence_transformer/dataset_overview.html#pre-existing-datasets)
  * [Loss Overview](loss_overview.html)
    * [Loss Table](loss_overview.html#loss-table)
    * [Distillation](loss_overview.html#distillation)
    * [Commonly used Loss Functions](loss_overview.html#commonly-used-loss-functions)
    * [Custom Loss Functions](loss_overview.html#custom-loss-functions)
  * [Training Examples](training/examples.html)
    * [Semantic Textual Similarity](../../examples/cross_encoder/training/sts/README.html)
      * [Training data](../../examples/cross_encoder/training/sts/README.html#training-data)
      * [Loss Function](../../examples/cross_encoder/training/sts/README.html#loss-function)
      * [Inference](../../examples/cross_encoder/training/sts/README.html#inference)
    * [Natural Language Inference](../../examples/cross_encoder/training/nli/README.html)
      * [Data](../../examples/cross_encoder/training/nli/README.html#data)
      * [CrossEntropyLoss](../../examples/cross_encoder/training/nli/README.html#crossentropyloss)
      * [Inference](../../examples/cross_encoder/training/nli/README.html#inference)
    * [Quora Duplicate Questions](../../examples/cross_encoder/training/quora_duplicate_questions/README.html)
      * [Training](../../examples/cross_encoder/training/quora_duplicate_questions/README.html#training)
      * [Inference](../../examples/cross_encoder/training/quora_duplicate_questions/README.html#inference)
    * [MS MARCO](../../examples/cross_encoder/training/ms_marco/README.html)
      * [Cross Encoder](../../examples/cross_encoder/training/ms_marco/README.html#cross-encoder)
      * [Training Scripts](../../examples/cross_encoder/training/ms_marco/README.html#training-scripts)
      * [Inference](../../examples/cross_encoder/training/ms_marco/README.html#inference)
    * [Rerankers](../../examples/cross_encoder/training/rerankers/README.html)
      * [BinaryCrossEntropyLoss](../../examples/cross_encoder/training/rerankers/README.html#binarycrossentropyloss)
      * [CachedMultipleNegativesRankingLoss](../../examples/cross_encoder/training/rerankers/README.html#cachedmultiplenegativesrankingloss)
      * [Inference](../../examples/cross_encoder/training/rerankers/README.html#inference)
    * [Model Distillation](../../examples/cross_encoder/training/distillation/README.html)
      * [Cross Encoder Knowledge Distillation](../../examples/cross_encoder/training/distillation/README.html#cross-encoder-knowledge-distillation)
      * [Inference](../../examples/cross_encoder/training/distillation/README.html#inference)
    * [Multimodal Training](../../examples/cross_encoder/training/multimodal/README.html)
      * [Transformer (Any-to-Any) + LogitScore](../../examples/cross_encoder/training/multimodal/README.html#transformer-any-to-any-logitscore)
      * [Transformer (Feature Extraction) + Pooling + Dense](../../examples/cross_encoder/training/multimodal/README.html#transformer-feature-extraction-pooling-dense)
      * [Comparing the Two Approaches](../../examples/cross_encoder/training/multimodal/README.html#comparing-the-two-approaches)
      * [Other Module Chains](../../examples/cross_encoder/training/multimodal/README.html#other-module-chains)
      * [References](../../examples/cross_encoder/training/multimodal/README.html#references)
    * [Distributed Training](../sentence_transformer/training/distributed.html)
      * [Comparison](../sentence_transformer/training/distributed.html#comparison)
      * [FSDP](../sentence_transformer/training/distributed.html#fsdp)



Sparse Encoder

  * [Usage](../sparse_encoder/usage/usage.html)
    * [Prompts](../sparse_encoder/usage/usage.html#prompts)
      * [Computing Sparse Embeddings](../../examples/sparse_encoder/applications/computing_embeddings/README.html)
      * [Semantic Textual Similarity](../../examples/sparse_encoder/applications/semantic_textual_similarity/README.html)
      * [Semantic Search](../../examples/sparse_encoder/applications/semantic_search/README.html)
      * [Retrieve & Re-Rank](../../examples/sparse_encoder/applications/retrieve_rerank/README.html)
      * [Sparse Encoder Evaluation](../../examples/sparse_encoder/evaluation/README.html)
      * [Speeding up Inference](../sparse_encoder/usage/efficiency.html)
  * [Pretrained Models](../sparse_encoder/pretrained_models.html)
    * [Core SPLADE Models](../sparse_encoder/pretrained_models.html#core-splade-models)
    * [Inference-Free SPLADE Models](../sparse_encoder/pretrained_models.html#inference-free-splade-models)
    * [Model Collections](../sparse_encoder/pretrained_models.html#model-collections)
  * [Training Overview](../sparse_encoder/training_overview.html)
    * [Why Finetune?](../sparse_encoder/training_overview.html#why-finetune)
    * [Training Components](../sparse_encoder/training_overview.html#training-components)
    * [Model](../sparse_encoder/training_overview.html#model)
    * [Dataset](../sparse_encoder/training_overview.html#dataset)
      * [Dataset Format](../sparse_encoder/training_overview.html#dataset-format)
    * [Loss Function](../sparse_encoder/training_overview.html#loss-function)
    * [Training Arguments](../sparse_encoder/training_overview.html#training-arguments)
    * [Evaluator](../sparse_encoder/training_overview.html#evaluator)
    * [Trainer](../sparse_encoder/training_overview.html#trainer)
      * [Callbacks](../sparse_encoder/training_overview.html#callbacks)
    * [Multi-Dataset Training](../sparse_encoder/training_overview.html#multi-dataset-training)
    * [Training Tips](../sparse_encoder/training_overview.html#training-tips)
    * [End-to-End Example](../sparse_encoder/training_overview.html#end-to-end-example)
  * [Dataset Overview](../sentence_transformer/dataset_overview.html)
    * [Multimodal Datasets](../sentence_transformer/dataset_overview.html#multimodal-datasets)
      * [Accepted column types](../sentence_transformer/dataset_overview.html#accepted-column-types)
      * [Cross-modal dataset example](../sentence_transformer/dataset_overview.html#cross-modal-dataset-example)
      * [Automatic preprocessing](../sentence_transformer/dataset_overview.html#automatic-preprocessing)
    * [Datasets on the Hugging Face Hub](../sentence_transformer/dataset_overview.html#datasets-on-the-hugging-face-hub)
    * [Pre-existing Datasets](../sentence_transformer/dataset_overview.html#pre-existing-datasets)
  * [Loss Overview](../sparse_encoder/loss_overview.html)
    * [Sparse specific Loss Functions](../sparse_encoder/loss_overview.html#sparse-specific-loss-functions)
      * [SPLADE Loss](../sparse_encoder/loss_overview.html#splade-loss)
      * [CSR Loss](../sparse_encoder/loss_overview.html#csr-loss)
    * [Loss Table](../sparse_encoder/loss_overview.html#loss-table)
    * [Distillation](../sparse_encoder/loss_overview.html#distillation)
    * [Commonly used Loss Functions](../sparse_encoder/loss_overview.html#commonly-used-loss-functions)
    * [Custom Loss Functions](../sparse_encoder/loss_overview.html#custom-loss-functions)
  * [Training Examples](../sparse_encoder/training/examples.html)
    * [Model Distillation](../../examples/sparse_encoder/training/distillation/README.html)
      * [MarginMSE](../../examples/sparse_encoder/training/distillation/README.html#marginmse)
    * [MS MARCO](../../examples/sparse_encoder/training/ms_marco/README.html)
      * [SparseMultipleNegativesRankingLoss](../../examples/sparse_encoder/training/ms_marco/README.html#sparsemultiplenegativesrankingloss)
    * [Semantic Textual Similarity](../../examples/sparse_encoder/training/sts/README.html)
      * [Training data](../../examples/sparse_encoder/training/sts/README.html#training-data)
      * [Loss Function](../../examples/sparse_encoder/training/sts/README.html#loss-function)
    * [Natural Language Inference](../../examples/sparse_encoder/training/nli/README.html)
      * [Data](../../examples/sparse_encoder/training/nli/README.html#data)
      * [SpladeLoss](../../examples/sparse_encoder/training/nli/README.html#spladeloss)
    * [Quora Duplicate Questions](../../examples/sparse_encoder/training/quora_duplicate_questions/README.html)
      * [Training](../../examples/sparse_encoder/training/quora_duplicate_questions/README.html#training)
    * [Information Retrieval](../../examples/sparse_encoder/training/retrievers/README.html)
      * [SparseMultipleNegativesRankingLoss (MNRL)](../../examples/sparse_encoder/training/retrievers/README.html#sparsemultiplenegativesrankingloss-mnrl)
      * [Inference & Evaluation](../../examples/sparse_encoder/training/retrievers/README.html#inference-evaluation)
    * [Distributed Training](../sentence_transformer/training/distributed.html)
      * [Comparison](../sentence_transformer/training/distributed.html#comparison)
      * [FSDP](../sentence_transformer/training/distributed.html#fsdp)



Package Reference

  * [Sentence Transformer](../package_reference/sentence_transformer/index.html)
    * [SentenceTransformer](../package_reference/sentence_transformer/model.html)
      * [SentenceTransformer](../package_reference/sentence_transformer/model.html#id1)
      * [SentenceTransformerModelCardData](../package_reference/sentence_transformer/model.html#sentencetransformermodelcarddata)
    * [Trainer](../package_reference/sentence_transformer/trainer.html)
      * [SentenceTransformerTrainer](../package_reference/sentence_transformer/trainer.html#sentencetransformertrainer)
    * [Training Arguments](../package_reference/sentence_transformer/training_args.html)
      * [SentenceTransformerTrainingArguments](../package_reference/sentence_transformer/training_args.html#sentencetransformertrainingarguments)
    * [Losses](../package_reference/sentence_transformer/losses.html)
      * [BatchAllTripletLoss](../package_reference/sentence_transformer/losses.html#batchalltripletloss)
      * [BatchHardSoftMarginTripletLoss](../package_reference/sentence_transformer/losses.html#batchhardsoftmargintripletloss)
      * [BatchHardTripletLoss](../package_reference/sentence_transformer/losses.html#batchhardtripletloss)
      * [BatchSemiHardTripletLoss](../package_reference/sentence_transformer/losses.html#batchsemihardtripletloss)
      * [ContrastiveLoss](../package_reference/sentence_transformer/losses.html#contrastiveloss)
      * [OnlineContrastiveLoss](../package_reference/sentence_transformer/losses.html#onlinecontrastiveloss)
      * [ContrastiveTensionLoss](../package_reference/sentence_transformer/losses.html#contrastivetensionloss)
      * [ContrastiveTensionLossInBatchNegatives](../package_reference/sentence_transformer/losses.html#contrastivetensionlossinbatchnegatives)
      * [CoSENTLoss](../package_reference/sentence_transformer/losses.html#cosentloss)
      * [AnglELoss](../package_reference/sentence_transformer/losses.html#angleloss)
      * [CosineSimilarityLoss](../package_reference/sentence_transformer/losses.html#cosinesimilarityloss)
      * [DenoisingAutoEncoderLoss](../package_reference/sentence_transformer/losses.html#denoisingautoencoderloss)
      * [GISTEmbedLoss](../package_reference/sentence_transformer/losses.html#gistembedloss)
      * [CachedGISTEmbedLoss](../package_reference/sentence_transformer/losses.html#cachedgistembedloss)
      * [GlobalOrthogonalRegularizationLoss](../package_reference/sentence_transformer/losses.html#globalorthogonalregularizationloss)
      * [EmbedDistillLoss](../package_reference/sentence_transformer/losses.html#embeddistillloss)
      * [MSELoss](../package_reference/sentence_transformer/losses.html#mseloss)
      * [MarginMSELoss](../package_reference/sentence_transformer/losses.html#marginmseloss)
      * [MatryoshkaLoss](../package_reference/sentence_transformer/losses.html#matryoshkaloss)
      * [Matryoshka2dLoss](../package_reference/sentence_transformer/losses.html#matryoshka2dloss)
      * [AdaptiveLayerLoss](../package_reference/sentence_transformer/losses.html#adaptivelayerloss)
      * [MegaBatchMarginLoss](../package_reference/sentence_transformer/losses.html#megabatchmarginloss)
      * [MultipleNegativesRankingLoss](../package_reference/sentence_transformer/losses.html#multiplenegativesrankingloss)
      * [CachedMultipleNegativesRankingLoss](../package_reference/sentence_transformer/losses.html#cachedmultiplenegativesrankingloss)
      * [MultipleNegativesSymmetricRankingLoss](../package_reference/sentence_transformer/losses.html#multiplenegativessymmetricrankingloss)
      * [CachedMultipleNegativesSymmetricRankingLoss](../package_reference/sentence_transformer/losses.html#cachedmultiplenegativessymmetricrankingloss)
      * [SoftmaxLoss](../package_reference/sentence_transformer/losses.html#softmaxloss)
      * [TripletLoss](../package_reference/sentence_transformer/losses.html#tripletloss)
      * [DistillKLDivLoss](../package_reference/sentence_transformer/losses.html#distillkldivloss)
    * [Evaluation](../package_reference/sentence_transformer/evaluation.html)
      * [BinaryClassificationEvaluator](../package_reference/sentence_transformer/evaluation.html#binaryclassificationevaluator)
      * [EmbeddingSimilarityEvaluator](../package_reference/sentence_transformer/evaluation.html#embeddingsimilarityevaluator)
      * [InformationRetrievalEvaluator](../package_reference/sentence_transformer/evaluation.html#informationretrievalevaluator)
      * [NanoBEIREvaluator](../package_reference/sentence_transformer/evaluation.html#nanobeirevaluator)
      * [MSEEvaluator](../package_reference/sentence_transformer/evaluation.html#mseevaluator)
      * [ParaphraseMiningEvaluator](../package_reference/sentence_transformer/evaluation.html#paraphraseminingevaluator)
      * [RerankingEvaluator](../package_reference/sentence_transformer/evaluation.html#rerankingevaluator)
      * [TranslationEvaluator](../package_reference/sentence_transformer/evaluation.html#translationevaluator)
      * [TripletEvaluator](../package_reference/sentence_transformer/evaluation.html#tripletevaluator)
    * [Datasets](../package_reference/sentence_transformer/datasets.html)
      * [ParallelSentencesDataset](../package_reference/sentence_transformer/datasets.html#parallelsentencesdataset)
      * [SentenceLabelDataset](../package_reference/sentence_transformer/datasets.html#sentencelabeldataset)
      * [DenoisingAutoEncoderDataset](../package_reference/sentence_transformer/datasets.html#denoisingautoencoderdataset)
      * [NoDuplicatesDataLoader](../package_reference/sentence_transformer/datasets.html#noduplicatesdataloader)
    * [Modules](../package_reference/sentence_transformer/modules.html)
      * [Main Modules](../package_reference/sentence_transformer/modules.html#main-modules)
      * [Further Modules](../package_reference/sentence_transformer/modules.html#further-modules)
  * [Cross Encoder](../package_reference/cross_encoder/index.html)
    * [CrossEncoder](../package_reference/cross_encoder/model.html)
      * [CrossEncoder](../package_reference/cross_encoder/model.html#id1)
      * [CrossEncoderModelCardData](../package_reference/cross_encoder/model.html#crossencodermodelcarddata)
    * [Trainer](../package_reference/cross_encoder/trainer.html)
      * [CrossEncoderTrainer](../package_reference/cross_encoder/trainer.html#crossencodertrainer)
    * [Training Arguments](../package_reference/cross_encoder/training_args.html)
      * [CrossEncoderTrainingArguments](../package_reference/cross_encoder/training_args.html#crossencodertrainingarguments)
    * [Losses](../package_reference/cross_encoder/losses.html)
      * [ADRMSELoss](../package_reference/cross_encoder/losses.html#adrmseloss)
      * [BinaryCrossEntropyLoss](../package_reference/cross_encoder/losses.html#binarycrossentropyloss)
      * [CrossEntropyLoss](../package_reference/cross_encoder/losses.html#crossentropyloss)
      * [LambdaLoss](../package_reference/cross_encoder/losses.html#lambdaloss)
      * [ListMLELoss](../package_reference/cross_encoder/losses.html#listmleloss)
      * [PListMLELoss](../package_reference/cross_encoder/losses.html#plistmleloss)
      * [ListNetLoss](../package_reference/cross_encoder/losses.html#listnetloss)
      * [MultipleNegativesRankingLoss](../package_reference/cross_encoder/losses.html#multiplenegativesrankingloss)
      * [CachedMultipleNegativesRankingLoss](../package_reference/cross_encoder/losses.html#cachedmultiplenegativesrankingloss)
      * [MSELoss](../package_reference/cross_encoder/losses.html#mseloss)
      * [MarginMSELoss](../package_reference/cross_encoder/losses.html#marginmseloss)
      * [RankNetLoss](../package_reference/cross_encoder/losses.html#ranknetloss)
    * [Evaluation](../package_reference/cross_encoder/evaluation.html)
      * [CrossEncoderRerankingEvaluator](../package_reference/cross_encoder/evaluation.html#crossencoderrerankingevaluator)
      * [CrossEncoderNanoBEIREvaluator](../package_reference/cross_encoder/evaluation.html#crossencodernanobeirevaluator)
      * [CrossEncoderClassificationEvaluator](../package_reference/cross_encoder/evaluation.html#crossencoderclassificationevaluator)
      * [CrossEncoderCorrelationEvaluator](../package_reference/cross_encoder/evaluation.html#crossencodercorrelationevaluator)
    * [Modules](../package_reference/cross_encoder/modules.html)
      * [LogitScore](../package_reference/cross_encoder/modules.html#logitscore)
  * [Sparse Encoder](../package_reference/sparse_encoder/index.html)
    * [SparseEncoder](../package_reference/sparse_encoder/model.html)
      * [SparseEncoder](../package_reference/sparse_encoder/model.html#id1)
      * [SparseEncoderModelCardData](../package_reference/sparse_encoder/model.html#sparseencodermodelcarddata)
    * [Trainer](../package_reference/sparse_encoder/trainer.html)
      * [SparseEncoderTrainer](../package_reference/sparse_encoder/trainer.html#sparseencodertrainer)
    * [Training Arguments](../package_reference/sparse_encoder/training_args.html)
      * [SparseEncoderTrainingArguments](../package_reference/sparse_encoder/training_args.html#sparseencodertrainingarguments)
    * [Losses](../package_reference/sparse_encoder/losses.html)
      * [SpladeLoss](../package_reference/sparse_encoder/losses.html#spladeloss)
      * [CachedSpladeLoss](../package_reference/sparse_encoder/losses.html#cachedspladeloss)
      * [FlopsLoss](../package_reference/sparse_encoder/losses.html#flopsloss)
      * [CSRLoss](../package_reference/sparse_encoder/losses.html#csrloss)
      * [CSRReconstructionLoss](../package_reference/sparse_encoder/losses.html#csrreconstructionloss)
      * [SparseMultipleNegativesRankingLoss](../package_reference/sparse_encoder/losses.html#sparsemultiplenegativesrankingloss)
      * [SparseMarginMSELoss](../package_reference/sparse_encoder/losses.html#sparsemarginmseloss)
      * [SparseDistillKLDivLoss](../package_reference/sparse_encoder/losses.html#sparsedistillkldivloss)
      * [SparseTripletLoss](../package_reference/sparse_encoder/losses.html#sparsetripletloss)
      * [SparseCosineSimilarityLoss](../package_reference/sparse_encoder/losses.html#sparsecosinesimilarityloss)
      * [SparseCoSENTLoss](../package_reference/sparse_encoder/losses.html#sparsecosentloss)
      * [SparseAnglELoss](../package_reference/sparse_encoder/losses.html#sparseangleloss)
      * [SparseMSELoss](../package_reference/sparse_encoder/losses.html#sparsemseloss)
    * [Samplers](../package_reference/base/sampler.html)
      * [BatchSamplers](../package_reference/base/sampler.html#batchsamplers)
      * [MultiDatasetBatchSamplers](../package_reference/base/sampler.html#multidatasetbatchsamplers)
    * [Evaluation](../package_reference/sparse_encoder/evaluation.html)
      * [SparseInformationRetrievalEvaluator](../package_reference/sparse_encoder/evaluation.html#sparseinformationretrievalevaluator)
      * [SparseNanoBEIREvaluator](../package_reference/sparse_encoder/evaluation.html#sparsenanobeirevaluator)
      * [SparseEmbeddingSimilarityEvaluator](../package_reference/sparse_encoder/evaluation.html#sparseembeddingsimilarityevaluator)
      * [SparseBinaryClassificationEvaluator](../package_reference/sparse_encoder/evaluation.html#sparsebinaryclassificationevaluator)
      * [SparseTripletEvaluator](../package_reference/sparse_encoder/evaluation.html#sparsetripletevaluator)
      * [SparseRerankingEvaluator](../package_reference/sparse_encoder/evaluation.html#sparsererankingevaluator)
      * [SparseTranslationEvaluator](../package_reference/sparse_encoder/evaluation.html#sparsetranslationevaluator)
      * [SparseMSEEvaluator](../package_reference/sparse_encoder/evaluation.html#sparsemseevaluator)
      * [ReciprocalRankFusionEvaluator](../package_reference/sparse_encoder/evaluation.html#reciprocalrankfusionevaluator)
    * [Modules](../package_reference/sparse_encoder/modules.html)
      * [SPLADE Pooling](../package_reference/sparse_encoder/modules.html#splade-pooling)
      * [SparseAutoEncoder](../package_reference/sparse_encoder/modules.html#sparseautoencoder)
      * [SparseStaticEmbedding](../package_reference/sparse_encoder/modules.html#sparsestaticembedding)
    * [Callbacks](../package_reference/sparse_encoder/callbacks.html)
      * [SpladeRegularizerWeightSchedulerCallback](../package_reference/sparse_encoder/callbacks.html#spladeregularizerweightschedulercallback)
    * [Search Engines](../package_reference/sparse_encoder/search_engines.html)
      * [`semantic_search_elasticsearch()`](../package_reference/sparse_encoder/search_engines.html#sentence_transformers.sparse_encoder.search_engines.semantic_search_elasticsearch)
      * [`semantic_search_opensearch()`](../package_reference/sparse_encoder/search_engines.html#sentence_transformers.sparse_encoder.search_engines.semantic_search_opensearch)
      * [`semantic_search_qdrant()`](../package_reference/sparse_encoder/search_engines.html#sentence_transformers.sparse_encoder.search_engines.semantic_search_qdrant)
      * [`semantic_search_seismic()`](../package_reference/sparse_encoder/search_engines.html#sentence_transformers.sparse_encoder.search_engines.semantic_search_seismic)
  * [Base](../package_reference/base/index.html)
    * [Model](../package_reference/base/model.html)
      * [BaseModel](../package_reference/base/model.html#basemodel)
      * [BaseModelCardData](../package_reference/base/model.html#basemodelcarddata)
    * [Trainer](../package_reference/base/trainer.html)
      * [BaseTrainer](../package_reference/base/trainer.html#basetrainer)
    * [Training Arguments](../package_reference/base/training_args.html)
      * [BaseTrainingArguments](../package_reference/base/training_args.html#basetrainingarguments)
    * [Samplers](../package_reference/base/sampler.html)
      * [BatchSamplers](../package_reference/base/sampler.html#batchsamplers)
      * [MultiDatasetBatchSamplers](../package_reference/base/sampler.html#multidatasetbatchsamplers)
    * [Modules](../package_reference/base/modules.html)
      * [Common Modules](../package_reference/base/modules.html#common-modules)
      * [Base Modules](../package_reference/base/modules.html#base-modules)
    * [Evaluation](../package_reference/base/evaluation.html)
      * [`BaseEvaluator`](../package_reference/base/evaluation.html#sentence_transformers.base.evaluation.BaseEvaluator)
      * [`SequentialEvaluator`](../package_reference/base/evaluation.html#sentence_transformers.base.evaluation.SequentialEvaluator)
  * [Utility Functions](../package_reference/util/index.html)
    * [distributed](../package_reference/util/distributed.html)
      * [`all_gather()`](../package_reference/util/distributed.html#sentence_transformers.util.distributed.all_gather)
      * [`all_gather_with_grad()`](../package_reference/util/distributed.html#sentence_transformers.util.distributed.all_gather_with_grad)
    * [environment](../package_reference/util/environment.html)
      * [`check_package_availability()`](../package_reference/util/environment.html#sentence_transformers.util.environment.check_package_availability)
      * [`get_device_name()`](../package_reference/util/environment.html#sentence_transformers.util.environment.get_device_name)
      * [`is_accelerate_available()`](../package_reference/util/environment.html#sentence_transformers.util.environment.is_accelerate_available)
      * [`is_datasets_available()`](../package_reference/util/environment.html#sentence_transformers.util.environment.is_datasets_available)
      * [`is_dist_initialized()`](../package_reference/util/environment.html#sentence_transformers.util.environment.is_dist_initialized)
      * [`is_training_available()`](../package_reference/util/environment.html#sentence_transformers.util.environment.is_training_available)
      * [`suggest_extra_on_exception()`](../package_reference/util/environment.html#sentence_transformers.util.environment.suggest_extra_on_exception)
    * [file_io](../package_reference/util/file_io.html)
      * [`disabled_tqdm`](../package_reference/util/file_io.html#sentence_transformers.util.file_io.disabled_tqdm)
      * [`http_get()`](../package_reference/util/file_io.html#sentence_transformers.util.file_io.http_get)
      * [`is_sentence_transformer_model()`](../package_reference/util/file_io.html#sentence_transformers.util.file_io.is_sentence_transformer_model)
      * [`load_dir_path()`](../package_reference/util/file_io.html#sentence_transformers.util.file_io.load_dir_path)
      * [`load_file_path()`](../package_reference/util/file_io.html#sentence_transformers.util.file_io.load_file_path)
    * [hard_negatives](../package_reference/util/hard_negatives.html)
      * [`mine_hard_negatives()`](../package_reference/util/hard_negatives.html#sentence_transformers.util.hard_negatives.mine_hard_negatives)
    * [misc](../package_reference/util/misc.html)
      * [`disable_datasets_caching()`](../package_reference/util/misc.html#sentence_transformers.util.misc.disable_datasets_caching)
      * [`disable_logging()`](../package_reference/util/misc.html#sentence_transformers.util.misc.disable_logging)
      * [`fullname()`](../package_reference/util/misc.html#sentence_transformers.util.misc.fullname)
      * [`import_from_string()`](../package_reference/util/misc.html#sentence_transformers.util.misc.import_from_string)
      * [`import_module_class()`](../package_reference/util/misc.html#sentence_transformers.util.misc.import_module_class)
    * [quantization](../package_reference/util/quantization.html)
      * [`quantize_embeddings()`](../package_reference/util/quantization.html#sentence_transformers.util.quantization.quantize_embeddings)
      * [`semantic_search_faiss()`](../package_reference/util/quantization.html#sentence_transformers.util.quantization.semantic_search_faiss)
      * [`semantic_search_usearch()`](../package_reference/util/quantization.html#sentence_transformers.util.quantization.semantic_search_usearch)
    * [retrieval](../package_reference/util/retrieval.html)
      * [`community_detection()`](../package_reference/util/retrieval.html#sentence_transformers.util.retrieval.community_detection)
      * [`information_retrieval()`](../package_reference/util/retrieval.html#sentence_transformers.util.retrieval.information_retrieval)
      * [`paraphrase_mining()`](../package_reference/util/retrieval.html#sentence_transformers.util.retrieval.paraphrase_mining)
      * [`paraphrase_mining_embeddings()`](../package_reference/util/retrieval.html#sentence_transformers.util.retrieval.paraphrase_mining_embeddings)
      * [`semantic_search()`](../package_reference/util/retrieval.html#sentence_transformers.util.retrieval.semantic_search)
    * [similarity](../package_reference/util/similarity.html)
      * [`SimilarityFunction`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.SimilarityFunction)
      * [`cos_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.cos_sim)
      * [`dot_score()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.dot_score)
      * [`euclidean_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.euclidean_sim)
      * [`manhattan_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.manhattan_sim)
      * [`pairwise_angle_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.pairwise_angle_sim)
      * [`pairwise_cos_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.pairwise_cos_sim)
      * [`pairwise_dot_score()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.pairwise_dot_score)
      * [`pairwise_euclidean_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.pairwise_euclidean_sim)
      * [`pairwise_manhattan_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.pairwise_manhattan_sim)
      * [`pytorch_cos_sim()`](../package_reference/util/similarity.html#sentence_transformers.util.similarity.pytorch_cos_sim)
    * [tensor](../package_reference/util/tensor.html)
      * [`batch_to_device()`](../package_reference/util/tensor.html#sentence_transformers.util.tensor.batch_to_device)
      * [`compute_count_vector()`](../package_reference/util/tensor.html#sentence_transformers.util.tensor.compute_count_vector)
      * [`normalize_embeddings()`](../package_reference/util/tensor.html#sentence_transformers.util.tensor.normalize_embeddings)
      * [`select_max_active_dims()`](../package_reference/util/tensor.html#sentence_transformers.util.tensor.select_max_active_dims)
      * [`truncate_embeddings()`](../package_reference/util/tensor.html#sentence_transformers.util.tensor.truncate_embeddings)



__[Sentence Transformers](../../index.html)

  * [](../../index.html)
  * Pretrained Models
  * [ Edit on GitHub](https://github.com/huggingface/sentence-transformers/blob/main/docs/cross_encoder/pretrained_models.md)



* * *

# Pretrained Models

We have released various pre-trained Cross Encoder models via our Cross Encoder Hugging Face organization. Additionally, numerous community Cross Encoder models have been publicly released on the Hugging Face Hub.

  * **Original models** : [Cross Encoder Hugging Face organization](https://huggingface.co/models?library=sentence-transformers&author=cross-encoder).

  * **Community models** : [All Cross Encoder models on Hugging Face](https://huggingface.co/models?library=sentence-transformers&pipeline_tag=text-ranking).




Each of these models can be easily downloaded and used like so:
    
    
    from sentence_transformers import CrossEncoder
    import torch
    
    # Load https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2
    model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2", activation_fn=torch.nn.Sigmoid())
    scores = model.predict([
        ("How many people live in Berlin?", "Berlin had a population of 3,520,031 registered inhabitants in an area of 891.82 square kilometers."),
        ("How many people live in Berlin?", "Berlin is well known for its museums."),
    ])
    # => array([0.9998173 , 0.01312432], dtype=float32)
    

Cross-Encoders require pairs as inputs and output a score (0 to 1 if the Sigmoid activation function is used). Most models work with text pairs, but some also support non-text inputs such as images (see Multimodal Rerankers). Cross-Encoders do not work for individual sentences and they don’t compute embeddings for individual texts.

## MS MARCO

[MS MARCO Passage Retrieval](https://github.com/microsoft/MSMARCO-Passage-Ranking) is a large dataset with real user queries from Bing search engine with annotated relevant text passages. Models trained on this dataset are very effective as rerankers for search systems.

Note

You can initialize these models with `activation_fn=torch.nn.Sigmoid()` to force the model to return scores between 0 and 1. Otherwise, the raw value can reasonably range between -10 and 10.

Model Name | NDCG@10 (TREC DL 19) | MRR@10 (MS Marco Dev) | Docs / Sec  
---|---|---|---  
[cross-encoder/ms-marco-TinyBERT-L2-v2](https://huggingface.co/cross-encoder/ms-marco-TinyBERT-L2) | 69.84 | 32.56 | 9000  
[cross-encoder/ms-marco-MiniLM-L2-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L2-v2) | 71.01 | 34.85 | 4100  
[cross-encoder/ms-marco-MiniLM-L4-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L4-v2) | 73.04 | 37.70 | 2500  
**[cross-encoder/ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)** | 74.30 | 39.01 | 1800  
[cross-encoder/ms-marco-MiniLM-L12-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L12-v2) | 74.31 | 39.02 | 960  
[cross-encoder/ms-marco-electra-base](https://huggingface.co/cross-encoder/ms-marco-electra-base) | 71.99 | 36.41 | 340  
  
For details on the usage, see [Retrieve & Re-Rank](../../examples/sentence_transformer/applications/retrieve_rerank/README.html).

## SQuAD (QNLI)

QNLI is based on the [SQuAD dataset](https://rajpurkar.github.io/SQuAD-explorer/) ([HF](https://huggingface.co/datasets/rajpurkar/squad)) and was introduced by the [GLUE Benchmark](https://huggingface.co/papers/1804.07461) ([HF](https://huggingface.co/datasets/nyu-mll/glue)). Given a passage from Wikipedia, annotators created questions that are answerable by that passage. These models output higher scores if a passage answers a question.

Model Name | Accuracy on QNLI dev set  
---|---  
[cross-encoder/qnli-distilroberta-base](https://huggingface.co/cross-encoder/qnli-distilroberta-base) | 90.96  
[cross-encoder/qnli-electra-base](https://huggingface.co/cross-encoder/qnli-electra-base) | 93.21  
  
## STSbenchmark

The following models can be used like this:
    
    
    from sentence_transformers import CrossEncoder
    
    model = CrossEncoder("cross-encoder/stsb-roberta-base")
    scores = model.predict([("It's a wonderful day outside.", "It's so sunny today!"), ("It's a wonderful day outside.", "He drove to work earlier.")])
    # => array([0.60443085, 0.00240758], dtype=float32)
    

They return a score 0…1 indicating the semantic similarity of the given sentence pair.

Model Name | STSbenchmark Test Performance  
---|---  
[cross-encoder/stsb-TinyBERT-L4](https://huggingface.co/cross-encoder/stsb-TinyBERT-L4) | 85.50  
[cross-encoder/stsb-distilroberta-base](https://huggingface.co/cross-encoder/stsb-distilroberta-base) | 87.92  
[cross-encoder/stsb-roberta-base](https://huggingface.co/cross-encoder/stsb-roberta-base) | 90.17  
[cross-encoder/stsb-roberta-large](https://huggingface.co/cross-encoder/stsb-roberta-large) | 91.47  
  
## Quora Duplicate Questions

These models have been trained on the [Quora duplicate questions dataset](https://huggingface.co/datasets/sentence-transformers/quora-duplicates). They can used like the STSb models and give a score 0…1 indicating the probability that two questions are duplicate questions.

Model Name | Average Precision dev set  
---|---  
[cross-encoder/quora-distilroberta-base](https://huggingface.co/cross-encoder/quora-distilroberta-base) | 87.48  
[cross-encoder/quora-roberta-base](https://huggingface.co/cross-encoder/quora-roberta-base) | 87.80  
[cross-encoder/quora-roberta-large](https://huggingface.co/cross-encoder/quora-roberta-large) | 87.91  
  
Note

The model don’t work for question similarity. The question “How to learn Java?” and “How to learn Python?” will get a low score, as these questions are not duplicates. For question similarity, a [`SentenceTransformer`](../package_reference/sentence_transformer/model.html#sentence_transformers.sentence_transformer.model.SentenceTransformer "sentence_transformers.sentence_transformer.model.SentenceTransformer") trained on the Quora dataset will yield much more meaningful results.

## NLI

Given two sentences, are these contradicting each other, entailing one the other or are these neutral? The following models were trained on the [SNLI](https://huggingface.co/datasets/stanfordnlp/snli) and [MultiNLI](https://huggingface.co/datasets/nyu-mll/multi_nli) datasets.

Model Name | Accuracy on MNLI mismatched set  
---|---  
[cross-encoder/nli-deberta-v3-base](https://huggingface.co/cross-encoder/nli-deberta-v3-base) | 90.04  
[cross-encoder/nli-deberta-base](https://huggingface.co/cross-encoder/nli-deberta-base) | 88.08  
[cross-encoder/nli-deberta-v3-xsmall](https://huggingface.co/cross-encoder/nli-deberta-v3-xsmall) | 87.77  
[cross-encoder/nli-deberta-v3-small](https://huggingface.co/cross-encoder/nli-deberta-v3-small) | 87.55  
[cross-encoder/nli-roberta-base](https://huggingface.co/cross-encoder/nli-roberta-base) | 87.47  
[cross-encoder/nli-MiniLM2-L6-H768](https://huggingface.co/cross-encoder/nli-MiniLM2-L6-H768) | 86.89  
[cross-encoder/nli-distilroberta-base](https://huggingface.co/cross-encoder/nli-distilroberta-base) | 83.98  
      
    
    from sentence_transformers import CrossEncoder
    
    model = CrossEncoder("cross-encoder/nli-deberta-v3-base")
    scores = model.predict([
        ("A man is eating pizza", "A man eats something"),
        ("A black race car starts up in front of a crowd of people.", "A man is driving down a lonely road."),
    ])
    
    # Convert scores to labels
    label_mapping = ["contradiction", "entailment", "neutral"]
    labels = [label_mapping[score_max] for score_max in scores.argmax(axis=1)]
    # => ['entailment', 'contradiction']
    

## Multimodal Rerankers

Multimodal rerankers can score pairs involving different modalities such as images, video, audio, and text. These models use the same [`Transformer`](../package_reference/base/modules.html#sentence_transformers.base.modules.Transformer "sentence_transformers.base.modules.Transformer") \+ [`LogitScore`](../package_reference/cross_encoder/modules.html#sentence_transformers.cross_encoder.modules.LogitScore "sentence_transformers.cross_encoder.modules.LogitScore") architecture as text-only decoder rerankers, but with a multimodal backbone that can process non-text inputs. You can check whether a model supports a given modality using [`modalities`](../package_reference/cross_encoder/model.html#sentence_transformers.cross_encoder.model.CrossEncoder.modalities "sentence_transformers.cross_encoder.model.CrossEncoder.modalities") and [`supports()`](../package_reference/cross_encoder/model.html#sentence_transformers.cross_encoder.model.CrossEncoder.supports "sentence_transformers.cross_encoder.model.CrossEncoder.supports").

See also

See the [Multimodal Embedding & Reranker Models](https://huggingface.co/blog/multimodal-sentence-transformers) blogpost for an inference walkthrough and an overview of the multimodal models supported at the time of writing.

Here are some community models:

  * [Qwen/Qwen3-VL-Reranker-2B](https://huggingface.co/Qwen/Qwen3-VL-Reranker-2B)

  * [Qwen/Qwen3-VL-Reranker-8B](https://huggingface.co/Qwen/Qwen3-VL-Reranker-8B)

  * [nvidia/llama-nemotron-rerank-vl-1b-v2](https://huggingface.co/nvidia/llama-nemotron-rerank-vl-1b-v2)

  * [jinaai/jina-reranker-m0](https://huggingface.co/jinaai/jina-reranker-m0)




See [Cross Encoder > Usage](usage/usage.html) for usage examples, and the training scripts in `examples/cross_encoder/training/multimodal/` to fine-tune your own multimodal reranker.

## Community Models

Some notable models from the Community include:

  * [BAAI/bge-reranker-base](https://huggingface.co/BAAI/bge-reranker-base)

  * [BAAI/bge-reranker-large](https://huggingface.co/BAAI/bge-reranker-large)

  * [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)

  * [BAAI/bge-reranker-v2-gemma](https://huggingface.co/BAAI/bge-reranker-v2-gemma)

  * [BAAI/bge-reranker-v2-minicpm-layerwise](https://huggingface.co/BAAI/bge-reranker-v2-minicpm-layerwise)

  * [jinaai/jina-reranker-v1-tiny-en](https://huggingface.co/jinaai/jina-reranker-v1-tiny-en)

  * [jinaai/jina-reranker-v1-turbo-en](https://huggingface.co/jinaai/jina-reranker-v1-turbo-en)

  * [mixedbread-ai/mxbai-rerank-xsmall-v1](https://huggingface.co/mixedbread-ai/mxbai-rerank-xsmall-v1)

  * [mixedbread-ai/mxbai-rerank-base-v1](https://huggingface.co/mixedbread-ai/mxbai-rerank-base-v1)

  * [mixedbread-ai/mxbai-rerank-large-v1](https://huggingface.co/mixedbread-ai/mxbai-rerank-large-v1)

  * [maidalun1020/bce-reranker-base_v1](https://huggingface.co/maidalun1020/bce-reranker-base_v1)

  * [Alibaba-NLP/gte-reranker-modernbert-base](https://huggingface.co/Alibaba-NLP/gte-reranker-modernbert-base)

  * [Alibaba-NLP/gte-multilingual-reranker-base](https://huggingface.co/Alibaba-NLP/gte-multilingual-reranker-base)




[ Previous](usage/efficiency.html "Speeding up Inference") [Next ](training_overview.html "Training Overview")

* * *

(C) Copyright 2026.

Built with [Sphinx](https://www.sphinx-doc.org/) using a [theme](https://github.com/readthedocs/sphinx_rtd_theme) provided by [Read the Docs](https://readthedocs.org). 
