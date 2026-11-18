import test from "node:test";
import assert from "node:assert/strict";
import { Pcm16Encoder } from "../public/pcm16-encoder.js";

test("PCM uses signed Int16 little endian and clips samples", () => {
  const frames = [];
  const encoder = new Pcm16Encoder(16000, (frame) => frames.push(frame), 4);
  encoder.push([new Float32Array([-2, -0.5, 0.5, 2])]);
  assert.equal(frames.length, 1);
  assert.deepEqual(
    [...new Uint8Array(frames[0].buffer)],
    [0, 128, 0, 192, 0, 64, 255, 127],
  );
});

test("48 kHz input becomes ten 100 ms frames per second at 16 kHz", () => {
  const frames = [];
  const encoder = new Pcm16Encoder(48000, (frame) => frames.push(frame));
  for (let offset = 0; offset < 48000; offset += 128) {
    encoder.push([new Float32Array(Math.min(128, 48000 - offset)).fill(0.25)]);
  }
  encoder.flush();
  assert.equal(frames.length, 10);
  assert.ok(frames.every((frame) => frame.buffer.byteLength === 3200));
  assert.ok(frames.every((frame) => Math.abs(frame.rms - 0.25) < 1e-9));
});

test("44.1 kHz fractional resampling retains duration across block boundaries", () => {
  const frames = [];
  const encoder = new Pcm16Encoder(44100, (frame) => frames.push(frame));
  for (let offset = 0; offset < 44100; offset += 128) {
    encoder.push([new Float32Array(Math.min(128, 44100 - offset)).fill(0.5)]);
  }
  encoder.flush();
  assert.equal(
    frames.reduce((sum, frame) => sum + frame.buffer.byteLength / 2, 0),
    16000,
  );
  assert.equal(frames.length, 10);
});

test("stereo input is mixed to mono before encoding", () => {
  const frames = [];
  const encoder = new Pcm16Encoder(16000, (frame) => frames.push(frame), 2);
  encoder.push([new Float32Array([1, -1]), new Float32Array([-1, 1])]);
  assert.deepEqual([...new Int16Array(frames[0].buffer)], [0, 0]);
  assert.equal(frames[0].rms, 0);
});

test("flush emits the remaining short frame once and does not send padding", () => {
  const frames = [];
  const encoder = new Pcm16Encoder(16000, (frame) => frames.push(frame));
  encoder.push([new Float32Array(1733).fill(0.2)]);
  encoder.flush();
  encoder.flush();
  assert.deepEqual(
    frames.map((frame) => frame.buffer.byteLength),
    [3200, 266],
  );
});

test("resampling is independent of how input is chunked", () => {
  const input = Float32Array.from({ length: 11025 }, (_, index) =>
    Math.sin(index / 12),
  );
  const encode = (chunkSize) => {
    const output = [];
    const encoder = new Pcm16Encoder(44100, ({ buffer }) =>
      output.push(Buffer.from(buffer)),
    );
    for (let i = 0; i < input.length; i += chunkSize)
      encoder.push([input.subarray(i, i + chunkSize)]);
    encoder.flush();
    return Buffer.concat(output);
  };
  assert.deepEqual(encode(128), encode(777));
});
