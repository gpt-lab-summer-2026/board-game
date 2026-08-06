const box = document.getElementById("message-box");

async function poll() {
  try {
    const res = await fetch("/status");
    const data = await res.json();
    box.textContent = data.message;
  } catch (err) {
    // server not reachable yet (e.g. voice pipeline still starting up) -- keep last message
  }
}

poll();
setInterval(poll, 1000);
