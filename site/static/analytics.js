// Google Analytics events for the crash lookup. Same safe-call pattern as maxmautner.com's trackEvent; every event
// is prefixed crashes_ so it can be filtered from the blog's events in the shared property. Nothing typed into the
// search box and no location is ever sent: the front page promises that stays on the device.
(function () {
  const page = document.querySelector(".cx-intersection");
  const intersection = page ? page.dataset.id : "";

  function track(name, params) {
    if (typeof gtag === "function") gtag("event", "crashes_" + name, Object.assign({ intersection }, params || {}));
  }
  window.cxTrack = track;

  // data-track="council_email_clicked" plus data-track-* params; data-track-pdf-page -> pdf_page
  function named(el) {
    const params = {};
    for (const [k, v] of Object.entries(el.dataset))
      if (k.startsWith("track") && k !== "track")
        params[k.slice(5).replace(/[A-Z]/g, (c) => "_" + c.toLowerCase()).replace(/^_/, "")] = v;
    track(el.dataset.track, params);
  }

  document.addEventListener("click", (ev) => {
    const el = ev.target.closest("a, button");
    if (!el) return;
    if (el.dataset.track) { named(el); return; }
    if (el.tagName !== "A") return;
    // links that leave maxmautner.com: city plans and pages, CCRS, GitHub
    try {
      const u = new URL(el.getAttribute("href") || "", location.href);
      if (u.protocol.startsWith("http") && u.hostname !== location.hostname)
        track("outbound_clicked", { link_url: u.href, link_text: el.textContent.trim().slice(0, 100) });
    } catch (e) { /* not a URL */ }
  });

  // <details data-track=...>: a crash or a plan opened; toggle doesn't bubble, so listen while capturing
  document.addEventListener("toggle", (ev) => {
    const el = ev.target;
    if (el.open && el.dataset && el.dataset.track) named(el);
  }, true);
})();
