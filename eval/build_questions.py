"""Generate eval/questions.yaml: the accuracy suite.

Each question has a reference ("gold") SQL query, written by hand against the documented conventions,
whose result is the correct answer. Grading (eval/run_eval.py) checks that the engine's answer table or
sentence contains the gold value(s). Some golds are pinned to official ESPNcricinfo figures
(`official:`), which checks the reference queries themselves.

Grade types:
  scalar  every value in the gold row must appear in the answer (numbers within rounding)
  list    the gold's first-column values (top N) must all appear in the answer's top rows
  refuse  the engine must answer can_answer = false
"""
from pathlib import Path

import yaml

OUT = Path(__file__).with_name("questions.yaml")

# Players by Cricsheet id, so gold queries can't be confused by duplicate names.
P = {
    "kohli": ("ba607b88", "Virat Kohli"), "rohit": ("740742ef", "Rohit Sharma"),
    "babar": ("8a75e999", "Babar Azam"), "buttler": ("99b75528", "Jos Buttler"),
    "bumrah": ("462411b3", "Jasprit Bumrah"), "mandhana": ("5d2eda89", "Smriti Mandhana"),
    "lanning": ("27e003ce", "Meg Lanning"), "perry": ("be150fc8", "Ellyse Perry"),
    "ecclestone": ("cdb82f1c", "Sophie Ecclestone"), "sky": ("271f83cd", "Suryakumar Yadav"),
    "salt": ("3d284ca3", "Phil Salt"), "shaheen": ("45a7e761", "Shaheen Shah Afridi"),
}

BAT = "FROM deliveries WHERE batter_id = '{id}' AND NOT is_super_over"
BOWL = "FROM deliveries WHERE bowler_id = '{id}' AND NOT is_super_over"
WKTS = "(SELECT COUNT(*) FROM wickets w JOIN innings i USING (match_id, innings) WHERE w.bowler_id = '{id}' AND w.is_bowler_wkt AND NOT i.is_super_over)"
OUTS = "(SELECT COUNT(*) FROM wickets w JOIN innings i USING (match_id, innings) WHERE w.player_out_id = '{id}' AND w.kind NOT IN ('retired hurt','retired not out') AND NOT i.is_super_over)"

TEMPLATES = [
    ("career_runs", "How many T20I runs has {name} scored?", f"SELECT SUM(runs_batter) {BAT}"),
    ("career_sr", "What is {name}'s career strike rate in T20Is?",
     f"SELECT ROUND(100.0 * SUM(runs_batter) / SUM(is_ball_faced::INT), 2) {BAT}"),
    ("career_sixes", "How many sixes has {name} hit in T20Is?", f"SELECT SUM(is_six::INT) {BAT}"),
    ("career_fours", "How many fours has {name} hit in T20 internationals?", f"SELECT SUM(is_four::INT) {BAT}"),
    ("highest_score", "What is {name}'s highest T20I score?",
     "SELECT MAX(runs) FROM batting_innings WHERE player_id = '{id}'"),
    ("fifties", "How many T20I half-centuries (50-99) does {name} have?",
     "SELECT COUNT(*) FROM batting_innings WHERE player_id = '{id}' AND runs BETWEEN 50 AND 99"),
    ("average", "What is {name}'s T20I batting average?",
     f"SELECT ROUND(SUM(runs_batter) / {OUTS}, 2) {BAT}"),
    ("pp_sr", "What's {name}'s strike rate in the powerplay in T20Is?",
     "SELECT ROUND(100.0 * SUM(runs_batter) / SUM(is_ball_faced::INT), 2) FROM deliveries "
     "WHERE batter_id = '{id}' AND phase = 'powerplay' AND NOT is_super_over"),
    ("vs_spin_sr", "What is {name}'s T20I strike rate against spin bowling?",
     "SELECT ROUND(100.0 * SUM(runs_batter) / SUM(is_ball_faced::INT), 2) FROM deliveries_ctx "
     "WHERE batter_id = '{id}' AND bowling_kind = 'spin' AND NOT is_super_over"),
    ("ducks", "How many T20I ducks has {name} made?",
     "SELECT COUNT(*) FROM batting_innings b WHERE b.player_id = '{id}' AND b.runs = 0 AND EXISTS ("
     "SELECT 1 FROM wickets w WHERE w.match_id = b.match_id AND w.innings = b.innings AND w.player_out_id = '{id}' "
     "AND w.kind NOT IN ('retired hurt','retired not out'))"),
]
BOWL_TEMPLATES = [
    ("career_wkts", "How many T20I wickets has {name} taken?", f"SELECT {WKTS}"),
    ("economy", "What is {name}'s career economy rate in T20Is?",
     f"SELECT ROUND(SUM(runs_conceded) / (SUM(is_legal_ball::INT) / 6.0), 2) {BOWL}"),
    ("death_econ", "What is {name}'s economy rate in the death overs (16-20) in T20Is?",
     "SELECT ROUND(SUM(runs_conceded) / (SUM(is_legal_ball::INT) / 6.0), 2) FROM deliveries "
     "WHERE bowler_id = '{id}' AND phase = 'death' AND NOT is_super_over"),
    ("dot_pct", "What percentage of {name}'s legal deliveries in T20Is have been dot balls?",
     f"SELECT ROUND(100.0 * SUM(is_dot::INT) / SUM(is_legal_ball::INT), 1) {BOWL}"),
    ("best_figures", "What are {name}'s best bowling figures in a T20I?",
     "SELECT wickets, runs_conceded FROM bowling_innings WHERE player_id = '{id}' "
     "ORDER BY wickets DESC, runs_conceded ASC LIMIT 1"),
]

