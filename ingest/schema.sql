-- Wickets.ai T20I demo schema (DuckDB). Source: Cricsheet (cricsheet.org).
-- Conventions: over is 0-indexed as in Cricsheet (over 0 = the 1st over).

CREATE TABLE venues (
    venue_id     INTEGER PRIMARY KEY,
    name         VARCHAR NOT NULL,   -- canonical name (Cricsheet string with ", City" suffix stripped)
    city         VARCHAR,
    country      VARCHAR,
    aliases      VARCHAR[]           -- every raw Cricsheet venue string mapped to this venue
);

CREATE TABLE matches (
    match_id          INTEGER PRIMARY KEY,   -- Cricsheet/ESPNcricinfo match id
    t20i_number       INTEGER,               -- official T20I number (men's and women's are numbered separately)
    gender            VARCHAR NOT NULL,      -- 'male' | 'female'
    date              DATE NOT NULL,
    season            VARCHAR,
    venue_id          INTEGER REFERENCES venues(venue_id),
    venue_raw         VARCHAR,
    city              VARCHAR,
    team1             VARCHAR NOT NULL,
    team2             VARCHAR NOT NULL,
    toss_winner       VARCHAR,
    toss_decision     VARCHAR,
    winner            VARCHAR,
    result            VARCHAR,               -- 'win' | 'tie' | 'no result' | 'draw'
    win_by_runs       INTEGER,
    win_by_wickets    INTEGER,
    decided_by        VARCHAR,               -- e.g. 'D/L', 'super over' (eliminator), 'bowl out'
    player_of_match   VARCHAR[],
    event_name        VARCHAR,
    event_match_no    VARCHAR,
    overs_per_side    INTEGER,
    balls_per_over    INTEGER,
    source            VARCHAR                -- 'cricsheet' | 'cricsheet-archive-<date>' | 'sportmonks' (withheld Afghanistan T20Is)
);

CREATE TABLE innings (
    match_id          INTEGER,
    innings           INTEGER,               -- 1, 2 (3+ for super overs)
    batting_team      VARCHAR,
    bowling_team      VARCHAR,
    is_super_over     BOOLEAN,
    target_runs       INTEGER,
    target_overs      DOUBLE,
    penalty_runs_pre  INTEGER,
    penalty_runs_post INTEGER,
    miscounted_overs  INTEGER,               -- overs the umpires miscounted (e.g. 7-ball overs), per Cricsheet
    PRIMARY KEY (match_id, innings)
);

CREATE TABLE players (
    player_id      VARCHAR PRIMARY KEY,      -- Cricsheet register identifier
    name           VARCHAR,                  -- Cricsheet scorecard name, e.g. 'JJ Bumrah'
    unique_name    VARCHAR,
    cricinfo_id    INTEGER,
    country        VARCHAR,                  -- team most often represented in T20Is
    batting_hand   VARCHAR,                  -- 'right' | 'left'          (player-profile source; NULL if unknown)
    bowling_style  VARCHAR,                  -- raw text, e.g. 'Right-arm fast'
    bowling_arm    VARCHAR,                  -- 'right' | 'left'
    bowling_kind   VARCHAR,                  -- 'pace' | 'spin'
    bowling_type   VARCHAR,                  -- 'fast','fast-medium','medium-fast','medium','off-spin','leg-spin','orthodox','wrist-spin'
    primary_role   VARCHAR,
    height_cm      INTEGER,
    profile_source VARCHAR                   -- where the profile fields came from
);

CREATE TABLE player_seasons (
    player_id        VARCHAR,
    year             INTEGER,
    avg_bowling_kph  DOUBLE,                 -- ESTIMATE, never ball-level fact
    source           VARCHAR,
    PRIMARY KEY (player_id, year)
);

CREATE TABLE match_roles (
    match_id         INTEGER,
    player_id        VARCHAR,
    team             VARCHAR,
    batting_position INTEGER,                -- order of arrival at the crease; NULL if did not bat
    captain          BOOLEAN,                -- not in Cricsheet; NULL until sourced
    wicketkeeper     BOOLEAN,                -- not in Cricsheet; NULL until sourced
    -- team is in the key: Cricsheet occasionally maps two same-named players in one match to one id
    PRIMARY KEY (match_id, player_id, team)
);

CREATE TABLE deliveries (
    match_id        INTEGER,
    innings         INTEGER,
    over            INTEGER,                 -- 0-indexed
    ball            INTEGER,                 -- sequence within the over, including illegal balls (1-based)
    batting_team    VARCHAR,
    bowling_team    VARCHAR,
    batter_id       VARCHAR,
    non_striker_id  VARCHAR,
    bowler_id       VARCHAR,
    runs_batter     INTEGER,
    extras          INTEGER,
    wides           INTEGER,
    noballs         INTEGER,
    byes            INTEGER,
    legbyes         INTEGER,
    penalty         INTEGER,
    total_runs      INTEGER,
    non_boundary    BOOLEAN,                 -- runs were all-run even though they total 4/6
    wicket_kind     VARCHAR,                 -- first dismissal on the ball (see wickets table for all)
    player_out_id   VARCHAR,
    -- derived
    is_legal_ball   BOOLEAN,                 -- not a wide and not a no-ball
    is_ball_faced   BOOLEAN,                 -- counts as a ball faced by the batter (everything but wides)
    runs_conceded   INTEGER,                 -- charged to bowler: total - byes - legbyes - penalty
    is_bowler_wkt   BOOLEAN,                 -- dismissal credited to the bowler
    is_four         BOOLEAN,
    is_six          BOOLEAN,
    is_dot          BOOLEAN,                 -- legal ball, nothing off the bat and nothing conceded
    phase           VARCHAR,                 -- 'powerplay' (overs 1-6) | 'middle' (7-15) | 'death' (16-20)
    in_powerplay    BOOLEAN,                 -- inside the actual mandatory powerplay recorded by Cricsheet
    is_super_over   BOOLEAN,
    PRIMARY KEY (match_id, innings, over, ball)
);

CREATE TABLE wickets (
    match_id       INTEGER,
    innings        INTEGER,
    over           INTEGER,
    ball           INTEGER,
    player_out_id  VARCHAR,
    kind           VARCHAR,
    bowler_id      VARCHAR,
    fielder_ids    VARCHAR[],
    is_bowler_wkt  BOOLEAN
);

-- Withheld / missing coverage, so answers can state their gaps.
CREATE TABLE coverage_notes (
    note VARCHAR
);
