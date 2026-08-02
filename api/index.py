import os
import json
import base64
import re
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "MasabIshaq/Go-Certificates")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"  # "Nano Banana" image model
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent"

REQUIRED_FIELDS = ["name", "reference", "course", "website"]


# ---------- Models ----------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    collected: dict = {}


class GenerateRequest(BaseModel):
    name: str
    reference: str
    course: str
    website: str
    date: Optional[str] = None
    length: Optional[str] = None
    instructor: Optional[str] = None


class SaveRequest(BaseModel):
    reference: str
    name: str
    course: str
    image_base64: str  # data:image/png;base64,....


# ---------- Helpers ----------

def missing_fields(collected: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if not collected.get(f)]


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "certificate"


async def github_get_file(path: str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
        if r.status_code == 200:
            return r.json()
        return None


async def github_put_file(path: str, content_bytes: bytes, message: str):
    existing = await github_get_file(path)
    sha = existing["sha"] if existing else None

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    async with httpx.AsyncClient() as client:
        r = await client.put(url, headers=headers, json=payload)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"GitHub write failed: {r.text}")
        return r.json()


# ---------- Routes ----------

@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "gemini_configured": bool(GEMINI_API_KEY),
        "github_configured": bool(GITHUB_TOKEN),
        "repo": GITHUB_REPO,
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Lightweight slot-filling 'chat'. Not a full LLM conversation —
    it inspects the latest user message for field-like info and asks
    for whatever's still missing. Keeps things predictable and cheap.
    """
    collected = dict(req.collected)
    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user":
            last_user_msg = m.content
            break

    # naive field extraction from "key: value" or "key=value" style input
    for line in re.split(r"[,\n]", last_user_msg):
        line = line.strip()
        m = re.match(r"(name|reference|id|course|website|date|length|instructor)\s*[:=]\s*(.+)", line, re.I)
        if m:
            key = m.group(1).lower()
            key = "reference" if key == "id" else key
            collected[key] = m.group(2).strip()

    missing = missing_fields(collected)

    if not missing:
        return {
            "done": True,
            "collected": collected,
            "reply": (
                f"Got everything I need:\n"
                f"- Name: {collected['name']}\n"
                f"- Reference/ID: {collected['reference']}\n"
                f"- Course: {collected['course']}\n"
                f"- Website: {collected['website']}\n\n"
                f"Generating the certificate now..."
            ),
        }

    prompts = {
        "name": "What's the full name to print on the certificate?",
        "reference": "What reference number or ID should this certificate use? (this is what people will search)",
        "course": "What's the course or certificate title?",
        "website": "What website/brand name should appear on the certificate (e.g. Go Projects)?",
    }
    next_field = missing[0]
    return {
        "done": False,
        "collected": collected,
        "reply": prompts[next_field],
        "missing": missing,
    }


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured on server")

    prompt = f"""Design a clean, professional "Certificate of Completion" image, landscape orientation, 1500x1050px.

Branding/website name at top: {req.website}
Heading: CERTIFICATE OF COMPLETION
Course title (large, bold serif): {req.course}
Recipient name (large, bold): {req.name}
{"Instructor: " + req.instructor if req.instructor else ""}
{"Date: " + req.date if req.date else ""}
{"Length: " + req.length if req.length else ""}
Reference number shown small in a corner: {req.reference}

Style: minimal, elegant, off-white background, one accent color, subtle border, modern serif for the title, sans-serif for labels. No photos of people. No watermarks other than the website name.
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
        )

    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Gemini error: {r.text}")

    data = r.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        image_part = next(p for p in parts if "inlineData" in p)
        b64_data = image_part["inlineData"]["data"]
        mime = image_part["inlineData"].get("mimeType", "image/png")
    except (KeyError, IndexError, StopIteration):
        raise HTTPException(status_code=500, detail="Gemini did not return an image")

    return {"image_base64": f"data:{mime};base64,{b64_data}"}


@app.post("/api/save")
async def save(req: SaveRequest):
    if not GITHUB_TOKEN:
        raise HTTPException(status_code=500, detail="GITHUB_TOKEN not configured on server")

    if "," not in req.image_base64:
        raise HTTPException(status_code=400, detail="image_base64 must be a data URL")

    header, b64 = req.image_base64.split(",", 1)
    image_bytes = base64.b64decode(b64)

    slug = slugify(req.name)
    file_path = f"certificates/{slug}.png"

    # 1. upload image
    await github_put_file(
        file_path,
        image_bytes,
        f"Add certificate image for {req.name}",
    )

    # 2. update certificates.json
    existing = await github_get_file("certificates.json")
    if existing:
        current_content = base64.b64decode(existing["content"]).decode("utf-8")
        records = json.loads(current_content)
    else:
        records = {}

    key = req.reference.strip().lower()
    records[key] = {
        "name": req.name,
        "title": req.course,
        "file": file_path,
    }

    new_json = json.dumps(records, indent=2)
    await github_put_file(
        "certificates.json",
        new_json.encode("utf-8"),
        f"Add certificate record for {req.name} ({req.reference})",
    )

    return {
        "ok": True,
        "reference": key,
        "file": file_path,
        "message": "Saved to GitHub. Vercel will redeploy automatically.",
    }
