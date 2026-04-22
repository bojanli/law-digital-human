mergeInto(LibraryManager.library, {
  UnityToWeb: function(messagePtr) {
    try {
      var message = UTF8ToString(messagePtr);
      var data = JSON.parse(message);
      window.postMessage(data, "*");
      if (data && data.event === "OnAvatarReady") {
        window.dispatchEvent(new CustomEvent("avatar:ready"));
      } else if (data && data.event === "OnPlayFinished") {
        window.dispatchEvent(new CustomEvent("avatar:play-finished"));
      }
    } catch (e) {
      console.warn("[UnityToWeb] failed:", e);
    }
  }
});
