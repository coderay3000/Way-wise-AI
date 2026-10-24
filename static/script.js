const $ = (id) => document.getElementById(id);
const EMOJI = ["🏝️", "🗼", "🏔️", "🌆", "🏖️", "🕌"];
const COLORS = ["#e3f2fd", "#fff3e0", "#e8f5e9", "#f3e5f5", "#fce4ec", "#e0f7fa"];

let trips = JSON.parse(localStorage.getItem("ww_trips") || "[]");
let cur = null;


/* ---------- helpers ---------- */

function save() {
  localStorage.setItem("ww_trips", JSON.stringify(trips));
  $("cnt").textContent = trips.length;
}

function md(el, text) {
  if (typeof marked !== "undefined") el.innerHTML = marked.parse(text || "");
  else el.textContent = text || "";
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 4000);
}

function show(view) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("v-" + view).classList.remove("hidden");
  if (view === "home") renderCards($("homeList"), trips.slice(0, 4));
  if (view === "trips") renderCards($("tripList"), trips);
  window.scrollTo(0, 0);
}

function showTab(name) {
  document.querySelectorAll(".panel").forEach((p) => p.classList.add("hidden"));
  $("t-" + name).classList.remove("hidden");
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
}


/* ---------- trip cards ---------- */

function renderCards(list, items) {
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = '<div class="empty">Abhi koi trip nahi hai. Upar search bar mein apna trip likho.</div>';
    return;
  }
  items.forEach((t) => {
    const n = [...t.id].reduce((a, c) => a + c.charCodeAt(0), 0);
    const card = document.createElement("div");
    card.className = "trip";
    card.innerHTML =
      '<div class="trip-top" style="background:' + COLORS[n % 6] + '">' + EMOJI[n % 6] + "</div>" +
      '<div class="trip-body"><h3></h3><p></p><span class="tag">AI Plan ✓</span></div>';
    card.querySelector("h3").textContent = t.title;
    card.querySelector("p").textContent = new Date(t.created).toLocaleDateString() + " · " + t.chat.length + " chat msgs";
    card.onclick = () => openTrip(t.id);
    list.appendChild(card);
  });
}

function openTrip(id) {
  cur = trips.find((t) => t.id === id);
  if (!cur) return show("home");
  $("dTitle").textContent = cur.title;
  $("crTitle").textContent = cur.title.slice(0, 40);
  $("dMeta").textContent = "Thread ID: " + cur.id;
  md($("resultBox"), cur.answer);
  $("rawFlights").textContent = cur.flights || "No data";
  $("rawHotels").textContent = cur.hotels || "No data";
  $("rawWeather").textContent = cur.weather || "No data";
  renderChat();
  showTab("plan");
  show("detail");
}


/* ---------- plan a trip ---------- */

async function planTrip() {
  const message = $("searchInput").value.trim();
  if (!message) return toast("Pehle apna travel request likho.");

  const steps = ["Searching flights...", "Finding hotels...", "Checking weather...", "Writing your plan..."];
  let i = 0;
  $("loadMsg").textContent = steps[0];
  $("overlay").classList.remove("hidden");
  const timer = setInterval(() => ($("loadMsg").textContent = steps[Math.min(++i, steps.length - 1)]), 9000);

  try {
    const res = await fetch("/api/travel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || "Kuch galat ho gaya.");

    const trip = {
      id: data.thread_id,
      title: message.length > 80 ? message.slice(0, 80) + "..." : message,
      created: Date.now(),
      answer: data.answer || data.itinerary,
      flights: data.flight_results,
      hotels: data.hotel_results,
      weather: data.weather_results,
      chat: [],
    };
    trips.unshift(trip);
    save();
    $("searchInput").value = "";
    openTrip(trip.id);
  } catch (e) {
    toast(e.message);
  } finally {
    clearInterval(timer);
    $("overlay").classList.add("hidden");
  }
}


/* ---------- chat ---------- */

function renderChat() {
  const box = $("chatBox");
  box.innerHTML = "";
  const hello = document.createElement("div");
  hello.className = "msg bot";
  hello.textContent = "Hi! Is trip ke baare mein kuch bhi pucho: itinerary, budget, hotels ya packing.";
  box.appendChild(hello);

  cur.chat.forEach((m) => {
    const d = document.createElement("div");
    d.className = "msg " + (m.role === "user" ? "user" : "bot");
    if (m.role === "user") d.textContent = m.content;
    else md(d, m.content);
    box.appendChild(d);
  });
  box.scrollTop = box.scrollHeight;
}

async function sendChat(text) {
  const question = (text || $("chatInput").value).trim();
  if (!question || !cur) return;

  const history = cur.chat.slice(-6);
  cur.chat.push({ role: "user", content: question });
  $("chatInput").value = "";
  renderChat();
  $("chatBtn").disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: cur.id, question, history }),
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || "Chat fail ho gayi.");
    cur.chat.push({ role: "assistant", content: data.answer });
  } catch (e) {
    cur.chat.push({ role: "assistant", content: "⚠️ " + e.message });
  } finally {
    save();
    renderChat();
    $("chatBtn").disabled = false;
  }
}


/* ---------- pdf & delete ---------- */

function downloadPDF() {
  if (!cur) return;
  showTab("plan");
  const btn = $("pdfBtn");
  btn.disabled = true;
  html2pdf()
    .set({
      margin: 0.5,
      filename: "travel-plan.pdf",
      html2canvas: { scale: 2, backgroundColor: "#ffffff" },
      jsPDF: { unit: "in", format: "a4", orientation: "portrait" },
      pagebreak: { mode: ["css", "legacy"] },
    })
    .from($("pdfContent"))
    .save()
    .finally(() => (btn.disabled = false));
}

function deleteTrip() {
  if (!cur || !confirm("Ye trip delete kar du?")) return;
  trips = trips.filter((t) => t.id !== cur.id);
  cur = null;
  save();
  show("trips");
}


/* ---------- events ---------- */

$("logo").onclick = () => show("home");
$("crHome").onclick = () => show("home");
$("crTrips").onclick = () => show("trips");
$("tripsLink").onclick = () => show("trips");
$("seeAll").onclick = () => show("trips");
$("searchBtn").onclick = planTrip;
$("searchInput").addEventListener("keydown", (e) => e.key === "Enter" && planTrip());
$("chatBtn").onclick = () => sendChat();
$("chatInput").addEventListener("keydown", (e) => e.key === "Enter" && sendChat());
$("pdfBtn").onclick = downloadPDF;
$("delBtn").onclick = deleteTrip;

document.querySelectorAll(".cat").forEach((c) =>
  c.addEventListener("click", () => {
    $("searchInput").value = c.dataset.p;
    $("searchInput").focus();
    window.scrollTo(0, 0);
    toast("Request ready. Search icon ya Enter dabao.");
  })
);
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
document.querySelectorAll(".quick button").forEach((b) => b.addEventListener("click", () => sendChat(b.dataset.q)));

$("cnt").textContent = trips.length;
show("home");