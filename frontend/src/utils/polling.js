/**
 * 任务轮询器：
 * - intervalMs 间隔轮询任务状态（默认 1 秒）
 * - maxWaitMs 最大等待（默认 60 秒），超时只通知，不自动重试/创建任务
 * - stop() 停止轮询（页面卸载、创建新任务时调用）
 * - 轮询过程中的请求错误直接停止并回调 onError
 */
export function createTaskPoller({
  taskId,
  fetchTask,
  onUpdate = () => {},
  onComplete = () => {},
  onFailed = () => {},
  onTimeout = () => {},
  onError = () => {},
  intervalMs = 1000,
  maxWaitMs = 60000,
} = {}) {
  if (!taskId) throw new Error("taskId is required");

  let timer = null;
  let stopped = false;
  let finished = false;
  const startedAt = Date.now();

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function stop() {
    stopped = true;
    clearTimer();
  }

  function schedule() {
    if (stopped || finished) return;
    timer = setTimeout(run, intervalMs);
  }

  async function run() {
    if (stopped || finished) return;
    let task = null;
    try {
      task = await fetchTask(taskId);
    } catch (error) {
      finished = true;
      clearTimer();
      await onError(error);
      return;
    }
    if (stopped || finished) return;

    onUpdate(task);
    if (task && task.status === "COMPLETED") {
      finished = true;
      clearTimer();
      await onComplete(task);
      return;
    }
    if (task && task.status === "FAILED") {
      finished = true;
      clearTimer();
      await onFailed(task);
      return;
    }
    if (Date.now() - startedAt >= maxWaitMs) {
      finished = true;
      clearTimer();
      await onTimeout(task);
      return;
    }
    schedule();
  }

  return {
    start() {
      if (stopped || finished) return;
      void run();
    },
    stop,
    isFinished: () => finished,
    isStopped: () => stopped,
  };
}
