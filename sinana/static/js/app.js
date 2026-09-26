let installPrompt = null;
const installButtons = () => [document.getElementById("install-app"), document.getElementById("install-app-inline")].filter(Boolean);
window.addEventListener("beforeinstallprompt", event => {
  event.preventDefault();
  installPrompt = event;
  installButtons().forEach(button => button.hidden = false);
});
installButtons().forEach(button => button.addEventListener("click", async () => {
  if (!installPrompt) {
    alert("На iPhone: нажмите «Поделиться» → «На экран Домой». На компьютере используйте значок установки в адресной строке браузера.");
    return;
  }
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  installButtons().forEach(item => item.hidden = true);
}));
document.getElementById("menu-toggle")?.addEventListener("click", () => document.body.classList.toggle("menu-open"));
document.querySelectorAll(".sidebar a").forEach(link => link.addEventListener("click", () => document.body.classList.remove("menu-open")));
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js", {scope: "/"}));
