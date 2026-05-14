import os
import struct
import time

import bpy
from ..utils.misc import load_game_data
import importlib
from . import m2_scene
from ..pywowlib.m2_file import M2File, M2Versions
from ..pywowlib.blp import BLP2PNG
from ..ui.preferences import get_project_preferences


def _normalize_wow_path(path: str) -> str:
    return (path or "").replace("/", "\\").lstrip("\\")


def _find_local_file_near_m2(m2_dir: str, identifier) -> str:
    """
    Best-effort resolver for a dependency that should live next to the imported .m2.
    Returns an absolute path if found, else empty string.
    """
    if not m2_dir:
        return ""

    # FileDataID case (modern clients): allow local dumps as "<fdid>.<ext>"
    if isinstance(identifier, int):
        return ""

    rel = _normalize_wow_path(str(identifier))
    candidates = []
    if rel:
        candidates.append(os.path.join(m2_dir, rel))
        candidates.append(os.path.join(m2_dir, os.path.basename(rel)))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return ""


def _extract_textures_local_as_png(cache_dir: str, m2_dir: str, identifiers):
    """
    Convert local .blp textures (near the imported .m2) into PNGs in cache_dir.
    Mirrors WoWFileData.extract_textures_as_png() shape (returns {identifier: absolute_png_path}).
    """
    if not cache_dir:
        raise Exception('Error: cache directory is not specified. Check addon settings.')

    pairs = []
    filepaths = {}

    for identifier in identifiers:
        # If the user already has a PNG next to the M2, prefer it (no conversion needed).
        if isinstance(identifier, str) and identifier:
            rel = _normalize_wow_path(identifier)
            png_candidates = [
                os.path.join(m2_dir, os.path.splitext(rel)[0] + ".png"),
                os.path.join(m2_dir, os.path.splitext(os.path.basename(rel))[0] + ".png"),
            ]
            for png_path in png_candidates:
                if os.path.isfile(png_path):
                    filepaths[identifier] = png_path
                    break
            if identifier in filepaths:
                continue

        # Find a .blp next to the M2.
        blp_path = ""
        rel_out = ""

        if isinstance(identifier, int):
            # Local dumps sometimes use raw FDID filenames (e.g. 12345.blp)
            blp_candidate = os.path.join(m2_dir, f"{identifier}.blp")
            if os.path.isfile(blp_candidate):
                blp_path = blp_candidate
                rel_out = f"{identifier}.png"
        else:
            rel = _normalize_wow_path(str(identifier))
            blp_candidates = [
                os.path.join(m2_dir, os.path.splitext(rel)[0] + ".blp"),
                os.path.join(m2_dir, os.path.splitext(os.path.basename(rel))[0] + ".blp"),
                os.path.join(m2_dir, rel),  # if identifier already ends with .blp
                os.path.join(m2_dir, os.path.basename(rel)),
            ]
            for cand in blp_candidates:
                if os.path.isfile(cand) and os.path.splitext(cand)[1].lower() == ".blp":
                    blp_path = cand
                    # Keep the same relative texture layout when possible
                    rel_out = os.path.splitext(rel if cand.endswith(rel) else os.path.basename(rel))[0] + ".png"
                    break

        if not blp_path:
            # Keep going; missing textures should not hard-fail local import.
            continue

        try:
            with open(blp_path, "rb") as f:
                blp_bytes = f.read()
        except OSError:
            continue

        rel_out = rel_out.replace("\\", "/")
        abs_out = os.path.join(cache_dir, rel_out.replace("/", os.sep))
        os.makedirs(os.path.dirname(abs_out), exist_ok=True)

        filepaths[identifier] = abs_out
        pairs.append((blp_bytes, rel_out.encode("utf-8")))

    if pairs:
        BLP2PNG().convert(pairs, cache_dir.encode("utf-8"))

    return filepaths


