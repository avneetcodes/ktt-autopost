#!/usr/bin/env python3
"""
keep.the.thoughts autopost: publishes carousels to Instagram with the
Instagram API with Instagram Login (graph.instagram.com).

Commands
  python autopost.py check                 verify the token, account and publishing quota
  python autopost.py prepare               convert posts/*/slide-*.png to Instagram-ready JPEGs
  python autopost.py next [--dry-run]      publish the oldest folder in posts/ not yet posted
  python autopost.py post <folder> [--dry-run]
  python autopost.py refresh-token         print a refreshed long-lived token (60 days)

Each post is a folder in posts/ (published in name order):
  posts/01-the-tip-of-the-iceberg/slide-1.jpg, slide-2.jpg, ... (2 to 10 slides)
  posts/01-the-tip-of-the-iceberg/caption.txt                    (optional)
Published folders are recorded in posted.json.
"""
import json, os, sys, time, glob, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
STATE = ROOT / "posted.json"
API_VERSION = os.environ.get("IG_API_VERSION", "v26.0")


def graph():
    """Instagram-login tokens (IG...) use graph.instagram.com; Meta business / system-user
    tokens (EAA...) use graph.facebook.com. IG_GRAPH_HOST overrides the guess."""
    host = os.environ.get("IG_GRAPH_HOST")
    if not host:
        t = os.environ.get("IG_ACCESS_TOKEN", "")
        host = "graph.facebook.com" if t.startswith("EAA") else "graph.instagram.com"
    return f"https://{host}/{API_VERSION}"


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def token():
    t = os.environ.get("IG_ACCESS_TOKEN")
    if not t:
        sys.exit("IG_ACCESS_TOKEN is not set (see README, step 3).")
    return t


def image_base_url():
    """Public base URL the slides are served from (Meta downloads them from here)."""
    base = os.environ.get("IMAGE_BASE_URL")
    if base:
        return base.rstrip("/")
    repo, ref = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_REF_NAME", "main")
    if repo:
        return f"https://raw.githubusercontent.com/{repo}/{ref}"
    sys.exit("Set IMAGE_BASE_URL, or run inside GitHub Actions (README, step 4).")


def api(method, path, dry=False, **params):
    import requests
    url = path if path.startswith("http") else f"{graph()}/{path}"
    if dry:
        shown = {k: v for k, v in params.items()}
        print(f"  [dry-run] {method} {url} {json.dumps(shown)}")
        return {"id": f"DRY_{abs(hash((path, json.dumps(shown, sort_keys=True)))) % 10**8}", "status_code": "FINISHED"}
    headers = {"Authorization": f"Bearer {token()}"}
    r = requests.request(method, url, headers=headers,
                         params=params if method == "GET" else None,
                         data=params if method != "GET" else None, timeout=60)
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text}
    if r.status_code >= 400 or "error" in body:
        sys.exit(f"Instagram API error on {method} {path}: {json.dumps(body, indent=2)}")
    return body


def account(dry=False):
    """The Instagram account to publish to. IG_USER_ID is required for business tokens (EAA...)."""
    ig_id = os.environ.get("IG_USER_ID")
    if dry:
        return {"user_id": ig_id or "DRY_IG_ID", "username": "keep.the.thoughts"}
    if ig_id:
        info = api("GET", ig_id, fields="username")
        return {"user_id": ig_id, "username": info.get("username")}
    return api("GET", "me", fields="user_id,username")


def wait_ready(container_id, dry=False, tries=30):
    for _ in range(tries):
        status = api("GET", container_id, dry=dry, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            sys.exit(f"Container {container_id} failed with status {status}.")
        time.sleep(5)
    sys.exit(f"Container {container_id} was not ready in time.")


def slides(folder):
    files = sorted(glob.glob(str(folder / "slide-*.jpg")), key=lambda p: int(Path(p).stem.split("-")[1]))
    if not 2 <= len(files) <= 10:
        sys.exit(f"{folder.name}: a carousel needs 2 to 10 JPEG slides (found {len(files)}). Run `prepare` first.")
    for f in files:
        if os.path.getsize(f) > 8 * 1024 * 1024:
            sys.exit(f"{f} is over Instagram's 8 MB limit.")
    return files


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"posted": []}


