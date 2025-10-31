# Íbúðaverð á Íslandi vs Bitcoin (ISK) — Hosting v3

Þessi útgáfa er tilbúin fyrir eftirfarandi hýsingar:
- **Hugging Face Spaces (Streamlit)** – *auðveldast*
- **Render.com** (með Dockerfile, styður $PORT)
- **Fly.io / Railway / Cloud Run** (Dockerfile notar `$PORT`)

## Hugging Face Spaces (án Git, drag‑and‑drop)
1. Fara á https://huggingface.co → stofna aðgang → **New Space**.
2. Space nafn: t.d. `iceland-housing-vs-btc`. **SDK**: *Streamlit*. **Visibility**: Public.
3. Smelltu **Create Space**.
4. Á Space-síðunni: dragðu **app.py**, **requirements.txt** og **(val) Dockerfile** inn í Files.
5. Bíddu þar til “Build” klárast → appið birtist með slóð `https://huggingface.co/spaces/<user>/<space>`.

> Ef þú vilt bara Streamlit, dugar `app.py` + `requirements.txt`. Dockerfile þarf ekki í Spaces.

## Render.com (Docker Web Service)
1. Stofna aðgang á https://render.com og tengja GitHub repo (með þessum skrám).
2. Render → **New +** → **Web Service** → Veldu repo‑ið.
3. Render þekkir Dockerfile sjálfkrafa. Engin “Start Command” þarf.
4. Veldu Free plan → Deploy.
5. Render setur `$PORT` sjálfkrafa. Dockerfile í þessari útgáfu notar það.

## Fly.io (Docker)
1. Setja upp flyctl (sjá leiðbeiningar á fly.io).
2. Í möppunni með skrám: `fly launch` → svara spurningum → samþykkja Docker deploy.
3. `fly deploy` → bíða → fá app slóð.

## Railway (Docker)
1. railway.app → New Project → Deploy from Repo (með Dockerfile).
2. Deploy → Railway skilgreinir `$PORT`; Dockerfile sér um rest.

## Keyra heima (local)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
Vafrinn: http://localhost:8501
