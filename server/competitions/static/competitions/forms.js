// Progressive enhancement: the same forms remain usable without JavaScript.
document.querySelectorAll('.cw-form').forEach((form) => {
  const outcome = form.querySelector('[name="outcome"]');
  const randomize = form.querySelector('[name="randomize"]');
  const format = form.querySelector('[name="format"]');
  const allocation = form.querySelector('[name="allocation"]');
  const method = form.querySelector('[name="method"]');
  const groupPlans = form.querySelector('[data-stage-groups]');
  const groupCount = form.querySelector('[name="group_count"]');
  const groupRows = form.querySelector('[data-group-rows]');
  function checkGroups() {
    if (!groupRows) return;
    let total = 0;
    let qualifiers = 0;
    const names = new Set();
    groupRows.querySelectorAll('.cw-group-plan-row').forEach((row) => {
      const name = row.querySelector('input');
      const size = row.querySelector('select[name^="group_size_"]');
      const quota = row.querySelector('select[name^="group_quota_"]');
      const duplicate = names.has(name.value.trim());
      name.setCustomValidity(duplicate ? 'Use a unique group name.' : '');
      names.add(name.value.trim());
      [...quota.options].forEach((option) => { option.disabled = Number(option.value) > Number(size.value); });
      quota.setCustomValidity(Number(quota.value) > Number(size.value) ? 'The quota cannot exceed group size.' : '');
      total += Number(size.value);
      qualifiers += Number(quota.value);
    });
    const incoming = Number(groupPlans.dataset.incomingCount);
    const error = incoming && total !== incoming ? `Group sizes must total ${incoming}; they total ${total}.` :
      total > 256 ? 'Group sizes cannot total more than 256 entrants.' : '';
    groupCount.setCustomValidity(error);
    form.querySelector('[data-group-summary]').textContent = error || `${total} entrants · ${qualifiers} qualify`;
  }
  function resizeGroups() {
    const count = Number(groupCount.value);
    while (groupRows.children.length > count) groupRows.lastElementChild.remove();
    while (groupRows.children.length < count) {
      const index = groupRows.children.length + 1;
      const row = groupRows.firstElementChild.cloneNode(true);
      row.querySelectorAll('.errorlist').forEach((error) => error.remove());
      row.querySelectorAll('[data-field-name]').forEach((field) => {
        const input = field.querySelector('input, select');
        const part = input.name.split('_')[1];
        input.name = `group_${part}_${index}`;
        input.id = `id_${input.name}`;
        input.removeAttribute('aria-invalid');
        input.removeAttribute('aria-describedby');
        input.value = part === 'name' ? `Group ${index}` : part === 'size' ? '2' : '1';
        field.dataset.fieldName = input.name;
        field.classList.remove('cw-field-invalid');
        const label = field.querySelector('label');
        label.htmlFor = input.id;
        label.textContent = `Group ${index} ${part === 'size' ? 'entrants' : part === 'quota' ? 'qualifiers' : 'name'}:`;
      });
      groupRows.append(row);
    }
    const incoming = Number(groupPlans.dataset.incomingCount);
    if (incoming) groupRows.querySelectorAll('select[name^="group_size_"]').forEach((select, index) => {
      select.value = String(Math.floor(incoming / count) + (index < incoming % count ? 1 : 0));
    });
    update();
  }
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
    form.querySelectorAll('[data-stage-groups], [data-stage-elimination]').forEach((section) => {
      const grouped = format.value === 'ROUND_ROBIN';
      const hide = section.hasAttribute('data-stage-groups') ? !grouped : grouped;
      section.hidden = hide;
      section.querySelectorAll('input, select').forEach((input) => { input.disabled = hide; });
    });
    if (outcome) {
      form.querySelectorAll('[name="side_one_score"], [name="side_two_score"]').forEach((input) => {
        input.required = outcome.value === 'PLAYED';
      });
    }
    checkGroups();
  }
  outcome?.addEventListener('change', update);
  randomize?.addEventListener('change', update);
  format?.addEventListener('change', update);
  allocation?.addEventListener('change', update);
  method?.addEventListener('change', update);
  groupCount?.addEventListener('change', resizeGroups);
  groupRows?.addEventListener('input', checkGroups);
  groupRows?.addEventListener('change', checkGroups);
  update();
});
