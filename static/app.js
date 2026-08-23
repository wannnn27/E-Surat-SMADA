// Dynamic Form, Stepper & Card Handler
const jenisSuratData = JSON.parse(document.getElementById('jenisSuratDataJson').textContent);
const jenisInput = document.getElementById('jenisSurat');
const searchBox = document.getElementById('searchBox');
const searchResults = document.getElementById('searchResults');
const idValueInput = document.getElementById('id_value');
const selectedPersonDiv = document.getElementById('selectedPerson');
const dynamicFields = document.getElementById('dynamicFields');

const step1 = document.getElementById('stepIndicator1');
const step2 = document.getElementById('stepIndicator2');
const step3 = document.getElementById('stepIndicator3');
const step4 = document.getElementById('stepIndicator4');

let currentKategori = 'guru';
let currentJenis = null;
let searchTimeout = null;

// Category Tabs Logic
const categoryTabs = document.querySelectorAll('.category-tab');
const gridGuru = document.getElementById('gridGuru');
const gridMurid = document.getElementById('gridMurid');
const wizardHeaderBadge = document.getElementById('wizardHeaderBadge');

categoryTabs.forEach(tab => {
  tab.addEventListener('click', () => {
    categoryTabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');

    const kat = tab.getAttribute('data-kategori');
    currentKategori = kat;
    if (kat === 'guru') {
      gridGuru.style.display = 'grid';
      gridMurid.style.display = 'none';
      if (wizardHeaderBadge) {
        wizardHeaderBadge.textContent = 'Kategori: Guru / Staff';
        wizardHeaderBadge.className = 'header-pill-badge';
      }
    } else {
      gridGuru.style.display = 'none';
      gridMurid.style.display = 'grid';
      if (wizardHeaderBadge) {
        wizardHeaderBadge.textContent = 'Kategori: Siswa / Murid';
        wizardHeaderBadge.className = 'header-pill-badge purple';
      }
    }
  });
});

// Category Cards Click Handler
const selectCards = document.querySelectorAll('.surat-card-grid .surat-select-card');
selectCards.forEach(card => {
  card.addEventListener('click', () => {
    const key = card.getAttribute('data-key');
    if (key) {
      selectJenisSurat(key);
    }
  });
});

function selectJenisSurat(key) {
  if (!key || !jenisSuratData[key]) return;

  currentJenis = key;
  jenisInput.value = key;

  const info = jenisSuratData[currentJenis];
  currentKategori = info.kategori;

  // Highlight active card across all grids
  document.querySelectorAll('.surat-select-card').forEach(c => {
    if (c.getAttribute('data-key') === key) {
      c.classList.add('active');
    } else {
      c.classList.remove('active');
    }
  });

  // Update Mobile Trigger Labels
  const mobTitle = document.getElementById('mobileSelectedSuratTitle');
  const mobSub = document.getElementById('mobileSelectedSuratSub');
  if (mobTitle) mobTitle.textContent = info.label;
  if (mobSub) mobSub.textContent = info.deskripsi || 'Template resmi SMADA';

  // Reset subsequent steps
  if (searchBox) searchBox.value = '';
  if (idValueInput) idValueInput.value = '';
  if (searchResults) searchResults.innerHTML = '';
  if (selectedPersonDiv) selectedPersonDiv.style.display = 'none';
  if (dynamicFields) dynamicFields.innerHTML = '';

  // Advance wizard to Step 2
  setWizardStep(2);

  if (searchBox) {
    searchBox.placeholder = currentKategori === 'guru'
      ? 'Ketik nama atau NIP guru/staff...'
      : 'Ketik nama, NIS, atau NISN murid...';
  }
}

searchBox.addEventListener('input', () => {
  clearTimeout(searchTimeout);
  const q = searchBox.value.trim();
  if (q.length < 2) {
    searchResults.innerHTML = '';
    return;
  }
  searchTimeout = setTimeout(() => {
    fetch(`/api/search?q=${encodeURIComponent(q)}&kategori=${currentKategori}`)
      .then(r => r.json())
      .then(renderResults);
  }, 200);
});

