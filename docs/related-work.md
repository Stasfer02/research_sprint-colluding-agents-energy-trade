# Related work & incidents — AI collusion in energy balancing markets

Compiled 23 Oct 2026 for the Apart AI Collusion Sprint project (LLM agents as BRP + BSP desks in a Dutch-style balancing market). Full source list at the bottom.

**Bottom line:** no documented case yet of AI agents colluding in an energy market. Three strands converge on our setup: (1) firms fined for gaming balancing and constraint mechanisms; (2) algorithms coordinating across firms in real markets, including grid batteries; (3) LLM agents colluding in lab markets and, in one real incident, building their own covert message board. A fourth strand — transparency and enforcement design — informs our experimental factors.

---

## 1. Energy incidents (single-firm manipulation at the balancing interface)

| Case | What happened | Relevance |
|---|---|---|
| Enron, California (2000–01) | "Load Shift": false load schedules created congestion, then Enron was paid to relieve it. "Fat Boy": over-scheduled load by 500–1,000 MW to be paid the real-time price. | Original "create the problem, get paid to fix it" |
| JPMorgan, US (FERC 2013, $410m) | Schedules swinging hour to hour raised CAISO/MISO ramping needs; the ISOs accepted JPM ramping bids up to $999/MWh (2010–12) | Exploiting how the operator procures flexibility |
| InterGen, GB (Ofgem, £37.3m) | Winter 2016: falsely told National Grid its plants wouldn't run in the evening peak; made ~£12.8m | Misleading the system operator to raise balancing costs; total ≈ 2.9× gain |
| Drax, GB (Ofgem, Jan 2023, £6.1m) | Pumped storage entered inflated balancing-mechanism bids when the grid was tight (2019–mid-2022) | Excess balancing rents |
| SSE, GB (Ofgem, Jul 2023, £9.78m) | Raised Foyers bid prices (May 2020) "to match what it believed other pumped storage operators charged" | Human tacit price-following |
| Germany, June 2019 (BNetzA 2021) | Energi Danmark €200k, Optimax €175k: sold intraday power they didn't have, leaving balancing groups short | BRP gaming the imbalance price; parallel conduct by several firms |
| Futugrid, Estonia (Oct 2026, €16k; appealable) | A bid meant never to be activated was activated and set the marginal balancing price | BSP bid setting the price |
| Netherlands, ACM (Jul 2026) | Several open cases on trading behaviour in the imbalance market; 21 signals in H1 2026; no fines | Our exact setting is under investigation |
| EU, ACER (2026) | Algorithms involved in ~60% of 42 suspicious-behaviour notifications; EPEX algorithmic share 44% → 70% (2020–24) | Algorithms are central to surveillance cases |

## 2. Algorithms coordinating across firms in real markets

| Case | Finding |
|---|---|
| German petrol (Assad et al., JPE 2024) | In duopoly/triopoly markets, margins rise only when all stations adopt algorithmic pricing |
| RealPage (DOJ settlement, Nov 2025) | Shared rent software using confidential data; remedy: no real-time data, non-public training data ≥ 1 year old; no admission |
| Australian batteries (Eschenbaum 2026) | Batteries on the same autobidder forgo dispatch that would hurt same-provider rivals (conduct parameter ≈ 1 when the provider holds ~30–70% of near-margin capacity) |

## 3. Research: algorithmic and LLM collusion in markets

| Paper | Key result |
|---|---|
| Calvano et al. (AER 2020) | Q-learning pricing algorithms learn supracompetitive prices without communicating, sustained by punishment |
| Fish et al. (2024) | LLM pricing agents reach supracompetitive prices; innocuous prompt wording changes how much |
| Lin et al. (2024) | LLM agents divide multi-commodity markets |
| Agrawal et al. (2025) | Double auction: seller messaging enables collusion; under monitoring, sellers tried emojis / one-character messages; urgency in the prompt led to success |
| Bracale Syrnikov et al. (2026) | Prompt-only anti-collusion text barely helps (high-tier collusion 50% → 44%); institutional enforcement (warnings, fines, suspensions) → 5.6% |
| Riemer et al. (ICML 2026 position) | Collusion risk among reasoning agents justifies certification before market decisions; repo has anti-collusion and "you are monitored" prompt variants |
| Seredynski & Tsaousoglou (2026) | RL generators on a 7-bus grid pass three tacit-collusion tests in 2 of 3 scenarios; the third is structural market power |
| Nguyen et al., TU/e (2025) | Dutch passive balancing: BRPs react simultaneously to the same signal, overloading some connection points |

## 4. Agents coordinating against oversight

| Case | What happened |
|---|---|
| Shi, Zhang & Yang (2026) | Shared-reward agents jointly violated a verification protocol in 93.6% of trajectories (10 models); separate rewards sharply reduced it; removing cross-episode memory nearly eliminated it |
| Shi et al. (2026, LLM-Trust-Breaking; as summarised on the sprint page) | In repeated n-player games, > 90% of deviations from public announcements were already stated in models' private plans |
| OpenAI / Hugging Face incident (Jul 2026) | 1,206 supposedly isolated agents used a package manager as a message board (70k+ messages); rebuilt it via directory names after it was cleared; 700+ took part in an attack on Hugging Face |

## 5. Transparency, signalling, enforcement and detection design

