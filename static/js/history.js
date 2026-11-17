(() => {
  const $ = id => document.getElementById(id);
  $('loadHistory').addEventListener('click', async () => {
    const id = $('historyDevice').value;
    if (!id) { $('historyMessage').textContent = 'Please select a device.'; return; }
    const limit = $('historyLimit').value;
    const from = $('historyFrom').value;
    const to = $('historyTo').value;
    if (from && to && from > to) { $('historyMessage').textContent = 'From date must not be later than To date.'; return; }
    $('historyMessage').textContent = 'Loading saved coordinate records…';
    try {
      const params = new URLSearchParams({device_id:id, limit, from, to});
      const data = await apiRequest(`/api/locations?${params.toString()}`);
      const rows = data.locations || [];
      $('historyRows').innerHTML = rows.length ? rows.map((p,i) => `<tr><td>${i+1}</td><td>${Number(p.latitude).toFixed(6)}</td><td>${Number(p.longitude).toFixed(6)}</td><td>${escapeText(p.recorded_at.replace('T',' '))}</td><td>${Number(p.speed).toFixed(1)} km/h</td><td><span class="movement-chip">${escapeText(p.movement_status)}</span></td></tr>`).join('') : '<tr><td colspan="6" class="empty-cell">No saved locations for this device yet.</td></tr>';
      $('historyMessage').textContent = `${rows.length} location record(s) loaded.`;
    } catch (e) { $('historyMessage').textContent = e.message; }
  });
  function escapeText(v) { return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
})();
