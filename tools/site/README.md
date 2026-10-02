# Static site (MkDocs Material)

*Contributor-facing.* Builds a browsable copy of this repository's
documentation. It is deployed only by the maintainer, from a local build, on the
`gh-pages` branch (see [Publishing](#publishing)). Every page carries
`<meta name="robots" content="noindex, nofollow">` and the site root serves a
`robots.txt` with `Disallow: /`.

## Build and serve

The build needs a pseudonym key (see [Participant IDs](#participant-ids)):

```sh
# one-time: the key file, outside the repository (back it up; see Participant IDs)
mkdir -p -m 700 ~/.config/nightscout-alignment
(umask 077; openssl rand -hex 32 > ~/.config/nightscout-alignment/pseudonym.key)
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

- The key comes from `SITE_PSEUDONYM_KEY`, then `NS_PSEUDONYM_KEY`, then the
  file `~/.config/nightscout-alignment/pseudonym.key` (override the path with
  `SITE_PSEUDONYM_KEY_FILE`). There is no default: with IDs present and no
  key, `make site` fails. `make` exports the key to the build and never
  echoes it.
- This is the one key shared with ns2parquet
  (`docs/30-design/ns2parquet-keyed-pseudonyms.md`). Make it once, keep it
  outside the repository, and back it up.
  The same key gives byte-identical output; a new key
  gives new pseudonyms, so keep one key for as long as links to pages whose
  names carry a pseudonym should stay stable.
- Neither the key nor any ID-to-pseudonym mapping is written to the repo, the
  build output or `build/site-report.json` (it records counts only).
- The key stays on the maintainer's machine. The site is built and published
  locally (`make site-publish`); there is no Actions workflow and no Actions
  secret.
- The `participant-id` scan kind fails the build and `make site-check` on any
  raw `odc-<2 to 12 digits>` left in `build/site-src/` or `build/site/` (HTML,
  search index, sitemap, file names). It cannot be allowlisted.

## Search index

Material builds its search index from every page, and the browser's search
worker loads it on every page view. Unfiltered, this site's index was 24 MB and
the worker held about 780 MB under phone emulation (2026-09-30). The staging
step now applies `tools/site/search.yaml` with Material's own mechanisms
(`search: exclude`, `search: boost` front matter and `{ data-search-exclude }`
on headings), without editing any source doc:

- generated folder-index and gallery pages are left out;
- outside the `keep_full` areas (home, overview, releases, queue, design,
  registers, site/pages), a page is indexed by its title and first `##` section
  only, so it stays findable by title;
- the overview pages, releases, the home page and REVIEWER-ONBOARDING are
  boosted.

`SITE_SEARCH_POLICY=off make site` builds without the policy (for comparison).
The report records the index size and what the policy did.

## Page labels: Record or Living

Published pages must be production-ready and accurate, unless they are an
explicit snapshot or point-in-time record (maintainer rule, 2026-09-30). So every
markdown page carries a label under its title:

- **Record**: the file name has a `YYYY-MM-DD` date. Banner: "Record as of
  <date>. A point-in-time document; it is not kept up to date."
- **Living**: every other page. Line: "Living document, last changed <git
  date> at <short sha>." Dates come from one `git log --name-only` pass.
- `tools/site/page-kinds.yaml` sets a path to either kind (a record with an
  undated name needs `as_of`). The build report lists dated pages whose names
  suggest a living document (`record_candidates_for_living`) for review; none
  is overridden automatically.

## site/pages

Committed rich HTML pages go in [`site/pages/`](../../site/pages/README.md).
They are copied into the site (plus the noindex meta if missing) and listed in
the nav under **Pages**. Rule: rich pages are committed here; artifacts are only
for private drafts. Every page needs an entry in `site/pages/pages.yaml`:

- `kind: snapshot` needs `as_of`, and the page must show a banner (an element
  with `data-site-banner="snapshot"` naming that date).
- `kind: living` needs `sources` and `source_commit`. The build fails, naming
  the page and the source, when a source changed after `source_commit`.
  Re-render the page (for the programme page:
  `tools/site/.venv/bin/python tools/site/render_programme.py`), check it, and
  move `source_commit` to the commit that last changed the source.

## Publishing

`make site-publish` refuses unless the working tree is clean, `HEAD` is on a
remote branch (`git branch -r --contains HEAD`), `SITE_PSEUDONYM_KEY` is set
and `make site-check` passes. It then fetches `origin/gh-pages`, copies
`build/site/` plus `.nojekyll` into the worktree `../rag-alignment-gh-pages`
(created on first use), and commits it as one new commit whose parent is
`origin/gh-pages`, with the source sha and build date in its message. It prints
a plain `git push`, which is a fast-forward; if someone published in between,
the push is rejected rather than overwriting their build, and re-running
`make site-publish` builds on theirs. A build identical to `origin/gh-pages`
is not committed. It never pushes.

- `make site-publish DRY_RUN=1` skips the remote check and stages the files in
  the worktree without committing.
- `make site-publish PURGE=1` makes the build the only commit of a fresh orphan
  `gh-pages` instead, so earlier builds leave the branch's history (for removing
  something that should not have been published; copies may already exist
  elsewhere). It prints `git push --force-with-lease` against the `gh-pages` it
  fetched.
- One-time repository setting: **Settings → Pages → Build and deployment →
  Deploy from a branch → `gh-pages` / `(root)`**.
