const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const scene = document.querySelector('.hero-art');

if (scene) {
  function illuminate(event) {
    if (reduced.matches) return;
    const bounds = scene.getBoundingClientRect();
    scene.style.setProperty('--x', ((event.clientX - bounds.left) / bounds.width * 100) + '%');
    scene.style.setProperty('--y', ((event.clientY - bounds.top) / bounds.height * 100) + '%');
    scene.classList.add('lit');
  }
  scene.addEventListener('pointermove', illuminate, { passive: true });
  scene.addEventListener('pointerdown', illuminate, { passive: true });
  for (const type of ['pointerleave', 'pointerup', 'pointercancel']) {
    scene.addEventListener(type, () => scene.classList.remove('lit'));
  }
}

if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('entered');
      const image = entry.target.querySelector('img[src$="massage-placeholder.svg"]');
      if (image && !reduced.matches) image.src = 'assets/lotus-bloom.svg';
      observer.unobserve(entry.target);
    }
  }, { threshold: 0.12 });
  document.querySelectorAll('.card').forEach(card => observer.observe(card));
}
