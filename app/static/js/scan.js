/* Camera scanning.
 *
 * Uses the browser's built-in BarcodeDetector, which covers QR, Data Matrix, and
 * Code 128 on Chrome and Android without shipping a decoder library. Where it is
 * unavailable the page falls back to the manual entry form, which is always present,
 * so no browser is locked out.
 *
 * The camera needs a secure context: localhost works, and a LAN deployment needs
 * HTTPS or a tunnel. That is stated in the UI rather than failing silently.
 */

(function () {
  "use strict";

  var root = document.querySelector("[data-scanner]");
  if (!root) return;

  var video = root.querySelector("video");
  var status = root.querySelector("[data-scan-status]");
  var startButton = document.querySelector("[data-scan-start]");
  var stopButton = document.querySelector("[data-scan-stop]");
  var manualInput = document.querySelector("[data-scan-code]");

  var stream = null;
  var detector = null;
  var running = false;
  var lastCode = "";
  var lastAt = 0;

  var FORMATS = ["qr_code", "data_matrix", "code_128", "code_39", "ean_13", "ean_8", "upc_a", "upc_e"];

  function say(message) {
    if (status) status.textContent = message;
  }

  function supported() {
    return "BarcodeDetector" in window && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
  }

  function stop() {
    running = false;
    if (stream) {
      stream.getTracks().forEach(function (track) {
        track.stop();
      });
      stream = null;
    }
    if (video) video.srcObject = null;
    root.classList.add("hidden");
    if (startButton) startButton.classList.remove("hidden");
    if (stopButton) stopButton.classList.add("hidden");
  }

  function found(code) {
    var now = Date.now();
    // The same sticker stays in frame for many frames; debounce so one scan is one hit.
    if (code === lastCode && now - lastAt < 2500) return;
    lastCode = code;
    lastAt = now;

    if (navigator.vibrate) navigator.vibrate(40);
    say("Found " + code + " - opening...");
    if (manualInput) manualInput.value = code;
    stop();
    window.location.assign("/scan?code=" + encodeURIComponent(code));
  }

  function loop() {
    if (!running || !detector || !video) return;
    if (video.readyState < 2) {
      window.requestAnimationFrame(loop);
      return;
    }
    detector
      .detect(video)
      .then(function (results) {
        if (results && results.length) {
          var value = (results[0].rawValue || "").trim();
          if (value) found(value);
        }
      })
      .catch(function () {
        /* A single dropped frame is not worth surfacing. */
      })
      .finally(function () {
        if (running) window.requestAnimationFrame(loop);
      });
  }

  function start() {
    if (!supported()) {
      say("This browser cannot scan with the camera. Type or paste the code below instead.");
      return;
    }
    root.classList.remove("hidden");
    say("Requesting the camera...");

    window.BarcodeDetector.getSupportedFormats()
      .then(function (available) {
        var wanted = FORMATS.filter(function (format) {
          return available.indexOf(format) !== -1;
        });
        detector = new window.BarcodeDetector(wanted.length ? { formats: wanted } : undefined);
        return navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
          audio: false
        });
      })
      .then(function (media) {
        stream = media;
        video.srcObject = media;
        video.setAttribute("playsinline", "");
        return video.play();
      })
      .then(function () {
        running = true;
        if (startButton) startButton.classList.add("hidden");
        if (stopButton) stopButton.classList.remove("hidden");
        say("Point the camera at a label.");
        window.requestAnimationFrame(loop);
      })
      .catch(function (error) {
        var name = error && error.name;
        if (name === "NotAllowedError") {
          say("Camera access was declined. Type the code below instead.");
        } else if (name === "NotFoundError") {
          say("No camera was found on this device.");
        } else if (!window.isSecureContext) {
          say("The camera needs HTTPS, or a localhost connection. Type the code below instead.");
        } else {
          say("The camera could not be started. Type the code below instead.");
        }
        stop();
      });
  }

  if (startButton) {
    startButton.addEventListener("click", start);
    if (!supported()) {
      startButton.disabled = true;
      startButton.title = "This browser has no built-in barcode detector";
      var hint = document.querySelector("[data-scan-hint]");
      if (hint) {
        hint.textContent =
          "This browser has no built-in barcode detector. Use Chrome on Android, or type the code.";
      }
    }
  }

  if (stopButton) stopButton.addEventListener("click", stop);

  document.addEventListener("visibilitychange", function () {
    if (document.hidden && running) stop();
  });

  if (manualInput) manualInput.focus();
})();
