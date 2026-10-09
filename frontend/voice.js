const RECORD_MS = 4000;
const TARGET_SAMPLE_RATE = 16000;

const micButton = document.getElementById("voice-mic");
const statusEl = document.getElementById("voice-status");
const transcriptEl = document.getElementById("voice-transcript");
const spriteEl = document.getElementById("voice-sprite");
const placeholderEl = document.getElementById("voice-placeholder");
const nameEl = document.getElementById("voice-name");
const tonieToggle = document.getElementById("voice-tonie-toggle");

let tonieRunning = false;
let tonieLastShownId = null;
let busy = false;

function setStatus(text) {
  statusEl.textContent = text;
}

function setTranscript(text) {
  transcriptEl.textContent = text ? `„${text}“` : "";
}

function showSprite(id, { shiny = false } = {}) {
  spriteEl.src = `/api/pokemon/${id}/display.png${shiny ? "?shiny=true" : ""}`;
  spriteEl.hidden = false;
  placeholderEl.hidden = true;
}

function clearSprite() {
  spriteEl.hidden = true;
  spriteEl.src = "";
  placeholderEl.hidden = false;
  nameEl.hidden = true;
  nameEl.textContent = "";
}

function setMicState(state) {
  micButton.classList.remove("listening", "processing");
  if (state) micButton.classList.add(state);
}

async function recordWav() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioCtx.createMediaStreamSource(stream);
  const processor = audioCtx.createScriptProcessor(4096, 1, 1);
  const chunks = [];

  source.connect(processor);
  processor.connect(audioCtx.destination);

  processor.onaudioprocess = (event) => {
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };

  await new Promise((resolve) => setTimeout(resolve, RECORD_MS));

  processor.disconnect();
  source.disconnect();
  stream.getTracks().forEach((track) => track.stop());

  const inputRate = audioCtx.sampleRate;
  await audioCtx.close();

  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  const downsampled = downsample(merged, inputRate, TARGET_SAMPLE_RATE);
  return encodeWav(downsampled, TARGET_SAMPLE_RATE);
}

function downsample(samples, inRate, outRate) {
  if (outRate === inRate) return samples;

  const ratio = inRate / outRate;
  const newLength = Math.round(samples.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < newLength) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < samples.length; i++) {
      accum += samples[i];
      count++;
    }
    result[offsetResult] = count ? accum / count : 0;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }

  return result;
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset, str) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }

  return new Blob([view], { type: "audio/wav" });
}

async function recognize(wavBlob) {
  const response = await fetch("/api/voice/recognize", {
    method: "POST",
    headers: { "Content-Type": "audio/wav" },
    body: wavBlob,
  });

  if (!response.ok) {
    throw new Error(`Erkennung fehlgeschlagen (${response.status})`);
  }

  return response.json();
}

function playAudio(url) {
  return new Promise((resolve, reject) => {
    const audio = new Audio(url);
    audio.addEventListener("ended", resolve);
    audio.addEventListener("error", () => reject(new Error(`Audio fehlgeschlagen: ${url}`)));
    audio.play().catch(reject);
  });
}

async function showAndSpeakPokemon(result) {
  showSprite(result.id);
  nameEl.textContent = result.german_name || result.name;
  nameEl.hidden = false;
  setStatus("Gefunden!");

  try {
    await playAudio(`/api/pokemon/${result.id}/cry.wav`);
  } catch (err) {
    // Cry may not exist for every form — continue regardless.
  }

  try {
    await playAudio(`/api/pokemon/${result.id}/tts/name`);
    await playAudio(`/api/pokemon/${result.id}/tts/description`);
  } catch (err) {
    setStatus("Audio nicht verfügbar.");
  }

  setStatus("Normal …");
  await new Promise((resolve) => setTimeout(resolve, 10000));
  showSprite(result.id, { shiny: true });
  setStatus("Schillernd …");
  await new Promise((resolve) => setTimeout(resolve, 10000));
  setStatus("Bereit.");
}

async function runSingleRecognition() {
  if (busy) return;
  busy = true;
  tonieToggle.disabled = true;
  micButton.disabled = true;

  try {
    setMicState("listening");
    setStatus("Ich höre zu …");
    setTranscript("");
    const wav = await recordWav();

    setMicState("processing");
    setStatus("Suche …");
    const result = await recognize(wav);
    setTranscript(result.transcript);

    if (result.matched) {
      await showAndSpeakPokemon(result);
    } else {
      setStatus("Nicht erkannt.");
      await new Promise((resolve) => setTimeout(resolve, 2000));
      setStatus("Bereit.");
    }
  } catch (err) {
    console.error(err);
    setStatus(err.message || "Fehler bei der Aufnahme.");
  } finally {
    setMicState(null);
    busy = false;
    micButton.disabled = tonieRunning;
    tonieToggle.disabled = false;
  }
}

async function tonieListenLoop() {
  while (tonieRunning) {
    try {
      setMicState("listening");
      setStatus("Tonie-Modus: höre zu …");
      const wav = await recordWav();

      if (!tonieRunning) break;

      setMicState("processing");
      setStatus("Tonie-Modus: suche …");
      const result = await recognize(wav);
      setTranscript(result.transcript);

      if (result.matched && result.id !== tonieLastShownId) {
        tonieLastShownId = result.id;
        showSprite(result.id);
        nameEl.textContent = result.german_name || result.name;
        nameEl.hidden = false;
      }
    } catch (err) {
      console.error(err);
      setStatus(err.message || "Fehler bei der Aufnahme.");
    }

    if (!tonieRunning) break;
    setMicState(null);
    setStatus("Tonie-Modus aktiv.");
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  setMicState(null);
  setStatus("Bereit.");
}

micButton.addEventListener("click", () => {
  if (tonieRunning) return;
  runSingleRecognition();
});

tonieToggle.addEventListener("change", () => {
  if (tonieToggle.checked) {
    tonieRunning = true;
    tonieLastShownId = null;
    micButton.disabled = true;
    clearSprite();
    setStatus("Tonie-Modus an");
    tonieListenLoop();
  } else {
    tonieRunning = false;
    micButton.disabled = false;
    setStatus("Tonie-Modus wird beendet …");
  }
});
