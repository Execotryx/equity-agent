# Ragas evaluation

Run 2026-10-02 21:24 UTC. Judge `claude-haiku-4-5`; answer-relevancy embeddings `sentence-transformers/all-MiniLM-L6-v2`. Reports generated fresh (agent caches cleared).

Samples scored: 35; skipped: 0; judge calls: 145, 292,918 input / 83,080 output tokens, about $0.708.

## By agent

| Agent | Samples | Faithfulness (mean) | Not scored | Answer relevancy (mean) |
|---|---|---|---|---|
| writer | 20 | 0.950 | 0 | 0.392 |
| analyst | 5 | 0.835 | 0 | 0.652 |
| risk | 5 | 0.724 | 0 | n/a |
| comps | 5 | 0.340 | 0 | n/a |
| **all** | 35 | 0.814 | 0 | 0.444 |

## By ticker

| Ticker | Signal | Faithfulness | Answer relevancy | Comps ready (s) | Signal ready (s) | Total (s) | LLM calls | Report cost |
|---|---|---|---|---|---|---|---|---|
| AAPL | HOLD | 0.795 | 0.435 | 6.6 | 15.6 | 15.6 | 4 | $0.082 |
| NVDA | BUY | 0.857 | 0.500 | 5.9 | 15.8 | 16.5 | 4 | $0.085 |
| JPM | BUY | 0.819 | 0.422 | 5.6 | 13.5 | 14.4 | 4 | $0.085 |
| COST | HOLD | 0.891 | 0.452 | 5.4 | 15.5 | 16.0 | 4 | $0.081 |
| TSLA | HOLD | 0.707 | 0.410 | 4.9 | 17.9 | 19.1 | 4 | $0.082 |

## Lowest faithfulness

- **AAPL comps/peers**: 0.214 (11 of 14 statements unsupported)
  - "MSFT (Microsoft Corporation) competes with Apple Inc. in Surface devices." — While Microsoft is mentioned as a competitor in personal computers, the context does not specifically mention Surface devices as a competitive product.
  - "MSFT (Microsoft Corporation) competes with Apple Inc. in operating systems." — The context mentions Microsoft as a competitor but does not specifically state that they compete in operating systems.
  - "MSFT (Microsoft Corporation) competes with Apple Inc. in cloud services." — The context mentions that Apple provides cloud services, and Microsoft is listed as a competitor, but the context does not explicitly state they compete in cloud services.
  - "GOOGL (Alphabet Inc.) offers Android as a rival to Apple's ecosystem." — The context mentions Google as a competitor that 'continuously innovate and strategize to challenge Apple's market dominance,' but does not specifically mention Android.
- **TSLA risk/risks**: 0.220 (32 of 41 statements unsupported)
  - "Weak adoption of electric vehicles would directly hurt Tesla, Inc.'s revenue." — While the context indicates that growth depends on demand for electric vehicles, it does not explicitly state that weak adoption would directly hurt revenue. The connection is implied but not directly stated.
  - "Weak adoption of electric vehicles would directly hurt Tesla, Inc.'s valuation." — The context does not explicitly state that weak adoption of electric vehicles would directly hurt valuation. This is an inference beyond what is directly stated.
  - "Weak adoption of autonomous driving would directly hurt Tesla, Inc.'s revenue." — While the context indicates that growth depends on adoption of autonomous driving, it does not explicitly state that weak adoption would directly hurt revenue.
  - "Weak adoption of autonomous driving would directly hurt Tesla, Inc.'s valuation." — The context does not explicitly state that weak adoption of autonomous driving would directly hurt valuation.
- **TSLA comps/peers**: 0.250 (12 of 16 statements unsupported)
  - "GM (General Motors Company) sells electric vehicles (EVs) and internal combustion engine (ICE) vehicles." — The context lists GM as an indirect competitor to Tesla and mentions it as a legacy automaker, but does not explicitly state that GM sells both EVs and ICE vehicles.
  - "GM (General Motors Company) sells vehicles to the same consumers as Tesla, Inc." — While the context indicates GM is a competitor to Tesla, it does not explicitly state that they sell to the same consumers. The context notes Tesla competes with luxury brands and ICE cars, but does not confirm identical consumer overlap.
  - "F (Ford Motor Company) competes in the electric vehicle (EV) market." — The context lists Ford as an indirect competitor to Tesla and a legacy automaker, but does not explicitly state that Ford competes in the EV market.
  - "F (Ford Motor Company) competes in the truck market." — The context does not provide information about Ford competing in the truck market.
- **JPM comps/peers**: 0.350 (13 of 20 statements unsupported)
  - "Bank of America Corporation (BAC) is the largest US diversified bank rival to JPMorgan Chase & Co." — The context states that Bank of America is JPMorgan Chase's biggest competitor in the US by total assets ($3.41 trillion), but JPMorgan Chase has $4.4 trillion in assets, making it larger. The statement claims BAC is the largest rival, which is not supported.
  - "Citigroup Inc. (C) is a global money-center bank." — The context lists Citigroup as a Banks - Diversified competitor with $186.35B market cap, but does not explicitly describe it as a global money-center bank.
  - "Citigroup Inc. (C) competes with JPMorgan Chase & Co. in credit cards." — JPMorgan Chase offers credit cards as part of its services. Citigroup is listed as a competitor in the Banks - Diversified subsector, but the context does not explicitly state that Citigroup competes in credit cards.
  - "Citigroup Inc. (C) competes with JPMorgan Chase & Co. in treasury services." — JPMorgan Chase offers cash management services. Citigroup is listed as a competitor, but the context does not explicitly state that Citigroup competes in treasury services.
- **NVDA comps/peers**: 0.385 (8 of 13 statements unsupported)
  - "AMD (Advanced Micro Devices, Inc.) is a direct rival of NVIDIA Corporation in gaming graphics cards." — While the context mentions AMD as a competitor to NVIDIA, it does not specifically state that AMD competes with NVIDIA in gaming graphics cards. The context focuses on data center and AI markets.
  - "AVGO (Broadcom Inc.) competes with NVIDIA Corporation for hyperscaler spending." — While the context identifies Broadcom as a competitor and mentions it is 'emerging as a major Nvidia competitor,' it does not explicitly state that Broadcom competes specifically for hyperscaler spending.
  - "INTC (Intel Corporation) competes with NVIDIA Corporation in AI accelerators." — The context identifies Intel as a primary hardware competitor and mentions that competitors are 'intensifying efforts in AI and data center markets,' but does not explicitly confirm Intel competes in AI accelerators specifically.
  - "INTC (Intel Corporation) competes with NVIDIA Corporation in discrete GPUs." — The context does not mention Intel competing with NVIDIA in discrete GPUs. The focus is on data center and AI markets.
- **COST comps/peers**: 0.500 (4 of 8 statements unsupported)
  - "Walmart Inc. (WMT) is the largest discount grocery and general merchandise rival to Costco Wholesale Corporation." — While the context identifies Walmart as a competitor with a market cap of $500B+, it does not explicitly state that Walmart is the largest rival or compare it as the primary competitor to Costco.
  - "PriceSmart, Inc. (PSMT) is a membership warehouse club operator in Central America and the Caribbean." — The context lists PriceSmart as a competitor but does not provide information about its geographic operations or specific regions served.
  - "PriceSmart, Inc. (PSMT) operates using the same business model as Costco Wholesale Corporation." — The context does not provide information about PriceSmart's business model or whether it operates similarly to Costco.
  - "The Kroger Co. (KR) is the largest US grocer." — The context lists Kroger as a competitor but does not state that it is the largest US grocer.
