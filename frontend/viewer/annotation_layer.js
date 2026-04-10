/**
 * Brain_Scape — Annotation Layer (Phase 3)
 *
 * Collaborative annotation workspace for 3D brain meshes.
 * Uses Three.js Raycaster for click-on-mesh accuracy.
 * WebSocket for real-time sync with other connected clients.
 */

class AnnotationLayer {
    constructor(viewer, options = {}) {
        this.viewer = viewer;
        this.scene = viewer.scene;
        this.camera = viewer.camera;
        this.renderer = viewer.renderer;
        this.container = viewer.container;

        // Configuration
        this.wsUrl = options.wsUrl || `ws://${window.location.host}/ws/annotations`;
        this.apiBaseUrl = options.apiBaseUrl || '/api';
        this.scanId = options.scanId || null;
        this.authToken = options.authToken || null;

        // State
        this.annotations = new Map();  // id -> annotation
        this.selectedAnnotation = null;
        this.isAnnotating = false;
        this.currentColor = '#FFD700'; // Default: gold
        this.currentMarkerType = 'point';  // point, region, measurement

        // Raycaster
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        // WebSocket
        this.ws = null;
        this.wsConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        // UI elements
        this.annotationPanel = null;
        this.annotationList = null;
        this.annotationForm = null;

        this._init();
    }

    _init() {
        this._createUI();
        this._connectWebSocket();
        this._bindEvents();
    }

    // ── UI Creation ──

    _createUI() {
        // Annotation panel (side panel)
        this.annotationPanel = document.createElement('div');
        this.annotationPanel.id = 'annotation-panel';
        this.annotationPanel.style.cssText = `
            position: absolute; top: 0; right: -360px; width: 340px;
            height: 100%; background: #1a1a2e; color: #e0e0e0;
            border-left: 1px solid #333; overflow-y: auto;
            transition: right 0.3s ease; z-index: 100; padding: 16px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        `;

        // Header
        const header = document.createElement('div');
        header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;';
        header.innerHTML = `
            <h3 style="margin: 0; color: #00d4ff;">Annotations</h3>
            <button id="close-annotations" style="background: none; border: none; color: #aaa; font-size: 20px; cursor: pointer;">✕</button>
        `;
        this.annotationPanel.appendChild(header);

        // Annotation mode toggle
        const modeDiv = document.createElement('div');
        modeDiv.style.cssText = 'margin-bottom: 16px;';
        modeDiv.innerHTML = `
            <button id="toggle-annotate" style="
                width: 100%; padding: 10px; background: #00d4ff; color: #000;
                border: none; border-radius: 6px; font-weight: bold; cursor: pointer;
            ">Start Annotating</button>
        `;
        this.annotationPanel.appendChild(modeDiv);

        // Marker type selector
        const markerDiv = document.createElement('div');
        markerDiv.style.cssText = 'margin-bottom: 16px; display: flex; gap: 8px;';
        markerDiv.innerHTML = `
            <button class="marker-btn active" data-type="point" style="flex: 1; padding: 6px; background: #2d2d44; color: #00d4ff; border: 1px solid #00d4ff; border-radius: 4px; cursor: pointer;">Point</button>
            <button class="marker-btn" data-type="region" style="flex: 1; padding: 6px; background: #2d2d44; color: #aaa; border: 1px solid #555; border-radius: 4px; cursor: pointer;">Region</button>
            <button class="marker-btn" data-type="measurement" style="flex: 1; padding: 6px; background: #2d2d44; color: #aaa; border: 1px solid #555; border-radius: 4px; cursor: pointer;">Measure</button>
        `;
        this.annotationPanel.appendChild(markerDiv);

        // Annotation list
        this.annotationList = document.createElement('div');
        this.annotationList.id = 'annotation-list';
        this.annotationList.style.cssText = 'margin-bottom: 16px;';
        this.annotationPanel.appendChild(this.annotationList);

        // Annotation form (shown when creating)
        this.annotationForm = document.createElement('div');
        this.annotationForm.id = 'annotation-form';
        this.annotationForm.style.cssText = `
            display: none; padding: 12px; background: #2d2d44; border-radius: 6px;
        `;
        this.annotationForm.innerHTML = `
            <textarea id="annotation-comment" placeholder="Add a clinical note..."
                style="width: 100%; height: 80px; background: #1a1a2e; color: #e0e0e0;
                border: 1px solid #555; border-radius: 4px; padding: 8px; resize: vertical;"></textarea>
            <div style="display: flex; gap: 8px; margin-top: 8px;">
                <button id="save-annotation" style="flex: 1; padding: 8px; background: #27ae60; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Save</button>
                <button id="cancel-annotation" style="flex: 1; padding: 8px; background: #e74c3c; color: #fff; border: none; border-radius: 4px; cursor: pointer;">Cancel</button>
            </div>
        `;
        this.annotationPanel.appendChild(this.annotationForm);

        this.container.parentElement.appendChild(this.annotationPanel);
    }

