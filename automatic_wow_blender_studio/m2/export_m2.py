import importlib

import os
import bpy
import time

from ..pywowlib import m2_file as m2_file_module
from ..pywowlib.file_formats import m2_chunks as m2_chunks_module
from ..pywowlib.file_formats import m2_format as m2_format_module
from ..pywowlib.file_formats import skin_format as skin_format_module
from . import m2_scene
from .operations import m2_export_warnings
from ..utils.misc import load_game_data, resolve_outside_model_path
from ..ui.preferences import get_project_preferences

MODERN_M2_EXPORT_VERSION = 6

def create_m2(version, filepath, selected_only, fill_textures, forward_axis, scale, merge_vertices):
    try:
        version = max(int(version), MODERN_M2_EXPORT_VERSION)
    except Exception:
        version = MODERN_M2_EXPORT_VERSION

    try:
        from ..pywowlib.file_formats.wow_common_types import M2VersionsManager, M2Versions
        M2VersionsManager().set_m2_version(M2Versions.from_expansion_number(version))
    except Exception:
        pass

    importlib.reload(m2_format_module)
    importlib.reload(m2_chunks_module)
    importlib.reload(skin_format_module)
    importlib.reload(m2_file_module)
    importlib.reload(m2_scene)
    importlib.reload(m2_export_warnings)

    proj_prefs = get_project_preferences()
    time_import_method = proj_prefs.time_import_method
    m2 = m2_file_module.M2File(version)
    bl_m2 = m2_scene.BlenderM2Scene(m2, proj_prefs)

    try:
        bpy.context.scene.wow_scene.version = str(version)
    except Exception:
        pass

    export_path = resolve_outside_model_path(filepath)
    if export_path:
        bpy.context.scene.wow_scene.game_path = export_path

    print("\n\n##########################")
    print("### Exporting M2 model ###")
    print("##########################")
    print("\n")

    start_time = time.time()

    bl_m2.prepare_export_axis(forward_axis, scale)
    bl_m2.prepare_pose(selected_only)
    bl_m2.save_properties(filepath, selected_only)
    bl_m2.save_bones(selected_only)
    bl_m2.save_cameras()
    bl_m2.save_attachments()
    bl_m2.save_events()
    bl_m2.save_lights()
    bl_m2.save_ribbons()
    bl_m2.save_particles(time_import_method)
    bl_m2.save_animations(time_import_method)
    bl_m2.save_geosets(selected_only, fill_textures, merge_vertices)
    bl_m2.save_collision(selected_only)
    bl_m2.restore_pose()

    try:
        scene = bpy.context.scene
        export_objects = scene.objects if not selected_only else scene.selected_objects
        imported_roundtrip = any(
            ob.type == 'MESH' and bool(ob.get("wbs_m2_imported_geoset"))
            for ob in export_objects
        )

        if imported_roundtrip:
            original_bounds = scene.get("wbs_m2_original_bounds")
            if original_bounds and len(original_bounds) == 7:
                m2.root.bounding_box.min = tuple(float(value) for value in original_bounds[0:3])
                m2.root.bounding_box.max = tuple(float(value) for value in original_bounds[3:6])
                m2.root.bounding_sphere_radius = float(original_bounds[6])
                m2.preserve_bounds = True

            if not scene.get("wbs_m2_original_had_collision", False):
                original_collision_bounds = scene.get("wbs_m2_original_collision_bounds")
                if original_collision_bounds and len(original_collision_bounds) == 7:
                    m2.root.collision_box.min = tuple(float(value) for value in original_collision_bounds[0:3])
                    m2.root.collision_box.max = tuple(float(value) for value in original_collision_bounds[3:6])
                    m2.root.collision_sphere_radius = float(original_collision_bounds[6])
                    m2.preserve_collision_bounds = True

            original_replacable_lookup = scene.get("wbs_m2_original_replacable_texture_lookup")
            if original_replacable_lookup:
                m2.root.replacable_texture_lookup.values = [
                    int(value) for value in original_replacable_lookup
                ]

            original_ldv1 = scene.get("wbs_m2_original_ldv1")
            if original_ldv1 and len(original_ldv1) == 8:
                m2.ldv1 = m2_chunks_module.LDV1()
                m2.ldv1.unk0 = int(original_ldv1[0])
                m2.ldv1.lod_count = int(original_ldv1[1])
                m2.ldv1.unk2_f = float(original_ldv1[2])
                m2.ldv1.particle_bone_lod = [int(value) for value in original_ldv1[3:7]]
                m2.ldv1.unk4 = int(original_ldv1[7])
    except Exception:
        pass

    try:
        from ..pywowlib.file_formats.m2_chunks import SFID

        def _parse_fdid_csv(raw_value):
            if not raw_value:
                return []
            values = []
            for token in raw_value.split(','):
                token = token.strip()
                if not token:
                    continue
                try:
                    values.append(max(0, int(token)))
                except ValueError:
                    continue
            return values

        scene = bpy.context.scene
        skin_ids = _parse_fdid_csv(getattr(scene.wow_scene, 'm2_skin_file_data_ids', ''))
        lod_skin_ids = _parse_fdid_csv(getattr(scene.wow_scene, 'm2_lod_skin_file_data_ids', ''))
        if not skin_ids:
            export_game_path = getattr(scene.wow_scene, 'game_path', '') or export_path or ''
            if export_game_path:
                skin_path = os.path.splitext(export_game_path)[0] + '00.skin'
                try:
                    game_data = load_game_data()
                except Exception:
                    game_data = None

                skin_fdid = m2_file_module.M2File.resolve_file_data_id(skin_path, game_data)
                if skin_fdid:
                    skin_ids = [skin_fdid]
                    scene.wow_scene.m2_skin_file_data_ids = str(skin_fdid)

        if skin_ids or lod_skin_ids:
            m2.sfid = SFID(n_views=len(m2.skins))
            m2.sfid.skin_file_data_ids = skin_ids[:len(m2.skins)]
            m2.sfid.lod_skin_file_data_ids = lod_skin_ids
    except Exception:
        pass

    warnings = m2_export_warnings.print_warnings()

    if warnings:
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: M2 Exported with Warnings, check console!!", font_size=32, y_offset=100, color=(1,0.15,0.15,1))
    else:
        bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully exported M2!", font_size=24, y_offset=67)    

    print("\nSuccessfully Exported M2 to " + filepath +
          "\nTotal export time: ", time.strftime("%M minutes %S seconds", time.gmtime(time.time() - start_time)))

    return m2


def export_m2(version, filepath, selected_only, fill_textures, forward_axis, scale, merge_vertices):
    if os.path.exists(filepath):
        os.remove(filepath)    
    create_m2(version,filepath,selected_only,fill_textures,forward_axis, scale, merge_vertices).write(filepath)