function renderResults(results) {
  if (results.length === 0) {
    searchResults.innerHTML = '<div style="padding:14px; text-align:center; color:var(--text-muted); font-size:13px;"><i class="fa-solid fa-circle-exclamation"></i> Data tidak ditemukan di database.</div>';
    return;
  }
  searchResults.innerHTML = results.map(p => {
    const idField = currentKategori === 'guru' ? p.nip : p.nis;
    const subtitle = currentKategori === 'guru'
      ? `NIP: ${p.nip} — ${p.jabatan}`
      : `NIS: ${p.nis} — Kelas ${p.kelas}`;
    const badgeLabel = currentKategori === 'guru' ? 'Guru/Staff' : `Kelas ${p.kelas}`;
    const detailSub = currentKategori === 'guru' ? p.jabatan : `NIS: ${p.nis}`;

    return `<div class="result-item" data-id="${idField}" data-name="${p.nama}" data-sub="${detailSub}">
              <div>
                <strong style="font-size:14px; color:var(--text-primary); display:block;">${p.nama}</strong>
                <small style="font-size:12px; color:var(--text-secondary);">${subtitle}</small>
              </div>
              <span class="header-pill-badge">${badgeLabel}</span>
            </div>`;
  }).join('');

  document.querySelectorAll('.result-item').forEach(el => {
    el.addEventListener('click', () => selectPerson(el.dataset.id, el.dataset.name, el.dataset.sub));
  });
}

function selectPerson(id, name, sub) {
  idValueInput.value = id;
  searchBox.value = name;
  searchResults.innerHTML = '';
  selectedPersonDiv.style.display = 'flex';
  selectedPersonDiv.innerHTML = `
    <div>
      <strong style="font-size:14px;"><i class="fa-solid fa-circle-check"></i> ${name}</strong><br>
      <small style="font-size:12px; opacity:0.9;">${currentKategori === 'guru' ? 'NIP' : 'NIS'}: ${id} — ${sub}</small>
    </div>
    <span class="header-pill-badge">Terpilih</span>
  `;

  loadFields(currentJenis);
  setWizardStep(3);
}

function loadFields(jenis) {
  fetch(`/api/fields/${jenis}`)
    .then(r => r.json())
    .then(info => {
      const d = new Date();
      const autoNo = `00.1.2.3/${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}/SMADA/${d.getFullYear()}`;
      
      let fieldsHtml = `
        <div class="form-group" style="grid-column: 1 / -1;">
          <label class="form-label">Nomor Surat Official (Dapat Diubah oleh TU)</label>
          <input type="text" name="nomor_surat_custom" value="${autoNo}" class="form-control field-input" data-field="nomor_surat_custom" placeholder="cth: 00.1.2.3/045/SMADA/2026" required>
        </div>
      `;

      fieldsHtml += info.fields.map(f => {
        const defaultVal = f.default || '';
        if (f.type === 'select') {
          const opts = f.options.map(o => `<option value="${o}">${o}</option>`).join('');
          return `<div class="form-group">
                    <label class="form-label">${f.label}</label>
                    <select name="${f.name}" class="form-control field-input" data-field="${f.name}" required>${opts}</select>
                  </div>`;
        }
        const inputType = f.type === 'date' ? 'date' : 'text';
        return `<div class="form-group">
                  <label class="form-label">${f.label}</label>
                  <input type="${inputType}" name="${f.name}" value="${defaultVal}"
                         class="form-control field-input" data-field="${f.name}"
                         placeholder="${f.placeholder || ''}" required>
                </div>`;
      }).join('');

      dynamicFields.innerHTML = fieldsHtml;

      // Attach Live Input Listeners
      document.querySelectorAll('.field-input').forEach(input => {
        input.addEventListener('input', updatePreviewFields);
        input.addEventListener('change', updatePreviewFields);
      });
      updatePreviewFields();
    });
}

