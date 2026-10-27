# StratoQ UI v1.0.7 — verifiable visual hotfix

This is a **frontend-only** update, based on the delivered v1.0.6 patch. It keeps
`STUDIO_VERSION = 1.0.5` so backend API 1.0.5 remains compatible.

## Correct installation (Mac)

Stop the running Vite process (Ctrl+C). From your *actual StratoQ project root*:

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v107-verified-ui-patch.zip
```

The archive must place files at these exact paths:

- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- `frontend/index.html`
- `frontend/public/favicon.svg`

**Verify local files are updated:**

```bash
grep -n 'data-ui-build="1.0.7"' frontend/src/App.jsx
grep -n 'v1.0.7 — audit fix' frontend/src/styles.css
grep -n 'favicon.svg?v=107' frontend/index.html
```

Start the frontend **from the same project folder**:

```bash
cd frontend
npm run dev -- --force
```

Open the exact `Local:` URL Vite prints (typically `http://127.0.0.1:5173/`),
not an older browser tab/port, and hard-refresh with Cmd+Shift+R.

**Check what Vite is serving** (replace 5173 with the port printed by Vite):

```bash
curl -fsS http://127.0.0.1:5173/src/App.jsx | grep 'data-ui-build'
curl -fsS http://127.0.0.1:5173/src/styles.css | grep 'v1.0.7'
curl -fsS http://127.0.0.1:5173/favicon.svg | grep 'ellipse'
```

If the first two commands return no matches, the browser's server is reading
**a different frontend folder or old port**. In that case, stop all Vite
instances, restart in the correct `frontend` directory, and use its printed URL.

**Unambiguous visual check:** the top-right version chip now reads
`STRATOQ · 1.0.5 · UI 1.0.7`. That UI suffix is only a *frontend build marker*.
It does not change the API compatibility version.

For a second check, Chrome DevTools > Elements should show `data-ui-build="1.0.7"`
on the `.app-shell` element.

## Corrections

- The original `.physics-last-run` and `.run-hint` declarations are updated
  (these were missed entirely in v1.0.6).
- Gold timeline controls, scrubber, play indicator, active switches, and
  `INTERACTIVE NETWORK ENVIRONMENT` overline.
- Header and browser tab reference exactly the **bundled** three-orbit
  `favicon.svg`, with a cache-busting version query.
- Networks Lab URL is `https://rboutaba-cs.github.io/watqkd/`.
- Waterloo footer retains the existing shield-only crop implementation. Its
  external image availability has **not** been verified, and Waterloo's
  branding guidelines require permission for standalone shield use.

## Testing limitations

The patch contains no simulation or backend changes. CSS source was parsed
with PostCSS and assertions verified the exact JSX/text and bundled SVG.
A complete Vite/browser runtime test could not be run in this environment
without dependencies and a browser, so please use the `curl` checks above
and send their output if anything still appears unchanged.
