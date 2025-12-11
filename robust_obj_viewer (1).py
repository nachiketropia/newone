import webbrowser
import os
import tempfile
import base64
from pathlib import Path
import traceback

def view_obj_with_mtl(obj_file_path, auto_open=True, max_texture_size_mb=10):
    """
    Opens a 3D OBJ file with MTL materials and textures in a web browser.
    Displays mesh structure with full error handling and validation.
    
    Args:
        obj_file_path (str): Path to the .obj file to view
        auto_open (bool): Whether to automatically open the browser (default: True)
        max_texture_size_mb (int): Maximum texture file size in MB to embed (default: 10)
    
    Returns:
        str: Path to the generated HTML file
    """
    
    html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D Mesh Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            overflow: hidden;
            height: 100vh;
        }
        #container { width: 100%; height: 100vh; position: relative; }
        #canvas { width: 100%; height: 100%; display: block; cursor: grab; }
        #canvas:active { cursor: grabbing; }
        .controls {
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.98);
            padding: 20px; border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            max-width: 340px; backdrop-filter: blur(10px);
            z-index: 100; max-height: 90vh; overflow-y: auto;
        }
        .controls h2 { 
            margin-bottom: 15px; color: #667eea; 
            font-size: 20px; display: flex; align-items: center; gap: 8px;
        }
        .control-group { margin-bottom: 15px; }
        .control-group label {
            display: block; margin-bottom: 8px;
            color: #333; font-size: 13px; font-weight: 600;
        }
        .control-group input[type="range"] {
            width: 100%; height: 6px; border-radius: 3px;
            background: #ddd; outline: none; -webkit-appearance: none;
        }
        .control-group input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none; appearance: none;
            width: 18px; height: 18px; border-radius: 50%;
            background: #667eea; cursor: pointer; transition: transform 0.2s;
        }
        .control-group input[type="range"]::-webkit-slider-thumb:hover { transform: scale(1.2); }
        .control-group input[type="range"]::-moz-range-thumb {
            width: 18px; height: 18px; border-radius: 50%;
            background: #667eea; cursor: pointer; border: none;
        }
        .button-group {
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 10px; margin-top: 15px;
        }
        .btn {
            padding: 10px; background: #667eea; color: white;
            border: none; border-radius: 6px; cursor: pointer;
            font-size: 13px; font-weight: 600; transition: all 0.2s;
        }
        .btn:hover { background: #5568d3; transform: translateY(-1px); }
        .btn:active { transform: translateY(0); }
        .info {
            position: absolute; bottom: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.98);
            padding: 15px 20px; border-radius: 8px;
            font-size: 12px; color: #666;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
            z-index: 100; max-height: 300px; overflow-y: auto;
            max-width: 340px;
        }
        .info div { margin-bottom: 5px; line-height: 1.5; }
        .info strong { color: #333; }
        .loading {
            position: absolute; top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(255, 255, 255, 0.98);
            padding: 30px 50px; border-radius: 12px;
            font-size: 18px; color: #667eea;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            z-index: 1000; text-align: center;
        }
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%; width: 40px; height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .warning {
            background: #fff3cd; color: #856404;
            padding: 8px 10px; border-radius: 6px;
            margin-top: 8px; font-size: 11px;
            border-left: 3px solid #ffc107;
        }
        .success {
            background: #d4edda; color: #155724;
            padding: 8px 10px; border-radius: 6px;
            margin-top: 8px; font-size: 11px;
            border-left: 3px solid #28a745;
        }
        .error {
            background: #f8d7da; color: #721c24;
            padding: 8px 10px; border-radius: 6px;
            margin-top: 8px; font-size: 11px;
            border-left: 3px solid #dc3545;
        }
    </style>
</head>
<body>
    <div id="container">
        <canvas id="canvas"></canvas>
        
        <div class="controls">
            <h2><span>🎨</span> Mesh Viewer</h2>
            
            <div class="control-group">
                <label>Rotation Speed: <span id="speedValue">0.5</span></label>
                <input type="range" id="rotationSpeed" min="0" max="2" step="0.1" value="0.5">
            </div>

            <div class="control-group">
                <label>Light Intensity: <span id="lightValue">1.0</span></label>
                <input type="range" id="lightIntensity" min="0" max="2" step="0.1" value="1">
            </div>

            <div class="button-group">
                <button class="btn" onclick="resetCamera()">🔄 Reset</button>
                <button class="btn" onclick="toggleWireframe()">🔲 Wireframe</button>
                <button class="btn" onclick="toggleRotation()">⏯️ Rotate</button>
                <button class="btn" onclick="centerModel()">🎯 Center</button>
            </div>
            
            <div id="statusMessages"></div>
        </div>

        <div class="info" id="info">
            <div><strong>🎮 Controls:</strong></div>
            <div>🖱️ Left Click + Drag: Rotate</div>
            <div>🖱️ Right Click + Drag: Pan</div>
            <div>🖱️ Scroll Wheel: Zoom</div>
            <div id="modelInfo" style="margin-top: 10px;"></div>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <div id="loadingText">Loading mesh structure...</div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script>
        const OBJ_DATA = `OBJ_FILE_CONTENT`;
        const MTL_DATA = `MTL_FILE_CONTENT`;
        const TEXTURES = TEXTURE_DATA;
        
        let scene, camera, renderer;
        let model;
        let autoRotate = false;
        let rotationSpeed = 0.5;
        let isWireframe = false;
        let lights = [];
        let loadingMessages = [];

        function addLoadingMessage(msg, type = 'info') {
            console.log(msg);
            loadingMessages.push({msg, type});
            updateLoadingDisplay();
        }

        function updateLoadingDisplay() {
            const loadingText = document.getElementById('loadingText');
            if (loadingText && loadingMessages.length > 0) {
                const latest = loadingMessages[loadingMessages.length - 1];
                loadingText.textContent = latest.msg;
            }
        }

        function addStatusMessage(msg, type = 'success') {
            const statusDiv = document.getElementById('statusMessages');
            const msgDiv = document.createElement('div');
            msgDiv.className = type;
            msgDiv.textContent = msg;
            statusDiv.appendChild(msgDiv);
        }

        function init() {
            try {
                addLoadingMessage('Initializing 3D scene...');
                
                const canvas = document.getElementById('canvas');
                scene = new THREE.Scene();
                scene.background = new THREE.Color(0x1a1a2e);
                
                camera = new THREE.PerspectiveCamera(
                    75, 
                    window.innerWidth / window.innerHeight, 
                    0.1, 
                    10000
                );
                camera.position.set(0, 50, 100);
                
                renderer = new THREE.WebGLRenderer({ 
                    canvas, 
                    antialias: true,
                    alpha: false
                });
                renderer.setSize(window.innerWidth, window.innerHeight);
                renderer.setPixelRatio(window.devicePixelRatio);
                renderer.shadowMap.enabled = true;
                renderer.shadowMap.type = THREE.PCFSoftShadowMap;

                addLoadingMessage('Setting up lighting...');
                
                const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
                scene.add(ambientLight);
                lights.push(ambientLight);
                
                const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
                directionalLight1.position.set(100, 100, 100);
                directionalLight1.castShadow = true;
                scene.add(directionalLight1);
                lights.push(directionalLight1);
                
                const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.5);
                directionalLight2.position.set(-100, 50, -100);
                scene.add(directionalLight2);
                lights.push(directionalLight2);
                
                const hemisphereLight = new THREE.HemisphereLight(0xffffff, 0x444444, 0.4);
                scene.add(hemisphereLight);
                lights.push(hemisphereLight);

                const gridHelper = new THREE.GridHelper(200, 20, 0x444444, 0x222222);
                scene.add(gridHelper);

                setupMouseControls();
                setupEventListeners();
                
                addLoadingMessage('Loading mesh data...');
                loadModel();
                
                animate();
            } catch (error) {
                console.error('Initialization error:', error);
                document.getElementById('loading').innerHTML = 
                    '<div style="color: #dc3545;">❌ Initialization Error: ' + error.message + '</div>';
            }
        }

        function setupEventListeners() {
            window.addEventListener('resize', onWindowResize);
            
            const speedSlider = document.getElementById('rotationSpeed');
            speedSlider.addEventListener('input', (e) => {
                rotationSpeed = parseFloat(e.target.value);
                document.getElementById('speedValue').textContent = rotationSpeed.toFixed(1);
            });
            
            const lightSlider = document.getElementById('lightIntensity');
            lightSlider.addEventListener('input', (e) => {
                const intensity = parseFloat(e.target.value);
                document.getElementById('lightValue').textContent = intensity.toFixed(1);
                if (lights.length >= 3) {
                    lights[1].intensity = intensity * 0.8;
                    lights[2].intensity = intensity * 0.5;
                }
            });
        }

        function setupMouseControls() {
            let isDragging = false, isPanning = false;
            let previousMousePosition = { x: 0, y: 0 };
            const canvas = document.getElementById('canvas');

            canvas.addEventListener('mousedown', (e) => {
                if (e.button === 0) isDragging = true;
                if (e.button === 2) isPanning = true;
                previousMousePosition = { x: e.clientX, y: e.clientY };
            });

            canvas.addEventListener('mousemove', (e) => {
                const deltaX = e.clientX - previousMousePosition.x;
                const deltaY = e.clientY - previousMousePosition.y;
                
                if (isDragging && model) {
                    model.rotation.y += deltaX * 0.01;
                    model.rotation.x += deltaY * 0.01;
                }
                if (isPanning) {
                    camera.position.x -= deltaX * 0.1;
                    camera.position.y += deltaY * 0.1;
                }
                previousMousePosition = { x: e.clientX, y: e.clientY };
            });

            canvas.addEventListener('mouseup', () => {
                isDragging = false;
                isPanning = false;
            });
            
            canvas.addEventListener('mouseleave', () => {
                isDragging = false;
                isPanning = false;
            });
            
            canvas.addEventListener('contextmenu', (e) => e.preventDefault());
            
            canvas.addEventListener('wheel', (e) => {
                e.preventDefault();
                const zoomSpeed = e.deltaY * 0.1;
                camera.position.z = Math.max(10, Math.min(500, camera.position.z + zoomSpeed));
            }, { passive: false });
        }

        async function loadModel() {
            try {
                addLoadingMessage('Parsing materials...');
                const materials = await parseMTL(MTL_DATA);
                
                addLoadingMessage('Parsing geometry...');
                const geometries = parseOBJ(OBJ_DATA, materials);
                
                if (geometries.length === 0) {
                    throw new Error('No valid geometry found in OBJ file');
                }
                
                addLoadingMessage('Building mesh...');
                model = new THREE.Group();
                let totalVertices = 0;
                let totalFaces = 0;
                
                geometries.forEach(({ geom, material }, index) => {
                    try {
                        const mesh = new THREE.Mesh(geom, material);
                        mesh.castShadow = true;
                        mesh.receiveShadow = true;
                        model.add(mesh);
                        totalVertices += geom.attributes.position.count;
                        totalFaces += geom.attributes.position.count / 3;
                    } catch (error) {
                        console.error(`Error creating mesh ${index}:`, error);
                    }
                });
                
                if (model.children.length === 0) {
                    throw new Error('Failed to create any meshes');
                }
                
                scene.add(model);
                centerModel();
                
                document.getElementById('loading').style.display = 'none';
                addStatusMessage(`✅ Mesh loaded successfully!`, 'success');
                
                updateModelInfo(
                    totalVertices, 
                    totalFaces,
                    geometries.length, 
                    Object.keys(materials).length
                );
                
            } catch (error) {
                console.error('Error loading model:', error);
                document.getElementById('loading').innerHTML = 
                    '<div style="color: #dc3545; text-align: left;">' +
                    '<strong>❌ Error Loading Model:</strong><br>' + 
                    error.message + 
                    '<br><br><small>Check console for details</small></div>';
                addStatusMessage('❌ Error: ' + error.message, 'error');
            }
        }

        async function parseMTL(mtlText) {
            const materials = {};
            
            if (!mtlText || mtlText.trim().length === 0) {
                addLoadingMessage('No MTL data, using default material');
                return materials;
            }
            
            try {
                let currentMaterial = null;
                const lines = mtlText.split('\n');
                const warnings = [];

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || trimmed.startsWith('#')) continue;
                    
                    const parts = trimmed.split(/\s+/);
                    
                    if (parts[0] === 'newmtl') {
                        currentMaterial = parts[1];
                        materials[currentMaterial] = {
                            color: new THREE.Color(0xcccccc),
                            map: null,
                            shininess: 30,
                            specular: new THREE.Color(0x111111),
                            opacity: 1.0
                        };
                    } else if (currentMaterial) {
                        try {
                            if (parts[0] === 'Kd' && parts.length >= 4) {
                                materials[currentMaterial].color = new THREE.Color(
                                    parseFloat(parts[1]) || 0,
                                    parseFloat(parts[2]) || 0,
                                    parseFloat(parts[3]) || 0
                                );
                            } else if (parts[0] === 'Ks' && parts.length >= 4) {
                                materials[currentMaterial].specular = new THREE.Color(
                                    parseFloat(parts[1]) || 0,
                                    parseFloat(parts[2]) || 0,
                                    parseFloat(parts[3]) || 0
                                );
                            } else if (parts[0] === 'Ns' && parts.length >= 2) {
                                materials[currentMaterial].shininess = parseFloat(parts[1]) || 30;
                            } else if (parts[0] === 'd' && parts.length >= 2) {
                                materials[currentMaterial].opacity = parseFloat(parts[1]) || 1.0;
                            } else if (parts[0] === 'map_Kd') {
                                const texturePath = parts.slice(1).join(' ');
                                const textureName = texturePath.split('/').pop().split('\\').pop();
                                
                                if (TEXTURES[textureName]) {
                                    try {
                                        const texture = new THREE.TextureLoader().load(TEXTURES[textureName]);
                                        texture.wrapS = THREE.RepeatWrapping;
                                        texture.wrapT = THREE.RepeatWrapping;
                                        materials[currentMaterial].map = texture;
                                    } catch (error) {
                                        warnings.push('Failed to load texture: ' + textureName);
                                    }
                                } else {
                                    warnings.push('Texture not found: ' + textureName);
                                }
                            }
                        } catch (error) {
                            console.warn('Error parsing MTL line:', line, error);
                        }
                    }
                }

                if (warnings.length > 0) {
                    addStatusMessage(`⚠️ ${warnings.length} texture warning(s)`, 'warning');
                }
                
                addLoadingMessage(`Loaded ${Object.keys(materials).length} materials`);
            } catch (error) {
                console.error('MTL parsing error:', error);
                addStatusMessage('⚠️ MTL parsing issues, using defaults', 'warning');
            }

            return materials;
        }

        function parseOBJ(objText, materials) {
            const geometries = [];
            
            if (!objText || objText.trim().length === 0) {
                throw new Error('OBJ file is empty');
            }
            
            try {
                const vertices = [], normals = [], uvs = [];
                const lines = objText.split('\n');
                
                let currentMaterial = null;
                let currentVertices = [], currentNormals = [], currentUVs = [];
                let lineNumber = 0;

                const finishGeometry = () => {
                    if (currentVertices.length > 0) {
                        try {
                            const geom = new THREE.BufferGeometry();
                            geom.setAttribute('position', new THREE.Float32BufferAttribute(currentVertices, 3));
                            
                            if (currentNormals.length === currentVertices.length) {
                                geom.setAttribute('normal', new THREE.Float32BufferAttribute(currentNormals, 3));
                            } else {
                                geom.computeVertexNormals();
                            }
                            
                            if (currentUVs.length > 0) {
                                const uvArray = new Float32Array(currentVertices.length / 3 * 2);
                                for (let i = 0; i < currentUVs.length && i < uvArray.length; i++) {
                                    uvArray[i] = currentUVs[i];
                                }
                                geom.setAttribute('uv', new THREE.Float32BufferAttribute(uvArray, 2));
                            }

                            const matData = materials[currentMaterial] || { 
                                color: new THREE.Color(0x888888), 
                                map: null, 
                                shininess: 30,
                                specular: new THREE.Color(0x111111),
                                opacity: 1.0
                            };
                            
                            const material = new THREE.MeshPhongMaterial({
                                color: matData.color,
                                map: matData.map,
                                shininess: matData.shininess,
                                specular: matData.specular,
                                side: THREE.DoubleSide,
                                transparent: matData.opacity < 1.0,
                                opacity: matData.opacity
                            });

                            geometries.push({ geom, material });
                        } catch (error) {
                            console.error('Error creating geometry:', error);
                        }
                        
                        currentVertices = [];
                        currentNormals = [];
                        currentUVs = [];
                    }
                };

                for (const line of lines) {
                    lineNumber++;
                    const trimmed = line.trim();
                    if (!trimmed || trimmed.startsWith('#')) continue;
                    
                    try {
                        const parts = trimmed.split(/\s+/);
                        
                        if (parts[0] === 'v' && parts.length >= 4) {
                            vertices.push([
                                parseFloat(parts[1]) || 0, 
                                parseFloat(parts[2]) || 0, 
                                parseFloat(parts[3]) || 0
                            ]);
                        } else if (parts[0] === 'vn' && parts.length >= 4) {
                            normals.push([
                                parseFloat(parts[1]) || 0, 
                                parseFloat(parts[2]) || 0, 
                                parseFloat(parts[3]) || 0
                            ]);
                        } else if (parts[0] === 'vt' && parts.length >= 2) {
                            uvs.push([
                                parseFloat(parts[1]) || 0, 
                                parseFloat(parts[2]) || 0
                            ]);
                        } else if (parts[0] === 'usemtl') {
                            finishGeometry();
                            currentMaterial = parts[1];
                        } else if (parts[0] === 'f' && parts.length >= 4) {
                            const faceVertices = [];
                            
                            for (let i = 1; i < parts.length; i++) {
                                const vertexInfo = parts[i].split('/');
                                const vIdx = parseInt(vertexInfo[0]) - 1;
                                const vtIdx = vertexInfo[1] ? parseInt(vertexInfo[1]) - 1 : null;
                                const vnIdx = vertexInfo[2] ? parseInt(vertexInfo[2]) - 1 : null;
                                
                                if (vIdx >= 0 && vIdx < vertices.length) {
                                    faceVertices.push({ vIdx, vtIdx, vnIdx });
                                }
                            }
                            
                            // Triangulate
                            for (let i = 1; i < faceVertices.length - 1; i++) {
                                [faceVertices[0], faceVertices[i], faceVertices[i + 1]].forEach(({ vIdx, vtIdx, vnIdx }) => {
                                    if (vertices[vIdx]) {
                                        currentVertices.push(...vertices[vIdx]);
                                    }
                                    if (vnIdx !== null && vnIdx >= 0 && vnIdx < normals.length) {
                                        currentNormals.push(...normals[vnIdx]);
                                    }
                                    if (vtIdx !== null && vtIdx >= 0 && vtIdx < uvs.length) {
                                        currentUVs.push(...uvs[vtIdx]);
                                    }
                                });
                            }
                        }
                    } catch (error) {
                        console.warn(`Error parsing line ${lineNumber}:`, line, error);
                    }
                }

                finishGeometry();
                
                addLoadingMessage(`Parsed ${vertices.length} vertices, ${geometries.length} meshes`);
            } catch (error) {
                console.error('OBJ parsing error:', error);
                throw new Error('Failed to parse OBJ file: ' + error.message);
            }

            return geometries;
        }

        function centerModel() {
            if (!model || model.children.length === 0) return;
            
            try {
                const box = new THREE.Box3().setFromObject(model);
                const center = box.getCenter(new THREE.Vector3());
                const size = box.getSize(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);
                
                if (maxDim > 0) {
                    const scale = 100 / maxDim;
                    model.position.sub(center);
                    model.scale.setScalar(scale);
                }
                
                camera.position.set(0, 50, 100);
                camera.lookAt(0, 0, 0);
            } catch (error) {
                console.error('Error centering model:', error);
            }
        }

        function resetCamera() {
            camera.position.set(0, 50, 100);
            camera.lookAt(0, 0, 0);
            camera.zoom = 1;
            camera.updateProjectionMatrix();
        }

        function toggleWireframe() {
            if (!model) return;
            isWireframe = !isWireframe;
            model.children.forEach(mesh => {
                if (mesh.material) {
                    mesh.material.wireframe = isWireframe;
                }
            });
        }

        function toggleRotation() {
            autoRotate = !autoRotate;
        }

        function updateModelInfo(vertexCount, faceCount, meshCount, materialCount) {
            const infoHTML = `
                <div style="margin-top: 10px; padding-top: 10px; border-top: 2px solid #667eea;">
                    <strong>📊 Mesh Statistics:</strong><br>
                    <strong>Vertices:</strong> ${vertexCount.toLocaleString()}<br>
                    <strong>Faces:</strong> ${Math.floor(faceCount).toLocaleString()}<br>
                    <strong>Meshes:</strong> ${meshCount}<br>
                    <strong>Materials:</strong> ${materialCount}<br>
                    <strong>Textures:</strong> ${Object.keys(TEXTURES).length}
                </div>
            `;
            document.getElementById('modelInfo').innerHTML = infoHTML;
        }

        function onWindowResize() {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }

        function animate() {
            requestAnimationFrame(animate);
            
            if (autoRotate && model) {
                model.rotation.y += rotationSpeed * 0.01;
            }
            
            renderer.render(scene, camera);
        }

        // Start the application
        init();
    </script>
</body>
</html>'''
    
    try:
        # Validate input file
        obj_path = Path(obj_file_path)
        if not obj_path.exists():
            raise FileNotFoundError(f"OBJ file not found: {obj_file_path}")
        
        if not obj_path.suffix.lower() == '.obj':
            raise ValueError("File must have .obj extension")
        
        print(f"\n{'='*60}")
        print(f"🚀 Starting OBJ Mesh Viewer")
        print(f"{'='*60}")
        print(f"📁 Loading OBJ file: {obj_path.name}")
        print(f"📍 Path: {obj_path}")
        
        # Read OBJ file with error handling
        try:
            with open(obj_path, 'r', encoding='utf-8', errors='ignore') as f:
                obj_content = f.read()
            
            if not obj_content.strip():
                raise ValueError("OBJ file is empty")
            
            print(f"✅ OBJ file loaded ({len(obj_content)} bytes)")
        except Exception as e:
            raise Exception(f"Failed to read OBJ file: {str(e)}")
        
        # Read MTL file
        mtl_path = obj_path.with_suffix('.mtl')
        mtl_content = ""
        
        if mtl_path.exists():
            try:
                print(f"📁 Loading MTL file: {mtl_path.name}")