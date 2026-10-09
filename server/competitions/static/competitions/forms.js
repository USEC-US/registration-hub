// Progressive enhancement: the same forms remain usable without JavaScript.
document.querySelectorAll('.cw-form').forEach((form) => {
  const outcome = form.querySelector('[name="outcome"]');
  const randomize = form.querySelector('[name="randomize"]');
  const format = form.querySelector('[name="format"]');
  const allocation = form.querySelector('[name="allocation"]');
  const method = form.querySelector('[name="method"]');
  const specs = form.querySelector('[name="group_specs"]');
  function update() {
    form.querySelectorAll('[data-field-name]').forEach((row) => {
      const name = row.dataset.fieldName;
      const hide = (name === 'winner_position' && outcome && outcome.value !== 'FORFEIT') ||
        (name.startsWith('seed_') && randomize && randomize.checked) ||
        (format && ['series_mode', 'meetings', 'win_points', 'draw_points', 'loss_points'].concat(['tiebreak_1', 'tiebreak_2', 'tiebreak_3', 'tiebreak_4']).includes(name) && format.value !== 'ROUND_ROBIN') ||
        (format && name === 'grand_final_policy' && format.value !== 'DOUBLE_ELIMINATION') ||
        (allocation && name.startsWith('group_') && name !== 'group_specs' && allocation.value !== 'MANUAL') ||
        (method && name.startsWith('order_') && method.value !== 'MANUAL') ||
        (method && name === 'series_length' && method.value !== 'EXTRA_MATCHES');
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
  format?.addEventListener('change', update);
  allocation?.addEventListener('change', update);
  method?.addEventListener('change', update);
  specs?.addEventListener('input', () => {
    const names = specs.value.split('\n').filter((line) => line.trim()).map((line) => line.split('|')[0].trim());
    form.querySelectorAll('select[name^="group_"]').forEach((select) => {
      const selected = select.value;
      select.replaceChildren(...names.map((name, index) => new Option(name, String(index + 1))));
      select.value = names[Number(selected) - 1] ? selected : '1';
    });
  });
  update();
});
