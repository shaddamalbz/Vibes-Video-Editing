"""Upload packs for the studio-upload skill: validate what is about to be uploaded, show it as one confirmation table,
and keep a log of what happened to every video. This script never touches a browser and never uploads anything.

    python upload_pack.py new <folder>                 write a starter upload.json listing the videos / images found there
    python upload_pack.py check <folder>...            validate each folder's upload.json (exit 1 on any error)
    python upload_pack.py table <folder>... [--now]    the confirmation table (Markdown) to show the owner before uploading
    python upload_pack.py log set <id> key=value ...   record what happened (status, video_id, url, scheduled, ...)
    python upload_pack.py log show [--pending]         the log; --pending = public videos still missing their follow-up
    python upload_pack.py chrome [--start]             the command that opens the dedicated upload browser (or start it)

upload.json (one per editing folder, next to the files it names):
  {"items": [
    {"id": "2026-11-12-thief-yt",           unique, stable: it is the key in the log
     "platform": "youtube",                 youtube | tiktok
     "kind": "short",                       short | long
     "file": "thief_final.mp4",
     "title": "...", "description": "...",  hashtags go inside the description text
     "tags": ["...", "..."],                YouTube Tags field (not hashtags); ignored on TikTok
     "thumbnail": "thumb.png",              optional (long videos; Shorts and TikTok use it as the cover where the site allows)
     "visibility": "schedule",              schedule | private | unlisted | public
     "schedule": "2026-11-12 18:00",        local time of the account, needed for visibility "schedule"
     "made_for_kids": false,
     "playlist": "",                        optional playlist title
     "type": "funny moment",                optional content-type marker; rules can require it among the tags / hashtags
     "related_video": "",                   optional: log id or video id of the long video a Short should point to
     "pinned_comment": "",                  optional first comment to post and pin once the video is public
     "notes": ""}                           anything the uploader must know ("add the sound in the phone app": then it is manual)
  ]}

Channel rules (optional, private): <profile_dir>/upload_rules.json
  {"max_hashtags": 5, "banned_hashtags": ["#fyp"], "type_markers": ["montage", "lore", "funny moment"],
   "require_type_marker": true, "require_pinned_comment": false}

Project config: video-project.json (found by walking up from the current directory, or VIDEO_PROJECT / ~/.video-project):
  "editing_dir", "profile_dir", and optionally
  "upload": {"chrome": "<chrome executable>", "user_data_dir": "<folder for the upload browser profile>", "port": 9222,
             "log": "<csv file>", "start_url": "https://studio.youtube.com"}
"""
import argparse, csv, datetime, json, os, platform, re, shutil, subprocess, sys

NAME, PACK = "video-project.json", "upload.json"
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
LIMITS = {"youtube": {"title": 100, "description": 5000, "tags_chars": 500},
          "tiktok": {"description": 2200}}                 # TikTok has one caption (title + description together)
LOG_FIELDS = ["id", "platform", "kind", "folder", "file", "title", "type", "status", "video_id", "url", "scheduled",
              "uploaded_at", "public_at", "pinned_comment", "related_video", "notes"]
STATUSES = ["planned", "uploaded", "scheduled", "public", "manual", "skipped", "failed"]
HASHTAG = re.compile(r"(?<![\w&])#[\w]+", re.UNICODE)


def _fwd(p):
    return os.path.abspath(p).replace("\\", "/")


def find_config():
    cands = [os.environ.get("VIDEO_PROJECT")]
    d = os.getcwd()
    while True:
        cands.append(d)
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    ptr = os.path.join(os.path.expanduser("~"), ".video-project")
    if os.path.isfile(ptr):
        cands.append(open(ptr, encoding="utf-8").read().strip())
    for c in cands:
        if not c:
            continue
        f = c if c.lower().endswith(".json") else os.path.join(c, NAME)
        if os.path.isfile(f):
            return _fwd(f)
    return None


