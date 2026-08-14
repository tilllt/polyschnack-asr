# Using the API

The ASR service exposes an **OpenAI-compatible** transcription endpoint. Any tool
that speaks the OpenAI Audio API works against it by overriding the `base_url` —
no client changes, **no API key required** (pass any non-empty string).

- **Base URL:** `http://localhost:5092/v1`
- **Model id:** `parakeet-tdt-0.6b-v3`
- **Auth:** none (the `api_key` is ignored — pass `"local"` or anything)
- **Languages:** multilingual (Parakeet TDT v3 — English + many European languages incl. Portuguese)

> The web UI (`:8088`) is just a thin client on top of this API. For programmatic
> use, talk to the ASR service directly on `:5092`.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/audio/transcriptions` | OpenAI-compatible transcription (multipart) |
| `POST` | `/v1/audio/transcriptions/stream` | SSE — one event per VAD chunk |
| `POST` | `/v1/audio/transcriptions/async` | Enqueue long audio → `{job_id}` |
| `GET`  | `/v1/audio/jobs/{id}` | Poll async job status + result |
| `POST` | `/v1/audio/transcriptions/batch` | Multi-file, non-OpenAI helper |
| `GET`  | `/health` | `{status, model, device}` |
| `GET`  | `/metrics` | `{queue_depth, total_requests, avg_latency_ms, ...}` |

### `response_format`
`json` (default, `{"text": ...}`), `text`, `verbose_json` (adds `duration` +
`segments[]` with `start`/`end`/`text`), `srt`, `vtt`. Pass
`timestamp_granularities=word` with `verbose_json` to also get word timings.

---

## curl

```bash
curl -s http://localhost:5092/v1/audio/transcriptions \
  -F "file=@audio.ogg" \
  -F "model=parakeet-tdt-0.6b-v3" \
  -F "response_format=json" | jq .text

# timestamped segments
curl -s http://localhost:5092/v1/audio/transcriptions \
  -F "file=@audio.ogg" -F "model=parakeet-tdt-0.6b-v3" \
  -F "response_format=verbose_json" | jq '.segments[] | {start, end, text}'
```

---

## OpenAI Python SDK

Drop-in — only `base_url` changes.

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:5092/v1", api_key="local")

with open("audio.ogg", "rb") as f:
    text = client.audio.transcriptions.create(
        model="parakeet-tdt-0.6b-v3",
        file=f,
        response_format="text",
    )
print(text)
```

Segments (for subtitles / click-to-seek / diarization-style chunking):

```python
with open("audio.ogg", "rb") as f:
    result = client.audio.transcriptions.create(
        model="parakeet-tdt-0.6b-v3",
        file=f,
        response_format="verbose_json",
    )
print(result.duration)
for seg in result.segments:
    print(f"[{seg['start']:.1f}-{seg['end']:.1f}] {seg['text']}")
```

Async client:

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(base_url="http://localhost:5092/v1", api_key="local")

async def main():
    with open("audio.ogg", "rb") as f:
        r = await client.audio.transcriptions.create(
            model="parakeet-tdt-0.6b-v3", file=f, response_format="text"
        )
    print(r)

asyncio.run(main())
```

### OpenAI Node / TypeScript

```ts
import OpenAI from "openai";
import fs from "fs";

const client = new OpenAI({ baseURL: "http://localhost:5092/v1", apiKey: "local" });

const r = await client.audio.transcriptions.create({
  model: "parakeet-tdt-0.6b-v3",
  file: fs.createReadStream("audio.ogg"),
  response_format: "text",
});
console.log(r);
```

---

## Langfuse (observability)

Langfuse ships a **drop-in** wrapper for the OpenAI SDK that auto-traces every
call — including transcriptions against this server.

```python
# pip install langfuse
# env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

from langfuse.openai import openai  # instead of `import openai`

client = openai.OpenAI(base_url="http://localhost:5092/v1", api_key="local")

with open("audio.ogg", "rb") as f:
    text = client.audio.transcriptions.create(
        model="parakeet-tdt-0.6b-v3", file=f, response_format="text"
    )
# → the transcription call now shows up as a generation in Langfuse
```

Wrap a multi-step pipeline (transcribe → summarize) in one trace with `@observe`:

```python
from langfuse import observe
from langfuse.openai import openai

asr = openai.OpenAI(base_url="http://localhost:5092/v1", api_key="local")
llm = openai.OpenAI()  # your real LLM provider

@observe()
def transcribe_and_summarize(path: str) -> str:
    with open(path, "rb") as f:
        text = asr.audio.transcriptions.create(
            model="parakeet-tdt-0.6b-v3", file=f, response_format="text"
        )
    out = llm.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Summarize:\n\n{text}"}],
    )
    return out.choices[0].message.content
