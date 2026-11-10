"""Render recipe: catatan cara bikin ulang render final dari raw assets, tanpa ngulang kerjaan (scan, milih momen, review).

Satu recipe per video final, disimpan di  <recipes_dir>/<dd-mm-yyyy>/<nama>/   (recipes_dir dari video-project.json)
  recipe.json    langkah2 (cmd, cwd, env, output), input mentah + fingerprint, output terakhir
  snapshot.zip   semua file kecil (script, json, txt, npy) dari folder kerja + engine (scripts/ dan tools/ skill ini)
  cache/         hasil antara kecil yang lama/acak kalau dibikin ulang (mix lagu, TTS, png), + teks upload pack

Pakai (dari mana aja):
  py -3.14 recipe.py new <nama> --date 25-10-2026 --project "D:/.../Projects/wukong/oct18" [--title "..."]
  py -3.14 recipe.py step <nama> --name "render final" [--cwd DIR] [--out PATH]... [--env K=V]... -- <command...>
        jalanin command + catat (PYTHONPATH yang lagi aktif ikut dicatat). --record-only = catat aja, ga dijalanin.
  py -3.14 recipe.py seal <nama> [--keep PATH]...       snapshot + cari input + fingerprint output (habis final di-approve)
  py -3.14 recipe.py check <nama|all>                   raw assets masih ada & sama?
  py -3.14 recipe.py rerender <nama> [--force-all] [--dry-run] [--only N,M]
        cek input -> balikin script ke versi snapshot (versi sekarang dibalikin lagi setelah selesai)
        -> balikin cache -> jalanin langkah yang outputnya belum ada -> output ke path aslinya
  py -3.14 recipe.py list
"""
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys, time, zipfile

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.realpath(__file__))), "scripts"))
import projcfg

ROOT = os.environ.get("SAS_RECIPE_ROOT") or projcfg.cfg()["recipes_dir"]
ENGINE_ROOTS = [projcfg.SCRIPTS_DIR.replace("\\", "/"), projcfg.TOOLS_DIR.replace("\\", "/")]
EDITING = projcfg.cfg()["editing_dir"].lower().rstrip("/") + "/"
SNAP_EXT = {".py", ".json", ".txt", ".md", ".tsv", ".csv", ".ps1", ".bat", ".srt", ".ass", ".vtt", ".yaml", ".yml",
            ".toml", ".ini", ".cfg"}
DATA_EXT = {".npy", ".npz", ".pkl"}
SNAP_MAX, DATA_MAX = 5 << 20, 20 << 20
VIDEO_EXT = {".mkv", ".mp4", ".mov", ".webm", ".avi", ".ts"}
MEDIA_EXT = VIDEO_EXT | {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".aac", ".opus", ".png", ".jpg", ".jpeg", ".webp",
                         ".ttf", ".otf"}
CACHE_MAX = 30 << 20          # non-video step outputs up to this size are kept in cache/ automatically
SYSTEM = "c:/windows/"                             # system fonts are not raw assets
SKIP_DIRS = {"__pycache__", ".git", "_rerender_backup"}
_ext = "|".join(e[1:] for e in sorted(MEDIA_EXT))
ABS_RE = re.compile(r"[A-Za-z]:[/\\][^\"'\n\r<>|*?]*?\.(?:%s)\b" % _ext, re.I)
REL_RE = re.compile(r"[\"']([^\"'\n\r<>|*?:]+?\.(?:%s))[\"']" % _ext, re.I)


# ------------------------------------------------------------------ helpers ----------
def norm(p):
    return os.path.abspath(p).replace("\\", "/")


def key(p):
    return norm(p).lower()


def inside(p, root):
    p, root = key(p), key(root).rstrip("/") + "/"
    return p.startswith(root)


