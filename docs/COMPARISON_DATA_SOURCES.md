# Process-Level Comparison Data Sources

Data sources for governance process mining comparison with DAO findings.
Goal: obtain event-level data (voter, timestamp, vote, proposal/session) to build event logs and apply the same process mining pipeline.

---

## 1. European Parliament — Roll-Call Votes (Recommended, Easiest)

**Why:** 705 MEPs, thousands of votes, timestamps, party affiliations, 1-person-1-vote. Good democratic baseline.

### HowTheyVote.eu (primary)

- **GitHub data repo:** https://github.com/HowTheyVote/data — weekly-updated CSV dumps
- **REST API:** https://howtheyvote.eu/developers/
- **Coverage:** 9th Parliament term onward (2019–present), roll-call votes only
- **Key fields:**
  - Vote ID, timestamp, description, procedure reference
  - MEP ID, name, country, political group
  - Position: `FOR`, `AGAINST`, `ABSTENTION`, `DID_NOT_VOTE`
  - Vote stats by group and country
- **CSV per vote:** `https://howtheyvote.eu/api/votes/{vote-id}/members.csv`
- **Volume:** 22,500+ votes, ~705 MEPs per vote
- **License:** Open data
- **Event log mapping:**
  - `case_id` = vote/procedure ID
  - `activity` = position (FOR/AGAINST/ABSTENTION)
  - `timestamp` = plenary session date (note: individual MEP vote timestamps not available, only session date)
  - `resource` = MEP ID
  - Additional: political group, country

### Limitations

- No per-MEP timestamps within a vote (all votes in a division happen simultaneously by electronic button press) — front-loading analysis not possible
- Roll-call votes only (~30-40% of all EP votes); show-of-hands and secret ballots excluded
- No proposal lifecycle events (no equivalent of proposal_created → queued → executed)

### What IS comparable

- Coalition/co-voting patterns (party discipline vs. cross-party voting)
- Voter segmentation (attendance patterns, participation rates)
- Temporal evolution (concept drift across parliamentary terms)
- Voting power distribution (equal votes, but party-level bloc analysis possible)

---

## 2. UK House of Commons — Division Records (Good Alternative)

**Why:** Longer history, well-structured API, individual division records with clear lifecycle.

### Official API

- **Commons Votes API:** https://commonsvotes-api.parliament.uk/
- **Lords Votes API:** https://lordsvotes-api.parliament.uk/
- **OpenAPI spec available** at the above URLs
- **R package:** https://github.com/houseofcommonslibrary/clvotes

### The Public Whip (bulk download)

- **URL:** https://www.publicwhip.org.uk/project/data.php
- **Format:** Tab-separated vote matrices per session, XML files, database dumps
- **Coverage:** 1997–present
- **License:** Open Database License
- **Contains:** MP name, constituency, party, division ID, date, vote (Aye/No/absent)

### Event log mapping

- `case_id` = division ID (or bill ID for lifecycle tracking)
- `activity` = Aye / No / Abstain
- `timestamp` = division date
- `resource` = MP ID
- Additional: party, constituency, government/opposition

### Advantage over EU Parliament

- Bills have a clear multi-stage lifecycle: First Reading → Second Reading → Committee → Report → Third Reading → Lords → Royal Assent
- This maps to a process mining event log much better than EU Parliament single-vote records
- Can track a bill as a case through governance stages — directly comparable to DAO proposal lifecycle

---

## 3. SEC Form N-PX — Mutual Fund Proxy Voting (Corporate Governance)

**Why:** Token-weighted voting equivalent. Funds vote shares proportionally — same mechanism as DAO governance.

### SEC EDGAR (official, free)

- **Search tool:** https://www.sec.gov/search-filings/mutual-funds-search/search-mutual-fund-proxy-voting-records
- **Bulk API:** https://data.sec.gov — nightly JSON ZIP dumps, no auth required
- **N-PX XML spec:** https://sec.gov/file/form-npx-xml (1.24 MB technical spec)
- **Rate limit:** 10 requests/second, User-Agent header required
- **Coverage:** Annual filings (July 1 – June 30), filed by August 31

### Third-party API (easier)

- **sec-api.io:** https://sec-api.io/docs/form-npx-proxy-voting-records-api
  - N-PX Search API: filter filings by fund, date, company
  - Voting Record API: structured JSON per filing
  - Paid service

### Key fields in N-PX filings

- Fund name, fund CIK
- Portfolio company name, CUSIP/ISIN, ticker
- Shareholder meeting date
- Proposal description, proposal category
- Management recommendation (For/Against)
- Fund vote cast (For/Against/Abstain/Withhold)
- Shares voted

### Event log mapping

- `case_id` = shareholder meeting + company (e.g., "AAPL-2025-annual")
- `activity` = proposal vote (For/Against/Abstain)
- `timestamp` = meeting date
- `resource` = fund CIK
- `weight` = shares voted (directly comparable to DAO voting power)

### Limitations

- Annual filing — no real-time data
- Meeting-level timestamps only (no intra-meeting timing)
- Massive data volume (thousands of funds × thousands of meetings)
- XML parsing required for bulk EDGAR data

### What IS comparable

- Voting power concentration (shares held = tokens held)
- Coalition patterns (do BlackRock, Vanguard, State Street always co-vote?)
- Management alignment (comparable to DAO proposer/voter alignment)
- Proposal type analysis (executive comp, board elections, shareholder proposals)

---

## 4. US Congress — Roll-Call Votes (Supplementary)

### unitedstates/congress project

- **GitHub:** https://github.com/unitedstates/congress
- **Format:** JSON and XML per vote
- **Coverage:** Historical roll-call votes
- **Fields:** Member ID, party, state, vote position, vote date/time, bill reference

### ProPublica Congress API

- **URL:** https://projects.propublica.org/api-docs/congress-api/
- **Free API key required**
- **Contains:** vote results, member voting records, bill lifecycle stages

---

## Recommendation: Priority Order

| Priority | Source | Effort | Process Mining Value |
|----------|--------|--------|---------------------|
| 1 | **UK Parliament** (Public Whip + API) | Low | High — bill lifecycle maps to proposal lifecycle |
| 2 | **EU Parliament** (HowTheyVote) | Low | Medium — good for coalition/participation, no lifecycle |
| 3 | **SEC N-PX** (EDGAR bulk) | High | High — weighted voting directly comparable to DAO |
| 4 | US Congress | Medium | Medium — similar to UK but messier data |

**UK Parliament is the best single comparison target** because bills have a multi-stage governance process (readings → committee → execution) that structurally mirrors DAO proposal lifecycles (proposal → vote → queue → execute). EU Parliament votes are point-in-time events without lifecycle stages.

**SEC N-PX is the best for weighted voting comparison** but requires significant data engineering effort.
