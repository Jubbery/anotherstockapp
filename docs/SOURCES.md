# Sources

Every externally-verifiable claim in `MASTER_SPEC.md`, with where it came from. Re-verify anything
time-sensitive before acting on it — this was compiled 2026-09-16 and the regulatory items in particular
are mid-transition.

## Regulation — the PDT retirement (spec §2.2)

- [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10)
- [SEC approval order, SR-FINRA-2025-017](https://www.sec.gov/files/rules/sro/finra/2026/34-105226.pdf) — approved 2026-04-14
- [Schwab: SEC Approves Scrapping $25,000 Day Trader Minimum](https://www.schwab.com/learn/story/sec-approves-scrapping-25000-day-trader-minimum)
- [FINRA: Understanding the New Intraday Margin Requirements](https://www.finra.org/investors/insights/intraday-margin-requirements)
- [E*TRADE: PDT Rule Change](https://us.etrade.com/knowledge/library/margin/pattern-day-trading-rule-change)

Effective 2026-06-04; firms have until 2027-10-20 to implement, so behaviour may vary by broker (R-2.2.c).

## Alpaca

- [FINRA Retires the PDT Rule: Alpaca's New Intraday Margin Framework](https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/) — implemented 2026-06-04, existing PDT restrictions lifted
- [Alpaca US docs](https://docs.alpaca.markets/us/) · [Funding Accounts](https://docs.alpaca.markets/us/docs/funding-accounts) · [ACH Funding](https://docs.alpaca.markets/docs/ach-funding)
- [Broker API funding + Plaid](https://alpaca.markets/docs/broker/integration/funding/) — the partner product, *not* what a personal account uses (spec §12.1)
- Market data plans: free tier = 15-min delayed REST, real-time IEX-only WebSocket, 200 rpm; Algo Trader Plus $99/mo = full SIP, OPRA, 10,000 rpm — [Alpaca pricing](https://alpaca.markets/) · [TradingDataCompare: Alpaca review](https://tradingdatacompare.com/providers/alpaca/)

### Alpaca MCP server (spec §19.1)

- [`alpacahq/alpaca-mcp-server`](https://github.com/alpacahq/alpaca-mcp-server) — official
- [Alpaca MCP docs](https://docs.alpaca.markets/us/docs/alpaca-mcp-server) · [product page](https://alpaca.markets/mcp-server)
- [Building an MCP trading workflow with Claude](https://alpaca.markets/learn/mcp-trading-with-claude-alpaca-google-sheets)

v2 rewrite on FastMCP + OpenAPI, v2.3.1 released 2026-09-01, 65 tools. Paper mode via `ALPACA_PAPER_TRADE`.

## BlackRock Advisor Center (spec §19.2)

Available in this Claude account as both a connector (`https://ac360-mcp.blackrock.com`) and the
`blackrock-advisor-center-plugin` in the `knowledge-work-plugins` marketplace. Neither is enabled yet.

Tools include `analyze_portfolio`, `analyze_risk`, `analyze_scenarios`, `analyze_characteristics`,
`analyze_fund_health`, `analyze_opportunities`, `analyze_esg`, `acknowledge_terms` (+21 more). Skills:
`portfolio-review`, `guided-benchmark-selection`, `guided-portfolio-builder`,
`portfolio-observations-and-opportunities`, `wealth-projections`, `ac360-capability-router`.

Per its own plugin description it **requires an Advisor Center account** — tracked as open item O-7.

## Day trading base rates (spec §2.1)

- [Barber & Odean et al., *The Profitability of Day Traders*, Financial Analysts Journal 59(6)](https://www.tandfonline.com/doi/abs/10.2469/faj.v59.n6.2578) — 64.2% net-negative after commissions
- Taiwan dataset, 360,000+ day traders: >80% lose money, <1% consistently profitable
- Brazil 2019: 97% of those persisting past 300 days lost money
- [Day Trading Statistics: What Academic Research Shows](https://curvedtrading.com/articles/en/trading/day-trading-statistics/)
- [Is Day Trading Profitable? A Data-Driven Reality Check](https://fortraders.com/blog/day-trading-profitable)

## Investopedia simulator (spec §2.3)

No official API. Community scrapers only, credential-based, variously stale:

- [dchrostowski/investopedia_simulator_api](https://github.com/dchrostowski/investopedia_simulator_api)
- [kirkthaker/investopedia-trading-api](https://github.com/kirkthaker/investopedia-trading-api)

## Storage (spec §4.3)

- [Supabase pricing](https://uibakery.io/blog/supabase-pricing) — free tier 500MB and **paused after one week of inactivity**; Pro $25/mo
- [Neon: the `timescaledb` extension](https://neon.com/docs/extensions/timescaledb) — Apache-2 edition only; **no native compression or tiered storage**
- [Neon: time-series data guidance](https://neon.com/guides/timeseries-data) — native partitioning + `pg_partman` (`pg_partman_bgw` 5.1.0)
- [Neon Postgres extensions](https://neon.com/docs/extensions/pg-extensions)
- [PostgreSQL hosting pricing comparison 2026](https://www.bytebase.com/blog/postgres-hosting-options-pricing-comparison/) — TigerData (Timescale, renamed June 2025) free tier 750MB

## Notifications (spec §13)

**Twilio A2P 10DLC — why the spec avoids it:**

- [Twilio free trial account guide](https://www.twilio.com/docs/usage/tutorials/how-to-use-your-free-trial-account) — **trial accounts cannot register for A2P 10DLC**; that requires a paid account. Trial accounts send to Verified Caller IDs; a verified toll-free number can message up to 5 pre-designated numbers
- [A2P 10DLC registration quickstart](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart) · [campaign approval requirements](https://help.twilio.com/articles/11847054539547-A2P-10DLC-Campaign-Approval-Requirements) — **campaign review currently runs 10–15 days**

A campaign is not needed here: one operator messaging their own verified number. §13 therefore makes
Telegram the primary channel and Twilio optional.

**Resend free tier:** 3,000 emails/month, **100/day**, one verified domain, 30-day log retention —
[Resend pricing 2026](https://nuntly.com/resend-pricing) · [free tier explained](https://automationatlas.io/answers/resend-free-tier-explained-2026/).
The daily cap is the binding constraint, hence R-13.4.a (EOD digest, not per-trade email).

**Telegram Bot API:** free and unmetered, inline keyboards for approve/reject, webhook secret-token header
(`X-Telegram-Bot-Api-Secret-Token`) for authentication — [Bot API docs](https://core.telegram.org/bots/api).

## Other market data providers considered (spec §19.3)

- [Alpha Vantage MCP](https://github.com/berlinbra/alpha-vantage-mcp) — free tier 25 calls/**day**; real-time US data needs premium
- [Market Data APIs Compared: Databento vs Polygon 2026](https://aifinhub.io/articles/market-data-apis-compared-2026/) — Polygon Stocks Advanced $199/mo; Databento metered ~$100–500/mo
- [Best Market Data APIs for Algorithmic Trading in 2026](https://www.alphanume.com/blog/best-market-data-apis-for-algorithmic-trading-in-2026)

## Methodology (spec §9)

Marcos López de Prado, *Advances in Financial Machine Learning* (Wiley, 2018) — triple-barrier labelling,
meta-labelling, purged K-fold with embargo, sample uniqueness weights, deflated and probabilistic Sharpe.
