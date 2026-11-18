# ktt-autopost

Posts the **keep.the.thoughts** carousels to Instagram on a schedule, using Meta's official
Instagram API (Instagram Login, `graph.instagram.com`). Drop a folder of slides into `posts/`,
push, and GitHub Actions publishes the next one every **Mon / Wed / Fri at 7:00 PM IST**.

```
posts/
  01-the-tip-of-the-iceberg/   slide-1.jpg  slide-2.jpg  slide-3.jpg  caption.txt
  02-feelings-are-weather/     ...
  03-when-quiet-feels-loud/    ...
posted.json                    which folders are already live (updated automatically)
```

Folders post in name order, one per run. The three launch carousels are already here as
1080 x 1350 JPEGs (quality 95, full colour detail), with draft captions you can edit.

---

## One-time setup (about 20 minutes)

### 1. Make the account a Creator account
Personal accounts can't publish through the API.
Instagram app → Settings → **Account type and tools** → **Switch to professional account** → **Creator**.
Followers and posts are unaffected.

### 2. Put this folder on GitHub
Create a **public** repo named `ktt-autopost` and push this folder to `main`.
It has to be public: Instagram downloads each slide from its `raw.githubusercontent.com` link.

### 3. Create the Meta app and get a token
1. Go to <https://developers.facebook.com/apps> → **Create app**.
2. Use case: **Manage messaging & content on Instagram**. App type: **Business**.
3. In the app, open **Instagram → API setup with Instagram login**.
4. Under **Generate access tokens**, click **Add account** and log in as `keep.the.thoughts`.
   If Instagram says the account needs a role: App roles → Roles → **Add Instagram Tester**,
   then accept it in Instagram → Settings → Apps and websites → Tester invites.
5. Click **Generate token** and copy it. It's a long-lived token (60 days); step 4 keeps it renewed.

Posting to your own account works in development mode; no App Review is needed.

### 4. Add the secrets
Repo → Settings → Secrets and variables → **Actions** → New repository secret:

| Name | Value |
| --- | --- |
| `IG_ACCESS_TOKEN` | the token from step 3 |
| `GH_PAT` | a fine-grained GitHub token for this repo with **Secrets: Read and write** (lets the weekly job renew the Instagram token) |

### 5. Test, then go live
Repo → **Actions** → **Post next carousel** → **Run workflow**:
1. Tick **Dry run** first: the log shows every API call, nothing is posted.
2. Run it again without dry run to publish the first carousel now.

From then on it posts by itself on the schedule. To change the days or time, edit the `cron`
line in `.github/workflows/autopost.yml` (times are UTC; IST = UTC + 5:30).

---

## Adding new carousels

1. Make a folder: `posts/04-your-topic/` with `slide-1.png`, `slide-2.png`, … (2 to 10 slides) and `caption.txt`.
2. Run `python autopost.py prepare` to make Instagram-ready JPEGs (the PNGs stay local).
3. Commit and push. It goes out on the next scheduled run.

## Running it from your laptop

```bash
pip install -r requirements.txt
cp .env.example .env            # paste your token and IMAGE_BASE_URL
python autopost.py check        # confirms the token and shows your publishing quota
python autopost.py next --dry-run
python autopost.py next         # publishes the next unposted folder
python autopost.py post 02-feelings-are-weather
```

## Limits worth knowing
- Slides: JPEG, max 8 MB each, 2 to 10 per carousel.
- Instagram caps API publishing per account per 24 hours (a carousel counts as one post);
  `python autopost.py check` shows your live usage.
- Never commit `.env` or paste the token into files; it lives only in GitHub secrets.