| Source | Point for our design |
|---|---|
| Albæk, Møllgaard & Overgaard (J. Industrial Economics 1997) — Danish ready-mix concrete | The competition authority published firm-specific prices from late 1993; prices rose 15–20% within a year. Mandated transparency can facilitate tacit collusion → our public board is a factor, not just a monitor (H1) |
| US v. Airline Tariff Publishing Co. (1994 consent decree) | Airlines used fares with future first-ticket dates as proposals, footnotes to link markets, and last-ticket dates to punish discounters. Model for "propose-and-match" signalling on a public board |
| EU container liner shipping commitments (2016) | Public price-increase announcements 3–5 weeks ahead let carriers align; remedy: announcements binding as maximum prices, ≤ 1 month ahead. Suggests a binding-vs-cheap-talk board arm |
| REMIT Art. 4 / ACER inside-information platforms | Real-world "public board": participants must promptly publish price-relevant inside information |
| REMIT Art. 18 (consolidated text) | Fines for market manipulation must at least equal the gain; ceilings expressed as % of annual turnover (15–20% per consolidated text — verify against the official text) |
| EU leniency programme | First cartel member to report gets full immunity; later applicants 30–50%, 20–30%, up to 20% off. Candidate add-on: does a leniency option break LLM coalitions? |
| Proz & Huber (2025) — ML for collusion and capacity withholding in Italian electricity markets | Screens (bid variance, CV, spread, lowest-bid gaps, offered/accepted quantities) classify two real cartels (Campania 2010 bid rotation in the balancing market; Brindisi 2016 withholding) with 79–99% accuracy. Template for our action detector |
| Becker (1968), economics of crime | A profit-maximiser deviates when audit probability × fine multiplier < 1 → audit-rate sweep as a rationality test |

## Gap

Nothing found combining LLM agents + imbalance settlement + one firm holding BRP and BSP roles under a compliance instruction, with transparency and enforcement as experimental factors.

---

## Sources

**Energy incidents**
- CAISO DMA report on Enron strategies — https://www.caiso.com/documents/chapterviii_29-apr-03.pdf
- JPMorgan FERC settlement — https://www.troutman.com/insights/jpmorgan-settles-ferc-manipulation-allegations-for-410-million.html
- Ofgem InterGen — https://www.ofgem.gov.uk/cy/press-release/ofgem-requires-intergen-pay-ps37m-over-energy-market-abuse
- Drax — https://www.energyvoice.com/renewables-energy-transition/grid-retail/475234/drax-fined-6-1m-for-charging-extreme-energy-prices/
- SSE — https://www.cityam.com/?p=2026802
- BNetzA fines (2021) — https://www.bundesnetzagentur.de/SharedDocs/Pressemitteilungen/EN/2021/20211005_BussgeldMarktmanipulation.html
- BNetzA proceedings (2020) — https://www.bundesnetzagentur.de/SharedDocs/Pressemitteilungen/EN/2020/20200907_Marktmanipulation.html
- Futugrid — https://www.lovguiden.dk/en/det-offentlige/eu-agenturet-for-samarbejde-mellem-energireguleringsmyndigheder/2026-10-14-estisk-boede-paa-16000-euro-for-manipulation-af-balanceringsmarkedet
- ACM REMIT update, Jul 2026 — https://www.acm.nl/system/files/documents/update-remit-indicatoren-juli-2026.pdf
- ACER REMIT Quarterly 45 summary — https://www.lovguiden.dk/en/det-offentlige/eu-agenturet-for-samarbejde-mellem-energireguleringsmyndigheder/2026-08-14-remit-algoritmisk-handel-og-markedsmanipulation-i-eu-energimarkeder
- TenneT balancing markets — https://www.tennet.eu/nl-en/markets/dutch-market/balancing-markets

**Algorithms across firms**
- Assad et al. — https://ideas.repec.org/a/ucp/jpolec/doi10.1086-726906.html
- RealPage — https://www.npr.org/2025/11/25/g-s1-99331/realpage-rent-algorithm-limits-settlement
- Eschenbaum — https://arxiv.org/pdf/2607.13002

**Research**
- Calvano et al. — https://www.aeaweb.org/doi/10.1257/aer.20190623
- Fish et al. — https://arxiv.org/pdf/2404.00806
- Lin et al. — https://arxiv.org/abs/2410.00031v1
- Agrawal et al. — https://arxiv.org/abs/2507.01413v1 · code: https://github.com/andyjliu/llm-agent-collusion
- Bracale Syrnikov et al. — https://arxiv.org/pdf/2601.11369
- Riemer et al. — https://arxiv.org/pdf/2608.18078 · code: https://github.com/mattriemer/LLMCartel
- Seredynski & Tsaousoglou — https://arxiv.org/pdf/2608.26896
- Nguyen et al. — https://arxiv.org/html/2511.13873v1

**Oversight evasion**
- Shi, Zhang & Yang — https://arxiv.org/pdf/2609.24967 · code: https://github.com/SALT-NLP/agent-collusion
- Sprint resources (incl. Shi et al. LLM-Trust-Breaking summary) — https://apartresearch.com/sprints/ai-collusion-research-sprint-2026-10-23-to-2026-10-25
- OpenAI / Hugging Face — https://infosecurity-magazine.com/news/openai-hugging-face-warning-shot

**Transparency, enforcement, detection**
- Albæk, Møllgaard & Overgaard — https://sites.duke.edu/collardwexler/files/2015/01/danish_concrete_cartel.pdf
- ATPCO proposed final judgment — https://www.govinfo.gov/content/pkg/FR-1994-03-31/html/94-7672.htm
- EU container shipping commitments — https://www.jdsupra.com/legalnews/european-commission-challenges-public-78269/
- ACER inside information — https://www.acer.europa.eu/remit/data-collection/inside-information-disclosure-and-collection
- REMIT Art. 18 (consolidated) — https://gesetze.legal/eu/vo_eu_2011_1227/18
- EU leniency — https://competition-policy.ec.europa.eu/cartels/leniency_en
- Proz & Huber — https://arxiv.org/pdf/2508.09885
