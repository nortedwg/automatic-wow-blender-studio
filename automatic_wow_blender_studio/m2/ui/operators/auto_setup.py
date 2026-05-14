"""
auto_setup.py — Auto-Setup Modelo Custom para WoW Blender Studio M2  (v2 — FIXED)
----------------------------------------------------------------------------------
Correcciones respecto al original:
  • UV map: renombra el primer UV a 'UVMap' y elimina los extras (Texture2, etc.)
  • Ruta de textura: convierte / en \ automáticamente y limpia espacios
  • Registro de Geoset/Material/Textura: orden correcto para que los callbacks
    del addon no rechacen el pointer (NO poner enabled=True antes del pointer)
  • Recalcula normales hacia afuera (evita modelo invisible por caras invertidas)
  • Aplica escala y rotación antes del skinning
  • Reset de enabled antes de re-registrar (re-run limpio sin duplicados)
  • Enlace material→textura después del registro (no antes)
"""

import bpy

from ....pywowlib.m2_file import M2File
from ....utils.misc import load_game_data


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def _find_m2_armature(scene):
    """Devuelve el primer armature M2 de la escena, o None."""
    for obj in scene.objects:
        if obj.type == 'ARMATURE':
            try:
                if obj.wow_m2_globalflags.enabled:
                    return obj
            except Exception:
                pass
    if getattr(getattr(scene, 'wow_scene', None), 'type', None) == 'M2':
        for obj in scene.objects:
            if obj.type == 'ARMATURE':
                return obj
    return None


def _normalize_wow_path(raw_path):
    """
    Convierte la ruta al formato WoW:
      - barras / → backslashes \\
      - elimina espacios extremos
      - asegura extensión .blp
    """
    path = raw_path.strip()
    path = path.replace('/', '\\')      # forward → back
    path = path.replace('\\\\', '\\')  # dobles backslash → simple
    # Extensión: si no termina en .blp (case insensitive), avisamos pero no bloqueamos
    return path


def _assign_texture_path_and_fdid(image, wow_path):
    normalized_path = M2File._normalize_path(wow_path)
    existing_path = M2File._normalize_path(getattr(image.wow_m2_texture, 'path', '') or '')
    existing_fdid = max(0, int(getattr(image.wow_m2_texture, 'file_data_id', 0) or 0))
    existing_fdid_path = M2File._normalize_path(getattr(image.wow_m2_texture, 'file_data_id_path', '') or '')
    try:
        game_data = load_game_data()
    except Exception:
        game_data = None

    image.wow_m2_texture.texture_type = '0'
    image.wow_m2_texture.path = wow_path

    # A previously stored FileDataID is only safe if it was explicitly recorded
    # for this exact WoW path. Matching the image path alone is not enough:
    # older versions stored stale IDs without a path association.
    if existing_fdid and existing_fdid_path == normalized_path:
        image.wow_m2_texture.file_data_id = existing_fdid
        image.wow_m2_texture.file_data_id_path = wow_path
        return

    looked_up_fdid = M2File.resolve_file_data_id(wow_path, game_data) if normalized_path else 0
    if looked_up_fdid:
        image.wow_m2_texture.file_data_id = looked_up_fdid
        image.wow_m2_texture.file_data_id_path = wow_path
        return

    if existing_path != normalized_path or existing_fdid_path != normalized_path:
        image.wow_m2_texture.file_data_id = 0
        image.wow_m2_texture.file_data_id_path = ""
    elif existing_fdid:
        image.wow_m2_texture.file_data_id_path = wow_path


def _fix_uv_maps(mesh_obj):
    """
    Deja exactamente UN mapa UV llamado 'UVMap'.
    - Si ya existe 'UVMap', elimina el resto.
    - Si hay otros mapas, renombra el primero a 'UVMap' y elimina los demás.
    - Si no hay ningún mapa UV, crea uno llamado 'UVMap'.
    Devuelve el nombre del mapa UV resultante.
    """
    mesh = mesh_obj.data
    uv_layers = mesh.uv_layers

    if len(uv_layers) == 0:
        # No hay ningún mapa: crear uno
        uv_layers.new(name='UVMap')
        return 'UVMap'

    # Renombrar el primero a UVMap si no lo es ya
    first = uv_layers[0]
    if first.name != 'UVMap':
        first.name = 'UVMap'

    # Eliminar todos los mapas extra (índice > 0)
    while len(uv_layers) > 1:
        uv_layers.remove(uv_layers[1])

    return 'UVMap'


