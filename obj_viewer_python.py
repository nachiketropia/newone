import webbrowser
import os
import tempfile
from pathlib import Path

def view_obj_file(obj_file_path, auto_open=True):
    """
    Opens a 3D OBJ file in a web browser using the Three.js viewer.
    
    Args:
        obj_file_path (str): Path to the .obj file to view
        auto_open (bool): Whether to automatically open the browser (default: True)
    
    Returns:
        str: Path to the generated HTML file
    """
    
    # Read the HTML template
    html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D OBJ Model Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            overflow: hidden;
            height: 100vh;
        }
        #container { width: 100%; height: 100vh; position: relative; }
        #canvas { width: 100%; height: 100%; display: block; cursor: grab; }
        #canvas:active { cursor: grabbing; }
        .controls {
            position: absolute; top: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.95);
            padding: 20px; border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            max-width: 320px; backdrop-filter: blur(10px);
        }
        .controls h2 { margin-bottom: 15px; color: #1e3c72; font-size: 20px; }
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
        .info {
            position: absolute; bottom: 20px; left: 20px;
            background: rgba(255, 255, 255, 0.95);
            padding: 15px 20px; border-radius: 8px;
            font-size: 12px; color: #666;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }
        .info div { margin-bottom: 5px; }
        .info strong { color: #333; }
        .loading {
            position: absolute; top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(255, 255, 255, 0.95);
            padding: 30px 50px; border-radius: 12px;
            font-size: 18px; color: #667eea; display: block;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
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
    </style>
</head>
<body>
    <div id="container">
        <canvas id="canvas"></canvas>
        
        <div class="controls">
            <h2>🎨 3D Model Viewer</h2>
            
            <div class="control-group">
                <label>Rotation Speed</label>
                <input type="range" id="rotationSpeed" min="0" max="2" step="0.1" value="0.5">
            </div>

            <div class="control-group">
                <label>Zoom</label>
                <input type="range" id="zoom" min="0.1" max="5" step="0.1" value="1">
            </div>

            <div class="button-group">
                <button class="btn" onclick="resetCamera()">🔄 Reset View</button>
                <button class="btn" onclick="toggleWireframe()">🔲 Wireframe</button>
                <button class="btn" onclick="toggleRotation()">⏯️ Auto Rotate</button>
                <button class="btn" onclick="centerModel()">🎯 Center</button>
            </div>
        </div>

        <div class="info" id="info">
            <div><strong>Controls:</strong></div>
            <div>🖱️ Left Click + Drag: Rotate</div>
            <div>🖱️ Right Click + Drag: Pan</div>
            <div>🖱️ Scroll: Zoom</div>
            <div id="modelInfo"></div>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            Loading model...
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script>
        const OBJ_DATA = `OBJ_FILE_CONTENT`;
        
        let scene, camera, renderer;
        let models = [];
        let autoRotate = false;
        let rotationSpeed = 0.5;
        let isWireframe = false;

        function init() {
            const canvas = document.getElementById('canvas');
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x1a1a2e);
            camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 10000);
            camera.position.set(0, 50, 100);
            renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.shadowMap.enabled = true;

            const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
            scene.add(ambientLight);
            const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight1.position.set(100, 100, 100);
            scene.add(directionalLight1);
            const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
            directionalLight2.position.set(-100, 50, -100);
            scene.add(directionalLight2);

            const gridHelper = new THREE.GridHelper(200, 20, 0x444444, 0x222222);
            scene.add(gridHelper);

            setupMouseControls();
            window.addEventListener('resize', onWindowResize);
            
            document.getElementById('rotationSpeed').addEventListener('input', (e) => {
                rotationSpeed = parseFloat(e.target.value);
            });
            document.getElementById('zoom').addEventListener('input', (e) => {
                camera.zoom = parseFloat(e.target.value);
                camera.updateProjectionMatrix();
            });

            loadOBJ(OBJ_DATA);
            animate();
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
                if (isDragging) {
                    const deltaX = e.clientX - previousMousePosition.x;
                    const deltaY = e.clientY - previousMousePosition.y;
                    models.forEach(model => {
                        model.rotation.y += deltaX * 0.01;
                        model.rotation.x += deltaY * 0.01;
                    });
                }
                if (isPanning) {
                    const deltaX = e.clientX - previousMousePosition.x;
                    const deltaY = e.clientY - previousMousePosition.y;
                    camera.position.x -= deltaX * 0.1;
                    camera.position.y += deltaY * 0.1;
                }
                previousMousePosition = { x: e.clientX, y: e.clientY };
            });

            canvas.addEventListener('mouseup', () => {
                isDragging = false;
                isPanning = false;
            });
            canvas.addEventListener('contextmenu', (e) => e.preventDefault());
            canvas.addEventListener('wheel', (e) => {
                e.preventDefault();
                camera.position.z += e.deltaY * 0.1;
            });
        }

        function loadOBJ(objText) {
            const geometry = new THREE.BufferGeometry();
            const vertices = [], normals = [], uvs = [];
            const lines = objText.split('\\n');
            const vertexData = [], normalData = [], uvData = [];

            lines.forEach(line => {
                const parts = line.trim().split(/\\s+/);
                if (parts[0] === 'v') {
                    vertexData.push([parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3])]);
                } else if (parts[0] === 'vn') {
                    normalData.push([parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3])]);
                } else if (parts[0] === 'vt') {
                    uvData.push([parseFloat(parts[1]), parseFloat(parts[2])]);
                } else if (parts[0] === 'f') {
                    for (let i = 1; i <= 3; i++) {
                        const vertexInfo = parts[i].split('/');
                        const vIdx = parseInt(vertexInfo[0]) - 1;
                        const vtIdx = vertexInfo[1] ? parseInt(vertexInfo[1]) - 1 : null;
                        const vnIdx = vertexInfo[2] ? parseInt(vertexInfo[2]) - 1 : null;
                        if (vertexData[vIdx]) vertices.push(...vertexData[vIdx]);
                        if (vnIdx !== null && normalData[vnIdx]) normals.push(...normalData[vnIdx]);
                        if (vtIdx !== null && uvData[vtIdx]) uvs.push(...uvData[vtIdx]);
                    }
                }
            });

            geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
            if (normals.length > 0) {
                geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
            } else {
                geometry.computeVertexNormals();
            }
            if (uvs.length > 0) {
                geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
            }

            const material = new THREE.MeshPhongMaterial({
                color: 0x888888, shininess: 30, side: THREE.DoubleSide
            });
            const mesh = new THREE.Mesh(geometry, material);
            scene.add(mesh);
            models.push(mesh);
            centerModel();
            document.getElementById('loading').style.display = 'none';
            updateModelInfo(vertices.length / 3);
        }

        function centerModel() {
            if (models.length === 0) return;
            const box = new THREE.Box3();
            models.forEach(model => box.expandByObject(model));
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            const scale = 100 / maxDim;
            models.forEach(model => {
                model.position.sub(center);
                model.scale.setScalar(scale);
            });
            camera.position.set(0, 50, 100);
            camera.lookAt(0, 0, 0);
        }

        function resetCamera() {
            camera.position.set(0, 50, 100);
            camera.lookAt(0, 0, 0);
            camera.zoom = 1;
            camera.updateProjectionMatrix();
            document.getElementById('zoom').value = 1;
        }

        function toggleWireframe() {
            isWireframe = !isWireframe;
            models.forEach(model => { model.material.wireframe = isWireframe; });
        }

        function toggleRotation() {
            autoRotate = !autoRotate;
        }

        function updateModelInfo(vertexCount) {
            document.getElementById('modelInfo').innerHTML = `
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd;">
                    <strong>Vertices:</strong> ${vertexCount.toLocaleString()}
                </div>
            `;
        }

        function onWindowResize() {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }

        function animate() {
            requestAnimationFrame(animate);
            if (autoRotate) {
                models.forEach(model => { model.rotation.y += rotationSpeed * 0.01; });
            }
            renderer.render(scene, camera);
        }

        init();
    </script>
</body>
</html>'''
    
    # Validate file path
    obj_path = Path(obj_file_path)
    if not obj_path.exists():
        raise FileNotFoundError(f"OBJ file not found: {obj_file_path}")
    
    if not obj_path.suffix.lower() == '.obj':
        raise ValueError("File must have .obj extension")
    
    # Read OBJ file content
    with open(obj_path, 'r') as f:
        obj_content = f.read()
    
    # Escape backticks and special characters for JavaScript
    obj_content = obj_content.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
    
    # Replace placeholder with actual OBJ content
    html_content = html_template.replace('OBJ_FILE_CONTENT', obj_content)
    
    # Create temporary HTML file
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, f"obj_viewer_{obj_path.stem}.html")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ HTML viewer created: {output_path}")
    
    # Open in browser
    if auto_open:
        webbrowser.open('file://' + os.path.abspath(output_path))
        print("✓ Opening in browser...")
    
    return output_path


# Example usage:
if __name__ == "__main__":
    # Replace with your OBJ file path
    obj_file = "path/to/your/model.obj"
    
    try:
        html_path = view_obj_file(obj_file)
        print(f"\nViewer ready! File saved at: {html_path}")
    except Exception as e:
        print(f"Error: {e}")