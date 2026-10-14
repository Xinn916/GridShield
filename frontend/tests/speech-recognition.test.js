import assert from "node:assert/strict";
import test from "node:test";
import {
  createSpeechRecognitionController,
  speechRecognitionErrorMessage,
} from "../src/agent/speech-recognition.js";

class FakeRecognition {
  static instances = [];

  constructor() {
    this.startCalls = 0;
    this.stopCalls = 0;
    this.abortCalls = 0;
    FakeRecognition.instances.push(this);
  }

  start() {
    this.startCalls += 1;
    this.onstart?.();
  }

  stop() {
    this.stopCalls += 1;
  }

  abort() {
    this.abortCalls += 1;
  }

  result(items) {
    const results = items.map(({ text, final = false }) => {
      const result = [{ transcript: text }];
      result.isFinal = final;
      return result;
    });
    this.onresult?.({ results });
  }
}

function createHarness(initial = "") {
  let input = initial;
  const states = [];
  const errors = [];
  const controller = createSpeechRecognitionController({
    environment: { SpeechRecognition: FakeRecognition },
    readInput: () => input,
    writeInput: (value) => { input = value; },
    onStateChange: (value) => states.push(value),
    onError: (message) => errors.push(message),
  });
  return { controller, errors, getInput: () => input, states };
}

test("speech input appends final and interim transcripts without duplication or auto-send", () => {
  FakeRecognition.instances.length = 0;
  const harness = createHarness("查询B园区");
  assert.equal(harness.controller.start(), true);
  const recognition = FakeRecognition.instances[0];
  assert.equal(recognition.startCalls, 1);
  assert.equal(recognition.lang, "zh-CN");
  assert.equal(recognition.interimResults, true);
  assert.equal(harness.controller.getState().listening, true);

  recognition.result([{ text: "十一月", final: false }]);
  assert.equal(harness.getInput(), "查询B园区 十一月");
  recognition.result([{ text: "十一月十一日", final: false }]);
  assert.equal(harness.getInput(), "查询B园区 十一月十一日", "interim updates must replace rather than append");
  recognition.result([
    { text: "十一月十一日", final: true },
    { text: "总用电量", final: false },
  ]);
  assert.equal(harness.getInput(), "查询B园区 十一月十一日 总用电量");

  recognition.onend();
  assert.equal(harness.controller.getState().listening, false);
  assert.equal(harness.getInput(), "查询B园区 十一月十一日 总用电量");
});

test("second toggle stops recognition and lifecycle cancellation invalidates late results", () => {
  FakeRecognition.instances.length = 0;
  const harness = createHarness();
  harness.controller.toggle();
  const recognition = FakeRecognition.instances[0];
  harness.controller.toggle();
  assert.equal(recognition.stopCalls, 1);
  assert.equal(harness.controller.getState().listening, false);

  harness.controller.start();
  const next = FakeRecognition.instances[1];
  next.result([{ text: "不会跨会话保留", final: false }]);
  harness.controller.cancel({ abort: true, discardInterim: true });
  assert.equal(next.abortCalls, 1);
  assert.equal(harness.getInput(), "");
  next.result([{ text: "迟到结果", final: true }]);
  assert.equal(harness.getInput(), "", "late recognition events must be ignored after cancellation");
});

test("speech errors are converted to safe Chinese guidance", () => {
  FakeRecognition.instances.length = 0;
  const harness = createHarness();
  harness.controller.start();
  FakeRecognition.instances[0].onerror({ error: "not-allowed" });
  assert.deepEqual(harness.errors, ["未获得麦克风权限，请允许浏览器访问麦克风后重试。"]);
  assert.equal(speechRecognitionErrorMessage("no-speech"), "未检测到语音，请重试。");
  assert.equal(speechRecognitionErrorMessage("audio-capture"), "未检测到可用麦克风。");
  assert.equal(speechRecognitionErrorMessage("network"), "语音识别暂时不可用，请使用文字输入。");
});

test("unsupported browsers remain safe and disabled-capable", () => {
  const errors = [];
  const controller = createSpeechRecognitionController({
    environment: {},
    onError: (message) => errors.push(message),
  });
  assert.deepEqual(controller.getState(), {
    supported: false,
    listening: false,
    unavailableReason: "当前浏览器暂不支持语音输入，请使用 Chrome 或 Edge。",
  });
  assert.equal(controller.start(), false);
  assert.deepEqual(errors, []);
});

test("public HTTP contexts expose a clear secure-origin limitation", () => {
  const controller = createSpeechRecognitionController({
    environment: { SpeechRecognition: FakeRecognition, isSecureContext: false },
  });
  assert.deepEqual(controller.getState(), {
    supported: false,
    listening: false,
    unavailableReason: "语音输入需要 HTTPS 或 localhost 安全环境。",
  });
  assert.equal(controller.start(), false);
});
