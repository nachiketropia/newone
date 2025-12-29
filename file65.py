#!/usr/bin/env python3
"""
GeoTIFF Processing Web Application
Processes and overlays large TIFF files on interactive maps
All HTML/JS embedded within Python

Backend fixes:
- Preview generation reads only required bands (memory-safe)
- Preview supports single-band colormap TIFFs (classified rasters)
- Upload returns the real preview error message (no more guessing)
- Merge merges the selected layers (via registry)
- Merge supports mixed CRS by reprojection to first layer's CRS
"""

import os
import json
import time
import uuid
import tempfile
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, send_file
from werkzeug.utils import secure_filename

import numpy as np
from PIL import Image

# Optional imports for TIFF processing
try:
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import calculate_default_transform, reproject, transform_bounds
    from rasterio.enums import Resampling as ResamplingEnum
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False
    print("⚠ rasterio not available. Install with: pip install rasterio")

try:
    from osgeo import gdal  # type: ignore
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False
    print("⚠ GDAL not available. Install with: pip install gdal")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['TILE_FOLDER'] = 'tiles'
app.config['REGISTRY_FILE'] = 'layer_registry.json'

# Create necessary folders
for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER'], app.config['TILE_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# ---------------------------
# Layer registry (layer_id -> filepath)
# ---------------------------
LAYER_REGISTRY = {}  # layer_id: {filepath, filename, preview_filename, ...}

def _load_registry():
    path = app.config['REGISTRY_FILE']
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}

def _save_registry():
    path = app.config['REGISTRY_FILE']
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(LAYER_REGISTRY, f, indent=2)
    except Exception as e:
        print("⚠ Failed to save registry:", e)

LAYER_REGISTRY.update(_load_registry())


