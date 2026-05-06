# Tatyana's Content Agent

Personal LinkedIn content agent. Mobile-first. Three features:
- **Link → Post**: Paste any URL, get 3 LinkedIn posts in your voice
- **Event Machine**: Full pre/during/post content sequence for any conference
- **Podcast Repurposer**: One episode → 5 LinkedIn posts

---

## Deploy to Railway (5 minutes)

1. Create a free account at railway.app
2. Click "New Project" → "Deploy from GitHub repo"
3. Push this folder to a GitHub repo first:
   ```
   git init
   git add .
   git commit -m "Initial deploy"
   git remote add origin YOUR_GITHUB_REPO_URL
   git push -u origin main
   ```
4. Railway auto-detects Python and deploys
5. Your app is live at: `yourapp.up.railway.app`

---

## Run locally (for testing)

```bash
pip install flask gunicorn
python app.py
```

Open: http://localhost:5500

---

## First use

1. Open the app on your phone or laptop
2. Tap the ⚙️ settings icon
3. Select your LLM provider (OpenAI or Anthropic)
4. Paste your API key
5. Tap Save

Your settings are stored securely in the `data/` folder.

---

## Files

```
app.py              ← Flask server (all 3 API endpoints)
index.html          ← Mobile-first UI
tatyana_kb.json     ← Your voice, style, and KB
requirements.txt    ← Python dependencies
Procfile            ← Railway process config
railway.json        ← Railway deployment config
data/               ← Your settings and memory (auto-created)
```
