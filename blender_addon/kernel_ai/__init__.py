"""Blender 4.5 の N パネルから手元の頭脳に編集台本を頼む。"""

bl_info = {
    'name': 'カーネル', 'author': 'Kernel AI contributors',
    'version': (0, 1, 0), 'blender': (4, 5, 0),
    'location': '3Dビュー > サイドバー > カーネル',
    'description': '手元のAIに台本を頼み、検査して既存の場面で実行する',
    'category': '3D View',
}

import queue
import time
from pathlib import Path

from . import core

try:
    import bpy
except ModuleNotFoundError:
    bpy = None  # Blender 不要の試験で core を読み込める。


_job = None
_retired = []
_runtime = {}


def _preferences(context):
    return context.preferences.addons[__package__].preferences


def _state(context):
    return context.window_manager.kernel_ai


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in ('VIEW_3D', 'TEXT_EDITOR'):
                area.tag_redraw()


def _scene_records(context):
    objects = sorted(context.scene.objects, key=lambda o: (not o.select_get(), o.name))
    records = []
    for obj in objects[:core.MAX_OBJECTS]:
        if obj.type == 'MESH' and obj.mode == 'EDIT':
            obj.update_from_editmode()
        mesh = obj.data if obj.type == 'MESH' else None
        records.append({
            '名前': obj.name, '種類': obj.type,
            '頂点数': len(mesh.vertices) if mesh else 0,
            '面数': len(mesh.polygons) if mesh else 0,
            '位置': [round(float(v), 5) for v in obj.matrix_world.translation],
            '大きさ': [round(float(v), 5) for v in obj.dimensions],
            '材質': [slot.material.name if slot.material else None for slot in obj.material_slots],
            '選択中': obj.select_get(), 'UV有り': bool(mesh and len(mesh.uv_layers)),
            'アクティブ': obj == context.view_layer.objects.active,
        })
    return core.scene_summary(records, len(objects))


def _set_error(state, error):
    state.error = str(error)
    state.status = str(error)[:180]


def _cancel_job():
    global _job
    if _job is not None:
        _job.cancel()
        _retired.append(_job)
        _job = None


def _poll():
    global _job
    _retired[:] = [job for job in _retired if not job.done.is_set()]
    if _job is None:
        return 0.2 if _retired else None
    state = _state(bpy.context)
    state.status = f'考え中… {int(time.monotonic() - _job.started)}秒'
    try:
        kind, result = _job.results.get_nowait()
    except queue.Empty:
        _redraw()
        return 0.2
    _job.thread.join(timeout=0.05)
    _job = None
    state.busy = False
    if kind == 'error':
        _set_error(state, result)
    else:
        try:
            script = core.extract_script(result)
            _runtime['script'] = script
            text = bpy.data.texts.get(core.TEXT_NAME) or bpy.data.texts.new(core.TEXT_NAME)
            text.clear()
            text.write(script)
            # エラーでも表示を残す。実行ボタンは検査合格後にだけ有効。
            core.validate_script(script, _runtime['kernel'])
            state.can_execute = True
            state.error = ''
            state.status = '台本ができました。内容を見てから実行してください'
        except Exception as exc:
            _set_error(state, f'{type(exc).__name__}: {exc}')
    _redraw()
    return 0.2 if _retired else None


def _start(context, repair=False):
    global _job
    state = _state(context)
    prefs = _preferences(context)
    _retired[:] = [job for job in _retired if not job.done.is_set()]
    if _job is not None or _retired:
        raise ValueError('前の通信を終了しています。少し待ってください')
    if repair:
        if state.repair_used or not state.error or not _runtime.get('request'):
            raise ValueError('直せるのは1回だけです。新しい頼みでやり直してください')
        if context.scene.as_pointer() != _runtime['scene']:
            raise ValueError('場面が変わりました。新しい頼みで考えてください')
        text = bpy.data.texts.get(core.TEXT_NAME)
        request = core.repair_request(_runtime['request'],
                                      text.as_string() if text and _runtime.get('script') else '',
                                      state.error)
    else:
        request = state.request.strip()
        if not request:
            raise ValueError('頼みを入力してください')
    # Blender データの取得も道具箱の読込も必ずメインスレッド。
    kernel = core.load_kernel(prefs.kernel_dir)
    toolbox = (Path(prefs.kernel_dir).expanduser() / 'sanjigen.md').read_text(encoding='utf-8')
    summary = _scene_records(context)
    if repair:
        state.repair_used = True
    else:
        _runtime.clear()
        _runtime.update(request=request, scene=context.scene.as_pointer(),
                        scene_name=context.scene.name_full, script='')
        state.repair_used = False
        entry = state.history.add()
        entry.request = request
        while len(state.history) > 8:
            state.history.remove(0)
    _runtime['kernel'] = kernel
    state.busy = True
    state.can_execute = False
    state.error = ''
    state.status = '考え中… 0秒'
    _job = core.RequestJob(core.system_prompt(toolbox, summary), request, prefs.model).start()
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=0.1)


