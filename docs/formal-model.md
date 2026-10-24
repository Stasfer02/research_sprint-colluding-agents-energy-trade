# Formal model: the balancing market and the market-share threshold for intra-firm self-dealing

*Working document, Sat 24 Oct 2026. It describes the simulation exactly as the code implements it (`src/desks/market.py`, `src/desks/simulation.py`; design-spec §2 and §13). It also sets out the payoff algebra behind the question: **from what market share onward can a firm's trading desk and balancing desk profit by coordinating?** Propositions 1–3 are derived below (short proofs). The threshold itself (§6) depends on several parameters and is meant to be computed numerically (§7); its form is derived here.*

## 1. Primitives

| Symbol | Meaning | Baseline value |
|---|---|---|
| $i \in \{A,B,C\}$ | firms; each runs a **BRP desk** (trading position) and a **BSP desk** (balancing bids) | 3 firms, 6 agents |
| $t = 1..T$ | settlement periods | $T = 30$ |
| $\kappa$ | size of one balancing block (MW, per direction) | 20 MW |
| $n_i$ | number of blocks firm $i$ owns | 2 each (equal shares) |
| $K_i = n_i\kappa$, $K = \sum_i K_i$ | firm and total balancing capacity per direction | 40 MW each, $K = 120$ |
| $s_i = K_i / K$ | **market share** (of balancing capacity) | $1/3$ each |
| $c_{ik}$ | marginal cost of firm $i$'s block $k$ (up) | ≈ 70–80 €/MWh (§8) |
| $\lambda$ | day-ahead reference price | 60 €/MWh |
| $\bar P, \underline P$ | price cap and floor | 1000, −200 €/MWh |
| $D_i$ | max deliberate deviation of firm $i$'s BRP | 25 MW |
| $e_{it} \sim N(0, \sigma_f^2)$ | firm $i$'s forecast error (not chosen, not observed before acting) | $\sigma_f = 8$ MW |
| $r_t = \rho r_{t-1} + \varepsilon_t$, $\varepsilon_t \sim N(0, \sigma_r^2)$ | rest-of-market imbalance (all other parties) | $\rho = 0.6$, $\sigma_r = 25$ MW |

Assumption maintained throughout: **$c_{ik} > \lambda$ for upward energy.** Providing upward balancing costs more than the day-ahead value of energy. This is what makes a "round trip" (a firm creating a shortage and filling it itself) costly (Proposition 1).

## 2. Timing within a period

