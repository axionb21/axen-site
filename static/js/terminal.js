(function () {
  const input = document.getElementById("term-input");
  const output = document.getElementById("term-output");
  if (!input || !output) return;

  function print(line) {
    const div = document.createElement("div");
    div.textContent = line;
    output.appendChild(div);
    output.scrollTop = output.scrollHeight;
  }

  async function run(cmd) {
    print("$ " + cmd);
    try {
      const res = await fetch("/api/terminal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cmd }),
      });
      const data = await res.json();
      if (data.type === "clear") {
        output.innerHTML = "";
      } else if (data.type === "open" && data.url) {
        print("opening " + data.url + " ...");
        window.open(data.url, "_blank", "noopener");
      } else if (data.type === "scroll" && data.target) {
        const el = document.getElementById(data.target);
        if (el) el.scrollIntoView({ behavior: "smooth" });
        print("jumped to #" + data.target);
      } else {
        print(data.data || "");
      }
    } catch (e) {
      print("error: could not reach server");
    }
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && input.value.trim()) {
      const cmd = input.value.trim();
      input.value = "";
      run(cmd);
    }
  });
})();
