# ESP32 Voice Interface

An ESPHome firmware (`pokedex.yaml`) that turns an ESP32 into a physical,
voice-driven front end for the Pokédex backend: press a button, say a
Pokémon's German name, see its sprite and hear its cry, name, and
description, then the display shows the normal sprite for 10 seconds
followed by the shiny variant for another 10 seconds — then it goes back
to deep sleep.

This is an [ESPHome](https://esphome.io) YAML configuration, not a
standalone PlatformIO/Arduino project — ESPHome owns the build/flash
toolchain.

## Hardware

| Part | Role |
| --- | --- |
| ESP32-S3 N16R8 (16MB flash / 8MB octal PSRAM) | Main board, as configured in `pokedex.yaml` (`variant: esp32s3`, `flash_size: 16MB`, `psram.mode: octal`). PSRAM is required — mic recording, buffered TTS/cry WAV responses, and the decoded sprite image all share that RAM budget. An S3 N8R2 (2MB quad PSRAM) should also work with less headroom — change `flash_size` to `8MB` and `psram.mode` to `quad`. Plain ESP32-C3/C6 don't work: only one I2S peripheral (this design needs separate mic/speaker buses) and no/too little PSRAM. |
| INMP441 | I2S digital microphone |
| MAX98357A | I2S amplifier + speaker |
| GC9A01(A) | 240×240 round SPI TFT display |
| Push button | Wakes the board from deep sleep and starts a recording |

### Wiring

Pins below match `pokedex.yaml` exactly — if you wire differently, update
the YAML to match, don't just rewire to match this table.

Pin choice is constrained on the ESP32-S3 N16R8: GPIO26–32 are wired to the
flash and GPIO33–37 to the octal PSRAM (don't use either), GPIO19/20 are
native USB, GPIO0/3/45/46 are strapping pins, GPIO43/44 are the UART0 log
port, and only GPIO0–21 (RTC GPIOs) can wake from deep sleep — so the wake
button must stay in that range.

| Signal | ESP32 pin | Notes |
| --- | --- | --- |
| **Wake button** | GPIO1 | Other leg to GND; `INPUT_PULLUP`, active-low |
| **INMP441** WS (L/R clock) | GPIO4 | shared mic I2S bus |
| **INMP441** SCK (bit clock) | GPIO5 | shared mic I2S bus |
| **INMP441** SD (data out) | GPIO6 | |
| **INMP441** L/R | GND | selects left channel (matches `channel: left`) |
| **MAX98357A** LRC | GPIO7 | separate speaker I2S bus (mic and speaker need their own I2S peripheral each) |
| **MAX98357A** BCLK | GPIO15 | |
| **MAX98357A** DIN | GPIO16 | |
| **MAX98357A** GAIN / SD | per module default (leave floating for ~9dB gain, or tie per datasheet) |
| **GC9A01** SCK/SCL | GPIO12 | SPI clock (often labeled SCL on these modules, despite being SPI, not I2C) |
| **GC9A01** SDA/MOSI | GPIO11 | SPI data |
| **GC9A01** CS | GPIO10 | |
| **GC9A01** DC | GPIO9 | |
| **GC9A01** RST | GPIO14 | |
| **GC9A01** BLK (backlight) | tie to 3V3, if present | many modules have no BLK pin — backlight is then hardwired on |

## Setup

1. Install ESPHome (`pip install esphome`, or use the ESPHome Docker
   image/Home Assistant add-on).
2. `cp esp32/secrets.yaml.example esp32/secrets.yaml` and fill in your
   WiFi credentials and the backend's LAN address
   (`http://<host>:1510`, no trailing slash) — the same backend started
   via `docker compose up -d pokedex` at the repo root.
3. Make sure the backend's voice models are installed
   (`backend/scripts/download_models.sh`, see the root `CLAUDE.md`) —
   otherwise `/api/voice/recognize` and the TTS endpoints return 503 and
   the flow will always show "Nicht erkannt".
4. First flash over USB:
   ```bash
   esphome run esp32/pokedex.yaml
   ```
5. Subsequent flashes can go over WiFi (OTA):
   ```bash
   esphome run esp32/pokedex.yaml --device pokedex-voice.local
   ```
6. `esphome logs esp32/pokedex.yaml` to watch the flow live (WiFi connect,
   recording, recognize response, playback) — useful for confirming the
   two unverified points below actually work on your hardware.

## Known risks to verify on first hardware bring-up

`pokedex.yaml` has inline comments at these points too:

- **Binary POST body.** The mic recording is POSTed to
  `/api/voice/recognize` as a raw WAV via a `body: !lambda` returning a
  `std::string` built from the PCM buffer. This should be binary-safe
  (`std::string` is length-based, not NUL-terminated) but isn't spelled
  out as supported in ESPHome's `http_request` docs. If the backend logs
  show a truncated/corrupted WAV, the fix is a small custom
  `external_components:` wrapper around `esp_http_client` for just this
  one POST — everything else (mic, speaker, display) stays as-is.
- **Speaker component API.** `id(spk)->play(...)` /
  `id(spk)->is_running()` are called directly from lambdas. Confirm these
  method names against the ESPHome version you're building with before
  relying on them; swap for the current equivalents if the API has moved
  on.

## Backend contract

All three audio endpoints (`/api/pokemon/{id}/cry.wav`,
`.../tts/name`, `.../tts/description`) and the expected mic upload format
are 16kHz mono 16-bit PCM WAV — see `backend/app/voice.py` and the "Voice
interface" section of the root `CLAUDE.md`.
