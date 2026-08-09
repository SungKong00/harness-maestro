"use strict";

(function attachProjectSnapshotLoader(root) {
  function createProjectSnapshotLoader({
    loadSnapshot,
    onStart,
    onSuccess,
    onFailure,
    onSettled,
  }) {
    let requestSequence = 0;
    let activeController = null;

    async function load(projectId) {
      const requestId = ++requestSequence;
      if (activeController) activeController.abort();

      const controller = new AbortController();
      activeController = controller;
      onStart(projectId);

      try {
        const snapshot = await loadSnapshot(projectId, controller.signal);
        if (requestId !== requestSequence || controller.signal.aborted) {
          return { status: "superseded", projectId };
        }
        onSuccess(snapshot, projectId);
        return { status: "loaded", projectId };
      } catch (reason) {
        if (
          requestId !== requestSequence
          || controller.signal.aborted
          || reason?.name === "AbortError"
        ) {
          return { status: "superseded", projectId };
        }
        onFailure(reason, projectId);
        return { status: "failed", projectId };
      } finally {
        if (requestId === requestSequence) {
          activeController = null;
          onSettled(projectId);
        }
      }
    }

    return { load };
  }

  root.createProjectSnapshotLoader = createProjectSnapshotLoader;
  if (typeof module === "object" && module.exports) {
    module.exports = { createProjectSnapshotLoader };
  }
}(globalThis));
