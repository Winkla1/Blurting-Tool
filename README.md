# Blurt

A small personal study tool built around the **blurting** technique. Paste a YouTube link, write down everything you remember from the video without looking, and get marked by AI against the video’s key points.

It’s a single-file Streamlit app that uses Google’s Gemini API (free tier) and runs locally on your own computer.

## How it works

1. **Load:** paste a YouTube link. The app fetches the video’s captions and has Gemini extract a numbered list of key points. The list stays hidden.
2. **Blurt:** write everything you can remember in a text box.
3. **Mark:** Gemini compares your blurt to the key points and shows:
    - what you got
    - what you partly got (and what was missing)
    - what you missed, with the video timestamp so you can go back and rewatch it
    - anything you got wrong, with a correction
    - an overall score out of 100
4. **Retry:** edit your blurt and mark it again.

## Limitations

- Works only with YouTube videos that have captions (auto-generated captions count). Videos without captions will show an error.
- The whole transcript is sent in one request, so very long videos (multi-hour lectures) may be too long.
- Marking quality depends on the model and can be a little generous or strict at times.
- Runs locally, with no accounts, database, or saved history.

## Setup

You need Python 3.9 or newer and a free Gemini API key.

**1. Get a Gemini API key**

Create one at https://aistudio.google.com/apikey. No credit card is needed for the free tier.

**2. Install the dependencies**

```
pip install streamlit google-genai youtube-transcript-api
```

**3. Set your API key**

macOS / Linux:

```
export GEMINI_API_KEY=your-key-here
```

Windows (Command Prompt):

```
set GEMINI_API_KEY=your-key-here
```

The key only lasts for that terminal window, so set it again whenever you open a new one. Never commit your key to GitHub.

**4. Run the app**

```
streamlit run blurt.py
```

Your browser should open the app at http://localhost:8501.

## Configuration

The model is set by the `MODEL` variable near the top of `blurt.py`. Google retires and adds models fairly often, so if you get a “model not found” error, change it to a current Flash model listed in Google AI Studio.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `API key not valid` | Check the key with `echo $GEMINI_API_KEY`. If you see a message that both `GOOGLE_API_KEY` and `GEMINI_API_KEY` are set, run `unset GOOGLE_API_KEY`, because it takes priority. Restart the app after changing keys. |
| `404 NOT_FOUND` / model no longer available | Update `MODEL` in `blurt.py` to the model name suggested in the error message. |
| `503 UNAVAILABLE` / high demand | Google’s servers are busy. The app retries automatically; if it still fails, wait a few minutes and try again. |
| `429` / quota errors | You’ve hit the free-tier rate limit. Wait a minute and retry. |
| Captions error | The video has no captions, or YouTube is blocking the request (this can happen on VPNs or cloud IPs). Try another video or a home connection. |
| `ModuleNotFoundError` | Run the `pip install` command again, using the same Python you run the app with. |
| `SyntaxError` on startup | Make sure `blurt.py` contains only Python code. Terminal commands belong in the terminal, not in the file. |

## License

MIT, or whatever you prefer. Add a `LICENSE` file to the repo to make it official.
