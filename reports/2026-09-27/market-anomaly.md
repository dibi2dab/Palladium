# 글로벌 공개시장 이상 (Market Anomaly)

> 실측 가격/거래량 데이터 기반 감지. 이상은 실제 수집 수치로만 판정하며 AI 생성 수치를 사용하지 않습니다.

## 가격/거래량 이상 감지

> '급등/급락' 라벨은 전 거래일 대비 실제 가격 움직임이 임계값을 넘은 경우에만 표시됩니다.

## 백금 (Platinum) (PL=F)

- PL=F: **1797.7** (2026-09-25) · 전일 1749.1 (+2.78%)

**감지된 이상**

- **급등** `PRICE_ANOMALY_UP` +1.62% — 백금 (Platinum) 가격 1801.9 (2026-09-16) vs 이전 1773.2 (2026-09-15) — +1.62%
- **거래량 급증** `TRADING_VOLUME_SPIKE`, 거래량 2,132 (213.2배) — 백금 (Platinum) 거래량 2,132 (2026-09-23) vs 최근 중앙값 10 — 213.20배
- **거래량 급증** `TRADING_VOLUME_SPIKE`, 거래량 2,567 (213.9배) — 백금 (Platinum) 거래량 2,567 (2026-09-24) vs 최근 중앙값 12 — 213.92배
- **거래량 급증** `TRADING_VOLUME_SPIKE`, 거래량 1,409 (176.1배) — 백금 (Platinum) 거래량 1,409 (2026-09-25) vs 최근 중앙값 8 — 176.12배
- **급등** `PRICE_ANOMALY_UP` +2.78% — 백금 (Platinum) 가격 1797.7 (2026-09-25) vs 이전 1749.1 (2026-09-24) — +2.78%

## 팔라듐 (Palladium) (PA=F)

- PA=F: **1276** (2026-09-25) · 전일 1270.2 (+0.46%)

**감지된 이상**

- **급등 가속** `PRICE_ACCELERATION_UP` +3.33% — 팔라듐 (Palladium) 가격 1323.9 (2026-09-11) vs 이전 1281.3 (2026-09-10) — +3.32%
- **급등** `PRICE_ANOMALY_UP` +2.82% — 팔라듐 (Palladium) 가격 1325.5 (2026-09-16) vs 이전 1289.2 (2026-09-15) — +2.82%
- **급등** `PRICE_ANOMALY_UP` +2.77% — 팔라듐 (Palladium) 가격 1326 (2026-09-18) vs 이전 1290.2 (2026-09-17) — +2.77%

## 은 (Silver) (SI=F)

- SI=F: **64.8** (2026-09-25) · 전일 63.46 (+2.11%)

**감지된 이상**

- **급등** `PRICE_ANOMALY_UP` +3.16% — 은 (Silver) 가격 65.24 (2026-09-16) vs 이전 63.24 (2026-09-15) — +3.16%
- **급등** `PRICE_ANOMALY_UP` +2.40% — 은 (Silver) 가격 67.04 (2026-09-18) vs 이전 65.47 (2026-09-17) — +2.40%
- **급등** `PRICE_ANOMALY_UP` +2.11% — 은 (Silver) 가격 64.8 (2026-09-25) vs 이전 63.46 (2026-09-24) — +2.11%

## 서부텍사스산 원유 (WTI) (CL=F)

- CL=F: **92.41** (2026-09-25) · 전일 94.61 (-2.33%)

**감지된 이상**

- **급락 가속** `PRICE_ACCELERATION_DOWN` -2.37% — 서부텍사스산 원유 (WTI) 가격 100.05 (2026-09-11) vs 이전 102.48 (2026-09-10) — -2.37%
- **급등 가속** `PRICE_ACCELERATION_UP` +2.32% — 서부텍사스산 원유 (WTI) 가격 102.37 (2026-09-14) vs 이전 100.05 (2026-09-11) — +2.32%
- **급락** `PRICE_ANOMALY_DOWN` -5.72% — 서부텍사스산 원유 (WTI) 가격 96.08 (2026-09-18) vs 이전 101.91 (2026-09-17) — -5.72%
- **급락** `PRICE_ANOMALY_DOWN` -5.75% — 서부텍사스산 원유 (WTI) 가격 94.53 (2026-09-21) vs 이전 100.3 (2026-09-18) — -5.75%
- **급락 가속** `PRICE_ACCELERATION_DOWN` -2.39% — 서부텍사스산 원유 (WTI) 가격 93.49 (2026-09-22) vs 이전 95.78 (2026-09-21) — -2.39%
- **급락** `PRICE_ANOMALY_DOWN` -5.58% — 서부텍사스산 원유 (WTI) 가격 89.31 (2026-09-23) vs 이전 94.59 (2026-09-22) — -5.58%
- **급락 가속** `PRICE_ACCELERATION_DOWN` -2.33% — 서부텍사스산 원유 (WTI) 가격 92.41 (2026-09-25) vs 이전 94.61 (2026-09-24) — -2.33%