function updatePreviewFields() {
  const inputs = document.querySelectorAll('.field-input');
  inputs.forEach(input => {
    const name = input.getAttribute('data-field');
    const val = input.value;
  });
}

// Interactive Sidebar Nav & Directory Modals
const modalGuru = document.getElementById('modalGuru');
const modalMurid = document.getElementById('modalMurid');
const modalTemplates = document.getElementById('modalTemplates');
const modalKodeArsip = document.getElementById('modalKodeArsip');
const modalRiwayat = document.getElementById('modalRiwayat');

const navItems = document.querySelectorAll('.nav-item');
navItems[1].addEventListener('click', () => {
  openGuruDirectory();
});
navItems[2].addEventListener('click', () => {
  openMuridDirectory();
});
navItems[3].addEventListener('click', () => {
  modalTemplates.style.display = 'flex';
});
if (navItems[4]) {
  navItems[4].addEventListener('click', () => {
    openRiwayatDirectory();
  });
}
if (navItems[5]) {
  navItems[5].addEventListener('click', () => {
    openKodeArsipDirectory();
  });
}

const mobileTrigger = document.getElementById('openMobileTemplateModal');
if (mobileTrigger) {
  mobileTrigger.addEventListener('click', () => {
    modalTemplates.style.display = 'flex';
  });
}

document.getElementById('closeGuruModalBtn').addEventListener('click', () => { modalGuru.style.display = 'none'; });
document.getElementById('closeMuridModalBtn').addEventListener('click', () => { modalMurid.style.display = 'none'; });
document.getElementById('closeTemplatesModalBtn').addEventListener('click', () => { modalTemplates.style.display = 'none'; });
document.getElementById('closeKodeArsipModalBtn').addEventListener('click', () => { modalKodeArsip.style.display = 'none'; });
document.getElementById('closeRiwayatModalBtn').addEventListener('click', () => { modalRiwayat.style.display = 'none'; });

// Open & Load Guru Directory
function openGuruDirectory() {
  fetch('/api/list/guru')
    .then(r => r.json())
    .then(data => {
      renderGuruModalList(data);
      modalGuru.style.display = 'flex';
    });
}

function renderGuruModalList(data) {
  const listEl = document.getElementById('guruModalList');
  if (data.length === 0) {
    listEl.innerHTML = '<div style="grid-column:1/-1; padding:20px; text-align:center; color:var(--text-muted);">Tidak ditemukan.</div>';
    return;
  }
  listEl.innerHTML = data.map(g => `
    <div class="surat-select-card" onclick="selectPersonFromModal('${g.nip}', '${g.nama}', '${g.jabatan}', 'guru')">
      <div class="card-top">
        <strong style="font-size:14px; color:var(--text-primary);">${g.nama}</strong>
        <span class="header-pill-badge">${g.status_pegawai || 'GURU'}</span>
      </div>
      <div style="font-size:12px; color:var(--text-secondary); font-weight:600;">NIP: ${g.nip}</div>
      <div style="font-size:11px; color:var(--text-muted);">${g.jabatan} | Gol: ${g.golongan || '-'}</div>
      <div style="font-size:11px; color:var(--text-muted); italic;">TTL: ${g.ttl || '-'}</div>
      <button type="button" class="btn-bottom-navy" style="padding:6px 12px; font-size:11px; margin-top:6px;">Pilih Personel</button>
    </div>
  `).join('');
}

document.getElementById('searchGuruModalInput').addEventListener('input', (e) => {
  const q = e.target.value.trim();
  fetch(`/api/list/guru?q=${encodeURIComponent(q)}`)
    .then(r => r.json())
    .then(renderGuruModalList);
});

// Open & Load Murid Directory
function openMuridDirectory() {
  fetch('/api/list/murid')
    .then(r => r.json())
    .then(data => {
      renderMuridModalList(data);
      modalMurid.style.display = 'flex';
    });
}

