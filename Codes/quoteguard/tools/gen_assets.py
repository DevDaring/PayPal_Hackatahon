"""Generate illustration assets with Gemini image models (key read from env GEMINI_KEY; never printed)."""
import base64, json, os, sys, httpx
KEY = os.environ["GEMINI_KEY"]
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
STYLE = ("Premium editorial vector illustration for a fintech procurement product. Palette strictly: warm off-white background (#FBF8F3), "
         "deep navy (#0F2541), teal (#0F766E, #14B8A6) and a small amber accent (#F59E0B). Flat shapes with soft subtle shadows, clean geometry, "
         "generous negative space, calm and trustworthy. Absolutely no text, no letters, no numbers, no logos, no watermarks.")
ASSETS = {
  "login-hero": ("Three supplier quotation documents fanned out; a teal magnifying lens highlights a line on one document with a soft amber highlight; "
                 "thin dotted lines connect the highlighted line to a navy shield with a checkmark, which connects to a teal payment receipt card. Isometric, "
                 "composition centered, portrait 4:5.", "4:5"),
  "empty-requests": ("A single neat clipboard with a blank checklist and a small teal plus symbol bubble beside it, minimal, centered on off-white.", "1:1"),
  "cover": ("Wide hero banner: on the left a stack of supplier PDF quotes with evidence highlight marks, in the middle a navy shield with a checkmark "
            "representing approval bound to exact terms, on the right a completed payment receipt with a teal check; connected by a flowing teal ribbon.", "16:9"),
}
for name, (prompt, ratio) in ASSETS.items():
    for model in ("gemini-3-pro-image", "gemini-2.5-flash-image"):
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": KEY},
                       json={"contents": [{"parts": [{"text": STYLE + " " + prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio}}}, timeout=180)
        if r.status_code != 200:
            print(name, model, "HTTP", r.status_code, r.text[:200]); continue
        parts = r.json()["candidates"][0]["content"]["parts"]
        img = next((p["inlineData"] for p in parts if "inlineData" in p), None)
        if img:
            ext = "png" if "png" in img["mimeType"] else "jpg"
            open(f"{OUT}/{name}.{ext}", "wb").write(base64.b64decode(img["data"])); print(name, "ok via", model, ext); break
