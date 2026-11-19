(function () {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: '0px 0px -30px 0px' }
  );

  document.querySelectorAll('.service-card').forEach((card, i) => {
    card.style.transitionDelay = i % 3 * 0.1 + 's';
    observer.observe(card);
  });
})();

(function () {
  if (!('IntersectionObserver' in window)) return;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const pending = new WeakMap();
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      const lotus = entry.target;
      clearTimeout(pending.get(lotus));
      if (entry.intersectionRatio < 0.65 || reducedMotion.matches) continue;

      pending.set(lotus, setTimeout(() => {
        lotus.classList.add('is-blooming');
        observer.unobserve(lotus);
      }, 180));
    }
  }, { threshold: 0.65 });

  document.querySelectorAll('.site-redesign .service-lotus').forEach(lotus => observer.observe(lotus));
})();
