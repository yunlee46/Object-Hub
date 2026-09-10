/* Object Hub front end.
 *
 * Progressive enhancement only: every page works with JavaScript disabled, because
 * the server renders complete HTML and all mutations are plain form posts. This file
 * adds the conveniences that make the app pleasant on a phone.
 *
 * No dependencies by design - a self-hosted NAS app should not need a CDN.
 */

(function () {
  "use strict";

  var THEME_KEY = "objecthub.theme";

  /* ---------------------------------------------------------------- theme */

  function applyTheme(theme) {
    var resolved = theme;
    if (resolved !== "light" && resolved !== "dark") {
      resolved = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    document.documentElement.setAttribute("data-theme", resolved);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.setAttribute("aria-label", "Switch to " + (resolved === "dark" ? "light" : "dark") + " theme");
      button.querySelectorAll("[data-theme-icon]").forEach(function (icon) {
        icon.classList.toggle("hidden", icon.getAttribute("data-theme-icon") !== resolved);
      });
    });
  }

  function initTheme() {
    var stored = null;
    try {
      stored = localStorage.getItem(THEME_KEY);
    } catch (err) {
      stored = null;
    }
    applyTheme(stored);

    document.addEventListener("click", function (event) {
      var toggle = event.target.closest("[data-theme-toggle]");
      if (!toggle) return;
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (err) {
        /* Private browsing: the choice simply does not persist. */
      }
      applyTheme(next);
    });

    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
      var stored2 = null;
      try {
        stored2 = localStorage.getItem(THEME_KEY);
      } catch (err) {
        stored2 = null;
      }
      if (!stored2) applyTheme(null);
    });
  }

  /* ------------------------------------------------------------ behaviours */

  function initFlash() {
    document.addEventListener("click", function (event) {
      var dismiss = event.target.closest("[data-dismiss]");
      if (!dismiss) return;
      var flash = dismiss.closest(".flash");
      if (flash) flash.remove();
    });
  }

  /* Destructive form posts ask once before submitting. */
  function initConfirm() {
    document.addEventListener("submit", function (event) {
      var form = event.target;
      var message = form.getAttribute("data-confirm");
      if (message && !window.confirm(message)) {
        event.preventDefault();
      }
    });
  }

  /* Any form marked data-autosubmit reloads the page when a control changes. */
  function initAutoSubmit() {
    document.querySelectorAll("form[data-autosubmit]").forEach(function (form) {
      form.addEventListener("change", function (event) {
        if (event.target.matches("input[type='text'], input[type='search']")) return;
        form.requestSubmit();
      });
    });
  }

  /* A tag editor over a plain comma-separated hidden input. */
  function initTagInputs() {
    document.querySelectorAll("[data-tag-input]").forEach(function (root) {
      var hidden = root.querySelector("input[type='hidden']");
      var entry = root.querySelector("[data-tag-entry]");
      var list = root.querySelector("[data-tag-list]");
      if (!hidden || !entry || !list) return;

      var tags = hidden.value
        .split(",")
        .map(function (value) {
          return value.trim();
        })
        .filter(Boolean);

      function sync() {
        hidden.value = tags.join(", ");
        list.textContent = "";
        tags.forEach(function (tag, index) {
          var chip = document.createElement("span");
          chip.className = "chip";
          chip.textContent = tag;
          var remove = document.createElement("button");
          remove.type = "button";
          remove.className = "chip-remove";
          remove.setAttribute("aria-label", "Remove tag " + tag);
          remove.textContent = "×";
          remove.addEventListener("click", function () {
            tags.splice(index, 1);
            sync();
          });
          chip.appendChild(remove);
          list.appendChild(chip);
        });
      }

      function add(raw) {
        raw
          .split(",")
          .map(function (value) {
            return value.trim();
          })
          .filter(Boolean)
          .forEach(function (value) {
            var exists = tags.some(function (tag) {
              return tag.toLowerCase() === value.toLowerCase();
            });
            if (!exists) tags.push(value);
          });
        entry.value = "";
        sync();
      }

      entry.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === ",") {
          event.preventDefault();
          add(entry.value);
        } else if (event.key === "Backspace" && !entry.value && tags.length) {
          tags.pop();
          sync();
        }
      });

      entry.addEventListener("blur", function () {
        if (entry.value.trim()) add(entry.value);
      });

      root.querySelectorAll("[data-tag-suggest]").forEach(function (button) {
        button.addEventListener("click", function () {
          add(button.getAttribute("data-tag-suggest") || button.textContent);
        });
      });

      sync();
    });
  }

  /* Type-ahead item lookup, used by the quick-find and move widgets. */
  function initCombos() {
    document.querySelectorAll("[data-combo]").forEach(function (root) {
      var input = root.querySelector("input[type='search'], input[type='text']");
      var list = root.querySelector("[data-combo-list]");
      if (!input || !list) return;

      var timer = null;
      var controller = null;

      function close() {
        list.textContent = "";
      }

      function search() {
        var text = input.value.trim();
        if (text.length < 2) {
          close();
          return;
        }
        if (controller) controller.abort();
        controller = new AbortController();
        fetch("/api/items?per_page=8&q=" + encodeURIComponent(text), {
          headers: { Accept: "application/json" },
          signal: controller.signal
        })
          .then(function (response) {
            return response.ok ? response.json() : { items: [] };
          })
          .then(function (payload) {
            list.textContent = "";
            (payload.items || []).forEach(function (item) {
              var option = document.createElement("a");
              option.className = "combo-option";
              option.href = "/items/" + item.id;
              option.textContent = item.name;
              if (item.location && item.location.path_label) {
                var path = document.createElement("span");
                path.className = "path";
                path.textContent = item.location.path_label;
                option.appendChild(path);
              }
              list.appendChild(option);
            });
          })
          .catch(function () {
            /* Aborted or offline: the plain form submit still works. */
          });
      }

      input.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(search, 180);
      });

      input.addEventListener("keydown", function (event) {
        if (event.key === "Escape") close();
      });

      document.addEventListener("click", function (event) {
        if (!root.contains(event.target)) close();
      });
    });
  }

  /* Label sheet: keep the print button in step with the checkbox selection. */
  function initLabelPicker() {
    var form = document.querySelector("[data-label-picker]");
    if (!form) return;
    var counter = form.querySelector("[data-label-count]");
    var toggleAll = form.querySelector("[data-label-all]");

    function boxes() {
      return Array.prototype.slice.call(form.querySelectorAll("input[name='id']"));
    }

    function refresh() {
      var chosen = boxes().filter(function (box) {
        return box.checked;
      });
      if (counter) {
        counter.textContent = chosen.length
          ? chosen.length + " selected"
          : "Nothing selected - printing every label shown";
      }
    }

    form.addEventListener("change", function (event) {
      if (event.target === toggleAll) {
        boxes().forEach(function (box) {
          box.checked = toggleAll.checked;
        });
      }
      refresh();
    });

    refresh();
  }

  /* Photo inputs preview locally before the form is posted. */
  function initPhotoPreview() {
    document.querySelectorAll("input[type='file'][data-preview]").forEach(function (input) {
      var target = document.querySelector(input.getAttribute("data-preview"));
      if (!target) return;
      input.addEventListener("change", function () {
        target.textContent = "";
        Array.prototype.slice.call(input.files || []).forEach(function (file) {
          if (!file.type.startsWith("image/")) return;
          var wrapper = document.createElement("div");
          wrapper.className = "photo";
          var image = document.createElement("img");
          image.alt = file.name;
          image.src = URL.createObjectURL(file);
          image.addEventListener("load", function () {
            URL.revokeObjectURL(image.src);
          });
          wrapper.appendChild(image);
          target.appendChild(wrapper);
        });
      });
    });
  }

  /* "/" focuses search, the way every other inventory tool behaves. */
  function initShortcuts() {
    document.addEventListener("keydown", function (event) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      var active = document.activeElement;
      if (active && active.matches("input, textarea, select, [contenteditable]")) return;
      var search = document.querySelector("[data-search-input]");
      if (search) {
        event.preventDefault();
        search.focus();
        search.select();
      }
    });
  }

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    initTheme();
    initFlash();
    initConfirm();
    initAutoSubmit();
    initTagInputs();
    initCombos();
    initLabelPicker();
    initPhotoPreview();
    initShortcuts();
  });
})();