def fingerprint(path, chunk=1 << 20):
    """size + sha1 of the first, middle and last MB: fast on 100 GB recordings, changes if the file does"""
    size = os.path.getsize(path)
    h = hashlib.sha1(str(size).encode())
    with open(path, "rb") as f:
        for off in sorted({0, max(0, size // 2 - chunk // 2), max(0, size - chunk)}):
            f.seek(off)
            h.update(f.read(chunk))
    return {"size": size, "fp": h.hexdigest()}


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def probe_duration(path):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from probe import duration   # ffprobe stand-in
        return round(duration(path), 3)
    except Exception:
        return None


def gb(n):
    return "%.2f GB" % (n / 1e9) if n > 5e8 else "%.1f MB" % (n / 1e6)


def find_recipe(name):
    if os.path.isfile(os.path.join(name, "recipe.json")):
        return norm(name)
    hits = []
    if os.path.isdir(ROOT):
        for d in os.listdir(ROOT):
            p = os.path.join(ROOT, d, name)
            if os.path.isfile(os.path.join(p, "recipe.json")):
                hits.append(norm(p))
    if not hits:
        sys.exit("recipe '%s' ga ketemu di %s" % (name, ROOT))
    if len(hits) > 1:
        sys.exit("recipe '%s' ada lebih dari satu, kasih path lengkap:\n  %s" % (name, "\n  ".join(hits)))
    return hits[0]


def all_recipes():
    out = []
    if os.path.isdir(ROOT):
        for d in sorted(os.listdir(ROOT)):
            for n in sorted(os.listdir(os.path.join(ROOT, d)) if os.path.isdir(os.path.join(ROOT, d)) else []):
                if os.path.isfile(os.path.join(ROOT, d, n, "recipe.json")):
                    out.append(norm(os.path.join(ROOT, d, n)))
    return out


def load(rdir):
    with open(os.path.join(rdir, "recipe.json"), encoding="utf-8") as f:
        return json.load(f)


def save(rdir, r):
    tmp = os.path.join(rdir, "recipe.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    os.replace(tmp, os.path.join(rdir, "recipe.json"))


def step_outputs(r):
    return {key(o): o for s in r["steps"] for o in s.get("outputs", [])}


# ------------------------------------------------------------------ new / step ----------
def cmd_new(a):
    try:
        datetime.datetime.strptime(a.date, "%d-%m-%Y")
    except ValueError:
        sys.exit("--date harus dd-mm-yyyy (tanggal folder Editing)")
    rdir = norm(os.path.join(ROOT, a.date, a.name))
    if os.path.exists(os.path.join(rdir, "recipe.json")) and not a.overwrite:
        sys.exit("udah ada: %s (pakai --overwrite kalau mau mulai dari nol)" % rdir)
    os.makedirs(rdir, exist_ok=True)
    save(rdir, {"version": 1, "name": a.name, "title": a.title or a.name, "date": a.date,
                "project": norm(a.project), "created": datetime.datetime.now().isoformat(timespec="seconds"),
                "notes": a.notes or "", "steps": [], "inputs": [], "outputs": [], "cache": [], "snapshot": None})
    print("recipe baru:", rdir)


def cmd_step(a):
    rdir = find_recipe(a.recipe)
    r = load(rdir)
    if not a.command:
        sys.exit("command kosong (tulis setelah --)")
    cwd = norm(a.cwd or os.getcwd())
    env = {}
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    for kv in a.env or []:
        k, _, v = kv.partition("=")
        env[k] = v
    outs = [norm(os.path.join(cwd, o)) for o in a.out or []]
    st = {"name": a.name, "cwd": cwd, "cmd": a.command, "env": env, "outputs": outs}
    if not a.record_only:
        for o in outs:
            os.makedirs(os.path.dirname(o), exist_ok=True)
        t0 = time.time()
        rc = subprocess.run(a.command, cwd=cwd, env={**os.environ, **env}).returncode
        st["seconds"] = round(time.time() - t0, 1)
        if rc != 0:
            sys.exit("command gagal (exit %d), langkah ga dicatat" % rc)
        missing = [o for o in outs if not os.path.exists(o)]
        if missing:
            print("PERINGATAN: output yang dibilang --out ga ada:", *missing, sep="\n  ")
    r = load(rdir)                                   # re-read: another step may have been recorded meanwhile
    same = [i for i, s in enumerate(r["steps"]) if s["name"] == a.name]
    if same:
        r["steps"][same[0]] = st                     # re-running a step (after a fix) replaces it
    else:
        r["steps"].append(st)
    save(rdir, r)
    print("dicatat: langkah '%s' (%d langkah)" % (a.name, len(r["steps"])))


# ------------------------------------------------------------------ seal ----------
def snapshot_roots(r):
    roots = [r["project"]] + ENGINE_ROOTS
    for s in r["steps"]:
        roots.append(s["cwd"])
        for tok in s["cmd"]:
            if tok.lower().endswith(".py") and os.path.isfile(tok):
                roots.append(norm(os.path.dirname(tok)))
    out = []
    for p in sorted({key(x): norm(x) for x in roots if os.path.isdir(x)}.values(), key=len):
        if not any(inside(p, q) for q in out):
            out.append(p)
    return out


def walk_small(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith("_rerender")]
        for f in files:
            p = os.path.join(d, f)
            ext = os.path.splitext(f)[1].lower()
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if (ext in SNAP_EXT and sz <= SNAP_MAX) or (ext in DATA_EXT and sz <= DATA_MAX):
                yield norm(p), ext


def cmd_seal(a):
    rdir = find_recipe(a.recipe)
    r = load(rdir)
    if not r["steps"]:
        sys.exit("belum ada langkah yang dicatat")
    produced = step_outputs(r)

    # 1. snapshot every small text/data file of the work folders + engine
    roots = snapshot_roots(r)
    files, refs = [], {}                             # refs: key -> [path, only mentioned by the engine]
    def add_ref(p, eng):
        p = norm(p)
        if key(p).startswith(SYSTEM):
            return
        if key(p) in refs:
            refs[key(p)][1] &= eng
        else:
            refs[key(p)] = [p, eng]
    zpath = os.path.join(rdir, "snapshot.zip")
    with zipfile.ZipFile(zpath + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
        for ri, root in enumerate(roots):
            eng = any(key(root) == key(e) or inside(root, e) for e in ENGINE_ROOTS)
            for p, ext in walk_small(root):
                rel = os.path.relpath(p, root).replace("\\", "/")
                z.write(p, "%d/%s" % (ri, rel))
                files.append({"root": ri, "rel": rel, "sha1": sha1_file(p)})
                if ext in SNAP_EXT:
                    try:
                        txt = open(p, encoding="utf-8", errors="ignore").read()
                    except OSError:
                        continue
                    for m in ABS_RE.findall(txt):
                        add_ref(m, eng)
                    for m in REL_RE.findall(txt):    # relative media paths: resolve against the file's folder
                        q = norm(os.path.join(os.path.dirname(p), m))
                        if os.path.exists(q):
                            add_ref(q, eng)
    os.replace(zpath + ".tmp", zpath)
    r["snapshot"] = {"file": "snapshot.zip", "roots": roots, "files": files}

    # 2. media referenced by commands too
    for s in r["steps"]:
        for tok in s["cmd"]:
            for m in ABS_RE.findall(tok):
                add_ref(m, False)
            if os.path.splitext(tok)[1].lower() in MEDIA_EXT:
                add_ref(os.path.join(s["cwd"], tok), False)

    # 3. classify: produced by a step -> intermediate; exists -> input (fingerprint); missing -> warning
    inputs, missing = [], []
    for k, (p, eng) in sorted(refs.items()):
        if k in produced or any(inside(p, o) for o in produced.values() if os.path.isdir(o)):
            continue
        if os.path.isfile(p):                        # engine-only refs (outro, SFX, fonts) may be unused: soft check
            inputs.append({"path": p, **fingerprint(p), "mtime": int(os.path.getmtime(p)), "soft": eng})
        elif not eng:                                # engine docs/examples name old recordings: not this video's
            missing.append(p)
    r["inputs"] = inputs

    # 4. cache: small non-video step outputs + --keep + upload text next to the finals
    cdir = os.path.join(rdir, "cache")
    cache = []
    def keep(p, why):
        p = norm(p)
        if not os.path.isfile(p) or any(c["path"].lower() == p.lower() for c in cache):
            return
        dst = "%03d_%s" % (len(cache), os.path.basename(p))
        os.makedirs(cdir, exist_ok=True)
        shutil.copy2(p, os.path.join(cdir, dst))
        cache.append({"path": p, "file": dst, "sha1": sha1_file(p), "why": why})
    for o in produced.values():
        ext = os.path.splitext(o)[1].lower()
        if os.path.isfile(o) and ext not in VIDEO_EXT and os.path.getsize(o) <= CACHE_MAX:
            keep(o, "step output")
    for k in a.keep or []:
        keep(k, "--keep")
    finals = [o for o in produced.values() if os.path.splitext(o)[1].lower() in VIDEO_EXT and (o.lower().replace("\\", "/").startswith(EDITING) or "/editing/" in o.lower())]
    for d in {os.path.dirname(f) for f in finals}:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if os.path.splitext(f)[1].lower() in {".txt", ".md"}:
                    keep(os.path.join(d, f), "upload text")
    if os.path.isdir(cdir):                          # drop stale cache files from an earlier seal
        live = {c["file"] for c in cache}
        for f in os.listdir(cdir):
            if f not in live:
                os.remove(os.path.join(cdir, f))
    r["cache"] = cache

    # 5. what the finals looked like (to compare after a re-render)
    r["outputs"] = []
    for o in produced.values():
        if os.path.isfile(o) and os.path.splitext(o)[1].lower() in VIDEO_EXT:
            r["outputs"].append({"path": o, "size": os.path.getsize(o), "duration": probe_duration(o)})
    r["sealed"] = datetime.datetime.now().isoformat(timespec="seconds")
    save(rdir, r)

    print("SEALED:", rdir)
    print("  snapshot: %d file kecil dari %d folder (%s)" % (len(files), len(roots), gb(os.path.getsize(zpath))))
    print("  input mentah (%d):" % len(inputs))
    for i in inputs:
        print("    %s  %s" % (gb(i["size"]).rjust(10), i["path"]))
    print("  cache (%d): %s" % (len(cache), ", ".join(c["file"] for c in cache) or "-"))
    print("  output: %s" % (", ".join("%s (%ss)" % (os.path.basename(o["path"]), o["duration"]) for o in r["outputs"]) or "-"))
    if missing:
        print("  PERINGATAN: path media disebut di script tapi ga ada & ga dibikin langkah manapun"
              " (kalau kepake buat final, tambahin langkahnya / --keep):")
        for m in missing[:40]:
            print("    ", m)


# ------------------------------------------------------------------ check ----------
def check_inputs(r, verbose=True):
    bad, soft = [], []
    for i in r["inputs"]:
        p, why = i["path"], None
        if not os.path.isfile(p):
            why = "HILANG"
        elif os.path.getsize(p) != i["size"]:
            why = "ukuran beda (%s, dulu %s)" % (gb(os.path.getsize(p)), gb(i["size"]))
        elif fingerprint(p)["fp"] != i["fp"]:
            why = "isinya beda (nama sama, file lain)"
        if why:
            (soft if i.get("soft") else bad).append((p, why))
    if verbose:
        for p, why in bad:
            print("  X %s: %s" % (why, p))
        for p, why in soft:
            print("  ? %s (cuma disebut engine, mungkin ga kepake): %s" % (why, p))
    return bad


def cmd_check(a):
    targets = all_recipes() if a.recipe == "all" else [find_recipe(a.recipe)]
    for rdir in targets:
        r = load(rdir)
        if not r.get("sealed"):
            print("[belum di-seal] %s" % rdir)
            continue
        print("%s/%s:" % (r["date"], r["name"]))
        bad = check_inputs(r)
        print("  %s (%d input)" % ("OK, bisa di-render ulang" if not bad else "%d masalah" % len(bad), len(r["inputs"])))


# ------------------------------------------------------------------ rerender ----------
def restore_snapshot(rdir, r, dry):
    """put the snapshot versions of changed/missing files in place; return the list to undo afterwards"""
    snap = r["snapshot"]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(rdir, "_rerender_backup", stamp)
    undo, changed = [], 0
    with zipfile.ZipFile(os.path.join(rdir, snap["file"])) as z:
        for f in snap["files"]:
            dst = os.path.join(snap["roots"][f["root"]], f["rel"])
            if os.path.isfile(dst) and sha1_file(dst) == f["sha1"]:
                continue
            changed += 1
            if dry:
                print("  balikin:", norm(dst))
                continue
            entry = {"path": norm(dst), "backup": None}
            if os.path.isfile(dst):
                b = os.path.join(bdir, str(f["root"]), f["rel"])
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(dst, b)
                entry["backup"] = norm(b)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open("%d/%s" % (f["root"], f["rel"])) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            undo.append(entry)
    if undo:
        with open(os.path.join(rdir, "_restore_pending.json"), "w", encoding="utf-8") as fh:
            json.dump(undo, fh, indent=1)
    print("  script/config: %d file beda dari snapshot%s" % (changed, " (dibalikin sementara)" if changed and not dry else ""))
    return undo


def undo_restore(rdir):
    pend = os.path.join(rdir, "_restore_pending.json")
    if not os.path.isfile(pend):
        return
    with open(pend, encoding="utf-8") as fh:
        undo = json.load(fh)
    for e in undo:
        if e["backup"]:
            shutil.copy2(e["backup"], e["path"])
        elif os.path.isfile(e["path"]):
            os.remove(e["path"])                     # file did not exist before the restore
    os.remove(pend)
    print("  script/config dibalikin ke versi terbaru (%d file)" % len(undo))


def cmd_rerender(a):
    rdir = find_recipe(a.recipe)
    r = load(rdir)
    if not r.get("sealed"):
        sys.exit("recipe belum di-seal")
    undo_restore(rdir)                               # leftover from a crashed run
    print("== %s/%s: %s" % (r["date"], r["name"], r["title"]))
    bad = check_inputs(r)
    if bad and not a.force:
        sys.exit("raw assets ga cocok, berhenti (pakai --force kalau yakin)")
    print("  input mentah %s (%d)" % ("BEDA, dipaksa --force" if bad else "OK", len(r["inputs"])))

    only = {int(x) for x in a.only.split(",")} if a.only else None
    plan, cached = [], {key(c["path"]) for c in r["cache"]}
    for n, s in enumerate(r["steps"], 1):
        outs = s.get("outputs", [])                  # cached outputs count as present (TTS / mixes stay identical)
        have = outs and all(os.path.exists(o) or key(o) in cached for o in outs)
        run = (only is None or n in only) and (a.force_all or only is not None or not have)
        plan.append((n, s, run))
        print("  %s %d. %s%s" % ("->" if run else "  ", n, s["name"],
                                 "" if run else "  (output masih ada, dilewati)"))
    if a.dry_run:
        restore_snapshot(rdir, r, dry=True)
        for c in r["cache"]:
            if not os.path.isfile(c["path"]):
                print("  balikin cache:", c["path"])
        return

    restore_snapshot(rdir, r, dry=False)
    try:
        for c in r["cache"]:
            if not os.path.isfile(c["path"]) or (a.force_all and sha1_file(c["path"]) != c["sha1"]):
                os.makedirs(os.path.dirname(c["path"]), exist_ok=True)
                shutil.copy2(os.path.join(rdir, "cache", c["file"]), c["path"])
                print("  cache dibalikin:", c["path"])
        for n, s, run in plan:
            if not run:
                continue
            for o in s.get("outputs", []):
                os.makedirs(os.path.dirname(o), exist_ok=True)
            print("\n== langkah %d: %s\n   %s" % (n, s["name"], " ".join(s["cmd"])))
            t0 = time.time()
            rc = subprocess.run(s["cmd"], cwd=s["cwd"], env={**os.environ, **s.get("env", {})}).returncode
            if rc != 0:
                sys.exit("langkah %d gagal (exit %d)" % (n, rc))
            print("   selesai %.1f menit" % ((time.time() - t0) / 60))
    finally:
        undo_restore(rdir)

    print("\nHASIL:")
    for o in r["outputs"]:
        p = o["path"]
        if os.path.isfile(p):
            d = probe_duration(p)
            ok = d is not None and o["duration"] is not None and abs(d - o["duration"]) < 0.1
            print("  %s %s  %ss (dulu %ss, %s)" % ("OK" if ok else "CEK", p, d, o["duration"], gb(o["size"])))
        else:
            print("  HILANG", p)


# ------------------------------------------------------------------ list ----------
def cmd_list(a):
    rs = all_recipes()
    if not rs:
        print("belum ada recipe di", ROOT)
    for rdir in rs:
        r = load(rdir)
        state = "belum seal" if not r.get("sealed") else ("raw OK" if not check_inputs(r, False) else "raw HILANG/BEDA")
        outs = ", ".join("%s%s" % (os.path.basename(o["path"]), "" if os.path.isfile(o["path"]) else " (dihapus)")
                         for o in r["outputs"])
        print("%s  %-28s %-16s %s" % (r["date"], r["name"], state, outs))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("name"); p.add_argument("--date", required=True)
    p.add_argument("--project", required=True); p.add_argument("--title"); p.add_argument("--notes")
    p.add_argument("--overwrite", action="store_true"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("step"); p.add_argument("recipe"); p.add_argument("--name", required=True)
    p.add_argument("--cwd"); p.add_argument("--out", action="append"); p.add_argument("--env", action="append")
    p.add_argument("--record-only", action="store_true"); p.set_defaults(fn=cmd_step)
    p = sub.add_parser("seal"); p.add_argument("recipe"); p.add_argument("--keep", action="append")
    p.set_defaults(fn=cmd_seal)
    p = sub.add_parser("check"); p.add_argument("recipe", nargs="?", default="all"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("rerender"); p.add_argument("recipe"); p.add_argument("--force-all", action="store_true")
    p.add_argument("--force", action="store_true"); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only"); p.set_defaults(fn=cmd_rerender)
    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    argv = sys.argv[1:]
    cut = argv.index("--") if "--" in argv else len(argv)   # everything after -- is the recorded command
    a = ap.parse_args(argv[:cut])
    a.command = argv[cut + 1:]
    a.fn(a)


if __name__ == "__main__":
    main()