# HTML Template with embedded JavaScript
# (UNCHANGED - exactly as you posted)
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
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="header">
                <h1>
                    🗺️ GeoTIFF Processor
                    <span class="badge">PYTHON</span>
                </h1>
                <p>Process & overlay large TIFF files</p>
            </div>
            
            <div class="upload-section">
                <label for="fileInput" class="upload-btn">
                    📁 Upload GeoTIFF Files
                    <input type="file" id="fileInput" multiple accept=".tif,.tiff" style="display:none;">
                </label>
                
                <button class="merge-btn" id="mergeBtn" disabled>
                    🔗 Merge All Layers
                </button>
                
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
        
        <!-- Map -->
        <div class="map-container">
            <div id="map"></div>
            
            <div class="map-controls">
                <button class="map-btn" onclick="map.zoomIn()" title="Zoom In">➕</button>
                <button class="map-btn" onclick="map.zoomOut()" title="Zoom Out">➖</button>
                <button class="map-btn" onclick="map.setView([20, 0], 2)" title="Reset View">🌍</button>
            </div>
            
            <div class="info-panel">
                <h3>📊 Features</h3>
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
        // Initialize map
        const map = L.map('map').setView([20, 0], 2);
        
        // Basemap definitions
        const satelliteLayer = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            { attribution: '© Esri Satellite', maxZoom: 19 }
        );

        const streetLayer = L.tileLayer(
            'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            { attribution: '© OpenStreetMap', maxZoom: 19 }
        );

        // ✅ Only one basemap active by default
        let currentBaseLayer = satelliteLayer;
        currentBaseLayer.addTo(map);

        // ✅ Switch basemap via dropdown
        document.getElementById('baseMapSelect').addEventListener('change', function() {
            // Remove current basemap
            map.removeLayer(currentBaseLayer);

            // Set new basemap based on dropdown
            if (this.value === 'street') {
                currentBaseLayer = streetLayer;
            } else {
                currentBaseLayer = satelliteLayer;
            }

            // Add new basemap
            currentBaseLayer.addTo(map);
        });
        
        // Update coordinates on map move
        function updateCoordinates() {
            const center = map.getCenter();
            const zoom = map.getZoom();
            document.getElementById('coordinates').textContent = 
                `Lat: ${center.lat.toFixed(4)}, Lng: ${center.lng.toFixed(4)} | Zoom: ${zoom}`;
        }
        
        map.on('move', updateCoordinates);
        map.on('zoom', updateCoordinates);
        updateCoordinates();
        
        // Layer management
        let layers = [];
        let overlays = {};
        
        // Set initial status
        setTimeout(() => updateStatus('Ready'), 100);
        
        // File upload handler
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
                    updateStatus('❌ Upload failed');
                }
            } catch (error) {
                console.error('Upload error:', error);
                alert(`Upload failed: ${error.message}`);
                updateStatus('❌ Upload error');
            } finally {
                hideLoading();
            }
        }
        
        function addLayerToMap(layer) {
            if (layer.bounds && layer.bounds.length === 4) {
                // Log bounds for debugging
                console.log('Layer:', layer.filename);
                console.log('Bounds [W,S,E,N]:', layer.bounds);
                console.log('CRS:', layer.crs);
                console.log('Preview URL:', layer.preview_url);
                
                // Validate bounds are in valid lat/lng range
                const [west, south, east, north] = layer.bounds;
                if (Math.abs(south) > 90 || Math.abs(north) > 90 || 
                    Math.abs(west) > 180 || Math.abs(east) > 180) {
                    console.error('Invalid geographic bounds! Coordinates may not be in WGS84.');
                    alert(`⚠️ Warning: ${layer.filename} has invalid coordinates.\n\n` +
                          `Bounds: [${layer.bounds.join(', ')}]\n\n` +
                          `These coordinates appear to be in a projected CRS, not WGS84. ` +
                          `The file may display at the wrong location.`);
                }
                
                const bounds = L.latLngBounds(
                    [south, west],  // Southwest corner
                    [north, east]   // Northeast corner
                );
                
                // Create image overlay with error handling
                const overlay = L.imageOverlay(layer.preview_url, bounds, {
                    opacity: 0.7,
                    interactive: true,
                    crossOrigin: true
                });
                
                overlay.on('error', function(e) {
                    console.error('Error loading image overlay:', layer.preview_url);
                    alert(`Failed to load preview for ${layer.filename}. Check if the file was processed correctly.`);
                });
                
                overlay.addTo(map);
                overlays[layer.id] = overlay;
                
                map.flyToBounds(bounds, {
                    padding: [50, 50],
                    duration: 1.5,
                    easeLinearity: 0.25
                });
                
                const center = bounds.getCenter();
                const marker = L.marker(center, {
                    title: layer.filename
                }).addTo(map);
                
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
                
                updateStatus(`📍 Zoomed to ${layer.filename}`);
            } else {
                console.warn('No valid bounds available for layer:', layer.filename);
                updateStatus(`⚠️ No location data for ${layer.filename}`);
            }
        }
        
        function updateLayersList() {
            const container = document.getElementById('layersList');
            document.getElementById('layerCount').textContent = layers.length;
            
            if (layers.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
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
                const bounds = L.latLngBounds(
                    [layer.bounds[1], layer.bounds[0]],
                    [layer.bounds[3], layer.bounds[2]]
                );
                
                map.flyToBounds(bounds, {
                    padding: [50, 50],
                    duration: 1.5,
                    easeLinearity: 0.25
                });
                
                updateStatus(`📍 Zoomed to ${layer.filename}`);
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
            if (overlay) {
                overlay.setOpacity(value / 100);
            }
            document.getElementById(`opacity-${layerId}`).textContent = value;
        }
        
        function removeLayer(layerId) {
            const overlay = overlays[layerId];
            const marker = overlays[layerId + '_marker'];
            
            if (overlay) {
                map.removeLayer(overlay);
                delete overlays[layerId];
            }
            if (marker) {
                map.removeLayer(marker);
                delete overlays[layerId + '_marker'];
            }
            
            layers = layers.filter(l => l.id !== layerId);
            updateLayersList();
        }
        
        // Merge layers
        document.getElementById('mergeBtn').addEventListener('click', async () => {
            if (layers.length < 2) return;
            
            showLoading('Merging layers...');
            
            try {
                const response = await fetch('/merge', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ layer_ids: layers.map(l => l.id) })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert(`✓ Merge complete!\n\nOutput: ${data.output_file}\n\nDownload available.`);
                    window.open(data.download_url, '_blank');
                    updateStatus('✓ Merge successful');
                } else {
                    alert(`Merge failed: ${data.error}`);
                    updateStatus('❌ Merge failed');
                }
            } catch (error) {
                alert(`Merge failed: ${error.message}`);
                updateStatus('❌ Merge error');
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


class TIFFProcessor:
    """Handle TIFF file processing operations"""

    @staticmethod
    def get_tiff_info(filepath):
        """Extract metadata from TIFF file"""
        info = {
            'width': None,
            'height': None,
            'bounds': None,   # WGS84 [west, south, east, north] OR None
            'crs': None,
            'bands': None
        }

        if RASTERIO_AVAILABLE:
            try:
                with rasterio.open(filepath) as src:
                    info['width'] = int(src.width)
                    info['height'] = int(src.height)
                    info['bands'] = int(src.count) if src.count else None
                    info['crs'] = src.crs.to_string() if src.crs else None

                    # Bounds in source CRS
                    b = src.bounds

                    # Transform bounds to EPSG:4326 for Leaflet (only when CRS exists)
                    if src.crs:
                        try:
                            epsg = src.crs.to_epsg()
                            if epsg == 4326:
                                info['bounds'] = [float(b.left), float(b.bottom), float(b.right), float(b.top)]
                            else:
                                bounds_wgs84 = transform_bounds(
                                    src.crs, "EPSG:4326",
                                    b.left, b.bottom, b.right, b.top,
                                    densify_pts=21
                                )
                                info['bounds'] = [float(x) for x in bounds_wgs84]
                        except Exception as e:
                            print("⚠ Bounds transform failed; continuing without bounds:", e)
                            info['bounds'] = None
                    else:
                        info['bounds'] = None

                return info
            except Exception as e:
                print(f"Error reading TIFF with rasterio: {e}")
                import traceback
                traceback.print_exc()

        # Fallback to PIL for basic info (no CRS/bounds)
        try:
            with Image.open(filepath) as img:
                info['width'], info['height'] = img.size
        except Exception:
            pass

        return info

    @staticmethod
    def create_preview(filepath, output_path, max_size=2048):
        """
        Robust preview generator with transparency.
        Returns: (True, None) on success, (False, error_message) on failure.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if not RASTERIO_AVAILABLE:
            return False, "Rasterio not available (pip install rasterio)"

        # Attempt 1: Rasterio preview
        try:
            with rasterio.open(filepath) as src:
                if src.width <= 0 or src.height <= 0:
                    return False, f"Invalid raster dimensions: {src.width}x{src.height}"

                scale = min(max_size / src.width, max_size / src.height, 1.0)
                out_w = max(1, int(src.width * scale))
                out_h = max(1, int(src.height * scale))

                count = int(src.count) if src.count else 1

                # Single-band colormap (classified rasters)
                if count == 1:
                    try:
                        cmap = src.colormap(1)  # {value: (r,g,b, a?)}
                    except Exception:
                        cmap = None

                    band = src.read(
                        1,
                        out_shape=(out_h, out_w),
                        resampling=ResamplingEnum.nearest,
                        masked=True
                    )

                    mask = ~np.ma.getmaskarray(band)
                    arr = np.ma.filled(band, 0).astype(np.int64)

                    if cmap:
                        rgba = np.zeros((out_h, out_w, 4), dtype=np.uint8)
                        rgba[..., 3] = (mask.astype(np.uint8) * 255)

                        if mask.any():
                            unique_vals = np.unique(arr[mask])
                            for v in unique_vals:
                                color = cmap.get(int(v), (0, 0, 0, 255))
                                if len(color) == 3:
                                    r, g, b = color
                                    a = 255
                                else:
                                    r, g, b, a = color[:4]
                                sel = (arr == v) & mask
                                rgba[sel, 0] = r
                                rgba[sel, 1] = g
                                rgba[sel, 2] = b
                                rgba[sel, 3] = a

                        Image.fromarray(rgba, mode="RGBA").save(output_path, "PNG", optimize=True)
                        return True, None

                    # No colormap: grayscale
                    band_f = np.ma.filled(band, np.nan).astype(np.float32)
                    valid = np.isfinite(band_f) & mask
                    if valid.any():
                        vmin, vmax = np.percentile(band_f[valid], [2, 98])
                        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
                            vmin, vmax = float(np.nanmin(band_f[valid])), float(np.nanmax(band_f[valid]))
                        scaled = (band_f - vmin) / (vmax - vmin) if vmax > vmin else np.zeros_like(band_f)
                    else:
                        scaled = np.zeros_like(band_f, dtype=np.float32)

                    gray8 = (np.clip(scaled, 0, 1) * 255).astype(np.uint8)
                    alpha = (mask.astype(np.uint8) * 255)
                    rgba = np.dstack([gray8, gray8, gray8, alpha])

                    Image.fromarray(rgba, mode="RGBA").save(output_path, "PNG", optimize=True)
                    return True, None

                # Multi-band: read only 1-3 safely
                if count >= 3:
                    data = src.read(
                        indexes=[1, 2, 3],
                        out_shape=(3, out_h, out_w),
                        resampling=ResamplingEnum.bilinear,
                        masked=True
                    )
                    r, g, b = data[0], data[1], data[2]
                elif count == 2:
                    data = src.read(
                        indexes=[1, 2],
                        out_shape=(2, out_h, out_w),
                        resampling=ResamplingEnum.bilinear,
                        masked=True
                    )
                    r, g = data[0], data[1]
                    b = g
                else:
                    band = src.read(
                        1,
                        out_shape=(out_h, out_w),
                        resampling=ResamplingEnum.bilinear,
                        masked=True
                    )
                    r = g = b = band

                invalid = (np.ma.getmaskarray(r) |
                           np.ma.getmaskarray(g) |
                           np.ma.getmaskarray(b))
                valid_mask = ~invalid

                r_arr = np.ma.filled(r, np.nan).astype(np.float32)
                g_arr = np.ma.filled(g, np.nan).astype(np.float32)
                b_arr = np.ma.filled(b, np.nan).astype(np.float32)

                def norm_uint8(arr):
                    good = np.isfinite(arr) & valid_mask
                    if not good.any():
                        return np.zeros(arr.shape, dtype=np.uint8)
                    vals = arr[good]
                    vmin, vmax = np.percentile(vals, [2, 98])
                    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
                        vmin, vmax = float(vals.min()), float(vals.max())
                        if vmax <= vmin:
                            return np.zeros(arr.shape, dtype=np.uint8)
                    scaled = (arr - vmin) / (vmax - vmin)
                    scaled = np.clip(scaled, 0, 1)
                    return (scaled * 255).astype(np.uint8)

                r8 = norm_uint8(r_arr)
                g8 = norm_uint8(g_arr)
                b8 = norm_uint8(b_arr)
                alpha = (valid_mask.astype(np.uint8) * 255)

                rgba = np.dstack([r8, g8, b8, alpha])
                Image.fromarray(rgba, mode="RGBA").save(output_path, "PNG", optimize=True)
                return True, None

        except Exception as e_rio:
            rio_err = f"Rasterio preview failed: {type(e_rio).__name__}: {e_rio}"
            print("❌", rio_err)

        # Attempt 2: GDAL fallback (if available)
        if GDAL_AVAILABLE:
            try:
                ds = gdal.Open(filepath)
                if ds is None:
                    return False, "GDAL could not open the dataset"

                w = ds.RasterXSize
                h = ds.RasterYSize
                if w <= 0 or h <= 0:
                    return False, f"GDAL invalid raster dimensions: {w}x{h}"

                scale = min(max_size / w, max_size / h, 1.0)
                out_w = max(1, int(w * scale))
                out_h = max(1, int(h * scale))

                opts = gdal.TranslateOptions(format="PNG", width=out_w, height=out_h)
                gdal.Translate(output_path, ds, options=opts)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return True, None
                return False, "GDAL fallback produced empty output"

            except Exception as e_gdal:
                gdal_err = f"GDAL preview failed: {type(e_gdal).__name__}: {e_gdal}"
                print("❌", gdal_err)
                return False, gdal_err

        return False, "Preview failed (Rasterio failed; GDAL not available)"

    @staticmethod
    def _reproject_to(src_path, dst_path, dst_crs):
        """Reproject a raster to dst_crs and write to dst_path."""
        with rasterio.open(src_path) as src:
            if src.crs is None:
                raise RuntimeError(f"Missing CRS: {os.path.basename(src_path)}")

            transform, width, height = calculate_default_transform(
                src.crs, dst_crs,
                src.width, src.height,
                *src.bounds
            )

            meta = src.meta.copy()
            meta.update({
                "crs": dst_crs,
                "transform": transform,
                "width": width,
                "height": height,
                "compress": "lzw",
                "tiled": True,
                "BIGTIFF": "IF_SAFER"
            })

            with rasterio.open(dst_path, "w", **meta) as dst:
                for i in range(1, src.count + 1):
                    reproject(
                        source=rasterio.band(src, i),
                        destination=rasterio.band(dst, i),
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=transform,
                        dst_crs=dst_crs,
                        resampling=ResamplingEnum.nearest
                    )

        return dst_path

    @staticmethod
    def merge_tiffs(input_files, output_file):
        """Merge multiple TIFF files. Supports mixed CRS by reprojection."""
        if not RASTERIO_AVAILABLE:
            return False, "rasterio not available"

        if len(input_files) < 2:
            return False, "Need at least 2 input files"

        try:
            with rasterio.open(input_files[0]) as src0:
                target_crs = src0.crs
            if target_crs is None:
                return False, "First layer has no CRS; cannot merge"

            with tempfile.TemporaryDirectory() as tmpdir:
                prepared_files = []
                for p in input_files:
                    with rasterio.open(p) as s:
                        if s.crs is None:
                            return False, f"Layer missing CRS; cannot merge: {os.path.basename(p)}"
                        same = (s.crs == target_crs)

                    if same:
                        prepared_files.append(p)
                    else:
                        rp = os.path.join(tmpdir, f"reproj_{uuid.uuid4().hex}.tif")
                        TIFFProcessor._reproject_to(p, rp, target_crs)
                        prepared_files.append(rp)

                src_files = [rasterio.open(f) for f in prepared_files]
                try:
                    mosaic, out_transform = merge(src_files)
                    out_meta = src_files[0].meta.copy()
                    out_meta.update({
                        "driver": "GTiff",
                        "height": mosaic.shape[1],
                        "width": mosaic.shape[2],
                        "transform": out_transform,
                        "count": mosaic.shape[0],
                        "compress": "lzw",
                        "tiled": True,
                        "BIGTIFF": "IF_SAFER"
                    })

                    with rasterio.open(output_file, "w", **out_meta) as dest:
                        dest.write(mosaic)

                finally:
                    for src in src_files:
                        try:
                            src.close()
                        except Exception:
                            pass

            return True, "Merge successful"

        except Exception as e:
            return False, str(e)


# Flask routes
@app.route('/')
def index():
    """Serve main page"""
    return render_template_string(
        HTML_TEMPLATE,
        gdal_available=GDAL_AVAILABLE,
        rasterio_available=RASTERIO_AVAILABLE
    )


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})

    if not file.filename.lower().endswith(('.tif', '.tiff')):
        return jsonify({'success': False, 'error': 'Not a TIFF file'})

    if not RASTERIO_AVAILABLE:
        return jsonify({'success': False, 'error': 'rasterio not installed. Install: pip install rasterio'})

    try:
        original_name = secure_filename(file.filename)
        layer_id = f"layer_{uuid.uuid4().hex}"

        # Store with unique name to prevent overwrites
        stored_name = f"{layer_id}_{original_name}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_name)
        file.save(filepath)

        print(f"\n{'='*70}")
        print(f"Processing uploaded file: {original_name}")
        print(f"Stored as: {stored_name}")
        print(f"File path: {filepath}")
        print(f"File size: {os.path.getsize(filepath) / (1024*1024):.2f} MB")
        print(f"{'='*70}")

        info = TIFFProcessor.get_tiff_info(filepath)
        if info['width'] is None or info['height'] is None:
            return jsonify({'success': False, 'error': 'Could not read TIFF dimensions'})

        preview_filename = f"{layer_id}_preview.png"
        preview_path = os.path.join(app.config['OUTPUT_FOLDER'], preview_filename)

        print("\nCreating preview...")
        ok, preview_err = TIFFProcessor.create_preview(filepath, preview_path)
        if not ok:
            return jsonify({'success': False, 'error': f'Failed to create preview image: {preview_err}'})

        if not os.path.exists(preview_path) or os.path.getsize(preview_path) == 0:
            return jsonify({'success': False, 'error': 'Preview file missing or empty'})

        layer = {
            'id': layer_id,
            'filename': original_name,
            'filepath': filepath,
            'width': info['width'],
            'height': info['height'],
            'bounds': info['bounds'],     # may be None (UI handles it)
            'crs': info['crs'],
            'preview_url': f'/preview/{preview_filename}?t={int(time.time())}'
        }

        LAYER_REGISTRY[layer_id] = {
            "filepath": filepath,
            "filename": original_name,
            "preview_filename": preview_filename,
            "uploaded_at": int(time.time()),
            "crs": info['crs']
        }
        _save_registry()

        print("✓ Upload successful!")
        print(f" Layer ID: {layer_id}")
        print(f" Preview URL: {layer['preview_url']}")
        print(f" Bounds (WGS84): {layer['bounds']}")
        print(f"{'='*70}\n")

        return jsonify({'success': True, 'layer': layer})

    except Exception as e:
        print(f"\n{'!'*70}")
        print(f"ERROR during upload: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'!'*70}\n")
        return jsonify({'success': False, 'error': f'Upload error: {str(e)}'})


@app.route('/merge', methods=['POST'])
def merge_layers():
    """Merge selected TIFF layers (by layer_ids)"""
    if not RASTERIO_AVAILABLE:
        return jsonify({'success': False, 'error': 'rasterio not installed. Install: pip install rasterio'})

    data = request.get_json(silent=True) or {}
    layer_ids = data.get('layer_ids', [])

    if len(layer_ids) < 2:
        return jsonify({'success': False, 'error': 'Need at least 2 layers'})

    try:
        input_files = []
        missing = []
        for lid in layer_ids:
            rec = LAYER_REGISTRY.get(lid)
            if not rec:
                missing.append(lid)
                continue
            fp = rec.get("filepath")
            if not fp or not os.path.exists(fp):
                missing.append(lid)
                continue
            input_files.append(fp)

        if missing:
            return jsonify({'success': False, 'error': f"Missing layer files for: {missing}"}), 404

        out_name = f"merged_{int(time.time())}_{uuid.uuid4().hex[:8]}.tif"
        output_file = os.path.join(app.config['OUTPUT_FOLDER'], out_name)

        success, message = TIFFProcessor.merge_tiffs(input_files, output_file)
        if not success:
            return jsonify({'success': False, 'error': message})

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            return jsonify({'success': False, 'error': 'Merged output missing or empty'})

        return jsonify({
            'success': True,
            'output_file': output_file,
            'download_url': f'/download/{out_name}'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/preview/<filename>')
def serve_preview(filename):
    """Serve preview images"""
    try:
        safe = secure_filename(filename)
        filepath = os.path.join(app.config['OUTPUT_FOLDER'], safe)

        if not os.path.exists(filepath):
            return "Preview not found", 404

        return send_file(
            filepath,
            mimetype='image/png',
            as_attachment=False,
            download_name=safe
        )
    except Exception as e:
        print(f"ERROR serving preview: {e}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500


@app.route('/download/<filename>')
def download_file(filename):
    """Download merged TIFF"""
    safe = secure_filename(filename)
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], safe)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=safe, mimetype="image/tiff")
    return "Not found", 404


if __name__ == '__main__':
    print("=" * 70)
    print("GeoTIFF Processing Web Application")
    print("=" * 70)
    print("\n✓ Flask server starting...")
    print(f"✓ GDAL Available: {GDAL_AVAILABLE}")
    print(f"✓ Rasterio Available: {RASTERIO_AVAILABLE}")
    print(f"\n📂 Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"📂 Output folder: {app.config['OUTPUT_FOLDER']}")
    print("\n🌐 Open browser to: http://localhost:5000")
    print("=" * 70)
    app.run(host='0.0.0.0', port=5000, debug=True)