## 금 (Gold) (GC=F)

- GC=F: **4321.2** (2026-09-25) · 전일 4298 (+0.54%)

_이번 관측에는 임계값을 넘는 이상이 없습니다._

## 구리 (Copper) (HG=F)

- HG=F: **6.77** (2026-09-25) · 전일 6.72 (+0.74%)

_이번 관측에는 임계값을 넘는 이상이 없습니다._

## 공시 이벤트 (SEC Disclosure)

> SEC EDGAR 공시(SEC) 기반 실측 이벤트 — 신문 헤드라인이 아닌 공식 공시에 근거합니다.

- **[NMP Acquisition Corp. (NMP)](https://www.sec.gov/Archives/edgar/data/0000002054876/000121390026097868/ea030467201ex99-1.htm)** — Material agreement entered into \| Regulation FD disclosure \| 8-K item 9.01 PRESS RELEASE, DATED AS OF SEPTEMBER 8, 2026 [8-K] 2026-09-08
- **[ChampionsGate Acquisition Corp (CHPG)](https://www.sec.gov/Archives/edgar/data/0000002024460/000121390026099015/ea030524301ex99-1.htm)** — Regulation FD disclosure \| 8-K item 9.01 PRESS RELEASE, DATED SEPTEMBER 11, 2026 [8-K] 2026-09-11
- **[Columbus Acquisition Corp/Cayman Islands (COLA)](https://www.sec.gov/Archives/edgar/data/0000002028201/000121390026098977/ea030516101ex99-1.htm)** — Other material event \| 8-K item 9.01 PRESS RELEASE DATED SEPTEMBER 11, 2026 [8-K] 2026-09-11
- **[AMR Resources Acquisition Corp. (AMAC)](https://www.sec.gov/Archives/edgar/data/0000002110119/000121390026097666/ea030463801ex99-1.htm)** — Other material event \| 8-K item 9.01 PRESS RELEASE, DATED SEPTEMBER 4, 2026 [8-K] 2026-09-04
- **[Catalyst Acquisition Corp. (CATL)](https://www.sec.gov/Archives/edgar/data/0000002104391/000121390026100217/ea030560301ex99-1.htm)** — Other material event \| 8-K item 9.01 PRESS RELEASE DATED SEPTEMBER 15, 2026 [8-K] 2026-09-15
- **[Market Technology Acquisition Corp (MTAK)](https://www.sec.gov/Archives/edgar/data/0000002133136/000121390026100364/ea030565801ex99-1.htm)** — Other material event \| 8-K item 9.01 PRESS RELEASE DATED SEPTEMBER 16, 2026 [8-K] 2026-09-16
- **[Leader's Advantage Acquisition Corp. (LEDR)](https://www.sec.gov/Archives/edgar/data/0000002109823/000121390026102625/ea030630401ex99-1.htm)** — Material agreement entered into \| Unregistered equity sale \| 8-K item 5.03 PRESS RELEASE, DATED SEPTEMBER 17, 2026 [8-K] 2026-09-23
- **[Allarity Therapeutics, Inc. (ALLR)](https://www.sec.gov/Archives/edgar/data/0000001860657/000121390026099576/ea030540801ex99-1.htm)** — Other material event \| 8-K item 9.01 PRESS RELEASE, DATED SEPTEMBER 11, 2026 [8-K] 2026-09-14
- **[Pinnacle Acquisition Corp (PNAQ)](https://www.sec.gov/Archives/edgar/data/0000002123955/000121390026103368/ea030652301ex99-1.htm)** — Other material event \| 8-K item 9.01 PRESS RELEASE DATED SEPTEMBER 25, 2026 [8-K] 2026-09-25
- **[ALLIANCE ENTERTAINMENT HOLDING CORP (AENT)](https://www.sec.gov/Archives/edgar/data/0000001823584/000149315226042141/form10-k.htm)** — 10-K 10-K [10-K] 2026-09-10

## 소스 상태

| 소스 | 상태 | 항목 수 |
|------|------|---------|
| 서부텍사스산 원유 (WTI) | OK | 1 |
| 미국 10년물 국채수익률 | FAILED | 0 |
| 미국 달러 인덱스 | FAILED | 0 |
| 금 (Gold) | OK | 1 |
| 금 런던 고시가 | FAILED | 0 |
| 구리 (Copper) | OK | 1 |
| 팔라듐 (Palladium) | OK | 1 |
| 백금 (Platinum) | OK | 1 |
| 은 (Silver) | OK | 1 |
