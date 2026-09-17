# Trainer Q&A — Week 07 · Wed · Build

My own prepared answers to the five trainer questions, before the next lecture.
Read these aloud in your own words — they are preparation, not a script.

---

## 1. Mechanically, why does the OpenAI Python client work against Ollama at all — what has to be true about Ollama's server for that to work?

The OpenAI Python client is just an HTTP client. Under the hood it sends a `POST`
request to `{base_url}/chat/completions` with a specific JSON body
(`model`, `messages`, ...) and parses a specific JSON response
(`choices[0].message.content`). For it to work against Ollama, three things must
be true about Ollama's server:

1. It must listen on a reachable address that we give as `base_url` (Ollama does:
   `http://localhost:11434/v1`), and it must accept HTTP requests, not just stdin.
2. It must implement the *same wire protocol* — the exact chat-completions request
   and response schema, at the path `/v1/chat/completions`, with the same field
   names and JSON types. It does, deliberately, so that any OpenAI-compatible
   tooling works against it untouched.
3. It must accept a key at all (any non-empty string). The client sends an
   `Authorization` header out of habit; Ollama doesn't validate it — it just needs
   to not reject it. A placeholder like `"ollama"` works.

Nothing about "being OpenAI's own server" matters. The client only needs a server
that speaks the contract at the configured address.

## 2. Walk through your shared ask_model function — what's the one thing that actually changes between your local call and your hosted call?

`ask_model(client, model, message)` builds one standard chat-completion request and
returns the reply — it has zero awareness of where the model runs. Between the two
endpoints, only two inputs differ:

- **`client`** — `get_client(use_local=True)` returns a client pointing at
  `localhost:11434/v1` with a placeholder key; `get_client(use_local=False)`
  returns one pointing at `api.groq.com/openai/v1` with the real key. The client
  *encodes the address (base_url) and credentials*.
- **`model`** — `llama3.2:3b` for local; `qwen/qwen3.8-27b` for hosted.

The things that stay identical: the request shape, the parsing, the error behaviour.
So the honest one-liner: **only the destination (encoded in the client's `base_url`)
and the model name vary — the code path is one and the same.**

## 3. What would have happened if you'd committed your .env before adding it to .gitignore — is removing it from a later commit enough to fix that?

Committing `.env` would put a live, billable secret into git **history**. Adding it
to `.gitignore` later only stops *future* commits from including it — the secret
would still sit in every past commit, recoverable by anyone with repository access
(`git log -p`, `git checkout <commit>`). On GitHub it is worse: once pushed, the
secret survives even force-push (GitHub retains reachable and often unreachable
commits to protect collaborator forks). Deleting the file in a later commit is **not**
enough. The only real fix, in order:

1. **Rotate the key immediately** — generate a new one and revoke the old. A
   committed secret must be treated as compromised, period.
2. Rewrite history to scrub it (`git filter-repo` / BFG / filter-branch), and
   force-push.
3. Add `.env` to `.gitignore` for the future.
4. In practice: for a key that was ever on GitHub, follow GitHub's secret-remediation
   guidance (key rotation + registry scrub), because old copies may live in forks,
   caches, and third-party scanners.

The lesson: the fix is **never** "just delete it from a later commit" — the key is
already burned.

## 4. In your own words, what does r control in a LoraConfig, and what would you expect if you set it very small versus very large?

`r` is the **rank** of the two low-rank update matrices (A and B) that LoRA trains
per layer instead of a full weight update. It directly controls how much
**capacity** (how many trainable parameters) the adapter has — the update is
approximated as `A·B`, so the number of trainable parameters per layer is
`r × (in_dim + out_dim)`, not `in_dim × out_dim`.

- **Very small `r`** (e.g. 2–4): tiny adapter — very cheap to train and store, but
  the low-rank approximation is too coarse to represent the needed behaviour change,
  so the model **underfits** the task (it can't "learn well enough").
- **Very large `r`** (e.g. hundreds): the adapter approaches a full-rank update —
  more expressive, closer to full fine-tuning quality, but memory and compute grow
  fast and the parameter-efficiency advantage is mostly gone. You pay near-full-tune
  costs for near-full-tune behaviour.

Typical practice: small values like 8–32 give a good capacity/cost trade-off.

## 5. Why does your test for ask_model use a fake client instead of actually calling Ollama or OpenAI — what specifically would be wrong with a test that made a real call?

A test hitting a real backend would be bad on five specific axes:

1. **Non-deterministic**: model output comes from sampling — you can't assert an
   exact expected reply, so the test can't verify your function's contract.
2. **Slow**: real network + inference latency, orders of magnitude slower than a
   mocked unit test.
3. **Brittle/flaky**: it requires a running Ollama server (or a hosted API), network
   access, a valid key, and rate-limit headroom at the moment tests run — fails in
   CI or offline even when your code is correct.
4. **Expensive**: a hosted call bills real money per run and hits rate limits;
   running tests should never spend.
5. **Wrong failure domain**: a failure would blame your code for what is actually a
   network/key/provider/model problem. You're not testing the model — you're testing
   *your* logic (correct request shape, right parsing, right error propagation). A
   `MagicMock` with a known fixed return isolates exactly that.