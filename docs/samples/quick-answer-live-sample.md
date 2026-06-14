<!-- Real ATLAS output: Quick Answer mode, generated live through the UI on 2026-06-12. Unedited. -->

# Sample output - Quick Answer mode (live run)

**Query:** What is speculative decoding and how much does it speed up LLM inference?

---

# What is speculative decoding and how much does it speed up LLM inference?

## Answer
Speculative decoding is a technique designed to accelerate inference in large language models (LLMs) by utilizing a smaller draft model to generate speculative tokens, which are then verified by the target LLM. This method can significantly reduce inference time, achieving speedups of up to 9.3 times compared to traditional inference engines [[3]](#source-3).

## Evidence
- Speculative decoding operates on a "Draft-then-Verify" paradigm, where multiple future tokens are drafted efficiently and then verified in parallel by the target LLM, enhancing overall inference speed [[4]](#source-4).
- In practical applications, LLMCad demonstrated a 9.3Ã speedup in on-device LLM inference by generating drafts with a smaller real-time model, minimizing the overhead of loading model weights [[3]](#source-3).
- The RaLMSpec framework applied speculative decoding to retrieval-augmented language models, achieving around 2Ã speedup by maintaining a local cache for speculative retrieval while ensuring identical model outputs [[3]](#source-3)[[4]](#source-4).
- The effectiveness of speculative decoding is influenced by the number of tokens accepted by the target model, which can affect the overall speedup achieved [[4]](#source-4).
- Recent studies indicate that combining speculative decoding with other techniques, such as Contrastive Decoding, can not only accelerate inference but also improve generation quality [[4]](#source-4).

## Caveats
While speculative decoding shows promise in accelerating LLM inference, the extent of speedup can vary based on the specific implementation and the characteristics of the models involved. Additionally, the performance gains may depend on the design of the draft model and the number of tokens processed, necessitating further empirical validation across different contexts and model architectures.

## Sources
- <span id="source-1" class="report-source-anchor"></span>[[1]](#source-1) [arXiv:2603.03251](https://arxiv.org/pdf/2603.03251)
- <span id="source-2" class="report-source-anchor"></span>[[2]](#source-2) [Decoding Speculative Decoding](https://arxiv.org/html/2402.01528v3)
- <span id="source-3" class="report-source-anchor"></span>[[3]](#source-3) [Accelerating inference in large language models with a unified layer skipping strategy](https://arxiv.org/html/2401.07851v2)
- <span id="source-4" class="report-source-anchor"></span>[[4]](#source-4) [arXiv:2410.06916](https://arxiv.org/html/2410.06916v2)
