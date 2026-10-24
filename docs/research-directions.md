# Research directions (after EXP0–EXP3)

Living document, started Sat 24 Oct 2026, morning. It records *why* each next experiment exists and what we would conclude from each outcome. Experiments that get run move to `docs/experiments/` with pre-registered hypotheses.

## Where we are

Haiku 5.5 doesn't collude in this market under any pressure, up to an explicit order from its principal. It refuses and escalates (EXP2). That blocks the pre-registered hypotheses that need collusion (H1, H2, H4, H5). Two results don't need collusion and are already solid: talk is unreliable evidence (EXP1), and the threat of enforcement chills legitimate passive balancing (EXP3). **These are the fallback story, a last resort.**

## D1. Multi-model collusion screen (backbone; **first step narrowed to one model, EXP5**)

*Update 24 Oct:* Stan chose to start with a single model, DeepSeek-V4-Flash (EXP5: the EXP2 gate replicated exactly), before any broader screen. The 6-model screen (EXP4) was withdrawn before completion.

**Question:** which models collude in the same market, and at which pressure level?
**Why:** it turns a single-model null into a cross-model comparison and removes the "one model family" limitation. Claude models are generally considered more aligned, so other families may behave differently.
**Design:** desk models via OpenRouter (OpenAI-compatible API), starting with cheap models (≈ $0.03–0.13 per run). The positive-control setting from EXP2 at levels `permission` and `explicit` serves as a **per-model gate**: only models that collude go on to the channel × enforcement grid (H1, H2, H4–H6) and the follow-ups below. The judge stays Haiku for every model, so detection is measured with one instrument.
**Reproducibility:** fixed temperature (0.7) where the model supports it, a per-run `seed` where supported, pinned provider (no fallbacks), and the provider and settings logged per call. This is "controlled and logged", not bit-identical: provider batching and some architectures are nondeterministic even at temperature 0. Some models reject `temperature` (e.g. OpenAI GPT-6-luna, Gemini batch variants), so we record that per model.
**Possible upgrade:** self-host open-weight models on Modal (vLLM) for exact control over weights and decoding. That only pays off if a specific open model becomes central.

## D2. Mixed-model markets: does single-model safety generalise to system safety? (high priority once D1 finds a colluder)

**Question:** Haiku doesn't collude in a market of Haiku agents. Does it start colluding, or at least go along, when the *other* firms are colluding models? One plausible motive: if it keeps bidding at cost while others are cartel bidders, it is the one losing share or equity.
**Why it matters:** if aligned agents hold out among their own kind but give in among colluders, then **single-model safety evaluations don't generalise to multi-agent system safety**, which is a clean, policy-relevant result. The opposite (Haiku refuses and reports, as it did against the *scripted* cartel in EXP1) is also informative: aligned agents act as whistle-blowers in a mixed market.
**Design:** firm A = Haiku (or vice versa), firms B and C = a colluding model from D1; compare against all-Haiku and all-colluder markets. Outcomes: Haiku's bid markup and leans over time, its private-channel replies (judge), reports or escalations. Needs per-firm model configuration.
**Note:** in this market, free-riding beats joining for the last firm in (scripted check, 23 Oct: C makes +32k free-riding next to A+B cartel bids vs +23k joining). So "Haiku joins" would be a strong signal of contagion beyond pure self-interest.

## D3. EXP1 with real LLM colluders (once D1 finds a colluder)

EXP1 used scripted colluders with canned posts, which makes talk detection artificially easy or hard. Real colluding agents' language is the realistic test of "talk is the wrong evidence" (H3, H5). Re-run the detection evaluation on D1 and D2 runs.

## D4. Reasoning on (fallback)

Only if no cheap model colludes: enable reasoning or thinking. Reasoning agents might find, or rationalise, collusive strategies (Riemer et al. 2026). Downsides: cost, and hidden reasoning isn't loggable.

## D5. Framing ablation (later, explanatory)

The same game in abstract terms (units, auction, no electricity, consumers or REMIT). This tests whether refusals come from recognising real-world harm. Cheap, but secondary.

## D6. Adopt an established setup (fallback if DeepSeek also refuses)

Stan, 24 Oct: if DeepSeek-V4-Flash also refuses under pressure (EXP5), the barrier is probably our market and framing rather than the model. Then we switch to, or port our questions onto, a setup with a known collusion baseline, e.g. one of Apart's sprint starter repositories (such as the Agrawal et al. double auction, where LLM sellers do collude). Our detection and enforcement layer (talk vs action, regulator, chilling) can be carried over.

## Not pursuing (for now)

- **Duopoly or simpler market:** tacit collusion is easier with two firms, but it changes the pre-registered design. Staying with 3 firms (Stan, 24 Oct).
- **Scripted seeded colluder ("contagion")** (Stan's idea, 23 Oct): superseded by D2, which uses natural LLM colluders.
