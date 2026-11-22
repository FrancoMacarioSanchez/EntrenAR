// EntrenAR · panel
(function () {
  const root = document.documentElement;
  const saved = localStorage.getItem("entrenar-theme");
  if (saved) root.dataset.theme = saved;
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches) root.dataset.theme = "dark";

  window.toggleTheme = function () {
    const t = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = t;
    localStorage.setItem("entrenar-theme", t);
  };

  function csrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }
  window.csrf = csrf;

  document.addEventListener("htmx:configRequest", (e) => { e.detail.headers["X-CSRFToken"] = csrf(); });

  document.addEventListener("click", (e) => {
    const c = e.target.closest("[data-confirm]");
    if (c && !confirm(c.dataset.confirm)) { e.preventDefault(); e.stopPropagation(); }
    const b = e.target.closest("[data-toggle-side]");
    if (b) document.querySelector(".side").classList.toggle("open");
  }, true);

  function initToasts(scope) {
    scope.querySelectorAll(".toast").forEach((t) => setTimeout(() => {
      t.style.transition = "opacity .4s, transform .4s"; t.style.opacity = 0; t.style.transform = "translateX(30px)";
      setTimeout(() => t.remove(), 400);
    }, 5500));
  }

  // select filtrable: <select data-filter> agrega un buscador arriba
  function initFilterSelects(scope) {
    scope.querySelectorAll("select[data-filter]").forEach((sel) => {
      if (sel.dataset.ready) return;
      sel.dataset.ready = 1;
      const inp = document.createElement("input");
      inp.className = "input"; inp.placeholder = "Buscar…"; inp.style.marginBottom = "6px";
      sel.parentNode.insertBefore(inp, sel);
      const all = Array.from(sel.options).map((o) => [o.value, o.text]);
      inp.addEventListener("input", () => {
        const q = inp.value.toLowerCase();
        const cur = sel.value;
        sel.innerHTML = "";
        all.filter(([v, t]) => !q || !v || t.toLowerCase().includes(q)).forEach(([v, t]) => {
          const o = new Option(t, v, false, v === cur); sel.add(o);
        });
        if (q && sel.options.length > 1) { sel.selectedIndex = 1; sel.dispatchEvent(new Event("change")); }
      });
    });
  }

  function initKanban(scope) {
    if (!window.Sortable) return;
    scope.querySelectorAll(".kcards").forEach((col) => {
      if (col.dataset.ready) return;
      col.dataset.ready = 1;
      new Sortable(col, {
        group: "leads", animation: 160, ghostClass: "sortable-ghost",
        onAdd: save, onUpdate: save,
      });
      function save(evt) {
        const el = evt.item;
        const body = new URLSearchParams({ stage: evt.to.dataset.stage, position: evt.newIndex });
        fetch(el.dataset.move, { method: "POST", headers: { "X-CSRFToken": csrf() }, body });
        document.querySelectorAll(".kcol").forEach((k) => {
          k.querySelector("[data-count]").textContent = k.querySelectorAll(".kcard").length;
        });
      }
    });
  }

  function init(scope) { initToasts(scope); initFilterSelects(scope); initKanban(scope); }
  document.addEventListener("DOMContentLoaded", () => init(document));
  document.addEventListener("htmx:afterSwap", (e) => init(e.target));
})();
