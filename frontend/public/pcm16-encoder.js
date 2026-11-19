/** Streaming mono resampler. Keeps fractional samples across AudioWorklet blocks. */
export class Pcm16Encoder {
  constructor(inputSampleRate, onFrame, frameSamples = 1600) {
    if (!Number.isFinite(inputSampleRate) || inputSampleRate <= 0) {
      throw new Error("Invalid input sample rate");
    }
    this.ratio = inputSampleRate / 16000;
    this.onFrame = onFrame;
    this.frameSamples = frameSamples;
    this.weight = 0;
    this.sum = 0;
    this.resetFrame();
  }

  resetFrame() {
    this.buffer = new ArrayBuffer(this.frameSamples * 2);
    this.view = new DataView(this.buffer);
    this.cursor = 0;
    this.energy = 0;
  }

  push(channels) {
    if (!channels.length || !channels[0].length) return;
    for (let i = 0; i < channels[0].length; i++) {
      let mono = 0;
      for (const channel of channels) mono += channel[i] / channels.length;
      let remaining = 1;
      // Weighted averaging also supplies a simple low-pass filter when downsampling.
      while (remaining > 1e-9) {
        const take = Math.min(remaining, this.ratio - this.weight);
        this.sum += mono * take;
        this.weight += take;
        remaining -= take;
        if (this.weight >= this.ratio - 1e-9) {
          const sample = Math.max(-1, Math.min(1, this.sum / this.ratio));
          this.view.setInt16(
            this.cursor * 2,
            Math.round(sample * (sample < 0 ? 32768 : 32767)),
            true,
          );
          this.energy += sample * sample;
          this.cursor++;
          this.weight = 0;
          this.sum = 0;
          if (this.cursor === this.frameSamples) this.emit();
        }
      }
    }
  }

  emit() {
    if (!this.cursor) return;
    const buffer =
      this.cursor === this.frameSamples
        ? this.buffer
        : this.buffer.slice(0, this.cursor * 2);
    const rms = Math.sqrt(this.energy / this.cursor);
    this.resetFrame();
    this.onFrame({ buffer, rms });
  }

  flush() {
    this.emit();
    this.weight = 0;
    this.sum = 0;
  }
}
