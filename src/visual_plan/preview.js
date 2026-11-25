(() => {
  const revealStep = () => {
    const target = document.getElementById(location.hash.slice(1));
    if (target?.matches("details.step")) target.open = true;
  };
  addEventListener("hashchange", revealStep);
  document.addEventListener("click", (event) => {
    const link = event.target.closest?.('a[href^="#step-"]');
    if (link) {
      const target = document.getElementById(link.getAttribute("href").slice(1));
      if (target) target.open = true;
    }
  });
  revealStep();

  let collapsed = [];
  addEventListener("beforeprint", () => {
    collapsed = [...document.querySelectorAll("details:not([open])")];
    for (const detail of collapsed) detail.open = true;
  });
  addEventListener("afterprint", () => {
    for (const detail of collapsed) detail.open = false;
    collapsed = [];
  });
})();
