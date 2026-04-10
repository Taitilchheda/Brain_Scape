/**
 * Brain_Scape — Damage Overlay Controls
 *
 * Controls for the color-coded damage layer:
 * - Toggle individual severity levels
 * - Adjust opacity
 * - Isolate specific atlas regions
 */

import { DAMAGE_COLORS } from './brain_viewer.js';

// ── Severity Level Toggles ──

const severityLevels = [
    { level: 0, label: 'Not implicated', color: '#4A90D9', visible: true },
    { level: 1, label: 'No damage detected', color: '#27AE60', visible: true },
    { level: 2, label: 'Mild abnormality', color: '#F1C40F', visible: true },
    { level: 3, label: 'Moderate-to-severe', color: '#E67E22', visible: true },
    { level: 4, label: 'Severe damage', color: '#E74C3C', visible: true },
];

let overlayOpacity = 0.85;

/**
 * Toggle visibility of a severity level in the 3D viewer.
 */
function toggleSeverityLevel(level) {
    const entry = severityLevels.find(s => s.level === level);
    if (entry) {
        entry.visible = !entry.visible;
        updateOverlay();
    }
}

/**
 * Set opacity for the damage overlay.
 */
function setOverlayOpacity(opacity) {
    overlayOpacity = Math.max(0, Math.min(1, opacity));
    updateOverlay();
}

/**
 * Isolate a specific atlas region, hiding all others.
 */
function isolateRegion(regionName) {
    // In production, this would filter the 3D mesh to show only
    // faces belonging to the specified atlas region
    console.log(`Isolating region: ${regionName}`);
}

/**
 * Show all regions (undo isolation).
 */
function showAllRegions() {
    severityLevels.forEach(s => s.visible = true);
    updateOverlay();
}

/**
 * Update the 3D overlay based on current visibility settings.
 */
function updateOverlay() {
    // This function updates the Three.js mesh colors based on
    // which severity levels are currently visible.
    // Called whenever visibility or opacity changes.

    const visibleLevels = severityLevels.filter(s => s.visible).map(s => s.level);
    console.log('Visible levels:', visibleLevels, 'Opacity:', overlayOpacity);

    // Dispatch custom event for the brain viewer to handle
    const event = new CustomEvent('damage-overlay-update', {
        detail: {
            visibleLevels,
            opacity: overlayOpacity,
        }
    });
    document.dispatchEvent(event);
}

/**
 * Initialize the damage overlay controls UI.
 */
function initOverlayControls() {
    const panel = document.querySelector('.side-panel');
    if (!panel) return;

    // Add opacity slider
    const opacitySection = document.createElement('div');
    opacitySection.innerHTML = `
        <div class="section-title">Overlay Opacity</div>
        <input type="range" min="0" max="100" value="${overlayOpacity * 100}"
               style="width:100%;" id="opacity-slider">
    `;
    panel.appendChild(opacitySection);

    document.getElementById('opacity-slider')?.addEventListener('input', (e) => {
        setOverlayOpacity(e.target.value / 100);
    });

    // Add severity level toggles
    const toggleSection = document.createElement('div');
    let toggleHTML = '<div class="section-title">Toggle Severity Levels</div>';

    severityLevels.forEach(s => {
        toggleHTML += `
            <label style="display:flex;align-items:center;gap:0.5rem;margin:0.3rem 0;cursor:pointer;">
                <input type="checkbox" checked data-level="${s.level}" class="severity-toggle">
                <span style="width:12px;height:12px;border-radius:50%;background:${s.color};"></span>
                <span style="font-size:0.85rem;">${s.label}</span>
            </label>
        `;
    });

    toggleSection.innerHTML = toggleHTML;
    panel.appendChild(toggleSection);

    // Attach event listeners
    document.querySelectorAll('.severity-toggle').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            const level = parseInt(e.target.dataset.level);
            toggleSeverityLevel(level);
        });
    });
}

// ── Region List Population ──

function populateRegionList(regions) {
    const listEl = document.getElementById('region-list');
    if (!listEl) return;

    listEl.innerHTML = '';

    regions.forEach(region => {
        const item = document.createElement('div');
        item.className = 'region-item';
        item.innerHTML = `
            <span style="color:${getSeverityHex(region.severity_level)};">
                ${region.anatomical_name || region.atlas_id}
            </span>
            <span style="float:right;font-size:0.75rem;color:#7a8ab0;">
                ${(region.confidence * 100).toFixed(0)}%
            </span>
        `;
        item.addEventListener('click', () => isolateRegion(region.anatomical_name));
        listEl.appendChild(item);
    });
}

function getSeverityHex(level) {
    const colors = { 0: '#4A90D9', 1: '#27AE60', 2: '#F1C40F', 3: '#E67E22', 4: '#E74C3C' };
    return colors[level] || '#7a8ab0';
}

// ── Initialize ──

document.addEventListener('DOMContentLoaded', () => {
    initOverlayControls();
});

export { toggleSeverityLevel, setOverlayOpacity, isolateRegion, showAllRegions, populateRegionList };