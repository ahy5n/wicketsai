"""Apply data/player_profiles.csv onto the players table."""


def apply_profiles(con, path):
    con.execute(f"""
        UPDATE players p SET
            batting_hand   = pr.batting_hand,
            bowling_style  = pr.bowling_style,
            bowling_arm    = pr.bowling_arm,
            bowling_kind   = pr.bowling_kind,
            bowling_type   = pr.bowling_type,
            primary_role   = pr.primary_role,
            height_cm      = pr.height_cm,
            profile_source = pr.profile_source
        FROM read_csv('{path}', header=true, all_varchar=true,
                      nullstr='') AS pr
        WHERE p.player_id = pr.player_id
    """)
