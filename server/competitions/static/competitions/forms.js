// Progressive enhancement: the same forms remain usable without JavaScript.
document.querySelectorAll('.cw-form').forEach((form) => {
  const outcome = form.querySelector('[name="outcome"]');
  const randomize = form.querySelector('[name="randomize"]');
  function update() {
    form.querySelectorAll('[data-field-name]').forEach((row) => {
      const name = row.dataset.fieldName;
      const hide = (name === 'winner_position' && outcome && outcome.value !== 'FORFEIT') ||
        (name.startsWith('seed_') && randomize && randomize.checked);
      row.hidden = Boolean(hide);
      row.querySelectorAll('input, select').forEach((input) => { input.disabled = Boolean(hide); });
    });
    if (outcome) {
      form.querySelectorAll('[name="side_one_score"], [name="side_two_score"]').forEach((input) => {
        input.required = outcome.value === 'PLAYED';
      });
    }
  }
  outcome?.addEventListener('change', update);
  randomize?.addEventListener('change', update);
  update();
});
