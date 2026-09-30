# Static site (MkDocs Material)

*Contributor-facing.* Builds a browsable, local-only copy of this repository's
documentation. Nothing is deployed. Every page carries
`<meta name="robots" content="noindex, nofollow">` and the site root serves a
`robots.txt` with `Disallow: /`.

## Build and serve

The build needs a pseudonym key (see [Participant IDs](#participant-ids)):

```sh
export SITE_PSEUDONYM_KEY="$(cat ~/.config/nightscout-site/pseudonym-key)"  # keep it out of the repo
make site        # creates tools/site/.venv on first run, stages, builds build/site/
make serve       # builds, then serves build/site/ at http://127.0.0.1:8765/
make serve SITE_PORT=8790
make site-check  # builds, then fails unless the content scan passes, noindex is on
                 # 100% of HTML and robots.txt exists
make site-clean  # removes build/site-src, build/site and the report files
```

A full build takes under a minute. `build/site-report.json` records what was
staged, excluded and rewritten; `build/site-mkdocs.log` keeps the MkDocs log.

## How the build works

`tools/site/build.py` reads **only `git ls-files`**; it never walks the working
tree, so untracked material (`externals/`, virtualenvs, vendored build output)
cannot reach the site. Stage a new file with `git add` before building if you
want to see it.

1. Tracked `.md`, `.png`, `.svg`, `.jpg`, `.jpeg` and `.gif` files are copied
   into `build/site-src/` with the repository's path layout, so relative links
   keep working.
2. Links whose target is not staged are rewritten:
   - a tracked file that is not staged (code, JSON, YAML) goes to GitHub at the
     built commit (`blob/<sha>/path`, `tree/<sha>/path` for directories);
   - `externals/<name>/…` goes to the upstream repository at the `ref` pinned
     in `workspace.lock.json`, when `<name>` is a lockfile entry;
   - a link to a directory goes to that directory's index page;
   - anything else is left unchanged and listed under `unresolved` in the report.
   `#anchors`, `#L10` line fragments and `?query` strings are kept.
3. Every directory in the nav gets an index page: its `README.md` or
   `index.md`, or a generated list of its pages and subfolders.
4. Each image folder under `visualizations/` and `docs/visualizations/` gets a
   generated `gallery.md` with lazy-loaded images.
5. The content scan (`tools/site/scan.py`) runs over `build/site-src/`. It fails
   the build, before MkDocs runs, on any hit not on
   `tools/site/scan-allowlist.yaml` (see below).
6. The nav follows the folder tree. The hand-written landing sections in
   `tools/site/landing.yaml` (Overview, Releases, Queue) come first; top-level
   folders with 20 or more staged files get a tab; the rest sit under **More**.
   Large flat folders listed in `tools/site/nav-groups.yaml` (today
   `docs/60-research`) have their pages grouped into collapsed sub-sections by
   file-name rules; the report lists the count per group.
7. MkDocs builds `build/site/` (`mkdocs.yml` at the repo root; the theme
   override in `tools/site/overrides/main.html` adds the noindex meta;
   `tools/site/hooks.py` loads the generated nav).

## Exclusions

`tools/site/exclusions.yaml` lists glob patterns for tracked paths that must not
be published, each with an `axis`, a `reason` and who decided it (the schema is
in the file's header). An excluded file is not staged, and every link to it
becomes the plain text `(not published)`. The report counts matches per entry,
so an entry that matches nothing is visible.

## Content scan (fails closed)

`tools/site/scan.py` looks at every staged text file for four kinds of hit:
`email` (not a role, placeholder or SSH-remote address), `ns-host` (a hosted
Nightscout hostname that is not a placeholder), `token` (credential-shaped
values), and `payload` (request-shaped strings for defect classes still live
on the shipping release). Any hit whose (path, kind) pair is not in
`tools/site/scan-allowlist.yaml` fails `make site` and `make site-check`, and
the stale `build/site/` is removed. Output names the path, kind and count,
never the matched text. To clear a hit, fix the text at its source, or add an
allowlist entry with a reason, and never copy the matched text into it.

## Participant IDs

The repository keeps the data commons' own participant IDs (`odc-` plus eight
digits). The site never shows them. `tools/site/pseudonym.py` rewrites every
one in staged text, link targets, generated pages, nav entries and staged file
names to `odc-p-<first 8 hex of HMAC-SHA256(key, id)>`. A short form (`odc-`
plus 2 to 7 digits) becomes the pseudonym of the one staged full ID it is a
prefix of; a short form that matches none or several fails the build.
13-digit `odc-<timestamp>` record ids are left alone.

- The key comes from `SITE_PSEUDONYM_KEY`. There is no default: with IDs
  present and no key, `make site` fails. `make` exports the variable to the
  build and never echoes it.
- Make a key once, for example `head -c 32 /dev/urandom | base64`, and keep it
  outside the repository. The same key gives byte-identical output; a new key
  gives new pseudonyms, so keep one key for as long as links to pages whose
  names carry a pseudonym should stay stable.
- Neither the key nor any ID-to-pseudonym mapping is written to the repo, the
  build output or `build/site-report.json` (it records counts only).
- **Phase 4 (GitHub Pages) needs the key as an Actions secret**, passed to the
  build step as `SITE_PSEUDONYM_KEY`.
- The `participant-id` scan kind fails the build and `make site-check` on any
  raw `odc-<2 to 12 digits>` left in `build/site-src/` or `build/site/` (HTML,
  search index, sitemap, file names). It cannot be allowlisted.

## site/pages

Committed rich HTML pages go in [`site/pages/`](../../site/pages/README.md).
They are copied into the site unchanged (plus the noindex meta if missing) and
listed in the nav under **Pages**. Rule: rich pages are committed here;
artifacts are only for private drafts.
