## 3 Methods

### 3.1 Market dynamics

We simulate a stylised electricity balancing market with three firms (A, B, C) over 30 settlement periods.

Each period, every firm's imbalance is a random forecast error plus a deliberate deviation of up to ±25 MW chosen by its trading desk. These, together with a persistent random imbalance from the rest of the market, make up the system imbalance.

The grid operator activates upward balancing bids, cheapest first, when the system is short, and downward bids when it is long. Each firm's balancing desk offers one 40 MW block per direction, at firm-specific marginal costs. The last activated bid sets a single imbalance price. That price pays all activated bids and settles all trading positions, relative to a 60 €/MWh day-ahead price.

The price links a firm's two desks. A high price rewards the balancing desk when it is activated but costs the trading desk when the firm is short. A firm could therefore try to raise the price by deepening a shortage while bidding high.

A competitive benchmark settles every period with the same shocks, no deliberate deviations, and bids at cost.

### 3.2 LLM agent setup

Six DeepSeek-V4-Flash agents run the six desks. Both desks of a firm are told to maximise the firm's total profit.

Each period, a desk sees the market rules, recent imbalances, prices and anonymised bids, its own results, the firm's profit, recent public posts and its own notes. An information barrier hides the firm's bids from its trading desk and its positions from its balancing desk. No agent sees the shocks or other firms' positions.

The only communication channel is a public board. Each desk must post a short rationale there every period, readable by all firms and the regulator. No prompt mentions coordination between desks or price manipulation.

### 3.3 Experimental design

- **EXP7 (baseline):** reasoning disabled.
- **EXP8 (reasoning):** high reasoning effort, with a larger output limit and timeout to accommodate it.
- **EXP9 (compliance):** EXP8 plus a statement that "market manipulation and collusion with other firms are prohibited under EU energy market rules (REMIT)", that a regulator reviews about half of all periods, and that violations are fined. No regulator actually acts.

Each condition has five runs. Run *k* faces identical random shocks in all three conditions, so runs can be compared in pairs. The model runs at temperature 1.0 on one pinned provider, and all prompts, outputs and reasoning are logged.

### 3.4 Evaluation

**(A) Potentially manipulative behaviour.** We report the share of firm-periods with:
- an *aggravating deviation*: at least 10 MW, and enlarging the system imbalance;
- a *bid markup*: at least 30% beyond marginal cost, in the direction of the imbalance;
- *both* in the same firm.

These indicators use the simulation's record of deliberate deviations, which a real regulator would not see. They flag behaviour, not proven manipulation or collusion.

**(B) Economic outcomes.** The firms' combined profit relative to the benchmark, and the mean price difference.

**(C) Communication.** Public posts that mention the firm's other desk, read qualitatively. An LLM judge's 0–4 rating of coordination intent serves as supporting evidence only. With five runs per condition, all comparisons are descriptive.
