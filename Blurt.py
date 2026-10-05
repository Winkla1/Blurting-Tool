import json
import re
import time

import streamlit as st
from google import genai
from google.genai import types
from youtube_transcript_api import YouTubeTranscriptApi

# Best model first. If one hits its quota (429) or doesn't exist (404), the app
# moves to the next one and switches back automatically when the better one is
# available again. Edit this list to match the models your key can use
# (see https://ai.dev/rate-limit).
MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]

client = genai.Client()  # reads GEMINI_API_KEY from your environment


# ---------- model fallback ----------

@st.cache_resource
def cooldowns():
    """{model_name: unix time when it's usable again}. Lives as long as the app runs."""
    return {}


def retry_seconds(msg):
    m = re.search(r"retryDelay\W+(\d+(?:\.\d+)?)s", msg)
    if m:
        return float(m.group(1))
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s", msg)
    if m:
        h, mi, s = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s)
    return 3600  # couldn't read it: assume an hour


def fmt(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def ask_json(prompt):
    cd = cooldowns()
    for model in MODELS:
        if cd.get(model, 0) > time.time():
            continue  # this model is cooling down, skip it
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                    ),
                )
                st.session_state.model_used = model
                text = response.text
                return json.loads(text[text.index("{"): text.rindex("}") + 1])
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    cd[model] = time.time() + retry_seconds(msg)
                    break  # try the next model
                if "404" in msg or "NOT_FOUND" in msg:
                    cd[model] = time.time() + 86400  # model doesn't exist for you
                    break
                if "503" in msg:
                    if attempt < 2:
                        time.sleep(4 * (attempt + 1))
                        continue
                    break  # still busy, try the next model
                raise
    soonest = min((cd.get(m, 0) for m in MODELS), default=0) - time.time()
    raise RuntimeError(
        f"Every model is at its limit or unavailable right now. "
        f"The first one is back in about {fmt(max(soonest, 0))}."
    )


# ---------- helpers ----------

def video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def get_transcript(vid):
    try:  # newer versions of youtube-transcript-api
        snippets = YouTubeTranscriptApi().fetch(vid)
        items = [(s.start, s.text) for s in snippets]
    except AttributeError:  # older versions
        raw = YouTubeTranscriptApi.get_transcript(vid)
        items = [(r["start"], r["text"]) for r in raw]
    return "\n".join(f"[{int(t) // 60}:{int(t) % 60:02d}] {x}" for t, x in items)


def extract_points(transcript):
    return ask_json(f"""Below is a timestamped video transcript. Extract the key points a student
should remember: main ideas, facts, definitions, and relationships. Skip filler and
sponsor segments. Aim for 10-30 points depending on length.

Return ONLY JSON: {{"points": [{{"id": 1, "point": "...", "time": "m:ss"}}]}}

Transcript:
{transcript}""")["points"]


def mark(points, blurt):
    return ask_json(f"""You are marking a student's "blurt": everything they could recall from a video,
written from memory. Mark ONLY against the key points below, not your own outside knowledge.
Credit paraphrases and correct meaning, not exact wording. Be fair but not generous.

Key points:
{json.dumps(points)}

Student's blurt:
{blurt}

Return ONLY JSON:
{{
  "covered": [{{"id": 1, "evidence": "short phrase from the blurt"}}],
  "partial": [{{"id": 2, "missing": "what was left out"}}],
  "missed": [3, 4],
  "incorrect": [{{"claim": "what the student said", "correction": "what the video said", "id": 5}}],
  "score": 0-100
}}
Every key point id must appear in exactly one of covered, partial, or missed.""")


# ---------- app ----------

st.title("Blurt")

url = st.text_input("YouTube link")
with st.expander("YouTube blocking the captions? Paste the transcript instead"):
    pasted = st.text_area(
        "On YouTube: click '...more' under the video, then 'Show transcript', "
        "select all the text and paste it here. Leave the link box empty.",
        height=150,
    )

if st.button("Load video") and (url or pasted.strip()):
    try:
        with st.spinner("Getting the transcript and extracting key points..."):
            if pasted.strip():
                transcript = pasted
            else:
                vid = video_id(url)
                if not vid:
                    raise ValueError("Couldn't find a video ID in that link.")
                transcript = get_transcript(vid)
            st.session_state.points = extract_points(transcript)
            st.session_state.result = None
    except Exception as e:
        st.error(f"Failed: {e}")

points = st.session_state.get("points")
if points:
    st.success(f"{len(points)} key points ready. Don't peek. Blurt everything you remember:")
    blurt = st.text_area("Your blurt", height=300, key="blurt")

    if st.button("Mark it") and blurt.strip():
        try:
            with st.spinner("Marking..."):
                st.session_state.result = mark(points, blurt)
        except Exception as e:
            st.error(f"Marking failed: {e}")

    r = st.session_state.get("result")
    if r:
        by_id = {p["id"]: p for p in points}
        st.header(f"Score: {r['score']}/100")

        if r.get("covered"):
            st.subheader("Got it")
            for c in r["covered"]:
                st.markdown(f"- ✅ {by_id[c['id']]['point']}")

        if r.get("partial"):
            st.subheader("Partly")
            for c in r["partial"]:
                p = by_id[c["id"]]
                st.markdown(f"- 🟡 {p['point']}  \n  *Missing: {c['missing']}* (at {p['time']})")

        if r.get("missed"):
            st.subheader("Missed")
            for i in r["missed"]:
                p = by_id[i]
                st.markdown(f"- ❌ {p['point']} (at {p['time']})")

        if r.get("incorrect"):
            st.subheader("Incorrect")
            for c in r["incorrect"]:
                st.markdown(f"- ⚠️ You said: {c['claim']}  \n  *Actually: {c['correction']}*")

        st.caption("Edit your blurt above and hit Mark again to retry.")

# ---------- sidebar: model status (runs last so it's up to date) ----------

with st.sidebar:
    st.subheader("Model status")
    now = time.time()
    for i, m in enumerate(MODELS):
        back = cooldowns().get(m, 0) - now
        if back > 0:
            st.write(f"⏳ {m}: back in {fmt(back)}")
        else:
            st.write(f"✅ {m}" + (" (best)" if i == 0 else ""))
    used = st.session_state.get("model_used")
    if used:
        st.caption(f"Last request used: {used}")
