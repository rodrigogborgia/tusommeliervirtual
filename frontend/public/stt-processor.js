class PCMProcessorSTT extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];

    // Más permisivo para debugging de STT-only
    this.chunkSeconds = 0.25;
    this.samplesPerChunk = Math.floor(sampleRate * this.chunkSeconds);

    // Umbrales más bajos (arranca fácil)
    this.startThreshold = 0.012;
    this.silenceThreshold = 0.007;

    this.inSpeech = false;
    this.silenceChunks = 0;
    this.maxSilenceChunks = 4; // ~1s
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;

    this.buffer.push(...input);

    while (this.buffer.length >= this.samplesPerChunk) {
      const chunk = this.buffer.slice(0, this.samplesPerChunk);

      let sum = 0;
      for (let i = 0; i < chunk.length; i++) sum += chunk[i] * chunk[i];
      const rms = Math.sqrt(sum / chunk.length);

      // Si detectamos voz, entramos en habla y empezamos a enviar audio.
      if (!this.inSpeech) {
        if (rms >= this.startThreshold) {
          this.inSpeech = true;
          this.silenceChunks = 0;
          this.port.postMessage({ type: "audio", data: new Float32Array(chunk) });
        }
      } else {
        this.port.postMessage({ type: "audio", data: new Float32Array(chunk) });

        if (rms < this.silenceThreshold) {
          this.silenceChunks++;
          if (this.silenceChunks >= this.maxSilenceChunks) {
            this.port.postMessage({ type: "end_of_utterance" });
            this.silenceChunks = 0;
            this.inSpeech = false;
          }
        } else {
          this.silenceChunks = 0;
        }
      }

      this.buffer = this.buffer.slice(this.samplesPerChunk);
    }

    return true;
  }
}

registerProcessor("pcm-processor-stt", PCMProcessorSTT);

