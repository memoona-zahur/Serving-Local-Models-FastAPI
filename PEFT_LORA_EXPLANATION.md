# PEFT / LoRA — Written Explanation

*Task requirement: read the Hugging Face LoRA conceptual guide, then explain in your own
words what `r` and `target_modules` control, and why training a LoRA adapter is drastically
cheaper than a full fine-tune.*

---

`r` is the rank of the two small update matrices (A and B) that LoRA trains instead of the
full weight matrix — it literally sets how many parameters the adapter gets to store per layer,
so a small `r` (e.g. 4) means a tiny adapter with few trainable parameters and a cheap,
underpowered adaptation, while a very large `r` approaches a full matrix update and erases
most of the memory savings. `target_modules` controls *which* layers get these adapters
injected at all — typically the attention projections like `q_proj` and `v_proj` — and any
module left out stays 100% frozen, so the count of trainable parameters and the quality of
the adaptation both live or die on this list. Training is dramatically cheaper than a full
fine-tune because the base model's billions of weights are frozen (only their gradients are
skipped, so the optimizer never touches them) and we train just the few million parameters
inside the low-rank adapters, which is what makes the whole thing fit on a laptop.

---

## Config walkthrough (from today's lesson)

| Parameter | Value | What it actually controls |
|-----------|-------|---------------------------|
| `r=16` | rank of the low-rank update matrices | bigger `r` = more trainable params + more expressive adapter; smaller = cheaper |
| `lora_alpha=16` | scaling factor applied to the adapter's contribution | adapter output is scaled by `alpha / r` during the forward pass |
| `target_modules=["q_proj", "v_proj"]` | which layers get an adapter injected | only the query/value attention projections are adapted here; everything else stays frozen |
| `lora_dropout=0.1` | dropout on the adapter's activations | regularisation during training; no effect on the frozen base weights |
| `bias="none"` | whether bias terms are trained | `"none"` trains no bias → fewest trainable parameters |

## Why it's cheap (the numbers)

A full fine-tune updates every parameter of the model. A LoRA adapter on the same model
updates only `r × (in_dim + out_dim)` parameters per targeted layer. For a 7-billion-parameter
model, a typical LoRA adapter trains on the order of **millions** of parameters instead of
**billions** — that is the difference between needing many GPUs and fitting on a single
laptop-sized device.

## Key consequence (the portable adapter)

Because the base weights stay frozen and untouched, the trained adapter is portable: a tiny
file (often a few tens of MB) that can be exported, shipped to other machines, and even
dropped on *top of* a different copy of the same base model — you are never "copying" the
whole model, just the delta.