if bpy is not None:
    from bpy.props import BoolProperty, CollectionProperty, PointerProperty, StringProperty

    class KERNEL_AI_Preferences(bpy.types.AddonPreferences):
        bl_idname = __package__
        kernel_dir: StringProperty(name='カーネルの場所', subtype='DIR_PATH',
                                   default=str(Path.home() / 'LocalAI_mirror' / 'kernel'))
        model: StringProperty(name='頭脳のモデル名', default='local')

        def draw(self, context):
            self.layout.prop(self, 'kernel_dir')
            self.layout.prop(self, 'model')
            self.layout.label(text='通信先: 127.0.0.1:8080（手元だけ）')

    class KERNEL_AI_History(bpy.types.PropertyGroup):
        request: StringProperty(name='頼み')

    class KERNEL_AI_State(bpy.types.PropertyGroup):
        request: StringProperty(name='頼み', maxlen=8000)
        status: StringProperty(name='状態', default='頼みを入力してください', options={'SKIP_SAVE'})
        error: StringProperty(options={'SKIP_SAVE'})
        busy: BoolProperty(options={'SKIP_SAVE'})
        can_execute: BoolProperty(options={'SKIP_SAVE'})
        repair_used: BoolProperty(options={'SKIP_SAVE'})
        show_history: BoolProperty(name='頼みの履歴', default=False)
        history: CollectionProperty(type=KERNEL_AI_History)

    class KERNEL_AI_OT_Think(bpy.types.Operator):
        bl_idname = 'kernel_ai.think'
        bl_label = '考える'
        bl_description = '手元の頭脳に台本を頼む（実行はしません）'

        def execute(self, context):
            try:
                _start(context)
            except Exception as exc:
                _set_error(_state(context), f'{type(exc).__name__}: {exc}')
                self.report({'ERROR'}, _state(context).status)
                return {'CANCELLED'}
            return {'FINISHED'}

    class KERNEL_AI_OT_Repair(bpy.types.Operator):
        bl_idname = 'kernel_ai.repair'
        bl_label = '直して'
        bl_description = 'エラーと台本を添えて1回だけ考え直す'

        def execute(self, context):
            try:
                _start(context, repair=True)
            except Exception as exc:
                self.report({'ERROR'}, str(exc))
                return {'CANCELLED'}
            return {'FINISHED'}

    class KERNEL_AI_OT_Stop(bpy.types.Operator):
        bl_idname = 'kernel_ai.stop'
        bl_label = 'やめる'
        bl_description = '考え中の通信を打ち切る（実行中のPythonの中断はできません）'

        def execute(self, context):
            _cancel_job()
            state = _state(context)
            state.busy = False
            state.can_execute = False
            state.status = 'やめました'
            state.error = ''
            return {'FINISHED'}

    class KERNEL_AI_OT_Execute(bpy.types.Operator):
        bl_idname = 'kernel_ai.execute'
        bl_label = '実行'
        bl_description = '表示中の台本を再検査し、元に戻せるようにして実行'
        bl_options = {'REGISTER', 'UNDO'}

        def execute(self, context):
            state = _state(context)
            if state.busy or not state.can_execute:
                self.report({'ERROR'}, '先に台本を考えてください')
                return {'CANCELLED'}
            if context.scene.as_pointer() != _runtime.get('scene'):
                self.report({'ERROR'}, '場面が変わりました。もう一度考えてください')
                return {'CANCELLED'}
            text = bpy.data.texts.get(core.TEXT_NAME)
            if not text:
                self.report({'ERROR'}, 'kernel_台本 がありません')
                return {'CANCELLED'}
            script = text.as_string()
            try:
                kernel = core.load_kernel(_preferences(context).kernel_dir)
                core.validate_script(script, kernel)
                if not context.preferences.edit.use_global_undo:
                    raise ValueError('プリファレンス > システム > グローバルの元に戻す を有効にしてください')
                # 画面の無い -b の試験では undo の記録ができない（画面のある Blender では必ず記録してから動かす）
                if not bpy.app.background and bpy.ops.ed.undo_push(message='カーネル') != {'FINISHED'}:
                    raise RuntimeError('元に戻す記録を作れなかったため実行しません')
            except Exception as exc:
                _set_error(state, f'{type(exc).__name__}: {exc}')
                self.report({'ERROR'}, state.status)
                return {'CANCELLED'}
            try:
                import bmesh
                import mathutils
                core.execute_script(script, kernel, bpy, bmesh, mathutils)
                state.status = '実行しました（編集 > 元に戻す で戻せます）'
                state.error = ''
            except Exception as exc:
                _set_error(state, f'{type(exc).__name__}: {exc}')
                self.report({'WARNING'}, state.status + '。途中の変更は元に戻せます')
            # 途中で失敗しても UNDO の終了記録を作る。
            return {'FINISHED'}

    class KERNEL_AI_OT_Show(bpy.types.Operator):
        bl_idname = 'kernel_ai.show_script'
        bl_label = '台本を表示'

        def execute(self, context):
            text = bpy.data.texts.get(core.TEXT_NAME)
            if not text:
                return {'CANCELLED'}
            areas = context.screen.areas
            area = next((a for a in areas if a.type == 'TEXT_EDITOR'), None)
            if area is None:
                area = next((a for a in areas if a.type in ('DOPESHEET_EDITOR', 'CONSOLE')), None)
            if area is None:
                self.report({'INFO'}, '領域をテキストエディターに変え、kernel_台本 を選んでください')
            else:
                area.type = 'TEXT_EDITOR'
                area.spaces.active.text = text
            return {'FINISHED'}

    class KERNEL_AI_PT_Panel(bpy.types.Panel):
        bl_label = 'カーネル'
        bl_idname = 'KERNEL_AI_PT_panel'
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'カーネル'

        def draw(self, context):
            state = _state(context)
            layout = self.layout
            entry = layout.column()
            entry.enabled = not state.busy
            entry.prop(state, 'request', text='頼み')
            entry.operator('kernel_ai.think')
            row = layout.row(align=True)
            run = row.row()
            run.enabled = state.can_execute and not state.busy
            run.operator('kernel_ai.execute')
            stop = row.row()
            stop.enabled = state.busy
            stop.operator('kernel_ai.stop')
            layout.label(text=state.status or '待機中', icon='TIME' if state.busy else 'INFO')
            if state.error:
                row = layout.row()
                row.enabled = not state.busy and not state.repair_used and bool(_runtime.get('request'))
                row.operator('kernel_ai.repair')
            text = bpy.data.texts.get(core.TEXT_NAME)
            if text:
                box = layout.box()
                box.label(text=core.TEXT_NAME)
                for line in text.as_string().splitlines()[:5]:
                    box.label(text=line[:65])
                box.operator('kernel_ai.show_script')
            layout.prop(state, 'show_history', icon='TRIA_DOWN' if state.show_history else 'TRIA_RIGHT')
            if state.show_history:
                for entry in reversed(list(state.history)):
                    layout.label(text=entry.request[:65])

    _CLASSES = (KERNEL_AI_Preferences, KERNEL_AI_History, KERNEL_AI_State,
                KERNEL_AI_OT_Think, KERNEL_AI_OT_Repair, KERNEL_AI_OT_Stop,
                KERNEL_AI_OT_Execute, KERNEL_AI_OT_Show, KERNEL_AI_PT_Panel)

    @bpy.app.handlers.persistent
    def _before_load(dummy):
        _cancel_job()
        _runtime.clear()
        state = _state(bpy.context)
        state.busy = state.can_execute = False
        state.error = ''
        state.status = '場面を読み替えました。新しく考えてください'

    @bpy.app.handlers.persistent
    def _after_undo(dummy):
        # Undo/Redo で Scene の RNA アドレスが替わっても同じ場面なら直せる。
        if _runtime and bpy.context.scene.name_full == _runtime.get('scene_name'):
            _runtime['scene'] = bpy.context.scene.as_pointer()


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.kernel_ai = PointerProperty(type=KERNEL_AI_State)
    bpy.app.handlers.load_pre.append(_before_load)
    bpy.app.handlers.undo_post.append(_after_undo)
    bpy.app.handlers.redo_post.append(_after_undo)


def unregister():
    _cancel_job()
    for job in _retired:
        job.cancel()
        job.thread.join(timeout=1)
    _retired.clear()
    _runtime.clear()
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)
    if _before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_before_load)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _after_undo in handlers:
            handlers.remove(_after_undo)
    del bpy.types.WindowManager.kernel_ai
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
