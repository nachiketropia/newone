#!/usr/bin/env python3
"""
Complete ODM Structure Merger - Enhanced Version
Merges multiple OpenDroneMap output folders with complete file handling
"""

import os
import json
import shutil
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from collections import defaultdict

class ODMStructureMerger:
    """Merge multiple complete ODM output folders"""
    
    def __init__(self, source_folders, output_folder):
        self.source_folders = [Path(f).resolve() for f in source_folders]
        self.output_folder = Path(output_folder).resolve()
        
        # Validate source folders
        for folder in self.source_folders:
            if not folder.exists():
                raise FileNotFoundError(f"Source folder not found: {folder}")
        
        # Create output structure
        self.create_output_structure()
        self.check_dependencies()
        
        # Track all processed files
        self.processed_files = set()
        self.skipped_files = []
        
    def create_output_structure(self):
        """Create the complete ODM folder structure"""
        folders = [
            self.output_folder,
            self.output_folder / "entwine_pointcloud",
            self.output_folder / "entwine_pointcloud" / "ept-data",
            self.output_folder / "entwine_pointcloud" / "ept-hierarchy",
            self.output_folder / "entwine_pointcloud" / "ept-sources",
            self.output_folder / "odm_dem",
            self.output_folder / "odm_georeferencing",
            self.output_folder / "odm_orthophoto",
            self.output_folder / "odm_report",
            self.output_folder / "odm_report" / "camera_mappings",
            self.output_folder / "odm_texturing",
            self.output_folder / "odm_texturing" / "textures"
        ]
        
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
    
    def check_dependencies(self):
        """Check available tools"""
        self.tools = {
            'pdal': self._check_command('pdal'),
            'laspy': self._check_python_module('laspy'),
            'rasterio': self._check_python_module('rasterio'),
            'gdal': self._check_command('gdal_merge.py'),
            'numpy': self._check_python_module('numpy')
        }
        
        print("Available tools:")
        for tool, available in self.tools.items():
            status = "✓" if available else "✗"
            print(f"  {status} {tool}")
        print()
    
    def _check_command(self, cmd):
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _check_python_module(self, module):
        try:
            __import__(module)
            return True
        except ImportError:
            return False
    
    def merge_entwine_pointcloud(self):
        """Merge Entwine point cloud folders"""
        print(f"\n{'='*70}")
        print("MERGING ENTWINE POINT CLOUDS")
        print(f"{'='*70}")
        
        # 1. Merge EPT-DATA (LAZ files)
        all_laz_files = []
        for source in self.source_folders:
            ept_data = source / "entwine_pointcloud" / "ept-data"
            if ept_data.exists():
                laz_files = list(ept_data.glob("*.laz"))
                all_laz_files.extend([(laz, source.name) for laz in laz_files])
                print(f"  Found {len(laz_files)} LAZ files in {source.name}")
        
        if all_laz_files:
            output_ept_data = self.output_folder / "entwine_pointcloud" / "ept-data"
            for laz_file, source_name in all_laz_files:
                # Keep original names but track source in hierarchy
                dest = output_ept_data / laz_file.name
                # If duplicate, add source prefix
                if dest.exists():
                    dest = output_ept_data / f"{source_name}_{laz_file.name}"
                shutil.copy2(laz_file, dest)
            print(f"  ✓ Copied {len(all_laz_files)} LAZ files")
        
        # 2. Merge EPT-HIERARCHY (JSON files with tile counts)
        self._merge_ept_hierarchy()
        
        # 3. Merge EPT-SOURCES
        self._merge_ept_sources()
        
        # 4. Merge EPT JSON files
        self._merge_ept_json()
        self._merge_ept_build_json()
        
        return True
    
    def _merge_ept_hierarchy(self):
        """Merge Entwine hierarchy JSON files (tile index with point counts)"""
        print("  Merging EPT hierarchy...")
        
        all_tiles = {}
        
        for source in self.source_folders:
            hierarchy_dir = source / "entwine_pointcloud" / "ept-hierarchy"
            if hierarchy_dir.exists():
                for json_file in hierarchy_dir.glob("*.json"):
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        # Merge tile counts - sum if duplicate tiles
                        for tile_name, point_count in data.items():
                            if tile_name in all_tiles:
                                all_tiles[tile_name] += point_count
                            else:
                                all_tiles[tile_name] = point_count
        
        if all_tiles:
            output_hierarchy = self.output_folder / "entwine_pointcloud" / "ept-hierarchy"
            output_file = output_hierarchy / "0-0-0-0.json"
            
            with open(output_file, 'w') as f:
                json.dump(all_tiles, f, indent=2)
            
            print(f"  ✓ Merged hierarchy: {len(all_tiles)} tiles, {sum(all_tiles.values()):,} total points")
    
    def _merge_ept_sources(self):
        """Merge EPT sources (manifest.json and metadata)"""
        print("  Merging EPT sources...")
        
        # Merge manifest.json (array of datasets)
        all_manifests = []
        
        for source in self.source_folders:
            manifest_file = source / "entwine_pointcloud" / "ept-sources" / "manifest.json"
            if manifest_file.exists():
                with open(manifest_file, 'r') as f:
                    manifest_data = json.load(f)
                    # manifest.json is an array
                    if isinstance(manifest_data, list):
                        all_manifests.extend(manifest_data)
                    else:
                        all_manifests.append(manifest_data)
        
        if all_manifests:
            output_manifest = self.output_folder / "entwine_pointcloud" / "ept-sources" / "manifest.json"
            with open(output_manifest, 'w') as f:
                json.dump(all_manifests, f, indent=2)
            print(f"  ✓ Merged manifest.json: {len(all_manifests)} datasets")
        
        # Merge odm_georeferenced_model.json from ept-sources
        all_georef_data = []
        
        for source in self.source_folders:
            georef_file = source / "entwine_pointcloud" / "ept-sources" / "odm_georeferenced_model.json"
            if georef_file.exists():
                with open(georef_file, 'r') as f:
                    data = json.load(f)
                    all_georef_data.append({
                        "source": source.name,
                        "data": data
                    })
        
        if all_georef_data:
            output_georef = self.output_folder / "entwine_pointcloud" / "ept-sources" / "odm_georeferenced_model.json"
            
            # If all have same structure, merge intelligently
            if len(all_georef_data) == 1:
                merged = all_georef_data[0]["data"]
            else:
                # Combine with source attribution
                merged = {
                    "merged_from": len(all_georef_data),
                    "datasets": all_georef_data
                }
            
            with open(output_georef, 'w') as f:
                json.dump(merged, f, indent=2)
            print(f"  ✓ Merged odm_georeferenced_model.json")
    
    def _merge_ept_json(self):
        """Merge ept.json files"""
        ept_jsons = []
        
        for source in self.source_folders:
            ept_json = source / "entwine_pointcloud" / "ept.json"
            if ept_json.exists():
                with open(ept_json, 'r') as f:
                    ept_jsons.append(json.load(f))
        
        if ept_jsons:
            merged = ept_jsons[0].copy()
            
            # Calculate combined bounds (min/max of all)
            if 'bounds' in merged:
                all_bounds = [ept['bounds'] for ept in ept_jsons if 'bounds' in ept]
                if all_bounds:
                    merged['bounds'] = [
                        min(b[0] for b in all_bounds),  # min X
                        min(b[1] for b in all_bounds),  # min Y
                        min(b[2] for b in all_bounds),  # min Z
                        max(b[3] for b in all_bounds),  # max X
                        max(b[4] for b in all_bounds),  # max Y
                        max(b[5] for b in all_bounds)   # max Z
                    ]
            
            # Sum point counts
            if 'points' in merged:
                merged['points'] = sum(ept.get('points', 0) for ept in ept_jsons)
            
            # Combine SRS if different
            all_srs = [ept.get('srs', {}) for ept in ept_jsons]
            if all_srs:
                merged['srs'] = all_srs[0]  # Use first, should be same
            
            output_json = self.output_folder / "entwine_pointcloud" / "ept.json"
            with open(output_json, 'w') as f:
                json.dump(merged, f, indent=2)
            
            print(f"  ✓ Merged ept.json")
    
    def _merge_ept_build_json(self):
        """Merge ept-build.json files"""
        build_jsons = []
        
        for source in self.source_folders:
            build_json = source / "entwine_pointcloud" / "ept-build.json"
            if build_json.exists():
                with open(build_json, 'r') as f:
                    build_jsons.append(json.load(f))
        
        if build_jsons:
            # Combine build information
            merged = {
                "merged": True,
                "merge_date": datetime.now().isoformat(),
                "source_builds": build_jsons
            }
            
            output_json = self.output_folder / "entwine_pointcloud" / "ept-build.json"
            with open(output_json, 'w') as f:
                json.dump(merged, f, indent=2)
    
    def merge_odm_dem(self):
        """Merge DEM files (DSM and DTM)"""
        print(f"\n{'='*70}")
        print("MERGING DEM FILES")
        print(f"{'='*70}")
        
        for dem_type in ['dsm.tif', 'dtm.tif']:
            dem_files = []
            
            for source in self.source_folders:
                dem_file = source / "odm_dem" / dem_type
                if dem_file.exists():
                    dem_files.append(dem_file)
                    
                    # Also copy aux.xml if exists
                    aux_file = source / "odm_dem" / f"{dem_type}.aux.xml"
                    if aux_file.exists():
                        self.processed_files.add(str(aux_file))
            
            if dem_files:
                output_file = self.output_folder / "odm_dem" / dem_type
                
                if self.tools['gdal']:
                    self._merge_rasters_gdal(dem_files, output_file, dem_type)
                elif self.tools['rasterio']:
                    self._merge_rasters_rasterio(dem_files, output_file, dem_type)
                else:
                    print(f"  ⚠ Cannot merge {dem_type} - copying first file only")
                    shutil.copy2(dem_files[0], output_file)
        
        return True
    
    def _merge_rasters_gdal(self, raster_files, output_file, name):
        """Merge rasters using GDAL"""
        cmd = ['gdal_merge.py', '-o', str(output_file), '-co', 'COMPRESS=LZW']
        cmd.extend([str(r) for r in raster_files])
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"  ✓ Merged {name} using GDAL")
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ✗ GDAL error for {name}: {e.stderr}")
            return False
    
    def _merge_rasters_rasterio(self, raster_files, output_file, name):
        """Merge rasters using rasterio"""
        try:
            import rasterio
            from rasterio.merge import merge
            
            src_files = [rasterio.open(str(r)) for r in raster_files]
            mosaic, out_trans = merge(src_files)
            
            out_meta = src_files[0].meta.copy()
            out_meta.update({
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans,
                "compress": "lzw"
            })
            
            with rasterio.open(output_file, "w", **out_meta) as dest:
                dest.write(mosaic)
            
            for src in src_files:
                src.close()
            
            print(f"  ✓ Merged {name} using rasterio")
            return True
        except Exception as e:
            print(f"  ✗ Error merging {name}: {e}")
            return False
    
    def merge_odm_georeferencing(self):
        """Merge georeferencing data"""
        print(f"\n{'='*70}")
        print("MERGING GEOREFERENCING DATA")
        print(f"{'='*70}")
        
        # 1. Merge LAZ point clouds
        laz_files = []
        for source in self.source_folders:
            laz = source / "odm_georeferencing" / "odm_georeferenced_model.laz"
            if laz.exists():
                laz_files.append(laz)
        
        if laz_files:
            output_laz = self.output_folder / "odm_georeferencing" / "odm_georeferenced_model.laz"
            self._merge_pointclouds(laz_files, output_laz)
        
        # 2. Merge bounds files
        self._merge_bounds_geojson()
        self._merge_bounds_gpkg()
        
        # 3. Merge boundary JSON
        self._merge_boundary_json()
        
        # 4. Merge coords.txt
        self._merge_coords_txt()
        
        # 5. Copy projection files (same for all)
        for source in self.source_folders:
            proj_file = source / "odm_georeferencing" / "proj.txt"
            if proj_file.exists():
                shutil.copy2(proj_file, self.output_folder / "odm_georeferencing" / "proj.txt")
                break
            
            geo_txt = source / "odm_georeferencing" / "odm_georeferencing_model_geo.txt"
            if geo_txt.exists():
                shutil.copy2(geo_txt, self.output_folder / "odm_georeferencing" / "odm_georeferencing_model_geo.txt")
                break
        
        # 6. Copy pc_classify_done.txt
        for source in self.source_folders:
            pc_classify = source / "odm_georeferencing" / "pc_classify_done.txt"
            if pc_classify.exists():
                shutil.copy2(pc_classify, self.output_folder / "odm_georeferencing" / "pc_classify_done.txt")
                break
        
        # 7. Merge all JSON files
        self._merge_georef_jsons()
        
        return True
    
    def _merge_pointclouds(self, pc_files, output_file):
        """Merge point cloud files"""
        if self.tools['pdal']:
            pipeline = {
                "pipeline": [str(pc) for pc in pc_files]
            }
            pipeline["pipeline"].append({"type": "filters.merge"})
            pipeline["pipeline"].append({
                "type": "writers.las",
                "filename": str(output_file),
                "compression": "true"
            })
            
            pipeline_file = output_file.parent / "merge_pipeline.json"
            with open(pipeline_file, 'w') as f:
                json.dump(pipeline, f, indent=2)
            
            try:
                subprocess.run(['pdal', 'pipeline', str(pipeline_file)], 
                             capture_output=True, text=True, check=True)
                print(f"  ✓ Merged point cloud: {output_file.name}")
                pipeline_file.unlink()
                return True
            except subprocess.CalledProcessError as e:
                print(f"  ✗ PDAL error: {e.stderr}")
                return False
        
        elif self.tools['laspy']:
            try:
                import laspy
                
                all_points = []
                for pc_file in pc_files:
                    las = laspy.read(pc_file)
                    all_points.append(las)
                
                merged = laspy.merge(all_points)
                merged.write(output_file)
                
                print(f"  ✓ Merged point cloud: {output_file.name}")
                return True
            except Exception as e:
                print(f"  ✗ Error: {e}")
                return False
        else:
            print("  ⚠ No point cloud tools - copying first file only")
            shutil.copy2(pc_files[0], output_file)
            return False
    
    def _merge_bounds_geojson(self):
        """Merge bounds GeoJSON files"""
        all_features = []
        
        for source in self.source_folders:
            geojson_file = source / "odm_georeferencing" / "odm_georeferenced_model.bounds.geojson"
            if geojson_file.exists():
                with open(geojson_file, 'r') as f:
                    data = json.load(f)
                    if 'features' in data:
                        # Add source attribution to properties
                        for feature in data['features']:
                            if 'properties' not in feature:
                                feature['properties'] = {}
                            feature['properties']['source_dataset'] = source.name
                        all_features.extend(data['features'])
        
        if all_features:
            merged = {
                "type": "FeatureCollection",
                "features": all_features
            }
            
            output_file = self.output_folder / "odm_georeferencing" / "odm_georeferenced_model.bounds.geojson"
            with open(output_file, 'w') as f:
                json.dump(merged, f, indent=2)
            
            print("  ✓ Merged bounds.geojson")
    
    def _merge_bounds_gpkg(self):
        """Copy first bounds GPKG file"""
        for source in self.source_folders:
            gpkg_file = source / "odm_georeferencing" / "odm_georeferenced_model.bounds.gpkg"
            if gpkg_file.exists():
                output_file = self.output_folder / "odm_georeferencing" / "odm_georeferenced_model.bounds.gpkg"
                shutil.copy2(gpkg_file, output_file)
                print("  ✓ Copied bounds.gpkg (from first dataset)")
                break
    
    def _merge_boundary_json(self):
        """Merge boundary.json files"""
        all_boundaries = []
        
        for source in self.source_folders:
            boundary_file = source / "odm_georeferencing" / "odm_georeferenced_model.boundary.json"
            if boundary_file.exists():
                with open(boundary_file, 'r') as f:
                    data = json.load(f)
                    all_boundaries.append({
                        "source": source.name,
                        "boundary": data
                    })
        
        if all_boundaries:
            output_file = self.output_folder / "odm_georeferencing" / "odm_georeferenced_model.boundary.json"
            
            if len(all_boundaries) == 1:
                merged = all_boundaries[0]["boundary"]
            else:
                merged = {
                    "type": "MultiPolygon",
                    "datasets": all_boundaries
                }
            
            with open(output_file, 'w') as f:
                json.dump(merged, f, indent=2)
    
    def _merge_coords_txt(self):
        """Merge coords.txt files"""
        all_coords = []
        header_written = False
        
        for source in self.source_folders:
            coords_file = source / "odm_georeferencing" / "coords.txt"
            if coords_file.exists():
                with open(coords_file, 'r') as f:
                    lines = f.readlines()
                    if not header_written:
                        all_coords.extend(lines)
                        header_written = True
                    else:
                        # Skip header from subsequent files
                        data_lines = [l for l in lines if not l.startswith('#') and l.strip()]
                        all_coords.extend(data_lines)
        
        if all_coords:
            output_file = self.output_folder / "odm_georeferencing" / "coords.txt"
            with open(output_file, 'w') as f:
                f.writelines(all_coords)
            print("  ✓ Merged coords.txt")
    
    def _merge_georef_jsons(self):
        """Merge all georeferencing JSON files"""
        json_files = [
            'odm_georeferenced_model.info.json',
            'odm_georeferenced_model.summary.json'
        ]
        
        for json_name in json_files:
            all_data = []
            
            for source in self.source_folders:
                json_file = source / "odm_georeferencing" / json_name
                if json_file.exists():
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        all_data.append({
                            "source": source.name,
                            "data": data
                        })
            
            if all_data:
                output_file = self.output_folder / "odm_georeferencing" / json_name
                
                if len(all_data) == 1:
                    merged = all_data[0]["data"]
                else:
                    # Merge statistics
                    merged = {
                        "merged": True,
                        "datasets": all_data,
                        "combined_stats": {}
                    }
                    
                    # Try to sum point counts
                    total_points = 0
                    for item in all_data:
                        if 'points' in item["data"]:
                            total_points += item["data"]["points"]
                    
                    if total_points > 0:
                        merged["combined_stats"]["total_points"] = total_points
                
                with open(output_file, 'w') as f:
                    json.dump(merged, f, indent=2)
    
    def merge_odm_orthophoto(self):
        """Merge orthophoto"""
        print(f"\n{'='*70}")
        print("MERGING ORTHOPHOTOS")
        print(f"{'='*70}")
        
        ortho_files = []
        for source in self.source_folders:
            ortho = source / "odm_orthophoto" / "odm_orthophoto.tif"
            if ortho.exists():
                ortho_files.append(ortho)
        
        if ortho_files:
            output_file = self.output_folder / "odm_orthophoto" / "odm_orthophoto.tif"
            
            if self.tools['gdal']:
                self._merge_rasters_gdal(ortho_files, output_file, "orthophoto")
            elif self.tools['rasterio']:
                self._merge_rasters_rasterio(ortho_files, output_file, "orthophoto")
            else:
                print("  ⚠ No raster tools - copying first file")
                shutil.copy2(ortho_files[0], output_file)
            
            # Generate TFW file
            self._generate_tfw()
        
        # Copy DXF extent file
        for source in self.source_folders:
            dxf_file = source / "odm_orthophoto" / "odm_orthophoto_extent.dxf"
            if dxf_file.exists():
                shutil.copy2(dxf_file, self.output_folder / "odm_orthophoto" / "odm_orthophoto_extent.dxf")
                break
        
        return True
    
    def _generate_tfw(self):
        """Generate TFW world file from TIF"""
        try:
            import rasterio
            
            tif_file = self.output_folder / "odm_orthophoto" / "odm_orthophoto.tif"
            tfw_file = self.output_folder / "odm_orthophoto" / "odm_orthophoto.tfw"
            
            with rasterio.open(tif_file) as src:
                transform = src.transform
                
                with open(tfw_file, 'w') as f:
                    f.write(f"{transform.a}\n")
                    f.write(f"{transform.b}\n")
                    f.write(f"{transform.d}\n")
                    f.write(f"{transform.e}\n")
                    f.write(f"{transform.c}\n")
                    f.write(f"{transform.f}\n")
                
                print("  ✓ Generated odm_orthophoto.tfw")
        except:
            # Copy existing TFW if available
            for source in self.source_folders:
                tfw_file = source / "odm_orthophoto" / "odm_orthophoto.tfw"
                if tfw_file.exists():
                    shutil.copy2(tfw_file, self.output_folder / "odm_orthophoto" / "odm_orthophoto.tfw")
                    break
    
    def merge_odm_report(self):
        """Merge report data"""
        print(f"\n{'='*70}")
        print("MERGING REPORTS")
        print(f"{'='*70}")
        
        # Merge shots.geojson
        self._merge_shots_geojson()
        
        # Merge stats.json
        self._merge_stats_json()
        
        # Merge camera mapping files
        self._merge_camera_mappings()
        
        # Copy report PDFs with source names
        self._copy_reports()
        
        return True
    
    def _merge_shots_geojson(self):
        """Merge camera shots GeoJSON"""
        all_features = []
        
        for source in self.source_folders:
            shots_file = source / "odm_report" / "shots.geojson"
            if shots_file.exists():
                with open(shots_file, 'r') as f:
                    data = json.load(f)
                    if 'features' in data:
                        # Add source to properties
                        for feature in data['features']:
                            if 'properties' not in feature:
                                feature['properties'] = {}
                            feature['properties']['source_dataset'] = source.name
                        all_features.extend(data['features'])
        
        if all_features:
            merged = {
                "type": "FeatureCollection",
                "features": all_features
            }
            
            output_file = self.output_folder / "odm_report" / "shots.geojson"
            with open(output_file, 'w') as f:
                json.dump(merged, f, indent=2)
            
            print(f"  ✓ Merged shots.geojson ({len(all_features)} camera positions)")
    
    def _merge_stats_json(self):
        """Merge statistics"""
        all_stats = []
        
        for source in self.source_folders:
            stats_file = source / "odm_report" / "stats.json"
            if stats_file.exists():
                with open(stats_file, 'r') as f:
                    data = json.load(f)
                    all_stats.append({
                        "source": source.name,
                        "stats": data
                    })
        
        if all_stats:
            merged = {
                "merged_datasets": len(all_stats),
                "merge_date": datetime.now().isoformat(),
                "individual_stats": all_stats
            }
            
            output_file = self.output_folder / "odm_report" / "stats.json"
            with open(output_file, 'w') as f:
                json.dump(merged, f, indent=2)
            
            print("  ✓ Merged stats.json")
    
    def _merge_camera_mappings(self):
        """Merge camera mapping numpy files"""
        if not self.tools['numpy']:
            print("  ⚠ NumPy not available, skipping camera mappings")
            return
        
        try:
            import numpy as np
            
            output_dir = self.output_folder / "odm_report" / "camera_mappings"
            
            for npy_name in ['0_mul.npy', '0_offset.npy', '0_x.npy', '0_y.npy', 'ids.npy']:
                all_arrays = []
                
                for source in self.source_folders:
                    npy_file = source / "odm_report" / "camera_mappings" / npy_name
                    if npy_file.exists():
                        all_arrays.append(np.load(npy_file))
                
                if all_arrays:
                    if len(all_arrays) == 1:
                        merged = all_arrays[0]
                    else:
                        # Concatenate arrays along first axis
                        merged = np.concatenate(all_arrays, axis=0)
                    
                    output_file = output_dir / npy_name
                    np.save(output_file, merged)
            
            print("  ✓ Merged camera mappings")
        except Exception as e:
            print(f"  ⚠ Error merging camera mappings: {e}")
    
    def _copy_reports(self):
        """Copy report PDFs with source identification"""
        for i, source in enumerate(self.source_folders, 1):
            report_pdf = source / "odm_report" / "report.pdf"
            if report_pdf.exists():
                output_pdf = self.output_folder / "odm_report" / f"report_{source.name}.pdf"
                shutil.copy2(report_pdf, output_pdf)
        
        print(f"  ✓ Copied {len(self.source_folders)} individual reports")
    
    def merge_odm_texturing(self):
        """Merge 3D textured meshes"""
        print(f"\n{'='*70}")
        print("MERGING 3D MESHES")
        print(f"{'='*70}")
        
        mesh_data = []
        
        for source in self.source_folders:
            obj_file = source / "odm_texturing" / "odm_textured_model_geo.obj"
            if obj_file.exists():
                mesh_data.append((obj_file, source.name))
        
        if not mesh_data:
            print("  ⚠ No meshes found")
            return False
        
        # Also copy GLB files
        self._copy_glb_files()
        
        return self._merge_obj_meshes(mesh_data)
    
    def _copy_glb_files(self):
        """Copy GLB files with source names"""
        for source in self.source_folders:
            glb_file = source / "odm_texturing" / "odm_textured_model_geo.glb"
            if glb_file.exists():
                output_glb = self.output_folder / "odm_texturing" / f"odm_textured_model_geo_{source.name}.glb"
                shutil.copy2(glb_file, output_glb)
        
        # Also copy conf files
        for source in self.source_folders:
            conf_file = source / "odm_texturing" / "odm_textured_model_geo.conf"
            if conf_file.exists():
                shutil.copy2(conf_file, self.output_folder / "odm_texturing" / "odm_textured_model_geo.conf")
                break
    
    def _merge_obj_meshes(self, mesh_data):
        """Merge OBJ files with textures"""
        output_obj = self.output_folder / "odm_texturing" / "odm_textured_model_geo.obj"
        output_mtl = self.output_folder / "odm_texturing" / "odm_textured_model_geo.mtl"
        textures_folder = self.output_folder / "odm_texturing" / "textures"
        
        all_vertices = []
        all_normals = []
        all_texcoords = []
        all_faces = []
        all_materials = {}
        
        v_offset = 0
        vn_offset = 0
        vt_offset = 0
        
        for mesh_file, dataset_name in mesh_data:
            print(f"  Processing {dataset_name}...", end=' ')
            
            mat_prefix = f"{dataset_name}_"
            
            # Parse OBJ
            vertices, normals, texcoords, faces = self._parse_obj(mesh_file)
            
            # Parse MTL and copy textures
            mtl_file = mesh_file.with_suffix('.mtl')
            if mtl_file.exists():
                materials = self._parse_mtl(mtl_file, mesh_file.parent, 
                                           textures_folder, mat_prefix)
                all_materials.update(materials)
            
            # Add geometry with offsets
            all_vertices.extend(vertices)
            all_normals.extend(normals)
            all_texcoords.extend(texcoords)
            
            # Adjust face indices
            for face_verts, material in faces:
                adjusted = []
                for v_str in face_verts:
                    parts = v_str.split('/')
                    new_parts = [
                        str(int(parts[0]) + v_offset) if parts[0] else '',
                        str(int(parts[1]) + vt_offset) if len(parts) > 1 and parts[1] else '',
                        str(int(parts[2]) + vn_offset) if len(parts) > 2 and parts[2] else ''
                    ]
                    adjusted.append('/'.join(new_parts))
                all_faces.append((adjusted, mat_prefix + material if material else None))
            
            v_offset += len(vertices)
            vn_offset += len(normals)
            vt_offset += len(texcoords)
            
            print(f"✓ {len(vertices):,} vertices")
        
        # Write combined OBJ
        self._write_obj(output_obj, all_vertices, all_normals, all_texcoords, all_faces)
        self._write_mtl(output_mtl, all_materials)
        
        print(f"  ✓ Combined mesh: {len(all_vertices):,} vertices total")
        return True
    
    def _parse_obj(self, obj_file):
        """Parse OBJ file"""
        vertices, normals, texcoords, faces = [], [], [], []
        current_material = None
        
        with open(obj_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split(None, 1)
                if not parts:
                    continue
                
                cmd = parts[0]
                if cmd == 'v':
                    vertices.append([float(x) for x in parts[1].split()])
                elif cmd == 'vn':
                    normals.append([float(x) for x in parts[1].split()])
                elif cmd == 'vt':
                    texcoords.append([float(x) for x in parts[1].split()])
                elif cmd == 'f':
                    faces.append((parts[1].split(), current_material))
                elif cmd == 'usemtl':
                    current_material = parts[1] if len(parts) > 1 else None
        
        return vertices, normals, texcoords, faces
    
    def _parse_mtl(self, mtl_file, source_folder, dest_folder, prefix):
        """Parse MTL and copy textures"""
        materials = {}
        current_mat = None
        
        with open(mtl_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split(None, 1)
                if parts[0] == 'newmtl':
                    current_mat = prefix + parts[1]
                    materials[current_mat] = []
                elif current_mat and parts[0].startswith('map_'):
                    texture_file = parts[1]
                    src = source_folder / texture_file
                    if src.exists():
                        dst = dest_folder / f"{prefix}{texture_file}"
                        shutil.copy2(src, dst)
                        materials[current_mat].append((parts[0], f"textures/{prefix}{texture_file}"))
                elif current_mat:
                    materials[current_mat].append(line)
        
        return materials
    
    def _write_obj(self, output_file, vertices, normals, texcoords, faces):
        """Write OBJ file"""
        with open(output_file, 'w') as f:
            f.write("# Combined ODM Textured Mesh\n")
            f.write(f"# Merged from {len(self.source_folders)} datasets\n")
            f.write(f"mtllib odm_textured_model_geo.mtl\n\n")
            
            for v in vertices:
                f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
            
            if texcoords:
                f.write("\n")
                for vt in texcoords:
                    f.write(f"vt {vt[0]:.6f} {vt[1]:.6f}\n")
            
            if normals:
                f.write("\n")
                for vn in normals:
                    f.write(f"vn {vn[0]:.6f} {vn[1]:.6f} {vn[2]:.6f}\n")
            
            f.write("\n")
            current_mat = None
            for face_verts, material in faces:
                if material != current_mat:
                    f.write(f"\nusemtl {material}\n")
                    current_mat = material
                f.write(f"f {' '.join(face_verts)}\n")
    
    def _write_mtl(self, output_file, materials):
        """Write MTL file"""
        with open(output_file, 'w') as f:
            f.write("# Combined Material Library\n\n")
            for mat_name, props in materials.items():
                f.write(f"newmtl {mat_name}\n")
                for prop in props:
                    if isinstance(prop, tuple):
                        f.write(f"{prop[0]} {prop[1]}\n")
                    else:
                        f.write(f"{prop}\n")
                f.write("\n")
    
    def merge_root_files(self):
        """Merge root-level JSON files"""
        print(f"\n{'='*70}")
        print("MERGING ROOT FILES")
        print(f"{'='*70}")
        
        # Merge cameras.json
        self._merge_cameras_json()
        
        # Merge images.json
        self._merge_images_json()
        
        # Merge logs
        self._merge_logs()
        
        # Copy task_output.txt
        self._merge_task_outputs()
        
        return True
    
    def _merge_cameras_json(self):
        """Merge camera calibration data"""
        all_cameras = []
        
        for source in self.source_folders:
            cameras_file = source / "cameras.json"
            if cameras_file.exists():
                with open(cameras_file, 'r') as f:
                    data = json.load(f)
                    all_cameras.append({
                        "source": source.name,
                        "cameras": data
                    })
        
        if all_cameras:
            if len(all_cameras) == 1:
                merged = all_cameras[0]["cameras"]
            else:
                merged = {
                    "merged": True,
                    "datasets": all_cameras
                }
            
            output_file = self.output_folder / "cameras.json"
            with open(output_file, 'w') as f:
                json.dump(merged, f, indent=2)
            
            print("  ✓ Merged cameras.json")
    
    def _merge_images_json(self):
        """Merge image metadata"""
        all_images = []
        
        for source in self.source_folders:
            images_file = source / "images.json"
            if images_file.exists():
                with open(images_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_images.extend(data)
                    else:
                        all_images.append(data)
        
        if all_images:
            output_file = self.output_folder / "images.json"
            with open(output_file, 'w') as f:
                json.dump(all_images, f, indent=2)
            
            print(f"  ✓ Merged images.json ({len(all_images)} images)")
    
    def _merge_logs(self):
        """Merge log files"""
        all_logs = []
        
        for source in self.source_folders:
            log_file = source / "log.json"
            if log_file.exists():
                with open(log_file, 'r') as f:
                    try:
                        data = json.load(f)
                        all_logs.append({
                            "source": source.name,
                            "log": data
                        })
                    except:
                        pass
        
        if all_logs:
            output_file = self.output_folder / "log.json"
            with open(output_file, 'w') as f:
                json.dump(all_logs, f, indent=2)
            
            print("  ✓ Merged log.json")
    
    def _merge_task_outputs(self):
        """Merge task output text files"""
        all_outputs = []
        
        for source in self.source_folders:
            task_file = source / "task_output.txt"
            if task_file.exists():
                with open(task_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    all_outputs.append(f"\n{'='*70}\n")
                    all_outputs.append(f"SOURCE: {source.name}\n")
                    all_outputs.append(f"{'='*70}\n\n")
                    all_outputs.append(content)
        
        if all_outputs:
            output_file = self.output_folder / "task_output.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.writelines(all_outputs)
            
            print("  ✓ Merged task_output.txt")
    
    def create_completion_marker(self):
        """Create a completion marker file"""
        marker_file = self.output_folder / "complete_structure.txt"
        
        with open(marker_file, 'w') as f:
            f.write("COMBINED ODM STRUCTURE - MERGE COMPLETE\n")
            f.write("="*70 + "\n\n")
            f.write(f"Merge Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Source Datasets: {len(self.source_folders)}\n\n")
            
            for i, source in enumerate(self.source_folders, 1):
                f.write(f"  {i}. {source.name}\n")
            
            f.write("\n" + "="*70 + "\n")
            f.write("All data has been merged into this combined structure.\n")
        
        print(f"\n  ✓ Created completion marker")
    
    def run(self):
        """Execute complete merge"""
        print("="*70)
        print("ODM COMPLETE STRUCTURE MERGER - ENHANCED")
        print("="*70)
        print(f"\nSource folders:")
        for i, folder in enumerate(self.source_folders, 1):
            print(f"  {i}. {folder}")
        print(f"\nOutput folder: {self.output_folder}\n")
        
        # Execute all merge operations
        operations = [
            ("Root Files", self.merge_root_files),
            ("Entwine Point Cloud", self.merge_entwine_pointcloud),
            ("DEM", self.merge_odm_dem),
            ("Georeferencing", self.merge_odm_georeferencing),
            ("Orthophoto", self.merge_odm_orthophoto),
            ("Report", self.merge_odm_report),
            ("3D Mesh", self.merge_odm_texturing)
        ]
        
        results = []
        for name, operation in operations:
            try:
                result = operation()
                results.append((name, result))
            except Exception as e:
                print(f"\n✗ Error in {name}: {e}")
                import traceback
                traceback.print_exc()
                results.append((name, False))
        
        # Create completion marker
        self.create_completion_marker()
        
        # Summary
        print("\n" + "="*70)
        print("MERGE SUMMARY")
        print("="*70)
        
        for name, result in results:
            status = "✓" if result else "✗"
            print(f"  {status} {name}")
        
        successful = sum(1 for _, r in results if r)
        print(f"\n  {successful}/{len(results)} operations completed")
        print(f"\n  📁 Output: {self.output_folder}")
        print(f"  ✅ Merge complete! Check 'complete_structure.txt' for details.")
        print("="*70)
        
        return successful > 0


def main():
    if len(sys.argv) < 3:
        print("Usage: python odm_merger.py <source1> <source2> [source3...] <output>")
        print("\nExample:")
        print("  python odm_merger.py dataset1 dataset2 combined_output")
        print("\nYou can merge 2 or more datasets.")
        sys.exit(1)
    
    source_folders = sys.argv[1:-1]
    output_folder = sys.argv[-1]
    
    try:
        merger = ODMStructureMerger(source_folders, output_folder)
        success = merger.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.