def cfg():
    f = find_config()
    c = json.load(open(f, encoding="utf-8")) if f else {}
    root = os.path.dirname(f) if f else os.getcwd()

    def rel(p):
        return _fwd(p if os.path.isabs(p) else os.path.join(root, p))
    up = dict(c.get("upload", {}))
    return {"root": _fwd(root), "file": f,
            "editing_dir": rel(c.get("editing_dir", "Editing")), "profile_dir": rel(c.get("profile_dir", "profile")),
            "chrome": up.get("chrome"), "port": int(up.get("port", 9222)),
            "user_data_dir": rel(up.get("user_data_dir", ".upload-browser")),
            "log": rel(up.get("log", "upload_log.csv")), "start_url": up.get("start_url", "https://studio.youtube.com")}


def rules():
    p = os.path.join(cfg()["profile_dir"], "upload_rules.json")
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}


def load_pack(folder):
    f = os.path.join(folder, PACK)
    if not os.path.isfile(f):
        raise SystemExit(f"upload_pack: no {PACK} in {folder} (make one with: upload_pack.py new \"{folder}\")")
    try:
        pack = json.load(open(f, encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"upload_pack: {f} is not valid JSON: {e}")
    return pack.get("items", [])


def parse_when(s):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            pass
    return None


def check_item(it, folder, now=None, seen=None):
    """-> (errors, warnings) for one item"""
    err, warn = [], []
    R = rules()
    plat, kind = it.get("platform"), it.get("kind")
    if not it.get("id"):
        err.append('missing "id"')
    elif seen is not None:
        if it["id"] in seen:
            err.append(f'duplicate id "{it["id"]}"')
        seen.add(it["id"])
    if plat not in LIMITS:
        err.append(f'platform "{plat}": use youtube or tiktok')
    if kind not in ("short", "long"):
        err.append(f'kind "{kind}": use short or long')
    for key in ("file", "thumbnail"):
        v = it.get(key)
        if key == "file" and not v:
            err.append('missing "file"')
        if v and not os.path.isfile(os.path.join(folder, v)):
            err.append(f'{key} not found: {v}')
    title, desc = (it.get("title") or "").strip(), (it.get("description") or "")
    lim = LIMITS.get(plat, {})
    if plat == "youtube":
        if not title:
            err.append("empty title")
        if len(title) > lim["title"]:
            err.append(f'title is {len(title)} characters, YouTube allows {lim["title"]}')
        if "<" in title or ">" in title:
            err.append("title contains < or >, YouTube rejects those")
        if len(desc) > lim["description"]:
            err.append(f'description is {len(desc)} characters, YouTube allows {lim["description"]}')
        tags = it.get("tags") or []
        n = sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)   # a tag with a space counts its quotes
        if n > lim["tags_chars"]:
            err.append(f'tags add up to about {n} characters, YouTube allows {lim["tags_chars"]}')
        if any("," in t for t in tags):
            err.append("a tag contains a comma: split it into separate tags")
        if kind == "long" and not it.get("thumbnail"):
            warn.append("long video without a thumbnail")
    elif plat == "tiktok":
        cap = (title + "\n\n" + desc).strip()
        if not cap:
            err.append("empty caption (title + description)")
        if len(cap) > lim["description"]:
            err.append(f'caption is {len(cap)} characters, TikTok allows {lim["description"]}')
    tags_h = HASHTAG.findall(title + "\n" + desc)
    if R.get("max_hashtags") is not None and len(tags_h) > R["max_hashtags"]:
        err.append(f'{len(tags_h)} hashtags, the channel rule is at most {R["max_hashtags"]}')
    banned = {b.lower() for b in R.get("banned_hashtags", [])}
    bad = [h for h in tags_h if h.lower() in banned]
    if bad:
        err.append("banned hashtags: " + " ".join(bad))
    markers = [m.lower() for m in R.get("type_markers", [])]
    if markers and kind == "short":
        typ = (it.get("type") or "").lower()
        if R.get("require_type_marker") and typ not in markers:
            err.append(f'"type" must be one of: {", ".join(markers)}')
        elif typ in markers:
            where = [t.lower() for t in it.get("tags") or []] if plat == "youtube" else [h.lower().lstrip("#") for h in tags_h]
            want = typ if plat == "youtube" else typ.replace(" ", "")
            if want not in where:
                warn.append(f'type marker "{typ}" is not among the ' + ("tags" if plat == "youtube" else "hashtags (as #" + want + ")"))
    vis = it.get("visibility", "private")
    if vis not in ("schedule", "private", "unlisted", "public"):
        err.append(f'visibility "{vis}": use schedule, private, unlisted or public')
    if vis == "schedule":
        when = parse_when(it.get("schedule") or "")
        if not when:
            err.append('visibility "schedule" needs "schedule": "YYYY-MM-DD HH:MM"')
        elif when <= (now or datetime.datetime.now()) + datetime.timedelta(minutes=20):
            err.append(f'schedule {it["schedule"]} is in the past or less than 20 minutes away')
    if vis == "public":
        warn.append("goes public immediately on upload")
    if R.get("require_pinned_comment") and kind == "long" and not (it.get("pinned_comment") or "").strip():
        warn.append("no pinned_comment")
    if it.get("notes"):
        warn.append("note: " + it["notes"])
    return err, warn


