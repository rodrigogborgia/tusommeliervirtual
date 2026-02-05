class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    // Chunks más cortos => menor latencia y mejor VAD.
    this.chunkSeconds = 0.25;
    this.samplesPerChunk = Math.floor(sampleRate * this.chunkSeconds);

    // VAD simple por RMS (float32 [-1..1]).
    // Ajustes típicos:
    // - startThreshold: cuánto RMS hace falta para considerar "habla" (evita hiss/ruido leve)
    // - silenceThreshold: por debajo de esto, contamos "silencio" para cerrar la frase
    // Modo "estricto" (minimiza falsos positivos): requiere voz más clara
    // Nota: si hablás muy bajo, puede no activar.
    this.startThreshold = 0.03;
    this.silenceThreshold = 0.018;

    // Requiere N chunks consecutivos por encima del umbral para entrar en "habla"
    // (evita disparos por clicks/ruido corto).
    this.startChunks = 0;
    this.minStartChunks = 3; // 3 * 0.25s = 0.75s sostenidos (más estricto)

    // Pre-roll para no comerse el inicio de palabras cortas (p.ej. "hola").
    // Guardamos los últimos ~0.5s y los enviamos cuando empieza el habla.
    this.preRoll = [];
    this.preRollMaxSamples = Math.floor(sampleRate * 0.5);

    // Chunks candidatos mientras validamos el arranque (cuando rms >= startThreshold).
    this.startCandidate = [];

    // Cantidad de chunks "silenciosos" seguidos para terminar la frase.
    // Con chunkSeconds=0.25, 4 => ~1s de silencio.
    this.silenceChunks = 0;
    this.maxSilenceChunks = 5; // ~1.25s (reduce cortes por micro-pausas)

    this.inSpeech = false;
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;

    this.buffer.push(...input);

    while (this.buffer.length >= this.samplesPerChunk) {
      const chunk = this.buffer.slice(0, this.samplesPerChunk);

      // calcular RMS
      let sum = 0;
      for (let i = 0; i < chunk.length; i++) sum += chunk[i] * chunk[i];
      const rms = Math.sqrt(sum / chunk.length);

      // Mantener pre-roll siempre (solo para el comienzo de la frase)
      this.preRoll.push(...chunk);
      if (this.preRoll.length > this.preRollMaxSamples) {
        this.preRoll = this.preRoll.slice(this.preRoll.length - this.preRollMaxSamples);
      }

      // Si todavía no detectamos voz, no enviamos audio (evita transcripciones fantasma por ruido/silencio).
      if (!this.inSpeech) {
        if (rms >= this.startThreshold) {
          this.startChunks++;
          this.startCandidate.push(chunk);
          if (this.startChunks >= this.minStartChunks) {
            this.inSpeech = true;
            this.silenceChunks = 0;

            // Enviar pre-roll + candidatos (incluye el inicio real)
            if (this.preRoll.length) {
              this.port.postMessage({ type: "audio", data: new Float32Array(this.preRoll) });
            }
            for (let i = 0; i < this.startCandidate.length; i++) {
              this.port.postMessage({ type: "audio", data: new Float32Array(this.startCandidate[i]) });
            }

            this.preRoll = [];
            this.startCandidate = [];
          }
        } else {
          this.startChunks = 0;
          this.startCandidate = [];
        }
        // si no hay voz, descartamos el chunk
      } else {
        // En habla: enviamos audio siempre
        this.port.postMessage({ type: "audio", data: new Float32Array(chunk) });

        // detección de silencio para fin de frase
        if (rms < this.silenceThreshold) {
          this.silenceChunks++;
          if (this.silenceChunks >= this.maxSilenceChunks) {
            this.port.postMessage({ type: "end_of_utterance", data: new Float32Array(0) });
            this.silenceChunks = 0;
            this.startChunks = 0;
            this.inSpeech = false;
            this.preRoll = [];
            this.startCandidate = [];
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

registerProcessor("pcm-processor", PCMProcessor);
