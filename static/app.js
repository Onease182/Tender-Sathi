document.addEventListener('DOMContentLoaded', () => {
  if (window.__draftFields) {
    Object.entries(window.__draftFields).forEach(([name, value]) => {
      const input = document.querySelector(`[name="${CSS.escape(name)}"]`);
      if (input) input.value = value;
    });
  }
  document.querySelectorAll('.financial-form').forEach(form => {
    const list = form.querySelector('.jv-list');
    if (!list) return;
    const add = document.createElement('button');
    add.type = 'button'; add.className = 'button ghost small'; add.textContent = 'Add another JV entry';
    add.addEventListener('click', () => {
      const row = list.querySelector('.jv-row').cloneNode(true);
      row.querySelectorAll('input').forEach(input => input.value = '');
      list.appendChild(row);
    });
    list.after(add);
  });
  document.querySelectorAll('.selection-row input[type="checkbox"]').forEach(input => {
    input.addEventListener('change', () => {
      const row = input.closest('.selection-row');
      if (row) row.classList.toggle('selected', input.checked);
    });
  });
});
