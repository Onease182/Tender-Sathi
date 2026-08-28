document.addEventListener('DOMContentLoaded', () => {
  const formatDateInput = input => {
    const digits = input.value.replace(/\D/g, '').slice(0, 8);
    const parts = [];
    if (digits.length > 0) parts.push(digits.slice(0, 4));
    if (digits.length > 4) parts.push(digits.slice(4, 6));
    if (digits.length > 6) parts.push(digits.slice(6, 8));
    input.value = parts.join('-');
    input.setCustomValidity('');
  };
  const validateDateInput = input => {
    const value = input.value.trim();
    if (!value) { input.setCustomValidity(''); return true; }
    const validShape = /^\d{4}-(?:0[1-9]|1[0-2])-\d{2}$/.test(value);
    input.setCustomValidity(validShape ? '' : 'Use YYYY-MM-DD format, for example 2081-01-01.');
    return validShape;
  };
  document.querySelectorAll('[name="award_date"], [name="completion_date"], [name="item_from"], [name="item_till"]').forEach(input => {
    input.inputMode = 'numeric';
    input.maxLength = 10;
    input.placeholder = 'YYYY-MM-DD';
    input.addEventListener('input', () => formatDateInput(input));
    input.addEventListener('blur', () => validateDateInput(input));
    input.form?.addEventListener('submit', event => {
      if (!validateDateInput(input)) event.preventDefault();
    });
  });

  document.querySelectorAll('form[method="post"]').forEach(form => {
    if (window.__csrfToken && !form.querySelector('[name="csrf_token"]')) {
      const token = document.createElement('input');
      token.type = 'hidden'; token.name = 'csrf_token'; token.value = window.__csrfToken;
      form.prepend(token);
    }
  });

  document.querySelectorAll('.password-toggle').forEach(button => {
    button.addEventListener('click', () => {
      const input = button.parentElement.querySelector('input[type="password"], input[type="text"]');
      if (!input) return;
      const visible = input.type === 'text';
      input.type = visible ? 'password' : 'text';
      button.textContent = visible ? 'Show' : 'Hide';
      button.setAttribute('aria-label', visible ? 'Show password' : 'Hide password');
    });
  });

  if (window.__draftFields) {
    Object.entries(window.__draftFields).forEach(([name, value]) => {
      const input = document.querySelector(`[name="${CSS.escape(name)}"]`);
      if (!input) return;
      if (input.type === 'checkbox') input.checked = value === 'on' || value === 'true';
      else input.value = value;
      input.dispatchEvent(new Event('change'));
    });
  }

  document.querySelectorAll('.item-section').forEach(section => {
    const list = section.querySelector('.item-list');
    const add = section.querySelector('.add-item');
    if (!list || !add) return;
    add.addEventListener('click', () => {
      const row = list.querySelector('.item-row')?.cloneNode(true);
      if (!row) return;
      row.querySelectorAll('input').forEach(input => { input.value = ''; });
      list.appendChild(row);
    });
    list.addEventListener('click', event => {
      if (!event.target.classList.contains('remove-item')) return;
      const rows = list.querySelectorAll('.item-row');
      if (rows.length > 1) event.target.closest('.item-row').remove();
    });
    list.addEventListener('change', event => {
      const input = event.target;
      if (!input.matches('[name="item_from"], [name="item_till"]') || !input.value.trim()) return;
      const value = input.value.trim();
      const year = Number(value.split(/[-/.]/)[0]);
      if (year >= 1900 && year <= 2050) {
        input.title = 'AD input is accepted and will be converted to BS when saved.';
        input.classList.add('date-ad-detected');
      } else {
        input.title = 'BS date detected.';
        input.classList.remove('date-ad-detected');
      }
    });
  });

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
    input.addEventListener('change', () => input.closest('.selection-row')?.classList.toggle('selected', input.checked));
  });
  document.querySelectorAll('.confirm-action').forEach(button => {
    button.addEventListener('click', event => {
      if (!window.confirm('Are you sure you want to delete this item?')) event.preventDefault();
    });
  });

  const bidForm = document.querySelector('.bid-form');
  if (bidForm) {
    const percentages = ['L_PER', 'F_PER', 'S_PER'].map(name => bidForm.elements[name]);
    const validate = () => {
      const total = percentages.reduce((sum, input) => sum + (parseFloat(input?.value) || 0), 0);
      percentages.forEach(input => input?.setCustomValidity(total > 0 && Math.abs(total - 100) > 0.01 ? `Partner shares total ${total.toFixed(2)}%; they must total 100%.` : ''));
    };
    percentages.forEach(input => input?.addEventListener('input', validate));
    bidForm.addEventListener('submit', event => { validate(); if (!event.defaultPrevented && event.submitter?.formAction?.includes('/generate/bid') && !window.confirm(`Review bid before generating?\n\nProject: ${bidForm.elements.PROJECT_NAME?.value || '—'}\nLead partner: ${bidForm.elements.LEAD_PARTNER_NAME?.value || '—'}`)) event.preventDefault(); });
  }

  document.querySelector('.profile-loader')?.addEventListener('change', event => {
    const option = event.target.selectedOptions[0];
    if (!option?.dataset.role) return;
    const prefix = option.dataset.role === 'lead' ? 'LEAD' : option.dataset.role === 'first' ? 'FIRST' : 'SECOND';
    const fields = {name: `${prefix}_PARTNER_NAME`, short: `${prefix}_PARTNER_SHORT`, address: prefix === 'FIRST' ? 'FIRST_ADDRESS' : prefix === 'SECOND' ? 'SECOND_ADDRESS' : 'LEAD_ADDRESS', ceo: `${prefix}_PARTNER_CEO`, md1: `${prefix}_PARTNER_MD1`, md2: `${prefix}_PARTNER_MD2`};
    Object.entries(fields).forEach(([key, name]) => {
      const input = document.querySelector(`[name="${name}"]`);
      if (input) input.value = option.dataset[key] || '';
    });
  });

  let dirty = false;
  document.querySelector('.bid-form')?.addEventListener('input', () => { dirty = true; });
  document.querySelectorAll('a[href*="draft_id"]').forEach(link => link.addEventListener('click', event => {
    if (dirty && !window.confirm('Open another draft and discard unsaved edits?')) event.preventDefault();
  }));
});
