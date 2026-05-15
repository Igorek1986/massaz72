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