def publish(folder, dry=False):
    folder = POSTS / folder if not isinstance(folder, Path) else folder
    files = slides(folder)
    caption_file = folder / "caption.txt"
    caption = caption_file.read_text().strip() if caption_file.exists() else ""
    base = image_base_url()
    ig = account(dry)
    ig_id = ig["user_id"]
    print(f"Publishing {folder.name} ({len(files)} slides) to @{ig.get('username')}")

    children = []
    for f in files:
        rel = Path(f).relative_to(ROOT).as_posix()
        item = api("POST", f"{ig_id}/media", dry=dry, image_url=f"{base}/{rel}", is_carousel_item="true")
        children.append(item["id"])
        print(f"  slide container {item['id']} <- {rel}")
    for c in children:
        wait_ready(c, dry)

    carousel = api("POST", f"{ig_id}/media", dry=dry, media_type="CAROUSEL",
                   children=",".join(children), caption=caption)
    wait_ready(carousel["id"], dry)
    media = api("POST", f"{ig_id}/media_publish", dry=dry, creation_id=carousel["id"])
    print(f"Published: media id {media['id']}")

    if not dry:
        state = load_state()
        state["posted"].append({"folder": folder.name, "media_id": media["id"],
                                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        STATE.write_text(json.dumps(state, indent=2) + "\n")
    return media


def cmd_next(dry):
    done = {p["folder"] for p in load_state()["posted"]}
    pending = [p for p in sorted(POSTS.iterdir()) if p.is_dir() and p.name not in done]
    if not pending:
        print("Nothing left to post. Add a new folder to posts/.")
        return
    publish(pending[0], dry)


def cmd_prepare():
    from PIL import Image
    n = 0
    for png in sorted(POSTS.glob("*/slide-*.png")):
        jpg = png.with_suffix(".jpg")
        im = Image.open(png).convert("RGB")
        if im.size != (1080, 1350):
            im = im.resize((1080, 1350), Image.LANCZOS)
        im.save(jpg, "JPEG", quality=95, subsampling=0, optimize=True)
        print(f"  {jpg.relative_to(ROOT)}  {jpg.stat().st_size // 1024} KB")
        n += 1
    print(f"Prepared {n} slides." if n else "No PNG slides found in posts/*/.")


def cmd_check():
    ig = account()
    print(f"Token OK for @{ig['username']} (Instagram user id {ig['user_id']}).")
    quota = api("GET", f"{ig['user_id']}/content_publishing_limit", fields="quota_usage,config")
    print("Publishing limit:", json.dumps(quota.get("data", quota)))


def cmd_refresh():
    if not token().startswith("IG"):
        print("This token type does not expire; nothing to refresh.", file=sys.stderr)
        sys.exit(3)
    body = api("GET", "https://graph.instagram.com/refresh_access_token",
               grant_type="ig_refresh_token", access_token=token())
    print(body["access_token"])
    print(f"(valid for {body.get('expires_in', 0) // 86400} days)", file=sys.stderr)


if __name__ == "__main__":
    load_env()
    p = argparse.ArgumentParser(description="Publish keep.the.thoughts carousels to Instagram.")
    p.add_argument("command", choices=["check", "prepare", "next", "post", "refresh-token"])
    p.add_argument("folder", nargs="?")
    p.add_argument("--dry-run", action="store_true", help="print the API calls without sending them")
    a = p.parse_args()
    if a.command == "check": cmd_check()
    elif a.command == "prepare": cmd_prepare()
    elif a.command == "next": cmd_next(a.dry_run)
    elif a.command == "post":
        if not a.folder: sys.exit("Usage: python autopost.py post <folder>")
        publish(POSTS / a.folder, a.dry_run)
    elif a.command == "refresh-token": cmd_refresh()
