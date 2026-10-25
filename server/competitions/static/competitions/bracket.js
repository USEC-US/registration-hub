document.querySelectorAll('.cw-bracket').forEach((bracket) => {
  const namespace = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(namespace, 'svg');
  svg.setAttribute('class', 'cw-bracket-lines');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  bracket.prepend(svg);

  const matches = new Map(
    Array.from(bracket.querySelectorAll('[data-match-id]'), (match) => [
      match.dataset.matchId,
      match,
    ]),
  );
  const routes = Array.from(
    bracket.querySelectorAll('[data-source-match]'),
  ).flatMap((slot) => {
    const source = matches.get(slot.dataset.sourceMatch);
    if (!source) return [];
    const target = slot.closest('[data-match-id]');
    const sourceSection = source.closest('[data-section]');
    const targetSection = target.closest('[data-section]');
    const path = document.createElementNS(namespace, 'path');
    path.dataset.source = source.dataset.matchId;
    path.dataset.match = target.dataset.matchId;
    path.dataset.position = slot.dataset.position;
    path.dataset.outcome = slot.dataset.sourceOutcome;
    svg.append(path);
    return [{ source, target, slot, sourceSection, targetSection, path }];
  });
  const drops = routes.filter(
    (route) =>
      route.sourceSection.dataset.section === 'UPPER' &&
      route.targetSection.dataset.section === 'LOWER',
  );

  function draw() {
    const origin = bracket.getBoundingClientRect();
    const gap = parseFloat(getComputedStyle(bracket).columnGap);
    svg.setAttribute('width', origin.width);
    svg.setAttribute('height', origin.height);
    svg.setAttribute('viewBox', `0 0 ${origin.width} ${origin.height}`);
    routes.forEach(
      ({ source, target, slot, sourceSection, targetSection, path }) => {
        const sourceBox = source.getBoundingClientRect();
        const sourceSlots = source
          .querySelector('.cw-slots')
          .getBoundingClientRect();
        const targetBox = target.getBoundingClientRect();
        const slotBox = slot.getBoundingClientRect();
        const startX = sourceBox.right - origin.left;
        const startY =
          sourceSlots.top +
          sourceSlots.height / 2 -
          origin.top +
          (path.dataset.outcome === 'LOSER' ? 6 : -6);
        const endX = targetBox.left - origin.left;
        const endY = slotBox.top + slotBox.height / 2 - origin.top;
        const drop = drops.findIndex((route) => route.path === path);
        if (drop !== -1) {
          // Loser routes cross the gap between brackets, outside cards and headings.
          const lane = (drop + 1) / (drops.length + 1);
          const upperBottom =
            sourceSection.getBoundingClientRect().bottom - origin.top;
          const lowerTop =
            targetSection.getBoundingClientRect().top - origin.top;
          const bridgeY = upperBottom + (lowerTop - upperBottom) * lane;
          const exitX = startX + gap * lane;
          const entryX = endX - gap * lane;
          path.setAttribute(
            'd',
            `M ${startX} ${startY} H ${exitX} V ${bridgeY} H ${entryX} V ${endY} H ${endX}`,
          );
        } else {
          const turnX =
            endX - gap * (path.dataset.outcome === 'LOSER' ? 0.7 : 0.3);
          path.setAttribute(
            'd',
            `M ${startX} ${startY} H ${turnX} V ${endY} H ${endX}`,
          );
        }
      },
    );
  }

  let frame;
  const observer = new ResizeObserver(() => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(draw);
  });
  observer.observe(bracket);
  bracket
    .querySelectorAll('.cw-match, .cw-round-heading')
    .forEach((element) => observer.observe(element));
});
