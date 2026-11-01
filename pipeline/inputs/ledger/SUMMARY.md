# @SRC_LEDGER — Nightly "SPY Post-Market Write-Up" (research summary)

Compiled 2026-10-20, 8:45 PM PT. Source files: `./2026-10-07.md` … `./2026-10-20.md` (full text plus post URL in each file).

## Where it lives
- **Platform: X Articles** (long-form posts on X), not Substack or beehiiv. Bio: "Valois Capital Management, LLC". There's no website link in the profile.
- Title format: "<Weekday> <M/D> SPY Post-Market Write-Up". Posted around 2:30–4:00 PM PT after the close, sometimes on the weekend for Friday's session. He usually reposts it in the evening ("Don't forget to read today's write-up").
- The daily write-ups are free and public. He also sells a paid X subscription tier ("macro analysis for subscribers"); none of that was accessed.
- **RSS: none.** X Articles have no RSS or Atom feed, and x.com/i/article URLs don't open without login (t.co reports 404). Nightly pull: use the X API (the `x` MCP `search_posts_all`, query `from:SRC_LEDGER url:article`, `post.fields=article`). It returns `article.title` and `article.plain_text`. Charts are images only (media ids, no text).

## Method / style
- **Instrument:** SPY, mostly the daily chart, with the 1H chart for next-day timing. ES is not used. Context instruments: VIX, VIX1D, VIX3M/VIX spread, VIX term structure, 10Y yield, DXY, Gold, WTI, IWM, RSP vs MAGS, % of stocks above their 50DMA. Occasionally KOSPI.
- **Levels:** the main tool is **dark-pool print levels** (large blocks, given with $ size). He prefers them to fibs. Recurring levels: 762.27 (the largest), 764.19, 767.41/.42, 769.45, **772.22/772.43** (the "ceiling since Aug 4"), 773.76/.84, 776.47, 777.86, 779.10, 757.40/.43, 746/745.
- **Options positioning:** GEX call and put walls (CheddarFlow, Unusual Whales), gamma/vanna/charm heatmaps, OI magnets, max pain, 0DTE walls. He follows OpEx and VIXperation dates closely.
- **Moving averages:** 10/20/50/100/200 DMA, EMA 8/21, 1H SMA 10/20/50/200. He calls a level broken only after a confirmed close ("one day doesn't confirm").
- **Oscillators:** MACD, RSI, Stochastic, Awesome Oscillator, Bollinger Bands (squeeze = coiling spring; close outside the band with RSI<30 = mean-reversion signal). He also reads MOC imbalances (first call vs. final call).
- **Rules of thumb:** VIX1D touching 6.88 means a next-day pullback. VIX closing up 10% or more gives an 80% chance of a SPY bounce within 2 sessions (95% if up 20% or more). Gold tracks SPY, so a Gold divergence warns. WTI above 95.64 is a headwind for stocks.
- **How he frames bias:** each issue ends with "My take": a base case with path and targets, an alternative case ("not my lean"), and the trigger level that flips him. He leans bearish on macro (AI bubble, stagflation, Iran/oil, "TACO" headlines) but traded the bull side into early October with 785 as the cap.