BATTERS = ["kohli", "rohit", "babar", "buttler", "mandhana", "lanning", "sky", "salt"]
BOWLERS = ["bumrah", "ecclestone", "shaheen", "perry"]

# Pinned to official figures (ESPNcricinfo, 2026-10-25): career totals where coverage is complete.
OFFICIAL = {("career_runs", "kohli"): 4188, ("career_runs", "rohit"): 4231, ("career_runs", "babar"): 4596,
            ("career_runs", "buttler"): 4384, ("career_wkts", "ecclestone"): 154}

# Gaps the answer must disclose (players with games in the withheld Afghanistan matches or early women's
# matches); graded separately from correctness.
DISCLOSE = {"bumrah": "Afghanistan", "lanning": "Women's", "perry": "Women's", "mandhana": "Women's"}


def templated():
    qs = []
    for key in BATTERS:
        pid, name = P[key]
        for tid, q, sql in TEMPLATES:
            qs.append(_q(f"{tid}_{key}", q.format(name=name), sql.format(id=pid), "player_batting", key, tid))
    for key in BOWLERS:
        pid, name = P[key]
        for tid, q, sql in BOWL_TEMPLATES:
            qs.append(_q(f"{tid}_{key}", q.format(name=name), sql.format(id=pid), "player_bowling", key, tid))
    return qs


def _q(qid, question, sql, category, key=None, tid=None, grade="scalar", **kw):
    d = {"id": qid, "category": category, "question": question, "grade": grade, "gold_sql": " ".join(sql.split()) if sql else None}
    if key and (tid, key) in OFFICIAL:
        d["official"] = OFFICIAL[(tid, key)]
    if key in DISCLOSE:
        d["expect_note"] = DISCLOSE[key]
    d.update(kw)
    return d


