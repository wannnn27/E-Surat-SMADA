(() => {
  'use strict';

  const byId = (id) => document.getElementById(id);

  function parseJsonScript(id, fallback) {
    const node = byId(id);
    if (!node) return fallback;
    try {
      return JSON.parse(node.textContent || '');
    } catch (error) {
      console.error('Data konfigurasi tidak valid:', id, error);
      return fallback;
    }
  }

  const jenisSuratData = parseJsonScript('jenisSuratDataJson', {});
  const statsData = parseJsonScript('statsDataJson', {});
  const currentRole = document.documentElement.getAttribute('data-role') || '';
  let csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  const elements = {
    appRoot: document.querySelector('.app-container'),
    form: byId('suratForm'),
    jenisInput: byId('jenisSurat'),
    idInput: byId('id_value'),
    studentIdsInputs: byId('studentIdsInputs'),
    requestIdInput: byId('requestId'),
    searchBox: byId('searchBox'),
    searchResults: byId('searchResults'),
    searchStatus: byId('searchStatus'),
    selectedPerson: byId('selectedPerson'),
    dynamicFields: byId('dynamicFields'),
    fieldsStatus: byId('fieldsStatus'),
    wizardStatus: byId('wizardStatus'),
    wizardHeaderIcon: byId('wizardHeaderIcon'),
    wizardHeaderTitle: byId('wizardHeaderTitle'),
    wizardHeaderBadge: byId('wizardHeaderBadge'),
    previewBtn: byId('previewBtn'),
    btnCancel: byId('btnCancel'),
    previewModal: byId('previewModal'),
    summaryList: byId('summaryList'),
    downloadStatus: byId('downloadStatus'),
    modalDownloadBtn: byId('modalDownloadBtn'),
    modalEditBtn: byId('modalEditBtn'),
    modalCloseBtn: byId('modalCloseBtn'),
    reopenSummaryBtn: byId('reopenSummaryBtn'),
    gridGuru: byId('gridGuru'),
    gridMurid: byId('gridMurid'),
    step2SelectedSurat: byId('step2SelectedSurat'),
    step3SelectedSurat: byId('step3SelectedSurat'),
    step3SelectedPerson: byId('step3SelectedPerson')
  };

  const panels = {
    1: byId('stepPanel1'),
    2: byId('stepPanel2'),
    3: byId('stepPanel3'),
    4: byId('stepPanel4')
  };

  const indicators = [
    byId('stepIndicator1'),
    byId('stepIndicator2'),
    byId('stepIndicator3'),
    byId('stepIndicator4')
  ];

  const modals = {
    guru: byId('modalGuru'),
    murid: byId('modalMurid'),
    templates: byId('modalTemplates'),
    arsip: byId('modalKodeArsip'),
    riwayat: byId('modalRiwayat'),
    summary: byId('previewModal'),
    help: byId('modalHelp')
  };

  const state = {
    phase: 1,
    kategori: 'guru',
    jenis: null,
    person: null,
    persons: [],
    fieldSchema: [],
    fieldsLoaded: false,
    loadingFields: false,
    loadingSummary: false,
    downloading: false,
    summary: null,
    summaryValid: false,
    requestId: null,
    dataVersion: 0,
    activeModal: null,
    archiveTargetInput: null,
    controllers: {},
    timers: {},
    lastFocused: new WeakMap()
  };

  function createElement(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function createIcon(classNames) {
    const icon = document.createElement('i');
    String(classNames || '').split(/\s+/).filter(Boolean).forEach((name) => icon.classList.add(name));
    icon.setAttribute('aria-hidden', 'true');
    return icon;
  }

  function setButtonContent(button, label, iconClass, iconAfter) {
    if (!button) return;
    const content = [];
    if (iconClass && !iconAfter) content.push(createIcon(iconClass));
    content.push(document.createTextNode(label));
    if (iconClass && iconAfter) content.push(createIcon(iconClass));
    button.replaceChildren(...content);
  }

  function setStatus(element, message, type) {
    if (!element) return;
    const text = String(message || '').trim();
    element.textContent = text;
    element.hidden = !text;
    element.classList.remove('is-error', 'is-success', 'is-loading', 'is-info');
    if (text) element.classList.add('is-' + (type || 'info'));
    element.setAttribute('role', type === 'error' ? 'alert' : 'status');
  }

  function currentInfo() {
    return state.jenis ? jenisSuratData[state.jenis] || null : null;
  }

  function maxPeople() {
    const info = currentInfo();
    return Math.max(1, Number(info && info.max_people) || 1);
  }

  function isMultiPersonSelection() {
    return maxPeople() > 1;
  }

  function syncPersonInputs() {
    const people = state.persons.length ? state.persons : (state.person ? [state.person] : []);
    state.person = people[0] || null;
    elements.idInput.value = state.person ? personId(state.person, state.kategori) : '';
    if (!elements.studentIdsInputs) return;
    elements.studentIdsInputs.replaceChildren();
    if (!isMultiPersonSelection()) return;
    people.forEach((person) => {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = 'student_ids';
      input.value = personId(person, 'murid');
      elements.studentIdsInputs.append(input);
    });
  }

  function categoryLabel(kategori) {
    return kategori === 'murid' ? 'Siswa / Murid' : 'Guru / Staff';
  }

  function categoryDatabaseLabel(kategori) {
    return kategori === 'murid' ? 'Database Murid' : 'Database Guru';
  }

  function personId(person, kategori) {
    if (!person) return '';
    if (kategori === 'murid') return String(person.nis || person.id || '');
    return String(person.nip || person.id || '');
  }

  function personName(person) {
    return person && person.nama ? String(person.nama) : '';
  }

  function requestController(key) {
    if (state.controllers[key]) state.controllers[key].abort();
    const controller = new AbortController();
    state.controllers[key] = controller;
    return controller;
  }

  function releaseController(key, controller) {
    if (state.controllers[key] === controller) delete state.controllers[key];
  }

  function abortRequest(key) {
    if (state.controllers[key]) {
      state.controllers[key].abort();
      delete state.controllers[key];
    }
  }

  function abortAllRequests() {
    Object.keys(state.controllers).forEach(abortRequest);
  }

  function clearTimer(key) {
    if (state.timers[key]) {
      window.clearTimeout(state.timers[key]);
      delete state.timers[key];
    }
  }

  async function responseError(response) {
    const fallback = 'Permintaan gagal (' + response.status + '). Silakan coba lagi.';
    try {
      const type = response.headers.get('Content-Type') || '';
      if (type.includes('application/json')) {
        const payload = await response.json();
        const error = new Error(payload.error || payload.message || fallback);
        error.status = response.status;
        error.fieldErrors = payload.field_errors || {};
        return error;
      }
      const text = (await response.text()).trim();
      const error = new Error(text || fallback);
      error.status = response.status;
      return error;
    } catch (error) {
      if (error instanceof Error && error.status) return error;
      const fallbackError = new Error(fallback);
      fallbackError.status = response.status;
      return fallbackError;
    }
  }

  function applyCsrfToken(token) {
    csrfToken = String(token || '');
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) meta.content = csrfToken;
    document.querySelectorAll('input[name="_csrf_token"], input[name="csrf_token"]').forEach((input) => {
      input.value = csrfToken;
    });
  }

  function prepareCsrfRequest(options) {
    const prepared = Object.assign({}, options || {});
    const method = String(prepared.method || 'GET').toUpperCase();
    if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) return prepared;

    const headers = new Headers(prepared.headers || {});
    if (csrfToken) headers.set('X-CSRFToken', csrfToken);
    prepared.headers = headers;

    if (prepared.body instanceof FormData && csrfToken) {
      if (prepared.body.has('_csrf_token')) prepared.body.set('_csrf_token', csrfToken);
      prepared.body.set('csrf_token', csrfToken);
    }
    return prepared;
  }

  async function isCsrfFailure(response) {
    if (response.status !== 403) return false;
    try {
      const payload = await response.clone().json();
      return payload && (
        payload.code === 'csrf_invalid' ||
        payload.error === 'Token CSRF tidak valid atau kedaluwarsa'
      );
    } catch (_error) {
      return false;
    }
  }

  async function refreshCsrfToken(signal) {
    const response = await fetch('/api/csrf', {
      method: 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
      signal
    });
    if (!response.ok) throw await responseError(response);
    const payload = await response.json();
    if (!payload || !payload.csrf_token) {
      throw new Error('Sesi tidak dapat diperbarui. Muat ulang halaman atau login kembali.');
    }
    applyCsrfToken(payload.csrf_token);
  }

  async function fetchWithCsrfRetry(url, options) {
    let prepared = prepareCsrfRequest(options);
    let response = await fetch(url, prepared);
    if (await isCsrfFailure(response)) {
      await refreshCsrfToken(prepared.signal);
      prepared = prepareCsrfRequest(options);
      response = await fetch(url, prepared);
    }
    return response;
  }

  async function fetchJson(url, options) {
    const response = await fetchWithCsrfRetry(url, options || {});
    if (!response.ok) throw await responseError(response);
    const payload = await response.json();
    if (payload && payload.error) throw new Error(payload.error);
    return payload;
  }

  function csrfHeaders() {
    return csrfToken ? { 'X-CSRFToken': csrfToken } : {};
  }

  function normaliseList(payload) {
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.items)) return payload.items;
    if (payload && Array.isArray(payload.results)) return payload.results;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
  }

  function readStat(keys) {
    for (const key of keys) {
      if (statsData && statsData[key] !== undefined && statsData[key] !== null) {
        const value = Number(statsData[key]);
        if (Number.isFinite(value)) return value;
      }
    }
    return null;
  }

  function updateStats() {
    const values = {
      statGuruCount: readStat(['guru', 'guru_count', 'jumlah_guru', 'guru_staff']),
      statMuridCount: readStat(['murid', 'murid_count', 'jumlah_murid', 'siswa']),
      statTemplateCount: readStat(['template', 'templates', 'template_count', 'jumlah_template']),
      statArsipCount: readStat(['kode_arsip', 'arsip', 'archive_count', 'jumlah_kode_arsip'])
    };
    if (values.statTemplateCount === null) values.statTemplateCount = Object.keys(jenisSuratData).length;
    Object.entries(values).forEach(([id, value]) => {
      const node = byId(id);
      if (node) node.textContent = value === null ? '—' : value.toLocaleString('id-ID');
    });
    const mobileSub = byId('mobileSelectedSuratSub');
    if (mobileSub) {
      mobileSub.textContent = 'Ketuk untuk memilih dari ' + values.statTemplateCount + ' template resmi';
    }
  }

  function updateTemplateCards() {
    document.querySelectorAll('.surat-select-card[data-key]').forEach((card) => {
      const selected = card.getAttribute('data-key') === state.jenis;
      card.classList.toggle('active', selected);
      if (card.matches('button')) card.setAttribute('aria-pressed', String(selected));
    });
  }

  function clearSearchResults() {
    elements.searchResults.replaceChildren();
    elements.searchResults.hidden = true;
    elements.searchBox.setAttribute('aria-expanded', 'false');
  }

  function clearSelectedPersonDisplay() {
    elements.selectedPerson.replaceChildren();
    elements.selectedPerson.hidden = true;
  }

  function invalidateSummary() {
    state.dataVersion += 1;
    state.summary = null;
    state.summaryValid = false;
    state.requestId = null;
    elements.requestIdInput.value = '';
    abortRequest('summary');
    abortRequest('download');
    setStatus(elements.downloadStatus, '', 'info');
    updateStepAvailability();
  }

  function clearPerson(options) {
    const settings = Object.assign({ clearSearch: true, clearFields: true }, options || {});
    clearTimer('personSearch');
    abortRequest('search');
    abortRequest('fields');
    state.person = null;
    state.persons = [];
    state.loadingFields = false;
    elements.dynamicFields.setAttribute('aria-busy', 'false');
    syncPersonInputs();
    clearSelectedPersonDisplay();
    if (settings.clearSearch) elements.searchBox.value = '';
    clearSearchResults();
    if (settings.clearFields) {
      state.fieldSchema = [];
      state.fieldsLoaded = false;
      elements.dynamicFields.replaceChildren();
      setStatus(elements.fieldsStatus, '', 'info');
    }
    invalidateSummary();
  }

  function clearTemplateSelection() {
    state.jenis = null;
    elements.jenisInput.value = '';
    clearPerson({ clearSearch: true, clearFields: true });
    updateTemplateCards();
  }

  function activateCategory(kategori, options) {
    const settings = Object.assign({ resetMismatch: true }, options || {});
    if (kategori !== 'guru' && kategori !== 'murid') return;
    const info = currentInfo();
    if (settings.resetMismatch && info && info.kategori !== kategori) clearTemplateSelection();
    state.kategori = kategori;

    document.querySelectorAll('.category-tab').forEach((tab) => {
      const active = tab.getAttribute('data-kategori') === kategori;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    elements.gridGuru.hidden = kategori !== 'guru';
    elements.gridMurid.hidden = kategori !== 'murid';

    if (state.phase === 1) {
      elements.wizardHeaderBadge.textContent = 'Kategori: ' + categoryLabel(kategori);
      elements.wizardHeaderBadge.className = kategori === 'murid'
        ? 'header-pill-badge purple'
        : 'header-pill-badge';
    }
  }

  function selectJenisSurat(key, sourceModal) {
    const info = jenisSuratData[key];
    if (!info) {
      setStatus(elements.wizardStatus, 'Template surat tidak valid atau sudah tidak tersedia.', 'error');
      return;
    }

    abortRequest('search');
    clearPerson({ clearSearch: true, clearFields: true });
    state.jenis = key;
    elements.jenisInput.value = key;
    activateCategory(info.kategori, { resetMismatch: false });
    updateTemplateCards();

    const mobileTitle = byId('mobileSelectedSuratTitle');
    const mobileSub = byId('mobileSelectedSuratSub');
    if (mobileTitle) mobileTitle.textContent = info.label || key;
    if (mobileSub) mobileSub.textContent = info.deskripsi || 'Template resmi SMADA';

    elements.searchBox.placeholder = info.kategori === 'murid'
      ? 'Ketik minimal 2 karakter nama, NIS, atau NISN siswa...'
      : 'Ketik minimal 2 karakter nama atau NIP guru/staff...';

    if (sourceModal) closeModal(modals.templates, { restoreFocus: false });
    setStatus(elements.wizardStatus, 'Template “' + (info.label || key) + '” dipilih. Cari personel yang sesuai.', 'success');
    setWizardStep(2);
  }

  function renderSelectedPerson() {
    if (!state.person) {
      clearSelectedPersonDisplay();
      return;
    }
    const people = state.persons.length ? state.persons : [state.person];
    const rows = people.map((person, index) => {
      const row = createElement('div', 'selected-person-row');
      const wrapper = createElement('div');
      const name = createElement('strong');
      name.append(createIcon('fa-solid fa-circle-check'), document.createTextNode(' ' + personName(person)));
      const detail = createElement('small');
      const idLabel = state.kategori === 'murid' ? 'NIS' : 'NIP';
      const sub = state.kategori === 'murid'
        ? 'Kelas ' + (person.kelas || '-')
        : (person.jabatan || '-');
      detail.textContent = idLabel + ': ' + personId(person, state.kategori) + ' - ' + sub;
      wrapper.append(name, document.createElement('br'), detail);
      if (isMultiPersonSelection()) {
        const remove = createElement('button', 'remove-person-btn', 'Hapus');
        remove.type = 'button';
        remove.setAttribute('aria-label', 'Hapus ' + personName(person) + ' dari surat');
        remove.addEventListener('click', () => removeSelectedPerson(index));
        row.append(wrapper, remove);
      } else {
        row.append(wrapper, createElement('span', 'header-pill-badge', 'Terpilih'));
      }
      return row;
    });
    elements.selectedPerson.replaceChildren(...rows);
    elements.selectedPerson.classList.toggle('multi-person', isMultiPersonSelection());
    elements.selectedPerson.hidden = false;
  }

  function removeSelectedPerson(index) {
    state.persons.splice(index, 1);
    state.person = state.persons[0] || null;
    syncPersonInputs();
    renderSelectedPerson();
    invalidateSummary();
    if (!state.person) {
      state.fieldsLoaded = false;
      state.fieldSchema = [];
      elements.dynamicFields.replaceChildren();
    }
    setStatus(
      elements.searchStatus,
      state.persons.length
        ? state.persons.length + ' dari ' + maxPeople() + ' siswa dipilih. Cari siswa lain atau lanjutkan.'
        : 'Pilih minimal satu siswa dari database resmi.',
      state.persons.length ? 'success' : 'info'
    );
    updateStepAvailability();
  }

  function renderSearchResults(records, kategori) {
    clearSearchResults();
    if (!records.length) {
      setStatus(elements.searchStatus, 'Data tidak ditemukan. Periksa ejaan atau nomor identitas.', 'info');
      return;
    }

    const fragment = document.createDocumentFragment();
    records.forEach((person, index) => {
      const id = personId(person, kategori);
      if (!id) return;
      if (isMultiPersonSelection() && state.persons.some((item) => personId(item, kategori) === id)) return;
      const button = createElement('button', 'result-item');
      button.type = 'button';
      button.setAttribute('role', 'option');
      button.setAttribute('aria-selected', 'false');

      const text = createElement('span', 'result-main');
      text.append(
        createElement('strong', 'result-name', personName(person) || 'Tanpa nama'),
        createElement(
          'small',
          'result-subtitle',
          kategori === 'murid'
            ? 'NIS: ' + id + ' — Kelas ' + (person.kelas || '-')
            : 'NIP: ' + id + ' — ' + (person.jabatan || '-')
        )
      );
      const badge = createElement(
        'span',
        kategori === 'murid' ? 'header-pill-badge purple' : 'header-pill-badge',
        kategori === 'murid' ? 'Kelas ' + (person.kelas || '-') : 'Guru/Staff'
      );
      button.append(text, badge);
      button.addEventListener('click', () => {
        void selectPersonRecord(person, kategori);
      });
      button.addEventListener('keydown', (event) => {
        const options = Array.from(elements.searchResults.querySelectorAll('[role="option"]'));
        const current = options.indexOf(button);
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          (options[current + 1] || options[0]).focus();
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          (options[current - 1] || elements.searchBox).focus();
        } else if (event.key === 'Escape') {
          event.preventDefault();
          clearSearchResults();
          elements.searchBox.focus();
        }
      });
      if (index === 0) button.dataset.firstResult = 'true';
      fragment.append(button);
    });

    elements.searchResults.append(fragment);
    elements.searchResults.hidden = elements.searchResults.childElementCount === 0;
    elements.searchBox.setAttribute('aria-expanded', String(!elements.searchResults.hidden));
    setStatus(
      elements.searchStatus,
      elements.searchResults.childElementCount + ' data ditemukan. Pilih hasil resmi.',
      'success'
    );
  }

  async function searchPersonnel(query, kategori) {
    const controller = requestController('search');
    const requestedQuery = query;
    const requestedCategory = kategori;
    setStatus(elements.searchStatus, 'Mencari data personel…', 'loading');
    try {
      const payload = await fetchJson(
        '/api/search?q=' + encodeURIComponent(query) + '&kategori=' + encodeURIComponent(kategori),
        { signal: controller.signal }
      );
      if (
        elements.searchBox.value.trim() !== requestedQuery ||
        state.kategori !== requestedCategory ||
        controller.signal.aborted
      ) return;
      renderSearchResults(normaliseList(payload), requestedCategory);
    } catch (error) {
      if (error.name !== 'AbortError') {
        clearSearchResults();
        setStatus(elements.searchStatus, error.message || 'Pencarian gagal. Silakan coba lagi.', 'error');
      }
    } finally {
      releaseController('search', controller);
    }
  }

  function handleSearchInput() {
    clearTimer('personSearch');
    abortRequest('search');
    if (state.person && !isMultiPersonSelection()) clearPerson({ clearSearch: false, clearFields: true });
    clearSearchResults();
    invalidateSummary();

    const query = elements.searchBox.value.trim();
    if (query.length < 2) {
      setStatus(elements.searchStatus, 'Ketik minimal 2 karakter, lalu pilih data dari hasil resmi.', 'info');
      updateStepAvailability();
      return;
    }

    setStatus(elements.searchStatus, 'Menunggu pencarian…', 'loading');
    const kategori = state.kategori;
    state.timers.personSearch = window.setTimeout(() => {
      delete state.timers.personSearch;
      void searchPersonnel(query, kategori);
    }, 250);
  }

  function fieldIsRequired(field) {
    if (field.required === false) return false;
    if (field.name === 'nomor_surat_custom') return false;
    return true;
  }

  function fieldOption(option) {
    if (option && typeof option === 'object') {
      return {
        value: String(option.value ?? option.kode ?? option.id ?? ''),
        label: String(option.label ?? option.keterangan ?? option.value ?? option.kode ?? '')
      };
    }
    return { value: String(option ?? ''), label: String(option ?? '') };
  }

  function isLongTextField(field) {
    if (field.type === 'textarea') return true;
    return /keperluan|alasan|alamat|uraian|keterangan|dasar|catatan/i.test(String(field.name || ''));
  }

  function fieldHint(field) {
    if (field.name === 'nomor_surat_custom') {
      return 'Opsional. Kosongkan agar sistem mengalokasikan nomor surat resmi saat dokumen dibuat.';
    }
    if (field.type === 'archive') {
      return 'Pilih kode klasifikasi yang sesuai untuk mengurangi kesalahan penomoran.';
    }
    if (field.type === 'date') {
      return 'Gunakan tanggal yang tercantum pada surat.';
    }
    return field.help || field.hint || '';
  }

  function createFieldControl(field, id, required) {
    const type = String(field.type || 'text').toLowerCase();
    let control;

    if (type === 'select') {
      control = document.createElement('select');
      const placeholder = createElement('option', '', 'Pilih ' + String(field.label || 'opsi'));
      placeholder.value = '';
      placeholder.disabled = required;
      placeholder.selected = !field.default;
      control.append(placeholder);
      (Array.isArray(field.options) ? field.options : []).forEach((rawOption) => {
        const item = fieldOption(rawOption);
        const option = createElement('option', '', item.label);
        option.value = item.value;
        option.selected = String(field.default ?? '') === item.value;
        control.append(option);
      });
    } else if (isLongTextField(field)) {
      control = document.createElement('textarea');
      control.rows = Number(field.rows) || 3;
      control.value = String(field.default ?? '');
    } else {
      control = document.createElement('input');
      control.type = type === 'date' ? 'date' : 'text';
      control.value = String(field.default ?? '');
    }

    control.id = id;
    control.name = String(field.name || '');
    control.className = 'form-control field-input';
    control.dataset.field = String(field.name || '');
    control.required = required;
    control.setAttribute('aria-required', String(required));
    control.autocomplete = 'off';
    if (field.placeholder) control.placeholder = String(field.placeholder);
    if (field.min) control.min = String(field.min);
    if (field.max) control.max = String(field.max);
    if (field.minlength) control.minLength = Number(field.minlength);
    if (field.maxlength) control.maxLength = Number(field.maxlength);
    if (field.pattern && control.tagName === 'INPUT' && control.type === 'text') {
      control.pattern = String(field.pattern);
    }
    return control;
  }

  function validateDateRange() {
    const start = elements.dynamicFields.querySelector('[name="tanggal_mulai"]');
    const end = elements.dynamicFields.querySelector('[name="tanggal_selesai"]');
    if (!end) return true;
    if (!end.hasAttribute('aria-invalid')) end.setCustomValidity('');
    if (start && start.value && end.value && end.value < start.value) {
      end.setCustomValidity('Tanggal selesai tidak boleh lebih awal dari tanggal mulai.');
      return false;
    }
    return true;
  }

  function handleFieldChange(event) {
    if (event && event.currentTarget && typeof event.currentTarget.setCustomValidity === 'function') {
      event.currentTarget.setCustomValidity('');
      event.currentTarget.removeAttribute('aria-invalid');
    }
    validateDateRange();
    invalidateSummary();
    setStatus(elements.wizardStatus, '', 'info');
  }

  function renderFields(fields) {
    elements.dynamicFields.replaceChildren();
    const fragment = document.createDocumentFragment();

    fields.forEach((field, index) => {
      if (!field || !field.name) return;
      const required = fieldIsRequired(field);
      const id = 'field_' + String(field.name).replace(/[^a-zA-Z0-9_-]/g, '_') + '_' + index;
      const group = createElement(
        'div',
        field.name === 'nomor_surat_custom' ? 'form-group form-group-full' : 'form-group'
      );
      const label = createElement('label', 'form-label', String(field.label || field.name));
      label.htmlFor = id;
      if (required) {
        const marker = createElement('span', 'required-marker', ' *');
        marker.setAttribute('aria-hidden', 'true');
        label.append(marker);
      } else {
        label.append(document.createTextNode(' (opsional)'));
      }

      const control = createFieldControl(field, id, required);
      const hintText = fieldHint(field);
      if (hintText) {
        const hint = createElement('small', 'field-hint', hintText);
        hint.id = id + '_hint';
        control.setAttribute('aria-describedby', hint.id);
        group.append(label);

        if (field.type === 'archive') {
          const row = createElement('div', 'archive-field-row');
          const picker = createElement('button', 'btn-field-picker', 'Lihat Kode');
          picker.type = 'button';
          picker.addEventListener('click', () => openKodeArsipDirectory(control));
          row.append(control, picker);
          group.append(row, hint);
        } else {
          group.append(control, hint);
        }
      } else {
        group.append(label, control);
      }

      control.addEventListener('input', handleFieldChange);
      control.addEventListener('change', handleFieldChange);
      control.addEventListener('invalid', () => {
        setStatus(elements.fieldsStatus, 'Periksa kembali field wajib yang ditandai browser.', 'error');
      });
      fragment.append(group);
    });

    elements.dynamicFields.append(fragment);
    validateDateRange();
  }

  async function loadFields() {
    if (!state.jenis || !state.person) return;
    const jenis = state.jenis;
    const selectedId = personId(state.person, state.kategori);
    const controller = requestController('fields');
    state.loadingFields = true;
    state.fieldsLoaded = false;
    elements.dynamicFields.setAttribute('aria-busy', 'true');
    elements.dynamicFields.replaceChildren();
    setStatus(elements.fieldsStatus, 'Memuat formulir detail surat…', 'loading');
    setStatus(elements.wizardStatus, 'Memuat formulir detail surat…', 'loading');
    updateStepAvailability();

    try {
      const payload = await fetchJson('/api/fields/' + encodeURIComponent(jenis), {
        signal: controller.signal
      });
      if (
        controller.signal.aborted ||
        state.jenis !== jenis ||
        !state.person ||
        personId(state.person, state.kategori) !== selectedId
      ) return;

      const fields = (Array.isArray(payload.fields) ? payload.fields : []).filter(
        (field) => currentRole === 'admin' || field.name !== 'nomor_surat_custom'
      );
      if (!fields.length) throw new Error('Konfigurasi field untuk template ini belum tersedia.');
      state.fieldSchema = fields;
      renderFields(fields);
      state.fieldsLoaded = true;
      state.loadingFields = false;
      setStatus(elements.fieldsStatus, 'Formulir berhasil dimuat. Field bertanda * wajib diisi.', 'success');
      setStatus(elements.wizardStatus, 'Formulir detail siap diisi.', 'success');
      setWizardStep(3);
    } catch (error) {
      if (error.name !== 'AbortError') {
        state.fieldsLoaded = false;
        state.loadingFields = false;
        setStatus(
          elements.fieldsStatus,
          error.message || 'Formulir gagal dimuat. Klik tombol lanjut untuk mencoba lagi.',
          'error'
        );
        setStatus(elements.wizardStatus, 'Formulir detail belum dapat dimuat.', 'error');
        setWizardStep(2, { focus: false });
      }
    } finally {
      const isCurrentRequest = state.controllers.fields === controller;
      releaseController('fields', controller);
      if (isCurrentRequest) {
        state.loadingFields = false;
        elements.dynamicFields.setAttribute('aria-busy', 'false');
        updateStepAvailability();
      }
    }
  }

  async function selectPersonRecord(person, kategori) {
    const info = currentInfo();
    if (!info) {
      activateCategory(kategori, { resetMismatch: true });
      setWizardStep(1);
      setStatus(elements.wizardStatus, 'Pilih template surat terlebih dahulu, kemudian pilih personel.', 'error');
      return;
    }
    if (info.kategori !== kategori) {
      clearTemplateSelection();
      activateCategory(kategori, { resetMismatch: false });
      setWizardStep(1);
      setStatus(elements.wizardStatus, 'Kategori personel tidak sesuai dengan template surat.', 'error');
      return;
    }

    const id = personId(person, kategori);
    if (!id) {
      setStatus(elements.searchStatus, 'Data personel tidak memiliki nomor identitas yang valid.', 'error');
      return;
    }

    if (isMultiPersonSelection()) {
      if (state.persons.some((item) => personId(item, kategori) === id)) {
        setStatus(elements.searchStatus, 'Siswa tersebut sudah dipilih.', 'info');
        return;
      }
      if (state.persons.length >= maxPeople()) {
        setStatus(elements.searchStatus, 'Maksimal ' + maxPeople() + ' siswa dalam satu surat dispensasi.', 'error');
        return;
      }
      abortRequest('search');
      state.persons.push(person);
      state.person = state.persons[0];
      state.kategori = kategori;
      syncPersonInputs();
      elements.searchBox.value = '';
      clearSearchResults();
      renderSelectedPerson();
      invalidateSummary();
      setStatus(
        elements.searchStatus,
        state.persons.length + ' dari ' + maxPeople() + ' siswa dipilih. Cari siswa lain atau lanjutkan.',
        'success'
      );
      updateStepAvailability();
      elements.searchBox.focus();
      return;
    }

    abortRequest('search');
    abortRequest('fields');
    state.loadingFields = false;
    state.fieldsLoaded = false;
    state.fieldSchema = [];
    elements.dynamicFields.replaceChildren();
    state.person = person;
    state.persons = [person];
    state.kategori = kategori;
    syncPersonInputs();
    elements.searchBox.value = personName(person);
    clearSearchResults();
    renderSelectedPerson();
    invalidateSummary();
    setStatus(elements.searchStatus, 'Personel dipilih dari database resmi.', 'success');
    await loadFields();
  }

  function stepPrerequisite(step) {
    if (step === 1) return true;
    if (step === 2) return Boolean(state.jenis);
    if (step === 3) return Boolean(state.jenis && state.person && state.fieldsLoaded);
    if (step === 4) return Boolean(state.summaryValid);
    return false;
  }

  function updateStepAvailability() {
    indicators.forEach((indicator, index) => {
      const step = index + 1;
      indicator.disabled = !stepPrerequisite(step);
      indicator.setAttribute('aria-disabled', String(indicator.disabled));
    });

    elements.previewBtn.disabled = state.loadingFields || state.loadingSummary || state.downloading;
    elements.previewBtn.setAttribute('aria-busy', String(state.loadingFields || state.loadingSummary));
    elements.modalDownloadBtn.disabled = state.downloading || !state.summaryValid;
    elements.modalDownloadBtn.setAttribute('aria-busy', String(state.downloading));
    elements.modalEditBtn.disabled = state.downloading;
    elements.modalCloseBtn.disabled = state.downloading;
  }

  function focusStep(step) {
    window.setTimeout(() => {
      if (step === 1) {
        const selected = document.querySelector('.surat-card-grid:not([hidden]) .surat-select-card.active');
        const target = selected || document.querySelector('.category-tab.active');
        if (target) target.focus();
      } else if (step === 2) {
        elements.searchBox.focus();
      } else if (step === 3) {
        const first = elements.dynamicFields.querySelector('input, select, textarea');
        if (first) first.focus();
      } else if (step === 4 && elements.reopenSummaryBtn) {
        elements.reopenSummaryBtn.focus();
      }
    }, 0);
  }

  function setWizardStep(step, options) {
    const settings = Object.assign({ focus: true }, options || {});
    if (!stepPrerequisite(step)) {
      if (step === 2) setStatus(elements.wizardStatus, 'Pilih template surat terlebih dahulu.', 'error');
      if (step === 3) setStatus(elements.wizardStatus, 'Pilih personel dan tunggu formulir selesai dimuat.', 'error');
      if (step === 4) setStatus(elements.wizardStatus, 'Buat Ringkasan Data terlebih dahulu.', 'error');
      return;
    }

    state.phase = step;
    Object.entries(panels).forEach(([number, panel]) => {
      panel.hidden = Number(number) !== step;
    });

    indicators.forEach((indicator, index) => {
      const number = index + 1;
      indicator.classList.toggle('active', number === step);
      indicator.classList.toggle('completed', number < step);
      if (number === step) indicator.setAttribute('aria-current', 'step');
      else indicator.removeAttribute('aria-current');
    });

    const info = currentInfo() || {};
    if (step === 1) {
      elements.wizardHeaderIcon.className = 'fa-solid fa-layer-group';
      elements.wizardHeaderTitle.textContent = 'Langkah 1: Kategori & Jenis Surat';
      elements.wizardHeaderBadge.textContent = 'Kategori: ' + categoryLabel(state.kategori);
      elements.wizardHeaderBadge.className = state.kategori === 'murid'
        ? 'header-pill-badge purple'
        : 'header-pill-badge';
      setButtonContent(elements.btnCancel, 'Batal');
      setButtonContent(elements.previewBtn, 'Lanjut ke Cari Personel', 'fa-solid fa-arrow-right', true);
    } else if (step === 2) {
      elements.step2SelectedSurat.textContent = info.label || state.jenis || '-';
      elements.wizardHeaderIcon.className = 'fa-solid fa-magnifying-glass';
      elements.wizardHeaderTitle.textContent = 'Langkah 2: Pencarian Data Personel';
      elements.wizardHeaderBadge.textContent = categoryDatabaseLabel(state.kategori);
      elements.wizardHeaderBadge.className = 'header-pill-badge purple';
      setButtonContent(elements.btnCancel, 'Kembali', 'fa-solid fa-arrow-left');
      setButtonContent(
        elements.previewBtn,
        state.person && !state.fieldsLoaded ? 'Muat Form Detail' : 'Lanjut ke Isi Detail',
        'fa-solid fa-arrow-right',
        true
      );
    } else if (step === 3) {
      elements.step3SelectedSurat.textContent = info.label || state.jenis || '-';
      elements.step3SelectedPerson.textContent = state.persons.length > 1
        ? state.persons.map(personName).join(', ')
        : (personName(state.person) || '-');
      elements.wizardHeaderIcon.className = 'fa-solid fa-pen-to-square';
      elements.wizardHeaderTitle.textContent = 'Langkah 3: Parameter & Rincian Surat';
      elements.wizardHeaderBadge.textContent = 'Formulir Detail';
      elements.wizardHeaderBadge.className = 'header-pill-badge';
      setButtonContent(elements.btnCancel, 'Kembali', 'fa-solid fa-arrow-left');
      setButtonContent(elements.previewBtn, 'Lanjut ke Ringkasan Data', 'fa-solid fa-arrow-right', true);
    } else {
      elements.wizardHeaderIcon.className = 'fa-solid fa-clipboard-check';
      elements.wizardHeaderTitle.textContent = 'Langkah 4: Ringkasan Data & Unduh';
      elements.wizardHeaderBadge.textContent = 'Siap Diperiksa';
      elements.wizardHeaderBadge.className = 'header-pill-badge';
      setButtonContent(elements.btnCancel, 'Kembali Edit', 'fa-solid fa-arrow-left');
      setButtonContent(elements.previewBtn, 'Buka Ringkasan Data', 'fa-solid fa-clipboard-list');
    }

    updateStepAvailability();
    if (settings.focus) focusStep(step);
  }

  function generateRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
      const random = Math.random() * 16 | 0;
      const value = character === 'x' ? random : (random & 0x3 | 0x8);
      return value.toString(16);
    });
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (Array.isArray(value)) return value.map(displayValue).join(', ');
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  function addSummaryRow(fragment, label, value, key) {
    const row = createElement('div', 'summary-row');
    if (key) row.dataset.summaryKey = key;
    row.append(
      createElement('dt', 'summary-label', label),
      createElement('dd', 'summary-value', displayValue(value))
    );
    fragment.append(row);
  }

  function renderSummary(payload) {
    const info = payload.info || currentInfo() || {};
    const context = payload.context || {};
    const person = payload.person || state.person || {};
    const signer = payload.signer || context.penandatangan || null;
    const fragment = document.createDocumentFragment();
    const used = new Set();

    addSummaryRow(fragment, 'Jenis Surat', info.label || state.jenis || '—', 'jenis_surat');
    addSummaryRow(fragment, 'Kategori', categoryLabel(info.kategori || state.kategori), 'kategori');
    const students = Array.isArray(payload.students) && payload.students.length
      ? payload.students
      : state.persons;
    if (Number(info.max_people) > 1) {
      students.forEach((student, index) => {
        const prefix = 'Siswa ' + (index + 1);
        addSummaryRow(fragment, prefix + ' - Nama', personName(student), 'student_' + index + '_nama');
        addSummaryRow(fragment, prefix + ' - NIS', personId(student, 'murid'), 'student_' + index + '_nis');
        addSummaryRow(fragment, prefix + ' - Kelas', student.kelas, 'student_' + index + '_kelas');
      });
    } else {
      addSummaryRow(fragment, 'Nama Personel', personName(person), 'nama');
      addSummaryRow(
        fragment,
        (info.kategori || state.kategori) === 'murid' ? 'NIS' : 'NIP',
        personId(person, info.kategori || state.kategori),
        'id_personel'
      );
      if ((info.kategori || state.kategori) === 'murid') {
        addSummaryRow(fragment, 'Kelas', person.kelas || context.kelas, 'kelas');
      } else {
        addSummaryRow(fragment, 'Jabatan', person.jabatan || context.jabatan, 'jabatan');
      }
    }

    const numberValue = context.nomor_surat || context.nomor_surat_custom ||
      'Dialokasikan otomatis saat dokumen dibuat';
    addSummaryRow(fragment, 'Nomor Surat', numberValue, 'nomor_surat');
    used.add('nomor_surat_custom');

    const schema = state.fieldSchema.length
      ? state.fieldSchema
      : (Array.isArray(info.fields) ? info.fields : []);
    schema.forEach((field) => {
      if (!field || !field.name || used.has(field.name)) return;
      used.add(field.name);
      addSummaryRow(fragment, field.label || field.name, context[field.name], field.name);
    });

    if (signer && signer.nama) {
      addSummaryRow(fragment, 'Penandatangan', signer.nama, 'penandatangan_nama');
      addSummaryRow(fragment, 'Peran Penandatangan', signer.peran || signer.jabatan, 'penandatangan_peran');
      if (signer.nip) addSummaryRow(fragment, 'NIP Penandatangan', signer.nip, 'penandatangan_nip');
    }

    elements.summaryList.replaceChildren(fragment);
    setStatus(elements.downloadStatus, '', 'info');
  }

  function validateDetails() {
    validateDateRange();
    if (!elements.form.reportValidity()) {
      setStatus(elements.fieldsStatus, 'Lengkapi field wajib dan perbaiki nilai yang tidak valid.', 'error');
      return false;
    }
    if (!state.jenis || !state.person || !state.fieldsLoaded) {
      setStatus(elements.wizardStatus, 'State formulir tidak lengkap. Pilih ulang template dan personel.', 'error');
      return false;
    }
    const info = currentInfo();
    if (!info || info.kategori !== state.kategori) {
      setStatus(elements.wizardStatus, 'Kategori template dan personel tidak cocok.', 'error');
      return false;
    }
    return true;
  }

  function applyFieldErrors(fieldErrors) {
    if (!fieldErrors || typeof fieldErrors !== 'object') return;
    let firstInvalid = null;
    Object.entries(fieldErrors).forEach(([name, message]) => {
      const control = Array.from(elements.form.elements).find((item) => item.name === name);
      if (!control || typeof control.setCustomValidity !== 'function' || control.type === 'hidden') return;
      control.setCustomValidity(String(message || 'Nilai tidak valid.'));
      control.setAttribute('aria-invalid', 'true');
      if (!firstInvalid && !control.hidden) firstInvalid = control;
    });
    if (firstInvalid) {
      firstInvalid.focus();
      firstInvalid.reportValidity();
    }
  }

  async function requestSummary() {
    if (!validateDetails() || state.loadingSummary) return;
    if (state.summaryValid && state.summary) {
      renderSummary(state.summary);
      setWizardStep(4, { focus: false });
      openModal(modals.summary, elements.modalCloseBtn);
      return;
    }

    const version = state.dataVersion;
    const controller = requestController('summary');
    state.loadingSummary = true;
    state.requestId = generateRequestId();
    elements.requestIdInput.value = state.requestId;
    setStatus(elements.wizardStatus, 'Menyusun Ringkasan Data…', 'loading');
    updateStepAvailability();

    try {
      const formData = new FormData(elements.form);
      const payload = await fetchJson('/api/preview_render', {
        method: 'POST',
        body: formData,
        headers: csrfHeaders(),
        signal: controller.signal
      });
      if (controller.signal.aborted || version !== state.dataVersion) return;
      state.summary = payload;
      state.summaryValid = true;
      renderSummary(payload);
      setStatus(elements.wizardStatus, 'Ringkasan siap. Periksa data sebelum mengunduh.', 'success');
      setWizardStep(4, { focus: false });
      openModal(modals.summary, elements.modalCloseBtn);
    } catch (error) {
      if (error.name !== 'AbortError') {
        state.requestId = null;
        elements.requestIdInput.value = '';
        applyFieldErrors(error.fieldErrors);
        setStatus(elements.wizardStatus, error.message || 'Ringkasan gagal dibuat.', 'error');
        setWizardStep(3, { focus: false });
      }
    } finally {
      state.loadingSummary = false;
      releaseController('summary', controller);
      updateStepAvailability();
    }
  }

  function parseFilename(contentDisposition) {
    const value = String(contentDisposition || '');
    const utfMatch = value.match(/filename\*=UTF-8''([^;]+)/i);
    if (utfMatch) {
      try {
        return decodeURIComponent(utfMatch[1].replace(/["']/g, ''));
      } catch (error) {
        return utfMatch[1].replace(/["']/g, '');
      }
    }
    const basicMatch = value.match(/filename="?([^";]+)"?/i);
    return basicMatch ? basicMatch[1] : '';
  }

  function safeFilename(filename) {
    const cleaned = String(filename || '')
      .replace(/[\\/:*?"<>|]+/g, '-')
      .replace(/\s+/g, '_')
      .slice(0, 180);
    return cleaned.toLowerCase().endsWith('.docx') ? cleaned : cleaned + '.docx';
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function downloadDocument() {
    if (state.downloading || !state.summaryValid || !state.requestId) return;
    state.downloading = true;
    const controller = requestController('download');
    setButtonContent(elements.modalDownloadBtn, 'Menyiapkan Dokumen…', 'fa-solid fa-spinner fa-spin');
    setStatus(elements.downloadStatus, 'Membuat dokumen DOCX. Jangan klik ulang atau menutup halaman.', 'loading');
    updateStepAvailability();

    try {
      elements.requestIdInput.value = state.requestId;
      const response = await fetchWithCsrfRetry('/generate', {
        method: 'POST',
        body: new FormData(elements.form),
        headers: Object.assign({}, csrfHeaders(), { 'X-Request-ID': state.requestId }),
        signal: controller.signal
      });
      const contentType = response.headers.get('Content-Type') || '';
      if (!response.ok || contentType.includes('application/json')) {
        throw await responseError(response);
      }

      const blob = await response.blob();
      if (!blob.size) throw new Error('Dokumen kosong dan tidak dapat diunduh.');

      const info = currentInfo() || {};
      const groupSuffix = state.persons.length > 1 ? '-dan-' + (state.persons.length - 1) + '-siswa' : '';
      const fallback = (state.jenis || 'surat') + '-' + (personName(state.person) || 'personel') + groupSuffix + '.docx';
      const filename = safeFilename(parseFilename(response.headers.get('Content-Disposition')) || fallback);
      const letterNumber = response.headers.get('X-Letter-Number') || '';
      downloadBlob(blob, filename);

      if (letterNumber && state.summary && state.summary.context) {
        state.summary.context.nomor_surat = letterNumber;
        renderSummary(state.summary);
      }
      setStatus(
        elements.downloadStatus,
        letterNumber
          ? 'Dokumen berhasil dibuat dengan nomor ' + letterNumber + ' dan mulai diunduh.'
          : 'Dokumen berhasil dibuat dan mulai diunduh.',
        'success'
      );
      setButtonContent(elements.modalDownloadBtn, 'Unduh Lagi (.docx)', 'fa-solid fa-download');
    } catch (error) {
      if (error.name !== 'AbortError') {
        applyFieldErrors(error.fieldErrors);
        setStatus(
          elements.downloadStatus,
          error.message || 'Dokumen gagal dibuat. Data tetap tersimpan di formulir.',
          'error'
        );
      }
      setButtonContent(elements.modalDownloadBtn, 'Coba Unduh Lagi (.docx)', 'fa-solid fa-download');
    } finally {
      state.downloading = false;
      releaseController('download', controller);
      updateStepAvailability();
    }
  }

  function focusableElements(modal) {
    return Array.from(modal.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), ' +
      'a[href], [tabindex]:not([tabindex="-1"])'
    )).filter((node) => !node.hidden && node.getClientRects().length > 0);
  }

  function openModal(modal, preferredFocus) {
    if (!modal) return;
    if (state.activeModal && state.activeModal !== modal) closeModal(state.activeModal, { restoreFocus: false });
    state.lastFocused.set(modal, document.activeElement);
    state.activeModal = modal;
    modal.hidden = false;
    document.body.classList.add('modal-open');
    if (elements.appRoot) elements.appRoot.inert = true;
    window.setTimeout(() => {
      const target = preferredFocus || focusableElements(modal)[0] || modal.querySelector('.modal-content');
      if (target) target.focus();
    }, 0);
  }

  function closeModal(modal, options) {
    const settings = Object.assign({ restoreFocus: true }, options || {});
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    if (state.activeModal === modal) state.activeModal = null;
    document.body.classList.remove('modal-open');
    if (elements.appRoot) elements.appRoot.inert = false;
    if (modal === modals.arsip) state.archiveTargetInput = null;
    if (settings.restoreFocus) {
      const previous = state.lastFocused.get(modal);
      if (previous && document.contains(previous)) window.setTimeout(() => previous.focus(), 0);
    }
  }

  function closeSummaryToEdit() {
    closeModal(modals.summary, { restoreFocus: false });
    setWizardStep(3);
  }

  function handleModalClose(modal) {
    if (modal === modals.summary && state.downloading) {
      setStatus(elements.downloadStatus, 'Tunggu proses pembuatan dokumen selesai sebelum kembali mengedit.', 'loading');
      return;
    }
    if (modal === modals.summary) closeSummaryToEdit();
    else closeModal(modal);
  }

  function trapModalKeyboard(event) {
    const modal = state.activeModal;
    if (!modal) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      handleModalClose(modal);
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = focusableElements(modal);
    if (!focusable.length) {
      event.preventDefault();
      modal.querySelector('.modal-content').focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function directoryPersonCard(person, kategori) {
    const card = createElement('button', 'surat-select-card directory-card');
    card.type = 'button';
    const top = createElement('span', 'card-top');
    top.append(
      createElement('strong', 'directory-name', personName(person) || 'Tanpa nama'),
      createElement(
        'span',
        kategori === 'murid' ? 'header-pill-badge purple' : 'header-pill-badge',
        kategori === 'murid'
          ? 'KELAS ' + (person.kelas || '-')
          : (person.status_pegawai || 'GURU')
      )
    );
    const identity = createElement(
      'span',
      'directory-identity',
      (kategori === 'murid' ? 'NIS: ' : 'NIP: ') + personId(person, kategori)
    );
    const detail = createElement(
      'span',
      'directory-detail',
      kategori === 'murid' ? 'Kelas ' + (person.kelas || '-') : (person.jabatan || '-')
    );
    const action = createElement('span', 'card-action-label', 'Pilih Personel');
    card.append(top, identity, detail, action);
    card.addEventListener('click', () => {
      closeModal(kategori === 'murid' ? modals.murid : modals.guru, { restoreFocus: false });
      void selectPersonRecord(person, kategori);
    });
    return card;
  }

  function renderPersonDirectory(listElement, records, kategori) {
    listElement.replaceChildren();
    if (!records.length) {
      listElement.append(createElement('p', 'empty-state', 'Data tidak ditemukan.'));
      return;
    }
    const fragment = document.createDocumentFragment();
    records.forEach((person) => fragment.append(directoryPersonCard(person, kategori)));
    listElement.append(fragment);
  }

  async function loadPersonDirectory(kategori, query) {
    const key = kategori + 'Directory';
    const controller = requestController(key);
    const status = byId(kategori === 'murid' ? 'muridModalStatus' : 'guruModalStatus');
    const list = byId(kategori === 'murid' ? 'muridModalList' : 'guruModalList');
    setStatus(status, 'Memuat data…', 'loading');
    try {
      const suffix = query ? '?q=' + encodeURIComponent(query) : '';
      const payload = await fetchJson('/api/list/' + kategori + suffix, { signal: controller.signal });
      const records = normaliseList(payload);
      renderPersonDirectory(list, records, kategori);
      setStatus(status, records.length + ' data ditampilkan.', 'success');
    } catch (error) {
      if (error.name !== 'AbortError') {
        list.replaceChildren();
        setStatus(status, error.message || 'Direktori gagal dimuat.', 'error');
      }
    } finally {
      releaseController(key, controller);
    }
  }

  function openGuruDirectory() {
    openModal(modals.guru, byId('searchGuruModalInput'));
    void loadPersonDirectory('guru', byId('searchGuruModalInput').value.trim());
  }

  function openMuridDirectory() {
    openModal(modals.murid, byId('searchMuridModalInput'));
    void loadPersonDirectory('murid', byId('searchMuridModalInput').value.trim());
  }

  function codeCard(record) {
    const interactive = Boolean(state.archiveTargetInput);
    const card = createElement(interactive ? 'button' : 'article', 'surat-select-card archive-card');
    if (interactive) card.type = 'button';
    else card.classList.add('is-static');
    const top = createElement('span', 'card-top');
    top.append(
      createElement('strong', 'archive-code', record.kode || '-'),
      createElement('span', 'header-pill-badge', 'KODE ARSIP')
    );
    card.append(top, createElement('span', 'archive-description', record.keterangan || '-'));
    if (interactive) {
      card.append(createElement('span', 'card-action-label', 'Gunakan Kode'));
      card.addEventListener('click', () => {
        const target = state.archiveTargetInput;
        if (!target) return;
        target.value = String(record.kode || '');
        target.dispatchEvent(new Event('input', { bubbles: true }));
        closeModal(modals.arsip);
        target.focus();
      });
    }
    return card;
  }

  async function loadKodeArsip(query) {
    const controller = requestController('arsipDirectory');
    const status = byId('kodeArsipStatus');
    const list = byId('kodeArsipList');
    setStatus(status, 'Memuat kode klasifikasi…', 'loading');
    try {
      const suffix = query ? '?q=' + encodeURIComponent(query) : '';
      const records = normaliseList(await fetchJson('/api/list/kode_arsip' + suffix, {
        signal: controller.signal
      }));
      list.replaceChildren();
      if (!records.length) list.append(createElement('p', 'empty-state', 'Kode arsip tidak ditemukan.'));
      else {
        const fragment = document.createDocumentFragment();
        records.forEach((record) => fragment.append(codeCard(record)));
        list.append(fragment);
      }
      setStatus(status, records.length + ' kode ditampilkan.', records.length ? 'success' : 'info');
    } catch (error) {
      if (error.name !== 'AbortError') {
        list.replaceChildren();
        setStatus(status, error.message || 'Kode arsip gagal dimuat.', 'error');
      }
    } finally {
      releaseController('arsipDirectory', controller);
    }
  }

  function openKodeArsipDirectory(targetInput) {
    state.archiveTargetInput = targetInput || null;
    const input = byId('searchKodeArsipInput');
    input.value = '';
    openModal(modals.arsip, input);
    void loadKodeArsip('');
  }

  function historyCard(record) {
    const card = createElement('article', 'history-card');
    const main = createElement('div', 'history-main');
    const heading = createElement('div', 'history-heading');
    heading.append(
      createElement('strong', '', record.jenis_surat || '-'),
      createElement(
        'span',
        record.kategori === 'murid' ? 'header-pill-badge purple' : 'header-pill-badge',
        record.kategori === 'murid' ? 'SISWA' : 'GURU/STAFF'
      )
    );
    main.append(
      heading,
      createElement('div', 'history-number', 'Nomor: ' + (record.nomor_surat || '-')),
      createElement(
        'div',
        'history-person',
        'Pemohon: ' + (record.nama_pemohon || '-') + ' (' + (record.id_pemohon || '-') + ')'
      ),
      createElement('div', 'history-purpose', 'Keperluan: ' + (record.keperluan || '-')),
      createElement('div', 'history-actor', 'Operator: ' + (record.created_by || 'data lama'))
    );
    const side = createElement('div', 'history-side');
    const status = String(record.status || 'generated').toLowerCase();
    const statusMeta = status === 'cancelled'
      ? { label: 'Dibatalkan', className: 'header-pill-badge error-badge' }
      : status === 'failed'
        ? { label: 'Gagal', className: 'header-pill-badge error-badge' }
        : status === 'rendering'
          ? { label: 'Diproses', className: 'header-pill-badge pending-badge' }
          : { label: 'Terbuat', className: 'header-pill-badge success-badge' };
    side.append(
      createElement('span', 'history-date', record.created_at || '-'),
      createElement('span', statusMeta.className, statusMeta.label)
    );
    if (record.cancel_reason) {
      side.append(createElement('small', 'history-cancel-reason', record.cancel_reason));
    }
    if (['admin', 'reviewer'].includes(currentRole) && ['generated', 'failed'].includes(status)) {
      const cancelButton = createElement('button', 'reset-link-btn history-cancel-btn', 'Batalkan');
      cancelButton.type = 'button';
      cancelButton.addEventListener('click', () => void cancelHistoryRecord(record));
      side.append(cancelButton);
    }
    card.append(main, side);
    return card;
  }

  async function cancelHistoryRecord(record) {
    const reason = window.prompt(
      'Masukkan alasan pembatalan nomor ' + (record.nomor_surat || '-') + ' (minimal 5 karakter):'
    );
    if (reason === null) return;
    if (reason.trim().length < 5) {
      setStatus(byId('riwayatModalStatus'), 'Alasan pembatalan minimal 5 karakter.', 'error');
      return;
    }
    if (!window.confirm('Nomor akan dipertahankan dan ditandai dibatalkan. Lanjutkan?')) return;

    const body = new FormData();
    body.set('reason', reason.trim());
    try {
      await fetchJson('/api/history/' + encodeURIComponent(record.id) + '/cancel', {
        method: 'POST',
        body,
        headers: csrfHeaders()
      });
      await openRiwayatDirectory(1, { open: false });
    } catch (error) {
      setStatus(
        byId('riwayatModalStatus'),
        error.message || 'Riwayat gagal dibatalkan.',
        'error'
      );
    }
  }

  function renderHistoryPagination(payload) {
    const container = byId('riwayatPagination');
    container.replaceChildren();
    const page = Number(payload.page || 1);
    const pages = Number(payload.pages || 0);
    if (pages <= 1) return;
    const previous = createElement('button', 'btn-bottom-cancel', 'Sebelumnya');
    previous.type = 'button';
    previous.disabled = page <= 1;
    previous.addEventListener('click', () => void openRiwayatDirectory(page - 1, { open: false }));
    const label = createElement('span', 'history-page-label', 'Halaman ' + page + ' dari ' + pages);
    const next = createElement('button', 'btn-bottom-cancel', 'Berikutnya');
    next.type = 'button';
    next.disabled = page >= pages;
    next.addEventListener('click', () => void openRiwayatDirectory(page + 1, { open: false }));
    container.append(previous, label, next);
  }

  async function openRiwayatDirectory(page, options) {
    const settings = Object.assign({ open: true }, options || {});
    if (settings.open) openModal(modals.riwayat, byId('closeRiwayatModalBtn'));
    const status = byId('riwayatModalStatus');
    const list = byId('riwayatModalList');
    const controller = requestController('history');
    setStatus(status, 'Memuat riwayat surat…', 'loading');
    try {
      const params = new URLSearchParams({
        page: String(page || 1),
        per_page: '25'
      });
      const search = byId('historySearchInput').value.trim();
      const statusFilter = byId('historyStatusFilter').value;
      const typeFilter = byId('historyTypeFilter').value;
      if (search) params.set('q', search);
      if (statusFilter) params.set('status', statusFilter);
      if (typeFilter) params.set('jenis', typeFilter);
      const payload = await fetchJson('/api/list/riwayat?' + params.toString(), {
        signal: controller.signal
      });
      const records = normaliseList(payload);
      list.replaceChildren();
      if (!records.length) list.append(createElement('p', 'empty-state', 'Belum ada riwayat surat.'));
      else {
        const fragment = document.createDocumentFragment();
        records.forEach((record) => fragment.append(historyCard(record)));
        list.append(fragment);
      }
      renderHistoryPagination(payload);
      setStatus(
        status,
        records.length + ' dari ' + Number(payload.total || records.length) + ' riwayat ditampilkan.',
        records.length ? 'success' : 'info'
      );
    } catch (error) {
      if (error.name !== 'AbortError') {
        list.replaceChildren();
        setStatus(status, error.message || 'Riwayat gagal dimuat.', 'error');
      }
    } finally {
      releaseController('history', controller);
    }
  }

  function exportHistoryCsv() {
    const params = new URLSearchParams();
    const search = byId('historySearchInput').value.trim();
    const statusFilter = byId('historyStatusFilter').value;
    const typeFilter = byId('historyTypeFilter').value;
    if (search) params.set('q', search);
    if (statusFilter) params.set('status', statusFilter);
    if (typeFilter) params.set('jenis', typeFilter);
    const suffix = params.toString() ? '?' + params.toString() : '';
    window.location.assign('/api/history/export.csv' + suffix);
  }

  function debounceDirectory(input, key, callback) {
    input.addEventListener('input', () => {
      clearTimer(key);
      state.timers[key] = window.setTimeout(() => {
        delete state.timers[key];
        callback(input.value.trim());
      }, 250);
    });
  }

  function isDirty() {
    if (state.jenis || state.person) return true;
    return Array.from(elements.dynamicFields.querySelectorAll('input, select, textarea'))
      .some((control) => String(control.value || '').trim() !== '');
  }

  function resetApplication() {
    abortAllRequests();
    Object.keys(state.timers).forEach(clearTimer);
    if (state.activeModal) closeModal(state.activeModal, { restoreFocus: false });
    elements.form.reset();
    state.phase = 1;
    state.kategori = 'guru';
    state.jenis = null;
    state.person = null;
    state.persons = [];
    state.fieldSchema = [];
    state.fieldsLoaded = false;
    state.loadingFields = false;
    state.loadingSummary = false;
    state.downloading = false;
    state.summary = null;
    state.summaryValid = false;
    state.requestId = null;
    state.dataVersion += 1;
    elements.jenisInput.value = '';
    elements.idInput.value = '';
    if (elements.studentIdsInputs) elements.studentIdsInputs.replaceChildren();
    elements.requestIdInput.value = '';
    elements.dynamicFields.replaceChildren();
    elements.summaryList.replaceChildren();
    elements.searchBox.value = '';
    elements.searchBox.placeholder = 'Ketik minimal 2 huruf nama, NIP, atau NIS...';
    clearSearchResults();
    clearSelectedPersonDisplay();
    setStatus(elements.wizardStatus, 'Formulir berhasil direset.', 'success');
    setStatus(elements.fieldsStatus, '', 'info');
    setStatus(elements.downloadStatus, '', 'info');
    setStatus(elements.searchStatus, 'Ketik minimal 2 karakter, lalu pilih data dari hasil resmi.', 'info');
    activateCategory('guru', { resetMismatch: false });
    updateTemplateCards();
    setWizardStep(1);
  }

  function requestReset() {
    if (!isDirty() || window.confirm('Reset seluruh pilihan dan isian formulir? Data yang belum diunduh akan hilang.')) {
      resetApplication();
    }
  }

  async function handlePrimaryAction() {
    setStatus(elements.wizardStatus, '', 'info');
    if (state.phase === 1) {
      if (!state.jenis) {
        setStatus(elements.wizardStatus, 'Pilih salah satu template surat terlebih dahulu.', 'error');
        focusStep(1);
        return;
      }
      setWizardStep(2);
    } else if (state.phase === 2) {
      if (!state.person) {
        setStatus(elements.wizardStatus, 'Cari dan pilih personel dari hasil resmi.', 'error');
        elements.searchBox.focus();
        return;
      }
      if (!state.fieldsLoaded) await loadFields();
      else setWizardStep(3);
    } else if (state.phase === 3) {
      await requestSummary();
    } else if (state.phase === 4) {
      if (state.summaryValid && state.summary) {
        renderSummary(state.summary);
        openModal(modals.summary, elements.modalCloseBtn);
      }
    }
  }

  function handleBackAction() {
    if (state.phase === 1) requestReset();
    else if (state.phase === 2) setWizardStep(1);
    else if (state.phase === 3) setWizardStep(2);
    else if (state.phase === 4) setWizardStep(3);
  }

  function bindModalClose(buttonId, modal) {
    const button = byId(buttonId);
    if (button) button.addEventListener('click', () => handleModalClose(modal));
    modal.addEventListener('click', (event) => {
      if (event.target === modal) handleModalClose(modal);
    });
  }

  function bindEvents() {
    elements.form.addEventListener('submit', (event) => event.preventDefault());
    elements.searchBox.addEventListener('input', handleSearchInput);
    elements.searchBox.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' && !elements.searchResults.hidden) {
        const first = elements.searchResults.querySelector('[role="option"]');
        if (first) {
          event.preventDefault();
          first.focus();
        }
      } else if (event.key === 'Escape') {
        clearSearchResults();
      }
    });

    document.querySelectorAll('.category-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        activateCategory(tab.getAttribute('data-kategori'), { resetMismatch: true });
        setWizardStep(1, { focus: false });
        setStatus(elements.wizardStatus, '', 'info');
      });
      tab.addEventListener('keydown', (event) => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        const next = tab.getAttribute('data-kategori') === 'guru' ? byId('tabMurid') : byId('tabGuru');
        next.click();
        next.focus();
      });
    });

    document.querySelectorAll('.surat-card-grid .surat-select-card[data-key]').forEach((card) => {
      card.addEventListener('click', () => selectJenisSurat(card.getAttribute('data-key'), false));
    });
    document.querySelectorAll('.template-modal-card[data-key]').forEach((card) => {
      card.addEventListener('click', () => selectJenisSurat(card.getAttribute('data-key'), true));
    });

    indicators.forEach((indicator) => {
      indicator.addEventListener('click', () => {
        const step = Number(indicator.getAttribute('data-step'));
        if (step === 4 && state.summaryValid && state.summary) {
          setWizardStep(4, { focus: false });
          renderSummary(state.summary);
          openModal(modals.summary, elements.modalCloseBtn);
        } else {
          setWizardStep(step);
        }
      });
    });

    elements.previewBtn.addEventListener('click', () => void handlePrimaryAction());
    elements.btnCancel.addEventListener('click', handleBackAction);
    elements.modalDownloadBtn.addEventListener('click', () => void downloadDocument());
    elements.modalEditBtn.addEventListener('click', closeSummaryToEdit);
    elements.reopenSummaryBtn.addEventListener('click', () => {
      if (state.summaryValid && state.summary) {
        renderSummary(state.summary);
        openModal(modals.summary, elements.modalCloseBtn);
      }
    });

    byId('changeTemplateBtn').addEventListener('click', () => setWizardStep(1));
    byId('changePersonBtn').addEventListener('click', () => setWizardStep(2));
    ['sidebarResetBtn', 'bottomResetBtn', 'mobileResetBtn'].forEach((id) => {
      const button = byId(id);
      if (button) button.addEventListener('click', requestReset);
    });

    document.querySelectorAll('[data-nav-action]').forEach((button) => {
      button.addEventListener('click', () => {
        const action = button.getAttribute('data-nav-action');
        if (action === 'home') setWizardStep(1);
        else if (action === 'guru') openGuruDirectory();
        else if (action === 'murid') openMuridDirectory();
        else if (action === 'templates') openModal(modals.templates, byId('closeTemplatesModalBtn'));
        else if (action === 'riwayat') void openRiwayatDirectory();
        else if (action === 'arsip') openKodeArsipDirectory(null);
      });
    });

    document.querySelectorAll('[data-stat-action]').forEach((button) => {
      button.addEventListener('click', () => {
        const action = button.getAttribute('data-stat-action');
        if (action === 'guru') openGuruDirectory();
        else if (action === 'murid') openMuridDirectory();
        else if (action === 'templates') openModal(modals.templates, byId('closeTemplatesModalBtn'));
        else if (action === 'arsip') openKodeArsipDirectory(null);
      });
    });

    const mobileTemplate = byId('openMobileTemplateModal');
    if (mobileTemplate) {
      mobileTemplate.addEventListener('click', () => openModal(modals.templates, byId('closeTemplatesModalBtn')));
    }
    byId('helpBtn').addEventListener('click', () => openModal(modals.help, byId('closeHelpModalBtn')));
    byId('historyRefreshBtn').addEventListener('click', () => void openRiwayatDirectory(1, { open: false }));
    byId('historyExportBtn').addEventListener('click', exportHistoryCsv);
    byId('historySearchInput').addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        void openRiwayatDirectory(1, { open: false });
      }
    });

    bindModalClose('closeGuruModalBtn', modals.guru);
    bindModalClose('closeMuridModalBtn', modals.murid);
    bindModalClose('closeTemplatesModalBtn', modals.templates);
    bindModalClose('closeKodeArsipModalBtn', modals.arsip);
    bindModalClose('closeRiwayatModalBtn', modals.riwayat);
    bindModalClose('closeHelpModalBtn', modals.help);
    bindModalClose('modalCloseBtn', modals.summary);

    debounceDirectory(
      byId('searchGuruModalInput'),
      'guruDirectorySearch',
      (query) => void loadPersonDirectory('guru', query)
    );
    debounceDirectory(
      byId('searchMuridModalInput'),
      'muridDirectorySearch',
      (query) => void loadPersonDirectory('murid', query)
    );
    debounceDirectory(
      byId('searchKodeArsipInput'),
      'arsipDirectorySearch',
      (query) => void loadKodeArsip(query)
    );

    document.addEventListener('keydown', trapModalKeyboard);
  }

  function initialise() {
    updateStats();
    bindEvents();
    activateCategory('guru', { resetMismatch: false });
    updateTemplateCards();
    clearSearchResults();
    setStatus(elements.wizardStatus, '', 'info');
    setStatus(elements.fieldsStatus, '', 'info');
    setStatus(elements.downloadStatus, '', 'info');
    setWizardStep(1, { focus: false });
  }

  initialise();
})();
