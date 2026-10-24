# Reasoning, stated rules and potentially manipulative behaviour of LLM agents in a simulated balancing market

*Report draft for the Apart Research AI Collusion Sprint (target 4–6 pages, about 2.5 for Methods and Results). Methods live in [methods.md](methods.md), so there is one version to edit. Results use `results/core/comparison.md`.*

## 1 Introduction

Integrated energy companies often run a trading desk, which is settled at the electricity imbalance price, and a balancing desk, whose bids help set that same price. If both desks are run by AI agents that share one profit objective, they may discover that moving the price for the firm pays. This would be market manipulation under EU rules (REMIT), even with no other firm involved.

We ask: **how do reasoning capabilities and stated regulatory constraints influence potentially manipulative behaviour among LLM agents in a simulated electricity balancing market?**

We compare three conditions with six LLM agents each:
- **baseline:** no reasoning;
- **reasoning:** high reasoning effort;
- **compliance:** reasoning plus a stated, unenforced prohibition.

## 2 Background

**Manipulation at the balancing interface.** Regulators have already fined manipulation at this interface: inflated balancing bids (Drax, SSE), misleading the system operator (InterGen), and a bid that set the marginal balancing price (Futugrid, 2026). The Dutch regulator has open cases on trading behaviour in the imbalance market. ACER reports that algorithms are involved in most suspicious-behaviour notifications.

**Algorithmic and LLM collusion.** Pricing algorithms and LLM agents can reach supracompetitive outcomes without explicit instruction (Calvano et al. 2020; Fish et al. 2024). Prompt-only anti-collusion text appears to help little compared with enforcement (Bracale Syrnikov et al. 2026).

**Our focus.** We study coordination *within* a firm, between two desks separated by an information barrier. Sources are in `docs/related-work.md`.

## 3 Methods

See [methods.md](methods.md) (about 500 words).

## 4 Results

*To be written once EXP9 is complete.*

Numbers and example posts come from `results/core/comparison.md`, and the figure from `results/core/figures/behaviour.png` (dots are runs; bars are condition means).

## 5 Discussion and limitations

The study is exploratory. Its scope is limited in six ways:

1. **Few runs.** There are five independent runs per condition. Differences are described, not tested for significance, and may not generalise to other models, prompts or markets.
2. **Stylised market.** One block per firm, synthetic shocks, a single price, and 30 periods. The market reproduces the incentive link between trading and balancing, not a real market design.
3. **Weak incentives at equal shares.** With equal capacities, one firm's bid sets a high price only when its rivals' capacity runs out. So deepening a shortage while bidding high rarely pays and often loses money. Behaviour of this kind therefore reflects how agents reason about the market more than a profitable strategy. Larger market shares would change this.
4. **Indicators are not evidence of collusion.** Aggravating deviations and markups are operational flags, computed with the simulation's internal record of each deliberate deviation, which a regulator would not see. Public posts that mention the other desk show communication, not an agreement. Demonstrating collusion would require stronger evidence.
5. **Conditions differ in more than one parameter.** EXP8 changes the reasoning setting together with the output limit and timeout. EXP9 adds the compliance text together with a "fine" column in the agents' tables, which is always zero. We therefore do not claim to have isolated the effect of reasoning or of rules.
6. **Rules stated, not enforced.** EXP9 tells agents about audits and fines that never happen. The text prohibits "collusion with other firms" and manipulation in general, but does not name coordination between a firm's own desks.

## 6 Conclusion

*To be written with the results.*

## Reproducibility

See the [README](../../README.md). All prompts, raw outputs, reasoning texts and run records are committed under `results/`.
