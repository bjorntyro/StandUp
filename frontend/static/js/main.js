// Menacing floating symbols
(function spawnMenacing() {
    const container = document.getElementById("menacingContainer");
    if (!container) return;
    const symbols = ["ゴ", "ゴ", "♦", "ゴ", "★", "ゴ"];
    for (let i = 0; i < 10; i++) {
        const el = document.createElement("span");
        el.className = "menacing";
        el.textContent = symbols[Math.floor(Math.random() * symbols.length)];
        el.style.left = Math.random() * 100 + "vw";
        el.style.animationDuration = (8 + Math.random() * 12) + "s";
        el.style.animationDelay = (Math.random() * 14) + "s";
        el.style.fontSize = (1.2 + Math.random() * 1.8) + "rem";
        container.appendChild(el);
    }
})();
