(() => {
  const $ = id => document.getElementById(id);
  const els = {
    deviceSelect: $('deviceSelect'), deviceList: $('deviceList'), summary: $('deviceSummary'),
    start: $('startBtn'), pause: $('pauseBtn'), resume: $('resumeBtn'), stop: $('stopBtn'),
    predict: $('predictBtn'), message: $('simMessage'), mapStatus: $('mapStatus'),
    lat: $('liveLat'), lng: $('liveLng'), speed: $('liveSpeed'), movement: $('liveMovement'),
    progressText: $('progressText'), progressBar: $('progressBar'), prediction: $('predictionResult')
  };
  let devices = [], selectedDevice = null, simulationId = null, timer = null, currentStatus = 'Ready';
  let map = null, marker = null, routeLine = null, predictionMarker = null, routePoints = [];

  function message(text, type = '') { els.message.textContent = text; els.message.className = `inline-message ${type}`; }
  function setStatus(status) { currentStatus = status; els.mapStatus.textContent = status.toUpperCase(); }
  function clearTimer() { if (timer) window.clearInterval(timer); timer = null; }
  function updateControls() {
    const hasDevice = Boolean(selectedDevice);
    els.start.disabled = !hasDevice || ['Running', 'Paused'].includes(currentStatus);
    els.pause.disabled = currentStatus !== 'Running';
    els.resume.disabled = currentStatus !== 'Paused';
    els.stop.disabled = !['Running', 'Paused'].includes(currentStatus);
    els.predict.disabled = !hasDevice || !routePoints.length;
    els.deviceSelect.disabled = ['Running', 'Paused'].includes(currentStatus);
  }
  function fmt(value) { return Number(value).toFixed(6); }
  function initMap() {
    if (!window.L || !$('trackingMap')) { $('trackingMap').innerHTML = '<div class="map-fallback">Map needs an internet connection to load map tiles.</div>'; return; }
    map = L.map('trackingMap').setView([17.385, 78.4867], 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);
    routeLine = L.polyline([], { color: '#71a7ff', weight: 4, opacity: .85 }).addTo(map);
  }
  function resetMap() {
    routePoints = [];
    if (routeLine) routeLine.setLatLngs([]);
    if (marker) { map.removeLayer(marker); marker = null; }
    if (predictionMarker) { map.removeLayer(predictionMarker); predictionMarker = null; }
  }
  function updateMap(lat, lng) {
    const point = [lat, lng]; routePoints.push(point);
    if (routeLine) routeLine.setLatLngs(routePoints);
    if (map) {
      if (!marker) marker = L.circleMarker(point, { radius: 9, color: '#fff', weight: 3, fillColor: '#3b82f6', fillOpacity: 1 }).addTo(map);
      else marker.setLatLng(point);
      map.panTo(point, { animate: true, duration: .45 });
    }
    updateControls();
  }
  function displayReading(data) {
    if (data.latitude == null) return;
    els.lat.textContent = fmt(data.latitude); els.lng.textContent = fmt(data.longitude);
    els.speed.textContent = `${Number(data.speed || 0).toFixed(1)} km/h`;
    els.movement.textContent = data.movement_status || '—';
    updateMap(Number(data.latitude), Number(data.longitude));
    if (data.index != null && data.total) {
      const pct = Math.round((data.index / (data.total - 1)) * 100);
      els.progressText.textContent = `${pct}%`; els.progressBar.style.width = `${pct}%`;
    }
  }
  async function loadDevices() {
    const data = await apiRequest('/api/devices'); devices = data.devices || [];
    els.deviceSelect.innerHTML = '<option value="">Select a simulation device</option>' + devices.map(d => `<option value="${d.id}">${escapeHtml(d.device_code)} · ${escapeHtml(d.device_name)}</option>`).join('');
    els.deviceList.innerHTML = devices.length ? devices.map(d => `<div class="device-row"><span class="device-avatar">⌖</span><div><strong>${escapeHtml(d.device_name)}</strong><small>${escapeHtml(d.device_code)} · ${escapeHtml(d.device_type)} · ${escapeHtml(d.route_key.replace('_',' '))}</small></div><span class="device-status ${d.status==='Active'?'active':''}">${escapeHtml(d.status)}</span></div>`).join('') : '<div class="empty-state">No devices yet. Add a device to begin.</div>';
    if (devices.length && !selectedDevice) els.deviceSelect.value = String(devices[0].id);
    chooseDevice();
    const stats = await apiRequest('/api/stats');
    $('statDevices').textContent = stats.devices; $('statActive').textContent = stats.active_devices;
    $('statSimulations').textContent = stats.simulations; $('statPoints').textContent = stats.location_points;
  }
  function escapeHtml(value) { return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function chooseDevice() {
    const id = Number(els.deviceSelect.value);
    selectedDevice = devices.find(d => d.id === id) || null;
    clearTimer(); simulationId = null; resetMap(); setStatus('Ready');
    els.progressText.textContent = '0%'; els.progressBar.style.width = '0%';
    els.lat.textContent = '—'; els.lng.textContent = '—'; els.speed.textContent = '—'; els.movement.textContent = '—';
    els.prediction.textContent = 'Run a simulation to generate a prediction.';
    els.summary.textContent = selectedDevice ? `${selectedDevice.device_code} · ${selectedDevice.device_type} · ${selectedDevice.route_key.replace('_', ' ')}` : 'Choose a device to view its details.';
    message(selectedDevice ? 'Ready to start a sample route.' : 'Select a device to begin.');
    updateControls();
  }
  async function startSimulation() {
    try {
      const data = await apiRequest('/api/simulations/start', { method: 'POST', body: { device_id: selectedDevice.id } });
      simulationId = data.simulation_id; setStatus('Running'); displayReading(data); message('Simulation started. Coordinates will update automatically.', 'success');
      updateControls(); timer = window.setInterval(tick, 1700); await refreshStats();
    } catch (e) { message(e.message, 'error'); }
  }
  async function tick() {
    if (!simulationId) return;
    try {
      const data = await apiRequest(`/api/simulations/${simulationId}/tick`, { method: 'POST', body: {} });
      if (data.latitude != null) displayReading(data);
      if (data.completed) {
        clearTimer(); setStatus('Completed'); message('Route completed. All simulated points have been saved.', 'success');
        updateControls(); await refreshStats();
      }
    } catch (e) { clearTimer(); message(e.message, 'error'); updateControls(); }
  }
  async function stateAction(action) {
    if (!simulationId) return;
    try {
      const data = await apiRequest(`/api/simulations/${simulationId}/${action}`, { method: 'POST', body: {} });
      setStatus(data.status);
      if (action === 'pause') { clearTimer(); message('Simulation paused.'); }
      if (action === 'resume') { message('Simulation resumed.', 'success'); timer = window.setInterval(tick, 1700); }
      if (action === 'stop') { clearTimer(); message('Simulation stopped. Saved records remain in history.'); await refreshStats(); }
      updateControls();
    } catch (e) { message(e.message, 'error'); }
  }
  async function refreshStats() {
    try { const s = await apiRequest('/api/stats'); $('statDevices').textContent = s.devices; $('statActive').textContent = s.active_devices; $('statSimulations').textContent = s.simulations; $('statPoints').textContent = s.location_points; } catch (_) {}
  }
  async function predict() {
    if (!selectedDevice) return;
    try {
      const data = await apiRequest(`/api/predict/${selectedDevice.id}`, { method: 'POST', body: {} });
      els.prediction.innerHTML = `<strong>${fmt(data.latitude)}, ${fmt(data.longitude)}</strong><small>${escapeHtml(data.classification)}</small><p>${escapeHtml(data.note)}</p>`;
      if (map) {
        if (predictionMarker) map.removeLayer(predictionMarker);
        predictionMarker = L.circleMarker([data.latitude, data.longitude], { radius: 8, color: '#fff', weight: 2, fillColor: '#a78bfa', fillOpacity: 1 }).addTo(map).bindTooltip('Predicted position');
      }
    } catch (e) { els.prediction.textContent = e.message; }
  }
  $('deviceSelect').addEventListener('change', chooseDevice);
  els.start.addEventListener('click', startSimulation);
  els.pause.addEventListener('click', () => stateAction('pause'));
  els.resume.addEventListener('click', () => stateAction('resume'));
  els.stop.addEventListener('click', () => stateAction('stop'));
  els.predict.addEventListener('click', predict);
  $('addDeviceToggle').addEventListener('click', () => $('addDeviceForm').classList.toggle('hidden'));
  $('addDeviceForm').addEventListener('submit', async event => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await apiRequest('/api/devices', { method: 'POST', body: Object.fromEntries(form.entries()) });
      event.currentTarget.reset(); event.currentTarget.classList.add('hidden'); message('Device added successfully.', 'success');
      selectedDevice = null; await loadDevices();
    } catch (e) { message(e.message, 'error'); }
  });
  window.addEventListener('beforeunload', clearTimer);
  initMap();
  loadDevices().catch(e => message(e.message, 'error'));
})();
