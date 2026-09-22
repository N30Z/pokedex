// Small helper to prepend a canonical 44-byte WAV header to raw 16kHz
// mono 16-bit PCM before POSTing it to the backend's /api/voice/recognize.
// Kept as a plain header (not an ESPHome component) since it's only ever
// called from a single lambda in pokedex.yaml.
#pragma once

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include "esp_heap_caps.h"

inline std::string build_wav_body(const std::vector<uint8_t> &pcm,
                                   uint32_t sample_rate = 16000,
                                   uint16_t channels = 1,
                                   uint16_t bits_per_sample = 16) {
  const uint32_t byte_rate =
      sample_rate * channels * (bits_per_sample / 8);
  const uint16_t block_align = channels * (bits_per_sample / 8);
  const uint32_t data_size = static_cast<uint32_t>(pcm.size());
  const uint32_t riff_size = 36 + data_size;

  std::string header;
  header.reserve(44 + pcm.size());

  header.append("RIFF", 4);
  header.append(reinterpret_cast<const char *>(&riff_size), 4);
  header.append("WAVE", 4);
  header.append("fmt ", 4);

  const uint32_t fmt_chunk_size = 16;
  const uint16_t audio_format = 1;  // PCM

  header.append(reinterpret_cast<const char *>(&fmt_chunk_size), 4);
  header.append(reinterpret_cast<const char *>(&audio_format), 2);
  header.append(reinterpret_cast<const char *>(&channels), 2);
  header.append(reinterpret_cast<const char *>(&sample_rate), 4);
  header.append(reinterpret_cast<const char *>(&byte_rate), 4);
  header.append(reinterpret_cast<const char *>(&block_align), 2);
  header.append(reinterpret_cast<const char *>(&bits_per_sample), 2);
  header.append("data", 4);
  header.append(reinterpret_cast<const char *>(&data_size), 4);

  header.append(reinterpret_cast<const char *>(pcm.data()), pcm.size());

  return header;
}

// Strips the (assumed 44-byte, canonical PCM) WAV header the backend
// always emits and returns the remaining raw PCM samples ready for
// speaker.play(). Backend contract (backend/app/voice.py), not sniffed.
inline std::vector<uint8_t> strip_wav_header(const std::string &body) {
  if (body.size() <= 44)
    return {};

  return std::vector<uint8_t>(body.begin() + 44, body.end());
}
