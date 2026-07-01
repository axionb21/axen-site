# AXEN — CTF Portfolio (Flask + Database)

A real backend site: writeups and certifications are stored in a **database**
(not just a file), so they **persist through restarts and redeploys**. The
admin area lives at a hidden URL — it is never linked from the public pages.

## What's inside
- `app.py` — Flask server: public pages, admin CRUD, hidden admin auth, terminal API
- `templates/` — HTML pages (Jinja2)
- `static/css/style.css` — design (terminal + ink/hanko aesthetic)
- `static/js/terminal.js` — the in-page terminal, calls `/api/terminal`
- `render.yaml` — one-click deploy config for Render (Postgres + persistent disk for cert images)

## Run locally
```bash
pip install -r requirements.txt
export SECRET_KEY="something-random"
export ADMIN_URL_PATH="axen-ctrl-7f3q"      # your secret admin path segment
export ADMIN_USER="axen"
export ADMIN_PASS="a-strong-password"
flask --app app.py init-admin                # creates the DB + your admin account
python app.py
```
Visit `http://localhost:5000` for the public site and
`http://localhost:5000/axen-ctrl-7f3q/login` for admin — **only you know that path.**

## Deploy to Render (free tier works)
1. Push this folder to a GitHub repo (e.g. `axionb21/axen-site`).
2. In Render: **New → Blueprint**, point it at the repo. `render.yaml` sets up
   the web service **and** a managed Postgres database automatically.
3. In the service's **Environment** tab, set `ADMIN_URL_PATH`, `ADMIN_USER`, `ADMIN_PASS`.
4. After first deploy, open Render's **Shell** tab for the service and run:
   ```bash
   flask --app app.py init-admin
   ```
5. Point your domain `b21chat.online` at the Render service (Render → Settings → Custom Domain).

Because data lives in Postgres (not a local file) and certificate images live
on a **persistent disk**, everything survives a restart or redeploy — a plain
SQLite file on Render's free web service would **not**, since its disk resets
on every deploy.

## Using the admin panel
- Go to `/<your-secret-path>/login`, sign in.
- **+ new** under *writeups* → paste your CTF writeup, pick category (pwn/web/crypto…).
- **+ new** under *certifications* → upload the `.png`/`.jpg` of your certificate; it
  renders as an image card on the homepage automatically.
- Add **social links** (label `linkedin`, `github`, etc.) — these power the terminal's
  `open linkedin` command on the public site.

## The terminal (public side)
Visitors can type commands like:
```
help
whoami
list writeups
open linkedin
open certs
```
`open <label>` looks up the URL you saved in the admin panel and opens it for real.

## Security notes
- Passwords are stored as salted hashes (`werkzeug.security`), never plain text.
- The admin path is a secret **you** choose (`ADMIN_URL_PATH`) — treat it like a password;
  don't commit it to a public repo. Change it any time by updating the env var.
- File uploads are restricted by extension and size (5 MB) and renamed on save,
  so a malicious filename can't overwrite server files.
- For extra hardening later: add rate-limiting on `/login` (e.g. `Flask-Limiter`)
  and 2FA if this ever holds anything sensitive.

## Vocabulary
- **persist** — to continue existing / not disappear, even after something restarts.
- **CRUD** — Create, Read, Update, Delete: the four basic operations on stored data.
- **hash** — a one-way scrambled version of a password; it can be checked but not reversed.
- **blueprint** (Render term) — a config file that tells the host what services to spin up.
- **disk** (persistent disk) — storage attached to a server that survives redeploys,
  unlike the server's normal temporary filesystem.
