import os
import struct

from io import BytesIO
from typing import Iterable, List
from collections import deque

from .enums.m2_enums import M2GlobalFlags, M2TextureTypes
from .file_formats import m2_chunks
from .file_formats.m2_format import *
from .file_formats.m2_chunks import *
from .file_formats.skin_format import M2ShadowBatch, M2SkinProfile, M2SkinSubmesh, M2SkinTextureUnit
from .file_formats.skel_format import SkelFile
from .file_formats.anim_format import AnimFile
from .file_formats.wow_common_types import M2Array, M2Versions, M2VersionsManager


_LISTFILE_PATH = os.path.join(os.path.dirname(__file__), 'archives', 'listfile.csv')
_LISTFILE_FDID_CACHE = {}
_LISTFILE_FDID_MISSES = set()
_LISTFILE_PATH_BY_FDID_CACHE = {}  # reverse: fdid (int) → path (str)
_DEFAULT_LDV1_FLOAT = 177.6384735107422
_DEFAULT_LDV1_FLAGS = 0x10800


class M2Dependencies:

    def __init__(self):
        self.textures = []
        self.skins = []
        self.anims = {}
        self.bones = []
        self.lod_skins = []


class M2File:
    def __init__(self, version, filepath=None):
        self.version = M2Versions.from_expansion_number(version)
        if filepath is None:
            self.version = max(int(self.version), int(M2Versions.LEGION))
        M2VersionsManager().set_m2_version(self.version)

        # New exports are always modern MD21/Legion. When reading an existing
        # file, read() replaces this root with the version declared by the file.
        self.root = MD21() if self.version >= M2Versions.CATA else MD20()
        self.filepath = filepath

        track_cache = M2TrackCache()
        track_cache.purge()
        
        self.dependencies = M2Dependencies()
        self.skins = [M2SkinProfile()]
        self.skels = deque()
        self.texture_path_map = {}

        self.pfid = None
        self.sfid = None
        self.afid = None
        self.bfid = None
        self.txac = None
        self.ldv1 = None
        self.expt = None
        self.exp2 = None
        self.pabc = None
        self.padc = None
        self.psbc = None
        self.pedc = None
        self.skid = None
        self.txid = None
        self.preserve_bounds = False
        self.preserve_collision_bounds = False

        if filepath:
            self.raw_path = os.path.splitext(filepath)[0]
            self.read()

    def read(self):
        self.skins = []

        with open(self.filepath, 'rb') as f:
            magic = f.read(4).decode('utf-8')

            if magic == 'MD20':
                self.root = MD20().read(f)
            else:
                self.root = MD21().read(f)

            self.version = self.root.version
            self.root.m2_version = self.root.version
            M2VersionsManager().set_m2_version(self.version)

            if magic != 'MD20':

                while True:
                    try:
                        magic = f.read(4).decode('utf-8')

                    except EOFError:
                        break

                    except struct.error:
                        break

                    except UnicodeDecodeError:
                        print('\nAttempted reading non-chunked data.')
                        break

                    if not magic:
                        break

                    # getting the correct chunk parsing class
                    chunk = getattr(m2_chunks, magic, None)

                    # skipping unknown chunks
                    if chunk is None:
                        print("\nEncountered unknown chunk \"{}\"".format(magic))
                        f.seek(M2ContentChunk().read(f).size, 1)
                        continue

                    if magic != 'SFID':
                        setattr(self, magic.lower(), chunk().read(f))

                    else:
                        self.sfid = SFID(n_views=self.root.num_skin_profiles).read(f)

    def find_main_skel(self) -> int:

        if self.skid:
            return self.skid.skeleton_file_id

        return 0

    def read_skel(self, path: str) -> int:

        skel = SkelFile(path)

        with open(path, 'rb') as f:
            skel.read(f)

        self.skels.appendleft(skel)

        if skel.skpd:
            return skel.skpd.parent_skel_file_id

        return 0

    def process_skels(self):

        for skel in self.skels:

            if skel.skl1:
                self.root.name = skel.skl1.name

            if skel.ska1:
                self.root.attachments = skel.ska1.attachments
                self.root.attachment_lookup_table = skel.ska1.attachment_lookup_table

            if skel.skb1:
                self.root.bones = skel.skb1.bones
                self.root.key_bone_lookup = skel.skb1.key_bone_lookup

            if skel.sks1:
                self.root.global_sequences = skel.sks1.global_loops
                self.root.sequences = skel.sks1.sequences
                self.root.sequence_lookup = skel.sks1.sequence_lookups

            if skel.afid:

                if not self.afid:
                    self.afid = AFID()

                self.afid.anim_file_ids = skel.afid.anim_file_ids

    def find_model_dependencies(self) -> M2Dependencies:

        # find skins
        if self.sfid:
            self.dependencies.skins = [fdid for fdid in self.sfid.skin_file_data_ids]
            self.dependencies.lod_skins = [fdid for fdid in self.sfid.lod_skin_file_data_ids]

        elif self.version >= M2Versions.WOTLK:

            # TODO : figure out if this is completely compatible with WOTLK
            # if self.version >= M2Versions.WOD:
            
            self.dependencies.lod_skins = ["{}{}.skin".format(
                self.raw_path, str(i + 1).zfill(2))  for i in range(2)]
            self.dependencies.skins = ["{}{}.skin".format(
                self.raw_path, str(i).zfill(2)) for i in range(self.root.num_skin_profiles)]

        # find textures
        for i, texture in enumerate(self.root.textures):

            if texture.type != M2TextureTypes.NONE:
                continue

            if texture.filename.value:
                self.dependencies.textures.append(texture.filename.value)

            elif self.txid and i < len(self.txid.texture_ids) and self.txid.texture_ids[i] > 0:

                texture.fdid = self.txid.texture_ids[i]
                self.dependencies.textures.append(texture.fdid)

        # find bones
        if self.bfid:
            self.dependencies.bones = [fdid for fdid in self.bfid.bone_file_data_ids]

        elif self.version >= M2Versions.WOD:

            for sequence in self.root.sequences:

                if sequence.id == 808:
                    self.dependencies.bones.append("{}_{}.bone".format(
                        self.raw_path, str(sequence.variation_index).zfill(2)))

        # TODO: find phys

        # find anims
        anim_paths_map = {}

        normalized_path = os.path.normpath(self.raw_path)
        path_parts = [part.lower() for part in normalized_path.split(os.sep)]
        if "character" in path_parts:
            base_path_index = path_parts.index("character")
        elif "creature" in path_parts:
            base_path_index = path_parts.index("creature")    
        elif "world" in path_parts:
            base_path_index = path_parts.index("world")    
        else:
            base_path_index = 0

        relevant_path = "\\".join(path_parts[base_path_index:])

        if not self.afid:
            for i, sequence in enumerate(self.root.sequences):
                # handle alias animations
                real_anim = sequence
                a_idx = i

                while real_anim.flags & 0x40 and real_anim.alias_next != a_idx:
                    a_idx = real_anim.alias_next
                    real_anim = self.root.sequences[real_anim.alias_next]

                if not sequence.flags & 0x130:
                    anim_paths_map[real_anim.id, sequence.variation_index] \
                        = "{}{}-{}.anim".format(relevant_path if not self.skels else self.skels[0].root_basepath
                                                , str(real_anim.id).zfill(4)
                                                , str(sequence.variation_index).zfill(2))

        else:
            for record in self.afid.anim_file_ids:

                if not record.file_id:
                    continue

                anim_paths_map[record.anim_id, record.sub_anim_id] = record.file_id


        self.dependencies.anims = anim_paths_map        
        return self.dependencies

    @staticmethod
    def process_anim_file(raw_data : BytesIO, tracks: List[M2Track], real_seq_index: int):
        
        for track in tracks:
            if track.global_sequence < 0 and track.timestamps.n_elements > real_seq_index:

                timestamps = track.timestamps[real_seq_index]
                timestamps.read(raw_data, ignore_header=True)

                if track.creator is not M2Event:

                    frame_values = track.values[real_seq_index]
                    frame_values.read(raw_data, ignore_header=True)

    def read_additional_files(self, skin_paths, anim_paths):
        self._set_version_context()

        if self.version >= M2Versions.WOTLK:
            # load skins

            for i in range(self.root.num_skin_profiles):

                try:
                    skin_path = skin_paths[i]
                    if skin_path is None:
                        raise FileNotFoundError
                    with open(skin_path, 'rb') as skin_file:
                        self.skins.append(M2SkinProfile().read(skin_file))
                except (FileNotFoundError, OSError) as e:
                    if i == 0:
                        raise FileNotFoundError(
                            'Error: could not load the primary .skin file "{}". '
                            'Make sure the .skin files are next to the .m2 file.'.format(
                                skin_paths[i] if skin_paths and i < len(skin_paths) else '?'
                            )
                        ) from e
                    # non-primary skins are optional, skip them
                    print('Warning: could not load skin {}: {}'.format(i, e))

            # load anim files
            track_cache = M2TrackCache()
            for i, sequence in enumerate(self.root.sequences):
                # handle alias animations
                real_anim = sequence
                a_idx = i

                while real_anim.flags & 0x40 and real_anim.alias_next != a_idx:
                    a_idx = real_anim.alias_next
                    real_anim = self.root.sequences[real_anim.alias_next]

                if not sequence.flags & 0x130:
                    chunked_anim_files = self.version >= M2Versions.LEGION and self.root.global_flags & M2GlobalFlags.ChunkedAnimFiles

                    anim_file = AnimFile(split=bool(self.skels)
                                         , old=not bool(self.skels)
                                                and not chunked_anim_files)
                                                # downported models that don't clean up flags can crash and be detected as new version
                                               # and not self.root.global_flags & M2GlobalFlags.ChunkedAnimFiles) 
                    
                    anim_path = anim_paths[real_anim.id, sequence.variation_index]

                    try:
                        if not os.path.exists(anim_path):
                            raise FileNotFoundError(
                                f"\nThe required .anim file \"{anim_path}\" was not found.\n"
                                "Please, add the missing .anim file and try again."
                            )

                        with open(anim_path, 'rb') as f:
                            # print(anim_path)
                            
                            anim_file.read(f)

                    except FileNotFoundError as e:
                        #import sys
                        #sys.tracebacklimit = 0
                        raise e

                    if anim_file.old or not anim_file.split:

                        if anim_file.old:
                            raw_data = anim_file.raw_data
                        else:
                            raw_data = anim_file.afm2.raw_data

                        for creator, tracks in track_cache.m2_tracks.items():

                            M2File.process_anim_file(raw_data, tracks, a_idx)

                    else:

                        for creator, tracks in track_cache.m2_tracks.items():

                            if creator == M2CompBone:
                                M2File.process_anim_file(anim_file.afsb.raw_data, tracks, a_idx)
                            elif creator == M2Attachment:
                                M2File.process_anim_file(anim_file.afsa.raw_data, tracks, a_idx)
                            else: #What's left in AFM2, seems like only Event data?
                                M2File.process_anim_file(anim_file.afm2.raw_data, tracks, a_idx)

        else:
            self.skins = self.root.skin_profiles

    @staticmethod
    def _normalize_path(path: str) -> str:
        return (path or '').replace('/', '\\').strip().lower()

    @staticmethod
    def _compute_bounds(vertices):
        min_x = min(vertex[0] for vertex in vertices)
        min_y = min(vertex[1] for vertex in vertices)
        min_z = min(vertex[2] for vertex in vertices)
        max_x = max(vertex[0] for vertex in vertices)
        max_y = max(vertex[1] for vertex in vertices)
        max_z = max(vertex[2] for vertex in vertices)

        center = (
            (min_x + max_x) / 2,
            (min_y + max_y) / 2,
            (min_z + max_z) / 2,
        )
        radius = max(
            ((vertex[0] - center[0]) ** 2 + (vertex[1] - center[1]) ** 2 + (vertex[2] - center[2]) ** 2) ** 0.5
            for vertex in vertices
        )

        return (min_x, min_y, min_z), (max_x, max_y, max_z), radius

    @classmethod
    def _lookup_file_data_id(cls, path: str) -> int:
        normalized_path = cls._normalize_path(path)
        if not normalized_path:
            return 0

        if normalized_path in _LISTFILE_FDID_CACHE:
            return _LISTFILE_FDID_CACHE[normalized_path]
        if normalized_path in _LISTFILE_FDID_MISSES:
            return 0

        try:
            with open(_LISTFILE_PATH, 'r', encoding='utf-8', errors='ignore') as listfile:
                for line in listfile:
                    line = line.rstrip('\r\n')
                    if not line:
                        continue

                    fdid_raw, sep, listfile_path = line.partition(';')
                    if not sep:
                        continue

                    if cls._normalize_path(listfile_path) != normalized_path:
                        continue

                    try:
                        file_data_id = int(fdid_raw)
                    except ValueError:
                        break

                    _LISTFILE_FDID_CACHE[normalized_path] = file_data_id
                    return file_data_id
        except OSError:
            pass

        _LISTFILE_FDID_MISSES.add(normalized_path)
        return 0

    @classmethod
    def _lookup_file_data_id_from_game_data(cls, path: str, game_data) -> int:
        normalized_path = cls._normalize_path(path)
        if not normalized_path or not game_data:
            return 0

        if normalized_path in _LISTFILE_FDID_CACHE:
            return _LISTFILE_FDID_CACHE[normalized_path]

        storages = getattr(game_data, 'files', None)
        if not storages:
            return 0

        try:
            from .archives.casc.CASC import FileOpenFlags
        except Exception:
            return 0

        for storage, is_archive in reversed(storages):
            if not is_archive:
                continue

            try:
                if (normalized_path, FileOpenFlags.CASC_OPEN_BY_NAME) not in storage:
                    continue

                with storage.read_file(normalized_path, FileOpenFlags.CASC_OPEN_BY_NAME) as casc_file:
                    file_info = casc_file.info

                file_data_id = int(getattr(file_info, 'file_data_id', 0) or 0)
                if file_data_id > 0:
                    _LISTFILE_FDID_CACHE[normalized_path] = file_data_id
                    return file_data_id
            except Exception:
                continue

        return 0

    @classmethod
    def resolve_file_data_id(cls, path: str, game_data=None) -> int:
        normalized_path = cls._normalize_path(path)
        if not normalized_path:
            return 0

        if normalized_path in _LISTFILE_FDID_CACHE:
            return _LISTFILE_FDID_CACHE[normalized_path]

        file_data_id = cls._lookup_file_data_id_from_game_data(normalized_path, game_data)
        if file_data_id:
            return file_data_id

        return cls._lookup_file_data_id(normalized_path)

    @classmethod
    def resolve_path_from_fdid(cls, fdid: int) -> str:
        """Look up a file path from a FileDataID using the bundled community listfile.

        This is the reverse of resolve_file_data_id and is used when importing newer
        WoW M2s (CASC/retail) that store textures by ID only (empty filename field).
        Results are cached for the lifetime of the session.

        Returns an empty string if the fdid cannot be resolved.
        """
        if not fdid:
            return ''

        if fdid in _LISTFILE_PATH_BY_FDID_CACHE:
            return _LISTFILE_PATH_BY_FDID_CACHE[fdid]

        try:
            with open(_LISTFILE_PATH, 'r', encoding='utf-8', errors='ignore') as listfile:
                for line in listfile:
                    line = line.rstrip('\r\n')
                    if not line:
                        continue
                    fdid_raw, sep, listfile_path = line.partition(';')
                    if not sep:
                        continue
                    try:
                        if int(fdid_raw) == fdid:
                            path = listfile_path.strip().replace('\\', '/').lower()
                            _LISTFILE_PATH_BY_FDID_CACHE[fdid] = path
                            return path
                    except ValueError:
                        continue
        except OSError:
            pass

        _LISTFILE_PATH_BY_FDID_CACHE[fdid] = ''
        return ''

    @staticmethod
    def _coerce_combo(values) -> tuple:
        if isinstance(values, Iterable) and not isinstance(values, (bytes, bytearray, str)):
            combo = tuple(values)
        else:
            combo = (values,)

        return tuple(int(value) for value in combo)

    @staticmethod
    def _append_lookup_combo(target, combo) -> int:
        combo = M2File._coerce_combo(combo)
        if not combo:
            return 0

        values = list(target)
        combo_len = len(combo)
        for start in range(len(values) - combo_len + 1):
            if tuple(values[start:start + combo_len]) == combo:
                return start

        target.extend(combo)
        return len(target) - combo_len

    def _set_version_context(self):
        M2VersionsManager().set_m2_version(self.version)
        self.root.version = self.version
        self.root.m2_version = self.version

    def _effective_export_version(self):
        # write() wraps the model in MD21 and patches the inner MD20 version to
        # a modern client version.  All dependent structures must be written with
        # that same version context; otherwise .skin is emitted as Wrath while
        # the .m2 advertises Cata/Legion, and the client reads the skin header
        # with the wrong layout.
        return max(int(self.version), int(M2Versions.LEGION))

    def _sync_skin_version_context(self):
        if self.version < M2Versions.WOTLK:
            return

        for skin in self.skins:
            skin.m2_version = self.version
            skin._size = 56 if self.version >= M2Versions.CATA else 48
            skin.magic = 'SKIN'

            for submesh in getattr(skin, 'submeshes', []):
                submesh.m2_version = self.version

            if self.version >= M2Versions.CATA and not hasattr(skin, 'shadow_batches'):
                skin.shadow_batches = M2Array(M2ShadowBatch)

    def _ensure_shadow_batches(self):
        if self.version < M2Versions.CATA:
            return

        for skin in self.skins:
            if not hasattr(skin, 'shadow_batches'):
                skin.shadow_batches = M2Array(M2ShadowBatch)

            if len(skin.shadow_batches) or not len(skin.texture_units):
                continue

            for tex_unit in skin.texture_units:
                material = None
                if 0 <= tex_unit.material_index < len(self.root.materials):
                    material = self.root.materials[tex_unit.material_index]

                render_flags = int(getattr(material, 'flags', 0) or 0)
                blending = int(getattr(material, 'blending_mode', 0) or 0)

                shadow_batch = M2ShadowBatch()
                shadow_batch.flags = int(tex_unit.flags) & 0xFF
                shadow_batch.flags2 = 0
                if render_flags & 0x04:
                    shadow_batch.flags2 |= 0x01
                if blending == 0:
                    shadow_batch.flags2 |= 0x02
                if render_flags & 0x80:
                    shadow_batch.flags2 |= 0x04
                if render_flags & 0x400:
                    shadow_batch.flags2 |= 0x06

                shadow_batch.submesh_id = tex_unit.skin_section_index
                shadow_batch.texture_id = tex_unit.texture_combo_index
                shadow_batch.color_id = 0xFFFF if tex_unit.color_index < 0 else tex_unit.color_index
                shadow_batch.transparency_id = tex_unit.texture_weight_combo_index
                skin.shadow_batches.add(shadow_batch)

    @staticmethod
    def _as_signed_int(value, bits):
        limit = 1 << bits
        half = 1 << (bits - 1)
        value = int(value)
        if value < -half or value > half - 1:
            value = ((value + half) % limit) - half
        return value

    def _sanitize_skin_for_write(self):
        tex_lookup_len = len(getattr(self.root, "texture_lookup_table", []))
        tex_unit_lookup_len = len(getattr(self.root, "tex_unit_lookup_table", []))
        transparency_lookup_len = len(getattr(self.root, "transparency_lookup_table", []))
        transform_lookup_len = len(getattr(self.root, "texture_transforms_lookup_table", []))

        for skin in self.skins:
            skin.magic = 'SKIN'

            for tex_unit in getattr(skin, "texture_units", []):
                tex_unit.flags = int(tex_unit.flags) & 0xFF
                tex_unit.shader_id = self._as_signed_int(tex_unit.shader_id, 16)
                tex_unit.texture_count = max(1, int(tex_unit.texture_count))

                if tex_lookup_len:
                    if tex_unit.texture_combo_index >= tex_lookup_len:
                        tex_unit.texture_combo_index = 0
                    remaining = tex_lookup_len - tex_unit.texture_combo_index
                    tex_unit.texture_count = max(1, min(tex_unit.texture_count, remaining))

                if tex_unit_lookup_len and tex_unit.texture_coord_combo_index >= tex_unit_lookup_len:
                    tex_unit.texture_coord_combo_index = 0
                if transparency_lookup_len and tex_unit.texture_weight_combo_index >= transparency_lookup_len:
                    tex_unit.texture_weight_combo_index = 0
                if transform_lookup_len and tex_unit.texture_transform_combo_index >= transform_lookup_len:
                    tex_unit.texture_transform_combo_index = 0

    def _finalize_bounds(self):
        if self.root.vertices and not self.preserve_bounds:
            vertices = [tuple(vertex.pos) for vertex in self.root.vertices]
            bounds_min, bounds_max, radius = self._compute_bounds(vertices)
            self.root.bounding_box.min = bounds_min
            self.root.bounding_box.max = bounds_max
            self.root.bounding_sphere_radius = radius

        if self.root.collision_vertices:
            vertices = [tuple(vertex) for vertex in self.root.collision_vertices]
            bounds_min, bounds_max, radius = self._compute_bounds(vertices)
            self.root.collision_box.min = bounds_min
            self.root.collision_box.max = bounds_max
            self.root.collision_sphere_radius = radius
        elif self.root.vertices and not self.preserve_collision_bounds:
            self.root.collision_box.min = tuple(self.root.bounding_box.min)
            self.root.collision_box.max = tuple(self.root.bounding_box.max)
            self.root.collision_sphere_radius = self.root.bounding_sphere_radius

    def _prepare_skin_chunks(self):
        if self.version < M2Versions.WOTLK:
            self.root.skin_profiles = self.skins
            return

        self.root.num_skin_profiles = len(self.skins)

        if not self.sfid:
            return

        self.sfid.n_views = len(self.skins)
        self.sfid.skin_file_data_ids = list(self.sfid.skin_file_data_ids[:len(self.skins)])
        while len(self.sfid.skin_file_data_ids) < len(self.skins):
            self.sfid.skin_file_data_ids.append(0)

    def _prepare_modern_chunks(self):
        if self.version < M2Versions.CATA:
            return

        existing_texture_ids = list(getattr(self.txid, 'texture_ids', []) or []) if self.txid else []

        if self.root.textures:
            self.txac = TXAC()
            self.txac.texture_ac = []
            self.txid = TXID()
            self.txid.texture_ids = []

            for i, texture in enumerate(self.root.textures):
                txac_entry = TextureAC()
                self.txac.texture_ac.append(txac_entry)

                file_data_id = 0
                if texture.type == M2TextureTypes.NONE:
                    file_data_id = int(getattr(texture, 'fdid', 0) or 0)
                    if not file_data_id and i < len(existing_texture_ids):
                        file_data_id = int(existing_texture_ids[i] or 0)
                    if not file_data_id and texture.filename.value:
                        file_data_id = self._lookup_file_data_id(texture.filename.value)

                    texture.fdid = file_data_id
                    if file_data_id:
                        texture.filename.value = ''

                self.txid.texture_ids.append(file_data_id)

        created_ldv1 = False
        if not self.ldv1:
            self.ldv1 = LDV1()
            created_ldv1 = True

        if created_ldv1 and not self.ldv1.unk0:
            self.ldv1.unk0 = 12
        lod_count = max(1, len(self.skins))
        if self.sfid:
            lod_count = max(
                lod_count,
                len(self.sfid.skin_file_data_ids) + len(self.sfid.lod_skin_file_data_ids)
            )
        if not self.ldv1.lod_count or self.ldv1.lod_count < lod_count:
            self.ldv1.lod_count = lod_count
        if created_ldv1 and not self.ldv1.unk2_f:
            self.ldv1.unk2_f = _DEFAULT_LDV1_FLOAT
        if created_ldv1 and not any(self.ldv1.particle_bone_lod):
            self.ldv1.particle_bone_lod = [0, 0, 1, 2]
        if created_ldv1 and not self.ldv1.unk4:
            self.ldv1.unk4 = _DEFAULT_LDV1_FLAGS

    def _write_skin_files(self, filepath):
        if self.version < M2Versions.WOTLK:
            self.root.skin_profiles = self.skins
            return

        self._sync_skin_version_context()
        self._ensure_shadow_batches()

        # Fix up skin metadata (submesh counts / texture unit indices) before writing.
        # Some exporter paths can leave section counters at 0, which makes the model invisible in-game.
        for skin in self.skins:
            try:
                # If we only have one submesh and it has zeroed counters, make it cover the whole buffers.
                if len(skin.submeshes) == 1:
                    sm = skin.submeshes[0]
                    if getattr(sm, "vertex_count", 0) == 0 and len(skin.vertex_indices):
                        sm.vertex_start = 0
                        sm.vertex_count = len(skin.vertex_indices)
                    if getattr(sm, "index_count", 0) == 0 and len(skin.triangle_indices):
                        sm.index_start = 0
                        sm.index_count = len(skin.triangle_indices)

                    # Transparent sorting depends on sort_radius; keep it consistent with render bounds.
                    if hasattr(sm, "sort_radius") and (getattr(sm, "sort_radius", 0.0) or 0.0) <= 0.0:
                        sm.sort_radius = float(getattr(self.root, "bounding_sphere_radius", 0.0) or 0.0)

                # Texture units must have at least 1 texture, and indices must be in range.
                tex_lookup_len = len(getattr(self.root, "texture_lookup_table", []))
                for tu in getattr(skin, "texture_units", []):
                    if getattr(tu, "texture_count", 0) <= 0:
                        tu.texture_count = 1
                    if tex_lookup_len and getattr(tu, "texture_combo_index", 0) >= tex_lookup_len:
                        tu.texture_combo_index = 0
            except Exception:
                pass

        self._sanitize_skin_for_write()

        raw_path = os.path.splitext(filepath)[0]
        for i, skin in enumerate(self.skins):
            skin_path = "{}{}.skin".format(raw_path, str(i).zfill(2))
            with open(skin_path, 'wb') as skin_file:
                skin.write(skin_file)

    def _write_tail_chunks(self, f, force=False):
        if not force and self.version < M2Versions.CATA:
            return

        if self.ldv1:
            self.ldv1.write(f)

        if self.sfid and (
            any(self.sfid.skin_file_data_ids)
            or any(self.sfid.lod_skin_file_data_ids)
        ):
            self.sfid.write(f)

        if self.txac and getattr(self.txac, 'texture_ac', None):
            self.txac.write(f)

        if self.txid and getattr(self.txid, 'texture_ids', None):
            self.txid.write(f)

    def _write_export(self, filepath):
        import struct as _st
        from io import BytesIO as _BIO

        self.version = self._effective_export_version()
        self._set_version_context()
        self._finalize_bounds()

        # ── Guarantee SFID chunk exists ──────────────────────────────────────
        # The SFID chunk tells the client where to find the .skin files via
        # FileDataID. For custom content (MPQ / patch) we use 0s; the client
        # falls back to the filename-based path. Without SFID the model is
        # completely invisible in BfA+ clients.
        if not self.sfid and self.skins:
            self.sfid = SFID(n_views=len(self.skins))
            self.sfid.skin_file_data_ids = [0] * len(self.skins)
            self.sfid.lod_skin_file_data_ids = []

        self._prepare_skin_chunks()
        self._prepare_modern_chunks()

        # Safety: strip flags that require physics/camera sidecar files
        try:
            if hasattr(self.root, 'global_flags'):
                self.root.global_flags = (
                    int(self.root.global_flags)
                    & ~int(M2GlobalFlags.LoadPhysData)
                )
        except Exception:
            pass

        # Bone safety
        try:
            if hasattr(self.root, 'bones') and len(self.root.bones) == 1:
                self.root.bones[0].parent_bone = -1
        except Exception:
            pass

        self._write_skin_files(filepath)

        # ── Always produce MD21 output ───────────────────────────────────────
        # MD20 (flat) is a legacy format. BfA+ clients (including Epsilon RP)
        # require the MD21 RIFF-like container plus the tail chunks SFID and
        # TXID so the engine can locate .skin and texture files by FileDataID.
        # We write the inner MD20 block to a buffer first, patch the version
        # field to the correct target value, then wrap everything in MD21.
        md20_buf = _BIO()
        M2Header.write(self.root, md20_buf)
        md20_bytes = bytearray(md20_buf.getvalue())

        # Patch inner version to at least CATA (272) so the client uses the
        # modern rendering path. Preserve higher versions (e.g. 274 for BfA).
        target_version = int(self.version)
        _st.pack_into('<I', md20_bytes, 4, target_version)

        with open(filepath, 'wb') as f:
            # MD21 chunk header: 4-byte magic + 4-byte inner-block size
            f.write(b'MD21')
            f.write(_st.pack('<I', len(md20_bytes)))
            f.write(bytes(md20_bytes))
            # Write TXAC / LDV1 / SFID / TXID tail chunks unconditionally
            self._write_tail_chunks(f, force=True)

    def write(self, filepath):
        """
        Write M2 file. Always produces MD21-wrapped format (version 272)
        compatible with Legion-era clients (Epsilon etc.).
        Post-processes the raw bytes to match required structure.
        """
        return self._write_export(filepath)
        # ── 1. Bounding box auto-fix ─────────────────────────────────────────
        if self.root.vertices:
            _vx = [v.pos[0] for v in self.root.vertices]
            _vy = [v.pos[1] for v in self.root.vertices]
            _vz = [v.pos[2] for v in self.root.vertices]
            _min = (min(_vx), min(_vy), min(_vz))
            _max = (max(_vx), max(_vy), max(_vz))
            _cx = (_min[0]+_max[0])/2
            _cy = (_min[1]+_max[1])/2
            _cz = (_min[2]+_max[2])/2
            _r = max(
                ((_v.pos[0]-_cx)**2+(_v.pos[1]-_cy)**2+(_v.pos[2]-_cz)**2)**0.5
                for _v in self.root.vertices
            )
            if self.root.bounding_sphere_radius < 0.001 or abs(self.root.bounding_box.min[0]) > 1000:
                self.root.bounding_box.min = _min
                self.root.bounding_box.max = _max
                self.root.bounding_sphere_radius = _r
            if self.root.collision_sphere_radius < 0.001 or abs(self.root.collision_box.min[0]) > 1000:
                self.root.collision_box.min = _min
                self.root.collision_box.max = _max
                self.root.collision_sphere_radius = _r

        # ── 2. Write skin files ──────────────────────────────────────────────
        if self.version < M2Versions.WOTLK:
            self.root.skin_profiles = self.skins
        else:
            raw_path = os.path.splitext(filepath)[0]
            _skin_paths = []
            for i, skin in enumerate(self.skins):
                _sp = "{}{}.skin".format(raw_path, str(i).zfill(2))
                _skin_paths.append(_sp)
                with open(_sp, 'wb') as skin_file:
                    skin.write(skin_file)

            # Post-process skin files to fix maxBones and batch issues
            for _sp in _skin_paths:
                try:
                    import struct as _s2
                    with open(_sp, 'rb') as _f: _sk = bytearray(_f.read())
                    # Fix maxBones: field at offset 44 (uint32).
                    # Original has 0. Large values (21+) cause client to
                    # allocate bone palettes it can't fill → crash.
                    _s2.pack_into('<I', _sk, 44, 0)
                    # Fix skin submesh startBone: should be 0, not 1.
                    # Field is uint16 at submesh[0]+14 inside the submesh table.
                    _n_sub = _s2.unpack_from('<I', _sk, 28)[0]
                    _o_sub = _s2.unpack_from('<I', _sk, 32)[0]
                    for _si in range(_n_sub):
                        _sb_off = _o_sub + _si * 48 + 14
                        if _sb_off + 2 <= len(_sk):
                            _s2.pack_into('<H', _sk, _sb_off, 0)  # startBone=0
                    with open(_sp, 'wb') as _f: _f.write(_sk)
                except Exception:
                    pass

        # ── 3. Write M2 header to buffer ─────────────────────────────────────
        # ALWAYS use MD21 format (version 272) regardless of self.version.
        # self.version may be 264 (WotLK expansion number) because the scene
        # uses expansion '2', but the client is Legion-era and needs MD21 + v272.
        from io import BytesIO as _BytesIO
        import struct as _struct

        # Force version 272 on the root object before writing
        self.root.version = 272
        self.root.m2_version = 272
        try:
            from .file_formats.wow_common_types import M2VersionsManager as _MVM
            _MVM().set_m2_version(272)
        except Exception:
            pass

        md20_buf = _BytesIO()
        # Use M2Header.write() directly — bypasses the broken MD21.write()
        M2Header.write(self.root, md20_buf)
        md20_bytes = bytearray(md20_buf.getvalue())

        # ── 4. Post-process: fix header fields to exactly match original ────
        def _pu32(buf, off, val): _struct.pack_into('<I', buf, off, val)
        def _gu32(buf, off):      return _struct.unpack_from('<I', buf, off)[0]

        # 4a. Set global_flags bit 0x80 (required by WoD models)
        _pu32(md20_bytes, 16, _gu32(md20_bytes, 16) | 0x80)

        # 4b. Clear nTexUnitLkp (original=0, non-zero can cause shader crash)
        _pu32(md20_bytes, 136, 0)
        _pu32(md20_bytes, 140, 0)

        # 4c. Clear nSeqLkp (original=0, static objects don't need sub-anim lookup)
        _pu32(md20_bytes, 36, 0)
        _pu32(md20_bytes, 40, 0)

        # 4d. Cap nTexLkp/nTranspLkp/nTexAnimLkp to 1 (original has exactly 1 each)
        for nOff in [128, 144, 152]:
            if _gu32(md20_bytes, nOff) > 1:
                _pu32(md20_bytes, nOff, 1)

        # 4e. Ensure nBoneLkp = 4 with all entries = 0 (original has [0,0,0,0])
        nBL = _gu32(md20_bytes, 120)
        oBL = _gu32(md20_bytes, 124)
        if oBL > 0 and oBL + 8 <= len(md20_bytes):
            for k in range(4):
                if oBL + k*2 + 2 <= len(md20_bytes):
                    _struct.pack_into('<H', md20_bytes, oBL + k*2, 0)
            _pu32(md20_bytes, 120, 4)

        # 4f. CRITICAL: Force nBones = 1 (original has 1, we export 2)
        #     Two bones causes client to allocate wrong-sized bone palette.
        #     The second bone is always a dummy root — truncate to first bone only.
        nBones = _gu32(md20_bytes, 44)
        if nBones > 1:
            _pu32(md20_bytes, 44, 1)

        # 4g. CRITICAL: Force nTransp = 1 (original has 1, we export 2)
        nTr = _gu32(md20_bytes, 88)
        if nTr > 1:
            _pu32(md20_bytes, 88, 1)

        # 4h. CRITICAL: Force nColors = 0 (original has 0).
        #     The M2Color struct contains M2Track fields. When the addon writes
        #     a color via BytesIO + MemoryManager, the struct is allocated but
        #     the inner M2Array offsets are not properly resolved (MemoryManager
        #     seek ops behave differently on BytesIO vs real file). The result
        #     is a Color struct with valid-looking n values but broken offsets.
        #     With nColors=1, the Legion client allocates a color slot and reads
        #     the track data — hitting a null inner pointer → crash at 0x24.
        #     Original has nColors=0: no color tracks needed for static objects.
        _pu32(md20_bytes, 72, 0)   # nColors = 0
        _pu32(md20_bytes, 76, 0)   # oColors = 0

        # 4i. Force nTexUnitLkp = 0 again (post-process may not have run earlier)
        #     Original has 0. Any non-zero value can cause shader lookup crash.
        _pu32(md20_bytes, 136, 0)
        _pu32(md20_bytes, 140, 0)

        # 4j. Force nTexAnimLkp = 1 if original expects it (skin batch taLkp=0)
        #     If nTexAnimLkp=0 and batch references taLkp=0, client reads empty table.
        #     Original has nTexAnimLkp=1. Ensure at least 1 entry exists.
        nTAL = _gu32(md20_bytes, 152)
        if nTAL == 0:
            _pu32(md20_bytes, 152, 1)
            # oTexAnimLkp: borrow the same offset as nTranspLkp table if possible
            oTrL = _gu32(md20_bytes, 148)
            if oTrL > 0:
                _pu32(md20_bytes, 156, oTrL)  # reuse transp lookup offset (value -1)

        # ── 5. Wrap in MD21 chunk ────────────────────────────────────────────
        with open(filepath, 'wb') as f:
            f.write(b'MD21')
            f.write(_struct.pack('<I', len(md20_bytes)))
            f.write(md20_bytes)
            # No SFID, no TXID — custom content resolves by filename/path

        # TODO: anim, skel and phys

    def add_skin(self):
        skin = M2SkinProfile()
        self.skins.append(skin)
        return skin

    def add_vertex(self, pos, normal, tex_coords, bone_weights, bone_indices, tex_coords2=None):
        vertex = M2Vertex()
        vertex.pos = tuple(pos)
        vertex.normal = tuple(normal)
        vertex.tex_coords = tuple(tex_coords)

        # rigging information
        vertex.bone_weights = bone_weights
        vertex.bone_indices = bone_indices

        skin = self.skins[0]

        # handle optional properties
        if tex_coords2:
            vertex.tex_coords2 = tex_coords2

        vertex_index = self.root.vertices.add(vertex)
        skin.vertex_indices.append(vertex_index)
        return vertex_index

    def add_geoset(self, vertices, normals, uv, uv2, tris, b_indices, b_weights, origin, sort_pos, sort_radius, mesh_part_id):
        submesh = M2SkinSubmesh()
        skin = self.skins[0]

        max_influences = 0
        ordered_bone_ids = []
        seen_bones = set()

        for bone_index_set, bone_weight_set in zip(b_indices, b_weights):
            influences = 0
            for bone_id, bone_weight in zip(bone_index_set, bone_weight_set):
                if bone_weight > 0:
                    influences += 1
                    if bone_id not in seen_bones:
                        seen_bones.add(bone_id)
                        ordered_bone_ids.append(bone_id)

            max_influences = max(max_influences, influences)

        if not ordered_bone_ids:
            ordered_bone_ids = [0]

        submesh.bone_combo_index = len(self.root.bone_lookup_table)
        submesh.bone_count = len(ordered_bone_ids)
        submesh.bone_influences = 0 if len(ordered_bone_ids) <= 1 else max(1, max_influences)

        bone_lookup = {}
        for bone_id in ordered_bone_ids:
            bone_lookup[bone_id] = self.root.bone_lookup_table.add(bone_id) - submesh.bone_combo_index

        if len(ordered_bone_ids) <= 1:
            skin.bone_count_max = 0
        elif len(ordered_bone_ids) > skin.bone_count_max:
            for value in (21, 53, 64, 256):
                if value >= len(ordered_bone_ids):
                    skin.bone_count_max = value
                    break

        start_index = len(self.root.vertices)
        for i, vertex_pos in enumerate(vertices):
            global_b_indices = tuple(int(index) for index in b_indices[i])
            args = [vertex_pos, normals[i], uv[i], b_weights[i], global_b_indices]

            if uv2:
                args.append(uv2[i])

            self.add_vertex(*args)

            indices = skin.bone_indices.new()
            indices.values = [0, 1, 2, 3]

        submesh.vertex_start = start_index
        submesh.vertex_count = len(vertices)
        submesh.center_position = tuple(origin)

        if self.version >= M2Versions.TBC:
            submesh.sort_ceter_position = tuple(sort_pos)
            submesh.sort_radius = sort_radius

        submesh.skin_section_id = mesh_part_id
        submesh.index_start = len(skin.triangle_indices)
        submesh.index_count = len(tris) * 3
        submesh.bone_influences = max_influences
        submesh.center_bone_index = ordered_bone_ids[0] if ordered_bone_ids else 0

        for tri in tris:
            for idx in tri:
                skin.triangle_indices.append(start_index + idx)

        return skin.submeshes.add(submesh)

    def add_material_to_geoset(self, geoset_id, render_flags, blending, flags, shader_id, texture_lookup_id, tex_mappings, priority_plane, mat_layer, tex_count, color_id, transparency_id, transform_id, second_render_flags=None, second_blending=None):  # TODO: Add extra params & cata +
        skin = self.skins[0]
        tex_unit = M2SkinTextureUnit()
        tex_unit.skin_section_index = geoset_id
        skin.texture_units.add(tex_unit)
        tex_unit.geoset_index = geoset_id
        tex_unit.flags = flags | 0x10
        tex_unit.priority_plane = priority_plane
        tex_unit.shader_id = shader_id
        tex_unit.texture_count = tex_count
        tex_unit.texture_combo_index = texture_lookup_id
        tex_unit.material_layer = mat_layer
        tex_unit.color_index = color_id
        tex_unit.texture_weight_combo_index = transparency_id
        tex_unit.texture_transform_combo_index = transform_id

        needs_second_material = tex_count == 2 and second_render_flags is not None and second_blending is not None

        # Materials need to be duplicated if they're being used by a different texture, else, we'll reuse materials to not repeat data, Blizz does too
        if needs_second_material:
            for i, material in enumerate(self.root.materials[:-1]):
                second_material = self.root.materials[i + 1]
                if (
                    material.flags == render_flags
                    and material.blending_mode == blending
                    and material.texture_used == texture_lookup_id
                    and second_material.flags == second_render_flags
                    and second_material.blending_mode == second_blending
                ):
                    tex_unit.material_index = i
                    break
            else:
                m2_mat = M2Material()
                m2_mat.flags = render_flags
                m2_mat.blending_mode = blending
                m2_mat.texture_used = texture_lookup_id
                tex_unit.material_index = self.root.materials.add(m2_mat)

                m2_mat2 = M2Material()
                m2_mat2.flags = second_render_flags
                m2_mat2.blending_mode = second_blending
                m2_mat2.texture_used = texture_lookup_id
                self.root.materials.add(m2_mat2)
        else:
            for i, material in enumerate(self.root.materials):
                if material.flags == render_flags and material.blending_mode == blending and material.texture_used == texture_lookup_id:
                    tex_unit.material_index = i
                    break
            else:
                m2_mat = M2Material()
                m2_mat.flags = render_flags
                m2_mat.blending_mode = blending
                m2_mat.texture_used = texture_lookup_id
                tex_unit.material_index = self.root.materials.add(m2_mat)

        tex_mappings = self._coerce_combo(tex_mappings)
        if all(value == 0 for value in tex_mappings):
            tex_unit.texture_coord_combo_index = 0
        else:
            tex_unit.texture_coord_combo_index = self._append_lookup_combo(self.root.tex_unit_lookup_table, tex_mappings)

        if self.version >= M2Versions.CATA:
            shadow_batch = M2ShadowBatch()
            shadow_batch.flags = tex_unit.flags & 0xFF
            shadow_batch.flags2 = 0
            if render_flags & 0x04:
                shadow_batch.flags2 |= 0x01
            if blending == 0:
                shadow_batch.flags2 |= 0x02
            if render_flags & 0x80:
                shadow_batch.flags2 |= 0x04
            if render_flags & 0x400:
                shadow_batch.flags2 |= 0x06
            shadow_batch.submesh_id = geoset_id
            shadow_batch.texture_id = texture_lookup_id
            shadow_batch.color_id = 0xFFFF if color_id < 0 else color_id
            shadow_batch.transparency_id = transparency_id
            skin.shadow_batches.add(shadow_batch)

    def add_texture(self, path, flags, tex_type, file_data_id=0):

        # check if this texture was already added
        for i, tex in enumerate(self.root.textures):
            if (
                tex.filename.value == path
                and tex.flags == flags
                and tex.type == tex_type
                and int(getattr(tex, 'fdid', 0) or 0) == int(file_data_id or 0)
            ):
                return i

        texture = M2Texture()
        # Normalize path: None → '' so len() never fails on the string block.
        path = path or ''
        # Only omit the filename when working in fdid-only mode (retail/CASC: path intentionally empty).
        # If a path was explicitly provided always write it so WotLK/Epsilon clients can find the texture.
        texture.filename.value = '' if (tex_type == M2TextureTypes.NONE and file_data_id and not path) else path
        texture.flags = flags
        texture.type = tex_type
        texture.fdid = int(file_data_id or 0)

        tex_id = self.root.textures.add(texture)
        self.root.replacable_texture_lookup.append(0)   # TODO: get back here

        return tex_id
    
    def add_tex_lookup(self, texture_lookup_ids):
        return self._append_lookup_combo(self.root.texture_lookup_table, texture_lookup_ids)

    def add_texture_transform_lookup(self, transform_ids):
        return self._append_lookup_combo(self.root.texture_transforms_lookup_table, transform_ids)

    def add_bone(self, pivot, key_bone_id, flags, parent_bone,submesh_id = 0, bone_name_crc = 0):
        m2_bone = M2CompBone()
        m2_bone.key_bone_id = key_bone_id
        m2_bone.flags = flags
        m2_bone.parent_bone = parent_bone
        m2_bone.pivot = tuple(pivot)
        m2_bone.submesh_id = submesh_id
        m2_bone.bone_name_crc = bone_name_crc
        bone_id = self.root.bones.add(m2_bone)
        if key_bone_id >= 0:
            while len(self.root.key_bone_lookup) <= key_bone_id:
                self.root.key_bone_lookup.append(-1)
            self.root.key_bone_lookup.set_index(key_bone_id,bone_id)

        return bone_id

    def add_dummy_anim_set(self, origin):
        if not len(self.root.bones):
            self.add_bone(tuple(origin), -1, 0, -1)

        seq_flags = 32 | (0x800 if self.version >= M2Versions.WOD else 0)
        self.add_anim(
            0,
            0,
            (0, 88.888),
            0,
            seq_flags,
            32767,
            (0, 0),
            (150, 0) if self.version >= M2Versions.WOD else 150,
            ((self.root.bounding_box.min, self.root.bounding_box.max), self.root.bounding_sphere_radius),
            None,
            None,
        )

        if not len(self.root.transparency_lookup_table):
            self.root.transparency_lookup_table.add(len(self.root.texture_weights))

        if len(self.root.texture_weights):
            texture_weight = self.root.texture_weights[0]
        else:
            texture_weight = self.root.texture_weights.new()
        if self.version >= M2Versions.WOTLK:
            if not len(texture_weight.timestamps):
                texture_weight.timestamps.new().add(0)
            if not len(texture_weight.values):
                texture_weight.values.new().add(32767)
        else:
            pass
            # TODO: pre-wotlk

    def add_anim(self, a_id, var_id, frame_bounds, movespeed, flags, frequency, replay, bl_time, bounds, var_next=None, alias_next=None):
        seq = M2Sequence()
        seq_id = self.root.sequences.add(seq)
        if var_id == 0:
            while len(self.root.sequence_lookup) <= a_id:
                self.root.sequence_lookup.append(0xffff)
            self.root.sequence_lookup.set_index(a_id,seq_id)

        # It is presumed that framerate is always 24 fps.
        if self.version <= M2Versions.TBC:
            seq.start_timestamp, seq.end_timestamp = int(frame_bounds[0] // 0.0266666), int(frame_bounds[1] // 0.0266666)
        else:
            seq.duration = int(round((frame_bounds[1] - frame_bounds[0]) / 0.0266666))

        seq.id = a_id
        seq.variation_index = var_id
        seq.variation_next = var_next if var_next else -1
        # seq.alias_next = alias_next if alias_next else seq_id
        seq.alias_next = alias_next if flags & 64 else seq_id
        seq.flags = flags
        seq.frequency = frequency
        seq.movespeed = movespeed
        seq.replay.minimum, seq.replay.maximum = replay
        seq.bounds.extent.min, seq.bounds.extent.max = bounds[0]
        seq.bounds.radius = bounds[1]

        if self.version <= M2Versions.WOD:
            # WotLK/WoD: single blend_time int
            seq.blend_time = bl_time if isinstance(bl_time, int) else bl_time[0]
        else:
            # Legion+: two separate blend_time_in / blend_time_out values.
            # FIX: callers (add_dummy_anim_set, m2_scene save_animations) pass a
            # plain int for bl_time — normalize it to a 2-tuple so unpack works.
            if isinstance(bl_time, int):
                bl_time = (bl_time, bl_time)
            seq.blend_time_in, seq.blend_time_out = bl_time

        return seq_id

    def add_bone_track(self, bone_id, trans, rot, scale):
        bone = self.root.bones[bone_id]

        rot_ts = [int(frame // 0.0266666) for frame in rot[0]]
        trans_ts = [int(frame // 0.0266666) for frame in trans[0]]
        scale_ts = [int(frame // 0.0266666) for frame in scale[0]]

        if self.version < M2Versions.WOTLK:
            rot_quats = rot[1]

            if self.version <= M2Versions.CLASSIC:
                rot_quats = [(qtrn[1], qtrn[2], qtrn[3], qtrn[0]) for qtrn in rot[1]]

            bone.rotation.interpolation_ranges.append(len(bone.rotation.timestamps), len(rot[0]) - 1)
            bone.rotation.timestamps.extend(rot_ts)
            bone.rotation.values.extend(rot_quats)

            bone.translation.interpolation_ranges.append(len(bone.translation.timestamps), len(trans[0]) - 1)
            bone.translation.timestamps.extend(trans_ts)
            bone.translation.values.extend(trans[1])

            bone.scale.interpolation_ranges.append(len(bone.scale.timestamps), len(rot[0]) - 1)
            bone.scale.timestamps.extend(scale_ts)
            bone.scale.values.extend(scale[1])

        else:
            bone.rotation.timestamps.new().from_iterable(rot_ts)
            bone.rotation.values.new().from_iterable(rot[1])

            bone.translation.timestamps.new().from_iterable(trans_ts)
            bone.translation.values.new().from_iterable(trans[1])

            bone.scale.timestamps.new().from_iterable(scale_ts)
            bone.scale.values.new().from_iterable(scale[1])

    def add_collision_mesh(self, vertices, faces, normals):

        # add collision geometry
        self.root.collision_vertices.extend(vertices)
        for face in faces: self.root.collision_triangles.extend(face)
        self.root.collision_normals.extend(normals)
