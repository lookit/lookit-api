const SMOOTHING_FACTOR = 0.99;
const SCALING_FACTOR = 5;
/**
 * Audio Worklet Processor class for processing audio input streams. This is
 * used by the Recorder to run a volume check on the microphone input stream.
 * Source:
 * https://www.webrtc-developers.com/how-to-know-if-my-microphone-works/#detect-noise-or-silence
 */
export default class MicCheckProcessor extends AudioWorkletProcessor {
    _volume;
    _micChecked;
    /** Constructor for the mic check processor. */
    constructor() {
        super();
        this._volume = 0;
        this._micChecked = false;
        /**
         * Callback to handle a message event on the processor's port. This
         * determines how the processor responds when the recorder posts a message
         * to the processor with e.g. this.processorNode.port.postMessage({
         * micChecked: true }).
         *
         * @param event - Message event generated from the 'postMessage' call, which
         *   includes, among other things, the data property.
         * @param event.data - Data sent by the message emitter.
         */
        this.port.onmessage = (event) => {
            if (event.data &&
                event.data.micChecked &&
                event.data.micChecked == true) {
                this._micChecked = true;
            }
        };
    }
    /**
     * Process method that implements the audio processing algorithm for the Audio
     * Processor Worklet. "Although the method is not a part of the
     * AudioWorkletProcessor interface, any implementation of
     * AudioWorkletProcessor must provide a process() method." Source:
     * https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletProcessor/process
     * The process method can take the following arguments: inputs, outputs,
     * parameters. Here we are only using inputs.
     *
     * @param inputs - An array of inputs from the audio stream (microphone)
     *   connnected to the node. Each item in the inputs array is an array of
     *   channels. Each channel is a Float32Array containing 128 samples. For
     *   example, inputs[n][m][i] will access n-th input, m-th channel of that
     *   input, and i-th sample of that channel.
     * @returns Boolean indicating whether or not the Audio Worklet Node should
     *   remain active, even if the User Agent thinks it is safe to shut down. In
     *   this case, when the recorder decides that the mic check criteria has been
     *   met, it will return false (processor should be shut down), otherwise it
     *   will return true (processor should remain active).
     */
    process(inputs) {
        if (this._micChecked) {
            return false;
        }
        else {
            const input = inputs[0];
            const samples = input[0];
            if (samples) {
                const sumSquare = samples.reduce((p, c) => p + c * c, 0);
                const rms = Math.sqrt(sumSquare / (samples.length || 1)) * SCALING_FACTOR;
                this._volume = Math.max(rms, this._volume * SMOOTHING_FACTOR);
                this.port.postMessage({ volume: this._volume });
            }
            return true;
        }
    }
}
registerProcessor("mic-check-processor", MicCheckProcessor);
