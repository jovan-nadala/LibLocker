(function () {
  // ===== Clock (top-right) =====
  const timeEl = document.getElementById("time");
  const dateEl = document.getElementById("date");

  function pad2(n){ return String(n).padStart(2, "0"); }

  function formatDate(d){
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  }

  function tick(){
    const now = new Date();
    const hh = pad2(now.getHours());
    const mm = pad2(now.getMinutes());
    timeEl.textContent = `${hh}:${mm}`;
    dateEl.textContent = formatDate(now);
  }
  tick();
  setInterval(tick, 1000);

  // ===== Card interactions (visual only for homepage) =====
  const cards = document.querySelectorAll(".action-card");
  cards.forEach((card) => {
    card.addEventListener("click", () => {
      cards.forEach(c => c.classList.remove("action-card--active"));
      card.classList.add("action-card--active");

      // You can hook navigation here later:
      // const action = card.dataset.action;
      // if (action === "register") window.location.href = "/kiosk/register";
      // etc.
    });
  });

  // Help button demo
  const help = document.querySelector(".help-btn");
  help.addEventListener("click", () => {
    alert("Help:\n1) Select an action.\n2) Tap RFID key fob.\n3) Follow on-screen instructions.");
  });

  // Language selector demo
  const langSelect = document.getElementById("langSelect");
  langSelect.addEventListener("change", () => {
    // Later: replace UI strings based on language
    console.log("Language:", langSelect.value);
  });
})();
