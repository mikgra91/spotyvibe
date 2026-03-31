export function toggleAudioFilters() {
    const body = document.getElementById('audioFiltersBody');
    const chevron = document.getElementById('audioFilterChevron');
    const open = !body.classList.contains('hidden');
    body.classList.toggle('hidden', open);
    chevron.textContent = open ? '▼' : '▲';
}

export function getAudioFilters() {
    const filters = {};
    const features = ['energy','valence','tempo','danceability','acousticness'];
    features.forEach(f => {
        const minEl = document.getElementById(`af-${f}-min`);
        const maxEl = document.getElementById(`af-${f}-max`);
        const lo = minEl && minEl.value !== '' ? parseFloat(minEl.value) : null;
        const hi = maxEl && maxEl.value !== '' ? parseFloat(maxEl.value) : null;
        if (lo !== null || hi !== null) {
            filters[f] = {};
            if (lo !== null) filters[f].min = lo;
            if (hi !== null) filters[f].max = hi;
        }
    });
    return Object.keys(filters).length ? filters : null;
}
