# Adversarial self-review

> Part of a personal portfolio desk study on public data (AI-assisted; not affiliated with LTA, SLA or URA;
> fictional corridor; not legal advice). Written at the last milestone: what a sceptical reviewer would attack,
> what was checked, what changed as a result, and what is still open. Figures quoted here are those of that
> run; the README and `results/` are the reference.

## Challenges, checks and outcomes

| # | Challenge | Check made | Outcome |
|---|---|---|---|
| 1 | "Is the corridor really not a planned line?" | Station pairs were screened against every line on URA's Master Plan 2025 rail layer as amended, which shows lines not yet built; LTA's March 2025 and March 2026 news releases on rail studies were read for the areas they name | The chosen pair lies away from every line and every named study area. Announcements that are in neither source cannot be ruled out, and the README says so |
| 2 | "Facts written from memory?" | Every VERIFIED quote was matched against a downloaded copy of its source; `scripts/check_quotes.py` repeats this automatically | Two rows were reworded after re-reading: the piling rule (F19) has a case-by-case exception the first draft left out, and URA's role (F31) is now quoted from its gazette press release. The automated check then failed on F32, whose source pointed at the wrong dataset page; the source was corrected and all VERIFIED quotes are now found |
| 3 | "Statutes from a third-party site?" | Singapore Statutes Online refused automated access, so the statutes were read from SSO-generated consolidations held by FAOLEX, each stamped with its in-force date | Kept, with the in-force dates in the fact sheet. The current State Lands Act and the Rapid Transit Systems Act could not be read; their rows are UNVERIFIED and no calculation uses them |
| 4 | "Is the 30 m default depth the law?" | The only source read for it is MinLaw's 2015 description of the Bill | It drives the stratum test, but every output calls it the default depth MinLaw described, and the current-text row (F22) is UNVERIFIED |
| 5 | "Does 'not shown as State land' mean private land?" | SLA's open layers cover only vacant State land, agent-managed State land and State reserves | Every mechanism is worded "if not State land ... confirm tenure with SLA", and the tenure table keeps road and park zoning apart from "Unknown" |
| 6 | "Distances to the existing railway look too precise" | The Master Plan lines are indicative centre lines | Bands are reported as lower bounds on proximity, measured both to the line and to the station outline |
| 7 | "Min-max scores exaggerate small differences" | Variants A and B differ by under one per cent on surface take | A tie variant (values within 5 % of the best count as best) gives the same ranking; the README says the ranking reflects how the variants were drawn |
| 8 | "Passing tests prove nothing" | Hand-written mutants in geometry, protection distances, area accounting, scoring, the database update, the outputs and the document checks | First run 48 of 55 caught. The seven survivors showed real gaps: the railway structure could include worksites, the one-at-a-time, leave-one-out and random-weight sensitivity results were not checked, a change of mechanism in a revision went unreported, an interest's area could be one piece instead of the sum, and number formatting was untested. Each got a test (`tests/test_round2.py`); the final run caught 57 of 57, including two mutants written for code added in review |
| 9 | "A building can be counted twice" | Re-reading the per-lot building count | A building touched by both a box and its worksite in the same lot was counted twice in the lot schedule (lot totals, not the variant totals, which already used distinct buildings). Fixed with a distinct count per lot and a test |
| 10 | "The README numbers could drift" | Documents are rendered from `results/` only; a test fails on a stale document or on any number typed into a template | The typed-number check is itself mutation-tested |
| 11 | "Floating point differs on another machine" | CI rebuilds on Linux | Results are compared with a small tolerance; the rounded documents must match exactly |
| 12 | "Linking to government pages" | SLA, LTA, URA and MinLaw website terms ask for permission before linking; OneMap allows links to its home page only | Their addresses are plain-text citations, never links; OneMap was not used |
| 13 | "Names and private data" | The raw files carried managing-agent company names, State-land asset descriptions, addresses and OSM names | Dropped before anything was written to the repository; tests check the extract's columns and scan every tracked text file for e-mail addresses, phone numbers, local paths and keys |

## Still open

- The station boxes and worksites at the Bedok end sit on built-up town-centre land in all three variants; a real
  options study would move them (road reserve, mined construction) before comparing routes.
- North worksites of two variants lie within the first reserve of the existing station. They were left there to
  show the check working, but they would have to move.
- No ground levels were used: depths are assumed directly in metres relative to the Singapore Height Datum, and
  there is no settlement or building-damage assessment.
- The sliver and building thresholds (one square metre each) were not varied; counts near them could move.
- OpenStreetMap completeness was checked only against URA's housing-block footprints.
- The data are a snapshot downloaded on 2026-11-24; SLA's cadastral layer is updated weekly.
