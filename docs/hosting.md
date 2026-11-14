# Hosting

The rules on what may go online are in `CLAUDE.md`.

- [Without a server: the export](#without-a-server-the-export)
- [Your own server](#your-own-server)
- [The Serveur tab](#the-serveur-tab)
- [The server](#the-server)
- [Uploading](#uploading)
- [The video and its password](#the-video-and-its-password)
- [Films and voice](#films-and-voice)
- [Viewers' reports](#viewers-reports)
- [Link previews and crawlers](#link-previews-and-crawlers)
- [Backup](#backup)
- [Two machines](#two-machines)
- [The club](#the-club)

## Without a server: the export

"Exporter le site" (a card of the Serveur tab, an item of the review's menu; `ExportSite.tsx`, `/app/export`) zips the
public pages of the matches picked, with their list (`matches.export`, `outputs/export/site.zip`, downloaded as
`matchs.zip` with a `matchs/` folder): as an upload builds them, without what needs the server (no video behind a password,
no "Signaler", no link previews) nor the gzip copies. Any static host serves it (shared hosting by FTP, GitHub Pages,
Netlify...), and its `index.html` opens from disk. Each export rebuilds the matches: 16 s for two, more the first time a
match's commentary voice is made. The download is offered while the matches ticked are those of the last zip.

## Your own server

Everything the Serveur tab does needs a Linux server reachable by SSH with a key, as root (the backups go to
`/root/backups/volleyball-stats`, `backup.ROOT`; the passwords' list reloads nginx), and rsync on both sides: Windows (WSL2)
and macOS have both. Tested against nginx 1.24 (Ubuntu 24.04's) unprivileged, with [`nginx.conf`](nginx.conf): the video
refused without its key then opened with it (`matches.protected`, `key_command`, `opens`), a report logged, a gzip copy sent.

1. On the server, for a site at `https://stats.example.org/` in `/srv/volleyball/site/`:

   ```bash
   sudo apt install nginx rsync
   sudo mkdir -p /srv/volleyball/site /srv/volleyball/feedback
   sudo touch /srv/volleyball/video_key.conf          # the videos' passwords, written by the app
   sudo chown www-data /srv/volleyball/feedback       # the viewers' reports, written by nginx
   sudo cp nginx.conf /etc/nginx/conf.d/volleyball.conf   # this repository's docs/nginx.conf, its names changed
   sudo nginx -t && sudo systemctl reload nginx
   sudo certbot --nginx -d stats.example.org          # HTTPS
   ```

2. On the machine running the app: `ssh-keygen -t ed25519 -f ~/.ssh/volleyball`, then
   `ssh-copy-id -i ~/.ssh/volleyball root@SERVER`.
3. In the Serveur tab: `root@SERVER`, `/srv/volleyball/site/`, `~/.ssh/volleyball`, `https://stats.example.org/`, then
   "Tester".

The app keeps `video_key.conf` and nginx `feedback/feedback.log` beside the site's folder (`matches.key_command`,
`feedback.fetch`); the pages send the reports to `feedback` under the public address (`matches.feedback_address`). Under a
path (`https://example.org/volleyball/`), name the site's folder after it (`/srv/www/volleyball/`, `root /srv/www;`) and put
the path before the config's locations and patterns, as the owner's server below. After the passwords' list, the app runs
`nginx -t -q && nginx -s reload`, inside a `volleyballstats` docker compose service when the folder above the site's one
composes it (the owner's). Left out of `nginx.conf`: the owner's crawler block (below) and Cloudflare (whose visitor's
address, `$http_cf_connecting_ip`, keys the limits there).

## The Serveur tab

The app's "Serveur" tab (on the list, `#serveur`, `server.py`, `ServerTab.tsx` in `app.js`, never hosted):

- sets the server: address, site folder, ssh key, public address, in `outputs/server.json`, written into every match's
  `publish.json` (a new match takes it from there, `matches.ensure_publish`); "Tester" checks it answers and holds the
  folder;
- lists the matches online, each "À jour" or "En retard" with its link (`server.online`). "En retard" once the page's data
  or the code of the match's page, the list or the 3D view changed since its upload (`review.read_hosted`; the review's
  tip lists each cause on its line);
- runs, as jobs that outlive the server, "Tout mettre à jour" (`matches --all`, recording each upload as the review does),
  "Sauvegarder maintenant" (`sync push --all`: every match changed here, then what sits beside them) and "Vérifier"
  (`sync verify`). Each has a bar, its stage (which match of how many) and the time left (`jobs.Stages`: each stage's last
  duration on this machine, `outputs/hosting_timings.json`, `outputs/backup_timings.json`);
- zips the site to put on any host ("Exporter le site", [above](#without-a-server-the-export));
- shows how the last copy and check went, switches the automatic backup and lists the copies on the server: its used and
  free room, each day's own size (its files no other copy shares, `find -links 1`: what removing it frees), a copy
  restored from or removed from there (never a match's newest, the one a pull brings), and how many copies the server
  keeps besides each match's newest (`settings.json`'s `keep`, 30 by default, the days a new count removes asked first).

## The server

- https://josselinbuils.dev/volleyball/ lists the matches, each at `/volleyball/DATE-TEAM-vs-TEAM/` (the first match at
  `/volleyball/2026-10-29-aspom-1-vs-aspom-2/`).
- The OVH server (`ssh root@<OVH IP> -i ~/.ssh/id_ed25519_ovh`): a `volleyballstats` nginx service in `/home/ubuntu/docker`
  (the owner's `docker` repo), the site in `volleyball-stats/site`, the `/volleyball` route in `reverse-proxy/Caddyfile`
  (rollback `/root/rollback-proxy.sh`). Every service restarts with the server.
- `/usr/local/bin/vbs-monitor.sh` logs the CPU every minute to `/var/log/vbs-monitor/`, with a snapshot when busy.
- SSH is key-only, but for root with a password from the Docker networks: the build manager
  (`josselinbuils/build-manager`, on a push to master of blog or portfolio) logs in so and rebuilds that service with
  `docker compose`.
- The docker repo takes commits on master directly, the owner's choice: GitHub reports the push as bypassing its PR rule.
  A change of a mounted config from `git pull` needs `docker compose up -d --force-recreate --no-deps volleyballstats`:
  the running container keeps the old file.
- Caching: `matches.build` writes `.gz` copies nginx sends as they are (`gzip_static`). Cloudflare and browsers keep the
  hashed and `?v=` files for good (the unhashed ones load with the build's hash, card pictures with their own), images a
  day; pages are checked each time; the video copy's files only in the viewer's browser (`private`).

## Uploading

- `outputs/hosted/` holds the hosted site: build each match into it without footage or pictures, list them (which names
  their folders), copy it over; nothing restarts.
- With `outputs/matches/MATCH/publish.json` (`site`, `url`, `light`, `av1`, `small`, `club`, `upload` as
  `root@<OVH IP>:…/site/`, `key`, `video`, `videoKey`; a match's video copies, once made, in its
  `data/matches/MATCH/reencoded/`), the review's "Mettre en ligne" does all of it (`matches.host`, refusing to upload a
  video copy that opens without the password) and says when.
- The review writes an imported match's `publish.json` on opening (`matches.ensure_publish`: the hosting from another
  match's, its club team from the club's teams, else the theme's name).
- The first "Mettre en ligne" asks: with the video and a password, or without it (`matches.choose`; to choose again, remove
  `video` from `publish.json`). Only the password's fingerprint is kept. Nothing is encoded before that choice: with the
  video, its copies are made then (`video_copies.py`).
- Each match page carries the code it was built with, so a change of the page or of the data it is built from reaches the
  matches online only once rebuilt: the review's "Mettre à jour tous les matchs en ligne" (`matches --all outputs/matches`)
  rebuilds every match online and uploads them at once (`rsync --delay-updates`: the new files replace the old together),
  nothing if one cannot be rebuilt (on the two matches: 26 s).

By hand:

```bash
uv run python -m volleyball_stats.web outputs/matches/2026-10-29-aspom-1-vs-aspom-2 --video data/matches/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4 --court outputs/courts/aspom_begles.json --footage none --club 1 --no-pictures --video-page video/ --feedback /volleyball/feedback --out outputs/hosted/MATCH
uv run python -m volleyball_stats.matches outputs/hosted --url https://josselinbuils.dev/volleyball/
rsync -rt --delete -e "ssh -i ~/.ssh/id_ed25519_ovh" outputs/hosted/ root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/site/
```

## The video and its password

- A match's video goes in its `video/` folder (`--out outputs/hosted/MATCH/video --footage full --copy-video --club both
  --pictures`); the public build links to it with `--video-page video/`, whose dialog asks the password.
- `--light-video`: a lighter H.264 copy on the same timeline (`ffmpeg -i VIDEO -vf scale=1920:1080:flags=lanczos,fps=25
  -c:v libx264 -preset slow -crf 28 -maxrate 5M -bufsize 10M -g 50 -c:a aac -b:a 96k -movflags +faststart`).
- `--av1-video`: an AV1 one the browsers that can play first (same with `-c:v libsvtav1 -preset 6 -crf 40 -g 50`; VMAF
  90.7 at 541 kb/s against the H.264 copy's 89.0 at 1254 kb/s with `-g 250`).
- `--small-video`: a 720p H.264 one (same with `scale=1280:720`, -56% against 1080p) the page plays while its player is
  small; the 1080p copy in full screen, zoomed or over 1600 screen pixels wide, the video carrying on where it stood.
- A keyframe every 2 s (`-g 50`) keeps the jumps between clips from freezing: 21 frames to decode a jump instead of 131
  with `-g 250`, for +30% size in H.264, +60% in AV1.
- The copies keep their source's date, so an upload skips an unchanged video.
- The service's nginx serves a `/volleyball/FOLDER/video/` file only with the cookie `video_key`, the SHA-256 of
  `volleyball:` and that match's password, listed in `volleyball-stats/video_key.conf` as `"FOLDER:<sha256>" 1;` (mounted
  in the container: written in place, then `nginx -s reload`, as `matches.host` does). Otherwise it redirects to the page
  with `?video=denied`, wrong keys limited to 10 a minute, `Cache-Control: private, no-store` so Cloudflare keeps nothing.
  Check that a `curl` without it gets 302 before uploading a video.

## Films and voice

- The players' films and the match's summary (`film.py`, real footage): the review's "Créer N films de joueurs" and "Créer
  les highlights" each make those of their kind whose `plan` changed, never an apply; a player's card in "Noms" makes
  their film alone when it is out of date (a rename, `/film`).
  `uv run python -m volleyball_stats.film outputs/matches/MATCH --video VIDEO --court COURT [--names A,B]` does the same.
- Only behind the page's password (the owner's rule): `web.copy_films` puts them only beside a page with the video, and
  `matches.host` refuses to upload a video outside a `video/` folder or a film that opens without the password.
- Files in `outputs/matches/MATCH/films/`, in the backup (a pull brings them); a film of a name no longer on the page (a
  renamed player's) is deleted at the next page build (`web.copy_films`).
- The commentary's voice: each upload first makes the missing audio in `outputs/matches/MATCH/voice/`
  (`matches.make_voice`), the build takes it (a line no longer true of the match is left out).

## Viewers' reports

- Hosted pages are built with `--feedback` at `feedback` under the public address (`matches.feedback_address`:
  `/volleyball/feedback` here): one tap on "Signaler" reports the moment, "Préciser" then
  adds what is wrong and a comment to the same report (its `id`).
- The service's nginx logs each POST (2 KB, 5 a minute per visitor) to `volleyball-stats/feedback/feedback.log`.
- The review's "Charger les signalements" (`feedback.fetch`) copies it to `outputs/feedback/feedback-DATE.log` (the review
  reads every `outputs/feedback/*.log`), then empties it online; `uv run python -m volleyball_stats.feedback LOG` lists a
  log's reports.
- Test the report endpoint without writing to that log (it holds viewers' reports): a GET writes an empty line too, which
  `feedback.read` skips.

## Link previews and crawlers

- `matches.build` with a `url` tags the list and each match page (`og:*`) with a `preview.png` drawn there from teams,
  colours, score and date: never footage or a player.
- The service's nginx answers 403 to the user agents of its `$blocked_bot` list (search engines, AI scrapers, SEO tools;
  link previews stay) and sends `X-Robots-Tag: noindex` on all; the pages carry the same meta tag. A bot lying about its
  name gets through; the domain's `robots.txt` has no rule, Cloudflare's bot settings are the owner's.

## Backup

`backup.py`, `sync.py`. Tested end to end against local folders (`tests/test_backup_flow.py`).

- With "Sauvegarde automatique" on, every 10 minutes a match changed here since it was last sent or brought
  (`sync.changed`) is sent, and what sits beside the matches (courts and their clicks, roster, lens, the club, the viewers'
  reports, the models trained on the reviewed matches: `learned/`, 345 MB) is kept in step with the server
  (`sync.keep_shared`). The review's "Sauvegarder sur le serveur" and the Serveur tab's "Sauvegarder maintenant"
  (`sync push --all`) do it at once; `uv run python -m volleyball_stats.backup outputs/matches/MATCH` goes through
  `sync.push` too.
- The choice is each machine's own (`outputs/backup.json`), on by default once a server is set.
- Copies go to `/root/backups/volleyball-stats/COPY/` on the OVH server (outside the website, root only), one per hour
  something changed (`2026-11-10T15`; the daily ones before have no hour). Each starts as the one before, hard-linked
  (`backup_remote.py`), so it holds every match while only what changed goes up; files go in place together at the end
  (`--delay-updates`).
- A match's files replace the copy's; what sits beside the matches is merged, each file the newest of both machines and
  none removed (`--update`), the reports line by line, the roster match by match. A change there alone moves no match's
  version.
- Kept: the last 30 copies (the tab's count) and each match's newest. None under 5 GB free.
- Each machine notes how its last copy and check went in `outputs/backup_state.json`; the list warns when copies are off,
  failing, a day behind a change, or differ. Weekly (and the tab's "Vérifier"), `sync verify` compares every match
  unchanged here with its copy byte by byte.
- The tab restores a match or what sits beside the matches from any copy (`server.restore`, this machine's set aside
  first, the restored one then sent as the newest).
- The source video is not in it (42 GB, 18 GB free there): the owner keeps a copy elsewhere.

## Two machines

The Mac and the PC (`sync.py`): the backup is also how a match goes from one to the other, and any machine works on any
match (the owner's rule, 8 Nov: no machine holds one).

- The server keeps each match's version (`claims/MATCH.json` beside the copies, under `flock`: the version, which machine
  sent the last copy and when, and the one sending a copy now); a copy goes only from the server's version (`.sync.json` in
  the match's folder, never copied, says which this machine started from).
- Opening a match, once the machine keeps its matches there (`sync.active`: automatic copies on, a server set in the
  Serveur tab, or a match pushed or pulled; otherwise the review reaches the server only when asked), the review first
  brings the server's newer copy when nothing changed here (`sync.check`, 15 s at most).
- Changed on both sides (at opening, or a copy refused later), it asks which to keep, "Modifié ici et sur MACHINE": "Celle
  de MACHINE" pulls it (this machine's changes kept in `backup-sync-<time>/`), "Celle d'ici" sends this one, the server's
  set aside first in `aside/<time>-v<version>/` beside the dated copies (hard links).
- The list of matches offers those only on the server ("À télécharger"), asked once the page shows
  (`/matches/remote.json`: the ssh round trip takes a second).
- A pull also brings the courts, lens, club and sponsors this machine lacks, and the roster is joined, each match's names
  from this machine where its copy is not behind the server's.
- By hand: `uv run python -m volleyball_stats.sync list | pull NAME... | pull --all | push outputs/matches/MATCH`; a machine
  with no match yet first sets the server in the Serveur tab (the key copied there).
- The videos go straight between the machines on the same network (`data_sync.py`, a code shown by the one waiting: the
  Mac, WSL2 being unreachable from outside: two Windows PCs cannot sync, the dialog says so on Windows), never through
  the server.

Uploads with two machines: never an older version online.

- A match whose server copy is newer than this machine's is left as it is online (`sync.behind`: "Mettre à jour" refuses
  it, the update of every match skips it; on 8 Nov the PC's put the first match's older copy online).
- The site folder is first made what the server holds (`matches.mirror`, the video copies aside), so the pages the other
  machine put online stay; the upload sends only the rebuilt matches' video copies, and refuses if its dry run would
  delete another match's page.
- The mirror brings the films too: a match with no `films/` folder here (made on the other machine, not pulled since)
  takes those online, names from the page (`matches.adopt_films`), so its rebuild keeps them; an upload that would still
  delete them refuses (the upload of 8 Nov from the PC took them offline).

## The club

The club, sponsors and teams included, is the app's "Club" dialog (`club_settings.py`), in `outputs/club/`: off GitHub,
each machine its own, a pull bringing it to a machine that has none. The hosted pages' build reads it from this machine.