    // ── WebSocket ──

    _connectWebSocket() {
        if (!this.scanId) return;

        try {
            const url = `${this.wsUrl}?scan_id=${this.scanId}`;
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                this.wsConnected = true;
                this.reconnectAttempts = 0;
                console.log('Annotation WebSocket connected');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this._handleWSMessage(data);
                } catch (e) {
                    console.error('Failed to parse WS message:', e);
                }
            };

            this.ws.onclose = () => {
                this.wsConnected = false;
                this._attemptReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('Annotation WebSocket error:', error);
            };
        } catch (e) {
            console.warn('WebSocket not available, annotations are local-only');
        }
    }

    _attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.warn('Max WebSocket reconnection attempts reached');
            return;
        }
        this.reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
        setTimeout(() => this._connectWebSocket(), delay);
    }

    _handleWSMessage(data) {
        switch (data.type) {
            case 'annotation_created':
                this._addAnnotationFromServer(data.annotation);
                break;
            case 'annotation_updated':
                this._updateAnnotationFromServer(data.annotation);
                break;
            case 'annotation_deleted':
                this._removeAnnotationFromServer(data.annotation_id);
                break;
            case 'user_joined':
                console.log(`User ${data.user_id} joined annotation session`);
                break;
            case 'user_left':
                console.log(`User ${data.user_id} left annotation session`);
                break;
        }
    }

    // ── Event Binding ──

    _bindEvents() {
        // Toggle annotation mode
        document.getElementById('toggle-annotate')?.addEventListener('click', () => {
            this.isAnnotating = !this.isAnnotating;
            const btn = document.getElementById('toggle-annotate');
            if (this.isAnnotating) {
                btn.textContent = 'Stop Annotating';
                btn.style.background = '#e74c3c';
            } else {
                btn.textContent = 'Start Annotating';
                btn.style.background = '#00d4ff';
            }
        });

        // Close panel
        document.getElementById('close-annotations')?.addEventListener('click', () => {
            this.annotationPanel.style.right = '-360px';
        });

        // Marker type buttons
        document.querySelectorAll('.marker-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.marker-btn').forEach(b => {
                    b.style.color = '#aaa';
                    b.style.borderColor = '#555';
                });
                btn.style.color = '#00d4ff';
                btn.style.borderColor = '#00d4ff';
                this.currentMarkerType = btn.dataset.type;
            });
        });

        // Save / Cancel annotation
        document.getElementById('save-annotation')?.addEventListener('click', () => {
            this._saveCurrentAnnotation();
        });
        document.getElementById('cancel-annotation')?.addEventListener('click', () => {
            this._cancelCurrentAnnotation();
        });

        // Click on mesh to annotate
        this.renderer.domElement.addEventListener('click', (event) => {
            if (!this.isAnnotating) return;
            this._handleMeshClick(event);
        });

        // Right-click panel toggle
        this.renderer.domElement.addEventListener('contextmenu', (event) => {
            event.preventDefault();
            this.annotationPanel.style.right = this.annotationPanel.style.right === '0px' ? '-360px' : '0px';
        });
    }

    // ── Click Handling ──

    _handleMeshClick(event) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);

        const intersects = this.raycaster.intersectObjects(this.viewer.meshGroup.children, true);
        if (intersects.length > 0) {
            const intersection = intersects[0];
            const faceIndex = intersection.faceIndex;
            const point = intersection.point;
            const face = intersection.face;

            // Get region name from atlas label
            const regionName = this._getRegionForFace(faceIndex);

            this._pendingAnnotation = {
                face_index: faceIndex,
                position: { x: point.x, y: point.y, z: point.z },
                region: regionName,
                marker_type: this.currentMarkerType,
            };

            // Show annotation form
            this.annotationForm.style.display = 'block';
            const commentField = document.getElementById('annotation-comment');
            commentField.value = '';
            commentField.focus();
            commentField.placeholder = `Add note about ${regionName || 'this region'}...`;

            // Place visual marker
            this._placeMarker(point, this.currentColor);
        }
    }

    _getRegionForFace(faceIndex) {
        // Look up the atlas region for this face
        if (this.viewer.regionLabels && this.viewer.regionLabels[faceIndex]) {
            return this.viewer.regionLabels[faceIndex];
        }
        return 'Unknown region';
    }

    _placeMarker(position, color) {
        const geometry = new THREE.SphereGeometry(0.02, 16, 16);
        const material = new THREE.MeshBasicMaterial({ color: color });
        const marker = new THREE.Mesh(geometry, material);
        marker.position.set(position.x, position.y, position.z);
        this.scene.add(marker);
        return marker;
    }

    // ── Annotation CRUD ──

    _saveCurrentAnnotation() {
        const comment = document.getElementById('annotation-comment')?.value || '';
        if (!this._pendingAnnotation) return;

        const annotation = {
            id: crypto.randomUUID(),
            scan_id: this.scanId,
            face_index: this._pendingAnnotation.face_index,
            position: this._pendingAnnotation.position,
            region: this._pendingAnnotation.region,
            marker_type: this._pendingAnnotation.marker_type,
            comment: comment,
            color: this.currentColor,
            version: 1,
            created_at: new Date().toISOString(),
            user_id: 'current-user',  // Set from auth
        };

        this.annotations.set(annotation.id, annotation);
        this._renderAnnotationList();
        this._broadcastAnnotation(annotation);

        // Save to server via REST
        this._saveToServer(annotation);

        // Reset form
        this.annotationForm.style.display = 'none';
        this._pendingAnnotation = null;
    }

    _cancelCurrentAnnotation() {
        this.annotationForm.style.display = 'none';
        this._pendingAnnotation = null;
    }

    _addAnnotationFromServer(annotation) {
        if (!this.annotations.has(annotation.id)) {
            this.annotations.set(annotation.id, annotation);
            this._placeMarker(
                new THREE.Vector3(annotation.position.x, annotation.position.y, annotation.position.z),
                annotation.color
            );
            this._renderAnnotationList();
        }
    }

    _updateAnnotationFromServer(annotation) {
        this.annotations.set(annotation.id, annotation);
        this._renderAnnotationList();
    }

    _removeAnnotationFromServer(annotationId) {
        this.annotations.delete(annotationId);
        this._renderAnnotationList();
    }

    _broadcastAnnotation(annotation) {
        if (this.ws && this.wsConnected) {
            this.ws.send(JSON.stringify({
                type: 'annotation_created',
                annotation: annotation,
            }));
        }
    }

    async _saveToServer(annotation) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/annotate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`,
                },
                body: JSON.stringify(annotation),
            });
            if (!response.ok) {
                console.error('Failed to save annotation:', response.statusText);
            }
        } catch (e) {
            console.error('Failed to save annotation:', e);
        }
    }

    // ── Render ──

    _renderAnnotationList() {
        if (!this.annotationList) return;
        this.annotationList.innerHTML = '';

        if (this.annotations.size === 0) {
            this.annotationList.innerHTML = '<p style="color: #666; text-align: center;">No annotations yet. Click on the brain to add one.</p>';
            return;
        }

        for (const [id, ann] of this.annotations) {
            const card = document.createElement('div');
            card.style.cssText = `
                background: #2d2d44; border-radius: 6px; padding: 10px;
                margin-bottom: 8px; border-left: 3px solid ${ann.color || '#FFD700'};
                cursor: pointer;
            `;
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div>
                        <span style="color: #00d4ff; font-size: 12px;">${ann.marker_type || 'point'}</span>
                        <span style="color: #888; font-size: 11px; margin-left: 8px;">${ann.region || ''}</span>
                    </div>
                    <span style="color: #666; font-size: 10px;">v${ann.version || 1}</span>
                </div>
                <p style="margin: 4px 0 0; color: #e0e0e0; font-size: 13px;">${ann.comment || '(no comment)'}</p>
            `;
            card.addEventListener('click', () => this._selectAnnotation(id));
            card.addEventListener('mouseenter', () => card.style.background = '#3d3d54');
            card.addEventListener('mouseleave', () => card.style.background = '#2d2d44');
            this.annotationList.appendChild(card);
        }
    }

    _selectAnnotation(id) {
        this.selectedAnnotation = id;
        const ann = this.annotations.get(id);
        if (ann && ann.position) {
            // Fly camera to annotation
            const target = new THREE.Vector3(ann.position.x, ann.position.y, ann.position.z);
            this.viewer.controls.target.copy(target);
            this.viewer.controls.update();
        }
        // Highlight in list
        this.annotationList.querySelectorAll('div').forEach(el => {
            el.style.outline = 'none';
        });
        const selected = this.annotationList.querySelector(`[data-id="${id}"]`);
        if (selected) selected.style.outline = '2px solid #00d4ff';
    }

    // ── Public API ──

    togglePanel() {
        if (this.annotationPanel.style.right === '0px') {
            this.annotationPanel.style.right = '-360px';
        } else {
            this.annotationPanel.style.right = '0px';
        }
    }

    loadAnnotations(annotations) {
        annotations.forEach(ann => {
            this.annotations.set(ann.id, ann);
            this._placeMarker(
                new THREE.Vector3(ann.position.x, ann.position.y, ann.position.z),
                ann.color || '#FFD700'
            );
        });
        this._renderAnnotationList();
    }

    getAnnotations() {
        return Array.from(this.annotations.values());
    }

    destroy() {
        if (this.ws) {
            this.ws.close();
        }
        this.annotationPanel.remove();
    }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AnnotationLayer };
}