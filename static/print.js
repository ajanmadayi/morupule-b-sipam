document.addEventListener("DOMContentLoaded", () => {
  document.querySelector("#printCommand")?.addEventListener("click", () => {
    window.print();
  });
});
