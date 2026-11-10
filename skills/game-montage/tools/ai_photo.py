"""AI polish for a thumbnail photo: in-game frame -> Codex CLI image generation (uses the Codex CLI's own login)
-> PNG that thumbkit / make_thumb uses as PHOTO. Text and layout stay with the thumbnail script; the AI only does the photo.

usage:
  py -3.14 ai_photo.py <frame.png> <out.png> "<what this picture should show>" [--look dark|keep] [--model gpt-6-luna]
  e.g. ai_photo.py f_K3362.5.png ai/s2_ai_v1.png "the red fox Pingping, a girl in disguise: sly smirk, her shadow on the rock is a young woman"

Writes <out>.prompt.txt (full prompt) and <out>.log (Codex output) next to the result. ~1-7 min per image, 1536x1024 PNG.
--look dark (default, user 26 Oct 2026): dark background, subtle rim light + soft key light on the subject, focus on the subject.
--look keep: keep the frame's own lighting/background, only clean up and sharpen.
The user's ~/.codex/config.toml default model (gpt-6-sol) is refused with a ChatGPT login, so --model defaults to gpt-6-luna.
A generated image can't be made again identically: once a final uses it, it is a recipe input (never move or delete it).
"""
import argparse, glob, os, shutil, subprocess, sys, time

BASE = """Use your image generation tool to edit the attached screenshot from a video game into a YouTube / TikTok thumbnail photo.
No text, no letters, no subtitles, no logos, no watermark anywhere in the image (the text is added later by another tool).

Keep the real game art style (same rendering look, not cartoon, not painting) and keep every character's exact game design
(face, horns, hair, armor, clothes, colours). Remove the game HUD completely (health bars, skill icons, prompts, subtitles).
Make the subject sharp and in focus (screenshots often have motion blur and depth of field).

What this picture should show:
{what}
"""
LOOKS = {
    "dark": """Lighting: the BACKGROUND STAYS DARK, almost black in the corners, no bright fire or big light sources behind.
Only a subtle rim light on the subject's outline and a soft key light on the face, high contrast, low-key, so all the attention is on the subject.""",
    "keep": """Lighting: keep the screenshot's own lighting and background mood, only a little more contrast on the subject.""",
}
COMPOSITION = """Composition: landscape 3:2. Everything important inside the central square of the image (the thumbnail tool crops a centred square),
the subject's head/face in the upper half of that square (the bottom third will be covered by big text), nothing important near the left and right edges.

Save the result as a PNG file named {name} in the current working directory, then reply with only the file path."""
PORTRAIT = """Composition: portrait 2:3, the picture fills the whole frame edge to edge with the real scene (extend the scene where needed, no borders, no colour panels).
The subject in the middle and lower part, the top third calm (sky, mist, dark trees) because text goes there later, nothing important near the edges.

Save the result as a PNG file named {name} in the current working directory, then reply with only the file path."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"), ap.add_argument("out"), ap.add_argument("what")
    ap.add_argument("--look", choices=sorted(LOOKS), default="dark")
    ap.add_argument("--model", default="gpt-6-luna")
    ap.add_argument("--portrait", action="store_true", help="full-bleed 2:3 picture for a text-on-image 9:16 thumbnail (Phantom Blade Zero style)")
    a = ap.parse_args()

    src, out = os.path.abspath(a.src), os.path.abspath(a.out)
    wd, name = os.path.dirname(out), os.path.basename(out)
    os.makedirs(wd, exist_ok=True)
    prompt = "\n".join([BASE.format(what=a.what.strip()), LOOKS[a.look], "", (PORTRAIT if a.portrait else COMPOSITION).format(name=name)])
    open(out + ".prompt.txt", "w", encoding="utf-8").write(prompt)

    codex = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex:
        sys.exit("codex CLI not found (npm install -g @openai/codex, user level)")
    t0 = time.time()
    with open(out + ".log", "w", encoding="utf-8", errors="replace") as log:
        rc = subprocess.run([codex, "exec", "--skip-git-repo-check", "-m", a.model, "-s", "workspace-write", "-C", wd,
                             "-i", src, "-"], input=prompt.encode("utf-8"), stdout=log, stderr=subprocess.STDOUT).returncode
    if not os.path.isfile(out) or os.path.getmtime(out) < t0:
        # Codex keeps every generated image in ~/.codex/generated_images/<session>/: take the newest one from this run
        new = [p for p in glob.glob(os.path.expanduser("~/.codex/generated_images/*/*.png")) if os.path.getmtime(p) >= t0]
        if not new:
            sys.exit(f"no image produced (codex rc={rc}), see {out}.log")
        shutil.copy2(max(new, key=os.path.getmtime), out)
    print(f"{out}  ({time.time() - t0:.0f} s, model {a.model}, look {a.look})")


if __name__ == "__main__":
    main()
