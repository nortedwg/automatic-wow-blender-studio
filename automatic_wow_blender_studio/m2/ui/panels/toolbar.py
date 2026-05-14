import bpy
from ..enums import *

_TEXTURE_TYPE_TOOLTIPS_ES = {
    "1": (
        "1   Skin\n"
        "La piel del cuerpo del personaje. El juego la asigna automáticamente\n"
        "según la raza y el color de piel elegido en la creación del personaje."
    ),
    "2": (
        "2   Object Skin / Cape\n"
        "La textura del equipo que lleva puesto el personaje (armaduras, capas,\n"
        "ropas). El juego la cambia según el item equipado en ese momento. "
        "Si tiene variantes, estilo azul, verde, etc, se mostrarán esas texturas. "
        "Deja la ID en 0 para ello."
    ),
    "3": (
        "3   Weapon Blade\n"
        "La textura de la hoja de un arma (espada, hacha, etc.).\n"
        "La asigna el juego cuando se equipa el arma."
    ),
    "4": (
        "4   Weapon Handle\n"
        "La textura de la empuñadura/mango del arma.\n"
        "Funciona igual que el tipo 3 pero para la parte del palo o mango."
    ),
    "5": (
        "5   Environment\n"
        "Un reflejo del entorno proyectado sobre el modelo.\n"
        "Lo genera el juego automáticamente para simular que una superficie\n"
        "metálica o mojada refleja lo que tiene alrededor."
    ),
    "6": (
        "6   Hair\n"
        "La textura del pelo del personaje. Cambia según el peinado y color\n"
        "de pelo elegidos en la personalización."
    ),
    "7": (
        "7   Facial Hair\n"
        "La textura del vello facial: barba, bigote, patillas, cejas.\n"
        "Funciona igual que el pelo pero para la zona de la cara."
    ),
    "8": (
        "8   Skin Extra\n"
        "Una capa extra pintada encima de la piel base. Se usa para tatuajes,\n"
        "marcas, escamas u otros detalles propios de cada raza.\n"
        "Ejemplo: los tatuajes de los Elfo de la Noche."
    ),
    "9": (
        "9   UI Skin\n"
        "Textura usada en elementos 3D de la interfaz del juego,\n"
        "como las miniaturas de personaje que aparecen en algunos menús."
    ),
    "10": (
        "10   Tauren Mane\n"
        "La textura de la melena de los Tauren. Tiene su propio slot separado\n"
        "porque la melena usa una malla y unas UVs distintas al pelo normal."
    ),
    "11": (
        "11   Monster 1\n"
        "Primera textura de piel de una criatura. El juego la elige según\n"
        "la variante visual de esa criatura (por ejemplo, un lobo gris\n"
        "vs un lobo negro son el mismo modelo con distinta textura aquí)."
    ),
    "12": (
        "12   Monster 2\n"
        "Segunda textura de piel de criatura. Algunos modelos usan varias\n"
        "capas superpuestas para componer su aspecto final."
    ),
    "13": (
        "13   Monster 3\n"
        "Tercera textura de piel de criatura. Lo mismo que los dos anteriores\n"
        "pero para modelos con más zonas diferenciadas de color."
    ),
    "14": (
        "14   Item Icon\n"
        "El icono 2D del objeto. Se usa en superficies planas dentro del\n"
        "modelo 3D que deben mostrar la imagen del item\n"
        "(por ejemplo, en displays decorativos dentro del juego)."
    ),
    "15": (
        "15   Guild Background Color\n"
        "El color de fondo del escudo/estandarte del gremio.\n"
        "Lo genera el juego con el color que eligió el líder del gremio."
    ),
    "16": (
        "16   Guild Emblem Color\n"
        "El color del símbolo principal del escudo del gremio."
    ),
    "17": (
        "17   Guild Border Color\n"
        "El color del borde decorativo alrededor del escudo del gremio."
    ),
    "18": (
        "18   Guild Emblem\n"
        "La forma del símbolo del gremio (el dibujo en sí, no el color).\n"
        "Se combina con el tipo 16 para dar el resultado final."
    ),
    "19": (
        "19   Eyes\n"
        "La textura de los ojos del personaje. Cambia según el color\n"
        "de ojos elegido en la personalización."
    ),
    "20": (
        "20   Accessory\n"
        "La textura de un accesorio decorativo incorporado al modelo\n"
        "(pendiente, joya, adorno facial). Puede cambiar según variantes."
    ),
    "21": (
        "21   Secondary Skin\n"
        "Una segunda capa de piel independiente. La usan razas que necesitan\n"
        "dos capas de piel distintas, por ejemplo para manchas o patrones\n"
        "corporales que no forman parte de la piel principal."
    ),
    "22": (
        "22   Secondary Hair\n"
        "Una segunda textura de pelo independiente. Para razas con elementos\n"
        "capilares complejos (trenzas, mechones extra) que no encajan\n"
        "en la misma textura que el pelo principal."
    ),
    "23": (
        "23   Unknown\n"
        "Sin documentación oficial. Por su posición en la lista probablemente\n"
        "es otra capa extra del sistema de personalización de personaje,\n"
        "añadida en expansiones recientes."
    ),
    "24": (
        "24   Unknown\n"
        "Igual que el tipo 23. Slot añadido para soportar las opciones\n"
        "ampliadas de personalización de Shadowlands / Dragonflight."
    ),
}