function renderMuridModalList(data) {
  const listEl = document.getElementById('muridModalList');
  if (data.length === 0) {
    listEl.innerHTML = '<div style="grid-column:1/-1; padding:20px; text-align:center; color:var(--text-muted);">Tidak ditemukan.</div>';
    return;
  }
  listEl.innerHTML = data.map(m => `
    <div class="surat-select-card" onclick="selectPersonFromModal('${m.nis}', '${m.nama}', 'Kelas ${m.kelas}', 'murid')">
      <div class="card-top">
        <strong style="font-size:14px; color:var(--text-primary);">${m.nama}</strong>
        <span class="header-pill-badge purple">KELAS ${m.kelas}</span>
      </div>
      <div style="font-size:12px; color:var(--text-secondary); font-weight:600;">NIS: ${m.nis} | NISN: ${m.nisn || '-'}</div>
      <div style="font-size:11px; color:var(--text-muted);">Gender: ${m.jk === 'L' ? 'Laki-laki' : 'Perempuan'} | Agama: ${m.agama || '-'}</div>
      <button type="button" class="btn-bottom-navy" style="padding:6px 12px; font-size:11px; margin-top:6px;">Pilih Siswa</button>
    </div>
  `).join('');
}

document.getElementById('searchMuridModalInput').addEventListener('input', (e) => {
  const q = e.target.value.trim();
  fetch(`/api/list/murid?q=${encodeURIComponent(q)}`)
    .then(r => r.json())
    .then(renderMuridModalList);
});

// Open & Load Riwayat Surat Log for TU
function openRiwayatDirectory() {
  fetch('/api/list/riwayat')
    .then(r => r.json())
    .then(data => {
      renderRiwayatModalList(data);
      modalRiwayat.style.display = 'flex';
    });
}

function renderRiwayatModalList(data) {
  const listEl = document.getElementById('riwayatModalList');
  if (data.length === 0) {
    listEl.innerHTML = '<div style="padding:20px; text-align:center; color:var(--text-muted); font-size:13px;"><i class="fa-solid fa-clock"></i> Belum ada riwayat surat yang terbuat. Surat yang dibuat akan otomatis tercatat di sini!</div>';
    return;
  }
  listEl.innerHTML = data.map(r => `
    <div style="background:var(--card-bg); border:1px solid var(--card-border); border-radius:12px; padding:14px; display:flex; align-items:center; justify-content:space-between;">
      <div>
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
          <strong style="font-size:14px; color:var(--text-primary);">${r.jenis_surat}</strong>
          <span class="header-pill-badge">${r.kategori === 'guru' ? 'GURU/STAFF' : 'SISWA'}</span>
        </div>
        <div style="font-size:12px; color:var(--primary-navy); font-weight:700;">Nomor: ${r.nomor_surat}</div>
        <div style="font-size:12px; color:var(--text-secondary);">Pemohon: <strong>${r.nama_pemohon}</strong> (${r.id_pemohon})</div>
        <div style="font-size:11px; color:var(--text-muted);">Keperluan: ${r.keperluan}</div>
      </div>
      <div style="text-align:right;">
        <span style="font-size:11px; color:var(--text-muted); display:block; margin-bottom:6px;"><i class="fa-solid fa-calendar"></i> ${r.created_at}</span>
        <span class="header-pill-badge" style="background:#ecfdf5; color:#047857; border-color:#a7f3d0;"><i class="fa-solid fa-check"></i> Terbuat</span>
      </div>
    </div>
  `).join('');
}

// Open & Load Kode Klasifikasi Arsip Directory
function openKodeArsipDirectory() {
  fetch('/api/list/kode_arsip')
    .then(r => r.json())
    .then(data => {
      renderKodeArsipModalList(data);
      modalKodeArsip.style.display = 'flex';
    });
}

