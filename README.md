# Go Certificates

## Files
- `index.html` — public verification page. Anyone can visit and search by reference number or name. Reads records from `certificates.json`.
- `admin.html` — **private** chat tool to generate new certificates with AI and push them to GitHub. Do not link to this publicly.
- `certificates.json` — the database of all certificates (auto-updated by the admin tool).
- `certificates/` — folder of certificate PNGs.
- `api/index.py` — FastAPI backend. Handles the AI generation and GitHub commits so your API keys never touch the browser.

## One-time setup: Vercel Environment Variables

Your API keys go here, NOT in any file you commit.

1. Push this project to `https://github.com/MasabIshaq/Go-Certificates` (already set as the target repo in the backend).
2. In Vercel, open your project → **Settings** → **Environment Variables**.
3. Add these three:

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key (for Nano Banana / gemini-2.5-flash-image) |
| `GITHUB_TOKEN` | A GitHub Personal Access Token with `repo` write access |
| `GITHUB_REPO` | `MasabIshaq/Go-Certificates` (only needed if you rename/fork the repo) |

4. Click **Save**, then redeploy (Vercel → Deployments → ⋯ → Redeploy) so the functions pick up the new variables.

### Creating the GitHub token
GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens →
New token → give it **read/write access to the Contents** permission, scoped to just the `Go-Certificates` repo.

## Using the admin panel
1. Visit `yoursite.vercel.app/admin.html`
2. Type certificate details in chat, e.g.:
   `name: Ali Khan, reference: 0009, course: Web Dev Basics, website: Go Projects`
3. It'll ask for anything missing, then generate a preview.
4. Hit **Save to GitHub** — it commits the image + updates `certificates.json`. Vercel auto-redeploys in ~30-60 seconds.
5. The new certificate is now searchable on the public `index.html` page.

## Security note
`admin.html` has no login. Anyone with the URL who reaches your deployed site can use it to generate and commit certificates. Since it's launched from a private link only you know, that's low-risk — but if you ever share this repo/site publicly, add a password check to `admin.html` and a matching check in the `/api/*` routes before going further.