## Per-issue table
| Date (session) | Bias (next session / week) | Key levels | Main ideas |
|---|---|---|---|
| Wed 10/7 | Bull to 785 by Fri, then sharp correction | 776.47, 779.10, 775 put OI, 785 OI magnet; 755–745 correction | Shallow AM pullback to the 1H EMA21 (~776), then up; breadth rolling over; "3 drives to a high" setup |
| Thu 10/8 | Bull into Wed 10/14, bear after OpEx | must hold 773.76, retake 776.47; 785/790 vanna-charm node; 767 put wall; max pain 768 | Pullback deeper than expected; 785 pushed to next week; sell 785 hard |
| Fri 10/9 | Pullback Mon to 773.84, then 785 by Wed (CPI), down week after | 773.84/773.76, 779 pin, 785/790, 750 OI | Low-volume "Icarus" melt-up; won't go below 772 this week |
| Mon 10/12 | Weak Tue, CPI Wed sends it to 785 by Fri | 785 (moved down from 790) | Short issue; possible evening star; magnet rolling down |
| Tue 10/13 | Big move on CPI; soft CPI: wick to 785, sold to 780; hot CPI: drop to 773.8 | 779 0DTE call wall, 785 call wall, 772 put wall, 773.76/.84, max pain 770 | Red flags: magnet rolling down daily (790→785→782); WTI 95.64 risk |
| Wed 10/14 | Bounce to 773.76/.84 (reach 777.86); if PPI hot, 762.27 | 767.41/.42 held, 769 put wall, max pain 770, 762.27 | Hot CPI, -1%; VIX up more than 10% → bounce odds; bounce expected to fail after OpEx |
| Thu 10/15 | OpEx pin at 770, range 768–772 | 772.22/772.43 ceiling, 769.45, 764.19, 772 put wall | Hot PPI absorbed; yields fell oddly (flight to safety?); condor day |
| Fri 10/16 | Bounce early week to 768 (stretch 772), then month ends near 745 | 762.27 held, 757.43/.40, 769 gamma, 750 gamma, 745 puts | Admitted the pin call was wrong; VIX wedge breakout; "like end of February" |
| Mon 10/19 | Slow bounce into Wed AM, then about 760 by Fri; next stops 757.40, then 746 | 772.22 retest unlikely, 50DMA, 767.41, 762.27, 750 put wall | Lost the 20 and 50 DMA; MOC first call -3.6B; will buy Nov puts on a rejection |
| Tue 10/20 (**for Wed 10/21**) | **Bearish lean:** AM push up, weakness after the VIX settles | **772.22/772.43** test (cap 777.86), 50DMA ≈768.3, 769.45 1H resistance, 768 GEX, 773 upside node, 764.19 support, 765 0DTE put wall | VIXperation removes the VIX<20 suppression; Gold diverging; TSLA/META/TXN/IBM earnings; close below the 50DMA means a correction into month-end |

## How the calls held up (SPY daily OHLC, Yahoo free data)
| Call made | Next session actual | Verdict |
|---|---|---|
| 10/7: shallow dip to ~776, then up | 10/8: low 770.44, close 773.93 | Partial: direction right, dip deeper (he admitted it) |
| 10/8: hold 773.76, ideally retake 776.47 | 10/9: low 775.14, close 778.57 (+0.6%) | Hit |
| 10/9: Mon dip to 773.84, 785 by Wed, no break of 772 | 10/12 flat (low 777.05); 10/14 low 766.71; peak 779.4 | Miss (785 never came, 772 broke) |
| 10/12: Tue weak | 10/13: -0.01% | Roughly right |
| 10/13: big CPI move, hot → 773.8 | 10/14: -1.08%, low 766.71 | Hit (went further than the target) |
| 10/14: bounce toward 773.76 | 10/15: high 772.87, close 771.79 (+0.3%) | Hit (target just missed) |
| 10/15: 770 pin, 768–772 | 10/16: close 763.25, low 760.64 | Miss |
| 10/16: early-week bounce to 768, stretch 772 | 10/19: high 770.46, close 766.48 | Hit |
| 10/19: grinding bounce, maybe 772.22 | 10/20: high 772.29, close 769.05 | Hit (exact level) |

Score: about 6 of 9 next-day calls right on direction. His intraday levels are precise; the 772.22 rejection on 10/20 was almost exact. His multi-day targets are weaker: 785 never came, and the 770 OpEx pin failed. ES was not checked; SPY daily only.

## Ideas for the Attaché dashboard
- Section name: **"Dark Pool Levels & Dealer Map"** (or "Overnight Level Map").
- Pull nightly after about 4 PM PT through the X API (no RSS). Parse: title/date, the "My take" paragraph (base case / alternative / flip trigger), and every 3-digit SPY price (dark-pool levels, walls, magnets) into a level table. Note his VIX1D 6.88 / VIX percentage-change signals as flags.
- Show his levels next to Attaché's own ORB and pre-market levels as a "confluence" layer. Score each call against the next day's OHLC to keep a running hit rate.
- Treat it as one input with a known bearish macro lean; for his multi-day targets, trust the levels more than the forecasts.