BESPOKE = [
    # --- The six example questions from the brief
    _q("brief_sky_spin_sixes", "How many sixes has Suryakumar Yadav hit off spinners in T20Is?",
       "SELECT SUM(is_six::INT) FROM deliveries_ctx WHERE batter_id = '271f83cd' AND bowling_kind = 'spin' AND NOT is_super_over",
       "brief"),
    _q("brief_bumrah_shaheen_death", "Bumrah vs Shaheen Afridi at the death: economy, dot-ball % and wickets.",
       "SELECT ROUND(SUM(runs_conceded) FILTER (WHERE bowler_id='462411b3') / (SUM(is_legal_ball::INT) FILTER (WHERE bowler_id='462411b3') / 6.0), 2), "
       "ROUND(SUM(runs_conceded) FILTER (WHERE bowler_id='45a7e761') / (SUM(is_legal_ball::INT) FILTER (WHERE bowler_id='45a7e761') / 6.0), 2) "
       "FROM deliveries WHERE phase = 'death' AND NOT is_super_over AND bowler_id IN ('462411b3','45a7e761')", "brief",
       expect_note="Afghanistan"),
    _q("brief_no11_top_score", "When did a No. 11 last top-score in a men's T20I innings?",
       "WITH s AS (SELECT b.match_id, b.runs, r.batting_position, MAX(b.runs) OVER (PARTITION BY b.match_id, b.innings) top "
       "FROM batting_innings b JOIN match_roles r ON r.match_id=b.match_id AND r.player_id=b.player_id) "
       "SELECT m.date FROM s JOIN matches m USING (match_id) WHERE s.batting_position=11 AND s.runs=s.top AND s.runs>0 "
       "AND m.gender='male' ORDER BY m.date DESC LIMIT 1", "brief"),
    _q("brief_women_pp_since_2020", "What are the highest powerplay totals in women's T20Is since 2020?",
       "SELECT SUM(total_runs) r FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender='female' "
       "AND m.date >= DATE '2020-01-01' AND phase='powerplay' AND NOT is_super_over GROUP BY d.match_id, d.innings ORDER BY r DESC LIMIT 1",
       "brief"),
    _q("brief_salt_sr_by_year", "How has Phil Salt's T20I strike rate changed year by year?",
       "SELECT ROUND(100.0*SUM(runs_batter)/SUM(is_ball_faced::INT),2) FROM deliveries_ctx WHERE batter_id='3d284ca3' "
       "AND NOT is_super_over AND year(date)=2023", "brief"),
    _q("brief_lhb_v_lawrist", "What's the strike rate of left-handed batters against left-arm wrist spin in men's T20Is?",
       "SELECT ROUND(100.0*SUM(runs_batter)/SUM(is_ball_faced::INT),2) FROM deliveries_ctx WHERE batter_hand='left' "
       "AND bowling_type='wrist-spin' AND gender='male' AND NOT is_super_over", "brief"),

    # --- Records
    _q("rec_highest_total_men", "What is the highest team total in a men's T20I?",
       "SELECT SUM(total_runs) t FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender='male' AND NOT is_super_over "
       "GROUP BY d.match_id, d.innings ORDER BY t DESC LIMIT 1", "records"),
    _q("rec_highest_total_women", "Highest team total in women's T20Is?",
       "SELECT SUM(total_runs) t FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender='female' AND NOT is_super_over "
       "GROUP BY d.match_id, d.innings ORDER BY t DESC LIMIT 1", "records"),
    _q("rec_lowest_total_men", "What's the lowest completed team total (all out) in men's T20Is?",
       "WITH t AS (SELECT d.match_id, d.innings, SUM(total_runs) runs, COUNT(player_out_id) FILTER (WHERE wicket_kind NOT IN ('retired hurt','retired not out')) w "
       "FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender='male' AND NOT is_super_over GROUP BY 1,2) "
       "SELECT MIN(runs) FROM t WHERE w >= 10", "records"),
    _q("rec_most_runs_men", "Who has scored the most runs in men's T20Is? Give the top 5.",
       "SELECT pi.name FROM batting_innings b JOIN player_index pi USING (player_id) WHERE pi.gender='male' "
       "GROUP BY pi.player_id, pi.name ORDER BY SUM(runs) DESC LIMIT 5", "records", grade="list"),
    _q("rec_most_runs_women", "Top 5 run-scorers in women's T20Is?",
       "SELECT pi.name FROM batting_innings b JOIN player_index pi USING (player_id) WHERE pi.gender='female' "
       "GROUP BY pi.player_id, pi.name ORDER BY SUM(runs) DESC LIMIT 5", "records", grade="list", expect_note="Women's"),
    _q("rec_most_wkts_men", "Who are the five leading wicket-takers in men's T20Is?",
       "SELECT pi.name FROM bowling_innings b JOIN player_index pi USING (player_id) WHERE pi.gender='male' "
       "GROUP BY pi.player_id, pi.name ORDER BY SUM(wickets) DESC LIMIT 5", "records", grade="list", expect_note="Afghanistan"),
    _q("rec_most_wkts_women", "Who has the most wickets in women's T20Is (top 5)?",
       "SELECT pi.name FROM bowling_innings b JOIN player_index pi USING (player_id) WHERE pi.gender='female' "
       "GROUP BY pi.player_id, pi.name ORDER BY SUM(wickets) DESC LIMIT 5", "records", grade="list", expect_note="Women's"),
    _q("rec_most_sixes_men", "Who has hit the most sixes in men's T20Is?",
       "SELECT pi.name FROM deliveries d JOIN player_index pi ON pi.player_id=d.batter_id WHERE pi.gender='male' AND NOT is_super_over "
       "GROUP BY pi.player_id, pi.name ORDER BY SUM(is_six::INT) DESC LIMIT 1", "records", grade="list"),
    _q("rec_most_sixes_women", "Most sixes in women's T20Is: who leads?",
       "SELECT pi.name FROM deliveries d JOIN player_index pi ON pi.player_id=d.batter_id WHERE pi.gender='female' AND NOT is_super_over "
       "GROUP BY pi.player_id, pi.name ORDER BY SUM(is_six::INT) DESC LIMIT 1", "records", grade="list"),
    _q("rec_highest_score_men", "What is the highest individual score in a men's T20I?",
       "SELECT MAX(runs) FROM batting_innings b JOIN matches m USING (match_id) WHERE m.gender='male'", "records"),
    _q("rec_highest_score_women", "Highest individual innings in women's T20Is?",
       "SELECT MAX(runs) FROM batting_innings b JOIN matches m USING (match_id) WHERE m.gender='female'", "records"),
    _q("rec_best_figs_men", "What are the best bowling figures in a men's T20I?",
       "SELECT wickets, runs_conceded FROM bowling_innings b JOIN matches m USING (match_id) WHERE m.gender='male' "
       "ORDER BY wickets DESC, runs_conceded LIMIT 1", "records"),
    _q("rec_fastest_100_men", "What is the fastest hundred (fewest balls) in men's T20Is?",
       "WITH r AS (SELECT match_id, innings, batter_id, SUM(runs_batter) OVER w rs, SUM(is_ball_faced::INT) OVER w bs "
       "FROM deliveries_ctx WHERE gender='male' AND NOT is_super_over WINDOW w AS (PARTITION BY match_id, innings, batter_id ORDER BY over, ball)) "
       "SELECT MIN(bs) FROM r WHERE rs >= 100", "records"),
    _q("rec_fastest_50_men", "Fastest fifty by balls faced in a men's T20I?",
       "WITH r AS (SELECT match_id, innings, batter_id, SUM(runs_batter) OVER w rs, SUM(is_ball_faced::INT) OVER w bs "
       "FROM deliveries_ctx WHERE gender='male' AND NOT is_super_over WINDOW w AS (PARTITION BY match_id, innings, batter_id ORDER BY over, ball)) "
       "SELECT MIN(bs) FROM r WHERE rs >= 50", "records"),
    _q("rec_most_ducks_men", "Which men's player has the most T20I ducks?",
       "SELECT pi.name FROM batting_innings b JOIN player_index pi USING (player_id) WHERE pi.gender='male' AND b.runs=0 AND EXISTS "
       "(SELECT 1 FROM wickets w WHERE w.match_id=b.match_id AND w.innings=b.innings AND w.player_out_id=b.player_id "
       "AND w.kind NOT IN ('retired hurt','retired not out')) GROUP BY pi.player_id, pi.name ORDER BY COUNT(*) DESC LIMIT 1",
       "records", grade="list"),
    _q("rec_most_hundreds_men", "Who has the most hundreds in men's T20Is?",
       "SELECT pi.name FROM batting_innings b JOIN player_index pi USING (player_id) WHERE pi.gender='male' AND runs>=100 "
       "GROUP BY pi.player_id, pi.name ORDER BY COUNT(*) DESC, pi.name LIMIT 1", "records", grade="list"),
    _q("rec_most_matches_women", "Which woman has played the most T20Is in the database?",
       "SELECT pi.name FROM match_roles r JOIN player_index pi USING (player_id) WHERE pi.gender='female' "
       "GROUP BY pi.player_id, pi.name ORDER BY COUNT(*) DESC LIMIT 1", "records", grade="list"),
    _q("rec_biggest_win_runs_men", "What is the biggest winning margin by runs in a men's T20I?",
       "SELECT MAX(win_by_runs) FROM matches WHERE gender='male'", "records"),
    _q("rec_most_extras_innings", "What's the most extras conceded in a single men's T20I innings?",
       "SELECT SUM(extras) e FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender='male' AND NOT is_super_over "
       "GROUP BY d.match_id, d.innings ORDER BY e DESC LIMIT 1", "records"),

    # --- Phases and splits
    _q("phase_india_pp_rr_2024", "What was India men's run rate in the powerplay in 2024 T20Is?",
       "SELECT ROUND(SUM(total_runs) / (SUM(is_legal_ball::INT)/6.0), 2) FROM deliveries_ctx WHERE gender='male' AND batting_team='India' "
       "AND phase='powerplay' AND year(date)=2024 AND NOT is_super_over", "phase"),
    _q("phase_death_rr_men_2025", "What was the average run rate at the death (overs 16-20) across men's T20Is in 2025?",
       "SELECT ROUND(SUM(total_runs) / (SUM(is_legal_ball::INT)/6.0), 2) FROM deliveries_ctx WHERE gender='male' AND phase='death' "
       "AND year(date)=2025 AND NOT is_super_over", "phase", expect_note="Afghanistan"),
    _q("phase_most_death_wkts_men", "Who has taken the most death-over wickets in men's T20Is?",
       "SELECT pi.name FROM wickets w JOIN deliveries d USING (match_id, innings, over, ball) JOIN player_index pi ON pi.player_id=w.bowler_id "
       "WHERE w.is_bowler_wkt AND d.phase='death' AND NOT d.is_super_over AND pi.gender='male' GROUP BY pi.player_id, pi.name "
       "ORDER BY COUNT(*) DESC LIMIT 1", "phase", grade="list"),
    _q("phase_bumrah_pp_wkts", "How many powerplay wickets has Jasprit Bumrah taken in T20Is?",
       "SELECT COUNT(*) FROM wickets w JOIN deliveries d USING (match_id, innings, over, ball) WHERE w.bowler_id='462411b3' "
       "AND w.is_bowler_wkt AND d.phase='powerplay' AND NOT d.is_super_over", "phase", expect_note="Afghanistan"),
    _q("split_kohli_v_pace", "What's Virat Kohli's strike rate against pace bowling in T20Is?",
       "SELECT ROUND(100.0*SUM(runs_batter)/SUM(is_ball_faced::INT),2) FROM deliveries_ctx WHERE batter_id='ba607b88' "
       "AND bowling_kind='pace' AND NOT is_super_over", "split"),
    _q("split_buttler_v_legspin", "How many times has Jos Buttler been dismissed by leg-spinners in T20Is?",
       "SELECT COUNT(*) FROM wickets w JOIN players p ON p.player_id=w.bowler_id WHERE w.player_out_id='99b75528' "
       "AND w.is_bowler_wkt AND p.bowling_type='leg-spin'", "split"),
    _q("split_mandhana_v_offspin", "What is Smriti Mandhana's strike rate against off-spin in T20Is?",
       "SELECT ROUND(100.0*SUM(runs_batter)/SUM(is_ball_faced::INT),2) FROM deliveries_ctx WHERE batter_id='5d2eda89' "
       "AND bowling_type='off-spin' AND NOT is_super_over", "split", expect_note="Women's"),
    _q("split_lhb_v_orthodox_women", "Strike rate of left-handers against left-arm orthodox spin in women's T20Is?",
       "SELECT ROUND(100.0*SUM(runs_batter)/SUM(is_ball_faced::INT),2) FROM deliveries_ctx WHERE gender='female' "
       "AND batter_hand='left' AND bowling_type='orthodox' AND NOT is_super_over", "split"),
    _q("split_pace_spin_share_2025", "What share of legal deliveries in men's T20Is between Full Members... no: what share of all legal balls in men's T20Is in 2025 were bowled by spinners?",
       "SELECT ROUND(100.0*SUM(is_legal_ball::INT) FILTER (WHERE bowling_kind='spin') / SUM(is_legal_ball::INT) FILTER (WHERE bowling_kind IS NOT NULL), 1) "
       "FROM deliveries_ctx WHERE gender='male' AND year(date)=2025 AND NOT is_super_over", "split"),

    # --- Head to head
    _q("h2h_rohit_starc", "How many times has Mitchell Starc dismissed Rohit Sharma in T20Is?",
       "SELECT COUNT(*) FROM wickets WHERE bowler_id=(SELECT player_id FROM player_index WHERE full_name='Mitchell Starc' AND gender='male') "
       "AND player_out_id='740742ef' AND is_bowler_wkt", "h2h"),
    _q("h2h_kohli_v_rashid_runs", "How many runs has Virat Kohli scored off Adil Rashid in T20Is?",
       "SELECT SUM(runs_batter) FROM deliveries WHERE batter_id='ba607b88' AND bowler_id=(SELECT player_id FROM player_index WHERE full_name='Adil Rashid') "
       "AND NOT is_super_over", "h2h"),
    _q("h2h_buttler_v_bumrah_balls", "How many balls has Jos Buttler faced from Jasprit Bumrah in T20Is?",
       "SELECT SUM(is_ball_faced::INT) FROM deliveries WHERE batter_id='99b75528' AND bowler_id='462411b3' AND NOT is_super_over", "h2h"),
    _q("h2h_mandhana_v_ecclestone", "How many times has Sophie Ecclestone dismissed Smriti Mandhana in T20Is?",
       "SELECT COUNT(*) FROM wickets WHERE bowler_id='cdb82f1c' AND player_out_id='5d2eda89' AND is_bowler_wkt", "h2h"),
    _q("team_ind_v_pak_wins", "How many men's T20Is has India won against Pakistan?",
       "SELECT COUNT(*) FROM matches WHERE gender='male' AND 'India' IN (team1,team2) AND 'Pakistan' IN (team1,team2) AND winner='India'", "team"),
    _q("team_aus_eng_women_matches", "How many women's T20Is have Australia and England played against each other?",
       "SELECT COUNT(*) FROM matches WHERE gender='female' AND 'Australia' IN (team1,team2) AND 'England' IN (team1,team2)", "team",
       expect_note="Women's"),
    _q("team_nz_2023_wins", "How many men's T20Is did New Zealand win in 2023?",
       "SELECT COUNT(*) FROM matches WHERE gender='male' AND year(date)=2023 AND winner='New Zealand'", "team"),
    _q("team_india_women_2024_matches", "How many T20Is did India women play in 2024?",
       "SELECT COUNT(*) FROM matches WHERE gender='female' AND year(date)=2024 AND 'India' IN (team1,team2)", "team"),
    _q("team_afg_wins_2022", "How many men's T20Is did Afghanistan win in 2022?",
       "SELECT COUNT(*) FROM matches WHERE gender='male' AND year(date)=2022 AND winner='Afghanistan'", "team"),
    _q("team_afg_since_2025", "How many T20Is has Afghanistan won since the start of 2025?", None, "coverage", grade="refuse",
       expect_note="Afghanistan"),
    _q("team_afg_highest_total", "What is Afghanistan's highest T20I total?",
       "SELECT SUM(total_runs) t FROM deliveries WHERE batting_team='Afghanistan' AND NOT is_super_over GROUP BY match_id, innings ORDER BY t DESC LIMIT 1",
       "coverage", expect_note="Afghanistan"),
    _q("team_rashid_khan_wkts", "How many T20I wickets has Afghanistan's Rashid Khan taken?",
       f"SELECT {WKTS.format(id='5f547c8b')}", "coverage", expect_note="Afghanistan"),

    # --- Venues, toss, results
    _q("venue_most_men", "Which ground has hosted the most men's T20Is?",
       "SELECT v.name FROM matches m JOIN venues v USING (venue_id) WHERE m.gender='male' GROUP BY v.venue_id, v.name ORDER BY COUNT(*) DESC LIMIT 1",
       "venue", grade="list"),
    _q("venue_mcg_highest", "What's the highest T20I team total at the Melbourne Cricket Ground (men)?",
       "SELECT SUM(total_runs) t FROM deliveries d JOIN matches m USING (match_id) JOIN venues v USING (venue_id) "
       "WHERE m.gender='male' AND v.name='Melbourne Cricket Ground' AND NOT is_super_over GROUP BY d.match_id, d.innings ORDER BY t DESC LIMIT 1", "venue"),
    _q("venue_wankhede_matches", "How many men's T20Is have been played at the Wankhede Stadium?",
       "SELECT COUNT(*) FROM matches m JOIN venues v USING (venue_id) WHERE m.gender='male' AND v.name ILIKE 'Wankhede%'", "venue"),
    _q("toss_bat_first_win_pct_men", "In men's T20Is with a result, how often has the team batting first won (percentage)?",
       "SELECT ROUND(100.0*COUNT(*) FILTER (WHERE winner=i.batting_team)/COUNT(*),1) FROM matches m JOIN innings i ON i.match_id=m.match_id AND i.innings=1 "
       "WHERE m.gender='male' AND m.result='win'", "results"),
    _q("toss_win_match_pct_women", "In women's T20Is with a result, what percentage were won by the side that won the toss?",
       "SELECT ROUND(100.0*COUNT(*) FILTER (WHERE winner=toss_winner)/COUNT(*),1) FROM matches WHERE gender='female' AND result='win'", "results"),
    _q("results_ties_men", "How many men's T20Is in the database ended in a tie?",
       "SELECT COUNT(*) FROM matches WHERE gender='male' AND result='tie'", "results"),
    _q("results_super_overs", "How many T20Is (men's and women's) have been decided by a super over?",
       "SELECT COUNT(*) FROM matches WHERE decided_by='super over'", "results"),
    _q("results_matches_2025_men", "How many men's T20Is were played in 2025?",
       "SELECT COUNT(*) FROM matches WHERE gender='male' AND year(date)=2025", "results", expect_note="Afghanistan"),
    _q("results_first_women", "When was the first women's T20I with ball-by-ball records in the database?",
       "SELECT MIN(date) FROM matches WHERE gender='female'", "results"),

    # --- Trends
    _q("trend_men_rr_2024", "What was the overall run rate in men's T20Is between Full Member nations in 2024?",
       "SELECT ROUND(SUM(total_runs)/(SUM(is_legal_ball::INT)/6.0),2) FROM deliveries_ctx d JOIN matches m USING (match_id) "
       "WHERE m.gender='male' AND year(m.date)=2024 AND NOT is_super_over AND m.team1 IN ('Afghanistan','Australia','Bangladesh','England','India','Ireland','New Zealand','Pakistan','South Africa','Sri Lanka','West Indies','Zimbabwe') "
       "AND m.team2 IN ('Afghanistan','Australia','Bangladesh','England','India','Ireland','New Zealand','Pakistan','South Africa','Sri Lanka','West Indies','Zimbabwe')", "trend"),
    _q("trend_sixes_per_match_women_2025", "How many sixes per match were hit in women's T20Is in 2025?",
       "SELECT ROUND(SUM(is_six::INT)*1.0/COUNT(DISTINCT match_id),2) FROM deliveries_ctx WHERE gender='female' AND year(date)=2025 AND NOT is_super_over", "trend"),
    _q("trend_kohli_best_year", "In which calendar year did Virat Kohli score the most T20I runs?",
       "SELECT year(date) FROM deliveries_ctx WHERE batter_id='ba607b88' AND NOT is_super_over GROUP BY 1 ORDER BY SUM(runs_batter) DESC LIMIT 1", "trend"),
    _q("trend_bumrah_2024_econ", "What was Jasprit Bumrah's T20I economy rate in 2024?",
       "SELECT ROUND(SUM(runs_conceded)/(SUM(is_legal_ball::INT)/6.0),2) FROM deliveries_ctx WHERE bowler_id='462411b3' AND year(date)=2024 AND NOT is_super_over", "trend"),

    # --- Should say "can't answer"
    _q("refuse_test_runs", "How many Test runs has Joe Root scored?", None, "refuse", grade="refuse"),
    _q("refuse_odi", "What's the highest ODI score by an Indian?", None, "refuse", grade="refuse"),
    _q("refuse_ipl", "Who has the most sixes in IPL history?", None, "refuse", grade="refuse"),
    _q("refuse_speed", "What is the fastest ball Jasprit Bumrah has bowled in a T20I?", None, "refuse", grade="refuse"),
    _q("refuse_line_length", "What percentage of Shaheen Afridi's deliveries are yorkers?", None, "refuse", grade="refuse"),
    _q("refuse_fielding_pos", "How many catches has Glenn Phillips taken at point in T20Is?", None, "refuse", grade="refuse"),
    _q("refuse_shot_type", "How many runs has Babar Azam scored with the cover drive in T20Is?", None, "refuse", grade="refuse"),
    _q("refuse_future", "Who will win the next men's T20 World Cup?", None, "refuse", grade="refuse"),
    _q("refuse_opinion", "Is Virat Kohli a better T20I batter than Babar Azam?", None, "refuse", grade="refuse"),
    _q("refuse_bbl", "Who has the most wickets in the Big Bash League?", None, "refuse", grade="refuse"),
    _q("refuse_wagon_wheel", "Where on the field does Suryakumar Yadav score most of his runs?", None, "refuse", grade="refuse"),
    _q("refuse_crowd", "What was the attendance at the 2024 men's T20 World Cup final?", None, "refuse", grade="refuse"),
]