class M2_OT_texture_type_info(bpy.types.Operator):
    """Tooltip helper for texture type."""

    bl_idname = "scene.m2_texture_type_info"
    bl_label = ""
    bl_options = {'INTERNAL'}

    tex_type: bpy.props.StringProperty(options={'HIDDEN'})

    @classmethod
    def description(cls, context, properties):
        key = str(getattr(properties, "tex_type", "") or "")
        if key in _TEXTURE_TYPE_TOOLTIPS_ES:
            return _TEXTURE_TYPE_TOOLTIPS_ES[key]
        if key == "0":
            return (
                "0   Hardcoded\n"
                "Textura fija. Normalmente usa ruta/ID directamente desde el archivo.\n"
                "No es reemplazada por el sistema de vestimenta."
            )
        return f"Tipo de textura {key} (sin descripción definida)."

    def execute(self, context):
        return {'FINISHED'}


def update_wow_visibility(self, context):
    values = self.m2_visibility

    for obj in self.objects:

        if 'wow_hide' not in obj:
            obj['wow_hide'] = obj.hide_get()

        if obj['wow_hide'] != obj.hide_get():
            continue

        if obj.type == "MESH": # only geoset and collision ?
            if  obj.wow_m2_geoset:
                if obj.wow_m2_geoset.collision_mesh:
                    obj.hide_set('6' not in values)
                if obj.wow_m2_geoset.enabled and obj.wow_m2_geoset.collision_mesh == False:
                    obj.hide_set('0' not in values)

        elif obj.wow_m2_attachment.enabled:
            obj.hide_set('1' not in values)
        elif obj.wow_m2_event.enabled:
            obj.hide_set('2' not in values)
        elif obj.wow_m2_particle.enabled:
            obj.hide_set('4' not in values)
        elif obj.type == "LIGHT" and obj.wow_m2_light.enabled:
            obj.hide_set('3' not in values)
        elif obj.type == "CAMERA" and obj.wow_m2_camera.enabled:
            obj.hide_set('5' not in values)
        elif obj.type == "ARMATURE": # and obj.data.edit_bones[0].wow_m2_bone: # wow_m2_bone. check if first armature's bone is m2 bone
            obj.hide_set('7' not in values)
        else:
            print("unknown type")
            print(obj.name)
            print(obj.type)
        
        obj['wow_hide'] = obj.hide_get()

class M2_PT_tools_panel_object_mode_structure(bpy.types.Panel):
    bl_label = 'Estructura M2'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Crear Estructura", icon='ARMATURE_DATA')
        col.separator(factor=0.5)

        row = col.row(align=True)
        row.enabled = context.active_object is not None and context.active_object.type == 'MESH'
        row.operator(
            "scene.m2_auto_setup_custom_model",
            text="Generar automáticamente",
            icon='PLAY'
        )

        if not row.enabled:
            col.label(text="Selecciona un mesh para activarlo.", icon='INFO')

    @classmethod
    def poll(cls, context):
        return context.scene is not None