function renderKodeArsipModalList(data) {
  const listEl = document.getElementById('kodeArsipList');
  if (data.length === 0) {
    listEl.innerHTML = '<div style="grid-column:1/-1; padding:20px; text-align:center; color:var(--text-muted);">Kode arsip tidak ditemukan.</div>';
    return;
  }
  listEl.innerHTML = data.map(k => `
    <div class="surat-select-card">
      <div class="card-top">
        <strong style="font-size:14px; color:var(--primary-navy);">${k.kode}</strong>
        <span class="header-pill-badge">KODE ARSIP</span>
      </div>
      <div style="font-size:12px; color:var(--text-primary); font-weight:600;">${k.keterangan}</div>
    </div>
  `).join('');
}

document.getElementById('searchKodeArsipInput').addEventListener('input', (e) => {
  const q = e.target.value.trim();
  fetch(`/api/list/kode_arsip?q=${encodeURIComponent(q)}`)
    .then(r => r.json())
    .then(renderKodeArsipModalList);
});

// Select Person directly from Directory Modals
window.selectPersonFromModal = function(id, name, sub, kategori) {
  if (kategori !== currentKategori) {
    const tab = document.querySelector(`.category-tab[data-kategori="${kategori}"]`);
    if (tab) tab.click();
  }
  modalGuru.style.display = 'none';
  modalMurid.style.display = 'none';

  if (!currentJenis) {
    const firstCard = document.querySelector(`.surat-select-card[data-kategori="${kategori}"]`);
    if (firstCard) firstCard.click();
  }

  selectPerson(id, name, sub);
};

window.selectJenisSuratFromModal = function(key) {
  modalTemplates.style.display = 'none';
  const info = jenisSuratData[key];
  if (!info) return;

  const kat = info.kategori;
  const tab = document.querySelector(`.category-tab[data-kategori="${kat}"]`);
  if (tab && !tab.classList.contains('active')) {
    tab.click();
  }

  selectJenisSurat(key);
};

let currentWizardStep = 1;

function setWizardStep(step) {
  currentWizardStep = step;
  const steps = [step1, step2, step3, step4];
  steps.forEach((s, idx) => {
    if (idx + 1 < currentWizardStep) {
      s.className = 'stepper-circle-item completed';
    } else if (idx + 1 === currentWizardStep) {
      s.className = 'stepper-circle-item active';
    } else {
      s.className = 'stepper-circle-item';
    }
  });

  const panel1 = document.getElementById('stepPanel1');
  const panel2 = document.getElementById('stepPanel2');
  const panel3 = document.getElementById('stepPanel3');

  const headerIcon = document.getElementById('wizardHeaderIcon');
  const headerTitle = document.getElementById('wizardHeaderTitle');
  const headerBadge = document.getElementById('wizardHeaderBadge');

  const btnCancel = document.getElementById('btnCancel');
  const previewBtn = document.getElementById('previewBtn');

  if (currentWizardStep === 1) {
    panel1.style.display = 'block';
    panel2.style.display = 'none';
    panel3.style.display = 'none';

    headerIcon.className = 'fa-solid fa-layer-group';
    headerTitle.textContent = 'Langkah 1: Kategori & Jenis Surat';
    headerBadge.textContent = 'Kategori: ' + (currentKategori === 'guru' ? 'Guru / Staff' : 'Siswa / Murid');
    headerBadge.className = currentKategori === 'guru' ? 'header-pill-badge' : 'header-pill-badge purple';

    btnCancel.innerHTML = 'Batal';
    btnCancel.onclick = () => location.reload();
    previewBtn.innerHTML = 'Lanjut ke Cari Personel <i class="fa-solid fa-arrow-right"></i>';

  } else if (currentWizardStep === 2) {
    panel1.style.display = 'none';
    panel2.style.display = 'block';
    panel3.style.display = 'none';

    const info = jenisSuratData[currentJenis] || {};
    document.getElementById('step2SelectedSurat').textContent = info.label || currentJenis;

    headerIcon.className = 'fa-solid fa-magnifying-glass';
    headerTitle.textContent = 'Langkah 2: Pencarian Data Personel';
    headerBadge.textContent = currentKategori === 'guru' ? 'Database Guru' : 'Database Murid';
    headerBadge.className = 'header-pill-badge purple';

    btnCancel.innerHTML = '<i class="fa-solid fa-arrow-left"></i> Kembali';
    btnCancel.onclick = () => setWizardStep(1);
    previewBtn.innerHTML = 'Lanjut ke Isi Detail <i class="fa-solid fa-arrow-right"></i>';

    setTimeout(() => searchBox.focus(), 100);

  } else if (currentWizardStep === 3) {
    panel1.style.display = 'none';
    panel2.style.display = 'none';
    panel3.style.display = 'block';

    const info = jenisSuratData[currentJenis] || {};
    document.getElementById('step3SelectedSurat').textContent = info.label || currentJenis;
    document.getElementById('step3SelectedPerson').textContent = searchBox.value || '-';

    headerIcon.className = 'fa-solid fa-pen-to-square';
    headerTitle.textContent = 'Langkah 3: Parameter & Rincian Surat';
    headerBadge.textContent = 'Formulir Detail';
    headerBadge.className = 'header-pill-badge';

    btnCancel.innerHTML = '<i class="fa-solid fa-arrow-left"></i> Kembali';
    btnCancel.onclick = () => setWizardStep(2);
    previewBtn.innerHTML = 'Lanjutkan ke Pratinjau <i class="fa-solid fa-arrow-right"></i>';

    setTimeout(() => {
      const firstInp = panel3.querySelector('input[type="date"], input[type="text"]');
      if (firstInp) firstInp.focus();
    }, 100);
  }
}