def import_m2(version, filepath, is_local_file, time_import_method):

    start_time = time.time()

    # get global variables
    project_preferences = get_project_preferences()

    game_data = None
    # Local M2 imports must not require MPQ/CASC (and should not attempt to initialize them).
    if not is_local_file:
        try:
            game_data = load_game_data()
        except UserWarning:
            game_data = None

    m2_file = M2File(version, filepath=filepath)
    m2 = m2_file.root
    m2.filepath = filepath  # TODO: HACK
    
    extract_dir = os.path.dirname(filepath) if is_local_file else project_preferences.cache_dir_path

    if not extract_dir:
        raise Exception('Error: cache directory is not specified. Check addon settings.')

    if is_local_file:
        # Local-only mode: resolve dependencies from the same directory as the .m2.
        print("\n\nImporting M2 from local folder (no CASC/MPQ required)")

        dependencies = m2_file.find_model_dependencies()

        # textures: convert local BLPs to PNGs into cache folder (Blender can't read BLP)
        m2_file.texture_path_map = _extract_textures_local_as_png(
            project_preferences.cache_dir_path,
            extract_dir,
            dependencies.textures
        )

        # anims: prefer "{basename}.anim" next to the M2 (find_model_dependencies stores IDs or relative paths)
        anim_filepaths = {}
        for key, identifier in dependencies.anims.items():
            # identifier can be an FDID in modern builds; local-only import requires a real file
            if isinstance(identifier, int):
                candidate = os.path.join(extract_dir, f"{identifier}.anim")
                anim_filepaths[key] = candidate
                continue

            full_path = os.path.join(extract_dir, os.path.split(str(identifier))[-1])
            anim_filepaths[key] = full_path

        # skins:
        skins_are_fdids = bool(dependencies.skins) and isinstance(dependencies.skins[0], int)
        if skins_are_fdids:
            raw_path = os.path.splitext(filepath)[0]
            skin_filepaths = [
                "{}{}.skin".format(raw_path, str(i).zfill(2))
                for i in range(len(dependencies.skins))
            ]
            if not skin_filepaths or not os.path.isfile(skin_filepaths[0]):
                raise FileNotFoundError(
                    'Error: could not find "{}".\n'
                    'Local Legion+ imports require the numbered .skin files next to the .m2.\n'
                    'Export the model with skins, or place the .skin files in the same folder.'.format(
                        skin_filepaths[0] if skin_filepaths else "<m2>00.skin"
                    )
                )
        else:
            # WotLK/no SFID: find_model_dependencies already built paths based on the .m2 raw_path.
            skin_filepaths = dependencies.skins

        # modern extra files are optional in local-only mode; if present, M2File will read them later as needed
        # (bones/lod skins are handled via dependency reads, but missing files will be reported by M2File).

    elif game_data and game_data.files:

        # extract and read skel
        # skel_fdid = m2_file.find_main_skel()

        # while skel_fdid:
        #     skel_path = game_data.extract_file(extract_dir, skel_fdid, 'skel')
        #     skel_fdid = m2_file.read_skel(skel_path)

        # m2_file.process_skels()

        print("\n\nExtracting M2 required files into cache folder")

        dependencies = m2_file.find_model_dependencies()

        # extract textures, always into cache folder
        m2_file.texture_path_map = game_data.extract_textures_as_png(project_preferences.cache_dir_path, dependencies.textures)

        # extract anims
        anim_filepaths = {}
        for key, identifier in dependencies.anims.items():
            #For importing m2 through import (folder)
            if is_local_file:
                    
                    full_path = os.path.join(extract_dir, os.path.split(identifier)[-1])

                    if os.path.exists(full_path):
                        anim_filepaths[key] = full_path
                    else:
                        anim_filepaths[key] = os.path.split(identifier)[-1]
                        print("\n.anim not found at:", full_path, '\n')
            #For importing thorugh WMV/WoW.Export...               
            else:
                try:
                    anim_filepaths[key] = game_data.extract_file(extract_dir, identifier, 'anim')
                except:
                        anim_filepaths[key] = os.path.split(identifier)[-1]
                        print("\n Failed to extract anim from game data:", identifier)

        # extract skins and everything else
        # Export writes skins as {raw_path}00.skin next to the .m2 (mirror of m2_file.write).
        # Import is the exact inverse: for local files the .skin files must live in the same
        # folder as the .m2.  If the SFID chunk is present, dependencies.skins contains integer
        # FDIDs which cannot be used directly as paths, so we reconstruct the numbered paths.
        skins_are_fdids = bool(dependencies.skins) and isinstance(dependencies.skins[0], int)

        if is_local_file:
            if skins_are_fdids:
                # Rebuild local numbered paths the same way _write_skin_files() creates them
                # on export: {filepath_no_ext}00.skin, 01.skin, ...
                raw_path = os.path.splitext(filepath)[0]
                local_skin_paths = [
                    "{}{}.skin".format(raw_path, str(i).zfill(2))
                    for i in range(len(dependencies.skins))
                ]
                if os.path.isfile(local_skin_paths[0]):
                    # .skin files are next to the .m2 - use them directly (normal local import)
                    skin_filepaths = local_skin_paths
                else:
                    # .skin files are not local - try to pull from game data via FDID
                    skin_filepaths = game_data.extract_files(extract_dir, dependencies.skins, 'skin')
                    if not skin_filepaths or skin_filepaths[0] is None:
                        raise FileNotFoundError(
                            'Error: could not find "{}".\n'
                            'Make sure the .skin files are in the same folder as the .m2.'.format(
                                local_skin_paths[0])
                        )
            else:
                # String paths (WotLK/no SFID): find_model_dependencies already built absolute paths.
                skin_filepaths = dependencies.skins
        else:
            skin_filepaths = game_data.extract_files(extract_dir, dependencies.skins, 'skin')

        if version >= M2Versions.WOD:
            game_data.extract_files(extract_dir, dependencies.bones, 'bone', True)
            game_data.extract_files(extract_dir, dependencies.lod_skins, 'skin', True)
        
    else:
        raise NotImplementedError('Error: Importing without gamedata loaded is not yet implemented.')

    m2_file.read_additional_files(skin_filepaths, anim_filepaths)
    m2_file.root.assign_bone_names()

    bpy.context.scene.wow_scene.version = '6' if version >= M2Versions.LEGION else '2'
    if m2_file.sfid:
        bpy.context.scene.wow_scene.m2_skin_file_data_ids = ",".join(str(val) for val in m2_file.sfid.skin_file_data_ids)
        bpy.context.scene.wow_scene.m2_lod_skin_file_data_ids = ",".join(str(val) for val in m2_file.sfid.lod_skin_file_data_ids)
    else:
        bpy.context.scene.wow_scene.m2_skin_file_data_ids = ""
        bpy.context.scene.wow_scene.m2_lod_skin_file_data_ids = ""

    try:
        scene = bpy.context.scene
        scene["wbs_m2_import_source"] = os.path.basename(filepath).lower()
        scene["wbs_m2_original_bounds"] = [
            *[float(value) for value in m2_file.root.bounding_box.min],
            *[float(value) for value in m2_file.root.bounding_box.max],
            float(m2_file.root.bounding_sphere_radius),
        ]
        scene["wbs_m2_original_collision_bounds"] = [
            *[float(value) for value in m2_file.root.collision_box.min],
            *[float(value) for value in m2_file.root.collision_box.max],
            float(m2_file.root.collision_sphere_radius),
        ]
        scene["wbs_m2_original_had_collision"] = bool(len(m2_file.root.collision_vertices))
        scene["wbs_m2_original_replacable_texture_lookup"] = [
            int(value) for value in m2_file.root.replacable_texture_lookup
        ]
        if m2_file.ldv1:
            scene["wbs_m2_original_ldv1"] = [
                int(m2_file.ldv1.unk0),
                int(m2_file.ldv1.lod_count),
                float(m2_file.ldv1.unk2_f),
                *[int(value) for value in m2_file.ldv1.particle_bone_lod],
                int(m2_file.ldv1.unk4),
            ]
    except Exception:
        pass

    if not is_local_file:
        for key, identifier in dependencies.anims.items():
            os.remove(os.path.join(extract_dir, identifier))

    print("\n\n### Importing M2 model ###")

    importlib.reload(m2_scene)
    bl_m2 = m2_scene.BlenderM2Scene(m2_file, project_preferences)

    cache_dir = project_preferences.cache_dir_path
    end_index = filepath.find(cache_dir) + len(cache_dir) + 1
    m2_filepath = filepath[end_index:]

    if not is_local_file:
        bpy.context.scene.wow_scene.game_path = m2_filepath
    else:
        normalized_path = os.path.normpath(filepath)
        path_parts = [part.lower() for part in normalized_path.split(os.sep)]
        wow_root_folders = ["character", "creature", "environments", "item", "spells", "world"]
        base_path_index = next((path_parts.index(cat) for cat in wow_root_folders if cat in path_parts), 0)
        
        bpy.context.scene.wow_scene.game_path = os.sep.join(path_parts[base_path_index:])

    #import cProfile
    #def profile_import_animations(instance):
        #cProfile.runctx('instance.load_animations()', globals(), locals(), sort='cumulative')
    #profile_import_animations(bl_m2)
        
    bl_m2.load_armature()
    bl_m2.load_animations()
    bl_m2.load_colors(time_import_method)
    bl_m2.load_transparency(time_import_method)
    dbc_textures = bl_m2.load_materials()
    bl_m2.load_geosets()
    bl_m2.load_texture_transforms()
    bl_m2.load_collision()
    bl_m2.load_attachments()
    bl_m2.load_lights()
    bl_m2.load_events()
    bl_m2.load_cameras(time_import_method)
    bl_m2.load_ribbons()
    bl_m2.load_particles(time_import_method)
    bl_m2.load_globalflags()

    if dbc_textures:
        bpy.ops.scene.wow_creature_load_textures(LoadAll=True) 

    print("\nDone importing M2. \nTotal import time: ",
          time.strftime("%M minutes %S seconds.", time.gmtime(time.time() - start_time)))

    bpy.ops.wbs.viewport_text_display('INVOKE_DEFAULT', message="Info: Successfully imported M2!", font_size=24, y_offset=67)   
        
    return m2_file