# --- Follow-ups: the second question only makes sense with the first.
FOLLOWUPS = [
    {"id": "fu_kohli_then_2016", "category": "followup", "grade": "scalar",
     "turns": ["How many T20I runs has Virat Kohli scored?", "And in 2016 alone?"],
     "gold_sql": "SELECT SUM(runs_batter) FROM deliveries_ctx WHERE batter_id='ba607b88' AND year(date)=2016 AND NOT is_super_over"},
    {"id": "fu_bumrah_then_death", "category": "followup", "grade": "scalar",
     "turns": ["What's Jasprit Bumrah's T20I economy rate?", "Now only in the death overs."],
     "gold_sql": "SELECT ROUND(SUM(runs_conceded)/(SUM(is_legal_ball::INT)/6.0),2) FROM deliveries WHERE bowler_id='462411b3' AND phase='death' AND NOT is_super_over",
     "expect_note": "Afghanistan"},
    {"id": "fu_mandhana_then_vs_aus", "category": "followup", "grade": "scalar",
     "turns": ["How many runs has Smriti Mandhana scored in T20Is?", "What about just against Australia?"],
     "gold_sql": "SELECT SUM(runs_batter) FROM deliveries WHERE batter_id='5d2eda89' AND bowling_team='Australia' AND NOT is_super_over",
     "expect_note": "Women's"},
    {"id": "fu_most_sixes_then_women", "category": "followup", "grade": "list",
     "turns": ["Who has hit the most sixes in men's T20Is?", "Same question for women."],
     "gold_sql": "SELECT pi.name FROM deliveries d JOIN player_index pi ON pi.player_id=d.batter_id WHERE pi.gender='female' AND NOT is_super_over GROUP BY pi.player_id, pi.name ORDER BY SUM(is_six::INT) DESC LIMIT 1"},
    {"id": "fu_babar_then_sr", "category": "followup", "grade": "scalar",
     "turns": ["How many T20I runs does Babar Azam have against Australia?", "And his strike rate in those games?"],
     "gold_sql": "SELECT ROUND(100.0*SUM(runs_batter)/SUM(is_ball_faced::INT),2) FROM deliveries WHERE batter_id='8a75e999' AND bowling_team='Australia' AND NOT is_super_over"},
]


def main():
    qs = templated() + BESPOKE
    for q in qs:
        q["turns"] = [q.pop("question")]
    # tidy one question whose wording I drafted badly
    for q in qs:
        if q["id"] == "split_pace_spin_share_2025":
            q["turns"] = ["What share of legal deliveries in men's T20Is in 2025 were bowled by spinners (among bowlers whose type is known)?"]
        if q["gold_sql"] is None:
            del q["gold_sql"]
    qs += FOLLOWUPS
    OUT.write_text(yaml.safe_dump(qs, sort_keys=False, width=140))
    print(f"{len(qs)} questions -> {OUT}")


if __name__ == "__main__":
    main()