// Initialize Step 1 navigation buttons
// Declare module-level previewBtn BEFORE setWizardStep(1) to avoid TDZ
const previewBtn = document.getElementById('previewBtn');
const previewModal = document.getElementById('previewModal');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalEditBtn = document.getElementById('modalEditBtn');
const modalDownloadBtn = document.getElementById('modalDownloadBtn');
const suratForm = document.getElementById('suratForm');

setWizardStep(1);

// Stepper Item Clicks
step1.addEventListener('click', () => {
  setWizardStep(1);
});
step2.addEventListener('click', () => {
  if (currentJenis) {
    setWizardStep(2);
  } else {
    alert('Silakan pilih jenis surat pada Langkah 1 terlebih dahulu.');
  }
});
step3.addEventListener('click', () => {
  if (idValueInput.value) {
    setWizardStep(3);
  } else {
    alert('Silakan pilih data Guru/Staff atau Murid pada Langkah 2 terlebih dahulu.');
  }
});
step4.addEventListener('click', () => {
  if (idValueInput.value && currentWizardStep === 3) {
    previewBtn.click();
  }
});

// Reset Buttons Handler
const resetFn = () => { location.reload(); };
document.getElementById('sidebarResetBtn').addEventListener('click', resetFn);
document.getElementById('bottomResetBtn').addEventListener('click', resetFn);
const mobileResetEl = document.getElementById('mobileResetBtn');
if (mobileResetEl) mobileResetEl.addEventListener('click', resetFn);

