        import * as THREE from "https://esm.sh/three@0.163.0";
        import { OrbitControls } from "https://esm.sh/three@0.163.0/examples/jsm/controls/OrbitControls.js";
        import { OBJLoader } from "https://esm.sh/three@0.163.0/examples/jsm/loaders/OBJLoader.js";
        import { GLTFLoader } from "https://esm.sh/three@0.163.0/examples/jsm/loaders/GLTFLoader.js";
        import * as BufferGeometryUtils from "https://esm.sh/three@0.163.0/examples/jsm/utils/BufferGeometryUtils.js";

        const API_BASE = window.__BRAINGSCAPE_API_BASE__ || window.__BRAINSCAPE_API_BASE__ || window.location.origin;
        const SURFACE_MESH_QUALITY = "extreme";
        const VOLUME_RENDER_RESOLUTION = "extreme";
        const DICOM_VOLUME_RESOLUTION = "extreme";
        const DICOM_TARGET_RENDER_EDGE = 1024;
        const DICOM_MAX_RENDER_EDGE = 1280;
        let authToken = localStorage.getItem("brainscape_token") || "";
        let currentScanId = null;
        let analysisData = null;
        let demoPatients = [];
        let selectedPatientId = "";
        let compareTargetPatientId = "";
        let clinicalGovernance = null;
        const PANEL_MODES = new Set(["all", "worklist", "findings", "dicom", "planning"]);
        let activePanelMode = "all";
        let comparisonScanCache = new Map();

        const DAMAGE_COLORS = {
            0: 0x4A90D9,
            1: 0x27AE60,
            2: 0xF1C40F,
            3: 0xE67E22,
            4: 0xE74C3C,
        };
        const SEVERITY_HEX = {
            0: "#4A90D9",
            1: "#27AE60",
            2: "#F1C40F",
            3: "#E67E22",
            4: "#E74C3C",
        };
        const SEVERITY_LABELS = {
            0: "Not implicated",
            1: "Healthy",
            2: "Mild",
            3: "Moderate",
            4: "Severe",
        };
        const RISK_LABELS = {
            high: "high",
            moderate: "moderate",
            low: "low",
        };
        let visibleLevels = new Set([0, 1, 2, 3, 4]);

        let scene;
        let camera;
        let renderer;
        let controls;
        let brainGroup = null;
        let volumeGroup = null;
        let volumeTexture = null;
        let volumeMaterials = [];
        let activeRenderMode = "hybrid";
        let volumeUsesSyntheticFallback = false;
        const objLoader = new OBJLoader();
        const gltfLoader = new GLTFLoader();
        let raycaster;
        let pointer;
        let viewerFocusMarker = null;
        let activeDicomStudy = null;
        let activeDicomVolume = null;
        let dicomCineTimer = null;

        const DICOM_FALLBACK_PRESETS = {
            brain: { window_width: 80, window_center: 40 },
            stroke: { window_width: 40, window_center: 35 },
            subdural: { window_width: 240, window_center: 80 },
            bone: { window_width: 2800, window_center: 600 },
        };

        const dicomState = {
            plane: "axial",
            preset: "brain",
            seriesUid: "",
            slice: 1,
            maxSlice: 1,
            ww: 80,
            wc: 40,
            invert: false,
            crosshair: true,
            measuring: false,
            measureTool: "distance",
            measureStart: null,
            measureEnd: null,
            measurePreview: null,
            measurePoints: [],
            measureAreaClosed: false,
            frameWidth: 1,
            frameHeight: 1,
        };

        const DICOM_CONTEXT_PRESETS = {
            auto: { preset: "brain", ww: 90, wc: 42 },
            brain: { preset: "brain", ww: 80, wc: 40 },
            stroke: { preset: "stroke", ww: 42, wc: 34 },
            flair: { preset: "brain", ww: 320, wc: 80 },
            subdural: { preset: "subdural", ww: 240, wc: 80 },
            bone: { preset: "bone", ww: 2800, wc: 600 },
            vascular: { preset: "bone", ww: 680, wc: 180 },
        };

        const CRITICAL_STRUCTURE_PROFILES = {
            speech: {
                label: "Language cortex",
                points: [
                    { x: -0.62, y: 0.32, z: 0.20 },
                    { x: -0.52, y: 0.18, z: 0.36 },
                ],
            },
            motor: {
                label: "Primary motor strip",
                points: [
                    { x: -0.48, y: 0.46, z: 0.16 },
                    { x: 0.48, y: 0.46, z: 0.16 },
                ],
            },
            visual: {
                label: "Visual pathways",
                points: [
                    { x: -0.32, y: -0.22, z: -0.74 },
                    { x: 0.32, y: -0.22, z: -0.74 },
                ],
            },
            vascular: {
                label: "Major vascular corridor",
                points: [
                    { x: -0.08, y: 0.02, z: 0.14 },
                    { x: 0.08, y: -0.06, z: 0.08 },
                ],
            },
        };

        const clinicalState = {
            linkedNav: true,
            navVoxel: { x: 0, y: 0, z: 0 },
            segmentation: {
                scanId: "",
                lesionVisible: true,
                edemaVisible: true,
                uncertaintyVisible: true,
                editMode: false,
                editClass: "lesion",
                tool: "brush",
                brushRadius: 2,
                pointerDown: false,
                lesionMask: null,
                edemaMask: null,
                uncertaintyMask: null,
            },
            trajectory: {
                activeMode: "",
                entry: null,
                target: null,
                visual: null,
            },
        };

        function normalizeRegions(data) {
            if (!data) return [];
            if (Array.isArray(data.regions)) return data.regions;
            if (Array.isArray(data.damage_summary)) return data.damage_summary;
            return [];
        }

        function getStringSeed(value) {
            return String(value || "demo").split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
        }

        function regionMatchesCoordinate(regionName, x, y, z) {
            const name = String(regionName || "").toLowerCase();
            const isLeft = name.includes("_l") || name.includes("left");
            const isRight = name.includes("_r") || name.includes("right");

            if (name.includes("hippocamp") && isLeft && y < 0 && x < 0) return true;
            if (name.includes("hippocamp") && isRight && y < 0 && x > 0) return true;
            if (name.includes("precentral") && isLeft && y > 0.2 && x < 0) return true;
            if (name.includes("precentral") && isRight && y > 0.2 && x > 0) return true;
            if (name.includes("frontal") && isLeft && y > 0 && x < 0) return true;
            if (name.includes("frontal") && isRight && y > 0 && x > 0) return true;
            if (name.includes("temporal") && isLeft && y < -0.1 && x < 0) return true;
            if (name.includes("temporal") && isRight && y < -0.1 && x > 0) return true;
            if (name.includes("parietal") && y > 0.3) return true;
            if (name.includes("occipital") && z < -0.5) return true;
            return false;
        }

        function resolveSeverityLevel(regions, x, y, z) {
            let severityLevel = 1;
            for (const region of regions) {
                const level = region.severity_level || 0;
                if (regionMatchesCoordinate(region.anatomical_name, x, y, z) && level > severityLevel) {
                    severityLevel = level;
                }
            }
            return severityLevel;
        }

        function inferRegionFromPoint(regions, x, y, z) {
            let topRegion = null;
            let topScore = -1;
            for (const region of regions) {
                if (!regionMatchesCoordinate(region.anatomical_name, x, y, z)) continue;
                const severity = region.severity_level || 0;
                const confidence = region.confidence || 0;
                const score = (severity * 10) + confidence;
                if (score > topScore) {
                    topScore = score;
                    topRegion = region;
                }
            }
            return topRegion;
        }

        function clampValue(value, min, max) {
            return Math.max(min, Math.min(max, value));
        }

        function getVolumeIndex(volume, x, y, z) {
            if (!volume) return -1;
            if (x < 0 || y < 0 || z < 0 || x >= volume.width || y >= volume.height || z >= volume.depth) {
                return -1;
            }
            return (z * volume.height * volume.width) + (y * volume.width) + x;
        }

        function getNavSliceForPlane(plane) {
            if (!activeDicomVolume) return 1;
            if (plane === "coronal") return clampValue(clinicalState.navVoxel.y + 1, 1, activeDicomVolume.height);
            if (plane === "sagittal") return clampValue(clinicalState.navVoxel.x + 1, 1, activeDicomVolume.width);
            return clampValue(clinicalState.navVoxel.z + 1, 1, activeDicomVolume.depth);
        }

        function normalizedToVoxel(volume, point) {
            if (!volume || !point) return { x: 0, y: 0, z: 0 };
            return {
                x: clampValue(Math.round(((point.x + 1) * 0.5) * (volume.width - 1)), 0, volume.width - 1),
                y: clampValue(Math.round(((1 - (point.y + 1) * 0.5)) * (volume.height - 1)), 0, volume.height - 1),
                z: clampValue(Math.round(((point.z + 1) * 0.5) * (volume.depth - 1)), 0, volume.depth - 1),
            };
        }

        function voxelToNormalized(volume, voxel) {
            if (!volume || !voxel) return { x: 0, y: 0, z: 0 };
            const widthBase = Math.max(1, volume.width - 1);
            const heightBase = Math.max(1, volume.height - 1);
            const depthBase = Math.max(1, volume.depth - 1);
            return {
                x: ((voxel.x / widthBase) * 2) - 1,
                y: 1 - ((voxel.y / heightBase) * 2),
                z: ((voxel.z / depthBase) * 2) - 1,
            };
        }

        function clampNavVoxelToVolume() {
            if (!activeDicomVolume) {
                clinicalState.navVoxel = { x: 0, y: 0, z: 0 };
                return;
            }
            clinicalState.navVoxel.x = clampValue(clinicalState.navVoxel.x, 0, activeDicomVolume.width - 1);
            clinicalState.navVoxel.y = clampValue(clinicalState.navVoxel.y, 0, activeDicomVolume.height - 1);
            clinicalState.navVoxel.z = clampValue(clinicalState.navVoxel.z, 0, activeDicomVolume.depth - 1);
        }

        function setNavVoxelToVolumeCenter() {
            if (!activeDicomVolume) {
                clinicalState.navVoxel = { x: 0, y: 0, z: 0 };
                return;
            }
            clinicalState.navVoxel = {
                x: Math.floor((activeDicomVolume.width - 1) / 2),
                y: Math.floor((activeDicomVolume.height - 1) / 2),
                z: Math.floor((activeDicomVolume.depth - 1) / 2),
            };
        }

        function setDicomSliceInputValue(nextSlice) {
            const sliceSlider = document.getElementById("dicom-slice-slider");
            if (sliceSlider) {
                sliceSlider.value = String(nextSlice);
            }
        }

        function syncMainSliceFromNav(preferredPlane = "") {
            if (!activeDicomVolume) return;
            if (preferredPlane && ["axial", "coronal", "sagittal"].includes(preferredPlane)) {
                dicomState.plane = preferredPlane;
            }
            const nextSlice = getNavSliceForPlane(dicomState.plane);
            dicomState.slice = nextSlice;
            setDicomSliceInputValue(nextSlice);
        }

        function mapPlanePointToVoxel(plane, sliceIndex, point, frame) {
            if (!activeDicomVolume) return null;

            const sx = clampValue(Math.round(point.x), 0, frame.width - 1);
            const sy = clampValue(Math.round(point.y), 0, frame.height - 1);
            let x = 0;
            let y = 0;
            let z = 0;

            if (plane === "coronal") {
                x = sx;
                y = clampValue(sliceIndex, 0, activeDicomVolume.height - 1);
                z = (frame.height - 1) - sy;
            } else if (plane === "sagittal") {
                x = clampValue(sliceIndex, 0, activeDicomVolume.width - 1);
                y = sx;
                z = (frame.height - 1) - sy;
            } else {
                x = sx;
                y = (frame.height - 1) - sy;
                z = clampValue(sliceIndex, 0, activeDicomVolume.depth - 1);
            }

            return {
                x: clampValue(x, 0, activeDicomVolume.width - 1),
                y: clampValue(y, 0, activeDicomVolume.height - 1),
                z: clampValue(z, 0, activeDicomVolume.depth - 1),
            };
        }

        function mapPlaneSampleToVoxelIndex(plane, sliceIndex, sampleX, sampleY, frame) {
            if (!activeDicomVolume) return -1;

            const sx = clampValue(Math.round(sampleX), 0, frame.width - 1);
            const sy = clampValue(Math.round(sampleY), 0, frame.height - 1);
            let x = 0;
            let y = 0;
            let z = 0;

            if (plane === "coronal") {
                x = sx;
                y = clampValue(sliceIndex, 0, activeDicomVolume.height - 1);
                z = (frame.height - 1) - sy;
            } else if (plane === "sagittal") {
                x = clampValue(sliceIndex, 0, activeDicomVolume.width - 1);
                y = sx;
                z = (frame.height - 1) - sy;
            } else {
                x = sx;
                y = (frame.height - 1) - sy;
                z = clampValue(sliceIndex, 0, activeDicomVolume.depth - 1);
            }

            return getVolumeIndex(
                activeDicomVolume,
                clampValue(x, 0, activeDicomVolume.width - 1),
                clampValue(y, 0, activeDicomVolume.height - 1),
                clampValue(z, 0, activeDicomVolume.depth - 1),
            );
        }

        function projectVoxelToPlanePoint(plane, voxel, frame) {
            if (!voxel || !frame) return { x: 0, y: 0 };
            if (plane === "coronal") {
                return {
                    x: clampValue(voxel.x, 0, frame.width - 1),
                    y: clampValue((frame.height - 1) - voxel.z, 0, frame.height - 1),
                };
            }
            if (plane === "sagittal") {
                return {
                    x: clampValue(voxel.y, 0, frame.width - 1),
                    y: clampValue((frame.height - 1) - voxel.z, 0, frame.height - 1),
                };
            }
            return {
                x: clampValue(voxel.x, 0, frame.width - 1),
                y: clampValue((frame.height - 1) - voxel.y, 0, frame.height - 1),
            };
        }

        function syncNavFromActiveDicomSlice() {
            if (!activeDicomVolume) return;
            const sliceIndex = clampValue(Math.round((dicomState.slice || 1) - 1), 0, dicomState.maxSlice - 1);
            if (dicomState.plane === "coronal") {
                clinicalState.navVoxel.y = sliceIndex;
            } else if (dicomState.plane === "sagittal") {
                clinicalState.navVoxel.x = sliceIndex;
            } else {
                clinicalState.navVoxel.z = sliceIndex;
            }
            clampNavVoxelToVolume();
        }

        function focus3DOnCurrentCrosshair() {
            if (!scene || !activeDicomVolume) return;

            const point = voxelToNormalized(activeDicomVolume, clinicalState.navVoxel);
            clearViewerFocus();

            const markerGeo = new THREE.SphereGeometry(0.03, 16, 16);
            const markerMat = new THREE.MeshStandardMaterial({ color: 0x278ed8, emissive: 0x145786, emissiveIntensity: 0.2 });
            viewerFocusMarker = new THREE.Mesh(markerGeo, markerMat);
            viewerFocusMarker.position.set(point.x, point.y, point.z);
            scene.add(viewerFocusMarker);

            if (controls) {
                controls.target.set(point.x, point.y, point.z);
                controls.update();
            }

            updateViewerPickInfo(`Crosshair focus synced to 3D: (${point.x.toFixed(2)}, ${point.y.toFixed(2)}, ${point.z.toFixed(2)})`);
        }

        function initScene() {
            const canvas = document.getElementById("brain-canvas");
            if (!canvas) return;

            scene = new THREE.Scene();
            scene.background = new THREE.Color(0xf3f7fd);

            const container = canvas.parentElement;
            camera = new THREE.PerspectiveCamera(44, container.clientWidth / container.clientHeight, 0.01, 100);
            camera.position.set(0, 0, 3);

            renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
            renderer.setSize(container.clientWidth, container.clientHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
            renderer.localClippingEnabled = true;
            renderer.toneMapping = THREE.ACESFilmicToneMapping;
            renderer.toneMappingExposure = 1.1;
            if ("outputColorSpace" in renderer) {
                renderer.outputColorSpace = THREE.SRGBColorSpace;
            }

            controls = new OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.rotateSpeed = 0.48;
            controls.autoRotate = false;
            controls.autoRotateSpeed = 1.2;

            raycaster = new THREE.Raycaster();
            pointer = new THREE.Vector2();

            scene.add(new THREE.HemisphereLight(0xf8fcff, 0x9db2c8, 0.78));
            const keyLight = new THREE.DirectionalLight(0xffffff, 0.94);
            keyLight.position.set(5, 9, 6);
            scene.add(keyLight);
            const fillLight = new THREE.DirectionalLight(0xaecbef, 0.5);
            fillLight.position.set(-5, -3, -4);
            scene.add(fillLight);
            const rimLight = new THREE.DirectionalLight(0xe7f2ff, 0.44);
            rimLight.position.set(-2, 3, 7);
            scene.add(rimLight);

            canvas.addEventListener("click", handleBrainCanvasClick);

            window.addEventListener("resize", () => {
                const c = canvas.parentElement;
                camera.aspect = c.clientWidth / c.clientHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(c.clientWidth, c.clientHeight);
                renderDicomSlice();
            });

            animate();
        }

        function animate() {
            requestAnimationFrame(animate);
            if (controls) controls.update();
            if (renderer && scene && camera) renderer.render(scene, camera);
        }

        function setViewerCameraPreset(mode) {
            if (!camera || !controls) return;
            const presets = {
                reset: [0, 0, 3],
                left: [-3, 0, 0],
                right: [3, 0, 0],
                top: [0, 3, 0],
                front: [0, 0, 3],
            };
            const target = presets[mode] || presets.reset;
            camera.position.set(target[0], target[1], target[2]);
            controls.target.set(0, 0, 0);
            controls.update();
        }

        function updateAutoRotateButton() {
            const button = document.getElementById("btn-auto-rotate");
            if (!button || !controls) return;
            button.classList.toggle("active", controls.autoRotate);
            button.textContent = controls.autoRotate ? "Auto Rotate On" : "Auto Rotate Off";
        }

        function toggleAutoRotate() {
            if (!controls) return;
            controls.autoRotate = !controls.autoRotate;
            updateAutoRotateButton();
        }

        function clearViewerFocus() {
            if (viewerFocusMarker && scene) {
                scene.remove(viewerFocusMarker);
                viewerFocusMarker = null;
            }
        }

        function updateViewerPickInfo(message) {
            const info = document.getElementById("viewer-pick-info");
            if (!info) return;
            info.textContent = message;
        }

        function updateRenderModeButtons() {
            const modeButtons = {
                hybrid: document.getElementById("btn-render-hybrid"),
                volume: document.getElementById("btn-render-volume"),
                surface: document.getElementById("btn-render-surface"),
            };

            Object.entries(modeButtons).forEach(([mode, button]) => {
                if (!button) return;
                button.classList.toggle("active", mode === activeRenderMode);
            });
        }

        function setRenderMode(mode) {
            activeRenderMode = mode;
            const showSurface = mode !== "volume";
            const showVolume = mode !== "surface";

            if (brainGroup) {
                brainGroup.visible = showSurface;
            }

            if (volumeGroup) {
                volumeGroup.visible = showVolume;
                volumeGroup.children.forEach((sliceMesh) => {
                    const clipVisible = sliceMesh.userData.clipVisible !== false;
                    sliceMesh.visible = showVolume && clipVisible;
                });
            }

            updateRenderModeButtons();
        }

        function decodeBase64ToUint8Array(encoded) {
            const binary = atob(encoded || "");
            const output = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                output[i] = binary.charCodeAt(i);
            }
            return output;
        }

        function disposeVolumeRenderAssets() {
            if (volumeGroup && scene) {
                scene.remove(volumeGroup);
            }

            if (volumeGroup) {
                volumeGroup.traverse((child) => {
                    if (child.isMesh) {
                        child.geometry?.dispose();
                    }
                });
            }

            volumeMaterials.forEach((material) => material.dispose());
            volumeMaterials = [];
            volumeGroup = null;

            if (volumeTexture) {
                volumeTexture.dispose();
                volumeTexture = null;
            }
        }

        async function fetchVolumePayload(scanId, resolution = "standard") {
            const params = new URLSearchParams();
            if (resolution) {
                params.set("resolution", resolution);
            }
            const query = params.toString() ? `?${params.toString()}` : "";
            const response = await fetch(`${API_BASE}/volume/${encodeURIComponent(scanId)}${query}`);
            if (!response.ok) {
                throw new Error(`Volume endpoint failed (${response.status})`);
            }
            return response.json();
        }

        function computeDamageVisibilityFactor() {
            const highlighted = [2, 3, 4].filter((level) => visibleLevels.has(level)).length;
            if (highlighted <= 0) return 0;
            return highlighted / 3;
        }

        function updateVolumeDamageVisibility() {
            const visibility = computeDamageVisibilityFactor();
            volumeMaterials.forEach((material) => {
                if (!material?.uniforms?.uDamageVisibility) return;
                material.uniforms.uDamageVisibility.value = visibility;
            });
        }

        function buildVolumeSlices(volumePayload) {
            const shape = Array.isArray(volumePayload?.shape) ? volumePayload.shape : [96, 96, 96];
            const spacing = Array.isArray(volumePayload?.spacing_mm) ? volumePayload.spacing_mm : [1, 1, 1];
            const [sx, sy, sz] = shape.map((value) => Math.max(1, Number(value) || 1));

            const packed = decodeBase64ToUint8Array(volumePayload.volume_b64);
            const expectedLength = sx * sy * sz * 4;
            if (packed.length !== expectedLength) {
                throw new Error(`Unexpected volume payload size. expected=${expectedLength} got=${packed.length}`);
            }

            const texture = new THREE.Data3DTexture(packed, sx, sy, sz);
            texture.format = THREE.RGBAFormat;
            texture.type = THREE.UnsignedByteType;
            texture.minFilter = THREE.LinearFilter;
            texture.magFilter = THREE.LinearFilter;
            texture.unpackAlignment = 1;
            texture.generateMipmaps = false;
            texture.needsUpdate = true;

            const scaleX = sx * Number(spacing[0] || 1.0);
            const scaleY = sy * Number(spacing[1] || 1.0);
            const scaleZ = sz * Number(spacing[2] || 1.0);
            const maxScale = Math.max(scaleX, scaleY, scaleZ, 1e-6);

            const group = new THREE.Group();
            group.scale.set(scaleX / maxScale, scaleY / maxScale, scaleZ / maxScale);

            const damageVisibility = computeDamageVisibilityFactor();
            const densityBoost = volumePayload?.synthetic_fallback ? 1.3 : 1.78;
            const voxelStep = new THREE.Vector3(1 / sx, 1 / sy, 1 / sz);

            const axialCount = Math.max(84, Math.min(128, Math.floor(sz * 0.62)));
            const coronalCount = Math.max(42, Math.min(72, Math.floor(sy * 0.34)));
            const sagittalCount = Math.max(42, Math.min(72, Math.floor(sx * 0.34)));

            const createSliceMaterial = (axis, slice, axisCount, opacityWeight) => {
                return new THREE.ShaderMaterial({
                    uniforms: {
                        uVolume: { value: texture },
                        uSlice: { value: slice },
                        uAxis: { value: axis },
                        uVoxelStep: { value: voxelStep },
                        uOpacity: { value: ((6.0 / Math.max(1, axisCount)) * densityBoost) * opacityWeight },
                        uDamageVisibility: { value: damageVisibility },
                    },
                    vertexShader: `
                        varying vec2 vUv;
                        void main() {
                            vUv = uv;
                            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                        }
                    `,
                    fragmentShader: `
                        precision highp float;
                        precision highp sampler3D;
                        uniform sampler3D uVolume;
                        uniform float uSlice;
                        uniform float uAxis;
                        uniform vec3 uVoxelStep;
                        uniform float uOpacity;
                        uniform float uDamageVisibility;
                        varying vec2 vUv;

                        vec3 samplePosition() {
                            if (uAxis < 0.5) {
                                return vec3(vUv, uSlice);          // axial (z)
                            }
                            if (uAxis < 1.5) {
                                return vec3(vUv.x, uSlice, 1.0 - vUv.y); // coronal (y)
                            }
                            return vec3(uSlice, vUv.x, 1.0 - vUv.y);     // sagittal (x)
                        }

                        void main() {
                            vec3 samplePos = samplePosition();
                            vec4 sampleValue = texture(uVolume, samplePos);
                            float intensity = sampleValue.r;
                            float grayMatter = sampleValue.g;
                            float whiteMatter = sampleValue.b;
                            float damage = sampleValue.a * uDamageVisibility;
                            float tissue = max(grayMatter, whiteMatter);
                            float anatomy = max(intensity, tissue * 0.94);

                            vec3 sx0 = vec3(clamp(samplePos.x - uVoxelStep.x, 0.0, 1.0), samplePos.y, samplePos.z);
                            vec3 sx1 = vec3(clamp(samplePos.x + uVoxelStep.x, 0.0, 1.0), samplePos.y, samplePos.z);
                            vec3 sy0 = vec3(samplePos.x, clamp(samplePos.y - uVoxelStep.y, 0.0, 1.0), samplePos.z);
                            vec3 sy1 = vec3(samplePos.x, clamp(samplePos.y + uVoxelStep.y, 0.0, 1.0), samplePos.z);
                            vec3 sz0 = vec3(samplePos.x, samplePos.y, clamp(samplePos.z - uVoxelStep.z, 0.0, 1.0));
                            vec3 sz1 = vec3(samplePos.x, samplePos.y, clamp(samplePos.z + uVoxelStep.z, 0.0, 1.0));

                            float gx = texture(uVolume, sx1).r - texture(uVolume, sx0).r;
                            float gy = texture(uVolume, sy1).r - texture(uVolume, sy0).r;
                            float gz = texture(uVolume, sz1).r - texture(uVolume, sz0).r;
                            vec3 normal = normalize(vec3(gx, gy, gz + 1e-4));
                            vec3 lightDir = normalize(vec3(-0.32, 0.44, 0.84));
                            float lambert = 0.42 + (0.58 * max(dot(normal, lightDir), 0.0));
                            float rim = pow(1.0 - max(dot(normal, vec3(0.0, 0.0, 1.0)), 0.0), 2.0);

                            if (anatomy < 0.012 && damage < 0.006) {
                                discard;
                            }

                            float anatomyResponse = smoothstep(0.02, 0.98, pow(anatomy, 1.14));
                            vec3 anatomyGray = vec3(0.10 + (0.90 * pow(intensity, 1.05)));
                            vec3 grayColor = vec3(0.56, 0.62, 0.72) * (0.35 + (0.65 * grayMatter));
                            vec3 whiteColor = vec3(0.92, 0.94, 0.98) * (0.45 + (0.55 * whiteMatter));
                            vec3 tissueColor = mix(grayColor, whiteColor, clamp(whiteMatter, 0.0, 1.0));
                            vec3 baseColor = mix(anatomyGray, tissueColor, 0.56);
                            baseColor *= (lambert + (rim * 0.08));

                            vec3 damageColor = mix(vec3(0.96, 0.78, 0.16), vec3(0.94, 0.18, 0.12), clamp(damage * 1.2, 0.0, 1.0));
                            vec3 finalColor = mix(baseColor, damageColor, clamp(damage * 0.56, 0.0, 0.74));

                            float alpha = clamp(
                                (anatomyResponse * 0.94) +
                                (grayMatter * 0.20) +
                                (whiteMatter * 0.24) +
                                (damage * 0.28),
                                0.0,
                                1.0
                            ) * uOpacity;
                            if (alpha < 0.0018) {
                                discard;
                            }

                            gl_FragColor = vec4(finalColor, alpha);
                        }
                    `,
                    transparent: true,
                    depthWrite: false,
                    side: THREE.DoubleSide,
                    blending: THREE.NormalBlending,
                });
            };

            const addSliceStack = (axis, count, opacityWeight) => {
                for (let i = 0; i < count; i++) {
                    const slice = count <= 1 ? 0 : (i / (count - 1));
                    const material = createSliceMaterial(axis, slice, count, opacityWeight);
                    const plane = new THREE.Mesh(new THREE.PlaneGeometry(2.02, 2.02), material);

                    if (axis === 0) {
                        plane.position.z = -1 + (slice * 2);
                        plane.userData.clipCoord = plane.position.z;
                    } else if (axis === 1) {
                        plane.rotation.x = Math.PI / 2;
                        plane.position.y = -1 + (slice * 2);
                        plane.userData.clipCoord = plane.position.y;
                    } else {
                        plane.rotation.y = Math.PI / 2;
                        plane.position.x = -1 + (slice * 2);
                        plane.userData.clipCoord = plane.position.x;
                    }

                    plane.renderOrder = 50 + group.children.length;
                    plane.userData.clipVisible = true;
                    group.add(plane);
                    volumeMaterials.push(material);
                }
            };

            addSliceStack(0, axialCount, 1.0);
            addSliceStack(1, coronalCount, 0.62);
            addSliceStack(2, sagittalCount, 0.62);

            return { group, texture };
        }

        async function loadVolumeFromAnalysis(data) {
            if (!data?.scan_id || !scene) return false;

            const attempts = [
                VOLUME_RENDER_RESOLUTION,
                "high",
                "standard",
            ].filter((value, index, arr) => arr.indexOf(value) === index);

            try {
                let payload = null;
                let lastError = null;
                for (const resolution of attempts) {
                    try {
                        payload = await fetchVolumePayload(data.scan_id, resolution);
                        break;
                    } catch (error) {
                        lastError = error;
                    }
                }

                if (!payload) {
                    throw (lastError || new Error("No volume payload could be loaded"));
                }

                volumeUsesSyntheticFallback = Boolean(payload?.synthetic_fallback);
                disposeVolumeRenderAssets();

                const result = buildVolumeSlices(payload);
                volumeGroup = result.group;
                volumeTexture = result.texture;
                scene.add(volumeGroup);

                const clipSlider = document.getElementById("clip-slider");
                applyClipDepthFromSlider(clipSlider ? clipSlider.value : 0);
                setRenderMode(activeRenderMode);
                return true;
            } catch (error) {
                console.warn("Volumetric reconstruction unavailable:", error);
                disposeVolumeRenderAssets();
                volumeUsesSyntheticFallback = false;
                return false;
            }
        }

        function applyClipDepthFromSlider(rawValue) {
            const sliderValue = Number(rawValue || 0);
            const normalized = sliderValue / 100;
            const clipConstant = (normalized * 2.3) - 1.15;

            if (brainGroup) {
                brainGroup.traverse((child) => {
                    if (!child.isMesh || !child.material) return;
                    if (sliderValue <= 0) {
                        child.material.clippingPlanes = [];
                        child.material.needsUpdate = true;
                        return;
                    }
                    const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), clipConstant);
                    child.material.clippingPlanes = [clipPlane];
                    child.material.needsUpdate = true;
                });
            }

            if (volumeGroup) {
                const clipZ = sliderValue <= 0 ? 1.1 : ((normalized * 2) - 1);
                volumeGroup.children.forEach((sliceMesh) => {
                    const coord = Number(sliceMesh.userData?.clipCoord);
                    sliceMesh.userData.clipVisible = sliderValue <= 0 || !Number.isFinite(coord) || coord <= clipZ;
                });
            }

            setRenderMode(activeRenderMode);
        }

        function updateTrajectoryButtons() {
            const entryBtn = document.getElementById("btn-plan-entry");
            const targetBtn = document.getElementById("btn-plan-target");
            if (entryBtn) entryBtn.classList.toggle("active", clinicalState.trajectory.activeMode === "entry");
            if (targetBtn) targetBtn.classList.toggle("active", clinicalState.trajectory.activeMode === "target");
        }

        function updateTrajectoryOutput(message) {
            const output = document.getElementById("trajectory-output");
            if (!output) return;
            output.innerHTML = message;
        }

        function clearTrajectoryVisual() {
            if (!scene || !clinicalState.trajectory.visual) return;
            scene.remove(clinicalState.trajectory.visual);
            clinicalState.trajectory.visual.traverse((child) => {
                if (child.geometry?.dispose) child.geometry.dispose();
                if (child.material?.dispose) child.material.dispose();
            });
            clinicalState.trajectory.visual = null;
        }

        function renderTrajectoryVisual() {
            clearTrajectoryVisual();
            if (!scene) return;

            const group = new THREE.Group();
            const entry = clinicalState.trajectory.entry;
            const target = clinicalState.trajectory.target;

            const makePoint = (point, color) => {
                const marker = new THREE.Mesh(
                    new THREE.SphereGeometry(0.028, 14, 14),
                    new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.2 })
                );
                marker.position.set(point.x, point.y, point.z);
                group.add(marker);
            };

            if (entry) makePoint(entry, 0x2f9bff);
            if (target) makePoint(target, 0xff7f3f);

            if (entry && target) {
                const points = [
                    new THREE.Vector3(entry.x, entry.y, entry.z),
                    new THREE.Vector3(target.x, target.y, target.z),
                ];
                const lineGeometry = new THREE.BufferGeometry().setFromPoints(points);
                const line = new THREE.Line(
                    lineGeometry,
                    new THREE.LineBasicMaterial({ color: 0xffb14a, transparent: true, opacity: 0.92 })
                );
                group.add(line);
            }

            clinicalState.trajectory.visual = group;
            scene.add(group);
        }

        function setTrajectoryCaptureMode(mode) {
            clinicalState.trajectory.activeMode = mode;
            updateTrajectoryButtons();
            if (mode === "entry") {
                updateTrajectoryOutput("Trajectory mode: click in the 3D viewer to set entry point.");
            } else if (mode === "target") {
                updateTrajectoryOutput("Trajectory mode: click in the 3D viewer to set target point.");
            }
        }

        function clearTrajectoryPlan() {
            clinicalState.trajectory.activeMode = "";
            clinicalState.trajectory.entry = null;
            clinicalState.trajectory.target = null;
            updateTrajectoryButtons();
            clearTrajectoryVisual();
            updateTrajectoryOutput("Choose entry and target points from 3D view, then compute risk-aware approach path.");
        }

        function distancePointToSegmentMm(pointMm, startMm, endMm) {
            const ab = {
                x: endMm.x - startMm.x,
                y: endMm.y - startMm.y,
                z: endMm.z - startMm.z,
            };
            const ap = {
                x: pointMm.x - startMm.x,
                y: pointMm.y - startMm.y,
                z: pointMm.z - startMm.z,
            };
            const denom = (ab.x * ab.x) + (ab.y * ab.y) + (ab.z * ab.z);
            if (denom <= 1e-6) {
                const dx = pointMm.x - startMm.x;
                const dy = pointMm.y - startMm.y;
                const dz = pointMm.z - startMm.z;
                return Math.sqrt((dx * dx) + (dy * dy) + (dz * dz));
            }
            const t = clampValue(((ap.x * ab.x) + (ap.y * ab.y) + (ap.z * ab.z)) / denom, 0, 1);
            const closest = {
                x: startMm.x + (ab.x * t),
                y: startMm.y + (ab.y * t),
                z: startMm.z + (ab.z * t),
            };
            const dx = pointMm.x - closest.x;
            const dy = pointMm.y - closest.y;
            const dz = pointMm.z - closest.z;
            return Math.sqrt((dx * dx) + (dy * dy) + (dz * dz));
        }

        function pointNormalizedToMm(point) {
            if (!activeDicomVolume || !point) return { x: 0, y: 0, z: 0 };
            const voxel = normalizedToVoxel(activeDicomVolume, point);
            const sx = Number(activeDicomVolume.pixelSpacing?.[0] || 1);
            const sy = Number(activeDicomVolume.pixelSpacing?.[1] || 1);
            const sz = Number(activeDicomVolume.sliceThickness || 1);
            return {
                x: voxel.x * sx,
                y: voxel.y * sy,
                z: voxel.z * sz,
            };
        }

        function computeTrajectoryPlan() {
            if (!activeDicomVolume) {
                updateTrajectoryOutput("Load a scan first to compute trajectory guidance.");
                return;
            }

            const entry = clinicalState.trajectory.entry;
            const target = clinicalState.trajectory.target;
            if (!entry || !target) {
                updateTrajectoryOutput("Set both entry and target points before computing trajectory.");
                return;
            }

            const entryMm = pointNormalizedToMm(entry);
            const targetMm = pointNormalizedToMm(target);
            const dx = targetMm.x - entryMm.x;
            const dy = targetMm.y - entryMm.y;
            const dz = targetMm.z - entryMm.z;
            const pathLength = Math.sqrt((dx * dx) + (dy * dy) + (dz * dz));

            const selectedStructures = Array.from(document.querySelectorAll("#critical-structure-toggles input:checked"))
                .map((input) => input.dataset.structure)
                .filter(Boolean);

            const structureRows = selectedStructures.map((key) => {
                const profile = CRITICAL_STRUCTURE_PROFILES[key];
                if (!profile) return null;

                const minDistance = profile.points.reduce((best, point) => {
                    const pointMm = pointNormalizedToMm(point);
                    const distance = distancePointToSegmentMm(pointMm, entryMm, targetMm);
                    return Math.min(best, distance);
                }, Number.POSITIVE_INFINITY);

                const classLabel = minDistance < 5
                    ? "No-go"
                    : (minDistance < 10 ? "High caution" : (minDistance < 16 ? "Caution" : "Acceptable"));
                return `<div>${profile.label}: clearance ${minDistance.toFixed(1)} mm (${classLabel})</div>`;
            }).filter(Boolean);

            const minClearance = structureRows.length > 0
                ? Math.min(...selectedStructures.map((key) => {
                    const profile = CRITICAL_STRUCTURE_PROFILES[key];
                    if (!profile) return Number.POSITIVE_INFINITY;
                    return profile.points.reduce((best, point) => {
                        const pointMm = pointNormalizedToMm(point);
                        const distance = distancePointToSegmentMm(pointMm, entryMm, targetMm);
                        return Math.min(best, distance);
                    }, Number.POSITIVE_INFINITY);
                }))
                : Number.POSITIVE_INFINITY;

            const overallRisk = minClearance < 5
                ? "High risk trajectory"
                : (minClearance < 10 ? "Moderate risk trajectory" : "Favorable trajectory");

            updateTrajectoryOutput(
                `<strong>${overallRisk}</strong><br>` +
                `Path length ${pathLength.toFixed(1)} mm | Entry (${entry.x.toFixed(2)}, ${entry.y.toFixed(2)}, ${entry.z.toFixed(2)}) | ` +
                `Target (${target.x.toFixed(2)}, ${target.y.toFixed(2)}, ${target.z.toFixed(2)})` +
                (structureRows.length ? `<br>${structureRows.join("")}` : "<br>No critical structures selected for clearance scoring.")
            );
        }

        function handleBrainCanvasClick(event) {
            if (!brainGroup || !analysisData || !raycaster || !pointer || !camera || !renderer) return;

            const rect = renderer.domElement.getBoundingClientRect();
            pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

            raycaster.setFromCamera(pointer, camera);
            const meshes = [];
            brainGroup.traverse((child) => {
                if (child.isMesh) meshes.push(child);
            });

            const hits = raycaster.intersectObjects(meshes, false);
            if (hits.length === 0) return;

            const hit = hits[0];

            if (activeDicomVolume) {
                clinicalState.navVoxel = normalizedToVoxel(activeDicomVolume, hit.point);
                clampNavVoxelToVolume();
                if (clinicalState.linkedNav) {
                    syncMainSliceFromNav(dicomState.plane);
                }
                renderDicomSlice();
            }

            if (clinicalState.trajectory.activeMode === "entry") {
                clinicalState.trajectory.entry = { x: hit.point.x, y: hit.point.y, z: hit.point.z };
                clinicalState.trajectory.activeMode = "";
                updateTrajectoryButtons();
                renderTrajectoryVisual();
                updateTrajectoryOutput("Entry point captured. Set target point and compute trajectory.");
            } else if (clinicalState.trajectory.activeMode === "target") {
                clinicalState.trajectory.target = { x: hit.point.x, y: hit.point.y, z: hit.point.z };
                clinicalState.trajectory.activeMode = "";
                updateTrajectoryButtons();
                renderTrajectoryVisual();
                updateTrajectoryOutput("Target point captured. Click Compute Trajectory to evaluate pathway risk.");
            }

            const regions = normalizeRegions(analysisData);
            const region = inferRegionFromPoint(regions, hit.point.x, hit.point.y, hit.point.z);
            const regionName = region?.anatomical_name || region?.atlas_id || "No mapped region";
            const severity = SEVERITY_LABELS[region?.severity_level || 1] || "Healthy";
            const confidence = Math.round((region?.confidence || 0.0) * 100);

            clearViewerFocus();
            const markerGeo = new THREE.SphereGeometry(0.03, 16, 16);
            const markerMat = new THREE.MeshStandardMaterial({ color: 0x1f77b4, emissive: 0x0f4f8a, emissiveIntensity: 0.2 });
            viewerFocusMarker = new THREE.Mesh(markerGeo, markerMat);
            viewerFocusMarker.position.copy(hit.point);
            scene.add(viewerFocusMarker);

            updateViewerPickInfo(`Selection: ${regionName} | ${severity}${confidence > 0 ? ` | ${confidence}% confidence` : ""}`);
        }

        function buildDemoBrain(damageData) {
            const group = new THREE.Group();
            const geo = new THREE.SphereGeometry(1, 64, 48);
            const seed = getStringSeed(`${damageData?.patient_id || ""}-${damageData?.scan_id || ""}`);
            const scaleX = 0.95 + ((seed % 11) * 0.006);
            const scaleY = 0.82 + ((seed % 7) * 0.008);
            const scaleZ = 1.08 + ((seed % 9) * 0.006);
            geo.scale(scaleX, scaleY, scaleZ);

            const regions = normalizeRegions(damageData);
            const pos = geo.attributes.position;
            const colors = new Float32Array(pos.count * 3);
            const ripple = 0.012 + ((seed % 5) * 0.0015);

            for (let i = 0; i < pos.count; i++) {
                const x = pos.getX(i);
                const y = pos.getY(i);
                const z = pos.getZ(i);

                const split = Math.abs(x) < 0.03 ? -0.04 : 0;
                const bump = Math.sin(x * 12) * Math.sin(y * 10) * Math.sin(z * 8) * ripple;
                pos.setY(i, y + split + bump);

                const severityLevel = resolveSeverityLevel(regions, x, y, z);
                const color = DAMAGE_COLORS[severityLevel] || DAMAGE_COLORS[1];
                colors[i * 3] = ((color >> 16) & 0xFF) / 255;
                colors[i * 3 + 1] = ((color >> 8) & 0xFF) / 255;
                colors[i * 3 + 2] = (color & 0xFF) / 255;
            }

            geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
            geo.computeVertexNormals();

            const material = new THREE.MeshPhongMaterial({
                vertexColors: true,
                shininess: 34,
                specular: 0x99a8bd,
            });

            const mesh = new THREE.Mesh(geo, material);
            group.add(mesh);

            const lineGeo = new THREE.BufferGeometry();
            const lineVerts = [];
            for (let i = 0; i <= 20; i++) {
                const t = (i / 20) * Math.PI - Math.PI / 2;
                lineVerts.push(0, Math.sin(t) * 0.86, Math.cos(t) * 1.15);
            }
            lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(lineVerts, 3));
            const lineMat = new THREE.LineBasicMaterial({ color: 0x445972, opacity: 0.6, transparent: true });
            group.add(new THREE.Line(lineGeo, lineMat));

            return group;
        }

        async function fetchDemoMesh(scanId, forceRebuild = false, quality = SURFACE_MESH_QUALITY) {
            const params = new URLSearchParams();
            if (forceRebuild) params.set("force_rebuild", "true");
            if (quality) params.set("quality", quality);
            const query = params.toString() ? `?${params.toString()}` : "";
            const response = await fetch(`${API_BASE}/demo/mesh/${encodeURIComponent(scanId)}${query}`);
            if (!response.ok) {
                throw new Error(`Demo mesh endpoint failed (${response.status})`);
            }
            return response.json();
        }

        async function fetchMeshForScan(scanId, forceRebuild = false, quality = SURFACE_MESH_QUALITY) {
            const params = new URLSearchParams();
            if (forceRebuild) params.set("force_rebuild", "true");
            if (quality) params.set("quality", quality);
            const query = params.toString() ? `?${params.toString()}` : "";
            const response = await fetch(`${API_BASE}/mesh/${encodeURIComponent(scanId)}${query}`, {
                headers: authToken ? authHeaders() : {},
            });

            if (response.ok) {
                return response.json();
            }

            if (String(scanId).startsWith("demo-scan")) {
                return fetchDemoMesh(scanId, forceRebuild, quality);
            }

            throw new Error(`Mesh endpoint failed (${response.status})`);
        }

        async function loadObjGroup(meshUrl) {
            const resolvedUrl = meshUrl.startsWith("http") ? meshUrl : `${API_BASE}${meshUrl}`;
            return new Promise((resolve, reject) => {
                objLoader.load(
                    resolvedUrl,
                    (obj) => resolve(obj),
                    undefined,
                    (error) => reject(error || new Error("OBJ load failed")),
                );
            });
        }

        async function loadGltfGroup(meshUrl) {
            const resolvedUrl = meshUrl.startsWith("http") ? meshUrl : `${API_BASE}${meshUrl}`;
            return new Promise((resolve, reject) => {
                gltfLoader.load(
                    resolvedUrl,
                    (gltf) => resolve(gltf.scene || gltf.scenes?.[0] || null),
                    undefined,
                    (error) => reject(error || new Error("GLB load failed")),
                );
            });
        }

        async function loadMeshGroup(meshUrl, meshFormat = "obj") {
            const normalized = String(meshFormat || "obj").toLowerCase();
            if (normalized === "glb" || String(meshUrl || "").toLowerCase().endsWith(".glb")) {
                const gltfScene = await loadGltfGroup(meshUrl);
                if (!gltfScene) {
                    throw new Error("GLB mesh did not contain a renderable scene");
                }
                return gltfScene;
            }
            return loadObjGroup(meshUrl);
        }

        function subdivideIndexedGeometry(inputGeometry, iterations = 1, maxVertices = 260000) {
            let workingGeometry = inputGeometry;

            for (let pass = 0; pass < iterations; pass++) {
                const indexAttr = workingGeometry.getIndex();
                const positionAttr = workingGeometry.getAttribute("position");
                if (!indexAttr || !positionAttr) break;
                if (positionAttr.count >= maxVertices) break;

                const positions = Array.from(positionAttr.array);
                const sourceIndices = Array.from(indexAttr.array);
                const midpointCache = new Map();
                const nextIndices = [];

                const midpointIndex = (a, b) => {
                    const i0 = Math.min(a, b);
                    const i1 = Math.max(a, b);
                    const key = `${i0}:${i1}`;

                    if (midpointCache.has(key)) {
                        return midpointCache.get(key);
                    }

                    const ax = positions[a * 3];
                    const ay = positions[(a * 3) + 1];
                    const az = positions[(a * 3) + 2];
                    const bx = positions[b * 3];
                    const by = positions[(b * 3) + 1];
                    const bz = positions[(b * 3) + 2];

                    const mIndex = positions.length / 3;
                    positions.push((ax + bx) * 0.5, (ay + by) * 0.5, (az + bz) * 0.5);
                    midpointCache.set(key, mIndex);
                    return mIndex;
                };

                for (let i = 0; i < sourceIndices.length; i += 3) {
                    const a = sourceIndices[i];
                    const b = sourceIndices[i + 1];
                    const c = sourceIndices[i + 2];

                    const ab = midpointIndex(a, b);
                    const bc = midpointIndex(b, c);
                    const ca = midpointIndex(c, a);

                    nextIndices.push(a, ab, ca);
                    nextIndices.push(b, bc, ab);
                    nextIndices.push(c, ca, bc);
                    nextIndices.push(ab, bc, ca);
                }

                const nextGeometry = new THREE.BufferGeometry();
                nextGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
                nextGeometry.setIndex(nextIndices);

                if (workingGeometry !== inputGeometry) {
                    workingGeometry.dispose();
                }
                workingGeometry = nextGeometry;
            }

            return workingGeometry;
        }

        function laplacianSmoothIndexedGeometry(inputGeometry, iterations = 2, blend = 0.24) {
            const indexAttr = inputGeometry.getIndex();
            const positionAttr = inputGeometry.getAttribute("position");
            if (!indexAttr || !positionAttr) return inputGeometry;

            const vertexCount = positionAttr.count;
            const neighbors = Array.from({ length: vertexCount }, () => new Set());
            const indices = indexAttr.array;

            for (let i = 0; i < indices.length; i += 3) {
                const a = indices[i];
                const b = indices[i + 1];
                const c = indices[i + 2];

                neighbors[a].add(b); neighbors[a].add(c);
                neighbors[b].add(a); neighbors[b].add(c);
                neighbors[c].add(a); neighbors[c].add(b);
            }

            let current = new Float32Array(positionAttr.array);
            let next = new Float32Array(current.length);

            for (let pass = 0; pass < iterations; pass++) {
                for (let v = 0; v < vertexCount; v++) {
                    const base = v * 3;
                    const adjacency = neighbors[v];

                    if (!adjacency || adjacency.size === 0) {
                        next[base] = current[base];
                        next[base + 1] = current[base + 1];
                        next[base + 2] = current[base + 2];
                        continue;
                    }

                    let ax = 0;
                    let ay = 0;
                    let az = 0;
                    adjacency.forEach((n) => {
                        const nBase = n * 3;
                        ax += current[nBase];
                        ay += current[nBase + 1];
                        az += current[nBase + 2];
                    });

                    const inv = 1 / adjacency.size;
                    next[base] = (current[base] * (1 - blend)) + ((ax * inv) * blend);
                    next[base + 1] = (current[base + 1] * (1 - blend)) + ((ay * inv) * blend);
                    next[base + 2] = (current[base + 2] * (1 - blend)) + ((az * inv) * blend);
                }

                const swap = current;
                current = next;
                next = swap;
            }

            const outputGeometry = inputGeometry.clone();
            outputGeometry.setAttribute("position", new THREE.BufferAttribute(current, 3));
            return outputGeometry;
        }

        function enhanceSurfaceGeometry(sourceGeometry) {
            let geometry = sourceGeometry.clone();
            geometry.deleteAttribute("normal");
            geometry = BufferGeometryUtils.mergeVertices(geometry, 1e-4);

            const positionAttr = geometry.getAttribute("position");
            const vertexCount = positionAttr ? positionAttr.count : 0;
            if (geometry.getIndex() && vertexCount > 0 && vertexCount < 180000) {
                geometry = subdivideIndexedGeometry(geometry, 1, 260000);
            }
            if (geometry.getIndex() && (geometry.getAttribute("position")?.count || 0) < 320000) {
                geometry = laplacianSmoothIndexedGeometry(geometry, 2, 0.24);
            }

            geometry.computeVertexNormals();
            geometry.normalizeNormals();
            geometry.computeBoundingSphere();
            return geometry;
        }

        function buildBrainFromObj(objectRoot) {
            const group = new THREE.Group();
            const candidates = [];

            objectRoot.updateMatrixWorld(true);
            objectRoot.traverse((child) => {
                if (!child.isMesh || !child.geometry) return;

                const geometry = child.geometry.clone();
                geometry.applyMatrix4(child.matrixWorld);
                const enhancedGeometry = enhanceSurfaceGeometry(geometry);

                const positionAttr = enhancedGeometry.getAttribute("position");
                const vertexCount = positionAttr ? positionAttr.count : 0;
                if (vertexCount <= 0) {
                    return;
                }

                candidates.push({ geometry: enhancedGeometry, vertexCount });
            });

            if (candidates.length === 0) {
                throw new Error("Reconstruction mesh had no renderable surfaces");
            }

            const largestComponent = Math.max(...candidates.map((entry) => entry.vertexCount));
            const retainedComponents = candidates.filter((entry) => entry.vertexCount >= (largestComponent * 0.08));

            retainedComponents.forEach((entry) => {
                const enhancedGeometry = entry.geometry;

                const material = new THREE.MeshPhysicalMaterial({
                    color: 0xd6ddeb,
                    vertexColors: true,
                    roughness: 0.36,
                    metalness: 0.03,
                    clearcoat: 0.34,
                    clearcoatRoughness: 0.58,
                    reflectivity: 0.32,
                    side: THREE.FrontSide,
                });

                const mesh = new THREE.Mesh(enhancedGeometry, material);
                group.add(mesh);
            });

            return group;
        }

        async function buildReconstructedBrain(data, meshQuality = SURFACE_MESH_QUALITY) {
            if (!data?.scan_id) {
                throw new Error("Missing scan ID for reconstruction mesh load");
            }

            const meshPayload = await fetchMeshForScan(data.scan_id, false, meshQuality);
            const loadedObj = await loadMeshGroup(meshPayload.mesh_url, meshPayload.mesh_format);
            return {
                group: buildBrainFromObj(loadedObj),
                payload: meshPayload,
            };
        }

        function applyDamageColors(group, damageData, visibleLvls) {
            const regions = normalizeRegions(damageData);
            const baseColor = { r: 0.82, g: 0.85, b: 0.90 };
            const severityBlend = { 2: 0.16, 3: 0.28, 4: 0.44 };

            group.traverse((child) => {
                if (!child.isMesh || !child.geometry || !child.geometry.attributes.position) return;

                const pos = child.geometry.attributes.position;
                if (!child.geometry.attributes.color) {
                    const colorArray = new Float32Array(pos.count * 3);
                    child.geometry.setAttribute("color", new THREE.BufferAttribute(colorArray, 3));
                }

                if (child.material) {
                    child.material.vertexColors = true;
                }

                const colors = child.geometry.attributes.color;

                for (let i = 0; i < pos.count; i++) {
                    const x = pos.getX(i);
                    const y = pos.getY(i);
                    const z = pos.getZ(i);
                    const severityLevel = resolveSeverityLevel(regions, x, y, z);

                    const corticalShade = 0.96 + (Math.max(-1, Math.min(1, y)) * 0.03);
                    const baseR = Math.min(1, Math.max(0, baseColor.r * corticalShade));
                    const baseG = Math.min(1, Math.max(0, baseColor.g * corticalShade));
                    const baseB = Math.min(1, Math.max(0, baseColor.b * corticalShade));

                    if (!visibleLvls.has(severityLevel) || severityLevel < 2) {
                        colors.setXYZ(i, baseR, baseG, baseB);
                        continue;
                    }

                    const c = DAMAGE_COLORS[severityLevel] || DAMAGE_COLORS[2];
                    const overlayR = ((c >> 16) & 0xFF) / 255;
                    const overlayG = ((c >> 8) & 0xFF) / 255;
                    const overlayB = (c & 0xFF) / 255;
                    const blend = severityBlend[severityLevel] || 0.2;

                    colors.setXYZ(
                        i,
                        (baseR * (1 - blend)) + (overlayR * blend),
                        (baseG * (1 - blend)) + (overlayG * blend),
                        (baseB * (1 - blend)) + (overlayB * blend),
                    );
                }
                colors.needsUpdate = true;
            });
        }

        function updateStatus(text) {
            const status = document.getElementById("status-text");
            if (status) status.textContent = text;
        }

        function updateJobInfo(text) {
            const jobInfo = document.getElementById("job-info");
            if (jobInfo) jobInfo.textContent = text;
        }

        function setAuthState(text, type) {
            const el = document.getElementById("auth-status");
            if (!el) return;
            el.textContent = text;
            el.className = `status-pill ${type}`;
            updateClinicalWorkflow();
        }

        function getRiskClass(riskBand) {
            const normalized = (riskBand || "low").toLowerCase();
            if (normalized === "high" || normalized === "moderate" || normalized === "low") {
                return normalized;
            }
            return "low";
        }

        function setWorkflowStepDone(stepId, isDone) {
            const step = document.getElementById(stepId);
            if (!step) return;
            step.classList.toggle("done", Boolean(isDone));
        }

        function setReadinessState(itemId, isReady, detailText) {
            const item = document.getElementById(itemId);
            if (!item) return;

            item.classList.toggle("ok", Boolean(isReady));
            const detail = item.querySelector(".readiness-value");
            if (detail && detailText) {
                detail.textContent = detailText;
            }
        }

        function updateClinicalKpis(data = analysisData, patientOverride = null) {
            const patient = patientOverride || findPatientById(data?.patient_id) || getSelectedPatient();
            const riskClass = getRiskClass(data?.risk_band || patient?.risk_band);
            const regions = normalizeRegions(data);
            const flaggedRegions = regions.filter((region) => (region.severity_level || 0) >= 2).length;
            const confidenceSource = data?.overall_confidence ?? patient?.overall_confidence;
            const confidencePct = confidenceSource === undefined || confidenceSource === null
                ? "-"
                : `${Math.round(Number(confidenceSource) * 100)}%`;

            const patientEl = document.getElementById("kpi-patient");
            const modalityEl = document.getElementById("kpi-modality");
            const riskEl = document.getElementById("kpi-risk");
            const regionsEl = document.getElementById("kpi-regions");
            const confidenceEl = document.getElementById("kpi-confidence");

            if (patientEl) {
                patientEl.textContent = patient
                    ? `${patient.patient_code || ""} ${patient.display_name || ""}`.trim()
                    : (data?.patient_code || data?.patient_name || "No patient selected");
            }
            if (modalityEl) {
                modalityEl.textContent = (data?.modalities && data.modalities[0]) || patient?.modality || "-";
            }
            if (riskEl) {
                riskEl.textContent = RISK_LABELS[riskClass] || "low";
                riskEl.className = `kpi-value ${riskClass}`;
            }
            if (regionsEl) {
                regionsEl.textContent = String(flaggedRegions);
            }
            if (confidenceEl) {
                confidenceEl.textContent = confidencePct;
            }
        }

        function formatGovLabel(value, fallback = "n/a") {
            if (value === null || value === undefined || value === "") return fallback;
            return String(value).split("_").join(" ");
        }

        function setGovText(id, text) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = text;
            }
        }

        function renderGovList(id, items, emptyText, formatter) {
            const list = document.getElementById(id);
            if (!list) return;

            if (!items || items.length === 0) {
                list.innerHTML = `<div class="gov-item muted">${emptyText}</div>`;
                return;
            }

            list.innerHTML = items.map((item) => `<div class="gov-item">${formatter(item)}</div>`).join("");
        }

        function renderGovernancePanel(data = analysisData) {
            const governance = data?.clinical_governance || null;
            clinicalGovernance = governance;

            if (!governance) {
                setGovText("gov-decision-tier", "not evaluated");
                setGovText("gov-review-state", "review pending");
                setGovText("gov-automation", "manual review");
                setGovText("gov-escalation", "routine");
                setGovText("gov-provenance", "Provenance details are unavailable until a scan is loaded.");
                setGovText("gov-message", "AI output is decision support and must be validated by the care team.");
                setGovText("gov-required-signoff", "Required sign-off roles: clinician");
                renderGovList("gov-evidence-list", [], "Evidence cards appear after loading a scan.", () => "");
                renderGovList("gov-signoff-list", [], "No sign-off activity recorded yet.", () => "");
                return;
            }

            const provenance = governance.provenance || data?.provenance || {};
            const escalation = governance.escalation || {};
            const requiredRoles = governance.required_signoff_roles || [];
            const evidenceCards = governance.evidence_cards || [];
            const signoffs = data?.signoff_history || [];

            setGovText("gov-decision-tier", formatGovLabel(governance.decision_tier, "not evaluated"));
            setGovText("gov-review-state", formatGovLabel(governance.review_state, "review pending"));
            setGovText("gov-automation", governance.automation_eligible ? "eligible" : "manual review");
            setGovText("gov-escalation", formatGovLabel(escalation.level, "routine"));

            const sourceKind = provenance.source_kind || "unknown";
            const synthetic = provenance.synthetic_fallback ? "yes" : "no";
            const meshQuality = provenance.mesh_quality || "n/a";
            const volumeResolution = provenance.volume_resolution || "n/a";
            setGovText(
                "gov-provenance",
                `Source: ${sourceKind}. Synthetic fallback: ${synthetic}. Mesh quality: ${meshQuality}. Volume resolution: ${volumeResolution}.`
            );

            setGovText(
                "gov-message",
                governance.messaging?.clinician_notice || "AI output is decision support and must be validated by the care team."
            );
            setGovText(
                "gov-required-signoff",
                `Required sign-off roles: ${requiredRoles.length ? requiredRoles.join(", ") : "clinician"}`
            );

            renderGovList(
                "gov-evidence-list",
                evidenceCards,
                "No moderate/high confidence evidence cards available.",
                (card) => `<strong>${card.region || "Region"}</strong> - ${card.severity_label || "UNKNOWN"} (${card.confidence_pct || 0}% confidence)`
            );

            renderGovList(
                "gov-signoff-list",
                signoffs.slice().reverse(),
                "No sign-off activity recorded yet.",
                (entry) => {
                    const when = entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "unknown time";
                    const who = entry.signed_by || "unknown";
                    const role = entry.signed_role || "n/a";
                    const decision = formatGovLabel(entry.decision, "recorded");
                    return `<strong>${decision}</strong> by ${who} (${role}) at ${when}`;
                }
            );
        }

        async function submitSignoffDecision(decision) {
            if (!authToken) {
                updateStatus("Please sign in before recording sign-off decisions.");
                return;
            }
            if (!currentScanId) {
                updateStatus("Load a scan before submitting sign-off.");
                return;
            }

            try {
                const response = await fetch(`${API_BASE}/signoff/${encodeURIComponent(currentScanId)}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", ...authHeaders() },
                    body: JSON.stringify({ decision }),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || `Sign-off failed (${response.status})`);
                }

                if (analysisData && analysisData.scan_id === currentScanId) {
                    analysisData.signoff_history = payload.history || [];
                    analysisData.review_state = payload.review_state;
                    analysisData.decision_tier = payload.decision_tier;
                    if (analysisData.clinical_governance) {
                        analysisData.clinical_governance.review_state = payload.review_state;
                        analysisData.clinical_governance.decision_tier = payload.decision_tier;
                        analysisData.clinical_governance.required_signoff_roles = payload.required_signoff_roles || [];
                    }
                }

                renderGovernancePanel(analysisData);
                updateStatus(`Sign-off decision '${formatGovLabel(decision)}' recorded for scan ${currentScanId}.`);
            } catch (error) {
                updateStatus(`Sign-off update failed: ${error.message}`);
            }
        }

        function updateClinicalWorkflow() {
            const hasAuth = Boolean(authToken);
            const hasSelectedPatient = Boolean(selectedPatientId || analysisData?.patient_id);
            const hasScan = Boolean(currentScanId);
            const regions = normalizeRegions(analysisData);
            const reviewedFindings = regions.some((region) => (region.severity_level || 0) >= 2);
            const dicomReady = Boolean(activeDicomVolume);
            const reportReady = hasScan;
            const governanceState = analysisData?.clinical_governance?.review_state || analysisData?.review_state || "";
            const decisionTier = analysisData?.clinical_governance?.decision_tier || analysisData?.decision_tier || "";

            setWorkflowStepDone("workflow-step-auth", hasAuth);
            setWorkflowStepDone("workflow-step-load", hasSelectedPatient);
            setWorkflowStepDone("workflow-step-analyze", hasScan);
            setWorkflowStepDone("workflow-step-verify", reviewedFindings || dicomReady);
            setWorkflowStepDone("workflow-step-report", reportReady);

            setReadinessState(
                "readiness-auth",
                hasAuth,
                hasAuth ? "Signed-in clinician context active." : "Authentication pending."
            );
            setReadinessState(
                "readiness-scan",
                hasScan,
                hasScan ? `Scan ${currentScanId} loaded.` : "No active scan loaded."
            );
            setReadinessState(
                "readiness-findings",
                reviewedFindings,
                reviewedFindings
                    ? `${regions.filter((region) => (region.severity_level || 0) >= 2).length} elevated regions reviewed. ${formatGovLabel(decisionTier || governanceState, "")}`.trim()
                    : "Awaiting reviewed anatomical findings."
            );
            setReadinessState(
                "readiness-dicom",
                dicomReady,
                dicomReady ? "Tri-planar DICOM workstation initialized." : "DICOM workstation not initialized."
            );
            setReadinessState(
                "readiness-export",
                reportReady,
                reportReady ? "Report and export actions enabled." : "Report view unavailable until scan load."
            );
        }

        function applyPanelMode(mode = "all") {
            const nextMode = PANEL_MODES.has(mode) ? mode : "all";
            activePanelMode = nextMode;

            document.querySelectorAll(".panel-mode-btn").forEach((button) => {
                button.classList.toggle("active", button.dataset.panelMode === nextMode);
            });

            document.querySelectorAll(".panel-card[data-panel-group]").forEach((card) => {
                const group = card.dataset.panelGroup || "all";
                const visible = nextMode === "all" || group === nextMode;
                card.classList.toggle("hidden-by-mode", !visible);
            });
        }

        function findPatientById(patientId) {
            return demoPatients.find((patient) => patient.patient_id === patientId) || null;
        }

        function getSelectedPatient() {
            return findPatientById(selectedPatientId);
        }

        function getPatientTimeline(patient) {
            if (!patient || !Array.isArray(patient.timeline)) return [];
            return patient.timeline;
        }

        function getPatientLatestScanId(patient) {
            if (!patient) return "";
            if (patient.latest_scan_id) return patient.latest_scan_id;
            const timeline = getPatientTimeline(patient);
            return timeline.length > 0 ? timeline[0].scan_id : "";
        }

        function formatSignedValue(value, suffix = "") {
            if (value === null || value === undefined || Number.isNaN(Number(value))) {
                return `0${suffix}`;
            }
            const numeric = Number(value);
            const sign = numeric > 0 ? "+" : "";
            return `${sign}${numeric}${suffix}`;
        }

        function getMetricsFromAnalysisPayload(data) {
            if (!data) return null;
            const regions = normalizeRegions(data);
            const flagged = regions.filter((region) => (region.severity_level || 0) >= 2).length;
            const severe = regions.filter((region) => (region.severity_level || 0) >= 4).length;
            const triage = Number(data.triage_score || 0);
            const confidencePct = Math.round(Number(data.overall_confidence || 0) * 100);
            return {
                flagged_regions: flagged,
                severe_regions: severe,
                triage_score: triage,
                confidence_pct: confidencePct,
            };
        }

        function cachePatientTimelineScans(patient) {
            if (!patient) return;
            const timeline = getPatientTimeline(patient);
            timeline.forEach((entry) => {
                if (!entry?.scan_id) return;
                const confidencePct = Math.round(Number(entry.overall_confidence ?? patient.overall_confidence ?? 0) * 100);
                const normalizedMetrics = {
                    flagged_regions: Number(entry.metrics?.flagged_regions || 0),
                    severe_regions: Number(entry.metrics?.severe_regions || 0),
                    triage_score: Number(entry.metrics?.triage_score || patient.triage_score || 0),
                    confidence_pct: Number(entry.metrics?.confidence_pct ?? confidencePct),
                };
                comparisonScanCache.set(entry.scan_id, {
                    scan_id: entry.scan_id,
                    study_date: entry.study_date || "",
                    risk_band: entry.risk_band || patient.risk_band || "low",
                    overall_confidence: Number(entry.overall_confidence ?? patient.overall_confidence ?? 0),
                    metrics: normalizedMetrics,
                    patient_id: patient.patient_id,
                    patient_code: patient.patient_code,
                    modality: patient.modality || "MRI",
                    label: `${entry.study_date || "Unknown date"} | ${entry.scan_id}`,
                });
            });
        }

        function getScanMeta(scanId, fallbackPatient = null) {
            if (!scanId) return null;
            if (comparisonScanCache.has(scanId)) {
                return comparisonScanCache.get(scanId);
            }

            if (analysisData?.scan_id === scanId) {
                const patient = fallbackPatient || findPatientById(analysisData.patient_id) || getSelectedPatient();
                const meta = {
                    scan_id: scanId,
                    study_date: "Current loaded",
                    risk_band: analysisData.risk_band || patient?.risk_band || "low",
                    overall_confidence: Number(analysisData.overall_confidence || patient?.overall_confidence || 0),
                    metrics: getMetricsFromAnalysisPayload(analysisData),
                    patient_id: analysisData.patient_id || patient?.patient_id || "",
                    patient_code: patient?.patient_code || analysisData.patient_code || "Current",
                    modality: (analysisData.modalities && analysisData.modalities[0]) || patient?.modality || "MRI",
                    label: `Current loaded | ${scanId}`,
                };
                comparisonScanCache.set(scanId, meta);
                return meta;
            }

            if (fallbackPatient) {
                const fallback = {
                    scan_id: scanId,
                    study_date: "Selected scan",
                    risk_band: fallbackPatient.risk_band || "low",
                    overall_confidence: Number(fallbackPatient.overall_confidence || 0),
                    metrics: null,
                    patient_id: fallbackPatient.patient_id,
                    patient_code: fallbackPatient.patient_code,
                    modality: fallbackPatient.modality || "MRI",
                    label: `Selected scan | ${scanId}`,
                };
                comparisonScanCache.set(scanId, fallback);
                return fallback;
            }

            return null;
        }

        function populateCompareScanOptions() {
            const leftSelect = document.getElementById("compare-left-scan");
            const rightSelect = document.getElementById("compare-right-scan");
            if (!leftSelect || !rightSelect) return;

            const selectedPatient = getSelectedPatient();
            const comparePatient = findPatientById(compareTargetPatientId);
            const previousLeft = leftSelect.value;
            const previousRight = rightSelect.value;

            comparisonScanCache = new Map();
            cachePatientTimelineScans(selectedPatient);
            cachePatientTimelineScans(comparePatient);

            const selectedTimeline = getPatientTimeline(selectedPatient);
            const optionEntries = [];
            selectedTimeline.forEach((entry) => {
                if (!entry?.scan_id) return;
                optionEntries.push({ value: entry.scan_id, label: `${entry.study_date || "Unknown date"} | ${entry.scan_id}` });
            });

            if (analysisData?.scan_id && selectedPatient && analysisData.patient_id === selectedPatient.patient_id) {
                if (!optionEntries.some((entry) => entry.value === analysisData.scan_id)) {
                    optionEntries.unshift({ value: analysisData.scan_id, label: `Current loaded | ${analysisData.scan_id}` });
                }
            }

            leftSelect.innerHTML = "";
            rightSelect.innerHTML = "";

            const leftAuto = document.createElement("option");
            leftAuto.value = "";
            leftAuto.textContent = "Auto previous scan";
            leftSelect.appendChild(leftAuto);

            const rightAuto = document.createElement("option");
            rightAuto.value = "";
            rightAuto.textContent = "Auto current scan";
            rightSelect.appendChild(rightAuto);

            optionEntries.forEach((entry) => {
                const leftOption = document.createElement("option");
                leftOption.value = entry.value;
                leftOption.textContent = entry.label;
                leftSelect.appendChild(leftOption);

                const rightOption = document.createElement("option");
                rightOption.value = entry.value;
                rightOption.textContent = entry.label;
                rightSelect.appendChild(rightOption);
            });

            if (previousLeft && optionEntries.some((entry) => entry.value === previousLeft)) {
                leftSelect.value = previousLeft;
            } else {
                leftSelect.value = "";
            }

            if (previousRight && optionEntries.some((entry) => entry.value === previousRight)) {
                rightSelect.value = previousRight;
            } else {
                rightSelect.value = "";
            }

            updateComparisonSummaries();
        }

        function resolveComparisonSelection() {
            const leftPatient = getSelectedPatient();
            const rightPatient = findPatientById(compareTargetPatientId) || leftPatient;
            const leftSelect = document.getElementById("compare-left-scan");
            const rightSelect = document.getElementById("compare-right-scan");
            const leftTimeline = getPatientTimeline(leftPatient);

            let leftScanId = leftSelect?.value || "";
            let rightScanId = rightSelect?.value || "";

            if (!leftScanId) {
                if (leftTimeline.length > 1) {
                    leftScanId = leftTimeline[leftTimeline.length - 1].scan_id;
                } else {
                    leftScanId = leftTimeline[0]?.scan_id || "";
                }
            }

            if (!rightScanId) {
                if (analysisData?.scan_id && leftPatient && analysisData.patient_id === leftPatient.patient_id) {
                    rightScanId = analysisData.scan_id;
                } else {
                    rightScanId = getPatientLatestScanId(rightPatient);
                }
            }

            if (leftScanId && rightScanId && leftScanId === rightScanId && leftTimeline.length > 1) {
                const fallbackLeft = leftTimeline.find((entry) => entry.scan_id !== rightScanId);
                if (fallbackLeft?.scan_id) {
                    leftScanId = fallbackLeft.scan_id;
                }
            }

            const leftMeta = getScanMeta(leftScanId, leftPatient);
            const rightMeta = getScanMeta(rightScanId, rightPatient);

            return {
                leftPatient,
                rightPatient,
                leftScanId,
                rightScanId,
                leftMeta,
                rightMeta,
            };
        }

        function formatComparisonSide(meta) {
            if (!meta) return "No scan selected.";
            const risk = RISK_LABELS[getRiskClass(meta.risk_band)] || "low";
            const confidence = `${Math.round(Number(meta.overall_confidence || 0) * 100)}% conf`;
            const metrics = meta.metrics || {};
            const flagged = Number(metrics.flagged_regions || 0);
            const severe = Number(metrics.severe_regions || 0);
            return `${meta.study_date || "Unknown date"} | ${meta.scan_id} | ${risk} risk | ${flagged} flagged / ${severe} severe | ${confidence}`;
        }

        function updateLongitudinalSummary() {
            const output = document.getElementById("longitudinal-delta-output");
            if (!output) return;

            const selection = resolveComparisonSelection();
            const leftMetrics = selection.leftMeta?.metrics;
            const rightMetrics = selection.rightMeta?.metrics;

            if (!selection.leftScanId || !selection.rightScanId) {
                output.textContent = "Longitudinal progression metrics require two valid scans.";
                return;
            }

            if (!leftMetrics || !rightMetrics) {
                output.textContent = `Selected pair: ${selection.leftScanId} -> ${selection.rightScanId}. Metrics are unavailable for one or both scans.`;
                return;
            }

            const flaggedDelta = Number(rightMetrics.flagged_regions || 0) - Number(leftMetrics.flagged_regions || 0);
            const severeDelta = Number(rightMetrics.severe_regions || 0) - Number(leftMetrics.severe_regions || 0);
            const triageDelta = Number(rightMetrics.triage_score || 0) - Number(leftMetrics.triage_score || 0);
            const confidenceDelta = Number(rightMetrics.confidence_pct || 0) - Number(leftMetrics.confidence_pct || 0);

            const trend = (severeDelta > 0 || triageDelta > 0 || flaggedDelta > 0)
                ? "Progression concern"
                : ((severeDelta < 0 || triageDelta < 0 || flaggedDelta < 0) ? "Interval improvement" : "Stable profile");

            output.innerHTML = `
                <strong>${trend}</strong><br>
                ${selection.leftScanId} -> ${selection.rightScanId} | Flagged ${formatSignedValue(flaggedDelta)} | Severe ${formatSignedValue(severeDelta)} | Triage ${formatSignedValue(triageDelta)} | Confidence ${formatSignedValue(confidenceDelta, "%")}
            `;
        }

        function updateComparisonSummaries() {
            const leftSummary = document.getElementById("compare-left-summary");
            const rightSummary = document.getElementById("compare-right-summary");
            const selection = resolveComparisonSelection();

            if (leftSummary) {
                leftSummary.textContent = formatComparisonSide(selection.leftMeta);
            }
            if (rightSummary) {
                rightSummary.textContent = formatComparisonSide(selection.rightMeta);
            }

            updateLongitudinalSummary();
        }

        function renderComparisonPlaceholder(message) {
            const output = document.getElementById("compare-output");
            if (!output) return;
            output.textContent = message;
        }

        function renderTimeline(patient, activeScanId = "") {
            const timelineEl = document.getElementById("timeline-list");
            if (!timelineEl) return;

            const timeline = getPatientTimeline(patient);
            if (timeline.length === 0) {
                timelineEl.innerHTML = "<div class='region-item muted'>No longitudinal history available for this patient.</div>";
                return;
            }

            timelineEl.innerHTML = "";
            timeline.forEach((entry) => {
                const metrics = entry.metrics || {};
                const isActive = activeScanId && entry.scan_id === activeScanId;
                const riskClass = getRiskClass(entry.risk_band);
                const button = document.createElement("button");
                button.type = "button";
                button.className = `timeline-item${isActive ? " active" : ""}`;
                button.innerHTML = `
                    <div class="timeline-main">
                        <span>${entry.study_date || "Unknown date"}</span>
                        <span class="risk-chip ${riskClass}">${RISK_LABELS[riskClass] || riskClass}</span>
                    </div>
                    <div class="timeline-meta">
                        <span>${entry.scan_id}</span>
                        <span>${Math.round((entry.overall_confidence || 0) * 100)}% conf</span>
                    </div>
                    <div class="timeline-meta">
                        <span>${metrics.flagged_regions || 0} flagged</span>
                        <span>${metrics.severe_regions || 0} severe</span>
                    </div>
                `;
                button.addEventListener("click", () => {
                    setSelectedPatient(patient.patient_id);
                    loadDemo(patient.patient_id, entry.scan_id);
                });
                timelineEl.appendChild(button);
            });
        }

        function renderComparePatientOptions() {
            const select = document.getElementById("compare-patient-select");
            if (!select) return;

            const options = demoPatients.filter((patient) => patient.patient_id !== selectedPatientId);
            select.innerHTML = "";

            if (options.length === 0) {
                const option = document.createElement("option");
                option.value = "";
                option.textContent = "No comparison patient available";
                select.appendChild(option);
                compareTargetPatientId = "";
                populateCompareScanOptions();
                return;
            }

            if (!compareTargetPatientId || !options.some((patient) => patient.patient_id === compareTargetPatientId)) {
                compareTargetPatientId = options[0].patient_id;
            }

            options.forEach((patient) => {
                const option = document.createElement("option");
                option.value = patient.patient_id;
                option.textContent = `${patient.patient_code} | ${patient.display_name}`;
                if (patient.patient_id === compareTargetPatientId) {
                    option.selected = true;
                }
                select.appendChild(option);
            });

            populateCompareScanOptions();
        }

        function pickHighestRiskPatientId() {
            if (demoPatients.length === 0) return "";
            const sorted = [...demoPatients].sort((left, right) => (right.triage_score || 0) - (left.triage_score || 0));
            const top = sorted[0];
            if (!top) return "";
            if (top.patient_id !== selectedPatientId) return top.patient_id;
            return sorted[1]?.patient_id || top.patient_id;
        }

        async function compareSelectedCases() {
            const selection = resolveComparisonSelection();
            const leftPatient = selection.leftPatient;
            const rightPatient = selection.rightPatient;
            const leftScanId = selection.leftScanId;
            const rightScanId = selection.rightScanId;

            updateComparisonSummaries();

            if (!leftPatient || !rightPatient) {
                renderComparisonPlaceholder("Select two patients before comparing cases.");
                return;
            }

            if (!leftScanId || !rightScanId) {
                renderComparisonPlaceholder("Comparison requires two valid scan IDs.");
                return;
            }

            if (leftScanId === rightScanId) {
                renderComparisonPlaceholder("Choose a different comparison patient to avoid identical scans.");
                return;
            }

            renderComparisonPlaceholder("Computing case deltas...");

            try {
                const url = `${API_BASE}/demo/compare?left_scan_id=${encodeURIComponent(leftScanId)}&right_scan_id=${encodeURIComponent(rightScanId)}`;
                const response = await fetch(url);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const payload = await response.json();

                const delta = payload.delta || {};
                const changedRegions = Array.isArray(payload.changed_regions) ? payload.changed_regions : [];
                const topRows = changedRegions.slice(0, 3).map((row) => {
                    const direction = row.delta_level > 0 ? "increased" : "reduced";
                    return `
                        <div class="compare-region-row">
                            <span>${row.region}</span>
                            <span>${direction} (${formatSignedValue(row.delta_level)})</span>
                        </div>
                    `;
                }).join("");

                const output = document.getElementById("compare-output");
                if (!output) return;

                const confidenceClass = Number(delta.confidence_pct || 0) >= 0 ? "positive" : "negative";
                const severeClass = Number(delta.severe_regions || 0) > 0 ? "negative" : "positive";
                const flaggedClass = Number(delta.flagged_regions || 0) > 0 ? "negative" : "positive";
                const triageClass = Number(delta.triage_score || 0) > 0 ? "negative" : "positive";

                output.innerHTML = `
                    <div><strong>${leftPatient.patient_code}</strong> versus <strong>${rightPatient.patient_code}</strong> (right minus left)</div>
                    <div class="compare-kpis">
                        <span class="compare-chip ${flaggedClass}">Flagged ${formatSignedValue(delta.flagged_regions)}</span>
                        <span class="compare-chip ${severeClass}">Severe ${formatSignedValue(delta.severe_regions)}</span>
                        <span class="compare-chip ${triageClass}">Triage ${formatSignedValue(delta.triage_score)}</span>
                        <span class="compare-chip ${confidenceClass}">Confidence ${formatSignedValue(delta.confidence_pct, "%")}</span>
                    </div>
                    <div class="compare-regions">
                        ${topRows || "<div class='compare-region-row'><span>No regional deltas detected.</span><span></span></div>"}
                    </div>
                `;
                updateComparisonSummaries();
            } catch (error) {
                renderComparisonPlaceholder(`Comparison unavailable: ${error.message}`);
            }
        }

        async function loadHighestRiskPatient() {
            const patientId = pickHighestRiskPatientId();
            if (!patientId) {
                updateStatus("No sample patient available for triage loading.");
                return;
            }
            setSelectedPatient(patientId);
            await loadDemo(patientId);
        }

        function setDicomMetaText(text) {
            const el = document.getElementById("dicom-meta");
            if (el) el.textContent = text;
        }

        function setDicomReadout(text) {
            const el = document.getElementById("dicom-measure-output");
            if (el) el.textContent = text;
        }

        function getDicomPresets() {
            return activeDicomStudy?.profile?.presets || DICOM_FALLBACK_PRESETS;
        }

        function getActiveDicomSeries() {
            const series = activeDicomStudy?.profile?.series || [];
            if (series.length === 0) return null;
            return series.find((entry) => entry.series_uid === dicomState.seriesUid) || series[0];
        }

        function stopDicomCine() {
            if (dicomCineTimer) {
                clearInterval(dicomCineTimer);
                dicomCineTimer = null;
            }
            const cineButton = document.getElementById("dicom-toggle-cine");
            if (cineButton) {
                cineButton.classList.remove("active");
                cineButton.textContent = "Start Cine";
            }
        }

        function updateDicomPlaneButtons() {
            document.querySelectorAll(".dicom-plane-btn").forEach((button) => {
                button.classList.toggle("active", button.dataset.plane === dicomState.plane);
            });
        }

        function updateDicomPresetButtons() {
            document.querySelectorAll(".dicom-preset-btn").forEach((button) => {
                button.classList.toggle("active", button.dataset.preset === dicomState.preset);
            });
        }

        function updateDicomValueLabels() {
            const ww = document.getElementById("dicom-ww-value");
            const wc = document.getElementById("dicom-wc-value");
            const slice = document.getElementById("dicom-slice-value");
            if (ww) ww.textContent = String(Math.round(dicomState.ww));
            if (wc) wc.textContent = String(Math.round(dicomState.wc));
            if (slice) slice.textContent = `${dicomState.slice} / ${dicomState.maxSlice}`;
        }

        function getVolumeVoxel(volume, x, y, z) {
            if (!volume) return 0;
            if (x < 0 || y < 0 || z < 0 || x >= volume.width || y >= volume.height || z >= volume.depth) return 0;
            const index = (z * volume.height * volume.width) + (y * volume.width) + x;
            return volume.data[index] || 0;
        }

        function getPlaneDimensions(volume, plane) {
            if (!volume) return { width: 1, height: 1, maxSlice: 1 };
            if (plane === "coronal") {
                return { width: volume.width, height: volume.depth, maxSlice: volume.height };
            }
            if (plane === "sagittal") {
                return { width: volume.height, height: volume.depth, maxSlice: volume.width };
            }
            return { width: volume.width, height: volume.height, maxSlice: volume.depth };
        }

        function getPlaneSpacing(volume, plane) {
            if (!volume) return [1.0, 1.0];
            if (plane === "coronal") return [volume.pixelSpacing[0], volume.sliceThickness];
            if (plane === "sagittal") return [volume.pixelSpacing[1], volume.sliceThickness];
            return [volume.pixelSpacing[0], volume.pixelSpacing[1]];
        }

        function getVoxelVolumeMm3(volume) {
            if (!volume) return 0;
            const spacingX = Number(volume.pixelSpacing?.[0] || 1.0);
            const spacingY = Number(volume.pixelSpacing?.[1] || 1.0);
            const spacingZ = Number(volume.sliceThickness || 1.0);
            return spacingX * spacingY * spacingZ;
        }

        function getSegmentationMask(segClass) {
            if (segClass === "edema") return clinicalState.segmentation.edemaMask;
            return clinicalState.segmentation.lesionMask;
        }

        function setSegmentationMask(segClass, mask) {
            if (segClass === "edema") {
                clinicalState.segmentation.edemaMask = mask;
                return;
            }
            clinicalState.segmentation.lesionMask = mask;
        }

        function createDilatedMask(baseMask, volume, radius = 1) {
            if (!volume || !baseMask) return null;
            const out = new Uint8Array(baseMask.length);
            const offsets = [];
            const r2 = radius * radius;

            for (let dz = -radius; dz <= radius; dz++) {
                for (let dy = -radius; dy <= radius; dy++) {
                    for (let dx = -radius; dx <= radius; dx++) {
                        if ((dx * dx) + (dy * dy) + (dz * dz) <= r2) {
                            offsets.push([dx, dy, dz]);
                        }
                    }
                }
            }

            for (let z = 0; z < volume.depth; z++) {
                for (let y = 0; y < volume.height; y++) {
                    for (let x = 0; x < volume.width; x++) {
                        const index = getVolumeIndex(volume, x, y, z);
                        if (index < 0 || baseMask[index] === 0) continue;

                        offsets.forEach(([dx, dy, dz]) => {
                            const nx = x + dx;
                            const ny = y + dy;
                            const nz = z + dz;
                            const nIndex = getVolumeIndex(volume, nx, ny, nz);
                            if (nIndex >= 0) {
                                out[nIndex] = 1;
                            }
                        });
                    }
                }
            }

            return out;
        }

        function buildAutoLesionMask(data, volume) {
            const voxelCount = volume.width * volume.height * volume.depth;
            const mask = new Uint8Array(voxelCount);
            const regions = normalizeRegions(data);
            let lesionCount = 0;

            for (let z = 0; z < volume.depth; z++) {
                const nz = ((z / Math.max(1, volume.depth - 1)) * 2) - 1;
                for (let y = 0; y < volume.height; y++) {
                    const ny = ((y / Math.max(1, volume.height - 1)) * 2) - 1;
                    for (let x = 0; x < volume.width; x++) {
                        const nx = ((x / Math.max(1, volume.width - 1)) * 2) - 1;
                        const index = getVolumeIndex(volume, x, y, z);
                        const intensity = volume.data[index] || 0;
                        const severity = resolveSeverityLevel(regions, nx, ny, nz);

                        const severeHit = severity >= 4 && intensity >= 48;
                        const moderateHit = severity === 3 && intensity >= 60;
                        const mildSparseHit = severity === 2 && intensity >= 96 && ((x + y + z) % 3 === 0);

                        if (severeHit || moderateHit || mildSparseHit) {
                            mask[index] = 1;
                            lesionCount += 1;
                        }
                    }
                }
            }

            // Keep downstream planning stable even for very low-signal demo cases.
            if (lesionCount < 18) {
                const cx = Math.floor(volume.width * 0.52);
                const cy = Math.floor(volume.height * 0.48);
                const cz = Math.floor(volume.depth * 0.54);
                const radius = Math.max(2, Math.round(Math.min(volume.width, volume.height, volume.depth) * 0.04));
                for (let z = Math.max(0, cz - radius); z <= Math.min(volume.depth - 1, cz + radius); z++) {
                    for (let y = Math.max(0, cy - radius); y <= Math.min(volume.height - 1, cy + radius); y++) {
                        for (let x = Math.max(0, cx - radius); x <= Math.min(volume.width - 1, cx + radius); x++) {
                            const distance2 = ((x - cx) * (x - cx)) + ((y - cy) * (y - cy)) + ((z - cz) * (z - cz));
                            if (distance2 > radius * radius) continue;
                            const index = getVolumeIndex(volume, x, y, z);
                            if (index >= 0) {
                                mask[index] = 1;
                            }
                        }
                    }
                }
            }

            return mask;
        }

        function buildUncertaintyMask(volume, lesionMask, edemaMask) {
            const uncertainty = new Uint8Array(volume.width * volume.height * volume.depth);

            for (let z = 0; z < volume.depth; z++) {
                for (let y = 0; y < volume.height; y++) {
                    for (let x = 0; x < volume.width; x++) {
                        const index = getVolumeIndex(volume, x, y, z);
                        const intensity = volume.data[index] || 0;
                        const lesion = lesionMask[index] > 0;
                        const edema = edemaMask[index] > 0;

                        let value = 0;
                        if (edema) value = Math.max(value, 80);
                        if (lesion) value = Math.max(value, 46);
                        if (intensity >= 42 && intensity <= 120) value = Math.max(value, 90);

                        if (lesion) {
                            const neighbors = [
                                getVolumeIndex(volume, x - 1, y, z),
                                getVolumeIndex(volume, x + 1, y, z),
                                getVolumeIndex(volume, x, y - 1, z),
                                getVolumeIndex(volume, x, y + 1, z),
                                getVolumeIndex(volume, x, y, z - 1),
                                getVolumeIndex(volume, x, y, z + 1),
                            ];
                            if (neighbors.some((nIndex) => nIndex >= 0 && lesionMask[nIndex] === 0)) {
                                value = Math.max(value, 170);
                            }
                        }

                        uncertainty[index] = value;
                    }
                }
            }

            return uncertainty;
        }

        function initializeClinicalSegmentation(data = analysisData) {
            if (!activeDicomVolume) {
                clinicalState.segmentation.lesionMask = null;
                clinicalState.segmentation.edemaMask = null;
                clinicalState.segmentation.uncertaintyMask = null;
                clinicalState.segmentation.scanId = "";
                return;
            }

            const expectedLength = activeDicomVolume.width * activeDicomVolume.height * activeDicomVolume.depth;
            const shouldRebuild = (
                clinicalState.segmentation.scanId !== (currentScanId || data?.scan_id || "") ||
                !clinicalState.segmentation.lesionMask ||
                clinicalState.segmentation.lesionMask.length !== expectedLength ||
                !clinicalState.segmentation.edemaMask ||
                clinicalState.segmentation.edemaMask.length !== expectedLength ||
                !clinicalState.segmentation.uncertaintyMask ||
                clinicalState.segmentation.uncertaintyMask.length !== expectedLength
            );

            if (!shouldRebuild) return;

            const lesionMask = buildAutoLesionMask(data, activeDicomVolume);
            const edemaMask = createDilatedMask(lesionMask, activeDicomVolume, 2) || new Uint8Array(expectedLength);
            const uncertaintyMask = buildUncertaintyMask(activeDicomVolume, lesionMask, edemaMask);

            clinicalState.segmentation.lesionMask = lesionMask;
            clinicalState.segmentation.edemaMask = edemaMask;
            clinicalState.segmentation.uncertaintyMask = uncertaintyMask;
            clinicalState.segmentation.scanId = currentScanId || data?.scan_id || "";
        }

        function getSegmentationCounts() {
            const lesionMask = clinicalState.segmentation.lesionMask;
            const edemaMask = clinicalState.segmentation.edemaMask;
            if (!lesionMask || !edemaMask) {
                return { lesion: 0, edema: 0 };
            }

            let lesion = 0;
            let edema = 0;
            for (let i = 0; i < lesionMask.length; i++) {
                if (lesionMask[i] > 0) lesion += 1;
                if (edemaMask[i] > 0) edema += 1;
            }
            return { lesion, edema };
        }

        function updateSegmentationVolumeOutput() {
            const output = document.getElementById("segmentation-volume-output");
            if (!output || !activeDicomVolume) {
                return;
            }

            const counts = getSegmentationCounts();
            const voxelMm3 = getVoxelVolumeMm3(activeDicomVolume);
            const lesionMl = (counts.lesion * voxelMm3) / 1000;
            const edemaMl = (counts.edema * voxelMm3) / 1000;

            output.innerHTML = `
                Lesion ${lesionMl.toFixed(2)} mL | Edema envelope ${edemaMl.toFixed(2)} mL<br>
                Voxel size ${voxelMm3.toFixed(2)} mm^3 | Brush ${clinicalState.segmentation.brushRadius}px ${clinicalState.segmentation.tool}
            `;
        }

        function computeLesionCentroidVoxel() {
            if (!activeDicomVolume || !clinicalState.segmentation.lesionMask) return null;

            let sumX = 0;
            let sumY = 0;
            let sumZ = 0;
            let count = 0;

            for (let z = 0; z < activeDicomVolume.depth; z++) {
                for (let y = 0; y < activeDicomVolume.height; y++) {
                    for (let x = 0; x < activeDicomVolume.width; x++) {
                        const index = getVolumeIndex(activeDicomVolume, x, y, z);
                        if (index < 0 || clinicalState.segmentation.lesionMask[index] === 0) continue;
                        sumX += x;
                        sumY += y;
                        sumZ += z;
                        count += 1;
                    }
                }
            }

            if (count <= 0) return null;
            return {
                x: sumX / count,
                y: sumY / count,
                z: sumZ / count,
            };
        }

        function distanceVoxelToNormalizedPointMm(voxel, normalizedPoint) {
            if (!activeDicomVolume || !voxel || !normalizedPoint) return Number.POSITIVE_INFINITY;
            const pointVoxel = normalizedToVoxel(activeDicomVolume, normalizedPoint);
            const sx = Number(activeDicomVolume.pixelSpacing?.[0] || 1);
            const sy = Number(activeDicomVolume.pixelSpacing?.[1] || 1);
            const sz = Number(activeDicomVolume.sliceThickness || 1);
            const dx = (voxel.x - pointVoxel.x) * sx;
            const dy = (voxel.y - pointVoxel.y) * sy;
            const dz = (voxel.z - pointVoxel.z) * sz;
            return Math.sqrt((dx * dx) + (dy * dy) + (dz * dz));
        }

        function updateCriticalStructureDistances() {
            const output = document.getElementById("critical-distance-list");
            if (!output || !activeDicomVolume) return;

            const lesionCentroid = computeLesionCentroidVoxel();
            if (!lesionCentroid) {
                output.textContent = "Lesion mask is not available yet. Load a case or enable segmentation overlays.";
                return;
            }

            const selectedStructures = Array.from(document.querySelectorAll("#critical-structure-toggles input:checked"))
                .map((input) => input.dataset.structure)
                .filter(Boolean);

            if (selectedStructures.length === 0) {
                output.textContent = "No critical structures selected. Enable at least one structure to compute proximity.";
                return;
            }

            const rows = selectedStructures.map((key) => {
                const profile = CRITICAL_STRUCTURE_PROFILES[key];
                if (!profile) return null;
                const closestMm = profile.points.reduce((best, point) => {
                    const distance = distanceVoxelToNormalizedPointMm(lesionCentroid, point);
                    return Math.min(best, distance);
                }, Number.POSITIVE_INFINITY);

                const riskTag = closestMm < 6 ? "high-risk corridor" : (closestMm < 12 ? "caution" : "clearance acceptable");
                return `<div>${profile.label}: ${closestMm.toFixed(1)} mm (${riskTag})</div>`;
            }).filter(Boolean);

            output.innerHTML = rows.join("") || "No structure distances available.";
        }

        function updateLinkedNavButton() {
            const button = document.getElementById("dicom-toggle-linked-nav");
            if (!button) return;
            button.classList.toggle("active", clinicalState.linkedNav);
            button.textContent = clinicalState.linkedNav ? "Linked Nav On" : "Linked Nav Off";
        }

        function updateSegmentationControls() {
            const lesionToggle = document.getElementById("seg-toggle-lesion");
            const edemaToggle = document.getElementById("seg-toggle-edema");
            const uncertaintyToggle = document.getElementById("seg-toggle-uncertainty");
            const editToggle = document.getElementById("seg-toggle-edit");
            const brushToggle = document.getElementById("seg-tool-brush");
            const eraseToggle = document.getElementById("seg-tool-erase");
            const brushSizeLabel = document.getElementById("seg-brush-size-value");

            if (lesionToggle) {
                lesionToggle.classList.toggle("active", clinicalState.segmentation.lesionVisible);
                lesionToggle.textContent = clinicalState.segmentation.lesionVisible ? "Lesion Overlay On" : "Lesion Overlay Off";
            }
            if (edemaToggle) {
                edemaToggle.classList.toggle("active", clinicalState.segmentation.edemaVisible);
                edemaToggle.textContent = clinicalState.segmentation.edemaVisible ? "Edema Overlay On" : "Edema Overlay Off";
            }
            if (uncertaintyToggle) {
                uncertaintyToggle.classList.toggle("active", clinicalState.segmentation.uncertaintyVisible);
                uncertaintyToggle.textContent = clinicalState.segmentation.uncertaintyVisible ? "Uncertainty On" : "Uncertainty Off";
            }
            if (editToggle) {
                editToggle.classList.toggle("active", clinicalState.segmentation.editMode);
                editToggle.textContent = clinicalState.segmentation.editMode ? "Edit Mode On" : "Edit Mode Off";
            }
            if (brushToggle) {
                brushToggle.classList.toggle("active", clinicalState.segmentation.tool === "brush");
            }
            if (eraseToggle) {
                eraseToggle.classList.toggle("active", clinicalState.segmentation.tool === "erase");
            }
            if (brushSizeLabel) {
                brushSizeLabel.textContent = `${clinicalState.segmentation.brushRadius} px`;
            }
        }

        function renderPlaneIntoCanvas(canvas, plane, sliceNumber) {
            if (!canvas) return;
            const ctx = canvas.getContext("2d");
            if (!ctx) return;

            if (!activeDicomVolume) {
                ctx.fillStyle = "#172436";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                return;
            }

            const frame = getPlaneDimensions(activeDicomVolume, plane);
            const safeSlice = clampValue(Math.round(sliceNumber), 1, frame.maxSlice);
            const sliceIndex = safeSlice - 1;
            const renderWidth = Math.max(120, Math.round(canvas.clientWidth || canvas.width || 224));
            const renderHeight = Math.max(120, Math.round(canvas.clientHeight || canvas.height || 224));
            canvas.width = renderWidth;
            canvas.height = renderHeight;

            const sourceXFactor = frame.width <= 1 ? 0 : ((frame.width - 1) / Math.max(1, renderWidth - 1));
            const sourceYFactor = frame.height <= 1 ? 0 : ((frame.height - 1) / Math.max(1, renderHeight - 1));

            const image = ctx.createImageData(renderWidth, renderHeight);
            const ww = Math.max(1, Number(dicomState.ww || 80));
            const wc = Number(dicomState.wc || 40);
            const low = wc - (ww / 2);
            const high = wc + (ww / 2);

            const lesionMask = clinicalState.segmentation.lesionMask;
            const edemaMask = clinicalState.segmentation.edemaMask;
            const uncertaintyMask = clinicalState.segmentation.uncertaintyMask;

            for (let py = 0; py < renderHeight; py++) {
                const sampleY = frame.height <= 1 ? 0 : (py * sourceYFactor);
                for (let px = 0; px < renderWidth; px++) {
                    const sampleX = frame.width <= 1 ? 0 : (px * sourceXFactor);
                    const raw = sampleDicomSliceBilinear(activeDicomVolume, plane, sliceIndex, sampleX, sampleY, frame);
                    let normalized = (raw - low) / (high - low);
                    normalized = Math.max(0, Math.min(1, normalized));

                    let red = Math.round(normalized * 255);
                    let green = red;
                    let blue = red;

                    const voxelIndex = mapPlaneSampleToVoxelIndex(plane, sliceIndex, sampleX, sampleY, frame);
                    if (voxelIndex >= 0) {
                        if (clinicalState.segmentation.edemaVisible && edemaMask && edemaMask[voxelIndex] > 0) {
                            red = Math.round((red * 0.65) + 68);
                            green = Math.round((green * 0.80) + 86);
                        }
                        if (clinicalState.segmentation.lesionVisible && lesionMask && lesionMask[voxelIndex] > 0) {
                            red = Math.round((red * 0.35) + 176);
                            green = Math.round(green * 0.34);
                            blue = Math.round(blue * 0.34);
                        }
                        if (clinicalState.segmentation.uncertaintyVisible && uncertaintyMask) {
                            const uncertainty = uncertaintyMask[voxelIndex] / 255;
                            if (uncertainty > 0.03) {
                                const blend = uncertainty * 0.34;
                                red = Math.round((red * (1 - blend)) + (92 * blend));
                                green = Math.round((green * (1 - blend)) + (154 * blend));
                                blue = Math.round((blue * (1 - blend)) + (205 * blend));
                            }
                        }
                    }

                    const outIndex = (py * renderWidth + px) * 4;
                    image.data[outIndex] = dicomState.invert ? (255 - red) : red;
                    image.data[outIndex + 1] = dicomState.invert ? (255 - green) : green;
                    image.data[outIndex + 2] = dicomState.invert ? (255 - blue) : blue;
                    image.data[outIndex + 3] = 255;
                }
            }

            ctx.putImageData(image, 0, 0);

            if (dicomState.crosshair) {
                const target = projectVoxelToPlanePoint(plane, clinicalState.navVoxel, frame);
                const scaleX = (renderWidth - 1) / Math.max(1, frame.width - 1);
                const scaleY = (renderHeight - 1) / Math.max(1, frame.height - 1);
                const crossX = target.x * scaleX;
                const crossY = target.y * scaleY;
                ctx.save();
                ctx.strokeStyle = "rgba(255, 190, 78, 0.78)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(crossX, 0);
                ctx.lineTo(crossX, renderHeight);
                ctx.moveTo(0, crossY);
                ctx.lineTo(renderWidth, crossY);
                ctx.stroke();
                ctx.restore();
            }
        }

        function renderTriPlanarCanvases() {
            const axial = document.getElementById("tri-canvas-axial");
            const coronal = document.getElementById("tri-canvas-coronal");
            const sagittal = document.getElementById("tri-canvas-sagittal");

            renderPlaneIntoCanvas(axial, "axial", getNavSliceForPlane("axial"));
            renderPlaneIntoCanvas(coronal, "coronal", getNavSliceForPlane("coronal"));
            renderPlaneIntoCanvas(sagittal, "sagittal", getNavSliceForPlane("sagittal"));
        }

        function updateNavFromPlanePoint(plane, sliceIndex, point, syncMainToPlane = false) {
            if (!activeDicomVolume) return;
            const frame = getPlaneDimensions(activeDicomVolume, plane);
            const voxel = mapPlanePointToVoxel(plane, sliceIndex, point, frame);
            if (!voxel) return;

            clinicalState.navVoxel = voxel;
            clampNavVoxelToVolume();
            if (clinicalState.linkedNav) {
                syncMainSliceFromNav(syncMainToPlane ? plane : dicomState.plane);
            }
            renderDicomSlice();
        }

        function applyDicomContextPreset() {
            const select = document.getElementById("dicom-context-select");
            const requested = select?.value || "auto";
            const resolved = requested === "auto"
                ? ((analysisData?.risk_band || "").toLowerCase() === "high" ? "stroke" : "brain")
                : requested;

            const preset = DICOM_CONTEXT_PRESETS[resolved] || DICOM_CONTEXT_PRESETS.brain;
            dicomState.preset = preset.preset;
            dicomState.ww = Number(preset.ww);
            dicomState.wc = Number(preset.wc);

            const wwSlider = document.getElementById("dicom-ww-slider");
            const wcSlider = document.getElementById("dicom-wc-slider");
            if (wwSlider) wwSlider.value = String(Math.round(dicomState.ww));
            if (wcSlider) wcSlider.value = String(Math.round(dicomState.wc));

            renderDicomSlice();
        }

        function editSegmentationAtVoxel(voxel) {
            if (!activeDicomVolume || !voxel) return;
            const mask = getSegmentationMask(clinicalState.segmentation.editClass);
            if (!mask) return;

            const radius = Math.max(1, Math.round(clinicalState.segmentation.brushRadius));
            const brushValue = clinicalState.segmentation.tool === "erase" ? 0 : 1;
            const plane = dicomState.plane;

            for (let dy = -radius; dy <= radius; dy++) {
                for (let dx = -radius; dx <= radius; dx++) {
                    if ((dx * dx) + (dy * dy) > (radius * radius)) continue;

                    let x = voxel.x;
                    let y = voxel.y;
                    let z = voxel.z;

                    if (plane === "coronal") {
                        x += dx;
                        z += dy;
                    } else if (plane === "sagittal") {
                        y += dx;
                        z += dy;
                    } else {
                        x += dx;
                        y -= dy;
                    }

                    const index = getVolumeIndex(activeDicomVolume, x, y, z);
                    if (index >= 0) {
                        mask[index] = brushValue;
                    }
                }
            }

            if (clinicalState.segmentation.editClass === "lesion") {
                clinicalState.segmentation.edemaMask = createDilatedMask(mask, activeDicomVolume, 2) || clinicalState.segmentation.edemaMask;
            }

            clinicalState.segmentation.uncertaintyMask = buildUncertaintyMask(
                activeDicomVolume,
                clinicalState.segmentation.lesionMask || new Uint8Array(mask.length),
                clinicalState.segmentation.edemaMask || new Uint8Array(mask.length),
            );

            updateSegmentationVolumeOutput();
            updateCriticalStructureDistances();
            renderDicomSlice();
        }

        function toggleSegmentationVisibility(layer) {
            if (layer === "lesion") {
                clinicalState.segmentation.lesionVisible = !clinicalState.segmentation.lesionVisible;
            } else if (layer === "edema") {
                clinicalState.segmentation.edemaVisible = !clinicalState.segmentation.edemaVisible;
            } else if (layer === "uncertainty") {
                clinicalState.segmentation.uncertaintyVisible = !clinicalState.segmentation.uncertaintyVisible;
            }
            updateSegmentationControls();
            renderDicomSlice();
        }

        function toggleSegmentationEditMode() {
            clinicalState.segmentation.editMode = !clinicalState.segmentation.editMode;
            if (clinicalState.segmentation.editMode && dicomState.measuring) {
                dicomState.measuring = false;
                resetDicomMeasurement();
                const measureButton = document.getElementById("dicom-toggle-measure");
                if (measureButton) {
                    measureButton.classList.remove("active");
                    measureButton.textContent = "Measure Off";
                }
            }
            if (clinicalState.segmentation.editMode) {
                setDicomReadout("Segmentation edit mode active. Click or drag on DICOM viewport to paint mask adjustments.");
            } else {
                setDicomReadout(dicomMeasurementInstruction(dicomState.measureTool, dicomState.measuring));
            }
            updateSegmentationControls();
        }

        function setSegmentationTool(tool) {
            clinicalState.segmentation.tool = tool === "erase" ? "erase" : "brush";
            updateSegmentationControls();
        }

        function handleTriCanvasClick(event) {
            if (!activeDicomVolume) return;
            const canvas = event.currentTarget;
            const plane = canvas?.dataset?.plane || "axial";
            const frame = getPlaneDimensions(activeDicomVolume, plane);
            const rect = canvas.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return;

            const normalizedX = clampValue((event.clientX - rect.left) / rect.width, 0, 1);
            const normalizedY = clampValue((event.clientY - rect.top) / rect.height, 0, 1);
            const point = {
                x: normalizedX * Math.max(0, frame.width - 1),
                y: normalizedY * Math.max(0, frame.height - 1),
            };

            const slice = getNavSliceForPlane(plane);
            updateNavFromPlanePoint(plane, slice - 1, point, true);
        }

        function refreshLongitudinalOutputs() {
            updateComparisonSummaries();
            updateLongitudinalSummary();
        }

        function runVolumeEstimation() {
            if (!activeDicomVolume) {
                updateStatus("Load a scan before estimating lesion volume.");
                return;
            }
            updateSegmentationVolumeOutput();
            updateCriticalStructureDistances();
            updateStatus("Segmentation volume estimate refreshed for lesion and edema masks.");
        }

        function percentileFromHistogram(histogram, sampleCount, quantile) {
            if (!sampleCount || sampleCount <= 0) return 0;
            const target = Math.max(1, Math.round(sampleCount * quantile));
            let cumulative = 0;
            for (let i = 0; i < histogram.length; i++) {
                cumulative += histogram[i];
                if (cumulative >= target) return i;
            }
            return histogram.length - 1;
        }

        function buildDicomVolumeFromPayload(volumePayload, series) {
            const shape = Array.isArray(volumePayload?.shape) ? volumePayload.shape : [0, 0, 0];
            const [width, height, depth] = shape.map((value) => Math.max(1, Number(value) || 1));
            const voxelCount = width * height * depth;
            if (voxelCount <= 1) {
                throw new Error("Invalid volumetric shape for DICOM rendering");
            }

            const packed = decodeBase64ToUint8Array(volumePayload?.volume_b64 || "");
            const expectedLength = voxelCount * 4;
            if (packed.length !== expectedLength) {
                throw new Error(`Unexpected volume payload size for DICOM view (${packed.length} vs ${expectedLength})`);
            }

            const values = new Uint8Array(voxelCount);
            const histogram = new Uint32Array(256);
            let nonZeroSamples = 0;

            for (let i = 0, p = 0; i < voxelCount; i++, p += 4) {
                const intensity = packed[p];
                const grayMatter = packed[p + 1];
                const whiteMatter = packed[p + 2];

                // Blend structural channels for better workstation-style contrast.
                const composite = Math.max(intensity, Math.round((grayMatter * 0.58) + (whiteMatter * 0.42)));
                values[i] = composite;

                if (composite > 0) {
                    histogram[composite] += 1;
                    nonZeroSamples += 1;
                }
            }

            const p10 = percentileFromHistogram(histogram, nonZeroSamples, 0.10);
            const p95 = percentileFromHistogram(histogram, nonZeroSamples, 0.95);
            const windowWidth = Math.max(36, p95 - p10);
            const windowCenter = Math.round((p95 + p10) / 2);

            const spacing = Array.isArray(volumePayload?.spacing_mm) ? volumePayload.spacing_mm : [];
            const pixelSpacing = [
                Number(spacing[0] || series?.pixel_spacing_mm?.[0] || 1.0),
                Number(spacing[1] || series?.pixel_spacing_mm?.[1] || 1.0),
            ];
            const sliceThickness = Number(spacing[2] || series?.slice_thickness_mm || 1.0);

            return {
                width,
                height,
                depth,
                data: values,
                pixelSpacing,
                sliceThickness,
                windowWidth,
                windowCenter,
                syntheticFallback: Boolean(volumePayload?.synthetic_fallback),
                resolutionProfile: String(volumePayload?.resolution_profile || "standard"),
            };
        }

        function buildSyntheticDicomVolume(data, series) {
            const width = 96;
            const height = 96;
            const depth = Math.max(52, Math.min(128, Number(series?.slice_count || 96)));
            const pixelSpacing = Array.isArray(series?.pixel_spacing_mm)
                ? [Number(series.pixel_spacing_mm[0] || 0.8), Number(series.pixel_spacing_mm[1] || 0.8)]
                : [0.8, 0.8];
            const sliceThickness = Number(series?.slice_thickness_mm || 1.2);
            const regions = normalizeRegions(data);
            const values = new Uint8Array(width * height * depth);

            for (let z = 0; z < depth; z++) {
                const nz = (z / (depth - 1)) * 2 - 1;
                for (let y = 0; y < height; y++) {
                    const ny = (y / (height - 1)) * 2 - 1;
                    for (let x = 0; x < width; x++) {
                        const nx = (x / (width - 1)) * 2 - 1;
                        const idx = (z * height * width) + (y * width) + x;
                        const insideBrain = ((nx * nx * 1.15) + (ny * ny * 1.25) + (nz * nz * 0.92)) <= 1;

                        if (!insideBrain) {
                            values[idx] = 0;
                            continue;
                        }

                        let intensity = 42 + (36 * Math.exp(-(nx * nx + ny * ny + nz * nz) * 1.6));
                        intensity += (Math.sin(nx * 8.5) + Math.cos(ny * 7.2) + Math.sin(nz * 5.7)) * 3.4;

                        for (const region of regions) {
                            const level = region?.severity_level || 0;
                            if (level < 2) continue;
                            if (regionMatchesCoordinate(region.anatomical_name, nx, ny, nz)) {
                                intensity += (level * 8.5);
                            }
                        }

                        values[idx] = Math.max(0, Math.min(255, Math.round(intensity)));
                    }
                }
            }

            return {
                width,
                height,
                depth,
                data: values,
                pixelSpacing,
                sliceThickness,
            };
        }

        function resetDicomMeasurement() {
            dicomState.measureStart = null;
            dicomState.measureEnd = null;
            dicomState.measurePreview = null;
            dicomState.measurePoints = [];
            dicomState.measureAreaClosed = false;
        }

        function dicomMeasurementInstruction(tool, enabled = true) {
            const selectedTool = String(tool || "distance");
            if (!enabled) {
                return "Measure mode off. Enable Measure and select Distance, Angle, or Area.";
            }
            if (selectedTool === "angle") {
                return "Angle tool active. Click point A, then apex point B, then point C. Move cursor for live preview.";
            }
            if (selectedTool === "area") {
                return "Area tool active. Click polygon vertices around region. Click near first point to close. Use Clear Measure to restart.";
            }
            return "Distance tool active. Click point A, move cursor for preview, then click point B to lock distance.";
        }

        function updateDicomMeasureToolButtons() {
            document.querySelectorAll(".dicom-measure-tool").forEach((button) => {
                button.classList.toggle("active", button.dataset.tool === dicomState.measureTool);
            });
        }

        function setDicomMeasureTool(tool) {
            const nextTool = ["distance", "angle", "area"].includes(tool) ? tool : "distance";
            if (dicomState.measureTool === nextTool) return;
            dicomState.measureTool = nextTool;
            resetDicomMeasurement();
            updateDicomMeasureToolButtons();
            setDicomReadout(dicomMeasurementInstruction(nextTool, dicomState.measuring));
            renderDicomSlice();
        }

        function computeDicomMeasurementMm(startPoint, endPoint, volume, plane) {
            const spacing = getPlaneSpacing(volume, plane);
            const dx = (endPoint.x - startPoint.x) * spacing[0];
            const dy = (endPoint.y - startPoint.y) * spacing[1];
            return Math.sqrt((dx * dx) + (dy * dy));
        }

        function computeDicomAngleDegrees(points, volume, plane) {
            if (!points || points.length < 3) return 0;
            const spacing = getPlaneSpacing(volume, plane);
            const p0 = { x: points[0].x * spacing[0], y: points[0].y * spacing[1] };
            const p1 = { x: points[1].x * spacing[0], y: points[1].y * spacing[1] };
            const p2 = { x: points[2].x * spacing[0], y: points[2].y * spacing[1] };

            const v1x = p0.x - p1.x;
            const v1y = p0.y - p1.y;
            const v2x = p2.x - p1.x;
            const v2y = p2.y - p1.y;

            const mag1 = Math.hypot(v1x, v1y);
            const mag2 = Math.hypot(v2x, v2y);
            if (mag1 <= 1e-6 || mag2 <= 1e-6) return 0;

            const dot = (v1x * v2x) + (v1y * v2y);
            const cosValue = Math.max(-1, Math.min(1, dot / (mag1 * mag2)));
            return (Math.acos(cosValue) * 180) / Math.PI;
        }

        function computeDicomPolygonAreaMm2(points, volume, plane) {
            if (!points || points.length < 3) return 0;
            const spacing = getPlaneSpacing(volume, plane);
            let twiceArea = 0;
            for (let i = 0; i < points.length; i++) {
                const current = points[i];
                const next = points[(i + 1) % points.length];
                const x1 = current.x * spacing[0];
                const y1 = current.y * spacing[1];
                const x2 = next.x * spacing[0];
                const y2 = next.y * spacing[1];
                twiceArea += (x1 * y2) - (x2 * y1);
            }
            return Math.abs(twiceArea) * 0.5;
        }

        function computeDicomPathLengthMm(points, volume, plane, closePath = false) {
            if (!points || points.length < 2) return 0;
            let total = 0;
            for (let i = 1; i < points.length; i++) {
                total += computeDicomMeasurementMm(points[i - 1], points[i], volume, plane);
            }
            if (closePath && points.length > 2) {
                total += computeDicomMeasurementMm(points[points.length - 1], points[0], volume, plane);
            }
            return total;
        }

        function formatDicomMeasurement(startPoint, endPoint, volume, plane, prefix = "Distance") {
            const mm = computeDicomMeasurementMm(startPoint, endPoint, volume, plane);
            const px = Math.hypot(endPoint.x - startPoint.x, endPoint.y - startPoint.y);
            const spacing = getPlaneSpacing(volume, plane);
            const deltaX = Math.abs(endPoint.x - startPoint.x) * spacing[0];
            const deltaY = Math.abs(endPoint.y - startPoint.y) * spacing[1];
            return `${prefix}: ${mm.toFixed(2)} mm (${px.toFixed(1)} px) | Î”x ${deltaX.toFixed(2)} mm | Î”y ${deltaY.toFixed(2)} mm on ${plane} plane.`;
        }

        function formatDicomAngleMeasurement(points, volume, plane, prefix = "Angle") {
            if (!points || points.length < 3) {
                return `${prefix}: ${points?.length || 0} points captured (need 3 points: A, apex B, C).`;
            }
            const angle = computeDicomAngleDegrees(points, volume, plane);
            const sideAB = computeDicomMeasurementMm(points[0], points[1], volume, plane);
            const sideBC = computeDicomMeasurementMm(points[1], points[2], volume, plane);
            return `${prefix}: ${angle.toFixed(1)} deg | AB ${sideAB.toFixed(2)} mm | BC ${sideBC.toFixed(2)} mm on ${plane} plane.`;
        }

        function formatDicomAreaMeasurement(points, volume, plane, prefix = "Area") {
            if (!points || points.length < 3) {
                return `${prefix}: ${points?.length || 0} vertices captured (need 3+ for area).`;
            }
            const area = computeDicomPolygonAreaMm2(points, volume, plane);
            const perimeter = computeDicomPathLengthMm(points, volume, plane, true);
            return `${prefix}: ${area.toFixed(2)} mm^2 | Perimeter ${perimeter.toFixed(2)} mm on ${plane} plane.`;
        }

        function getDicomCanvasPoint(event) {
            const canvas = document.getElementById("dicom-canvas");
            if (!canvas) return null;

            const frameWidth = Math.max(1, Number(dicomState.frameWidth || 1));
            const frameHeight = Math.max(1, Number(dicomState.frameHeight || 1));
            const rect = canvas.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return null;

            const normalizedX = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
            const normalizedY = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));

            return {
                x: Math.round(normalizedX * (frameWidth - 1)),
                y: Math.round(normalizedY * (frameHeight - 1)),
            };
        }

        function computeDicomRenderDimensions(frame) {
            const largestEdge = Math.max(frame.width, frame.height, 1);
            const baseScale = Math.max(1, Math.floor(DICOM_TARGET_RENDER_EDGE / largestEdge));

            const rawWidth = frame.width * baseScale;
            const rawHeight = frame.height * baseScale;
            const limiter = Math.max(rawWidth / DICOM_MAX_RENDER_EDGE, rawHeight / DICOM_MAX_RENDER_EDGE, 1);

            return {
                width: Math.max(1, Math.round(rawWidth / limiter)),
                height: Math.max(1, Math.round(rawHeight / limiter)),
            };
        }

        function sampleDicomSliceBilinear(volume, plane, sliceIndex, sampleX, sampleY, frame) {
            const x0 = Math.max(0, Math.min(frame.width - 1, Math.floor(sampleX)));
            const y0 = Math.max(0, Math.min(frame.height - 1, Math.floor(sampleY)));
            const x1 = Math.max(0, Math.min(frame.width - 1, x0 + 1));
            const y1 = Math.max(0, Math.min(frame.height - 1, y0 + 1));
            const tx = Math.max(0, Math.min(1, sampleX - x0));
            const ty = Math.max(0, Math.min(1, sampleY - y0));

            const readSample = (sx, sy) => {
                let vx = 0;
                let vy = 0;
                let vz = 0;

                if (plane === "coronal") {
                    vx = sx;
                    vy = sliceIndex;
                    vz = frame.height - 1 - sy;
                } else if (plane === "sagittal") {
                    vx = sliceIndex;
                    vy = sx;
                    vz = frame.height - 1 - sy;
                } else {
                    vx = sx;
                    vy = frame.height - 1 - sy;
                    vz = sliceIndex;
                }

                return getVolumeVoxel(volume, vx, vy, vz);
            };

            const v00 = readSample(x0, y0);
            const v10 = readSample(x1, y0);
            const v01 = readSample(x0, y1);
            const v11 = readSample(x1, y1);

            const v0 = v00 + ((v10 - v00) * tx);
            const v1 = v01 + ((v11 - v01) * tx);
            return v0 + ((v1 - v0) * ty);
        }

        function drawDicomMeasurementOverlay(ctx, frame, renderWidth, renderHeight) {
            const tool = dicomState.measureTool;
            const points = [...(dicomState.measurePoints || [])];

            if (dicomState.measurePreview) {
                if (tool === "distance" && points.length === 1) {
                    points.push(dicomState.measurePreview);
                } else if (tool === "angle" && points.length >= 1 && points.length < 3) {
                    points.push(dicomState.measurePreview);
                } else if (tool === "area" && points.length >= 1) {
                    points.push(dicomState.measurePreview);
                }
            }

            if (points.length === 0) return;

            const scaleX = (renderWidth - 1) / Math.max(1, frame.width - 1);
            const scaleY = (renderHeight - 1) / Math.max(1, frame.height - 1);
            const project = (point) => ({
                x: point.x * scaleX,
                y: point.y * scaleY,
            });
            const projected = points.map(project);

            const markerRadius = Math.max(2.8, Math.min(5.2, 2.8 * Math.min(scaleX, scaleY)));
            const lineWidth = Math.max(1.1, Math.min(2.2, 1.1 * Math.min(scaleX, scaleY)));

            ctx.save();
            ctx.strokeStyle = "#52d1f5";
            ctx.fillStyle = "#52d1f5";
            ctx.lineWidth = lineWidth;

            if (tool === "distance") {
                if (projected.length >= 2) {
                    ctx.beginPath();
                    ctx.moveTo(projected[0].x, projected[0].y);
                    ctx.lineTo(projected[1].x, projected[1].y);
                    ctx.stroke();
                }
            } else if (tool === "angle") {
                if (projected.length >= 2) {
                    ctx.beginPath();
                    ctx.moveTo(projected[0].x, projected[0].y);
                    ctx.lineTo(projected[1].x, projected[1].y);
                    ctx.stroke();
                }
                if (projected.length >= 3) {
                    ctx.beginPath();
                    ctx.moveTo(projected[1].x, projected[1].y);
                    ctx.lineTo(projected[2].x, projected[2].y);
                    ctx.stroke();

                    const a = projected[0];
                    const b = projected[1];
                    const c = projected[2];
                    const startAngle = Math.atan2(a.y - b.y, a.x - b.x);
                    const endAngle = Math.atan2(c.y - b.y, c.x - b.x);
                    const rawDelta = ((endAngle - startAngle + (Math.PI * 3)) % (Math.PI * 2)) - Math.PI;
                    const arcRadius = Math.max(12, Math.min(30, Math.min(renderWidth, renderHeight) * 0.04));

                    ctx.strokeStyle = "rgba(82, 209, 245, 0.7)";
                    ctx.beginPath();
                    ctx.arc(b.x, b.y, arcRadius, startAngle, startAngle + rawDelta, rawDelta < 0);
                    ctx.stroke();
                    ctx.strokeStyle = "#52d1f5";
                }
            } else if (tool === "area") {
                if (projected.length >= 2) {
                    ctx.beginPath();
                    ctx.moveTo(projected[0].x, projected[0].y);
                    for (let i = 1; i < projected.length; i++) {
                        ctx.lineTo(projected[i].x, projected[i].y);
                    }
                    ctx.stroke();
                }
                if (projected.length >= 3) {
                    ctx.beginPath();
                    ctx.moveTo(projected[0].x, projected[0].y);
                    for (let i = 1; i < projected.length; i++) {
                        ctx.lineTo(projected[i].x, projected[i].y);
                    }
                    ctx.closePath();
                    ctx.fillStyle = "rgba(82, 209, 245, 0.18)";
                    ctx.fill();
                    ctx.fillStyle = "#52d1f5";
                }
            }

            projected.forEach((point) => {
                ctx.beginPath();
                ctx.arc(point.x, point.y, markerRadius, 0, Math.PI * 2);
                ctx.fill();
            });

            let labelText = "";
            let labelX = projected[0]?.x || 0;
            let labelY = projected[0]?.y || 0;

            if (tool === "distance" && points.length >= 2) {
                const mm = computeDicomMeasurementMm(points[0], points[1], activeDicomVolume, dicomState.plane);
                labelText = `${mm.toFixed(2)} mm`;
                labelX = (projected[0].x + projected[1].x) * 0.5;
                labelY = (projected[0].y + projected[1].y) * 0.5;
            } else if (tool === "angle" && points.length >= 3) {
                const deg = computeDicomAngleDegrees(points, activeDicomVolume, dicomState.plane);
                labelText = `${deg.toFixed(1)} deg`;
                labelX = projected[1].x;
                labelY = projected[1].y;
            } else if (tool === "area" && points.length >= 3) {
                const areaMm2 = computeDicomPolygonAreaMm2(points, activeDicomVolume, dicomState.plane);
                labelText = `${areaMm2.toFixed(2)} mm^2`;
                labelX = projected.reduce((sum, point) => sum + point.x, 0) / projected.length;
                labelY = projected.reduce((sum, point) => sum + point.y, 0) / projected.length;
            }

            if (labelText) {
                const fontSize = Math.max(12, Math.min(16, Math.round(11 * Math.min(scaleX, scaleY))));
                ctx.font = `600 ${fontSize}px Sora, sans-serif`;
                ctx.textBaseline = "alphabetic";

                const paddingX = 6;
                const paddingY = 4;
                const textWidth = ctx.measureText(labelText).width;
                const boxWidth = textWidth + (paddingX * 2);
                const boxHeight = fontSize + (paddingY * 2);
                const boxX = Math.max(6, Math.min(renderWidth - boxWidth - 6, labelX - (boxWidth / 2)));
                const boxY = Math.max(6, Math.min(renderHeight - boxHeight - 6, labelY - boxHeight - 8));

                ctx.fillStyle = "rgba(12, 27, 43, 0.72)";
                ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
                ctx.fillStyle = "#d6f4ff";
                ctx.fillText(labelText, boxX + paddingX, boxY + boxHeight - paddingY - 1);
            }

            ctx.restore();
        }

        function renderDicomSlice() {
            const canvas = document.getElementById("dicom-canvas");
            if (!canvas) return;
            const ctx = canvas.getContext("2d");
            if (!ctx) return;
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = "high";

            if (!activeDicomVolume) {
                ctx.fillStyle = "#172436";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                dicomState.frameWidth = Math.max(1, canvas.width);
                dicomState.frameHeight = Math.max(1, canvas.height);
                renderTriPlanarCanvases();
                return;
            }

            initializeClinicalSegmentation(analysisData);
            clampNavVoxelToVolume();

            const frame = getPlaneDimensions(activeDicomVolume, dicomState.plane);
            dicomState.maxSlice = frame.maxSlice;
            dicomState.slice = Math.max(1, Math.min(dicomState.slice, frame.maxSlice));

            const sliceSlider = document.getElementById("dicom-slice-slider");
            if (sliceSlider) {
                sliceSlider.max = String(frame.maxSlice);
                sliceSlider.value = String(dicomState.slice);
            }

            const renderDimensions = computeDicomRenderDimensions(frame);
            canvas.width = renderDimensions.width;
            canvas.height = renderDimensions.height;
            dicomState.frameWidth = frame.width;
            dicomState.frameHeight = frame.height;

            const renderWidth = canvas.width;
            const renderHeight = canvas.height;
            const sourceXFactor = frame.width <= 1 ? 0 : ((frame.width - 1) / Math.max(1, renderWidth - 1));
            const sourceYFactor = frame.height <= 1 ? 0 : ((frame.height - 1) / Math.max(1, renderHeight - 1));

            const image = ctx.createImageData(renderWidth, renderHeight);
            const ww = Math.max(1, Number(dicomState.ww || 80));
            const wc = Number(dicomState.wc || 40);
            const low = wc - (ww / 2);
            const high = wc + (ww / 2);
            const sliceIndex = dicomState.slice - 1;
            const lesionMask = clinicalState.segmentation.lesionMask;
            const edemaMask = clinicalState.segmentation.edemaMask;
            const uncertaintyMask = clinicalState.segmentation.uncertaintyMask;

            if (clinicalState.linkedNav) {
                syncNavFromActiveDicomSlice();
            }

            for (let py = 0; py < renderHeight; py++) {
                const sampleY = frame.height <= 1 ? 0 : (py * sourceYFactor);
                for (let px = 0; px < renderWidth; px++) {
                    const sampleX = frame.width <= 1 ? 0 : (px * sourceXFactor);
                    const raw = sampleDicomSliceBilinear(
                        activeDicomVolume,
                        dicomState.plane,
                        sliceIndex,
                        sampleX,
                        sampleY,
                        frame,
                    );
                    let normalized = (raw - low) / (high - low);
                    normalized = Math.max(0, Math.min(1, normalized));

                    let red = Math.round(normalized * 255);
                    let green = red;
                    let blue = red;

                    const voxelIndex = mapPlaneSampleToVoxelIndex(dicomState.plane, sliceIndex, sampleX, sampleY, frame);
                    if (voxelIndex >= 0) {
                        if (clinicalState.segmentation.edemaVisible && edemaMask && edemaMask[voxelIndex] > 0) {
                            red = Math.round((red * 0.65) + 68);
                            green = Math.round((green * 0.80) + 86);
                        }
                        if (clinicalState.segmentation.lesionVisible && lesionMask && lesionMask[voxelIndex] > 0) {
                            red = Math.round((red * 0.35) + 176);
                            green = Math.round(green * 0.34);
                            blue = Math.round(blue * 0.34);
                        }
                        if (clinicalState.segmentation.uncertaintyVisible && uncertaintyMask) {
                            const uncertainty = uncertaintyMask[voxelIndex] / 255;
                            if (uncertainty > 0.03) {
                                const blend = uncertainty * 0.34;
                                red = Math.round((red * (1 - blend)) + (92 * blend));
                                green = Math.round((green * (1 - blend)) + (154 * blend));
                                blue = Math.round((blue * (1 - blend)) + (205 * blend));
                            }
                        }
                    }

                    const index = (py * renderWidth + px) * 4;
                    image.data[index] = dicomState.invert ? (255 - red) : red;
                    image.data[index + 1] = dicomState.invert ? (255 - green) : green;
                    image.data[index + 2] = dicomState.invert ? (255 - blue) : blue;
                    image.data[index + 3] = 255;
                }
            }

            ctx.putImageData(image, 0, 0);

            if (dicomState.crosshair) {
                const crossPoint = projectVoxelToPlanePoint(dicomState.plane, clinicalState.navVoxel, frame);
                const crossX = crossPoint.x * ((renderWidth - 1) / Math.max(1, frame.width - 1));
                const crossY = crossPoint.y * ((renderHeight - 1) / Math.max(1, frame.height - 1));
                ctx.save();
                ctx.strokeStyle = "rgba(255, 186, 76, 0.78)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(crossX, 0);
                ctx.lineTo(crossX, renderHeight);
                ctx.moveTo(0, crossY);
                ctx.lineTo(renderWidth, crossY);
                ctx.stroke();
                ctx.restore();
            }

            drawDicomMeasurementOverlay(ctx, frame, renderWidth, renderHeight);

            updateDicomValueLabels();
            updateDicomPlaneButtons();
            updateDicomPresetButtons();
            updateDicomMeasureToolButtons();
            renderTriPlanarCanvases();
        }

        function applyDicomPreset(presetName) {
            const presets = getDicomPresets();
            const preset = presets[presetName] || DICOM_FALLBACK_PRESETS[presetName] || DICOM_FALLBACK_PRESETS.brain;
            dicomState.preset = presetName;
            dicomState.ww = Number(preset.window_width || 80);
            dicomState.wc = Number(preset.window_center || 40);

            const wwSlider = document.getElementById("dicom-ww-slider");
            const wcSlider = document.getElementById("dicom-wc-slider");
            if (wwSlider) wwSlider.value = String(Math.round(dicomState.ww));
            if (wcSlider) wcSlider.value = String(Math.round(dicomState.wc));

            renderDicomSlice();
        }

        function setDicomPlane(plane) {
            dicomState.plane = plane;
            if (clinicalState.linkedNav && activeDicomVolume) {
                syncMainSliceFromNav(plane);
            }
            resetDicomMeasurement();
            if (dicomState.measuring) {
                setDicomReadout(dicomMeasurementInstruction(dicomState.measureTool, true));
            }
            renderDicomSlice();
        }

        function toggleDicomCine() {
            if (!activeDicomVolume) return;
            const cineButton = document.getElementById("dicom-toggle-cine");
            if (dicomCineTimer) {
                stopDicomCine();
                return;
            }

            if (cineButton) {
                cineButton.classList.add("active");
                cineButton.textContent = "Stop Cine";
            }

            dicomCineTimer = setInterval(() => {
                dicomState.slice = dicomState.slice >= dicomState.maxSlice ? 1 : dicomState.slice + 1;
                renderDicomSlice();
            }, 130);
        }

        function configureDicomSeriesOptions(studyPayload) {
            const select = document.getElementById("dicom-series-select");
            if (!select) return;

            const series = studyPayload?.profile?.series || [];
            select.innerHTML = "";

            if (series.length === 0) {
                const fallback = document.createElement("option");
                fallback.value = "";
                fallback.textContent = "No DICOM series loaded";
                select.appendChild(fallback);
                dicomState.seriesUid = "";
                return;
            }

            if (!series.some((entry) => entry.series_uid === dicomState.seriesUid)) {
                dicomState.seriesUid = series[0].series_uid;
            }

            series.forEach((entry) => {
                const option = document.createElement("option");
                option.value = entry.series_uid;
                option.textContent = `${entry.series_number}. ${entry.description}`;
                if (entry.series_uid === dicomState.seriesUid) {
                    option.selected = true;
                }
                select.appendChild(option);
            });
        }

        async function rebuildDicomVolume(dataOverride = null) {
            const sourceData = dataOverride || analysisData;
            if (!sourceData) {
                return { sourceLabel: "unavailable", resolutionProfile: "unavailable", dimensions: [0, 0, 0] };
            }
            const series = getActiveDicomSeries();
            if (!series) {
                return { sourceLabel: "unavailable", resolutionProfile: "unavailable", dimensions: [0, 0, 0] };
            }

            let sourceLabel = "native volume";
            let resolutionProfile = DICOM_VOLUME_RESOLUTION;
            try {
                const volumePayload = await fetchVolumePayload(sourceData.scan_id, DICOM_VOLUME_RESOLUTION);
                activeDicomVolume = buildDicomVolumeFromPayload(volumePayload, series);
                resolutionProfile = String(activeDicomVolume.resolutionProfile || volumePayload?.resolution_profile || DICOM_VOLUME_RESOLUTION);
                if (activeDicomVolume.syntheticFallback) {
                    sourceLabel = "backend synthetic fallback";
                }
            } catch (error) {
                console.warn("DICOM workstation falling back to synthetic local volume:", error);
                activeDicomVolume = buildSyntheticDicomVolume(sourceData, series);
                sourceLabel = "local synthetic fallback";
                resolutionProfile = "local-fallback";
            }

            dicomState.plane = String(series.plane || dicomState.plane || "axial").toLowerCase();
            dicomState.slice = Math.max(1, Math.floor((series.slice_count || activeDicomVolume.depth) / 2));
            setNavVoxelToVolumeCenter();
            syncNavFromActiveDicomSlice();
            initializeClinicalSegmentation(sourceData);

            if (activeDicomVolume.windowWidth && activeDicomVolume.windowCenter) {
                dicomState.ww = Number(activeDicomVolume.windowWidth);
                dicomState.wc = Number(activeDicomVolume.windowCenter);

                const wwSlider = document.getElementById("dicom-ww-slider");
                const wcSlider = document.getElementById("dicom-wc-slider");
                if (wwSlider) wwSlider.value = String(Math.round(dicomState.ww));
                if (wcSlider) wcSlider.value = String(Math.round(dicomState.wc));
            }

            resetDicomMeasurement();
            stopDicomCine();
            updateSegmentationControls();
            updateSegmentationVolumeOutput();
            updateCriticalStructureDistances();
            updateLinkedNavButton();
            renderDicomSlice();
            return {
                sourceLabel,
                resolutionProfile,
                dimensions: [activeDicomVolume.width, activeDicomVolume.height, activeDicomVolume.depth],
            };
        }

        function handleDicomCanvasClick(event) {
            if (!activeDicomVolume) return;
            const point = getDicomCanvasPoint(event);
            if (!point) return;
            
            const frame = getPlaneDimensions(activeDicomVolume, dicomState.plane);
            const sliceIndex = clampValue(dicomState.slice - 1, 0, frame.maxSlice - 1);
            
            if (clinicalState.segmentation.editMode && !dicomState.measuring) {
                const voxel = mapPlanePointToVoxel(dicomState.plane, sliceIndex, point, frame);
                editSegmentationAtVoxel(voxel);
                return;
            }
            
            if (!dicomState.measuring) {
                updateNavFromPlanePoint(dicomState.plane, sliceIndex, point, false);
                return;
            }

            const tool = dicomState.measureTool;
            const points = dicomState.measurePoints;

            if (tool === "distance") {
                if (points.length === 0 || points.length >= 2) {
                    dicomState.measurePoints = [point];
                    dicomState.measureStart = point;
                    dicomState.measureEnd = null;
                    dicomState.measurePreview = null;
                    setDicomReadout("Distance point A captured. Move cursor for preview, then click point B.");
                } else {
                    points.push(point);
                    dicomState.measureEnd = point;
                    dicomState.measurePreview = null;
                    setDicomReadout(formatDicomMeasurement(points[0], points[1], activeDicomVolume, dicomState.plane));
                }
                renderDicomSlice();
                return;
            }

            if (tool === "angle") {
                if (points.length >= 3) {
                    dicomState.measurePoints = [];
                }
                dicomState.measurePoints.push(point);
                dicomState.measurePreview = null;

                if (dicomState.measurePoints.length === 1) {
                    setDicomReadout("Angle point A captured. Click apex point B.");
                } else if (dicomState.measurePoints.length === 2) {
                    setDicomReadout("Angle apex point B captured. Move cursor to preview and click point C to lock angle.");
                } else {
                    setDicomReadout(formatDicomAngleMeasurement(dicomState.measurePoints, activeDicomVolume, dicomState.plane));
                }
                renderDicomSlice();
                return;
            }

            if (dicomState.measureAreaClosed) {
                dicomState.measurePoints = [point];
                dicomState.measureAreaClosed = false;
                dicomState.measurePreview = null;
                setDicomReadout("Area point 1 captured. Add more vertices and click near the first point to close.");
                renderDicomSlice();
                return;
            }

            if (points.length >= 3) {
                const first = points[0];
                const canvas = document.getElementById("dicom-canvas");
                const rect = canvas ? canvas.getBoundingClientRect() : null;
                const scaleX = rect ? (rect.width / Math.max(1, dicomState.frameWidth - 1)) : 1;
                const scaleY = rect ? (rect.height / Math.max(1, dicomState.frameHeight - 1)) : 1;
                const closeDistancePx = Math.hypot((point.x - first.x) * scaleX, (point.y - first.y) * scaleY);
                const closeThresholdPx = rect
                    ? Math.max(10, Math.min(24, Math.min(rect.width, rect.height) * 0.026))
                    : 12;

                if (closeDistancePx <= closeThresholdPx) {
                    dicomState.measureAreaClosed = true;
                    dicomState.measurePreview = null;
                    setDicomReadout(formatDicomAreaMeasurement(points, activeDicomVolume, dicomState.plane));
                    renderDicomSlice();
                    return;
                }
            }

            points.push(point);
            dicomState.measurePreview = null;
            dicomState.measureAreaClosed = false;
            if (points.length < 3) {
                setDicomReadout(`Area point ${points.length} captured. Add ${3 - points.length} more point(s) then close polygon.`);
            } else {
                setDicomReadout(formatDicomAreaMeasurement(points, activeDicomVolume, dicomState.plane, "Area Preview"));
            }
            renderDicomSlice();
        }

        function handleDicomCanvasMove(event) {
            if (!activeDicomVolume) return;

            if (clinicalState.segmentation.editMode && !dicomState.measuring && clinicalState.segmentation.pointerDown) {
                const point = getDicomCanvasPoint(event);
                if (!point) return;
                const frame = getPlaneDimensions(activeDicomVolume, dicomState.plane);
                const sliceIndex = clampValue(dicomState.slice - 1, 0, frame.maxSlice - 1);
                const voxel = mapPlanePointToVoxel(dicomState.plane, sliceIndex, point, frame);
                editSegmentationAtVoxel(voxel);
                return;
            }

            if (!dicomState.measuring) return;
            const tool = dicomState.measureTool;
            const points = dicomState.measurePoints;

            if (points.length === 0) return;
            if (tool === "distance" && points.length >= 2) return;
            if (tool === "angle" && points.length >= 3) return;
            if (tool === "area" && dicomState.measureAreaClosed) return;

            const point = getDicomCanvasPoint(event);
            if (!point) return;

            dicomState.measurePreview = point;

            if (tool === "distance") {
                setDicomReadout(formatDicomMeasurement(points[0], point, activeDicomVolume, dicomState.plane, "Preview"));
            } else if (tool === "angle") {
                const previewPoints = [...points, point];
                setDicomReadout(formatDicomAngleMeasurement(previewPoints, activeDicomVolume, dicomState.plane, "Preview"));
            } else {
                const previewPoints = [...points, point];
                setDicomReadout(formatDicomAreaMeasurement(previewPoints, activeDicomVolume, dicomState.plane, "Preview"));
            }

            renderDicomSlice();
        }

        function handleDicomCanvasLeave() {
            clinicalState.segmentation.pointerDown = false;
            if (!dicomState.measuring) return;
            if (dicomState.measurePreview) {
                dicomState.measurePreview = null;
                renderDicomSlice();
            }

            const points = dicomState.measurePoints;
            if (points.length > 0) {
                setDicomReadout(dicomMeasurementInstruction(dicomState.measureTool, true));
            }
        }

        async function loadDicomWorkstation(data) {
            if (!data?.scan_id) {
                setDicomMetaText("No scan loaded for DICOM workstation.");
                updateClinicalWorkflow();
                return;
            }

            activeDicomStudy = null;
            activeDicomVolume = null;
            setDicomMetaText("Loading DICOM study profile...");
            updateClinicalWorkflow();

            try {
                const response = await fetch(`${API_BASE}/demo/dicom/${encodeURIComponent(data.scan_id)}`);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const payload = await response.json();
                activeDicomStudy = payload;

                configureDicomSeriesOptions(payload);
                const defaultWl = payload?.profile?.window_level || DICOM_FALLBACK_PRESETS.brain;
                dicomState.ww = Number(defaultWl.window_width || 80);
                dicomState.wc = Number(defaultWl.window_center || 40);
                dicomState.preset = "brain";
                dicomState.invert = false;
                dicomState.crosshair = true;
                dicomState.measuring = false;
                dicomState.measureTool = "distance";
                resetDicomMeasurement();

                const wwSlider = document.getElementById("dicom-ww-slider");
                const wcSlider = document.getElementById("dicom-wc-slider");
                const invertButton = document.getElementById("dicom-toggle-invert");
                const crosshairButton = document.getElementById("dicom-toggle-crosshair");
                const measureButton = document.getElementById("dicom-toggle-measure");

                if (wwSlider) wwSlider.value = String(Math.round(dicomState.ww));
                if (wcSlider) wcSlider.value = String(Math.round(dicomState.wc));
                if (invertButton) {
                    invertButton.classList.remove("active");
                    invertButton.textContent = "Invert Off";
                }
                if (crosshairButton) {
                    crosshairButton.classList.add("active");
                    crosshairButton.textContent = "Crosshair On";
                }
                if (measureButton) {
                    measureButton.classList.remove("active");
                    measureButton.textContent = "Measure Off";
                }
                updateDicomMeasureToolButtons();

                stopDicomCine();
                const volumeSource = await rebuildDicomVolume(data);

                const profile = payload.profile || {};
                const seriesCount = Array.isArray(profile.series) ? profile.series.length : 0;
                setDicomMetaText(
                    `${payload.patient_code || "Demo"} | ${profile.modality || "MRI"} | ${seriesCount} series | UID ${profile.study_uid || "n/a"}`
                );
                const sourceMessage = volumeSource.sourceLabel === "native volume"
                    ? "Native patient volume loaded."
                    : (volumeSource.sourceLabel === "backend synthetic fallback"
                        ? "Backend synthetic volume fallback loaded."
                        : "Local synthetic volume fallback loaded.");
                const [dx, dy, dz] = volumeSource.dimensions || [0, 0, 0];
                setDicomReadout(
                    `${sourceMessage} Resolution profile: ${volumeSource.resolutionProfile}. ` +
                    `Volume: ${dx}x${dy}x${dz}. ${dicomMeasurementInstruction(dicomState.measureTool, false)}`
                );
                updateClinicalWorkflow();
            } catch (error) {
                activeDicomStudy = null;
                activeDicomVolume = null;
                clinicalState.segmentation.scanId = "";
                clinicalState.segmentation.lesionMask = null;
                clinicalState.segmentation.edemaMask = null;
                clinicalState.segmentation.uncertaintyMask = null;
                setDicomMetaText(`DICOM profile unavailable: ${error.message}`);
                setDicomReadout("Unable to initialize DICOM tools for this scan.");
                const volumeOutput = document.getElementById("segmentation-volume-output");
                if (volumeOutput) {
                    volumeOutput.textContent = "Segmentation volumes will appear after loading a case.";
                }
                const proximityOutput = document.getElementById("critical-distance-list");
                if (proximityOutput) {
                    proximityOutput.textContent = "Load a case to compute lesion proximity to eloquent structures and vessels.";
                }
                updateSegmentationControls();
                updateLinkedNavButton();
                renderDicomSlice();
                updateClinicalWorkflow();
            }
        }

        function updateActivePatientBadge(patient, isLoaded) {
            const badge = document.getElementById("active-patient-badge");
            if (!badge) return;

            if (!patient) {
                badge.textContent = "No sample selected";
                return;
            }

            badge.textContent = isLoaded
                ? `${patient.patient_code} active`
                : `${patient.patient_code} selected`;
        }

        function renderPatientList() {
            const list = document.getElementById("patient-list");
            if (!list) return;

            const query = (document.getElementById("patient-search")?.value || "").trim().toLowerCase();
            const riskFilter = document.getElementById("patient-risk-filter")?.value || "all";

            const filtered = demoPatients.filter((patient) => {
                const searchable = `${patient.display_name} ${patient.patient_code} ${patient.primary_concern || ""}`.toLowerCase();
                const matchesQuery = searchable.includes(query);
                const matchesRisk = riskFilter === "all" || getRiskClass(patient.risk_band) === riskFilter;
                return matchesQuery && matchesRisk;
            });

            list.innerHTML = "";
            if (filtered.length === 0) {
                list.innerHTML = "<div class='region-item muted'>No patients match current filters.</div>";
                return;
            }

            filtered.forEach((patient) => {
                const item = document.createElement("button");
                const riskClass = getRiskClass(patient.risk_band);
                const isActive = patient.patient_id === selectedPatientId;
                item.type = "button";
                item.className = `patient-item${isActive ? " active" : ""}`;
                item.innerHTML = `
                    <div class="patient-item-top">
                        <span>${patient.patient_code}</span>
                        <span class="risk-chip ${riskClass}">${RISK_LABELS[riskClass]}</span>
                    </div>
                    <div class="patient-item-name">${patient.display_name}</div>
                    <div class="patient-item-meta">
                        <span>${patient.age}y ${patient.sex}</span>
                        <span>${patient.modality || "N/A"}</span>
                    </div>
                    <div class="patient-item-note">${patient.primary_concern || "No concern listed."}</div>
                    <div class="patient-item-meta">
                        <span>${Math.round((patient.overall_confidence || 0) * 100)}% conf</span>
                        <span>Triage ${patient.triage_score || 0}</span>
                    </div>
                `;
                item.addEventListener("click", () => {
                    setSelectedPatient(patient.patient_id);
                });
                list.appendChild(item);
            });
        }

        function updateCaseSnapshot(data, patientOverride = null) {
            const patient = patientOverride || findPatientById(data?.patient_id) || getSelectedPatient();
            const regions = normalizeRegions(data);

            const nameEl = document.getElementById("snapshot-name");
            const scanEl = document.getElementById("snapshot-scan");
            const modalityEl = document.getElementById("snapshot-modality");
            const riskEl = document.getElementById("snapshot-risk");
            const summaryEl = document.getElementById("snapshot-summary");
            const statsEl = document.getElementById("snapshot-stats");

            if (!nameEl || !scanEl || !modalityEl || !riskEl || !summaryEl || !statsEl) return;

            if (!patient && !data) {
                nameEl.textContent = "No patient selected";
                scanEl.textContent = "-";
                modalityEl.textContent = "-";
                riskEl.textContent = "-";
                riskEl.className = "snapshot-risk low";
                summaryEl.textContent = "Choose one of the sample patients to preview findings and trend context before loading the full viewer.";
                statsEl.innerHTML = "<span class='snapshot-pill'>No active findings</span>";
                renderTimeline(null, "");
                updateClinicalKpis(null, patient);
                renderGovernancePanel(null);
                return;
            }

            const riskClass = getRiskClass(data?.risk_band || patient?.risk_band);
            const patientName = patient ? `${patient.patient_code} | ${patient.display_name}` : (data?.patient_code || data?.patient_name || "Sample patient");

            nameEl.textContent = patientName;
            scanEl.textContent = data?.scan_id || patient?.latest_scan_id || "-";
            modalityEl.textContent = (data?.modalities && data.modalities[0]) || patient?.modality || "-";
            riskEl.textContent = RISK_LABELS[riskClass] || "low";
            riskEl.className = `snapshot-risk ${riskClass}`;
            summaryEl.textContent = data?.executive_summary || patient?.primary_concern || "Sample patient selected. Load demo to see full findings.";

            const severe = regions.filter((region) => (region.severity_level || 0) === 4).length;
            const moderate = regions.filter((region) => (region.severity_level || 0) === 3).length;
            const mild = regions.filter((region) => (region.severity_level || 0) === 2).length;
            const involved = severe + moderate + mild;
            const confidence = data?.overall_confidence ? Math.round(data.overall_confidence * 100) : null;

            const statPills = [];
            if (involved > 0) {
                const className = severe > 0 ? "critical" : (moderate > 0 ? "warning" : "");
                statPills.push(`<span class='snapshot-pill ${className}'>${involved} regions flagged</span>`);
            } else {
                statPills.push("<span class='snapshot-pill'>No elevated regions</span>");
            }

            if (severe > 0) statPills.push(`<span class='snapshot-pill critical'>${severe} severe</span>`);
            if (moderate > 0) statPills.push(`<span class='snapshot-pill warning'>${moderate} moderate</span>`);
            if (mild > 0) statPills.push(`<span class='snapshot-pill'>${mild} mild</span>`);
            if (confidence !== null) statPills.push(`<span class='snapshot-pill'>${confidence}% confidence</span>`);

            statsEl.innerHTML = statPills.join("");
            renderTimeline(patient, data?.scan_id || "");
            updateClinicalKpis(data, patient);
            renderGovernancePanel(data || null);
        }

        function setSelectedPatient(patientId) {
            if (!patientId) return;
            selectedPatientId = patientId;
            renderPatientList();
            renderComparePatientOptions();
            renderComparisonPlaceholder("Select the comparison patient then click Compare Cases.");

            const selectedPatient = getSelectedPatient();
            const hasLoadedSelectedCase = Boolean(analysisData && analysisData.patient_id === selectedPatientId);
            updateActivePatientBadge(selectedPatient, hasLoadedSelectedCase);
            updateCaseSnapshot(hasLoadedSelectedCase ? analysisData : null, selectedPatient);
            updateClinicalKpis(hasLoadedSelectedCase ? analysisData : null, selectedPatient);
            updateClinicalWorkflow();
        }

        async function fetchDemoPatients() {
            const list = document.getElementById("patient-list");
            if (list) {
                list.innerHTML = "<div class='region-item muted'>Loading sample patients...</div>";
            }

            try {
                const response = await fetch(`${API_BASE}/demo/patients`);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const payload = await response.json();
                demoPatients = Array.isArray(payload.patients) ? payload.patients : [];
                demoPatients.sort((left, right) => (right.triage_score || 0) - (left.triage_score || 0));

                if (!selectedPatientId && demoPatients.length > 0) {
                    selectedPatientId = demoPatients[0].patient_id;
                }

                renderPatientList();
                renderComparePatientOptions();
                renderComparisonPlaceholder("Select the comparison patient then click Compare Cases.");
                updateCaseSnapshot(null, getSelectedPatient());
                updateActivePatientBadge(getSelectedPatient(), false);
                updateClinicalKpis(null, getSelectedPatient());
                updateClinicalWorkflow();
            } catch (error) {
                if (list) {
                    list.innerHTML = "<div class='region-item muted'>Sample patients unavailable.</div>";
                }
                updateStatus("Sample patient list unavailable. You can still upload scans manually.");
                updateClinicalKpis();
                renderGovernancePanel(null);
                updateClinicalWorkflow();
            }
        }

        function pickRandomPatientId() {
            if (demoPatients.length === 0) return "";
            if (demoPatients.length === 1) return demoPatients[0].patient_id;

            const otherPatients = demoPatients.filter((patient) => patient.patient_id !== selectedPatientId);
            const source = otherPatients.length > 0 ? otherPatients : demoPatients;
            const randomIndex = Math.floor(Math.random() * source.length);
            return source[randomIndex].patient_id;
        }

        function populateRegionList(regions) {
            const list = document.getElementById("region-list");
            if (!list) return;
            list.innerHTML = "";

            if (!regions || regions.length === 0) {
                list.innerHTML = "<div class='region-item muted'>No regions available for this scan.</div>";
                return;
            }

            regions.forEach((region) => {
                const item = document.createElement("div");
                item.className = "region-item";
                const color = SEVERITY_HEX[region.severity_level] || "#5e7394";
                const label = SEVERITY_LABELS[region.severity_level] || "Unknown";
                const confidence = Math.round((region.confidence || 0) * 100);
                item.innerHTML = `
                    <div style="display:flex; justify-content:space-between; gap:0.5rem; align-items:center;">
                        <strong style="color:${color}; font-weight:650;">${region.anatomical_name || region.atlas_id}</strong>
                        <span style="color:#637a99; font-size:0.75rem;">${confidence}%</span>
                    </div>
                    <div style="margin-top:0.1rem; color:#5c7292; font-size:0.77rem;">${label}</div>
                `;
                list.appendChild(item);
            });
        }

        function showDiagnosis(data) {
            const el = document.getElementById("differential-diagnosis");
            if (!el) return;

            if (!data) {
                el.innerHTML = "<div class='diag-muted'>Run a scan to view ranked diagnostic hypotheses.</div>";
                return;
            }

            const damageSummary = data.damage_summary || normalizeRegions(data);
            const relevant = damageSummary.filter((r) => (r.severity_level || 0) >= 2);
            if (relevant.length === 0) {
                el.innerHTML = "<div class='diag-item' style='border-left-color:#27AE60;'><strong>No significant findings</strong><br>Observed regions are within low-risk thresholds.</div>";
                return;
            }

            el.innerHTML = relevant.map((r) => {
                const color = SEVERITY_HEX[r.severity_level] || "#d1dfef";
                const label = SEVERITY_LABELS[r.severity_level] || "Unknown";
                const confidence = Math.round((r.confidence || 0) * 100);
                return `
                    <div class="diag-item" style="border-left-color:${color};">
                        <strong>${r.anatomical_name || r.atlas_id}</strong><br>
                        ${label} pattern with ${confidence}% confidence.
                    </div>
                `;
            }).join("");
        }

        async function login() {
            const role = document.getElementById("auth-role").value;
            try {
                const resp = await fetch(`${API_BASE}/auth/token`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ user_id: `demo-${role}`, role }),
                });
                const data = await resp.json();
                authToken = data.access_token;
                localStorage.setItem("brainscape_token", authToken);
                setAuthState(`Signed in as ${role}`, "ok");
                updateStatus(`Authenticated as ${role}. Upload a scan or load demo data.`);
            } catch (error) {
                setAuthState("Authentication failed", "error");
                updateStatus("Could not authenticate. Please retry.");
            }
        }

        function authHeaders() {
            return { Authorization: `Bearer ${authToken}` };
        }

        function resolveReportMode() {
            const role = (document.getElementById("auth-role")?.value || "patient").toLowerCase();
            return role === "clinician" ? "clinician" : "patient";
        }

        function openReportViewForCurrentScan() {
            if (!currentScanId) {
                updateStatus("Load a scan first to open a report view.");
                return;
            }

            const mode = resolveReportMode();
            window.open(`/report-view/${encodeURIComponent(currentScanId)}?mode=${mode}`, "_blank");
            updateClinicalWorkflow();
        }

        async function loadDemo(patientId = selectedPatientId, scanId = "") {
            if (!authToken) {
                updateStatus("Please sign in first.");
                return;
            }

            const resolvedPatientId = patientId || selectedPatientId || "";
            const queryParams = new URLSearchParams();
            if (scanId) {
                queryParams.set("scan_id", scanId);
            } else if (resolvedPatientId) {
                queryParams.set("patient_id", resolvedPatientId);
            }
            const patientQuery = queryParams.toString() ? `?${queryParams.toString()}` : "";

            updateStatus("Loading selected demo scan...");
            updateJobInfo(scanId || resolvedPatientId || "demo");

            try {
                const ingestResp = await fetch(`${API_BASE}/demo/ingest${patientQuery}`, {
                    method: "POST",
                    headers: authHeaders(),
                });
                if (!ingestResp.ok) {
                    throw new Error(`Demo ingest failed (${ingestResp.status})`);
                }

                const resp = await fetch(`${API_BASE}/demo/analysis${patientQuery}`, { headers: authHeaders() });
                if (!resp.ok) {
                    throw new Error(`Demo analysis failed (${resp.status})`);
                }

                analysisData = await resp.json();
                currentScanId = analysisData.scan_id;
                if (analysisData.patient_id) {
                    selectedPatientId = analysisData.patient_id;
                }
                renderPatientList();
                await loadBrainFromAnalysis(analysisData);
            } catch (error) {
                updateStatus(`Error loading demo: ${error.message}`);
                updateJobInfo("No active job");
            }
        }

        async function loadBrainFromAnalysis(data) {
            if (brainGroup) scene.remove(brainGroup);
            disposeVolumeRenderAssets();
            clearViewerFocus();
            clearTrajectoryPlan();

            let reconstructionMode = "procedural";
            let reconstructionQuality = "";
            let reconstructionFallbackReason = "";
            try {
                const reconstruction = await buildReconstructedBrain(data, SURFACE_MESH_QUALITY);
                brainGroup = reconstruction.group;
                reconstructionMode = "mri-fmri";
                reconstructionQuality = reconstruction.payload?.mesh_quality === "extreme"
                    ? "extreme-fidelity"
                    : reconstruction.payload?.mesh_quality === "high"
                        ? "high-fidelity"
                        : "standard";
            } catch (extremeError) {
                console.warn("Extreme-quality mesh load failed; retrying high-quality mesh:", extremeError);
                try {
                    const reconstruction = await buildReconstructedBrain(data, "high");
                    brainGroup = reconstruction.group;
                    reconstructionMode = "mri-fmri";
                    reconstructionQuality = "high-fidelity";
                    reconstructionFallbackReason = "Extreme-detail mesh was unavailable, using high-detail patient mesh.";
                } catch (highError) {
                    console.warn("High-quality mesh load failed; retrying standard mesh:", highError);
                    try {
                        const reconstruction = await buildReconstructedBrain(data, "standard");
                        brainGroup = reconstruction.group;
                        reconstructionMode = "mri-fmri";
                        reconstructionQuality = "standard";
                        reconstructionFallbackReason = "High-detail mesh was unavailable, using standard patient mesh.";
                    } catch (standardError) {
                        console.warn("Patient mesh load failed; falling back to procedural preview:", standardError);
                        reconstructionFallbackReason = "Patient mesh generation failed, displaying procedural preview.";
                        brainGroup = buildDemoBrain(data);
                    }
                }
            }

            scene.add(brainGroup);
            const volumeLoaded = await loadVolumeFromAnalysis(data);

            const overlay = document.getElementById("upload-overlay");
            if (overlay) overlay.style.display = "none";

            const clipSlider = document.getElementById("clip-slider");
            applyClipDepthFromSlider(clipSlider ? clipSlider.value : 0);
            setRenderMode(volumeLoaded ? activeRenderMode : "surface");
            updateViewerPickInfo("Click any cortical area in the 3D view to inspect the nearest affected region.");

            const regions = data.damage_summary || normalizeRegions(data);
            populateRegionList(regions);
            showDiagnosis(data);
            applyDamageColors(brainGroup, data, visibleLevels);
            updateCaseSnapshot(data);
            populateCompareScanOptions();
            updateComparisonSummaries();

            const activePatient = findPatientById(data.patient_id) || getSelectedPatient();
            updateActivePatientBadge(activePatient, true);
            updateClinicalKpis(data, activePatient);
            updateClinicalWorkflow();

            const volumeStatus = volumeLoaded
                ? (volumeUsesSyntheticFallback
                    ? "Volumetric view active (synthetic fallback due to non-volumetric upload source)."
                    : "Volumetric view active with tri-planar (axial/coronal/sagittal) combined reconstruction and optional damage overlay.")
                : "Volumetric shader unavailable, using surface-only mode.";

            if (reconstructionMode === "mri-fmri") {
                const detail = reconstructionQuality ? `${reconstructionQuality} mesh quality` : "mesh quality";
                const fallbackSuffix = reconstructionFallbackReason ? ` ${reconstructionFallbackReason}` : "";
                updateStatus(`Loaded scan ${data.scan_id} with MRI/fMRI-derived cortical reconstruction (${detail}). ${volumeStatus}${fallbackSuffix}`);
            } else {
                const fallbackSuffix = reconstructionFallbackReason ? ` ${reconstructionFallbackReason}` : "";
                updateStatus(`Loaded scan ${data.scan_id} with fallback preview mesh. ${volumeStatus}${fallbackSuffix}`);
            }
            updateJobInfo(data.scan_id || "completed");
            loadDicomWorkstation(data);
        }

        async function uploadScan(file) {
            if (!authToken) {
                updateStatus("Please sign in first.");
                return;
            }

            updateStatus("Uploading scan...");
            updateJobInfo("uploading");

            const formData = new FormData();
            formData.append("file", file);

            try {
                const resp = await fetch(`${API_BASE}/ingest`, {
                    method: "POST",
                    body: formData,
                    headers: authHeaders(),
                });
                const data = await resp.json();
                if (!resp.ok) {
                    throw new Error(data.detail || `Upload failed (${resp.status})`);
                }
                if (!data?.job_id) {
                    throw new Error("Upload response did not include a job id");
                }
                updateStatus(`Scan uploaded. Job ${data.job_id} is processing.`);
                updateJobInfo(data.job_id);
                pollJobStatus(data.job_id);
            } catch (error) {
                updateStatus(`Upload failed: ${error.message}`);
                updateJobInfo("No active job");
            }
        }

        async function pollJobStatus(jobId) {
            const poll = async () => {
                try {
                    const resp = await fetch(`${API_BASE}/status/${jobId}`, { headers: authHeaders() });
                    const data = await resp.json();
                    updateStatus(`Processing stage: ${data.stage || "pending"} (${data.progress_pct || 0}%)`);
                    updateJobInfo(`${jobId} - ${data.status || "unknown"}`);

                    if (data.status === "complete") {
                        updateStatus("Analysis complete. Loading 3D viewer...");
                        try {
                            const resolvedScanId = data.scan_id || jobId;
                            const aResp = await fetch(`${API_BASE}/analysis/${encodeURIComponent(resolvedScanId)}`, { headers: authHeaders() });
                            if (!aResp.ok) {
                                throw new Error(`Analysis fetch failed (${aResp.status})`);
                            }
                            analysisData = await aResp.json();
                            currentScanId = analysisData.scan_id;
                            await loadBrainFromAnalysis(analysisData);
                        } catch (error) {
                            updateStatus(`Analysis complete, but viewer data could not be loaded: ${error.message}`);
                        }
                        return;
                    }

                    if (data.status === "failed") {
                        updateStatus(`Processing failed: ${data.error_message || "unknown error"}`);
                        updateJobInfo(`${jobId} - failed`);
                        return;
                    }

                    setTimeout(poll, 3000);
                } catch (error) {
                    updateStatus("Status check interrupted. Retrying...");
                    setTimeout(poll, 5000);
                }
            };

            poll();
        }

        async function askQuestion(question) {
            if (!currentScanId) return;

            const el = document.getElementById("qa-response");
            el.style.display = "block";
            el.innerHTML = "<span class='loading-spinner'></span>Analyzing clinical context...";

            try {
                const resp = await fetch(`${API_BASE}/query`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", ...authHeaders() },
                    body: JSON.stringify({ scan_id: currentScanId, question }),
                });
                const data = await resp.json();
                el.textContent = data.answer || data.response || JSON.stringify(data);
            } catch (error) {
                el.textContent = `Error: ${error.message}`;
            }
        }

        function bootstrapBrainScapeApp() {
            if (window.__BRAINGSCAPE_BOOTSTRAPPED__) {
                return;
            }
            window.__BRAINGSCAPE_BOOTSTRAPPED__ = true;

            try {
                initScene();
            } catch (error) {
                console.error("Viewer initialization failed:", error);
                updateStatus("3D viewer could not initialize in this browser. Core patient, report, and API features are still available.");
            }
            fetchDemoPatients();
            setViewerCameraPreset("reset");
            updateAutoRotateButton();
            updateRenderModeButtons();
            setRenderMode("hybrid");
            renderDicomSlice();
            applyPanelMode(activePanelMode);
            updateClinicalKpis();
            renderGovernancePanel(null);
            updateClinicalWorkflow();
            updateSegmentationControls();
            updateLinkedNavButton();
            updateTrajectoryButtons();
            updateComparisonSummaries();

            if (authToken) {
                setAuthState("Session restored", "ok");
            }

            document.querySelectorAll(".panel-mode-btn").forEach((button) => {
                button.addEventListener("click", () => {
                    applyPanelMode(button.dataset.panelMode || "all");
                });
            });

            document.getElementById("btn-view-reset").addEventListener("click", () => setViewerCameraPreset("reset"));
            document.getElementById("btn-view-left").addEventListener("click", () => setViewerCameraPreset("left"));
            document.getElementById("btn-view-right").addEventListener("click", () => setViewerCameraPreset("right"));
            document.getElementById("btn-view-top").addEventListener("click", () => setViewerCameraPreset("top"));
            document.getElementById("btn-view-front").addEventListener("click", () => setViewerCameraPreset("front"));
            document.getElementById("btn-auto-rotate").addEventListener("click", toggleAutoRotate);
            document.getElementById("btn-render-hybrid").addEventListener("click", () => setRenderMode("hybrid"));
            document.getElementById("btn-render-volume").addEventListener("click", () => setRenderMode("volume"));
            document.getElementById("btn-render-surface").addEventListener("click", () => setRenderMode("surface"));
            document.getElementById("clip-slider").addEventListener("input", (event) => {
                applyClipDepthFromSlider(event.target.value);
            });

            document.getElementById("btn-login").addEventListener("click", login);
            document.getElementById("btn-demo").addEventListener("click", () => loadDemo(selectedPatientId));
            document.getElementById("btn-load-patient").addEventListener("click", () => loadDemo(selectedPatientId));
            document.getElementById("btn-random-patient").addEventListener("click", () => {
                const randomPatientId = pickRandomPatientId();
                if (!randomPatientId) {
                    updateStatus("No sample patient available yet.");
                    return;
                }
                setSelectedPatient(randomPatientId);
                loadDemo(randomPatientId);
            });

            document.getElementById("compare-patient-select").addEventListener("change", (event) => {
                compareTargetPatientId = event.target.value;
                populateCompareScanOptions();
                updateComparisonSummaries();
            });
            document.getElementById("compare-left-scan").addEventListener("change", updateComparisonSummaries);
            document.getElementById("compare-right-scan").addEventListener("change", updateComparisonSummaries);
            document.getElementById("btn-compare-cases").addEventListener("click", compareSelectedCases);
            document.getElementById("btn-load-high-risk").addEventListener("click", loadHighestRiskPatient);
            document.getElementById("btn-signoff-approve").addEventListener("click", () => submitSignoffDecision("approve"));
            document.getElementById("btn-signoff-second-read").addEventListener("click", () => submitSignoffDecision("requires_second_read"));
            document.getElementById("btn-signoff-escalate").addEventListener("click", () => submitSignoffDecision("escalate"));

            document.getElementById("patient-search").addEventListener("input", renderPatientList);
            document.getElementById("patient-risk-filter").addEventListener("change", renderPatientList);

            document.getElementById("dicom-series-select").addEventListener("change", async (event) => {
                dicomState.seriesUid = event.target.value;
                await rebuildDicomVolume(analysisData);
                updateClinicalWorkflow();
            });
            document.querySelectorAll(".dicom-plane-btn").forEach((button) => {
                button.addEventListener("click", () => setDicomPlane(button.dataset.plane));
            });
            document.getElementById("dicom-slice-slider").addEventListener("input", (event) => {
                dicomState.slice = Number(event.target.value || 1);
                if (clinicalState.linkedNav) {
                    syncNavFromActiveDicomSlice();
                }
                renderDicomSlice();
            });
            document.getElementById("dicom-ww-slider").addEventListener("input", (event) => {
                dicomState.ww = Number(event.target.value || 80);
                dicomState.preset = "";
                renderDicomSlice();
            });
            document.getElementById("dicom-wc-slider").addEventListener("input", (event) => {
                dicomState.wc = Number(event.target.value || 40);
                dicomState.preset = "";
                renderDicomSlice();
            });
            document.querySelectorAll(".dicom-preset-btn").forEach((button) => {
                button.addEventListener("click", () => applyDicomPreset(button.dataset.preset));
            });
            document.getElementById("dicom-toggle-cine").addEventListener("click", toggleDicomCine);
            document.getElementById("dicom-toggle-invert").addEventListener("click", () => {
                dicomState.invert = !dicomState.invert;
                const button = document.getElementById("dicom-toggle-invert");
                button.classList.toggle("active", dicomState.invert);
                button.textContent = dicomState.invert ? "Invert On" : "Invert Off";
                renderDicomSlice();
            });
            document.getElementById("dicom-toggle-crosshair").addEventListener("click", () => {
                dicomState.crosshair = !dicomState.crosshair;
                const button = document.getElementById("dicom-toggle-crosshair");
                button.classList.toggle("active", dicomState.crosshair);
                button.textContent = dicomState.crosshair ? "Crosshair On" : "Crosshair Off";
                renderDicomSlice();
            });
            document.getElementById("dicom-toggle-measure").addEventListener("click", () => {
                dicomState.measuring = !dicomState.measuring;
                if (dicomState.measuring && clinicalState.segmentation.editMode) {
                    clinicalState.segmentation.editMode = false;
                    updateSegmentationControls();
                }
                const button = document.getElementById("dicom-toggle-measure");
                button.classList.toggle("active", dicomState.measuring);
                button.textContent = dicomState.measuring ? "Measure On" : "Measure Off";
                resetDicomMeasurement();
                setDicomReadout(dicomMeasurementInstruction(dicomState.measureTool, dicomState.measuring));
                renderDicomSlice();
            });
            document.getElementById("dicom-clear-measure").addEventListener("click", () => {
                resetDicomMeasurement();
                setDicomReadout(`Measurement cleared. ${dicomMeasurementInstruction(dicomState.measureTool, dicomState.measuring)}`);
                renderDicomSlice();
            });

            document.querySelectorAll(".dicom-measure-tool").forEach((button) => {
                button.addEventListener("click", () => {
                    setDicomMeasureTool(button.dataset.tool);
                });
            });

            document.getElementById("dicom-apply-context").addEventListener("click", applyDicomContextPreset);
            document.getElementById("dicom-toggle-linked-nav").addEventListener("click", () => {
                clinicalState.linkedNav = !clinicalState.linkedNav;
                if (clinicalState.linkedNav) {
                    syncMainSliceFromNav(dicomState.plane);
                }
                updateLinkedNavButton();
                renderDicomSlice();
            });
            document.getElementById("dicom-sync-to-3d").addEventListener("click", () => {
                focus3DOnCurrentCrosshair();
                updateStatus("3D view centered on DICOM crosshair target.");
            });

            document.getElementById("seg-toggle-lesion").addEventListener("click", () => toggleSegmentationVisibility("lesion"));
            document.getElementById("seg-toggle-edema").addEventListener("click", () => toggleSegmentationVisibility("edema"));
            document.getElementById("seg-toggle-uncertainty").addEventListener("click", () => toggleSegmentationVisibility("uncertainty"));
            document.getElementById("seg-toggle-edit").addEventListener("click", toggleSegmentationEditMode);
            document.getElementById("seg-tool-brush").addEventListener("click", () => setSegmentationTool("brush"));
            document.getElementById("seg-tool-erase").addEventListener("click", () => setSegmentationTool("erase"));
            document.getElementById("seg-class-select").addEventListener("change", (event) => {
                clinicalState.segmentation.editClass = event.target.value === "edema" ? "edema" : "lesion";
            });
            document.getElementById("seg-brush-size").addEventListener("input", (event) => {
                clinicalState.segmentation.brushRadius = Number(event.target.value || 2);
                updateSegmentationControls();
            });
            document.getElementById("btn-estimate-volume").addEventListener("click", runVolumeEstimation);
            document.getElementById("btn-refresh-longitudinal").addEventListener("click", refreshLongitudinalOutputs);

            document.querySelectorAll("#critical-structure-toggles input").forEach((input) => {
                input.addEventListener("change", () => {
                    updateCriticalStructureDistances();
                    if (clinicalState.trajectory.entry && clinicalState.trajectory.target) {
                        computeTrajectoryPlan();
                    }
                });
            });

            document.getElementById("btn-plan-entry").addEventListener("click", () => setTrajectoryCaptureMode("entry"));
            document.getElementById("btn-plan-target").addEventListener("click", () => setTrajectoryCaptureMode("target"));
            document.getElementById("btn-plan-compute").addEventListener("click", computeTrajectoryPlan);
            document.getElementById("btn-plan-clear").addEventListener("click", clearTrajectoryPlan);

            document.querySelectorAll(".tri-canvas").forEach((canvas) => {
                canvas.addEventListener("click", handleTriCanvasClick);
            });

            const dicomCanvas = document.getElementById("dicom-canvas");
            dicomCanvas.addEventListener("click", handleDicomCanvasClick);
            dicomCanvas.addEventListener("mousemove", handleDicomCanvasMove);
            dicomCanvas.addEventListener("mouseleave", handleDicomCanvasLeave);
            dicomCanvas.addEventListener("mousedown", () => {
                clinicalState.segmentation.pointerDown = true;
            });
            document.addEventListener("mouseup", () => {
                clinicalState.segmentation.pointerDown = false;
            });

            const fileInput = document.getElementById("file-input");
            document.getElementById("btn-upload").addEventListener("click", () => fileInput.click());
            document.getElementById("btn-download-sample").addEventListener("click", () => {
                const selectedPatient = getSelectedPatient();
                const preferred = (selectedPatient?.modality || "MRI_T1").toLowerCase().includes("fmri") ? "fmri" : "mri";
                window.open(`${API_BASE}/demo/upload-sample?modality=${preferred}`, "_blank");
            });
            fileInput.addEventListener("change", (event) => {
                if (event.target.files.length > 0) uploadScan(event.target.files[0]);
                event.target.value = "";
            });

            const dropZone = document.getElementById("drop-zone");
            dropZone.addEventListener("dragover", (event) => event.preventDefault());
            dropZone.addEventListener("drop", (event) => {
                event.preventDefault();
                if (event.dataTransfer.files.length > 0) uploadScan(event.dataTransfer.files[0]);
            });

            document.querySelectorAll(".severity-toggle input").forEach((checkbox) => {
                checkbox.addEventListener("change", () => {
                    visibleLevels = new Set();
                    document.querySelectorAll(".severity-toggle input:checked").forEach((el) => {
                        visibleLevels.add(parseInt(el.dataset.level, 10));
                    });
                    if (brainGroup && analysisData) {
                        applyDamageColors(brainGroup, analysisData, visibleLevels);
                    }
                    updateVolumeDamageVisibility();
                });
            });

            document.getElementById("qa-input").addEventListener("keypress", (event) => {
                if (event.key === "Enter") {
                    const question = event.target.value.trim();
                    if (question) askQuestion(question);
                }
            });

            document.getElementById("btn-export-report").addEventListener("click", () => {
                openReportViewForCurrentScan();
            });

            document.getElementById("btn-export-glb").addEventListener("click", async () => {
                if (!currentScanId) {
                    updateStatus("Load a scan before exporting mesh artifacts.");
                    return;
                }

                try {
                    const payload = await fetchMeshForScan(currentScanId, false, SURFACE_MESH_QUALITY);
                    window.open(payload.mesh_url, "_blank");
                    updateStatus(`Opened exported ${payload.mesh_format || "mesh"} artifact.`);
                } catch (error) {
                    updateStatus(`Mesh export unavailable: ${error.message}`);
                }
            });

            document.getElementById("nav-viewer").addEventListener("click", () => {
                document.getElementById("nav-viewer").classList.add("active");
                document.getElementById("nav-report").classList.remove("active");
            });

            document.getElementById("nav-report").addEventListener("click", () => {
                document.getElementById("nav-report").classList.add("active");
                document.getElementById("nav-viewer").classList.remove("active");
                openReportViewForCurrentScan();
            });
        }

        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", bootstrapBrainScapeApp, { once: true });
        } else {
            bootstrapBrainScapeApp();
        }