def cmd_new(a):
    folder = a.folder
    f = os.path.join(folder, PACK)
    if os.path.exists(f):
        raise SystemExit(f"upload_pack: {f} already exists (not overwritten)")
    vids = sorted(x for x in os.listdir(folder) if os.path.splitext(x)[1].lower() in VIDEO_EXT)
    imgs = sorted(x for x in os.listdir(folder) if os.path.splitext(x)[1].lower() in IMAGE_EXT)
    day = os.path.basename(os.path.normpath(folder))
    items = [{"id": f"{day}-{os.path.splitext(v)[0]}-yt", "platform": "youtube", "kind": "short", "file": v, "title": "", "description": "",
              "tags": [], "thumbnail": "", "visibility": "schedule", "schedule": "", "made_for_kids": False, "playlist": "", "type": "",
              "related_video": "", "pinned_comment": "", "notes": ""} for v in vids]
    json.dump({"_images_found": imgs, "items": items}, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {f}: {len(items)} item(s). Fill in the texts from the upload text file, set kind / thumbnail / schedule, "
          f"add a tiktok item per video that also goes there, then run: upload_pack.py check \"{folder}\"")


def cmd_check(a):
    bad, seen = 0, set()
    for folder in a.folders:
        for it in load_pack(folder):
            err, warn = check_item(it, folder, seen=seen)
            mark = "FAIL" if err else "WARN" if warn else "OK  "
            print(f'{mark} {it.get("id", "?")}  [{it.get("platform")}/{it.get("kind")}]  {it.get("file")}')
            for e in err:
                print("       error:", e)
            for w in warn:
                print("       warn :", w)
            bad += bool(err)
    print(f"\n{'FAIL' if bad else 'OK'}: {bad} item(s) with errors")
    sys.exit(1 if bad else 0)


