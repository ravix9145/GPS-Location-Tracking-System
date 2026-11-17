(() => {
  const form = document.getElementById('distanceForm');
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    for (const key of Object.keys(data)) data[key] = Number(data[key]);
    const result = document.getElementById('distanceResult');
    result.textContent = 'Calculating…';
    try {
      const response = await apiRequest('/api/distance', {method:'POST', body:data});
      result.textContent = `Distance: ${response.distance_km} km (${response.distance_m} metres)`;
      result.className = 'inline-message success';
    } catch (error) {
      result.textContent = error.message;
      result.className = 'inline-message error';
    }
  });
})();
