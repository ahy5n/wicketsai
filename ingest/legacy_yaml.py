"""Convert Cricsheet's legacy YAML match format (data_version 0.9x) to the JSON 1.x structure.

Legacy deliveries are keyed by over.ball floats (0.1, 0.2, ...). A 10th delivery in an over
(after extras) would be 0.10 == 0.1 as a float, so only the integer over is taken from the key and
the order of the list is trusted for sequence.
"""
import yaml


def _delivery(d):
    runs = d["runs"]
    out = {
        "batter": d["batsman"],
        "bowler": d["bowler"],
        "non_striker": d["non_striker"],
        "runs": {"batter": runs["batsman"], "extras": runs["extras"], "total": runs["total"]},
    }
    if runs.get("non_boundary"):
        out["runs"]["non_boundary"] = True
    if d.get("extras"):
        out["extras"] = dict(d["extras"])
    wickets = d.get("wickets") or d.get("wicket") or []  # a dict, or a list when two fall on one ball
    if isinstance(wickets, dict):
        wickets = [wickets]
    if wickets:
        out["wickets"] = [{
            "player_out": w["player_out"],
            "kind": w["kind"],
            **({"fielders": [{"name": f} for f in w["fielders"]]} if w.get("fielders") else {}),
        } for w in wickets]
    return out


def convert(d):
    innings = []
    for entry in d["innings"]:
        (label, inn), = entry.items()
        overs = {}
        for ball in inn["deliveries"]:
            (key, delivery), = ball.items()
            overs.setdefault(int(float(key)), []).append(_delivery(delivery))
        out = {"team": inn["team"], "overs": [{"over": o, "deliveries": ds} for o, ds in sorted(overs.items())]}
        if "super over" in label.lower() or inn.get("super_over"):
            out["super_over"] = True
        if inn.get("penalty_runs"):
            out["penalty_runs"] = inn["penalty_runs"]
        innings.append(out)
    info = dict(d["info"])
    info["dates"] = [str(x) for x in info["dates"]]
    return {"meta": {**d["meta"], "converted_from": "yaml"}, "info": info, "innings": innings}


def load(text):
    return convert(yaml.safe_load(text))
