#!/usr/bin/env python3
"""
Complete ODM Dataset Merger
Combines multiple OpenDroneMap datasets using point clouds, meshes, or orthophotos
"""

import os
import json
import shutil
from pathlib import Path
import subprocess
import sys

class ODMDatasetMerger:
    """Merge multiple ODM datasets"""
    
    def __init__(self, mother_folder):
        self.mother_folder = Path(mother_folder).resolve()
        if not self.mother_folder.exists():
            raise FileNotFoundError(f"MotherFolder not found: {self.mother_folder}")
        
        self.output_folder = self.mother_folder / "combined_output"
        self.output_folder.mkdir(exist_ok=True)
        
        # Check available tools
        self.check_dependencies()
    
    def check_dependencies(self):
        """Check what tools are available"""
        self.tools = {
            'pdal': self._check_command('pdal'),
            'laspy': self._check_python_module('laspy'),
            'rasterio': self._check_python_module('rasterio'),
            'gdal': self._check_command('gdal_merge.py')
        }
        
        print("Available tools:")
        for tool, available in self.tools.items():
            status = "✓" if available else "✗"
            print(f"  {status} {tool}")
        print()
    
    def _check_command(self, cmd):
        """Check if command exists"""
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _check_python_module(self, module):
        """Check if Python module exists"""
        try:
            __import__(module)
            return True
        except ImportError:
            return False
    
    def find_datasets(self):
        """Find all dataset folders"""
        datasets = []
        for item in self.mother_folder.iterdir():
            if item.is_dir() and item.name.startswith('dataset_'):
                # Check if it has ODM output structure
                has_odm = any([
                    (item / 'odm_georeferencing').exists(),
                    (item / 'georeferences').exists(),
                    (item / 'odm_texturing').exists(),
                    (item / 'orthophoto').exists()
                ])
                if has_odm:
                    datasets.append(item)
        return sorted(datasets)
    
    def analyze_dataset(self, dataset):
        """Analyze what data is available in a dataset"""
        info = {
            'name': dataset.name,
            'path': dataset,
            'has_pointcloud': False,
            'has_mesh': False,
            'has_orthophoto': False,
            'has_dem': False,
            'pointcloud_file': None,
            'mesh_file': None,
            'orthophoto_file': None,
            'dem_files': []
        }
        
        # Check for georeferenced point cloud
        pc_paths = [
            dataset / 'odm_georeferencing' / 'odm_georeferenced_model.laz',
            dataset / 'georeferences' / 'odm_georeferenced_model.laz'
        ]
        for pc_path in pc_paths:
            if pc_path.exists():
                info['has_pointcloud'] = True
                info['pointcloud_file'] = pc_path
                break
        
        # Check for textured mesh
        mesh_paths = [
            dataset / 'odm_texturing' / 'odm_textured_model_geo.obj',
            dataset / 'odm_texturing' / 'odm_textured_model.obj'
        ]
        for mesh_path in mesh_paths:
            if mesh_path.exists():
                info['has_mesh'] = True
                info['mesh_file'] = mesh_path
                break
        
        # Check for orthophoto
        ortho_path = dataset / 'orthophoto' / 'odm_orthophoto.tif'
        if ortho_path.exists():
            info['has_orthophoto'] = True
            info['orthophoto_file'] = ortho_path
        
        # Check for DEM
        dem_folder = dataset / 'odm_dem'
        if dem_folder.exists():
            for dem_file in ['dsm.tif', 'dtm.tif']:
                dem_path = dem_folder / dem_file
                if dem_path.exists():
                    info['has_dem'] = True
                    info['dem_files'].append(dem_path)
        
        return info
    
    def merge_point_clouds(self, datasets_info):
        """Merge point clouds from multiple datasets"""
        point_clouds = [d['pointcloud_file'] for d in datasets_info if d['has_pointcloud']]
        
        if not point_clouds:
            print("⚠ No point clouds found to merge")
            return False
        
        print(f"\n{'='*70}")
        print(f"MERGING POINT CLOUDS ({len(point_clouds)} files)")
        print(f"{'='*70}")
        
        output_laz = self.output_folder / "combined_pointcloud.laz"
        
        # Try PDAL first (best method)
        if self.tools['pdal']:
            return self._merge_with_pdal(point_clouds, output_laz)
        # Fallback to laspy
        elif self.tools['laspy']:
            return self._merge_with_laspy(point_clouds, output_laz)
        else:
            print("✗ No point cloud merging tools available")
            print("  Install: pip install pdal laspy[lazrs]")
            return False
    
    def _merge_with_pdal(self, point_clouds, output_file):
        """Merge using PDAL"""
        print("Using PDAL for merging...")
        
        pipeline = {
            "pipeline": [str(pc) for pc in point_clouds]
        }
        pipeline["pipeline"].append({"type": "filters.merge"})
        pipeline["pipeline"].append({
            "type": "writers.las",
            "filename": str(output_file),
            "compression": "true"
        })
        
        pipeline_file = self.output_folder / "merge_pipeline.json"
        with open(pipeline_file, 'w') as f:
            json.dump(pipeline, f, indent=2)
        
        try:
            subprocess.run(['pdal', 'pipeline', str(pipeline_file)], 
                         capture_output=True, text=True, check=True)
            print(f"✓ Combined point cloud: {output_file}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ PDAL error: {e.stderr}")
            return False
    
    def _merge_with_laspy(self, point_clouds, output_file):
        """Merge using laspy"""
        print("Using laspy for merging...")
        
        try:
            import laspy
            
            all_points = []
            for pc_file in point_clouds:
                print(f"  Reading {pc_file.parent.parent.name}...", end=' ')
                las = laspy.read(pc_file)
                all_points.append(las)
                print(f"✓ {len(las.points):,} points")
            
            print("  Merging...")
            merged = laspy.merge(all_points)
            
            print(f"  Writing {len(merged.points):,} points...")
            merged.write(output_file)
            
            print(f"✓ Combined point cloud: {output_file}")
            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            return False
    
    def merge_orthophotos(self, datasets_info):
        """Merge orthophotos from multiple datasets"""
        orthophotos = [d['orthophoto_file'] for d in datasets_info if d['has_orthophoto']]
        
        if not orthophotos:
            print("⚠ No orthophotos found to merge")
            return False
        
        print(f"\n{'='*70}")
        print(f"MERGING ORTHOPHOTOS ({len(orthophotos)} files)")
        print(f"{'='*70}")
        
        output_tif = self.output_folder / "combined_orthophoto.tif"
        
        # Try GDAL first
        if self.tools['gdal']:
            return self._merge_with_gdal(orthophotos, output_tif)
        # Fallback to rasterio
        elif self.tools['rasterio']:
            return self._merge_with_rasterio(orthophotos, output_tif)
        else:
            print("✗ No raster merging tools available")
            print("  Install GDAL: conda install -c conda-forge gdal")
            print("  Or install rasterio: pip install rasterio")
            return False
    
    def _merge_with_gdal(self, orthophotos, output_file):
        """Merge using GDAL"""
        print("Using GDAL for merging...")
        
        cmd = ['gdal_merge.py', '-o', str(output_file)] + [str(o) for o in orthophotos]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✓ Combined orthophoto: {output_file}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ GDAL error: {e.stderr}")
            return False
    
    def _merge_with_rasterio(self, orthophotos, output_file):
        """Merge using rasterio"""
        print("Using rasterio for merging...")
        
        try:
            import rasterio
            from rasterio.merge import merge
            
            src_files = [rasterio.open(str(o)) for o in orthophotos]
            mosaic, out_trans = merge(src_files)
            
            out_meta = src_files[0].meta.copy()
            out_meta.update({
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans
            })
            
            with rasterio.open(output_file, "w", **out_meta) as dest:
                dest.write(mosaic)
            
            for src in src_files:
                src.close()
            
            print(f"✓ Combined orthophoto: {output_file}")
            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            return False
    
    def merge_meshes(self, datasets_info):
        """Merge OBJ meshes from multiple datasets"""
        meshes = [(d['mesh_file'], d['name']) for d in datasets_info if d['has_mesh']]
        
        if not meshes:
            print("⚠ No meshes found to merge")
            return False
        
        print(f"\n{'='*70}")
        print(f"MERGING 3D MESHES ({len(meshes)} files)")
        print(f"{'='*70}")
        
        return self._merge_obj_files(meshes)
    
    def _merge_obj_files(self, mesh_data):
        """Merge OBJ files with materials and textures"""
        output_obj = self.output_folder / "combined_mesh.obj"
        output_mtl = self.output_folder / "combined_mesh.mtl"
        textures_folder = self.output_folder / "textures"
        textures_folder.mkdir(exist_ok=True)
        
        all_vertices = []
        all_normals = []
        all_texcoords = []
        all_faces = []
        all_materials = {}
        
        v_offset = 0
        vn_offset = 0
        vt_offset = 0
        
        for mesh_file, dataset_name in mesh_data:
            print(f"Processing {dataset_name}...", end=' ')
            
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
        
        print(f"✓ Combined mesh: {output_obj}")
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
                    # Copy texture
                    src = source_folder / texture_file
                    if src.exists():
                        dst = dest_folder / f"{prefix}{texture_file}"
                        shutil.copy2(src, dst)
                        materials[current_mat].append((parts[0], f"{prefix}{texture_file}"))
                elif current_mat:
                    materials[current_mat].append(line)
        
        return materials
    
    def _write_obj(self, output_file, vertices, normals, texcoords, faces):
        """Write OBJ file"""
        with open(output_file, 'w') as f:
            f.write("# Combined ODM Mesh\n")
            f.write(f"mtllib combined_mesh.mtl\n\n")
            
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
                        f.write(f"{prop[0]} textures/{prop[1]}\n")
                    else:
                        f.write(f"{prop}\n")
                f.write("\n")
    
    def run(self):
        """Main execution"""
        datasets = self.find_datasets()
        
        if not datasets:
            print("✗ No datasets found!")
            return False
        
        print("="*70)
        print("ODM Dataset Merger")
        print("="*70)
        print(f"Found {len(datasets)} dataset(s)\n")
        
        # Analyze each dataset
        datasets_info = []
        for dataset in datasets:
            info = self.analyze_dataset(dataset)
            datasets_info.append(info)
            
            print(f"📁 {info['name']}")
            print(f"   Point Cloud: {'✓' if info['has_pointcloud'] else '✗'}")
            print(f"   Mesh: {'✓' if info['has_mesh'] else '✗'}")
            print(f"   Orthophoto: {'✓' if info['has_orthophoto'] else '✗'}")
            print(f"   DEM: {'✓' if info['has_dem'] else '✗'}")
            print()
        
        # Merge available data types
        results = []
        results.append(self.merge_point_clouds(datasets_info))
        results.append(self.merge_orthophotos(datasets_info))
        results.append(self.merge_meshes(datasets_info))
        
        if any(results):
            print("\n" + "="*70)
            print("✓ MERGE COMPLETE!")
            print("="*70)
            print(f"Output folder: {self.output_folder}")
            return True
        else:
            print("\n✗ No data could be merged")
            return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mother_folder = sys.argv[1]
    else:
        mother_folder = "MotherFolder"
    
    try:
        merger = ODMDatasetMerger(mother_folder)
        success = merger.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
