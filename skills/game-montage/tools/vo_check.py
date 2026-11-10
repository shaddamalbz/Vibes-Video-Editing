"""Whisper word check of a VO take: prints every word with its confidence, flags low ones.
usage: vo_check.py <wav> [model]"""
import sys, json, whisper
wav = sys.argv[1]; model = sys.argv[2] if len(sys.argv) > 2 else "small"
m = whisper.load_model(model)
r = m.transcribe(wav, language="en", word_timestamps=True, temperature=0, condition_on_previous_text=False)
out = []
for s in r["segments"]:
    print(f"\n[{s['start']:6.2f}-{s['end']:6.2f}] {s['text'].strip()}")
    line = []
    for w in s["words"]:
        p = w["probability"]; out.append([w["start"], w["end"], w["word"].strip(), round(p, 3)])
        line.append(w["word"].strip() + ("" if p >= 0.6 else f"({p:.2f})"))
    print("   ", " ".join(line))
json.dump(out, open(wav.rsplit(".", 1)[0] + f"_{model}_words.json", "w"), indent=0)