```

---

## LangChain

The reliable pattern: transcribe with the OpenAI client (pointed at this server),
then feed the text into any LangChain chain. `ChatOpenAI` can likewise point at a
local OpenAI-compatible **chat** model via its own `base_url`.

```python
# pip install langchain langchain-openai openai
from openai import OpenAI
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

asr = OpenAI(base_url="http://localhost:5092/v1", api_key="local")

def transcribe(path: str) -> Document:
    with open(path, "rb") as f:
        text = asr.audio.transcriptions.create(
            model="parakeet-tdt-0.6b-v3", file=f, response_format="text"
        )
    return Document(page_content=text, metadata={"source": path})

doc = transcribe("meeting.ogg")

chain = (
    ChatPromptTemplate.from_template("Extract action items:\n\n{transcript}")
    | ChatOpenAI(model="gpt-4o-mini")          # or base_url=... for a local LLM
    | StrOutputParser()
)
print(chain.invoke({"transcript": doc.page_content}))
```

To expose transcription as a LangChain **tool** for an agent:

```python
from langchain_core.tools import tool

@tool
def transcribe_audio(path: str) -> str:
    """Transcribe a local audio file (mp3/wav/ogg/m4a/...) to text."""
    with open(path, "rb") as f:
        return asr.audio.transcriptions.create(
            model="parakeet-tdt-0.6b-v3", file=f, response_format="text"
        )
```

---

## Agno

Use `OpenAILike` for any OpenAI-compatible **chat** model, and give the agent a
**tool** that calls this transcription server.

```python
# pip install agno openai
from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from agno.tools import tool
from openai import OpenAI

asr = OpenAI(base_url="http://localhost:5092/v1", api_key="local")

@tool
def transcribe(path: str) -> str:
    """Transcribe a local audio file to text.

    Args:
        path (str): path to an audio file (mp3, wav, ogg/opus, m4a, flac, webm).
    """
    with open(path, "rb") as f:
        return asr.audio.transcriptions.create(
            model="parakeet-tdt-0.6b-v3", file=f, response_format="text"
        )

agent = Agent(
    # the reasoning model can be anything — OpenAI, a local OpenAI-compatible
    # server, etc. Point base_url wherever your chat model lives.
    model=OpenAILike(id="gpt-4o-mini", base_url="https://api.openai.com/v1", api_key="sk-..."),
    tools=[transcribe],
    markdown=True,
)

agent.print_response("Transcribe ./standup.ogg and list the blockers mentioned.")
```

---

## Streaming (SSE)

Incremental results, one event per window — useful for long audio / live UX.
Each line: `data: {"text", "chunk_index", "total_chunks", "start", "end", "final"}`.

```python
import json, httpx

with httpx.stream(
    "POST", "http://localhost:5092/v1/audio/transcriptions/stream",
    files={"file": open("long.ogg", "rb")},
    data={"model": "parakeet-tdt-0.6b-v3"},
    timeout=None,
) as r:
    for line in r.iter_lines():
        if line.startswith("data:"):
            ev = json.loads(line[5:])
            print(ev["chunk_index"], ev["text"])
            if ev.get("final"):
                break
```

---

## Async jobs (large audio)

Submit and poll — avoids HTTP timeouts on long files (e.g. 30+ min).

```python
import time, httpx

base = "http://localhost:5092"
job = httpx.post(
    f"{base}/v1/audio/transcriptions/async",
    files={"file": open("podcast_2h.mp3", "rb")},
    data={"model": "parakeet-tdt-0.6b-v3"},
).json()
jid = job["job_id"]

while True:
    r = httpx.get(f"{base}/v1/audio/jobs/{jid}").json()
    if r["status"] in ("done", "failed"):
        break
    time.sleep(3)

print(r["status"], r.get("text", r.get("error")))
```

---

## Notes

- Audio formats: anything `ffmpeg` decodes (mp3, wav, ogg/opus, m4a, flac, webm, …);
  PCM WAV is decoded natively.
- On CPU the server caps chunk length and serializes inference for low memory —
  see `approach-a/POC_NOTES.md` im Repo. Relax these on a
  bigger host or GPU.
- GPU: run the stack with the GPU overlay
  (`docker compose -f compose.yml -f compose.gpu.yml up -d`, NVIDIA Container
  Toolkit required). The `asr` image (`registry.example.com/public/polyschnack-asr`)
  is **hybrid** — `POLYSCHNACK_USE_GPU=auto` selects CUDA when available and
  falls back to CPU-INT8 otherwise. Verify the model fits your VRAM
  (`grikdotnet/...-fp16` or INT8 for ~4 GB cards).
- The other backends (pk-cpp, qwen3-asr, ark-asr, moonshine-de, canary-asr)
  expose the same OpenAI-compatible API on their own ports (5093–5097) — the
  endpoint contract (`POST /v1/audio/transcriptions`, `verbose_json`,
  `timestamp_granularities=word`) is identical.