class M2_OT_skin_id_add(bpy.types.Operator):
    """Añade una ID .skin vacía a la lista"""
    bl_idname = 'scene.m2_skin_id_add'
    bl_label = 'Añadir un .skin'
    bl_options = {'UNDO', 'INTERNAL'}

    def execute(self, context):
        ids = _get_skin_ids(context.scene)
        ids.append('0')
        _set_skin_ids(context.scene, ids)
        return {'FINISHED'}


class M2_OT_skin_id_remove(bpy.types.Operator):
    """Elimina una ID .skin de la lista"""
    bl_idname = 'scene.m2_skin_id_remove'
    bl_label = 'Eliminar ID .skin'
    bl_options = {'UNDO', 'INTERNAL'}

    index: bpy.props.IntProperty(options={'HIDDEN'})

    def execute(self, context):
        ids = _get_skin_ids(context.scene)
        if 0 <= self.index < len(ids):
            ids.pop(self.index)
        _set_skin_ids(context.scene, ids)
        return {'FINISHED'}


class M2_OT_skin_id_set(bpy.types.Operator):
    """Edita el valor de una ID .skin"""
    bl_idname = 'scene.m2_skin_id_set'
    bl_label = 'Editar ID .skin'
    bl_options = {'UNDO', 'INTERNAL'}

    index: bpy.props.IntProperty(options={'HIDDEN'})
    value: bpy.props.StringProperty(name='ID .skin', default='')

    def invoke(self, context, event):
        ids = _get_skin_ids(context.scene)
        if 0 <= self.index < len(ids):
            self.value = ids[self.index]
        return context.window_manager.invoke_props_dialog(self, width=240)

    def draw(self, context):
        self.layout.prop(self, 'value', text='ID')

    def execute(self, context):
        ids = _get_skin_ids(context.scene)
        while len(ids) <= self.index:
            ids.append('0')
        ids[self.index] = self.value.strip()
        _set_skin_ids(context.scene, ids)
        return {'FINISHED'}


def _get_skin_ids(scene):
    raw = (scene.wow_scene.m2_skin_file_data_ids or '').strip()
    return [x.strip() for x in raw.split(',') if x.strip()] if raw else []


def _set_skin_ids(scene, ids):
    scene.wow_scene.m2_skin_file_data_ids = ','.join(ids)


class M2_OT_m2_texture_add(bpy.types.Operator):
    """Añade una textura M2 (slot + imagen) a la lista"""
    bl_idname = 'scene.m2_texture_add'
    bl_label = 'Añadir textura M2'
    bl_options = {'UNDO', 'INTERNAL'}

    def execute(self, context):
        scene = context.scene
        root = getattr(scene, 'wow_m2_root_elements', None)
        if root is None or not hasattr(root, 'textures'):
            return {'CANCELLED'}

        # Crear una imagen placeholder para poder editar Path/ID en el panel
        img_name = "M2_Texture"
        i = 1
        while img_name in bpy.data.images:
            i += 1
            img_name = f"M2_Texture.{str(i).zfill(3)}"

        img = bpy.data.images.new(img_name, 4, 4)
        img.generated_color = (0.8, 0.2, 0.8, 1.0)

        # Asegurar que el slot acepta el pointer (poll requiere enabled=False)
        try:
            img.wow_m2_texture.enabled = False
        except Exception:
            pass
        try:
            img.wow_m2_texture.texture_type = '0'
        except Exception:
            pass

        slot = root.textures.add()
        slot.pointer = img
        scene.wow_m2_root_elements.cur_texture = max(0, len(root.textures) - 1)
        return {'FINISHED'}


class M2_OT_m2_texture_remove(bpy.types.Operator):
    """Elimina una textura M2 de la lista"""
    bl_idname = 'scene.m2_texture_remove'
    bl_label = 'Eliminar textura M2'
    bl_options = {'UNDO', 'INTERNAL'}

    index: bpy.props.IntProperty(options={'HIDDEN'})

    def execute(self, context):
        scene = context.scene
        root = getattr(scene, 'wow_m2_root_elements', None)
        if root is None or not hasattr(root, 'textures'):
            return {'CANCELLED'}

        col = root.textures
        if 0 <= self.index < len(col):
            item = col[self.index]
            img = getattr(item, 'pointer', None)
            if img:
                try:
                    img.wow_m2_texture.enabled = False
                except Exception:
                    pass
            col.remove(self.index)
            root.cur_texture = min(root.cur_texture, max(0, len(col) - 1))
        return {'FINISHED'}


