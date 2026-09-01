# Governance Power Concentration: Quantitative Comparison

Comparison of voting power concentration across three governance paradigms:
publicly traded corporations (Aminadav & Papaioannou, 2016),
DAO governance (ENS, AAVE),
and representative democracy (UK Parliament).

---

## 1. Methodology Mapping

| Corporate Concept | DAO Equivalent | Implementation |
|---|---|---|
| Firm | Proposal (each vote = one governance decision) | `case:concept:name` |
| Shareholder | Voter address | `org:resource` |
| Equity stake (voting rights) | Voting power (VP) share within proposal | `voting_power / sum(voting_power)` |
| C1 (largest shareholder) | Largest voter VP share per proposal | Top-1 VP / total VP |
| C3 / C5 | Top-3 / top-5 voter VP share | Sum of top-N VP / total VP |
| Shapley-Shubik power index | SS index for top-50 voters per proposal | Monte Carlo (10,000 samples), majority quota = 0.5 |
| Controlled firm (SS >= threshold) | Controlled proposal (SS >= 0.75) | Any voter's SS index >= 0.75 |
| Widely-held with block (>5%) | Proposal with block voter (>5% VP share) | Any voter share >= 5% |
| Widely-held no block | Retail-driven proposal | No voter >= 5% VP share |
| Family/individual control | Whale control | Single address holds >50% VP |
| Institutional investor block | Delegate block | Address with >5% VP, not >50% alone |

**Key differences**:

- In corporate governance, equity stakes are persistent across decisions.
  In DAOs, voting power is cast per-proposal and may vary.
  Each proposal is treated as an independent "firm" for concentration metrics.
- UK Parliament uses equal-weight voting (VP=1.0 per MP). Concentration
  indices mechanically reflect participation levels, not wealth-based power
  differentials. For bills with multiple divisions, each MP's VP is summed
  across divisions attended.

---

## 2. Concentration Indices (C1, C3, C5)

| Metric | Corporate (Paper) | ENS | AAVE | UK Parliament |
|---|---|---|---|---|
| C1 mean | 31.5% | 11.5% | 36.0% | 0.4% |
| C1 median | 24.1% | 10.7% | 33.6% | 0.2% |
| C3 mean | 41.7% | 27.9% | 65.3% | 1.1% |
| C3 median | 39.1% | 28.4% | 66.8% | 0.6% |
| C5 mean | 44.6% | 41.7% | 80.1% | 1.8% |
| C5 median | 44.1% | 44.7% | 85.2% | 1.1% |

### C3 Median by Legal Origin (Corporate) vs Governance Systems

| Category | C3 Median |
|---|---|
| Common law countries | 29.0% |
| French civil law | 62.2% |
| German civil law | 44.4% |
| Scandinavian civil law | 36.1% |
| **ENS** | **28.4%** |
| **AAVE** | **66.8%** |
| **UK Parliament** | **0.6%** |

---

## 3. Shapley-Shubik Power Index Analysis

