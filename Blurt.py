import json
import re
import time

import streamlit as st
from google import genai
from google.genai import types
from youtube_transcript_api import YouTubeTranscriptApi

MODEL = "gemini-3.8-flash"
client = genai.Client()  # reads GEMINI_API_KEY from your environment


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


def ask_json(prompt):
       for attempt in range(5):  # retry if Google is busy (503)
           try:
               response = client.models.generate_content(
                   model=MODEL,
                   contents=prompt,
                   config=types.GenerateContentConfig(
                       temperature=0,
                       response_mime_type="application/json",
                   ),
               )
               break
           except Exception as e:
               if "503" in str(e) and attempt < 4:
                   time.sleep(4 * (attempt + 1))
                   continue
               raise
       text = response.text
       return json.loads(text[text.index("{"): text.rindex("}") + 1])


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
if st.button("Load video") and url:
    vid = video_id(url)
    if not vid:
        st.error("Couldn't find a video ID in that link.")
    else:
        try:
            with st.spinner("Fetching captions and extracting key points..."):
                st.session_state.points = extract_points(get_transcript(vid))
                st.session_state.result = None
        except Exception as e:
            st.error(f"Failed (does the video have captions?): {e}")

points = st.session_state.get("points")
if points:
    st.success(f"{len(points)} key points ready. Don't peek. Blurt everything you remember:")
    blurt = st.text_area("Your blurt", height=300, key="blurt")

    if st.button("Mark it") and blurt.strip():
        with st.spinner("Marking..."):
            st.session_state.result = mark(points, blurt)

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
