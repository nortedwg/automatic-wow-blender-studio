import bpy


class M2_OT_create_m2_structure(bpy.types.Operator):
    bl_idname = "scene.wow_m2_create_structure"
    bl_label = "Crear estructura M2"
    bl_description = "Crea una estructura M2 genérica lista para importar modelos 3D personalizados"
    bl_options = {'UNDO', 'REGISTER'}

    model_name: bpy.props.StringProperty(
        name="Nombre del modelo",
        default="M2_Model",
        description="Nombre base para la estructura M2"
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        scene = context.scene

        # Set scene type to M2
        scene.wow_scene.type = 'M2'

        # --- Create armature with a root bone ---
        arm_data = bpy.data.armatures.new('{}_Armature'.format(self.model_name))
        arm_obj = bpy.data.objects.new(self.model_name, arm_data)
        context.collection.objects.link(arm_obj)

        # Select and make active
        bpy.ops.object.select_all(action='DESELECT')
        arm_obj.select_set(True)
        context.view_layer.objects.active = arm_obj

        # Enter edit mode to add root bone
        bpy.ops.object.mode_set(mode='EDIT')
        root_bone = arm_data.edit_bones.new('$root')
        root_bone.head = (0.0, 0.0, 0.0)
        root_bone.tail = (0.0, 0.0, 0.1)
        bpy.ops.object.mode_set(mode='OBJECT')

        # Enable M2 global flags on the armature
        try:
            arm_obj.wow_m2_globalflags.enabled = True
        except Exception:
            pass

        # Set WoW scene version if not already set
        if not scene.wow_scene.version:
            scene.wow_scene.version = '6'

        self.report({'INFO'}, "Estructura M2 '{}' creada. Importa tu modelo 3D y asígnalo como geoset.".format(self.model_name))
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "model_name")
