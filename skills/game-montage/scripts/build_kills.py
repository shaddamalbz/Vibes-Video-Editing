"""Merge detector output into kills.json: group into sequences (multikills), label, rank."""
import json
from kitcfg import VIDEO, PLAYER

FPS = 60.0
ev = json.load(open("scan/events60.json"))
kills = sorted(ev["kills"], key=lambda k: k["kill_frame"])
deaths = sorted(ev["deaths"], key=lambda d: d["row_onset"])
SEQ_GAP = 20.0   # s: kills further apart than this are different rounds (a buy phase alone is ~20s+)

seqs, cur = [], []
for k in kills:
    if cur:
        gap = k["kill_time"] - cur[-1]["kill_time"]
        died_between = any(cur[-1]["kill_frame"] < d["row_onset"] < k["kill_frame"] for d in deaths)
        if gap > SEQ_GAP or died_between:
            seqs.append(cur); cur = []
    cur.append(k)
if cur:
    seqs.append(cur)

LABEL = {1: "single", 2: "double kill", 3: "triple kill", 4: "quadra kill", 5: "ACE"}
out = []
for si, s in enumerate(seqs, 1):
    for i, k in enumerate(s, 1):
        # did the player die soon after the sequence (clutch-ish / trade)?
        end = s[-1]["kill_time"]
        died_after = next((d["death_time"] for d in deaths if 0 < d["death_time"] - end < 15), None)
        out.append({
            "id": len(out) + 1,
            "kill_frame": k["kill_frame"],
            "kill_time": round(k["kill_time"], 4),
            "sequence": si, "index_in_sequence": i, "sequence_size": len(s),
            "label": LABEL.get(len(s), f"{len(s)}K"),
            "gap_from_prev_kill_s": round(k["kill_time"] - s[i - 2]["kill_time"], 2) if i > 1 else None,
            "confidence": k["confidence"],
            "signals": {"killfeed_row_onset_frame": k["row_onset"], "yellow_outline_frame": k["yellow_frame"],
                        "skull_onset_frame": k["skull_onset"], "audio_hi_band_ratio": round(k["audio_ratio"], 2)},
            "died_after_sequence_s": round(died_after - end, 2) if died_after else None,
        })

# rank sequences for the montage (best kills go to the drop)
rank = sorted(range(len(seqs)), key=lambda i: (-len(seqs[i]), seqs[i][0]["kill_time"]))
summary = [{"sequence": i + 1, "kills": len(seqs[i]), "label": LABEL.get(len(seqs[i]), f"{len(seqs[i])}K"),
            "start": round(seqs[i][0]["kill_time"], 2), "end": round(seqs[i][-1]["kill_time"], 2),
            "span_s": round(seqs[i][-1]["kill_time"] - seqs[i][0]["kill_time"], 2)} for i in range(len(seqs))]
data = {"video": VIDEO, "fps": 60, "player": PLAYER,
        "detection": "killfeed own-row (yellow outline + teal body) + centre-bottom kill skull + game-audio hi-band bump; 60fps frame-accurate",
        "total_kills": len(out), "kills": out, "sequences": summary, "deaths": [round(d["death_time"], 2) for d in deaths]}
json.dump(data, open("kills.json", "w"), indent=1)

print(f"{len(out)} kills in {len(seqs)} sequences; deaths {len(deaths)}")
for s in summary:
    print(f"  seq {s['sequence']:2d}  {s['label']:12s} start {s['start']:8.2f}s span {s['span_s']:5.2f}s")