class M2_PT_datos_m2(bpy.types.Panel):
    bl_label = 'Datos del M2'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ── ID .skin ─────────────────────────────────────────────────
        box_skin = layout.box()
        box_skin.label(text='ID .skin', icon='MOD_SKIN')

        ids = _get_skin_ids(scene)
        for i, val in enumerate(ids):
            row = box_skin.row(align=True)
            # Display the value; clicking opens edit dialog
            op_edit = row.operator('scene.m2_skin_id_set', text=val or '(vacío)', emboss=True)
            op_edit.index = i
            op_edit.value = val
            op_rem = row.operator('scene.m2_skin_id_remove', text='', icon='X')
            op_rem.index = i

        row_add = box_skin.row()
        row_add.operator('scene.m2_skin_id_add', text='Añadir un .skin', icon='ADD')

        # ── Texturas M2 ───────────────────────────────────────────────
        layout.separator(factor=0.5)
        box_tex = layout.box()
        box_tex.label(text='Texturas M2:', icon='IMAGE_DATA')

        root = getattr(scene, 'wow_m2_root_elements', None)
        textures_col = root.textures if root and hasattr(root, 'textures') else None

        if not textures_col or len(textures_col) == 0:
            box_tex.label(text='No hay texturas M2 configuradas.', icon='INFO')
        else:
            for i, slot in enumerate(textures_col):
                img = getattr(slot, 'pointer', None)
                sub = box_tex.box()

                row_head = sub.row(align=True)
                row_head.label(text='BLP:', icon='IMAGE_RGB')
                op_rem = row_head.operator('scene.m2_texture_remove', text='', icon='X')
                op_rem.index = i

                if not img:
                    sub.label(text='(slot vacío)', icon='INFO')
                    continue

                tex = img.wow_m2_texture
                row_type = sub.row(align=True)
                row_type.label(text="Tipo Textura:")
                row_type.prop(tex, "texture_type", text="")
                op_info = row_type.operator("scene.m2_texture_type_info", text="", icon='INFO', emboss=False)
                op_info.tex_type = str(getattr(tex, "texture_type", "") or "")

                if getattr(tex, "texture_type", "0") == "0":
                    sub.prop(tex, 'path', text='Ruta')
                    sub.prop(tex, 'file_data_id', text='ID')
                else:
                    sub.prop(tex, 'file_data_id', text='ID')

                if i == 0 and getattr(tex, 'file_data_id', None) == 0 and str(getattr(tex, "texture_type", "") or "") == "2":
                    row_hint = sub.row(align=True)
                    row_hint.prop(tex, "variant_color_hint", text="", icon='INFO', emboss=False)
                    row_hint.label(
                        text="Si la primera textura es 0 y del tipo Object Skin, el m2 cargará el blp correspondiente a su variante de color... _green.blp _blue.blp etc."
                    )

        row_add_tex = box_tex.row()
        row_add_tex.operator('scene.m2_texture_add', text='Añadir textura', icon='ADD')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'


class M2_PT_tools_object_mode_display(bpy.types.Panel):
    bl_label = 'M2 Display'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'
    bl_order = 2

    def draw(self, context):
        layout = self.layout.split()
        col = layout.column(align=True)
        col_row = col.row()
        col_row.column(align=True).prop(context.scene, "m2_visibility")
        col_col = col_row.column(align=True)
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_geoset'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_attachment'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_event'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_particle'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_camera'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'wow_m2_light'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'Collision'
        col_col.operator("scene.wow_m2_select_entity", text='', icon='VIEWZOOM').entity = 'Skeleton'


    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'


