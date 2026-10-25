# Wickets.ai statistical conventions (T20I demo)

ICC playing and statistical conventions apply unless the question asks otherwise. Every answer states
any convention it relied on that a reader might not assume.

## Scope
- T20 Internationals only, men's (`gender = 'male'`) and women's (`'female'`). Tests, ODIs, franchise
  and domestic T20s are out of scope: say so rather than answer.
- If a question doesn't say men's or women's and the player or team settles it, use that. If it doesn't
  (e.g. "highest T20I total"), answer for men's and say so, or give both when that's short.
- Super overs are excluded from all batting, bowling and team records (ICC practice). Bowl-outs are
  not deliveries.

## Batting
- **Runs** = runs off the bat (`runs_batter`). Extras never count to the batter.
- **Balls faced** = every delivery except wides (no-balls count as balls faced).
- **Strike rate** = runs / balls faced x 100.
- **Dismissals** count every way out except retired hurt / retired not out. Retired out counts.
- **Average** = runs / dismissals; undefined when never dismissed (show "-", not infinity).
- **Innings** = innings in which the player faced at least one ball or was dismissed without facing
  (e.g. run out as non-striker). Players who didn't bat aren't counted.
- **Fours / sixes** are boundaries off the bat only (`is_four`, `is_six`); all-run 4s are not fours.
- **Fifty** = 50-99, **hundred** = 100+ in an innings.
- **Batting position** is order of arrival at the crease (openers 1 and 2).

## Bowling
- **Balls bowled** = legal deliveries (wides and no-balls are not balls in the over).
- **Overs** are written o.b, e.g. 23 balls = 3.5 overs. Never compute decimal overs as balls/6 in output.
- **Runs conceded** = total runs minus byes, leg-byes and penalty runs. Wides and no-balls (and runs
  off the bat from no-balls) are charged to the bowler.
- **Wickets** = bowled, caught, caught and bowled, lbw, stumped, hit wicket. Run outs and other
  dismissals are not the bowler's.
- **Economy** = runs conceded / (balls bowled / 6).
- **Bowling average** = runs conceded / wickets. **Bowling strike rate** = balls bowled / wickets.
- **Dot-ball %** = legal balls with nothing off the bat and nothing conceded / legal balls x 100.
- **Best figures** rank by wickets, then fewest runs.

## Phases (fixed over numbers, per the brief)
- Powerplay = overs 1-6, middle = overs 7-15, death = overs 16-20 (database `over` 0-5, 6-14, 15-19).
- Rain-reduced matches keep these over numbers. `in_powerplay` holds the actual mandatory powerplay
  when a question is specifically about it.

## Bowling types and batting hand
- Come from player profiles (English Wikipedia), not from ball-level data. Players without a profile
  have NULL type/hand: say how many balls were unclassified when it matters (more than ~2%).
- Pace = fast, fast-medium, medium-fast, medium. Spin = off-spin, leg-spin, orthodox (left-arm
  finger spin), wrist-spin (left-arm wrist spin). "Left-arm wrist spin" = `bowling_type = 'wrist-spin'`.
  "Leg-spin" alone means right-arm leg-spin.

## Teams and matches
- "Matches" means T20Is with ball-by-ball records in the database. Matches abandoned without a ball
  aren't included (official counts can be one or two higher).
- Team totals include extras. A team's innings total is `SUM(total_runs)` for that innings.
- Home / away / neutral is not stored; don't infer it from venue country unless asked, and say so.

## Coverage (say so whenever it affects the answer)
- Men's ball-by-ball from Feb 2005; women's from 2009, patchy before about 2014.
- 30 Afghanistan men's T20Is after 26 Jun 2024 are not in the database (withheld by Cricsheet).
  Answers involving Afghanistan, or a team or player that played them since then, must say this.
- Associate-nation coverage since 2019 is partial.