// Modal Preview Handlers
previewBtn.addEventListener('click', () => {
  if (currentWizardStep === 1) {
    if (!jenisInput.value) {
      alert('Silakan pilih salah satu jenis surat pada Langkah 1 terlebih dahulu.');
      return;
    }
    setWizardStep(2);
    setTimeout(() => {
      searchBox.focus();
    }, 150);
  } else if (currentWizardStep === 2) {
    if (!idValueInput.value) {
      alert('Silakan cari dan pilih data Guru/Staff atau Murid pada Langkah 2 terlebih dahulu.');
      return;
    }
    loadFields(currentJenis);
    setWizardStep(3);
  } else if (currentWizardStep === 3) {
    if (!suratForm.reportValidity()) {
      return;
    }
    const formData = new FormData(suratForm);
    fetch('/api/preview_render', {
      method: 'POST',
      body: formData
    })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        alert(data.error);
        return;
      }
      const info = data.info;
      const ctx = data.context;
      const p = data.person;

      document.getElementById('modalDocTitle').textContent = info.label.toUpperCase();
      document.getElementById('modalDocNo').textContent = 'Nomor: ' + ctx.nomor_surat;
      document.getElementById('modalDocDate').textContent = 'Wonosari, ' + ctx.tanggal_surat;

      if (info.kategori === 'guru') {
        document.getElementById('modalDocRole').textContent = 'Hormat saya / Pemohon,';
        document.getElementById('modalDocName').textContent = p.nama;
        document.getElementById('modalDocNip').textContent = 'NIP. ' + p.nip;
      } else {
        document.getElementById('modalDocRole').textContent = ctx.nama_kepsek ? 'Kepala Sekolah,' : 'Orang Tua / Wali,';
        document.getElementById('modalDocName').textContent = ctx.nama_kepsek || ctx.nama_wali || p.nama;
        document.getElementById('modalDocNip').textContent = ctx.nip_kepsek ? ('NIP. ' + ctx.nip_kepsek) : '';
      }

      let bodyHtml = `
        <div style="margin-bottom:12px; font-family:'Times New Roman', serif;">Yang bertanda tangan di bawah ini:</div>
        <table style="width:100%; border-collapse:collapse; margin-bottom:16px; font-family:'Times New Roman', serif; font-size:14px; color:var(--text-primary);">
          <tr>
            <td style="width:170px; padding:3px 0; vertical-align:top;">Nama</td>
            <td style="width:16px; padding:3px 0; vertical-align:top; text-align:center;">:</td>
            <td style="padding:3px 0; vertical-align:top; font-weight:700;">${p.nama}</td>
          </tr>
          <tr>
            <td style="padding:3px 0; vertical-align:top;">${info.kategori === 'guru' ? 'NIP' : 'NIS / NISN'}</td>
            <td style="padding:3px 0; vertical-align:top; text-align:center;">:</td>
            <td style="padding:3px 0; vertical-align:top; font-weight:700;">${info.kategori === 'guru' ? p.nip : (p.nis + (p.nisn ? (' / ' + p.nisn) : ''))}</td>
          </tr>
          <tr>
            <td style="padding:3px 0; vertical-align:top;">${info.kategori === 'guru' ? 'Jabatan' : 'Kelas'}</td>
            <td style="padding:3px 0; vertical-align:top; text-align:center;">:</td>
            <td style="padding:3px 0; vertical-align:top;">${info.kategori === 'guru' ? p.jabatan : ('Kelas ' + p.kelas)}</td>
          </tr>
      `;

      if (info.kategori === 'guru' && p.golongan) {
        bodyHtml += `
          <tr>
            <td style="padding:3px 0; vertical-align:top;">Pangkat / Golongan</td>
            <td style="padding:3px 0; vertical-align:top; text-align:center;">:</td>
            <td style="padding:3px 0; vertical-align:top;">${p.golongan}</td>
          </tr>
        `;
      }

      info.fields.forEach(f => {
        const val = ctx[f.name] || '-';
        bodyHtml += `
          <tr>
            <td style="padding:3px 0; vertical-align:top;">${f.label}</td>
            <td style="padding:3px 0; vertical-align:top; text-align:center;">:</td>
            <td style="padding:3px 0; vertical-align:top;">${val}</td>
          </tr>
        `;
      });

      bodyHtml += `</table>`;

      document.getElementById('modalPaperBody').innerHTML = bodyHtml;
      setWizardStep(4);
      previewModal.style.display = 'flex';
    });
  }
});

modalCloseBtn.addEventListener('click', () => { previewModal.style.display = 'none'; });
modalEditBtn.addEventListener('click', () => { previewModal.style.display = 'none'; });
modalDownloadBtn.addEventListener('click', () => {
  suratForm.submit();
});
