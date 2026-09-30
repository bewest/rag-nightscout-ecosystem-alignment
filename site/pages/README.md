# site/pages — committed rich pages

*Contributor-facing.*

**Rule: rich pages are committed here; artifacts are only for private drafts.**

An HTML page meant for the site (an interactive explainer, a dashboard, a
figure that needs JavaScript) is committed to this directory. `make site`
copies every git-tracked `.html` file here into the built site at the same
path and lists it in the nav under **Pages**, titled by its `<title>`.
Hosted artifact links are for private drafts only; a page that other people
rely on lives here, under review like any other file.

The build adds `<meta name="robots" content="noindex, nofollow">` to a page
that does not carry one, and `make site-check` fails if any output page lacks
it. Pages here are also subject to `tools/site/exclusions.yaml`.

Keep pages self-contained (inline CSS and JS, or files committed beside them)
and free of personal or health data, like everything else in this public repo.