1. Nature draws $e_{it}$ and $r_t$.
2. Each BRP chooses a deviation $d_{it} \in [-D_i, D_i]$; each BSP submits one up-bid and one down-bid **per block** (€/MWh). Agents see information up to $t-1$ only (§5).
3. Positions: $x_{it} = e_{it} + d_{it}$ ($x > 0$ long). System imbalance $S_t = \sum_i x_{it} + r_t$.
4. The TSO (TenneT's role) clears the merit order (§3), and settlement follows (§4).
5. The TSO publishes $S_t$, $P_t$, the direction, and the anonymised merit order (bid prices, block sizes, activated MW, **no owners**). Public-board posts written in $t$ become visible in $t+1$.

## 3. Clearing (single price, pay-as-cleared)

Take a **short** period, $S_t < -\epsilon$ (the long case is symmetric with down-bids). The need is $N_t = -S_t$. Blocks are sorted by up-bid, ascending (ties broken at random), and activated in that order until $N_t$ is covered. The last activated block is **marginal**, and its bid sets the price $P_t$ that **every** activated block is paid and every short BRP pays. If $N_t > K$: everything is activated and $P_t = \bar P$. If $|S_t| \le \epsilon$: nothing is activated and $P_t$ = the midpoint of the best up-bid and the best down-bid.

Let $q_{it}$ be the MW of firm $i$'s blocks activated.

## 4. Settlement and profits

$$\pi^{BRP}_{it} = x_{it}(P_t - \lambda), \qquad \pi^{BSP}_{it} = \sum_k q_{ikt}\,(P_t - c_{ik}), \qquad \pi^{R}_t = r_t (P_t - \lambda).$$

The firm's profit is $\pi_{it} = \pi^{BRP}_{it} + \pi^{BSP}_{it}$. Writing $C_i(q)$ for the firm's cost of the activated volume,

$$\pi_{it} = P_t\,(q_{it} + x_{it}) - C_i(q_{it}) - \lambda x_{it}. \tag{1}$$

**Net exposure.** $E_{it} := q_{it} + x_{it}$ is the firm's net sale of balancing-period energy: balancing energy sold, plus BRP surplus. A higher price helps the firm iff $E_{it} > 0$.

The price is a transfer. In a short period, short positions (rest of market and short BRPs) pay $P_t$ per MWh of shortage to the activated blocks. Raising $P_t$ moves money from the short side to the activated BSPs, including the **rivals'** activated blocks. The **competitive benchmark** uses the same $e, r$, with $d = 0$ and every bid at cost. Excess profit = profit − benchmark profit; rest-of-market harm = $\pi^R - \pi^{R,\text{bench}}$.

## 5. Agents and information (baseline, Stan 24 Oct)

- **Six LLM agents**, one BRP and one BSP per firm. Both desks are told to maximise **their firm's** total profit. Firms are distinct: no shared owner, no channel between firms.
- **Public board:** every desk must post a short rationale each period. The TSO's market results (above) are public. **No internal channel** between a firm's desks in the baseline, so the BRP and BSP of a firm know about each other only through the public data and the shared profit figure.
- A BRP sees its own $d$, $x$ and BRP P&L, plus the firm's total profit. A BSP sees its own bids, activations and BSP P&L, plus the firm's total profit. **Never visible:** $e$, $r$, other firms' $d$, owners in the merit order.
- **No enforcement:** no fines, no compliance text. The prompts **never mention collusion**, neither as allowed nor as forbidden.

## 6. The self-dealing strategy and its payoff

**Self-dealing** = the BRP deliberately goes short ($d_{it} = -\delta$, $\delta > 0$) so that the system needs more balancing energy, while the BSP prices some of the firm's capacity high ("withholding") and earns the resulting high marginal price.

### Proposition 1 (gain decomposition)

Fix everything except firm $i$'s BRP deviation. Moving from $d$ to $d - \delta$ changes the outcome from $(P^0, q^0, x^0)$ to $(P^1, q^0 + \Delta q, x^0 - \delta)$, where $\Delta q \in [0, \delta]$ is the part of the extra need served by firm $i$'s own blocks at average cost $\bar c$. Then

$$\Delta\pi_i = \underbrace{(P^1 - P^0)\,E^0_i}_{\text{price effect on net exposure}} \;+\; \underbrace{(P^1 - \bar c)\,\Delta q - (P^1 - \lambda)\,\delta}_{\text{round trip}}. \tag{2}$$

If the firm serves the whole push itself ($\Delta q = \delta$):

$$\Delta\pi_i = (P^1 - P^0)\,E^0_i \;-\; (\bar c - \lambda)\,\delta. \tag{3}$$

*Proof:* substitute both outcomes into (1) and subtract. ∎

**Reading.** Each pushed MW is bought by the BRP at $P$ and sold by the BSP at $P$, so on the margin it nets $\lambda - \bar c < 0$. **A push can only pay through the price effect.** That requires (a) the push raises the marginal price ($P^1 > P^0$), and (b) the firm was a net seller before the push ($E^0_i > 0$). If rivals serve part of the push ($\Delta q < \delta$), each such MW costs the firm $P^1 - \lambda$, which is far worse at high prices.

### Proposition 2 (where the price can jump: reach and exposure)

Let firm $i$ bid its top $U_i$ MW at a high price $b$, above every other bid, and its remaining $L_i = K_i - U_i$ MW at cost. Let all rivals bid at cost. The withheld tranche is marginal iff $N > K - U_i$. Write $N^0$ for the need without the push. Then:

- **Withholding alone sets $P = b$** when $N^0 > K - U_i$. This is unilateral market power of the BSP desk; no coordination is needed, and the push only adds the round-trip cost.
- **The push is decisive** in the **reach window**
$$K - U_i - \delta \;<\; N^0 \;\le\; K - U_i, \tag{4}$$
where it lifts $P$ from $P^0 \approx$ cost to $b$. The gain in the window is $(b - P^0)\,E^0_i - (\bar c - \lambda)\delta$, where $E^0_i = q^0_i + x^0_i$ and $q^0_i \le L_i$ is the firm's activated *non-withheld* volume.
- **Outside the window** the push costs $(\bar c - \lambda)\delta$ (or more if rivals serve it) and gains nothing.

So intra-firm self-dealing needs **both** of the following:
1. **Reach:** withheld capacity close enough to the typical need, i.e. $K - U_i - D_i$ small relative to the distribution of $N$.
2. **Exposure:** enough non-withheld capacity actually dispatched, i.e. $L_i$ large and the firm's blocks early in the merit order.

**Both grow with the firm's size $K_i = s_i K$:** a larger firm can withhold more ($U_i$ larger, so the window moves down to frequent need levels) while keeping more inframarginal capacity ($L_i$ larger, so exposure is positive).

### Proposition 3 (single block: coordination never pays)

If each firm owns **one** block ($n_i = 1$), the BRP push never increases expected firm profit, at **any** market share. Market share then only affects whether *unilateral* withholding by the BSP pays.

*Proof sketch:* with one block, withholding means bidding the whole block at $b$ ($U_i = K_i$).
- **In the reach window (4):** the block is not yet activated, so $q^0_i = 0$ and $E^0_i = x^0_i = e_i$. The push activates $\Delta q \le \delta$ of the firm's block at $P^1 = b$, so by (2)
$\Delta\pi_i = (b - P^0)\,e_i + (b - \bar c)\Delta q - (b - \lambda)\delta \le (b - P^0)\,e_i - (\bar c - \lambda)\delta$.
The BRP does not observe $e_i$, which has mean zero (and is, if anything, negatively correlated with landing in the window, since a high $N^0$ goes with a low $e_i$). So the expected gain is at most $-(\bar c - \lambda)\delta < 0$.
- **Outside the window:** either the price does not move, or the withheld block is already marginal; in both cases (3) gives $-(\bar c - \lambda)\delta$.
- **Without withholding:** the push cannot lift the price to a bid of the firm's own. ∎

*Scope.* Proposition 3 assumes rival blocks are bid near cost. A push can also lift the price from one rival block to the next, more expensive one. The gain is then at most $\Delta c\,E^0_i$ per crossing, with $\Delta c$ the cost step between blocks (5 €/MWh in v1), against a certain round-trip cost of $(P^1 - \lambda)\delta$ per push. With v1's parameters this is negative in expectation: in the scripted check, a lone aggravator loses about €1.4k per run. It stops being negative if rivals' bids are spread far apart, for example when rivals themselves mark up (cross-firm behaviour).

**Consequence for the design.** The original market (v1: one 40 MW block per firm) makes two-desk self-dealing impossible *by construction*, at every market share. A share threshold for **coordination** can only appear if firms own **several blocks**. Then a large firm can keep inframarginal capacity *and* control the top of the merit order.

### The threshold

For a strategy $(U_i, \delta)$, the expected per-period value of the BRP push over withholding alone is

$$G_i(s_i) = \mathbb{E}\!\left[(b - P^0)\,E^0_i\;\mathbf{1}\{K - U_i - \delta < N^0 \le K - U_i\}\right] - (\bar c - \lambda)\,\delta\;\Pr(\text{short}) - \text{(cost of misses served by rivals)}, \tag{5}$$

where $N^0$'s distribution is conditional on what the BRP knows at decision time (essentially $S_{t-1}$, through $\rho$). Define the **coordination threshold**

$$s^\* = \min\{\, s : \max_{U \le sK,\; \delta \le D}\; G(s) > 0 \,\}$$

and, separately, the **withholding threshold** $s^{\dagger}$, the smallest share at which withholding alone beats bidding at cost. Both are functions of $(b, \bar P, \kappa, D, \sigma_r, \rho, \sigma_f, c - \lambda)$, not single numbers. Two qualitative predictions follow from (4)–(5):

- **Lower $K - U$ (a bigger firm) moves the reach window into the bulk of the need distribution.** With $\sigma_N \approx \sigma_r/\sqrt{1-\rho^2} \approx 31$ MW, a window starting at 75 MW (equal shares, top block withheld: $K - U = 100$, $D = 25$) is reached in about 1% of periods. A window starting at 35 MW (a firm with 80 of 120 MW withholding 60) is reached in about 13%.
- **Predictability raises $G$.** A BRP that pushes only when $S_{t-1}$ was strongly short concentrates its pushes in the window, so $G$ increases with $\rho$.

**Worked example** (checked by hand against the clearing rules). Rival capacity is 40 MW at 75 €/MWh. Firm $i$ has one 20 MW block bid at cost 70 and one withheld 20 MW block at $b = 300$. Need without the push $N^0 = 55$: the firm's 20 MW at 70 and 35 MW of the rival are activated, so $P^0 = 75$ and the firm earns 100. With a push $\delta = 10$, $N^1 = 65$: the withheld block becomes marginal, so $P^1 = 300$; the BSP earns $25 \times 230 = 5{,}750$ and the BRP pays $10 \times 240 = 2{,}400$. **Gain = 3,250**, which matches (2): $225 \times 20 + 230 \times 5 - 240 \times 10$. The rival gains 9,000.

## 7. Who gains and who loses

In a single-price market, a dominant firm's self-dealing **raises the price paid to every activated block**. Small rivals' balancing desks *gain* (in the example: +9,000; in the market-v2 gate, B and C gain about €5.5k per run each). The losers are the **short side**: the rest of the market (and short BRPs, including the small firms' own BRPs when they happen to be short). So "suffocating smaller parties" does **not** follow from this market design. It would need pay-as-bid pricing, capacity foreclosure, or small firms whose BRP portfolios are structurally short. Worth stating carefully in the report.

## 8. Open modelling choices (to settle before the share sweep)

1. **Blocks.** Equal-sized blocks, with market share = number of blocks owned (2/2/2 at baseline; then 3/2/1, 4/1/1, …). This keeps the merit order anonymous and makes share the single varied parameter.
2. **Costs.** v1 has firm-specific costs (A cheapest: 70 / 75 / 80). For a clean share effect, give every block the same cost ladder independent of owner, e.g. 70, 72, … by merit position (or identical costs with random tie-breaks). Otherwise "A is cheapest" confounds "A is biggest".
3. **BRP size.** Should a larger firm also have a larger trading portfolio ($D_i$, $\sigma_{f,i}$ proportional to $s_i$)? A larger $D_i$ widens the reach window (4) directly, so this choice moves $s^\*$.
4. **Bid cap $b$.** The gain scales with $b - P^0$; with $b$ up to the 1000 €/MWh cap, rare scarcity events dominate. Report results for the cap as is and for a lower cap (e.g. 300) as a robustness check.

## 9. Numerical verification

The scripted market computes $G(s)$ exactly for given policies. Plan: sweep $s_A \in \{2,3,4,5\}/6$ (with 6 blocks of 20 MW). For each share, compare four scripted profiles for firm A: cost bidding; withholding only; push only; and **push + withholding**, with the push conditioned on $S_{t-1}$. Read off $s^\dagger$ (withholding pays) and $s^\*$ (push + withholding beats withholding alone), across ≥ 300 seeds. This uses no API calls and gives the threshold curve the maths predicts.
