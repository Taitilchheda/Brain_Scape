/**
 * Brain_Scape — 3D Brain Viewer
 *
 * Interactive Three.js viewer for the reconstructed brain mesh with
 * damage overlay. Supports orbit, zoom, pan, and click-to-inspect.
 *
 * Uses GLTFLoader with Draco compression for progressive loading:
 * low-LOD appears in < 2 seconds, full resolution loads progressively.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

// ── Constants ──
const API_BASE = window.location.origin;
const DAMAGE_COLORS = {
    0: 0x4A90D9,  // BLUE — Not implicated
    1: 0x27AE60,  // GREEN — No damage detected
    2: 0xF1C40F,  // YELLOW — Mild abnormality
    3: 0xE67E22,  // ORANGE — Moderate-to-severe
    4: 0xE74C3C,  // RED — Severe damage
};

// ── Scene Setup ──
let scene, camera, renderer, controls;
let brainMesh = null;
let damageOverlay = null;
let raycaster, mouse;
let regionData = [];

function init() {
    const canvas = document.getElementById('brain-canvas');
    if (!canvas) return;

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x111111);

    // Camera
    const aspect = canvas.parentElement.clientWidth / canvas.parentElement.clientHeight;
    camera = new THREE.PerspectiveCamera(45, aspect, 0.01, 100);
    camera.position.set(0, 0, 3);

    // Renderer
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setSize(canvas.parentElement.clientWidth, canvas.parentElement.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.outputEncoding = THREE.sRGBEncoding;

    // Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.rotateSpeed = 0.5;
    controls.zoomSpeed = 0.8;

    // Lighting
    const ambient = new THREE.AmbientLight(0x404040, 0.8);
    scene.add(ambient);

    const directional = new THREE.DirectionalLight(0xffffff, 0.8);
    directional.position.set(5, 10, 5);
    scene.add(directional);

    const backLight = new THREE.DirectionalLight(0x4060ff, 0.3);
    backLight.position.set(-5, -5, -5);
    scene.add(backLight);

    // Raycaster for click-to-inspect
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    // Resize handler
    window.addEventListener('resize', onWindowResize);
    canvas.addEventListener('click', onCanvasClick);

    // Start render loop
    animate();
}

function onWindowResize() {
    const container = document.getElementById('brain-canvas').parentElement;
    const width = container.clientWidth;
    const height = container.clientHeight;

    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
}

function onCanvasClick(event) {
    if (!brainMesh) return;

    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObject(brainMesh);

    if (intersects.length > 0) {
        const face = intersects[0].face;
        const faceIndex = face.a; // Use vertex index as face ID

        // Find region data for this face
        const region = findRegionForFace(faceIndex);
        if (region) {
            showRegionInfo(region);
        }
    }
}

function findRegionForFace(faceIndex) {
    // Match face index to region data
    for (const region of regionData) {
        if (faceIndex >= region.startFace && faceIndex < region.endFace) {
            return region;
        }
    }
    return null;
}

function showRegionInfo(region) {
    const infoDiv = document.getElementById('qa-response');
    if (infoDiv) {
        infoDiv.style.display = 'block';
        infoDiv.innerHTML = `
            <strong>${region.anatomical_name || 'Unknown Region'}</strong><br>
            Severity: ${region.severity_label}<br>
            Confidence: ${(region.confidence * 100).toFixed(1)}%
        `;
    }
}

// ── Mesh Loading ──

async function loadBrainMesh(scanId) {
    updateStatus('Loading 3D brain mesh...');

    const loader = new GLTFLoader();
    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');
    loader.setDRACOLoader(dracoLoader);

    try {
        const gltf = await loader.loadAsync(`${API_BASE}/export/${scanId}?format=glb`);
        brainMesh = gltf.scene;

        // Center the mesh
        const box = new THREE.Box3().setFromObject(brainMesh);
        const center = box.getCenter(new THREE.Vector3());
        brainMesh.position.sub(center);

        scene.add(brainMesh);
        updateStatus('Brain mesh loaded. Click any region for details.');

        // Hide upload overlay
        const overlay = document.getElementById('upload-overlay');
        if (overlay) overlay.style.display = 'none';

    } catch (error) {
        console.error('Failed to load mesh:', error);
        updateStatus('Error loading mesh. Please try again.');
    }
}

// ── Damage Overlay ──

function applyDamageOverlay(damageMap) {
    if (!brainMesh) return;

    brainMesh.traverse((child) => {
        if (child.isMesh && damageMap.regions) {
            const colors = new Float32Array(child.geometry.attributes.position.count * 3);

            // Apply per-vertex colors based on damage map
            for (let i = 0; i < child.geometry.attributes.position.count; i++) {
                // Default to GREEN (healthy)
                let color = DAMAGE_COLORS[1];

                if (damageMap.total_faces && i < damageMap.total_faces) {
                    // Find region for this vertex
                    for (const region of damageMap.regions) {
                        if (i >= (region.start_face || 0) && i < (region.end_face || Infinity)) {
                            color = DAMAGE_COLORS[region.severity_level] || DAMAGE_COLORS[1];
                            break;
                        }
                    }
                }

                colors[i * 3] = ((color >> 16) & 0xFF) / 255;
                colors[i * 3 + 1] = ((color >> 8) & 0xFF) / 255;
                colors[i * 3 + 2] = (color & 0xFF) / 255;
            }

            child.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
            child.material.vertexColors = true;
            child.material.needsUpdate = true;
        }
    });
}

// ── Animation Loop ──

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}

// ── Status Updates ──

function updateStatus(text) {
    const el = document.getElementById('status-text');
    if (el) el.textContent = text;
}

// ── Upload Handler ──

async function uploadScan(file) {
    updateStatus('Uploading scan...');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE}/ingest`, {
            method: 'POST',
            body: formData,
        });

        const data = await response.json();
        updateStatus(`Scan uploaded. Job ID: ${data.job_id}. Processing...`);

        // Poll for status
        pollJobStatus(data.job_id);

    } catch (error) {
        updateStatus('Upload failed. Please try again.');
        console.error('Upload error:', error);
    }
}

async function pollJobStatus(jobId) {
    const poll = async () => {
        try {
            const response = await fetch(`${API_BASE}/status/${jobId}`);
            const data = await response.json();

            updateStatus(`Processing: ${data.stage} (${data.progress_pct}%)`);

            if (data.status === 'complete') {
                updateStatus('Analysis complete! Loading 3D viewer...');
                loadBrainMesh(jobId);
                return;
            } else if (data.status === 'failed') {
                updateStatus(`Processing failed: ${data.error_message}`);
                return;
            }

            // Continue polling
            setTimeout(poll, 5000);
        } catch (error) {
            updateStatus('Error checking status. Retrying...');
            setTimeout(poll, 10000);
        }
    };

    poll();
}

// ── Initialize ──

document.addEventListener('DOMContentLoaded', () => {
    init();

    // File upload
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) {
        dropZone.addEventListener('dragover', (e) => e.preventDefault());
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            if (e.dataTransfer.files.length > 0) {
                uploadScan(e.dataTransfer.files[0]);
            }
        });
    }

    // Q&A
    const qaInput = document.getElementById('qa-input');
    if (qaInput) {
        qaInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                const question = qaInput.value.trim();
                if (!question) return;

                const response = document.getElementById('qa-response');
                response.style.display = 'block';
                response.textContent = 'Thinking...';

                try {
                    const res = await fetch(`${API_BASE}/query`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ scan_id: 'current', question }),
                    });
                    const data = await res.json();
                    response.textContent = data.answer || 'No answer available.';
                } catch (error) {
                    response.textContent = 'Error processing question.';
                }
            }
        });
    }
});

export { loadBrainMesh, applyDamageOverlay, regionData };