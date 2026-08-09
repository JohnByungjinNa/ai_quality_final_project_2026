(() => {
  const themeToggle = document.querySelector('.theme-toggle');
  const savedTheme = window.localStorage.getItem('ai-qa-theme');

  if (savedTheme === 'dark') {
    document.body.classList.add('theme-dark');
    themeToggle?.setAttribute('aria-pressed', 'true');
  }

  themeToggle?.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('theme-dark');
    themeToggle.setAttribute('aria-pressed', String(isDark));
    window.localStorage.setItem('ai-qa-theme', isDark ? 'dark' : 'light');
  });

  const revealItems = document.querySelectorAll('[data-reveal]');
  if (!('IntersectionObserver' in window)) {
    revealItems.forEach((item) => item.classList.add('is-visible'));
    return;
  }

  const observer = new IntersectionObserver((entries, currentObserver) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      currentObserver.unobserve(entry.target);
    });
  }, { threshold: 0.12 });

  revealItems.forEach((item) => observer.observe(item));
})();
