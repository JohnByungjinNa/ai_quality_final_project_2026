const root = document.documentElement;
const themeToggle = document.querySelector(".theme-toggle");
const themeLabel = document.querySelector(".theme-toggle__label");
const savedTheme = window.localStorage.getItem("portfolio-theme");

if (savedTheme === "dark") {
  root.dataset.theme = "dark";
}

function updateThemeButton() {
  const isDark = root.dataset.theme === "dark";
  themeToggle.setAttribute("aria-pressed", String(isDark));
  themeLabel.textContent = isDark ? "Light" : "Dark";
}

updateThemeButton();

themeToggle.addEventListener("click", () => {
  const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
  if (nextTheme === "dark") {
    root.dataset.theme = "dark";
  } else {
    delete root.dataset.theme;
  }
  window.localStorage.setItem("portfolio-theme", nextTheme);
  updateThemeButton();
});

const filterButtons = document.querySelectorAll(".filter-button");
const projectCards = document.querySelectorAll(".project");
const filterEmpty = document.querySelector(".filter-empty");

filterButtons.forEach((button) => {
  button.setAttribute("aria-pressed", String(button.classList.contains("is-active")));
  button.addEventListener("mousedown", (event) => {
    event.preventDefault();
    button.focus({ preventScroll: true });
  });
});

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const filter = button.dataset.filter;
    let visibleCount = 0;

    filterButtons.forEach((item) => {
      const isActive = item === button;
      item.classList.toggle("is-active", isActive);
      item.setAttribute("aria-pressed", String(isActive));
    });
    projectCards.forEach((card) => {
      const isVisible = filter === "all" || card.dataset.category.split(" ").includes(filter);
      card.hidden = !isVisible;
      if (isVisible) visibleCount += 1;
    });
    filterEmpty.hidden = visibleCount > 0;
    button.focus({ preventScroll: true });
  });
});

const navLinks = document.querySelectorAll(".site-nav a");
const observedSections = [...navLinks]
  .map((link) => link.getAttribute("href"))
  .filter((href) => href && href.startsWith("#"))
  .map((href) => document.querySelector(href))
  .filter(Boolean);

const sectionObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => {
        link.classList.toggle("is-current", link.getAttribute("href") === `#${entry.target.id}`);
      });
    });
  },
  { rootMargin: "-35% 0px -55%" }
);

observedSections.forEach((section) => sectionObserver.observe(section));