def _reset_geoset_enabled(mesh_obj):
    """Pone enabled=False en el geoset del mesh para que el callback lo acepte."""
    try:
        mesh_obj.wow_m2_geoset.enabled = False
    except Exception:
        pass


def _reset_material_enabled(mat):
    """Pone enabled=False en el material para que el callback lo acepte."""
    try:
        mat.wow_m2_material.enabled = False
    except Exception:
        pass


def _reset_texture_enabled(img):
    """Pone enabled=False en la textura para que el callback lo acepte."""
    try:
        img.wow_m2_texture.enabled = False
    except Exception:
        pass


def _remove_existing_geoset_slot(scene, mesh_obj):
    """Elimina el slot de geoset existente para este mesh (evita duplicados)."""
    geosets = scene.wow_m2_root_elements.geosets
    for i in range(len(geosets) - 1, -1, -1):
        if geosets[i].pointer == mesh_obj or geosets[i].name == mesh_obj.name:
            geosets.remove(i)


def _remove_existing_material_slot(scene, mat):
    """Elimina el slot de material existente para este material (evita duplicados)."""
    materials = scene.wow_m2_root_elements.materials
    for i in range(len(materials) - 1, -1, -1):
        if materials[i].pointer == mat or materials[i].name == mat.name:
            materials.remove(i)


def _remove_existing_texture_slot(scene, img):
    """Elimina el slot de textura existente para esta imagen (evita duplicados)."""
    textures = scene.wow_m2_root_elements.textures
    for i in range(len(textures) - 1, -1, -1):
        if textures[i].pointer == img or textures[i].name == img.name:
            textures.remove(i)


def _apply_transforms(context, mesh_obj):
    """Aplica escala y rotación al mesh (necesario antes del skinning)."""
    try:
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        context.view_layer.objects.active = mesh_obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    except Exception:
        pass


def _recalculate_normals_outside(context, mesh_obj):
    """Recalcula normales hacia afuera (evita caras invertidas = modelo invisible)."""
    try:
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        context.view_layer.objects.active = mesh_obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass


def _get_or_create_image(mesh_obj):
    """
    Busca una imagen existente en los materiales del mesh.
    Si no encuentra ninguna, crea un placeholder morado.
    """
    for mat in mesh_obj.data.materials:
        if mat and mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    return node.image
    # Placeholder
    img_name = f"{mesh_obj.name}_Tex"
    if img_name in bpy.data.images:
        return bpy.data.images[img_name]
    img = bpy.data.images.new(img_name, width=4, height=4)
    img.generated_color = (0.8, 0.2, 0.8, 1.0)
    return img


def _setup_shader_nodes(mat, img):
    """
    Crea/actualiza los nodos del shader para previsualización en Viewport.
    Estructura mínima compatible con el addon: Tex1_image → Tex1_mapping → BSDF
    """
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Nodo imagen principal (Tex1_image — nombre que usa el addon internamente)
    tex1 = nodes.get('Tex1_image')
    if tex1 is None:
        tex1 = nodes.new('ShaderNodeTexImage')
        tex1.name = 'Tex1_image'
        tex1.location = (-600, 300)
    tex1.image = img

    # Nodo UV Map (Tex1_mapping — nombre que usa el addon)
    uv_node = nodes.get('Tex1_mapping')
    if uv_node is None:
        uv_node = nodes.new('ShaderNodeUVMap')
        uv_node.name = 'Tex1_mapping'
        uv_node.location = (-800, 300)
    uv_node.uv_map = 'UVMap'

    # Conectar UV → Imagen → BSDF
    if not tex1.inputs['Vector'].is_linked:
        links.new(uv_node.outputs['UV'], tex1.inputs['Vector'])

    bsdf = nodes.get('Principled BSDF')
    if bsdf and not bsdf.inputs['Base Color'].is_linked:
        links.new(tex1.outputs['Color'], bsdf.inputs['Base Color'])

    # Nodo placeholder para Tex2_mapping (el addon lo busca)
    uv2 = nodes.get('Tex2_mapping')
    if uv2 is None:
        uv2 = nodes.new('ShaderNodeUVMap')
        uv2.name = 'Tex2_mapping'
        uv2.location = (-800, 100)
        uv2.uv_map = 'UVMap'


# ══════════════════════════════════════════════════════════════════
#  OPERATOR
# ══════════════════════════════════════════════════════════════════

