import bpy
from ..enums import *


def _update_texture_path(self, context):
    try:
        from ....pywowlib.m2_file import M2File
        from ....utils.misc import load_game_data
    except Exception:
        return

    normalized_path = M2File._normalize_path(getattr(self, 'path', '') or '')
    source_path = M2File._normalize_path(getattr(self, 'file_data_id_path', '') or '')

    if not normalized_path:
        self.file_data_id = 0
        self.file_data_id_path = ""
        return

    if self.file_data_id and source_path == normalized_path:
        return

    try:
        game_data = load_game_data()
    except Exception:
        game_data = None

    file_data_id = M2File.resolve_file_data_id(self.path, game_data)
    if file_data_id:
        self.file_data_id = file_data_id
        self.file_data_id_path = self.path
    elif source_path != normalized_path:
        self.file_data_id = 0
        self.file_data_id_path = ""


def _update_texture_file_data_id(self, context):
    current_path = getattr(self, 'path', '') or ''
    if int(getattr(self, 'file_data_id', 0) or 0) > 0:
        self.file_data_id_path = current_path
        return

    try:
        from ....pywowlib.m2_file import M2File
    except Exception:
        self.file_data_id_path = ""
        return

    if M2File._normalize_path(getattr(self, 'file_data_id_path', '') or '') == M2File._normalize_path(current_path):
        self.file_data_id_path = ""



class SetDefaultTexture(bpy.types.Operator):
    """Sets the texture to the default value 'textures\\ShaneCube.blp'"""
    bl_idname = "wow_m2_texture.set_default_texture"
    bl_label = "Set Default Texture"

    img_name:  bpy.props.StringProperty(options={'HIDDEN'})

    def execute(self, context):
        edit_image = bpy.data.images[self.img_name]
        edit_image.wow_m2_texture.path = "textures\\ShaneCube.blp"
        edit_image.wow_m2_texture.file_data_id = 0
        edit_image.wow_m2_texture.file_data_id_path = ""
        return {'FINISHED'}

class M2_PT_texture_panel(bpy.types.Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "image"
    bl_label = "M2 Texture"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(context.edit_image.wow_m2_texture, "flags")
        col.separator()
        col.prop(context.edit_image.wow_m2_texture, "texture_type")
        col.separator()
        # only show path setting if texture type is hardcoded
        if context.edit_image.wow_m2_texture.texture_type == "0":
            col.prop(context.edit_image.wow_m2_texture, "path", text='Path')
            col.prop(context.edit_image.wow_m2_texture, "file_data_id", text='FileDataID')
            if(len(context.edit_image.wow_m2_texture.path) == 0):
                op = col.operator(SetDefaultTexture.bl_idname, text="Set Default Texture", icon="CONSOLE")
                # todo: not a great method, but it should work reliably since this updates every frame
                op.img_name = context.edit_image.name

    @classmethod
    def poll(cls, context):
        return (context.scene is not None
                and context.scene.wow_scene.type == 'M2'
                and context.image is not None)


class WowM2TexturePropertyGroup(bpy.types.PropertyGroup):
    
    enabled:  bpy.props.BoolProperty()

    flags:  bpy.props.EnumProperty(
        name="Texture flags",
        description="WoW  M2 texture flags",
        items=TEXTURE_FLAGS,
        options={"ENUM_FLAG"},
        default={'1', '2'}
        )

    texture_type:  bpy.props.EnumProperty(
        name="Texture type",
        description="WoW  M2 texture type",
        items=TEXTURE_TYPES
        )

    path:  bpy.props.StringProperty(
        name='Path',
        description='Path to .blp file in wow file system.',
        update=_update_texture_path
    )

    file_data_id: bpy.props.IntProperty(
        name='FileDataID',
        description='Modern WoW FileDataID used for TXID export when available.',
        default=0,
        min=0,
        update=_update_texture_file_data_id
    )

    file_data_id_path: bpy.props.StringProperty(
        name='FileDataID Path',
        description='Internal helper storing the WoW texture path associated with the current FileDataID.',
        default='',
        options={'HIDDEN'}
    )

    variant_color_hint: bpy.props.BoolProperty(
        name="",
        description="Si la primera textura es 0 y del tipo Object Skin, el m2 cargará el blp correspondiente a su variante de color... _green.blp _blue.blp etc.",
        default=False,
        options={'HIDDEN'}
    )

    # self_pointer: bpy.props.PointerProperty(type=bpy.types.Image)

def register():
    bpy.types.Image.wow_m2_texture = bpy.props.PointerProperty(type=WowM2TexturePropertyGroup)


def unregister():
    del bpy.types.Image.wow_m2_texture
