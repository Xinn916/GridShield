const ERROR_MESSAGES = {
  "not-allowed": "未获得麦克风权限，请允许浏览器访问麦克风后重试。",
  "service-not-allowed": "未获得麦克风权限，请允许浏览器访问麦克风后重试。",
  "no-speech": "未检测到语音，请重试。",
  "audio-capture": "未检测到可用麦克风。",
  network: "语音识别暂时不可用，请使用文字输入。",
};

export function speechRecognitionErrorMessage(code) {
  return ERROR_MESSAGES[code] || "语音识别暂时不可用，请使用文字输入。";
}

export function joinSpeechText(...parts) {
  return parts
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .join(" ");
}

function transcriptFromResult(result) {
  return String(result?.[0]?.transcript || "").trim();
}

export function createSpeechRecognitionController({
  environment = globalThis.window,
  readInput = () => "",
  writeInput = () => {},
  onStateChange = () => {},
  onError = () => {},
} = {}) {
  const Recognition = environment?.SpeechRecognition || environment?.webkitSpeechRecognition;
  const apiSupported = typeof Recognition === "function";
  const secureContext = environment?.isSecureContext !== false;
  const supported = apiSupported && secureContext;
  const unavailableReason = !apiSupported
    ? "当前浏览器暂不支持语音输入，请使用 Chrome 或 Edge。"
    : !secureContext ? "语音输入需要 HTTPS 或 localhost 安全环境。" : "";
  let recognition = null;
  let listening = false;
  let activeRun = 0;
  let baseText = "";
  let finalTranscript = "";
  let interimTranscript = "";

  const state = () => ({ supported, listening, unavailableReason });
  const emitState = () => onStateChange(state());
  const writeTranscript = () => {
    const value = joinSpeechText(baseText, finalTranscript, interimTranscript);
    writeInput(value);
    return value;
  };

  function resetTranscriptState() {
    baseText = "";
    finalTranscript = "";
    interimTranscript = "";
  }

  function start() {
    if (!supported || listening) return false;
    const instance = new Recognition();
    const run = ++activeRun;
    recognition = instance;
    baseText = String(readInput() || "").trim();
    finalTranscript = "";
    interimTranscript = "";
    instance.lang = "zh-CN";
    instance.interimResults = true;
    instance.continuous = true;

    instance.onstart = () => {
      if (run !== activeRun) return;
      listening = true;
      emitState();
    };
    instance.onresult = (event) => {
      if (run !== activeRun) return;
      let nextFinal = "";
      let nextInterim = "";
      for (let index = 0; index < (event.results?.length || 0); index += 1) {
        const text = transcriptFromResult(event.results[index]);
        if (!text) continue;
        if (event.results[index].isFinal) nextFinal = joinSpeechText(nextFinal, text);
        else nextInterim = joinSpeechText(nextInterim, text);
      }
      finalTranscript = nextFinal;
      interimTranscript = nextInterim;
      writeTranscript();
    };
    instance.onerror = (event) => {
      if (run !== activeRun) return;
      listening = false;
      emitState();
      if (event?.error !== "aborted") onError(speechRecognitionErrorMessage(event?.error));
    };
    instance.onend = () => {
      if (run !== activeRun) return;
      writeTranscript();
      recognition = null;
      listening = false;
      resetTranscriptState();
      emitState();
    };

    listening = true;
    emitState();
    try {
      instance.start();
      return true;
    } catch {
      recognition = null;
      listening = false;
      resetTranscriptState();
      emitState();
      onError("语音识别暂时不可用，请使用文字输入。");
      return false;
    }
  }

  function requestStop() {
    if (!recognition) return false;
    listening = false;
    emitState();
    try {
      recognition.stop();
    } catch {
      // The browser may already have ended the recognition session.
    }
    return true;
  }

  function cancel({ abort = false, discardInterim = false } = {}) {
    if (discardInterim && interimTranscript) {
      writeInput(joinSpeechText(baseText, finalTranscript));
    }
    const instance = recognition;
    activeRun += 1;
    recognition = null;
    listening = false;
    resetTranscriptState();
    if (instance) {
      try {
        if (abort && typeof instance.abort === "function") instance.abort();
        else instance.stop();
      } catch {
        // Ending an already-finished browser session is harmless.
      }
    }
    emitState();
  }

  function toggle() {
    return listening ? requestStop() : start();
  }

  return {
    cancel,
    getState: state,
    requestStop,
    start,
    toggle,
  };
}