def import_m2_gamedata(version, filepath, is_local_file):


    game_data = load_game_data()

    if not game_data or not game_data.files:
        raise FileNotFoundError("Game data is not loaded.")

    addon_prefs = get_project_preferences()
    cache_dir = addon_prefs.cache_dir_path
    time_import_method = addon_prefs.time_import_method

    if time_import_method == 'Convert':
        bpy.context.scene.render.fps = 30
        bpy.context.scene.sync_mode = 'NONE'
    else:
        bpy.context.scene.render.fps = 1000
        bpy.context.scene.sync_mode = 'FRAME_DROP'

    game_data.extract_file(cache_dir, filepath)

    if os.name != 'nt':
        filepath = filepath.lower()
        root_path = os.path.join(cache_dir, filepath.replace('\\', '/'))
    else:
        root_path = os.path.join(cache_dir, filepath)

    with open(root_path, 'rb') as f:
        f.seek(68)
        n_skins = struct.unpack('I', f.read(4))[0]

    skin_paths = ["{}{}.skin".format(filepath[:-3], str(i).zfill(2)) for i in range(n_skins)]
    game_data.extract_files(cache_dir, skin_paths)

    import_m2(version, root_path, is_local_file, time_import_method)    

    # clean up unnecessary files and directories
    os.remove(root_path)
    for skin_path in skin_paths:
        os.remove(os.path.join(cache_dir, *skin_path.split('\\')))