Shapley-Shubik power index computed via Monte Carlo approximation
(10,000 random permutations) for top-50 voters per proposal.
Control threshold: SS >= 0.75 (matching the paper's methodology).
Majority quota: 0.5 (standard corporate voting rule).

| Metric | ENS | AAVE | UK Parliament |
|---|---|---|---|
| Max SS index (mean across proposals) | 0.123 | 0.459 | 0.001 |
| Max SS index (median) | 0.113 | 0.383 | 0.000 |
| % proposals classified as controlled | 0.9% | 17.4% | 0.0% |

### ENS — SS Max Distribution

| Percentile | SS Max Value |
|---|---|
| P10 | 0.073 |
| P25 | 0.087 |
| P50 | 0.113 |
| P75 | 0.145 |
| P90 | 0.169 |
| P95 | 0.184 |
| P99 | 0.233 |

### AAVE — SS Max Distribution

| Percentile | SS Max Value |
|---|---|
| P10 | 0.145 |
| P25 | 0.237 |
| P50 | 0.383 |
| P75 | 0.583 |
| P90 | 1.000 |
| P95 | 1.000 |
| P99 | 1.000 |

### UK Parliament — SS Max Distribution

| Percentile | SS Max Value |
|---|---|
| P10 | 0.000 |
| P25 | 0.000 |
| P50 | 0.000 |
| P75 | 0.000 |
| P90 | 0.000 |
| P95 | 0.000 |
| P99 | 0.022 |

---

## 4. Corporate Control Taxonomy Classification

| Category | Corporate (Paper) | ENS | AAVE | UK Parliament |
|---|---|---|---|---|
| Controlled (SS >= 0.75) | 44.0% | 0.9% | 17.4% | 0.0% |
| Widely-held with block (>5%) | 47.0% | 95.5% | 82.6% | 0.0% |
| Widely-held no block | 9.0% | 3.6% | 0.0% | 100.0% |

### By Legal Origin (Corporate) vs Governance Systems

| Category | % Controlled |
|---|---|
| Common law countries | 32.0% |
| French civil law | 66.0% |
| **ENS** | **0.9%** |
| **AAVE** | **17.4%** |
| **UK Parliament** | **0.0%** |

---

## 5. Controller Type Mapping

| Corporate Type | DAO Equivalent | ENS | AAVE | UK Parliament |
|---|---|---|---|---|
| Family/individual control | Whale control (single addr >50% VP) | 0.9% | 16.3% | 0.0% |
| Controlled by private firm/coalition | Coalition control (SS-controlled, C1 <50%) | 0.0% | 1.1% | 0.0% |
| Institutional investor block | Delegate block (>5% VP, not controlled) | 95.5% | 82.6% | 0.0% |
| Widely-held dispersed | Retail (no voter >5% VP) | 3.6% | 0.0% | 100.0% |

---

## 6. Key Divergences and Thesis Implications

### 6.1 Governance Mechanism Spectrum

The three governance paradigms represent a spectrum of voting power allocation:

| System | Voting Mechanism | C3 Median | % Controlled (SS) |
|---|---|---|---|
| UK Parliament | Equal-weight (1 MP = 1 vote) | 0.6% | 0.0% |
| Corporate (Paper) | Equity-weighted (persistent stakes) | 39.1% | 44.0% |
| ENS DAO | Token-weighted (per-proposal) | 28.4% | 0.9% |
| AAVE DAO | Token-weighted (per-proposal) | 66.8% | 17.4% |

This spectrum demonstrates that **voting mechanism design is the primary
determinant of power concentration** — analogous to the paper's finding that
legal origin explains corporate control patterns.

### 6.2 Equal-Weight Voting as Concentration Baseline

UK Parliament shows near-zero concentration:
C1=0.2%, C3=0.6%, C5=1.1% median.
With ~571 MPs per bill, each voter's share is ≈1/N.
No bill is classified as controlled (SS max ≈ 1/N).
100.0% of bills fall in the "widely-held no block"
category — the dispersed governance that token-weighted DAOs almost never achieve.

This confirms that equal-weight voting produces the theoretical minimum
of concentration metrics, providing a baseline against which token-weighted
and equity-weighted mechanisms can be measured.

### 6.3 DAO Concentration: Between Corporate and Extreme

Per-proposal concentration (C1/C3/C5) reveals a split between DAOs:

**ENS** has C3 median of 28.4%,
comparable to common law corporate environments (29.0%).
This is because ENS has many voters per proposal (~1173 average),
spreading VP across many addresses. However, the Gini of 0.967 (from the
full analysis) shows that *across all proposals combined*, power is extremely
concentrated. The key insight: ENS distributes power more evenly *within*
each proposal, but the same small cohort dominates *across* proposals.

**AAVE** has C3 median of 66.8%, exceeding French civil law
countries (62.2%), the most concentrated legal
family in the paper. At the C5 level, AAVE proposals show top-5 voter
concentration of 85.2% median — far beyond any corporate benchmark.

The corporate world shows C1 mean of 31.5% and moderate C3-to-C5 growth
(41.7% → 44.6%), indicating many similarly-sized block holders. AAVE shows
C1=36.0%, C3=65.3%, C5=80.1% —
steep concentration in the top few addresses.

### 6.4 Control Classification Across Governance Systems

Using the paper's Shapley-Shubik methodology with the same 75% threshold:
- Corporate: 44.0% of firms are controlled
- ENS: 0.9% of proposals are controlled
- AAVE: 17.4% of proposals are controlled
- UK Parliament: 0.0% of bills are controlled

Parliament shows 0% controlled — with equal voting weights,
no individual can be pivotal.
ENS proposals are rarely controlled (power spread among multiple
whales with moderate shares); the Gini of 0.967 across all proposals
reveals systemic inequality invisible to per-proposal SS analysis.
AAVE shows 17.4% controlled proposals, driven by
cases where a single address casts >50% of VP.
The corporate benchmark (44%) reflects persistent cross-decision control;
DAO 'control' is per-proposal and more volatile.

### 6.5 The "Widely-Held No Block" Spectrum

In the corporate world, 9.0% of firms have no
shareholder exceeding 5%.

- ENS: 3.6%
- AAVE: 0.0%
- UK Parliament: 100.0%

Fully dispersed governance is the norm in parliamentary systems, rare in
corporate governance, and virtually absent in token-weighted DAOs.

### 6.6 Structural vs Temporal Comparison

The paper finds that corporate control is remarkably stable: 64% of firms
had zero change in controlling shareholder over 2004-2012 (9 years).
DAO governance, by contrast, shows:
- ENS: no structural concept drift (fitness 0.9998), but dramatic
  behavioral changes (participation decline, execution rate increase)
- AAVE: asymmetric concept drift (fitness 0.9644 for late→early),
  three distinct governance eras in 5 years

Parliamentary governance sits between these extremes: the legislative
process structure is stable by design (codified in Standing Orders), but
political dynamics shift with elections and party realignment.

### 6.7 Legal Origin Analogy — With Empirical Evidence

The paper demonstrates that legal origin (common law vs civil law) is a
primary determinant of corporate control patterns. The three-way comparison
now provides empirical support for the analogous thesis:
**governance mechanism design determines concentration.**

| Governance Mechanism | Concentration Level | Analogy |
|---|---|---|
| Equal-weight (Parliament) | Near-zero (C3 ≈ 0.6%) | Theoretical minimum |
| Equity-weighted (Corporate) | Moderate (C3 = 29.0%–62.2%) | Legal-origin dependent |
| Token-weighted (DAOs) | Variable (C3 = 28.4%–66.8%) | Mechanism-design dependent |

UK Parliament serves as empirical proof that equal-weight voting eliminates
concentration. The jump from Parliament's 0.6% C3
to ENS's 28.4% and AAVE's 66.8%
is entirely attributable to the shift from equal to token-weighted voting.
This parallels the paper's finding that common law → French civil law
increases C3 from 29.0% to 62.2%
— the mechanism (legal framework or voting rules) is the dominant variable.

---

## 7. Data Summary

| | Corporate (Paper) | ENS | AAVE | UK Parliament |
|---|---|---|---|---|
| Entities analyzed | 26,843 firms | 110 proposals | 569 proposals | 42 bills |
| Participants | 80,607 shareholders | 90,242 voters | 83,032 voters | 1,241 voters |
| Countries / Systems | 85 countries | 1 DAO | 1 DAO | 1 Parliament |
| Period | 2004-2012 | 2021-2025 | 2020-2026 | 2017-2026 |
| Methodology | Shapley-Shubik (exact + Bachrach approx) | Shapley-Shubik (MC 10,000 samples) | Shapley-Shubik (MC 10,000 samples) | Shapley-Shubik (MC 10,000 samples) |

---

*Generated by `comparative_analysis.py`*