class M2_OT_auto_setup_custom_model(bpy.types.Operator):
    """Auto-Setup Modelo Custom M2 — configura estructura, skinning,
geoset, material y textura con un solo clic. (v2 — corregido)"""

    bl_idname  = "scene.m2_auto_setup_custom_model"
    bl_label   = "Crear Estructura M2"
    bl_description = (
        "Configura automáticamente tu modelo 3D como M2: crea estructura, "
        "skinning a $root, registra geoset, material y textura con un clic. "
        "Corrige UV maps, normales, rutas y orden de registro."
    )
    bl_options = {'UNDO', 'REGISTER'}

    # ── Propiedades del diálogo ────────────────────────────────────
    model_name: bpy.props.StringProperty(
        name="Nombre del modelo",
        default="M2_Model",
        description="Nombre base para el armature M2 (solo se usa si no hay estructura aún)"
    )

    texture_wow_path: bpy.props.StringProperty(
        name="Ruta WoW de la textura (.blp)",
        default="Textures\\MiModelo\\textura.blp",
        description=(
            "Ruta interna WoW del archivo .blp. Se usa para resolver el ID "
            "si no se introduce manualmente."
        )
    )

    texture_file_data_id: bpy.props.IntProperty(
        name="ID numérica del .blp",
        default=0,
        min=0,
        description=(
            "FileDataID de la textura. Si es mayor que 0, el exportador lo usara "
            "como TXID con prioridad sobre la ruta."
        )
    )

    skin_file_data_id: bpy.props.IntProperty(
        name="ID numérica del archivo .skin",
        default=0,
        min=0,
        description=(
            "FileDataID del archivo .skin principal. En M2 modernos se exporta "
            "como SFID para que el cliente encuentre el skin correcto."
        )
    )

    fix_normals: bpy.props.BoolProperty(
        name="Recalcular normales hacia afuera",
        description=(
            "Recalcula las normales de todas las caras hacia afuera. "
            "Actívalo si el modelo era invisible o las caras se veían del revés."
        ),
        default=True
    )

    apply_transforms: bpy.props.BoolProperty(
        name="Aplicar escala y rotación",
        description=(
            "Aplica la escala y rotación del objeto antes de hacer el skinning. "
            "Recomendado si tu modelo tiene escala != 1.0"
        ),
        default=True
    )

    # ── Poll ───────────────────────────────────────────────────────
    @classmethod
    def poll(cls, context):
        return (
            context.scene is not None
            and context.active_object is not None
            and context.active_object.type == 'MESH'
        )

    # ── Execute ────────────────────────────────────────────────────
    def execute(self, context):
        scene    = context.scene
        mesh_obj = context.active_object

        if mesh_obj is None or mesh_obj.type != 'MESH':
            self.report({'ERROR'}, "Selecciona un objeto MESH antes de continuar.")
            return {'CANCELLED'}

        # Guardamos el modo actual para restaurarlo al final
        prev_mode = mesh_obj.mode

        # ── 0. Normalizar ruta de textura ──────────────────────────
        wow_path = _normalize_wow_path(self.texture_wow_path)
        if not wow_path.lower().endswith('.blp'):
            self.report({'WARNING'},
                        f"La ruta '{wow_path}' no termina en .blp — revísala.")

        # ── 1. Asegurarse de estar en Object Mode ──────────────────
        if mesh_obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # ── 2. Aplicar escala/rotación (opcional) ─────────────────
        if self.apply_transforms:
            _apply_transforms(context, mesh_obj)

        # ── 3. Recalcular normales (opcional) ─────────────────────
        if self.fix_normals:
            _recalculate_normals_outside(context, mesh_obj)
            # Volver a seleccionar el mesh tras el modo EDIT
            bpy.ops.object.select_all(action='DESELECT')
            mesh_obj.select_set(True)
            context.view_layer.objects.active = mesh_obj

        # ── 4. Arreglar UV maps: solo 'UVMap' ─────────────────────
        uv_name = _fix_uv_maps(mesh_obj)
        # uv_name siempre será 'UVMap' tras la llamada

        # ── 5. Estructura M2 ──────────────────────────────────────
        arm_obj = _find_m2_armature(scene)

        if arm_obj is None:
            scene.wow_scene.type = 'M2'

            arm_data = bpy.data.armatures.new(f'{self.model_name}_Armature')
            arm_obj  = bpy.data.objects.new(self.model_name, arm_data)
            context.collection.objects.link(arm_obj)

            bpy.ops.object.select_all(action='DESELECT')
            arm_obj.select_set(True)
            context.view_layer.objects.active = arm_obj

            bpy.ops.object.mode_set(mode='EDIT')
            root_bone      = arm_data.edit_bones.new('$root')
            root_bone.head = (0.0, 0.0, 0.0)
            root_bone.tail = (0.0, 0.0, 0.1)
            bpy.ops.object.mode_set(mode='OBJECT')

            try:
                arm_obj.wow_m2_globalflags.enabled = True
                arm_obj.wow_m2_globalflags.flagsLegion = {'128', '8192', '2097152'}
            except Exception:
                pass

            scene.wow_scene.version = '6'
        else:
            scene.wow_scene.type = 'M2'
            scene.wow_scene.version = '6'

        # ── 6. Skinning automático a $root ────────────────────────
        # Limpiar vertex groups previos
        for vg in list(mesh_obj.vertex_groups):
            mesh_obj.vertex_groups.remove(vg)

        vg_root = mesh_obj.vertex_groups.new(name='$root')
        all_idx = [v.index for v in mesh_obj.data.vertices]
        vg_root.add(all_idx, 1.0, 'REPLACE')

        # Modificador Armature
        arm_mod = mesh_obj.modifiers.get('Armature')
        if arm_mod is None:
            arm_mod = mesh_obj.modifiers.new(name='Armature', type='ARMATURE')
        arm_mod.object = arm_obj

        # Parent mesh → armature (sin modificador extra)
        mesh_obj.parent = arm_obj

        # ── 7. Registrar Geoset ───────────────────────────────────
        # ORDEN CORRECTO:
        #   a) limpiar slots duplicados
        #   b) reset enabled=False para que el callback lo acepte
        #   c) crear slot vacío
        #   d) asignar pointer → el callback pone enabled=True
        _remove_existing_geoset_slot(scene, mesh_obj)
        _reset_geoset_enabled(mesh_obj)

        geoset_slot = scene.wow_m2_root_elements.geosets.add()
        geoset_slot.pointer = mesh_obj   # callback: enabled→True, name→mesh_obj.name

        try:
            mesh_obj.wow_m2_geoset.collision_mesh = False
        except Exception:
            pass

        # ── 8. Material ───────────────────────────────────────────
        mat_name = f"{mesh_obj.name}_Mat"
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            mat = bpy.data.materials.new(mat_name)

        # Añadir al mesh si no está ya
        if mat.name not in [m.name for m in mesh_obj.data.materials if m]:
            mesh_obj.data.materials.append(mat)

        # ORDEN CORRECTO para material
        _remove_existing_material_slot(scene, mat)
        _reset_material_enabled(mat)

        mat_slot = scene.wow_m2_root_elements.materials.add()
        mat_slot.pointer = mat   # callback: enabled→True

        # ── 9. Textura ────────────────────────────────────────────
        img = _get_or_create_image(mesh_obj)

        # ORDEN CORRECTO para textura
        _remove_existing_texture_slot(scene, img)
        _reset_texture_enabled(img)

        tex_slot = scene.wow_m2_root_elements.textures.add()
        tex_slot.pointer = img   # callback: enabled→True

        # Propiedades WoW de la imagen (DESPUÉS del registro)
        try:
            _assign_texture_path_and_fdid(img, wow_path)
            if self.texture_file_data_id > 0:
                img.wow_m2_texture.file_data_id = int(self.texture_file_data_id)
                img.wow_m2_texture.file_data_id_path = wow_path
        except Exception:
            try:
                img.wow_m2_texture.texture_type = '0'
                img.wow_m2_texture.path = wow_path
                img.wow_m2_texture.file_data_id = int(self.texture_file_data_id) if self.texture_file_data_id > 0 else 0
                img.wow_m2_texture.file_data_id_path = wow_path if self.texture_file_data_id > 0 else ""
            except Exception:
                pass

        # ── 10. Enlace material → textura (DESPUÉS de registrar ambos) ──
        try:
            mat.wow_m2_material.texture_1         = img
            mat.wow_m2_material.texture_1_mapping = 'UVMap'   # el UV map que fijamos
        except Exception:
            pass

        if self.skin_file_data_id > 0:
            try:
                scene.wow_scene.m2_skin_file_data_ids = str(int(self.skin_file_data_id))
            except Exception:
                pass

        # ── 11. Configurar nodos del Shader ──────────────────────
        _setup_shader_nodes(mat, img)

        # ── 12. Restaurar selección al mesh ───────────────────────
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        context.view_layer.objects.active = mesh_obj

        # ── Informe final ─────────────────────────────────────────
        final_fdid = int(getattr(img.wow_m2_texture, 'file_data_id', 0) or 0)
        self.report(
            {'INFO'},
            f"Auto-Setup OK — '{mesh_obj.name}' listo como M2. "
            f"UV: '{uv_name}'  |  Textura: {wow_path}  |  TXID: {final_fdid or 'sin FDID'}"
            f"  |  SFID: {self.skin_file_data_id or 'por nombre'}"
        )
        return {'FINISHED'}

    # ── Invoke: abrir diálogo ─────────────────────────────────────
    def invoke(self, context, event):
        if context.active_object:
            self.model_name = context.active_object.name
        try:
            skin_ids = getattr(context.scene.wow_scene, 'm2_skin_file_data_ids', '') or ''
            first_skin_id = skin_ids.split(',', 1)[0].strip()
            if first_skin_id and int(first_skin_id) > 0:
                self.skin_file_data_id = int(first_skin_id)
        except Exception:
            pass
        return context.window_manager.invoke_props_dialog(self, width=460)

    # ── Draw: UI del diálogo ──────────────────────────────────────
    def draw(self, context):
        layout  = self.layout
        mesh    = context.active_object
        has_arm = _find_m2_armature(context.scene) is not None

        # Estado actual — estructura M2
        if not has_arm:
            box = layout.box()
            box.label(text="Nueva estructura M2", icon='ARMATURE_DATA')
            box.prop(self, 'model_name')
        else:
            layout.label(
                text="Estructura M2 detectada — se reutilizará.",
                icon='CHECKMARK'
            )

        layout.separator()

        # UV maps actuales
        if mesh:
            uv_layers = mesh.data.uv_layers
            box_uv = layout.box()
            box_uv.label(text="UV Maps actuales del mesh:", icon='UV')
            if len(uv_layers) == 0:
                box_uv.label(text="  ⚠  Sin UV maps — se creará 'UVMap'",
                             icon='ERROR')
            elif len(uv_layers) == 1 and uv_layers[0].name == 'UVMap':
                box_uv.label(text=f"  ✔  '{uv_layers[0].name}' — correcto",
                             icon='CHECKMARK')
            else:
                for uv in uv_layers:
                    icon = 'CHECKMARK' if uv.name == 'UVMap' else 'X'
                    action = "se conservará" if uv.name == 'UVMap' else "se ELIMINARÁ"
                    box_uv.label(
                        text=f"  {'✔' if icon == 'CHECKMARK' else '✖'}  '{uv.name}' — {action}",
                        icon=icon
                    )
            if len(uv_layers) > 1 or (len(uv_layers) == 1 and uv_layers[0].name != 'UVMap'):
                box_uv.label(
                    text="→ Se dejará solo 'UVMap' (necesario para WoW)",
                    icon='INFO'
                )

        layout.separator()

        # Ruta de textura
        box2 = layout.box()
        box2.label(text="Ruta WoW de la textura (.blp)", icon='IMAGE_DATA')
        box2.prop(self, 'texture_wow_path', text='')
        box2.prop(self, 'texture_file_data_id')
        box2.prop(self, 'skin_file_data_id')
        # Preview ruta normalizada
        if self.texture_wow_path.strip():
            normalized = _normalize_wow_path(self.texture_wow_path)
            box2.label(text=f"  → {normalized}", icon='RIGHTARROW')
        if self.texture_file_data_id > 0:
            box2.label(text=f"  → TXID manual: {self.texture_file_data_id}", icon='CHECKMARK')
        if self.skin_file_data_id > 0:
            box2.label(text=f"  → SFID skin: {self.skin_file_data_id}", icon='CHECKMARK')

        layout.separator()

        # Opciones adicionales
        box3 = layout.box()
        box3.label(text="Opciones:", icon='PREFERENCES')
        box3.prop(self, 'fix_normals')
        box3.prop(self, 'apply_transforms')

        layout.separator()

        # Resumen de acciones
        box4 = layout.box()
        box4.label(text="Se hará automáticamente:", icon='PREFERENCES')
        col = box4.column(align=True)
        if not has_arm:
            col.label(text="  ✔  Crear armature M2 con hueso $root")
        col.label(text="  ✔  Arreglar UV maps → solo 'UVMap'")
        col.label(text="  ✔  Skinning completo a $root (peso 1.0)")
        col.label(text="  ✔  Modificador Armature + Parent")
        col.label(text="  ✔  Registrar Geoset (orden correcto)")
        col.label(text="  ✔  Crear y registrar Material")
        col.label(text="  ✔  Crear y registrar Textura con la ruta WoW")
        col.label(text="  ✔  Enlazar Material → Textura → UV 'UVMap'")
        col.label(text="  ✔  Configurar nodos Shader para previsualización")
        if self.fix_normals:
            col.label(text="  ✔  Recalcular normales hacia afuera")
        if self.apply_transforms:
            col.label(text="  ✔  Aplicar escala y rotación")