class M2_PT_tools_panel_object_mode_add_to_scene(bpy.types.Panel):
    bl_label = 'Add to scene'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'
    bl_order = 3

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)

        # ──────────────────────────────────────────────────────────────────
        #  Botones originales (setup manual)
        # ──────────────────────────────────────────────────────────────────
        col.label(text="Setup Manual:", icon='TOOL_SETTINGS')
        col.separator()
        col.operator("scene.wow_m2_create_structure", text="Crear estructura M2", icon="ARMATURE_DATA")
        col.separator()

        col1_col = col.column(align=True)
        col1_row2 = col1_col.row(align=True)
        col1_row2.operator("scene.m2_add_attachment", text='Attachment', icon='POSE_HLT')
        col1_row2.operator("scene.m2_add_event", text='Event', icon='POSE_HLT')

        col1_row3 = col1_col.row(align=True)
        col1_row3.operator("scene.wow_m2_texture_import", text='Texture', icon='IMAGE_DATA')

        col.separator()

    @classmethod
    def poll(cls, context):
        return context.scene is not None


class M2_PT_tools_object_mode_actions(bpy.types.Panel):
    bl_label = 'Actions'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = 'objectmode'
    bl_category = 'M2'
    bl_order = 4

    def draw(self, context):
        layout = self.layout.split()
        col = layout.column(align=True)
        col.separator()
        box_col = col.column(align=True)

        col1_row1 = box_col.row(align=True)  
    
        col1_row1.operator("scene.m2_ot_enable_drivers", text='Drivers ON', icon='RADIOBUT_ON')
        col1_row1.operator("scene.m2_ot_disable_drivers", text='Drivers OFF', icon='RADIOBUT_OFF')

        box_col.operator("scene.wow_creature_editor_toggle", text='Creature Editor', icon_value=ui_icons['WOW_STUDIO_SCALE_ADD'])

        if bpy.context.selected_objects:
            box_col.operator("scene.m2_fill_textures", text='Fill Paths', icon='SEQ_SPLITVIEW')
            
        if context.object and context.object.type == 'ARMATURE':
            box_col.operator("object.m2_bone_renamer", text='Rename', icon='CONSOLE')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'


class M2_MT_mesh_wow_components_add(bpy.types.Menu):
    bl_label = "WoW"
    bl_options = {'REGISTER'}

    def draw(self, context):
        layout = self.layout
        col = layout.column()

        col.operator("scene.wow_m2_create_structure", text='Crear estructura M2', icon='ARMATURE_DATA')
        col.operator("scene.m2_add_attachment", text='Attachment', icon='POSE_HLT')
        col.operator("scene.m2_add_event", text='Event', icon='POSE_HLT')

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.scene.wow_scene.type == 'M2'

def wow_components_add_menu_item(self, context):
    self.layout.menu("M2_MT_mesh_wow_components_add", icon_value=ui_icons['WOW_STUDIO_WOW'])


def render_viewport_toggles_right(self, context):
    if hasattr(context.scene, 'wow_scene') \
    and hasattr(context.scene.wow_scene, 'type') \
    and context.scene.wow_scene.type == 'M2':
        layout = self.layout
        row = layout.row(align=True)
        row.popover(  panel="M2_PT_tools_object_mode_display"
                    , text=''
                    , icon='HIDE_OFF'
                   )


def register():
    bpy.types.Scene.m2_visibility = bpy.props.EnumProperty(
        items=[
            ('0', "Geosets", "Display geosets", 'FILE_3D', 0x1),
            ('1', "Attachments", "Display attachments", 'POSE_HLT', 0x2),
            ('2', "Events", "Display events", 'PLUGIN', 0x4),
            ('3', "Lights", "Display lights", 'LIGHT', 0x8),
            ('4', "Particles emitters", "Display particle emitters", 'MOD_PARTICLES', 0x10),
            ('5', "Cameras", "Display cameras", 'CAMERA_DATA', 0x20),
            ('6', "Collision", "Display collision", 'CON_SIZELIMIT', 0x40),
            ('7', "Skeleton", "Display bones", 'BONE_DATA', 0x80)],
        options={'ENUM_FLAG'},
        default={'0', '1', '2', '3', '4', '5', '6', '7'},
        update=update_wow_visibility
    )


    bpy.types.VIEW3D_MT_add.prepend(wow_components_add_menu_item)
    bpy.types.VIEW3D_HT_header.append(render_viewport_toggles_right)


def unregister():
    del bpy.types.Scene.m2_visibility

    bpy.types.VIEW3D_MT_add.remove(wow_components_add_menu_item)
    bpy.types.VIEW3D_MT_add.remove(render_viewport_toggles_right)
