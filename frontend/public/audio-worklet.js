import { Pcm16Encoder } from "./pcm16-encoder.js";

class CodeTalkAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.accepting = true;
    this.encoder = new Pcm16Encoder(sampleRate, ({ buffer, rms }) => {
      this.port.postMessage({ type: "audio", buffer, rms }, [buffer]);
    });
    this.port.onmessage = ({ data }) => {
      if (data?.type === "flush") {
        this.accepting = false;
        this.encoder.flush();
        // Port ordering guarantees the last PCM frame arrives before this acknowledgement.
        this.port.postMessage({ type: "flushed" });
      }
    };
  }

  process(inputs) {
    if (!this.accepting) return false;
    this.encoder.push(inputs[0] || []);
    return true;
  }
}

registerProcessor("codetalk-audio", CodeTalkAudioProcessor);