def cmd_table(a):
    log = {r["id"]: r for r in read_log()}
    rows, bad, seen = [], 0, set()
    for folder in a.folders:
        for it in load_pack(folder):
            err, warn = check_item(it, folder, seen=seen)
            bad += bool(err)
            done = log.get(it.get("id"), {}).get("status", "")
            size = os.path.getsize(os.path.join(folder, it["file"])) / 1e6 if it.get("file") and os.path.isfile(os.path.join(folder, it["file"])) else 0
            when = it.get("schedule") if it.get("visibility", "private") == "schedule" else it.get("visibility", "private")
            flag = "ERROR: " + "; ".join(err) if err else ("already " + done if done in ("uploaded", "scheduled", "public") else
                                                          "; ".join(w for w in warn)[:90])
            rows.append((it.get("platform", ""), it.get("kind", ""), (it.get("title") or "").replace("|", "/")[:70], it.get("file", ""),
                         f"{size:.0f} MB", when or "", flag))
    print("| # | Platform | Kind | Title | File | Size | Goes live | Notes |")
    print("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        print(f"| {i} | " + " | ".join(r) + " |")
    print(f"\n{len(rows)} item(s), {bad} with errors." + (" Fix the errors before uploading." if bad else ""))
    sys.exit(1 if bad else 0)


def read_log():
    f = cfg()["log"]
    if not os.path.isfile(f):
        return []
    with open(f, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_log(rows):
    f = cfg()["log"]
    os.makedirs(os.path.dirname(f), exist_ok=True)
    tmp = f + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, f)


def cmd_log(a):
    rows = read_log()
    if a.action == "show":
        if a.pending:
            rows = [r for r in rows if r.get("status") in ("scheduled", "public")
                    and ((r.get("pinned_comment") or "") not in ("done", "none") or (r.get("related_video") or "") not in ("done", "none"))]
        if not rows:
            print("nothing pending" if a.pending else f'the log is empty ({cfg()["log"]})')
            return
        for r in rows:
            print(f'{r["id"]:38} {r.get("platform", ""):8} {r.get("status", ""):10} {r.get("scheduled", "") or r.get("public_at", ""):17} '
                  f'comment:{r.get("pinned_comment") or "-":5} related:{r.get("related_video") or "-":5} {r.get("url", "")}')
        return
    if not a.id:
        raise SystemExit("upload_pack: log set needs an id")
    kv = {}
    for pair in a.pairs:
        if "=" not in pair:
            raise SystemExit(f"upload_pack: expected key=value, got {pair}")
        k, v = pair.split("=", 1)
        if k not in LOG_FIELDS:
            raise SystemExit(f"upload_pack: unknown field {k} (fields: {', '.join(LOG_FIELDS)})")
        if k == "status" and v not in STATUSES:
            raise SystemExit(f"upload_pack: status must be one of {', '.join(STATUSES)}")
        kv[k] = v
    row = next((r for r in rows if r["id"] == a.id), None)
    if row is None:
        row = {k: "" for k in LOG_FIELDS}
        row["id"] = a.id
        rows.append(row)
    if a.folder:                                     # copy the static fields from the pack
        it = next((i for i in load_pack(a.folder) if i.get("id") == a.id), None)
        if it is None:
            raise SystemExit(f"upload_pack: id {a.id} is not in {a.folder}/{PACK}")
        row.update({"platform": it.get("platform", ""), "kind": it.get("kind", ""), "folder": os.path.basename(os.path.normpath(a.folder)),
                    "file": it.get("file", ""), "title": it.get("title", ""), "type": it.get("type", "")})
        row["pinned_comment"] = row["pinned_comment"] or ("pending" if (it.get("pinned_comment") or "").strip() else "none")
        row["related_video"] = row["related_video"] or ("pending" if (it.get("related_video") or "").strip() else "none")
    row.update(kv)
    if kv.get("status") in ("uploaded", "scheduled") and not row.get("uploaded_at"):
        row["uploaded_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    write_log(rows)
    print("logged", a.id, {k: row[k] for k in ("status", "video_id", "scheduled", "pinned_comment", "related_video") if row.get(k)})


def chrome_exe(c):
    if c["chrome"]:
        return c["chrome"]
    s = platform.system()
    cands = {"Windows": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                         os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")],
             "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]}.get(s, [])
    for p in cands:
        if os.path.isfile(p):
            return p
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")


def port_open(port):
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read()
        return True
    except Exception:
        return False


def cmd_chrome(a):
    c = cfg()
    exe = chrome_exe(c)
    if not exe:
        raise SystemExit(f'upload_pack: Chrome not found; set "upload": {{"chrome": "<path>"}} in {NAME}')
    args = [exe, f"--remote-debugging-port={c['port']}", f"--user-data-dir={c['user_data_dir']}", "--no-first-run", c["start_url"]]
    if port_open(c["port"]):
        print(f"upload browser already running on port {c['port']}")
        return
    if not a.start:
        print(" ".join(f'"{x}"' if " " in x else x for x in args))
        print("(a separate browser profile: the owner signs in there once; add --start to launch it)")
        return
    os.makedirs(c["user_data_dir"], exist_ok=True)
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import time
    for _ in range(15):
        if port_open(c["port"]):
            print(f"upload browser started on port {c['port']}, profile {c['user_data_dir']}")
            return
        time.sleep(0.8)
    raise SystemExit("upload_pack: the browser did not open its debugging port (is another Chrome using this profile?)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("folder"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("check"); p.add_argument("folders", nargs="+"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("table"); p.add_argument("folders", nargs="+"); p.set_defaults(fn=cmd_table)
    p = sub.add_parser("log"); p.add_argument("action", choices=["set", "show"]); p.add_argument("id", nargs="?")
    p.add_argument("pairs", nargs="*"); p.add_argument("--folder"); p.add_argument("--pending", action="store_true"); p.set_defaults(fn=cmd_log)
    p = sub.add_parser("chrome"); p.add_argument("--start", action="store_true"); p.set_defaults(fn=cmd_chrome)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
