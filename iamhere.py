import os
import time
from flask import Flask, render_template_string, request, jsonify, send_file
from werkzeug.utils import secure_filename
import numpy as np
from PIL import Image

try:
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import transform_bounds
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False
    print("Rasterio not available")

try:
    from osgeo import gdal, osr  # noqa: F401
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False
    print("GDAL not available")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# Use absolute directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['OUTPUT_FOLDER'] = os.path.join(BASE_DIR, 'outputs')
app.config['TILE_FOLDER'] = os.path.join(BASE_DIR, 'tiles')

for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER'], app.config['TILE_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# In-memory store: layer_id -> dict(metadata + filepath)
LAYER_STORE = {}


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GeoTIFF Processor - Python Edition</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; }

        .container { display: flex; height: 100vh; }

        .sidebar {
            width: 350px;
            background: #1f2937;
            color: white;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .header {
            padding: 20px;
            border-bottom: 1px solid #374151;
        }

        .header h1 {
            font-size: 20px;
            margin-bottom: 5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .header p {
            font-size: 13px;
            color: #9ca3af;
        }

        .upload-section {
            padding: 20px;
            border-bottom: 1px solid #374151;
        }

        .upload-btn {
            width: 100%;
            padding: 12px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: background 0.2s;
        }

        .upload-btn:hover { background: #2563eb; }

        .merge-btn {
            width: 100%;
            padding: 12px;
            background: #10b981;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            margin-top: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .merge-btn:hover { background: #059669; }
        .merge-btn:disabled { background: #6b7280; cursor: not-allowed; }

        .layers-section {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }

        .layers-title {
            font-size: 12px;
            font-weight: 600;
            color: #9ca3af;
            text-transform: uppercase;
            margin-bottom: 15px;
            letter-spacing: 0.5px;
        }

        .layer-item {
            background: #374151;
            border: 1px solid #4b5563;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
            transition: all 0.2s;
        }

        .layer-item:hover { border-color: #6b7280; }

        .layer-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }

        .layer-name {
            font-size: 14px;
            font-weight: 500;
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .layer-controls {
            display: flex;
            gap: 4px;
        }

        .layer-btn {
            background: #4b5563;
            border: none;
            color: white;
            padding: 4px 7px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            transition: background 0.2s;
        }

        .layer-btn:hover { background: #6b7280; }

        .layer-info {
            font-size: 11px;
            color: #9ca3af;
            margin-top: 8px;
        }

        .opacity-control {
            margin-top: 10px;
        }

        .opacity-control label {
            font-size: 11px;
            color: #9ca3af;
            display: block;
            margin-bottom: 5px;
        }

        .opacity-control input[type="range"] {
            width: 100%;
        }

        .status-bar {
            padding: 15px 20px;
            border-top: 1px solid #374151;
            font-size: 11px;
            color: #9ca3af;
        }

        .map-container {
            flex: 1;
            position: relative;
        }

        #map { width: 100%; height: 100%; }

        .map-controls {
            position: absolute;
            top: 20px;
            right: 20px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 1000;
        }

        .map-btn {
            background: white;
            border: none;
            padding: 10px;
            border-radius: 8px;
            cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .map-btn:hover { background: #f3f4f6; }

        .loading {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.8);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        }

        .loading.active { display: flex; }

        .spinner {
            width: 50px;
            height: 50px;
            border: 4px solid #374151;
            border-top-color: #3b82f6;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .loading-text {
            color: white;
            margin-top: 20px;
            font-size: 14px;
        }

        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #6b7280;
        }

        .empty-state svg {
            width: 60px;
            height: 60px;
            margin-bottom: 15px;
            opacity: 0.3;
        }

        .info-panel {
            position: absolute;
            bottom: 20px;
            left: 20px;
            background: rgba(31, 41, 55, 0.95);
            color: white;
            padding: 15px;
            border-radius: 8px;
            max-width: 400px;
            font-size: 13px;
            z-index: 1000;
        }

        .info-panel h3 {
            font-size: 14px;
            margin-bottom: 8px;
        }

        .info-panel ul {
            margin-left: 20px;
            line-height: 1.6;
        }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            background: #3b82f6;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            margin-left: 5px;
        }
    </style>
</head>
<body>
    <div class="loading" id="loading">
        <div style="text-align: center;">
            <div class="spinner"></div>
            <div class="loading-text" id="loadingText">Processing...</div>
        </div>
    </div>

    <div class="container">
        <div class="sidebar">
            <div class="header">
                <h1>
                    GeoTIFF Processor
                    <span class="badge">PYTHON</span>
                </h1>
                <p>Process & overlay large TIFF files</p>
            </div>

            <div class="upload-section">
                <label for="fileInput" class="upload-btn">
                    Upload GeoTIFF Files
                    <input type="file" id="fileInput" multiple accept=".tif,.tiff" style="display:none;">
                </label>

                <button class="merge-btn" id="mergeBtn" disabled>
                    Merge All Layers
                </button>

                <!-- NEW: Output path input -->
                <div style="margin-top: 12px;">
                    <label style="display: block; font-size: 12px; color: #9ca3af; margin-bottom: 5px;">
                        Merge output path (server)
                    </label>
                    <input id="mergeOutputPath" type="text"
                           placeholder="Leave empty = outputs/merged_output.tif"
                           style="width: 100%; padding: 8px; background: #374151; color: white; border: 1px solid #4b5563; border-radius: 6px; font-size: 13px;">
                    <div style="margin-top: 6px; font-size: 11px; color: #9ca3af;">
                        Example: <code>/tmp/merged_output.tif</code> or <code>D:\\data\\merged_output.tif</code>
                    </div>
                </div>

                <div style="margin-top: 15px;">
                    <label style="display: block; font-size: 12px; color: #9ca3af; margin-bottom: 5px;">Base Map</label>
                    <select id="baseMapSelect" style="width: 100%; padding: 8px; background: #374151; color: white; border: 1px solid #4b5563; border-radius: 6px; font-size: 13px; cursor: pointer;">
                        <option value="satellite">Satellite Image</option>
                        <option value="street">Street Map</option>
                    </select>
                </div>
            </div>

            <div class="layers-section">
                <div class="layers-title">LAYERS (<span id="layerCount">0</span>)</div>
                <div id="layersList">
                    <div class="empty-state">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
                        <p>No layers loaded</p>
                        <p style="font-size: 11px; margin-top: 5px;">Upload GeoTIFF files to begin</p>
                    </div>
                </div>
            </div>

            <div class="status-bar">
                <div id="statusText">Ready • GDAL: {{ 'Available' if gdal_available else 'Not Available' }}</div>
                <div style="margin-top: 5px; font-size: 10px; color: #6b7280;">
                    <span id="coordinates">Lat: 0.0000, Lng: 0.0000 | Zoom: 2</span>
                </div>
            </div>
        </div>

        <div class="map-container">
            <div id="map"></div>

            <!-- Keep custom buttons on right -->
            <div class="map-controls">
                <button class="map-btn" onclick="map.zoomIn()" title="Zoom In">+</button>
                <button class="map-btn" onclick="map.zoomOut()" title="Zoom Out">-</button>
                <button class="map-btn" onclick="map.setView([20, 0], 2)" title="Reset View">Reset</button>
            </div>

            <div class="info-panel">
                <h3>Features</h3>
                <ul>
                    <li>Upload GeoTIFF files (auto-zoom to location)</li>
                    <li>Satellite imagery base map</li>
                    <li>Automatic coordinate transformation to WGS84</li>
                    <li>Layer visibility & opacity controls</li>
                    <li>Merge multiple files into one</li>
                    <li>Export combined GeoTIFF</li>
                </ul>
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.2); font-size: 11px;">
                    <strong>Tip:</strong> Click 📍 on any layer to zoom to its location. Use opacity slider to blend layers. Check console for coordinate details.
                </div>
            </div>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // Disable Leaflet default zoom so you don't get zoom buttons on both left and right
        const map = L.map('map', { zoomControl: false }).setView([20, 0], 2);

        const satelliteLayer = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            { attribution: '© Esri Satellite', maxZoom: 19 }
        );

        const streetLayer = L.tileLayer(
            'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            { attribution: '© OpenStreetMap', maxZoom: 19 }
        );

        let currentBaseLayer = satelliteLayer;
        currentBaseLayer.addTo(map);

        document.getElementById('baseMapSelect').addEventListener('change', function() {
            map.removeLayer(currentBaseLayer);
            currentBaseLayer = (this.value === 'street') ? streetLayer : satelliteLayer;
            currentBaseLayer.addTo(map);
        });

        function updateCoordinates() {
            const center = map.getCenter();
            const zoom = map.getZoom();
            document.getElementById('coordinates').textContent =
                `Lat: ${center.lat.toFixed(4)}, Lng: ${center.lng.toFixed(4)} | Zoom: ${zoom}`;
        }

        map.on('move', updateCoordinates);
        map.on('zoom', updateCoordinates);
        updateCoordinates();

        let layers = [];
        let overlays = {};

        setTimeout(() => updateStatus('Ready'), 100);

        document.getElementById('fileInput').addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);
            for (const file of files) {
                await uploadFile(file);
            }
            e.target.value = '';
        });

        async function uploadFile(file) {
            const formData = new FormData();
            formData.append('file', file);

            showLoading(`Uploading ${file.name}...`);

            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    layers.push(data.layer);
                    addLayerToMap(data.layer);
                    updateLayersList();
                    updateStatus(`✓ Uploaded: ${file.name}`);
                } else {
                    alert(`Error: ${data.error}`);
                    updateStatus('Upload failed');
                }
            } catch (error) {
                console.error('Upload error:', error);
                alert(`Upload failed: ${error.message}`);
                updateStatus('Upload error');
            } finally {
                hideLoading();
            }
        }

        function addLayerToMap(layer) {
            if (layer.bounds && layer.bounds.length === 4) {
                console.log('Layer:', layer.filename);
                console.log('Bounds [W,S,E,N]:', layer.bounds);
                console.log('CRS:', layer.crs);
                console.log('Preview URL:', layer.preview_url);

                const [west, south, east, north] = layer.bounds;
                const bounds = L.latLngBounds([south, west], [north, east]);

                const overlay = L.imageOverlay(layer.preview_url, bounds, {
                    opacity: 0.7,
                    interactive: true,
                    crossOrigin: true
                });

                overlay.on('error', function() {
                    console.error('Error loading image overlay:', layer.preview_url);
                    alert(`Failed to load preview for ${layer.filename}.\n\nOpen this URL directly in a new tab to see the real error:\n${layer.preview_url}`);
                });

                overlay.on('load', function() {
                    console.log('Successfully loaded overlay for:', layer.filename);
                });

                overlay.addTo(map);
                overlays[layer.id] = overlay;

                map.flyToBounds(bounds, { padding: [50, 50], duration: 1.5, easeLinearity: 0.25 });

                const center = bounds.getCenter();
                const marker = L.marker(center, { title: layer.filename }).addTo(map);

                marker.bindPopup(`
                    <div style="font-family: sans-serif;">
                        <strong>${layer.filename}</strong><br>
                        <small style="color: #666;">
                            Size: ${layer.width} × ${layer.height} px<br>
                            CRS: ${layer.crs || 'Unknown'}<br>
                            Center: ${center.lat.toFixed(6)}, ${center.lng.toFixed(6)}<br>
                            Bounds: [${layer.bounds.map(b => b.toFixed(4)).join(', ')}]
                        </small>
                    </div>
                `);

                overlays[layer.id + '_marker'] = marker;
                updateStatus(`Zoomed to ${layer.filename}`);
            } else {
                console.warn('No valid bounds available for layer:', layer.filename);
                updateStatus(`No location data for ${layer.filename}`);
            }
        }

        function updateLayersList() {
            const container = document.getElementById('layersList');
            document.getElementById('layerCount').textContent = layers.length;

            if (layers.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>No layers loaded</p>
                    </div>
                `;
                document.getElementById('mergeBtn').disabled = true;
                return;
            }

            document.getElementById('mergeBtn').disabled = layers.length < 2;

            container.innerHTML = layers.map(layer => `
                <div class="layer-item">
                    <div class="layer-header">
                        <div class="layer-name">${layer.filename}</div>
                        <div class="layer-controls">
                            <button class="layer-btn" onclick="zoomToLayer('${layer.id}')" title="Zoom to layer">📍</button>
                            <button class="layer-btn" onclick="toggleLayer('${layer.id}')" title="Toggle visibility">👁️</button>
                            <button class="layer-btn" onclick="removeLayer('${layer.id}')" title="Remove layer">🗑️</button>
                        </div>
                    </div>
                    <div class="opacity-control">
                        <label>Opacity: <span id="opacity-${layer.id}">70</span>%</label>
                        <input type="range" min="0" max="100" value="70"
                               oninput="setOpacity('${layer.id}', this.value)">
                    </div>
                    <div class="layer-info">
                        Size: ${layer.width} × ${layer.height} px<br>
                        ${layer.crs || 'Unknown CRS'}<br>
                        Bounds: [${layer.bounds ? layer.bounds.map(b => b.toFixed(4)).join(', ') : 'N/A'}]
                    </div>
                </div>
            `).join('');
        }

        function zoomToLayer(layerId) {
            const layer = layers.find(l => l.id === layerId);
            if (layer && layer.bounds) {
                const bounds = L.latLngBounds([layer.bounds[1], layer.bounds[0]], [layer.bounds[3], layer.bounds[2]]);
                map.flyToBounds(bounds, { padding: [50, 50], duration: 1.5, easeLinearity: 0.25 });
                updateStatus(`Zoomed to ${layer.filename}`);
            }
        }

        function toggleLayer(layerId) {
            const overlay = overlays[layerId];
            const marker = overlays[layerId + '_marker'];

            if (overlay) {
                if (map.hasLayer(overlay)) {
                    map.removeLayer(overlay);
                    if (marker) map.removeLayer(marker);
                } else {
                    overlay.addTo(map);
                    if (marker) marker.addTo(map);
                }
            }
        }

        function setOpacity(layerId, value) {
            const overlay = overlays[layerId];
            if (overlay) overlay.setOpacity(value / 100);
            document.getElementById(`opacity-${layerId}`).textContent = value;
        }

        function removeLayer(layerId) {
            const overlay = overlays[layerId];
            const marker = overlays[layerId + '_marker'];

            if (overlay) { map.removeLayer(overlay); delete overlays[layerId]; }
            if (marker) { map.removeLayer(marker); delete overlays[layerId + '_marker']; }

            layers = layers.filter(l => l.id !== layerId);
            updateLayersList();
        }

        document.getElementById('mergeBtn').addEventListener('click', async () => {
            if (layers.length < 2) return;

            showLoading('Merging layers...');

            try {
                const outputPath = document.getElementById('mergeOutputPath')?.value?.trim() || '';

                const response = await fetch('/merge', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        layer_ids: layers.map(l => l.id),
                        output_path: outputPath
                    })
                });

                const data = await response.json();

                if (data.success) {
                    alert(`✓ Merge complete!\n\nSaved to: ${data.saved_to}\n` +
                          (data.download_url ? `\nDownloading...` : `\n(No download link since it was saved outside outputs/)`));

                    // Chrome-style download (no new tab)
                    if (data.download_url) {
                        window.location.href = data.download_url;
                    }

                    updateStatus('✓ Merge successful');
                } else {
                    alert(`Merge failed: ${data.error}`);
                    updateStatus('Merge failed');
                }
            } catch (error) {
                alert(`Merge failed: ${error.message}`);
                updateStatus('Merge error');
            } finally {
                hideLoading();
            }
        });

        function showLoading(text) {
            document.getElementById('loading').classList.add('active');
            document.getElementById('loadingText').textContent = text;
        }

        function hideLoading() {
            document.getElementById('loading').classList.remove('active');
        }

        function updateStatus(text) {
            const statusDiv = document.getElementById('statusText');
            const gdalStatus = "{{ 'Available' if gdal_available else 'Not Available' }}";
            statusDiv.textContent = `${text} • GDAL: ${gdalStatus}`;
        }
    </script>
</body>
</html>
"""


def send_file_compat(path, *, mimetype=None, as_attachment=False, filename=None):
    """Compatibility wrapper: Flask 2.x uses download_name; Flask 1.x uses attachment_filename."""
    try:
        return send_file(
            path,
            mimetype=mimetype,
            as_attachment=as_attachment,
            download_name=filename
        )
    except TypeError:
        return send_file(
            path,
            mimetype=mimetype,
            as_attachment=as_attachment,
            attachment_filename=filename
        )


class TIFFProcessor:
    @staticmethod
    def get_tiff_info(filepath):
        info = {'width': None, 'height': None, 'bounds': None, 'crs': None, 'bands': None}

        if RASTERIO_AVAILABLE:
            try:
                with rasterio.open(filepath) as src:
                    info['width'] = src.width
                    info['height'] = src.height
                    info['bands'] = src.count
                    info['crs'] = src.crs.to_string() if src.crs else None

                    bounds = src.bounds

                    if src.crs:
                        epsg = src.crs.to_epsg()
                        if epsg != 4326:
                            b = transform_bounds(
                                src.crs, "EPSG:4326",
                                bounds.left, bounds.bottom, bounds.right, bounds.top,
                                densify_pts=21
                            )
                            info['bounds'] = [b[0], b[1], b[2], b[3]]
                        else:
                            info['bounds'] = [bounds.left, bounds.bottom, bounds.right, bounds.top]
                    else:
                        info['bounds'] = None

                return info
            except Exception as e:
                print(f"Error reading TIFF: {e}")
                import traceback
                traceback.print_exc()

        try:
            with Image.open(filepath) as img:
                info['width'], info['height'] = img.size
        except Exception:
            pass

        return info

    @staticmethod
    def create_preview(filepath, output_path, max_size=2048):
        """Create downsampled RGBA PNG preview with transparent NoData background."""
        try:
            if not RASTERIO_AVAILABLE:
                raise RuntimeError("Rasterio required for preview generation")

            with rasterio.open(filepath) as src:
                scale = min(max_size / src.width, max_size / src.height, 1.0)
                out_w = max(1, int(src.width * scale))
                out_h = max(1, int(src.height * scale))

                data = src.read(
                    out_shape=(src.count, out_h, out_w),
                    resampling=Resampling.bilinear
                ).astype("float32")

                if data.shape[0] >= 3:
                    rgb = data[:3]
                else:
                    rgb = np.repeat(data[:1], 3, axis=0)

                # Alpha from dataset mask (nodata/mask aware)
                try:
                    mask = src.dataset_mask(out_shape=(out_h, out_w), resampling=Resampling.nearest)
                    alpha = mask.astype(np.uint8)  # 0..255
                except Exception:
                    nodata = src.nodata
                    raw = src.read(out_shape=(src.count, out_h, out_w), resampling=Resampling.nearest)
                    if nodata is not None:
                        valid = np.any(raw != nodata, axis=0)
                    else:
                        valid = np.any(raw != 0, axis=0)
                    alpha = (valid.astype(np.uint8) * 255)

                # Normalize RGB bands (alpha handles background transparency)
                for i in range(3):
                    band = rgb[i]
                    band_min, band_max = float(np.nanmin(band)), float(np.nanmax(band))
                    if band_max > band_min:
                        band = (band - band_min) / (band_max - band_min)
                    else:
                        band[:] = 0.0
                    rgb[i] = band

                rgb = np.clip(rgb * 255, 0, 255).astype(np.uint8)
                rgb = np.transpose(rgb, (1, 2, 0))  # HWC

                rgba = np.dstack([rgb, alpha])

                img = Image.fromarray(rgba, mode="RGBA")
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                img.save(output_path, "PNG")
                return True

        except Exception as e:
            print("Preview generation failed")
            print(e)
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def merge_tiffs(input_files, output_file):
        if not RASTERIO_AVAILABLE:
            return False, "rasterio not available"

        try:
            with rasterio.open(input_files[0]) as ref:
                ref_crs = ref.crs
                if not ref_crs:
                    return False, "Reference raster has no CRS; cannot merge reliably."

                datasets = []
                try:
                    datasets.append(rasterio.open(input_files[0]))

                    for fp in input_files[1:]:
                        src = rasterio.open(fp)
                        if not src.crs:
                            src.close()
                            return False, f"Raster has no CRS: {os.path.basename(fp)}"

                        if src.crs != ref_crs:
                            vrt = WarpedVRT(src, crs=ref_crs, resampling=Resampling.nearest)
                            datasets.append(vrt)
                        else:
                            datasets.append(src)

                    mosaic, out_transform = merge(datasets)

                    out_meta = ref.meta.copy()
                    out_meta.update({
                        "driver": "GTiff",
                        "height": mosaic.shape[1],
                        "width": mosaic.shape[2],
                        "count": mosaic.shape[0],
                        "transform": out_transform,
                        "crs": ref_crs,
                        "compress": "lzw"
                    })

                    with rasterio.open(output_file, "w", **out_meta) as dest:
                        dest.write(mosaic)

                finally:
                    for ds in datasets:
                        try:
                            ds.close()
                        except Exception:
                            pass

            return True, "Merge successful"
        except Exception as e:
            return False, str(e)


@app.route('/')
def index():
    return render_template_string(
        HTML_TEMPLATE,
        gdal_available=GDAL_AVAILABLE,
        rasterio_available=RASTERIO_AVAILABLE
    )


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})

    if not file.filename.lower().endswith(('.tif', '.tiff')):
        return jsonify({'success': False, 'error': 'Not a TIFF file'})

    try:
        layer_id = f"layer_{int(time.time() * 1000)}_{os.getpid()}"
        original_name = secure_filename(file.filename)
        stored_name = f"{layer_id}_{original_name}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
        file.save(filepath)

        info = TIFFProcessor.get_tiff_info(filepath)

        if info['width'] is None or info['height'] is None:
            return jsonify({'success': False, 'error': 'Could not read TIFF dimensions'})

        if not info['bounds'] or len(info['bounds']) != 4:
            return jsonify({'success': False, 'error': 'Could not extract valid WGS84 bounds (missing/unknown CRS?)'})

        preview_filename = f"{layer_id}_preview.png"
        preview_path = os.path.join(app.config['OUTPUT_FOLDER'], preview_filename)

        preview_created = TIFFProcessor.create_preview(filepath, preview_path)
        if not preview_created:
            return jsonify({'success': False, 'error': 'Failed to create preview image. Check server logs.'})

        if not os.path.exists(preview_path) or os.path.getsize(preview_path) == 0:
            return jsonify({'success': False, 'error': 'Preview file missing or empty'})

        layer = {
            'id': layer_id,
            'filename': original_name,
            'width': info['width'],
            'height': info['height'],
            'bounds': info['bounds'],
            'crs': info['crs'],
            'preview_url': f'/preview/{preview_filename}?t={int(time.time())}'
        }

        LAYER_STORE[layer_id] = {
            **layer,
            'filepath': filepath,
            'preview_path': preview_path,
            'stored_name': stored_name
        }

        return jsonify({'success': True, 'layer': layer})

    except Exception as e:
        print(f"ERROR during upload: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Upload error: {str(e)}'})


@app.route('/merge', methods=['POST'])
def merge_layers():
    data = request.get_json(silent=True) or {}
    layer_ids = data.get('layer_ids', [])
    output_path = (data.get('output_path') or "").strip()

    if len(layer_ids) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 layers'})

    input_files = []
    missing = []
    for lid in layer_ids:
        entry = LAYER_STORE.get(lid)
        if not entry:
            missing.append(lid)
        else:
            input_files.append(entry['filepath'])

    if missing:
        return jsonify({'success': False, 'error': f'Unknown layer ids: {missing}'})

    # Determine output file path
    if output_path:
        if os.path.isdir(output_path):
            output_file = os.path.join(output_path, "merged_output.tif")
        else:
            output_file = output_path

        out_dir = os.path.dirname(os.path.abspath(output_file)) or BASE_DIR
        os.makedirs(out_dir, exist_ok=True)

        # Safety: restrict output to BASE_DIR (comment out if you want "write anywhere")
        base_real = os.path.realpath(BASE_DIR)
        out_real = os.path.realpath(os.path.abspath(output_file))
        if not out_real.startswith(base_real):
            return jsonify({'success': False, 'error': f'For safety, output path must be inside: {BASE_DIR}'})
    else:
        output_file = os.path.join(app.config['OUTPUT_FOLDER'], 'merged_output.tif')

    success, message = TIFFProcessor.merge_tiffs(input_files, output_file)
    if not success:
        return jsonify({'success': False, 'error': message})

    out_real = os.path.realpath(os.path.abspath(output_file))
    outputs_real = os.path.realpath(app.config['OUTPUT_FOLDER'])

    resp = {
        'success': True,
        'output_file': os.path.basename(output_file),
        'saved_to': os.path.abspath(output_file),
        'download_url': None
    }

    # Only expose download URL if the file lives inside OUTPUT_FOLDER
    if out_real.startswith(outputs_real):
        resp['download_url'] = f"/download/{os.path.basename(output_file)}"

    return jsonify(resp)


@app.route('/preview/<path:filename>')
def serve_preview(filename):
    filename = os.path.basename(filename)
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)

    if not os.path.exists(filepath):
        return "Preview not found", reminder_404()

    return send_file_compat(filepath, mimetype='image/png', as_attachment=False, filename=filename)


def reminder_404():
    # Small helper so your server logs can still explain what happened.
    print("ERROR: Preview not found. Output folder contents:", os.listdir(app.config['OUTPUT_FOLDER']))
    return 404


@app.route('/download/<path:filename>')
def download_file(filename):
    filename = os.path.basename(filename)
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)

    if not os.path.exists(filepath):
        return "Not found", 404

    return send_file_compat(filepath, as_attachment=True, filename=filename)


@app.route('/debug/preview/<path:filename>')
def debug_preview(filename):
    filename = os.path.basename(filename)
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    return jsonify({
        "filename": filename,
        "filepath": filepath,
        "exists": os.path.exists(filepath),
        "size_bytes": os.path.getsize(filepath) if os.path.exists(filepath) else None,
        "output_dir": app.config['OUTPUT_FOLDER'],
        "output_dir_listing": os.listdir(app.config['OUTPUT_FOLDER'])
    })


if __name__ == '__main__':
    print("=" * 70)
    print("GeoTIFF Processing Web Application")
    print("=" * 70)
    print("✓ Flask server starting...")
    print(f"✓ GDAL Available: {GDAL_AVAILABLE}")
    print(f"✓ Rasterio Available: {RASTERIO_AVAILABLE}")
    print(f"\nUpload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"Output folder: {app.config['OUTPUT_FOLDER']}")
    print("\nOpen browser to: http://localhost:5002")
    print("=" * 70)
    app.run(debug=True, host='0.0.0.0', port=5002)
