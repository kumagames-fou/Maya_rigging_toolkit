# -*- coding: utf-8 -*-
"""
rigging_toolkit.py  +  Normal Orient  +  Move to Center

リギング作業に必要なツールを一つのウィンドウに集約したランチャー。

構成:
  - 上部: Maya標準エディタ呼び出しボタン
  - 下部: タブ式ペイン
      Tab1: Curve Snap to Joints
      Tab2: Curve Color Override
      Tab3: Constraint Pairing
      Tab4: Normal -> Joint Orient
      Tab5: Controller Group Duplicate
      Tab6: IK/FK BlendColors Setup
      Tab7: BlendColors
      Tab8: Move to Center

使い方:
    MayaのスクリプトエディタでこのスクリプトをPythonで実行。

制作 クマ
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.OpenMaya as om1
import re
import maya.mel as mel
import math



# ================================================================
# -- Controller Group Duplicate  コア処理 -----------------------
# ================================================================

def _ctrldup_classify_selection():
    """選択ノードをジョイントとテンプレートグループに自動振り分け（選択順不問）"""
    sel = cmds.ls(selection=True, long=True)
    joints = []
    template_grp = None

    for node in sel:
        node_type = cmds.nodeType(node)

        if node_type == 'joint':
            joints.append(node)
            continue

        if node_type == 'transform':
            shapes = cmds.listRelatives(node, shapes=True, type='nurbsCurve') or []
            if shapes:
                parent = cmds.listRelatives(node, parent=True, fullPath=True)
                template_grp = parent[0] if parent else node
                continue

            all_shapes = cmds.listRelatives(node, shapes=True) or []
            if not all_shapes:
                children = cmds.listRelatives(node, children=True, type='transform', fullPath=True) or []
                for child in children:
                    child_shapes = cmds.listRelatives(child, shapes=True, type='nurbsCurve') or []
                    if child_shapes:
                        template_grp = node
                        break

    return template_grp, joints


def _ctrldup_get_joint_hierarchy_order(joints):
    """ジョイントを階層順（親→子）にソート"""
    def get_depth(j):
        depth = 0
        p = cmds.listRelatives(j, parent=True, type='joint', fullPath=True)
        while p:
            depth += 1
            p = cmds.listRelatives(p[0], parent=True, type='joint', fullPath=True)
        return depth
    return sorted(joints, key=get_depth)


def _ctrldup_duplicate_and_place(template_grp, joint, src_word, dst_word,
                                  grp_suffix, rename_curve_flag):
    """グループを複製してジョイントにスナップ・リネーム"""
    new_grp = cmds.duplicate(template_grp, renameChildren=True)[0]

    jnt_short = joint.split('|')[-1]
    ctrl_name = jnt_short.replace(src_word, dst_word)
    new_grp_name = ctrl_name + grp_suffix
    new_grp = cmds.rename(new_grp, new_grp_name)

    if rename_curve_flag:
        children = cmds.listRelatives(new_grp, children=True, type='transform') or []
        for child in children:
            cmds.rename(child, ctrl_name)

    cmds.matchTransform(new_grp, joint, pos=True, rot=True)
    return new_grp


def ctrldup_run(src_word, dst_word, grp_suffix, rename_curve_flag):
    """
    メイン処理:
      1. 選択を自動判別（ジョイント / テンプレートグループ）
      2. ジョイントごとにグループを複製・スナップ・リネーム
      3. GRP -> CNTRL -> 子GRP -> 子CNTRL の階層を構築
    """
    template_grp, joints = _ctrldup_classify_selection()

    if not template_grp:
        cmds.warning("[CtrlDup] テンプレートとなるカーブまたはグループが選択されていません。")
        return
    if not joints:
        cmds.warning("[CtrlDup] ジョイントが選択されていません。")
        return

    ordered_joints = _ctrldup_get_joint_hierarchy_order(joints)

    grp_map = {}
    for joint in ordered_joints:
        new_grp = _ctrldup_duplicate_and_place(
            template_grp, joint, src_word, dst_word, grp_suffix, rename_curve_flag
        )
        ctrl = (cmds.listRelatives(new_grp, children=True, type='transform') or [None])[0]
        grp_map[joint] = (new_grp, ctrl)

    for joint in ordered_joints:
        parent_joints = cmds.listRelatives(joint, parent=True, type='joint', fullPath=True)
        if not parent_joints:
            continue
        parent_joint = parent_joints[0]
        if parent_joint not in grp_map:
            continue

        child_grp   = grp_map[joint][0]
        parent_ctrl = grp_map[parent_joint][1]

        if parent_ctrl:
            cmds.parent(child_grp, parent_ctrl)
        else:
            cmds.warning("[CtrlDup] {} のCNTRLが見つかりません。GRP同士で親子化します。".format(parent_joint))
            cmds.parent(child_grp, grp_map[parent_joint][0])

    root_joints = [
        j for j in ordered_joints
        if not cmds.listRelatives(j, parent=True, type='joint', fullPath=True)
        or cmds.listRelatives(j, parent=True, type='joint', fullPath=True)[0] not in grp_map
    ]
    cmds.select([grp_map[j][0] for j in root_joints])
    om1.MGlobal.displayInfo("[CtrlDup] 完了: {} 個のコントローラーグループを作成しました。".format(len(grp_map)))


def _build_tab_ctrldup(parent):
    cmds.setParent(parent)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 10))
    cmds.separator(height=8, style="none")
    cmds.text(label="カーブ(またはグループ)とジョイントを選択して実行",
              align="left", font="smallBoldLabelFont")
    cmds.text(label="選択順は問いません。ノードタイプで自動判別します。",
              align="left", font="smallPlainLabelFont")
    cmds.separator(height=6, style="in")

    cmds.text(label="リネーム設定", align="left", font="smallBoldLabelFont")
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(110, 10, 180), adjustableColumn=3)
    cmds.text(label="検索する文字列")
    cmds.text(label="")
    src_field = cmds.textField(text="JNT")
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=3, columnWidth3=(110, 10, 180), adjustableColumn=3)
    cmds.text(label="置換する文字列")
    cmds.text(label="")
    dst_field = cmds.textField(text="CNTRL")
    cmds.setParent("..")

    cmds.separator(height=6, style="in")
    cmds.text(label="オプション", align="left", font="smallBoldLabelFont")

    cmds.rowLayout(numberOfColumns=3, columnWidth3=(110, 10, 180), adjustableColumn=3)
    cmds.text(label="グループサフィックス")
    cmds.text(label="")
    grp_suffix_field = cmds.textField(text="_GRP")
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(110, 180))
    cmds.text(label="カーブもリネーム")
    rename_cb = cmds.checkBox(label="", value=True)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")
    cmds.text(label="生成される階層構造:", align="left", font="smallPlainLabelFont")
    cmds.text(label="  GRP  ->  CNTRL  ->  子GRP  ->  子CNTRL",
              align="left", font="smallPlainLabelFont")
    cmds.separator(height=8, style="in")

    status = cmds.text(label="", align="left", font="smallPlainLabelFont")
    cmds.separator(height=4, style="none")

    def on_run(*_):
        ctrldup_run(
            src_word=cmds.textField(src_field, q=True, text=True),
            dst_word=cmds.textField(dst_field, q=True, text=True),
            grp_suffix=cmds.textField(grp_suffix_field, q=True, text=True),
            rename_curve_flag=cmds.checkBox(rename_cb, q=True, value=True),
        )
        cmds.text(status, edit=True, label="実行しました。スクリプトエディタで結果を確認してください。")

    cmds.button(label="実行", height=34, command=on_run,
                backgroundColor=(0.22, 0.55, 0.38))
    cmds.separator(height=8, style="none")
    cmds.setParent("..")

# ================================================================
# -- Normal Orient  コア処理 ------------------------------------
# ================================================================

def _get_vertex_normal_world(mesh_dag, vtx_id):
    mesh_fn = om.MFnMesh(mesh_dag)
    normals = mesh_fn.getVertexNormals(False, om.MSpace.kWorld)
    return om.MVector(normals[vtx_id])


def _get_joint_world_pos(joint_name):
    t = cmds.xform(joint_name, q=True, ws=True, t=True)
    return om.MPoint(t[0], t[1], t[2])


def _parse_selection():
    sel        = om.MGlobal.getActiveSelectionList()
    vtx_list   = []
    joint_list = []
    for s in cmds.ls(sl=True, fl=True):
        if cmds.objectType(s) == 'joint':
            joint_list.append(s)
    iter_sel = om.MItSelectionList(sel, om.MFn.kMeshVertComponent)
    while not iter_sel.isDone():
        dag, component = iter_sel.getComponent()
        iter_vtx = om.MItMeshVertex(dag, component)
        while not iter_vtx.isDone():
            vtx_id = iter_vtx.index()
            pos    = iter_vtx.position(om.MSpace.kWorld)
            normal = _get_vertex_normal_world(dag, vtx_id)
            vtx_list.append((dag, vtx_id, pos, normal))
            iter_vtx.next()
        iter_sel.next()
    return vtx_list, joint_list


def _get_selected_meshes():
    result = []
    for s in cmds.ls(sl=True, fl=True):
        otype = cmds.objectType(s)
        if otype == 'transform':
            if cmds.listRelatives(s, shapes=True, type='mesh'):
                result.append(s)
        elif otype == 'mesh':
            result.append(cmds.listRelatives(s, parent=True)[0])
    return result


def _parse_selection_mesh_mode():
    sel_strings = cmds.ls(sl=True, fl=True)
    joint_list  = []
    mesh_list   = _get_selected_meshes()
    for s in sel_strings:
        if cmds.objectType(s) == 'joint':
            joint_list.append(s)
    if not mesh_list:
        cmds.warning("[NormalToOrient] メッシュが選択されていません")
        return [], []
    if not joint_list:
        cmds.warning("[NormalToOrient] ジョイントが選択されていません")
        return [], []
    vtx_list = []
    for jname in joint_list:
        jpos   = _get_joint_world_pos(jname)
        best_d = float('inf')
        best_nor, best_vtx, best_pos = None, 0, None
        for mesh_name in mesh_list:
            sel_om   = om.MSelectionList()
            sel_om.add(mesh_name)
            mesh_dag = sel_om.getDagPath(0)
            mesh_fn  = om.MFnMesh(mesh_dag)
            for i, pt in enumerate(mesh_fn.getPoints(om.MSpace.kWorld)):
                dx,dy,dz = pt.x-jpos.x, pt.y-jpos.y, pt.z-jpos.z
                d = dx*dx+dy*dy+dz*dz
                if d < best_d:
                    best_d, best_vtx, best_pos = d, i, pt
                    best_nor = _get_vertex_normal_world(mesh_dag, i)
        vtx_list.append((None, best_vtx, best_pos, best_nor))
    return vtx_list, joint_list


def _pair_nearest(vtx_list, joint_list):
    remaining = list(vtx_list)
    pairs     = []
    for jname in joint_list:
        jpos     = _get_joint_world_pos(jname)
        best_idx = None
        best_d   = float('inf')
        for i, (dag, vtx_id, pos, normal) in enumerate(remaining):
            dx,dy,dz = pos.x-jpos.x, pos.y-jpos.y, pos.z-jpos.z
            d = dx*dx+dy*dy+dz*dz
            if d < best_d:
                best_d, best_idx = d, i
        if best_idx is not None:
            dag, vtx_id, pos, normal = remaining.pop(best_idx)
            pairs.append((jname, dag, vtx_id, normal))
    return pairs


def _to_mvec(v):
    return om.MVector(v.x, v.y, v.z)


def _ortho(base, hint):
    b = _to_mvec(base).normalize()
    h = _to_mvec(hint)
    p = h - (h * b) * b
    if p.length() < 1e-6:
        fallback = om.MVector(0,1,0) if abs(b.y) < 0.9 else om.MVector(1,0,0)
        p = fallback - (fallback * b) * b
    return p.normalize()


def _matrix_to_euler(mat):
    mmat  = om.MTransformationMatrix(mat)
    euler = mmat.rotation(asQuaternion=False)
    return [math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z)]


def _get_joint_local_axis_world(jname, axis_label):
    wm  = om.MMatrix(cmds.getAttr(jname + '.worldMatrix[0]'))
    row = {'X': 0, 'Y': 1, 'Z': 2}[axis_label]
    return om.MVector(wm[row*4], wm[row*4+1], wm[row*4+2]).normalize()


def _compute_orient_euler(jname, normal, primary_axis, normal_axis, child_dir):
    axes    = ['X','Y','Z']
    RHS_POS = {('X','Y'), ('Y','Z'), ('Z','X')}

    sign     = -1 if normal_axis.startswith('-') else 1
    nor_base = normal_axis.lstrip('-')
    nor_vec  = (_to_mvec(normal) * sign).normalize()
    pri_base = primary_axis

    pri_world = child_dir

    if nor_base != pri_base:
        proj = nor_vec - (nor_vec * pri_world) * pri_world
        if proj.length() < 1e-6:
            fallback = om.MVector(0,1,0) if abs(pri_world.y) < 0.9 else om.MVector(1,0,0)
            proj = fallback - (fallback * pri_world) * pri_world
        nor_world = proj.normalize()
    else:
        nor_world = pri_world

    if nor_base != pri_base:
        thi_base = [a for a in axes if a != pri_base and a != nor_base][0]
        if (pri_base, nor_base) in RHS_POS:
            thi_world = (pri_world ^ nor_world).normalize()
        else:
            thi_world = (nor_world ^ pri_world).normalize()
        assign = {pri_base: pri_world, nor_base: nor_world, thi_base: thi_world}
    else:
        rem2      = [a for a in axes if a != pri_base]
        sec_world = _ortho(pri_world, om.MVector(0,1,0))
        thi_base  = rem2[1]
        if (rem2[0], thi_base) in RHS_POS:
            thi_world = (sec_world ^ pri_world).normalize()
        else:
            thi_world = (pri_world ^ sec_world).normalize()
        assign = {pri_base: pri_world, rem2[0]: sec_world, thi_base: thi_world}

    x, y, z = assign['X'], assign['Y'], assign['Z']
    world_rot_mat = om.MMatrix([
        x.x, x.y, x.z, 0,
        y.x, y.y, y.z, 0,
        z.x, z.y, z.z, 0,
        0,   0,   0,   1,
    ])
    parent_mat = om.MMatrix(cmds.getAttr(jname + '.parentMatrix[0]'))
    local_mat  = world_rot_mat * parent_mat.inverse()
    deg        = _matrix_to_euler(local_mat)

    cmds.setAttr(jname + '.jointOrientX', deg[0])
    cmds.setAttr(jname + '.jointOrientY', deg[1])
    cmds.setAttr(jname + '.jointOrientZ', deg[2])
    cmds.setAttr(jname + '.rotateX', 0)
    cmds.setAttr(jname + '.rotateY', 0)
    cmds.setAttr(jname + '.rotateZ', 0)


def apply_normal_to_joint_orient(primary_axis, normal_axis, mode="orient",
                                  sel_mode="vertex", include_children=False):
    if sel_mode == "mesh":
        vtx_list, joint_list = _parse_selection_mesh_mode()
        if not vtx_list or not joint_list:
            return
        pairs = [(joint_list[i], None, vtx_list[i][1], vtx_list[i][3])
                 for i in range(len(joint_list))]
    else:
        vtx_list, joint_list = _parse_selection()
        if not joint_list:
            cmds.warning("[NormalToOrient] ジョイントが選択されていません"); return
        if not vtx_list:
            cmds.warning("[NormalToOrient] 頂点が選択されていません"); return
        if len(joint_list) > len(vtx_list):
            cmds.warning("[NormalToOrient] ジョイント数が頂点数より多いです"); return
        pairs = _pair_nearest(vtx_list, joint_list)

    if include_children:
        extra_joints = []
        def _collect(jlist):
            for j in jlist:
                ch = cmds.listRelatives(j, children=True, type='joint', fullPath=True) or []
                extra_joints.extend(ch)
                _collect(ch)
        _collect(joint_list)
        for j in extra_joints:
            jpos = _get_joint_world_pos(j)
            if sel_mode == "mesh":
                best_d, best_nor, best_vid = float('inf'), None, 0
                for mesh_name in _get_selected_meshes():
                    sel_om = om.MSelectionList()
                    sel_om.add(mesh_name)
                    mesh_dag = sel_om.getDagPath(0)
                    mesh_fn  = om.MFnMesh(mesh_dag)
                    for i, pt in enumerate(mesh_fn.getPoints(om.MSpace.kWorld)):
                        dx,dy,dz = pt.x-jpos.x, pt.y-jpos.y, pt.z-jpos.z
                        d = dx*dx+dy*dy+dz*dz
                        if d < best_d:
                            best_d, best_vid = d, i
                            best_nor = _get_vertex_normal_world(mesh_dag, i)
                if best_nor is not None:
                    pairs.append((j, None, best_vid, best_nor))
            else:
                best_d, best_idx = float('inf'), None
                for i, (dag, vid, pos, nor) in enumerate(vtx_list):
                    dx,dy,dz = pos.x-jpos.x, pos.y-jpos.y, pos.z-jpos.z
                    d = dx*dx+dy*dy+dz*dz
                    if d < best_d:
                        best_d, best_idx = d, i
                if best_idx is not None:
                    dag, vid, pos, nor = vtx_list[best_idx]
                    pairs.append((j, dag, vid, nor))

    for jname, dag, vtx_id, normal in pairs:
        ch_joints = cmds.listRelatives(jname, children=True, type='joint', fullPath=True) or []
        if ch_joints:
            cpos = _get_joint_world_pos(ch_joints[0])
            jpos = _get_joint_world_pos(jname)
            child_dir = om.MVector(cpos.x-jpos.x, cpos.y-jpos.y, cpos.z-jpos.z).normalize()
        else:
            child_dir = om.MVector(0, 1, 0)

        all_children = cmds.listRelatives(jname, children=True, fullPath=True) or []
        child_world  = {}
        for ch in all_children:
            child_world[ch] = (
                cmds.xform(ch, q=True, ws=True, t=True),
                cmds.xform(ch, q=True, ws=True, ro=True),
                cmds.xform(ch, q=True, ws=True, s=True),
            )
        free_children = cmds.parent(all_children, world=True) if all_children else []

        _compute_orient_euler(jname, normal, primary_axis, normal_axis, child_dir)

        if free_children:
            cmds.parent(free_children, jname)
            for ch, (t, r, s) in child_world.items():
                short   = ch.split("|")[-1]
                matches = cmds.ls(short, long=True)
                target  = matches[0] if matches else short
                cmds.xform(target, ws=True, t=t)
                cmds.xform(target, ws=True, ro=r)
                cmds.xform(target, ws=True, s=s)

        jo = cmds.getAttr(jname + '.jointOrient')[0]
        if mode == "orient":
            print("[NormalToOrient] {} <- vtx[{}]  jointOrient=({:.2f},{:.2f},{:.2f})".format(
                jname, vtx_id, jo[0], jo[1], jo[2]))
        else:
            cmds.setAttr(jname + ".rotateX", jo[0])
            cmds.setAttr(jname + ".rotateY", jo[1])
            cmds.setAttr(jname + ".rotateZ", jo[2])
            cmds.setAttr(jname + ".jointOrientX", 0)
            cmds.setAttr(jname + ".jointOrientY", 0)
            cmds.setAttr(jname + ".jointOrientZ", 0)
            print("[NormalToOrient] {} <- vtx[{}]  rotate=({:.2f},{:.2f},{:.2f})".format(
                jname, vtx_id, jo[0], jo[1], jo[2]))

    cmds.select(joint_list)
    print("[NormalToOrient] Done — {} pair(s) processed.".format(len(pairs)))


# ================================================================
# -- Curve Snap to Joints  コア処理 ----------------------------
# ================================================================

def _open_sdk_editor():
    mel.eval('setDrivenKeyWindow "" {}')


def _snap_get_world_translation(node):
    return cmds.xform(node, q=True, worldSpace=True, translation=True)


def _snap_freeze(nodes):
    cmds.makeIdentity(nodes, apply=True, translate=True, rotate=True, scale=True, normal=False)


def _snap_apply_constraint(dup, joint, constraint_type, direction, options):
    mo = options.get("maintainOffset", False)
    driver, driven = (dup, joint) if direction == "curve_to_joint" else (joint, dup)
    if constraint_type == "parentConstraint":
        cmds.parentConstraint(driver, driven, maintainOffset=mo,
                              skipTranslate=options.get("skipTranslate", []) or "none",
                              skipRotate=options.get("skipRotate", []) or "none")
    elif constraint_type == "pointConstraint":
        cmds.pointConstraint(driver, driven, maintainOffset=mo,
                             skip=options.get("skipTranslate", []) or "none")
    elif constraint_type == "orientConstraint":
        cmds.orientConstraint(driver, driven, maintainOffset=mo,
                              skip=options.get("skipRotate", []) or "none")
    elif constraint_type == "scaleConstraint":
        cmds.scaleConstraint(driver, driven, maintainOffset=mo,
                             skip=options.get("skipScale", []) or "none")
    elif constraint_type == "aimConstraint":
        cmds.aimConstraint(driver, driven, maintainOffset=mo,
                           aimVector=options.get("aimVector", [1,0,0]),
                           upVector=options.get("upVector", [0,1,0]),
                           worldUpType=options.get("worldUpType", "vector"),
                           worldUpVector=options.get("worldUpVector", [0,1,0]))


def snap_run(parent_to_curve=False, select_result=True,
             freeze_duplicates=False, freeze_source=False,
             snap_mode="snap_only", constraint_type=None,
             constraint_direction="curve_to_joint", constraint_options=None):
    if constraint_options is None:
        constraint_options = {}
    sel = cmds.ls(selection=True, long=True)
    if not sel:
        om1.MGlobal.displayError("[curve_snap] 何も選択されていません。"); return []
    curves, joints = [], []
    for node in sel:
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        if any(cmds.nodeType(s) == "nurbsCurve" for s in shapes):
            curves.append(node)
        elif cmds.nodeType(node) == "joint":
            joints.append(node)
    if not curves: om1.MGlobal.displayError("[curve_snap] カーブが選択されていません。"); return []
    if len(curves) > 1:
        om1.MGlobal.displayWarning("[curve_snap] カーブが複数あります。最初の1つを使用します。")
    if not joints: om1.MGlobal.displayError("[curve_snap] ジョイントが選択されていません。"); return []
    curve_short = curves[0].split("|")[-1]
    created = []
    for joint in joints:
        js  = joint.split("|")[-1]
        dup = cmds.duplicate(curve_short, name="{}_{}".format(curve_short, js), upstreamNodes=False)[0]
        created.append(dup)
    if snap_mode in ("snap_only", "both"):
        for dup, joint in zip(created, joints):
            pos = _snap_get_world_translation(joint.split("|")[-1])
            cmds.xform(dup, worldSpace=True, translation=pos)
    if parent_to_curve and created:
        cmds.parent(created, curve_short)
    if freeze_source:
        _snap_freeze([curve_short])
    if freeze_duplicates and created:
        _snap_freeze(created)
    if snap_mode in ("constraint_only", "both") and constraint_type:
        for dup, joint in zip(created, joints):
            _snap_apply_constraint(dup, joint.split("|")[-1],
                                   constraint_type, constraint_direction, constraint_options)
    if select_result and created:
        cmds.select(created, replace=True)
    om1.MGlobal.displayInfo("[curve_snap] 完了: {}個複製。".format(len(created)))
    return created


# ================================================================
# -- Curve Color Override  コア処理 ----------------------------
# ================================================================

COLOR_INDEX_LIST = [
    (0,  "0: なし（Override無効）",  (0.0,  0.0,  0.0 )),
    (1,  "1: Black",                 (0.0,  0.0,  0.0 )),
    (2,  "2: Dark Grey",             (0.25, 0.25, 0.25)),
    (3,  "3: Light Grey",            (0.6,  0.6,  0.6 )),
    (4,  "4: Crimson",               (0.61, 0.0,  0.16)),
    (5,  "5: Dark Blue",             (0.0,  0.02, 0.4 )),
    (6,  "6: Blue",                  (0.0,  0.0,  1.0 )),
    (7,  "7: Dark Green",            (0.0,  0.28, 0.1 )),
    (8,  "8: Dark Purple",           (0.15, 0.0,  0.26)),
    (9,  "9: Pink / Magenta",        (0.78, 0.0,  0.78)),
    (10, "10: Brown",                (0.54, 0.28, 0.2 )),
    (11, "11: Dark Brown",           (0.25, 0.13, 0.13)),
    (12, "12: Dark Red",             (0.6,  0.19, 0.19)),
    (13, "13: Red",                  (1.0,  0.0,  0.0 )),
    (14, "14: Green",                (0.0,  1.0,  0.0 )),
    (15, "15: Cobalt Blue",          (0.0,  0.26, 0.64)),
    (16, "16: White",                (1.0,  1.0,  1.0 )),
    (17, "17: Yellow",               (1.0,  1.0,  0.0 )),
    (18, "18: Cyan",                 (0.0,  1.0,  1.0 )),
    (19, "19: Aqua",                 (0.0,  1.0,  0.5 )),
    (20, "20: Pink",                 (1.0,  0.69, 0.69)),
    (21, "21: Peach / Salmon",       (0.89, 0.67, 0.47)),
    (22, "22: Pale Yellow",          (1.0,  1.0,  0.39)),
    (23, "23: Pale Green",           (0.0,  0.6,  0.33)),
    (24, "24: Tan",                  (0.63, 0.42, 0.19)),
    (25, "25: Orange-Yellow",        (0.62, 0.63, 0.19)),
    (26, "26: Medium Green",         (0.41, 0.63, 0.19)),
    (27, "27: Olive",                (0.19, 0.63, 0.37)),
    (28, "28: Forest Green",         (0.19, 0.63, 0.63)),
    (29, "29: Sky Blue",             (0.19, 0.4,  0.63)),
    (30, "30: Steel Blue",           (0.43, 0.19, 0.63)),
    (31, "31: Purple",               (0.63, 0.19, 0.42)),
]

COLOR_TARGET_ITEMS  = ["トランスフォーム", "シェイプ", "両方"]
COLOR_TARGET_VALUES = ["transform", "shape", "both"]


def color_get_curves():
    sel = cmds.ls(selection=True, long=True)
    return [n for n in sel
            if any(cmds.nodeType(s) == "nurbsCurve"
                   for s in (cmds.listRelatives(n, shapes=True, fullPath=True) or []))]


def color_apply_index(nodes, index, target):
    for node in nodes:
        if target in ("transform", "both"):
            if index == 0:
                cmds.setAttr("{}.overrideEnabled".format(node), False)
            else:
                cmds.setAttr("{}.overrideEnabled".format(node), True)
                cmds.setAttr("{}.overrideRGBColors".format(node), False)
                cmds.setAttr("{}.overrideColor".format(node), index)
        if target in ("shape", "both"):
            for s in (cmds.listRelatives(node, shapes=True, fullPath=True) or []):
                if cmds.nodeType(s) == "nurbsCurve":
                    if index == 0:
                        cmds.setAttr("{}.overrideEnabled".format(s), False)
                    else:
                        cmds.setAttr("{}.overrideEnabled".format(s), True)
                        cmds.setAttr("{}.overrideRGBColors".format(s), False)
                        cmds.setAttr("{}.overrideColor".format(s), index)


def color_apply_rgb(nodes, r, g, b, target):
    def _ap(n):
        cmds.setAttr("{}.overrideEnabled".format(n), True)
        cmds.setAttr("{}.overrideRGBColors".format(n), True)
        cmds.setAttr("{}.overrideColorRGB".format(n), r, g, b)
    for node in nodes:
        if target in ("transform", "both"): _ap(node)
        if target in ("shape", "both"):
            for s in (cmds.listRelatives(node, shapes=True, fullPath=True) or []):
                if cmds.nodeType(s) == "nurbsCurve": _ap(s)


# ================================================================
# -- Constraint Pairing  コア処理 ------------------------------
# ================================================================

def _pair_get_world_pos(node):
    return cmds.xform(node, q=True, worldSpace=True, rotatePivot=True)


def _tokenize(name):
    name = re.sub(r'([a-z])([A-Z])', r'\1_\2', name)
    return set(t.lower() for t in re.split(r'[_\-\s]+', name) if t)


def pair_by_name(curves, joints):
    pairs, used = [], set()
    for curve in curves:
        ct = _tokenize(curve)
        best_score, best_joint = -1, None
        for joint in joints:
            if joint in used: continue
            score = len(ct & _tokenize(joint))
            if score > best_score:
                best_score, best_joint = score, joint
        pairs.append((curve, best_joint))
        if best_joint: used.add(best_joint)
    return pairs


def pair_by_distance(curves, joints):
    if not curves or not joints:
        return [(c, None) for c in curves]
    dist_matrix = []
    for curve in curves:
        cp = _pair_get_world_pos(curve)
        dist_matrix.append([
            sum((a-b)**2 for a,b in zip(cp, _pair_get_world_pos(j)))**0.5
            for j in joints
        ])
    candidates = sorted(
        [(dist_matrix[ci][ji], ci, ji)
         for ci in range(len(curves)) for ji in range(len(joints))]
    )
    used_c, used_j, assigned = set(), set(), {}
    for d, ci, ji in candidates:
        if ci in used_c or ji in used_j: continue
        assigned[ci] = ji; used_c.add(ci); used_j.add(ji)
    return [(curves[ci], joints[assigned[ci]] if ci in assigned else None)
            for ci in range(len(curves))]


def pair_apply_constraint(curve, joint, constraint_type, direction, options):
    mo = options.get("maintainOffset", False)
    driver, driven = (curve, joint) if direction == "curve_to_joint" else (joint, curve)
    if constraint_type == "parentConstraint":
        cmds.parentConstraint(driver, driven, maintainOffset=mo,
                              skipTranslate=options.get("skipTranslate",[]) or "none",
                              skipRotate=options.get("skipRotate",[]) or "none")
    elif constraint_type == "pointConstraint":
        cmds.pointConstraint(driver, driven, maintainOffset=mo,
                             skip=options.get("skipTranslate",[]) or "none")
    elif constraint_type == "orientConstraint":
        cmds.orientConstraint(driver, driven, maintainOffset=mo,
                              skip=options.get("skipRotate",[]) or "none")
    elif constraint_type == "scaleConstraint":
        cmds.scaleConstraint(driver, driven, maintainOffset=mo,
                             skip=options.get("skipScale",[]) or "none")
    elif constraint_type == "aimConstraint":
        cmds.aimConstraint(driver, driven, maintainOffset=mo,
                           aimVector=options.get("aimVector",[1,0,0]),
                           upVector=options.get("upVector",[0,1,0]),
                           worldUpType=options.get("worldUpType","vector"),
                           worldUpVector=options.get("worldUpVector",[0,1,0]))


def pair_run_constraints(pairs, constraint_type, direction, options):
    ok = ng = 0
    for curve, joint in pairs:
        if not curve or not joint:
            om1.MGlobal.displayWarning("[pair] 未解決: {} / {}".format(curve, joint))
            ng += 1; continue
        try:
            pair_apply_constraint(curve, joint, constraint_type, direction, options)
            ok += 1
        except Exception as e:
            om1.MGlobal.displayError("[pair] エラー: {}".format(e)); ng += 1
    return ok, ng


# ================================================================
# -- 共通UIヘルパー --------------------------------------------
# ================================================================

CONSTRAINT_TYPES = ["parentConstraint", "pointConstraint",
                    "orientConstraint",  "scaleConstraint", "aimConstraint"]


def _build_constraint_options_ui():
    cmds.text(label="種類", align="left", font="smallPlainLabelFont")
    const_menu = cmds.optionMenu()
    for ct in CONSTRAINT_TYPES:
        cmds.menuItem(label=ct)
    cmds.text(label="方向", align="left", font="smallPlainLabelFont")
    dir_col = cmds.radioCollection()
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(160, 150))
    rb_c2j = cmds.radioButton(label="カーブ → ジョイント", collection=dir_col, select=True)
    cmds.radioButton(label="ジョイント → カーブ", collection=dir_col)
    cmds.setParent("..")
    opt_mo = cmds.checkBox(label="オフセットを保持", value=False)
    cmds.separator(height=4, style="none")

    def _skip_row(label):
        cmds.text(label=label, align="left", font="smallPlainLabelFont")
        cmds.rowLayout(numberOfColumns=3, columnWidth3=(60,60,60))
        cx = cmds.checkBox(label="X", value=False)
        cy = cmds.checkBox(label="Y", value=False)
        cz = cmds.checkBox(label="Z", value=False)
        cmds.setParent("..")
        return cx, cy, cz

    frame_pc = cmds.frameLayout(label="ペアレントコンストレイント オプション",
                                 collapsable=False, marginWidth=8, marginHeight=4)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    pt_tx, pt_ty, pt_tz = _skip_row("移動をスキップ")
    pt_rx, pt_ry, pt_rz = _skip_row("回転をスキップ")
    cmds.setParent(".."); cmds.setParent("..")

    frame_po = cmds.frameLayout(label="ポイントコンストレイント オプション",
                                 collapsable=False, marginWidth=8, marginHeight=4)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    po_tx, po_ty, po_tz = _skip_row("移動をスキップ")
    cmds.setParent(".."); cmds.setParent("..")

    frame_oo = cmds.frameLayout(label="オリエントコンストレイント オプション",
                                 collapsable=False, marginWidth=8, marginHeight=4)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    or_rx, or_ry, or_rz = _skip_row("回転をスキップ")
    cmds.setParent(".."); cmds.setParent("..")

    frame_sc = cmds.frameLayout(label="スケールコンストレイント オプション",
                                 collapsable=False, marginWidth=8, marginHeight=4)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    sc_sx, sc_sy, sc_sz = _skip_row("スケールをスキップ")
    cmds.setParent(".."); cmds.setParent("..")

    frame_ac = cmds.frameLayout(label="エイムコンストレイント オプション",
                                 collapsable=False, marginWidth=8, marginHeight=4)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.rowLayout(numberOfColumns=4, columnWidth4=(80,55,55,55))
    cmds.text(label="エイムベクトル")
    aim_x = cmds.floatField(value=1.0, precision=2)
    aim_y = cmds.floatField(value=0.0, precision=2)
    aim_z = cmds.floatField(value=0.0, precision=2)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=4, columnWidth4=(80,55,55,55))
    cmds.text(label="アップベクトル")
    up_x = cmds.floatField(value=0.0, precision=2)
    up_y = cmds.floatField(value=1.0, precision=2)
    up_z = cmds.floatField(value=0.0, precision=2)
    cmds.setParent("..")
    cmds.text(label="ワールドアップタイプ", align="left", font="smallPlainLabelFont")
    wup_menu = cmds.optionMenu()
    for wt in ["vector","object","objectrotation","scene","none"]:
        cmds.menuItem(label=wt)
    cmds.rowLayout(numberOfColumns=4, columnWidth4=(80,55,55,55))
    cmds.text(label="ワールドアップベクトル")
    wupv_x = cmds.floatField(value=0.0, precision=2)
    wupv_y = cmds.floatField(value=1.0, precision=2)
    wupv_z = cmds.floatField(value=0.0, precision=2)
    cmds.setParent(".."); cmds.setParent(".."); cmds.setParent("..")

    const_frames = {
        "parentConstraint": frame_pc, "pointConstraint": frame_po,
        "orientConstraint": frame_oo, "scaleConstraint": frame_sc,
        "aimConstraint":    frame_ac,
    }

    def _update_frames(*_):
        ct = cmds.optionMenu(const_menu, query=True, value=True)
        for k, fr in const_frames.items():
            cmds.frameLayout(fr, edit=True, visible=(k == ct))
    cmds.optionMenu(const_menu, edit=True, changeCommand=_update_frames)
    _update_frames()

    w = {
        "pt_tx": pt_tx, "pt_ty": pt_ty, "pt_tz": pt_tz,
        "pt_rx": pt_rx, "pt_ry": pt_ry, "pt_rz": pt_rz,
        "po_tx": po_tx, "po_ty": po_ty, "po_tz": po_tz,
        "or_rx": or_rx, "or_ry": or_ry, "or_rz": or_rz,
        "sc_sx": sc_sx, "sc_sy": sc_sy, "sc_sz": sc_sz,
        "aim_x": aim_x, "aim_y": aim_y, "aim_z": aim_z,
        "up_x":  up_x,  "up_y":  up_y,  "up_z":  up_z,
        "wup_menu": wup_menu,
        "wupv_x": wupv_x, "wupv_y": wupv_y, "wupv_z": wupv_z,
    }
    return const_menu, rb_c2j, opt_mo, w


def _collect_constraint_options(const_menu, rb_c2j, opt_mo, w):
    ct        = cmds.optionMenu(const_menu, query=True, value=True)
    direction = "curve_to_joint" if cmds.radioButton(rb_c2j, query=True, select=True) else "joint_to_curve"
    do_mo     = cmds.checkBox(opt_mo, query=True, value=True)

    def skips(*cbs):
        axes = ["x","y","z"]
        return [axes[i] for i,cb in enumerate(cbs) if cmds.checkBox(cb, query=True, value=True)]

    def ff(key): return cmds.floatField(w[key], query=True, value=True)

    if ct == "parentConstraint":
        opts = {"maintainOffset": do_mo,
                "skipTranslate": skips(w["pt_tx"], w["pt_ty"], w["pt_tz"]),
                "skipRotate":    skips(w["pt_rx"], w["pt_ry"], w["pt_rz"])}
    elif ct == "pointConstraint":
        opts = {"maintainOffset": do_mo,
                "skipTranslate": skips(w["po_tx"], w["po_ty"], w["po_tz"])}
    elif ct == "orientConstraint":
        opts = {"maintainOffset": do_mo,
                "skipRotate": skips(w["or_rx"], w["or_ry"], w["or_rz"])}
    elif ct == "scaleConstraint":
        opts = {"maintainOffset": do_mo,
                "skipScale": skips(w["sc_sx"], w["sc_sy"], w["sc_sz"])}
    elif ct == "aimConstraint":
        opts = {"maintainOffset": do_mo,
                "aimVector":     [ff("aim_x"), ff("aim_y"), ff("aim_z")],
                "upVector":      [ff("up_x"),  ff("up_y"),  ff("up_z")],
                "worldUpType":   cmds.optionMenu(w["wup_menu"], query=True, value=True),
                "worldUpVector": [ff("wupv_x"), ff("wupv_y"), ff("wupv_z")]}
    else:
        opts = {"maintainOffset": do_mo}
    return ct, direction, opts


# ================================================================
# -- タブ UI ---------------------------------------------------
# ================================================================

def _build_tab_snap(parent):
    cmds.setParent(parent)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 10))
    cmds.separator(height=8, style="none")
    cmds.text(label="カーブ 1つ + ジョイント 複数 を選択して実行",
              align="left", font="smallBoldLabelFont")
    cmds.separator(height=6, style="in")
    opt_parent     = cmds.checkBox(label="複製カーブを元カーブの子にする",           value=False)
    opt_select     = cmds.checkBox(label="実行後に複製カーブを選択状態にする",        value=True)
    cmds.separator(height=4, style="in")
    opt_freeze_dup = cmds.checkBox(label="複製カーブのトランスフォームをフリーズ",    value=False)
    opt_freeze_src = cmds.checkBox(label="複製元カーブのトランスフォームをフリーズ",  value=False)
    cmds.separator(height=6, style="in")
    cmds.text(label="コンストレイント", align="left", font="smallBoldLabelFont")
    cmds.text(label="移動モード",       align="left", font="smallPlainLabelFont")
    snap_col = cmds.radioCollection()
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(90,120,70))
    rb_snap  = cmds.radioButton(label="スナップのみ",         collection=snap_col, select=True)
    rb_const = cmds.radioButton(label="コンストレイントのみ", collection=snap_col)
    rb_both  = cmds.radioButton(label="両方",                collection=snap_col)
    cmds.setParent("..")
    const_menu, rb_c2j, opt_mo, w = _build_constraint_options_ui()
    cmds.separator(height=8, style="in")
    status = cmds.text(label="", align="left", font="smallPlainLabelFont")
    cmds.separator(height=4, style="none")

    def on_run(*_):
        if   cmds.radioButton(rb_snap,  query=True, select=True): mode = "snap_only"
        elif cmds.radioButton(rb_const, query=True, select=True): mode = "constraint_only"
        else: mode = "both"
        ct, direction, opts = _collect_constraint_options(const_menu, rb_c2j, opt_mo, w)
        result = snap_run(
            parent_to_curve=   cmds.checkBox(opt_parent,     query=True, value=True),
            select_result=     cmds.checkBox(opt_select,     query=True, value=True),
            freeze_duplicates= cmds.checkBox(opt_freeze_dup, query=True, value=True),
            freeze_source=     cmds.checkBox(opt_freeze_src, query=True, value=True),
            snap_mode=mode, constraint_type=ct,
            constraint_direction=direction, constraint_options=opts,
        )
        cmds.text(status, edit=True,
                  label="{} 個複製完了。".format(len(result)) if result else "実行できませんでした。")

    cmds.button(label="実行", height=34, command=on_run, backgroundColor=(0.22, 0.48, 0.85))
    cmds.separator(height=8, style="none")
    cmds.setParent("..")


def _build_tab_color(parent):
    cmds.setParent(parent)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 10))
    cmds.separator(height=8, style="none")
    cmds.text(label="選択中のカーブに色を一括適用", align="left", font="smallBoldLabelFont")
    cmds.separator(height=6, style="in")
    cmds.text(label="適用対象", align="left", font="smallPlainLabelFont")
    target_menu = cmds.optionMenu()
    for item in COLOR_TARGET_ITEMS:
        cmds.menuItem(label=item)
    cmds.separator(height=6, style="in")
    cmds.text(label="カラーインデックス", align="left", font="smallBoldLabelFont")
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
    index_slider = cmds.intSliderGrp(label="インデックス", field=True,
                                     minValue=0, maxValue=31, value=0,
                                     columnWidth3=(70,40,100))
    idx_canvas = cmds.canvas(width=30, height=20, rgbValue=COLOR_INDEX_LIST[0][2])
    cmds.setParent("..")

    def on_index_change(*_):
        idx = cmds.intSliderGrp(index_slider, query=True, value=True)
        cmds.canvas(idx_canvas, edit=True, rgbValue=COLOR_INDEX_LIST[idx][2])
    cmds.intSliderGrp(index_slider, edit=True,
                      changeCommand=on_index_change, dragCommand=on_index_change)

    status_idx = cmds.text(label="", align="left", font="smallPlainLabelFont")

    def _apply_index(*_):
        curves = color_get_curves()
        if not curves:
            cmds.text(status_idx, edit=True, label="カーブが選択されていません。"); return
        idx    = cmds.intSliderGrp(index_slider, query=True, value=True)
        target = COLOR_TARGET_VALUES[cmds.optionMenu(target_menu, query=True, select=True)-1]
        color_apply_index(curves, idx, target)
        cmds.text(status_idx, edit=True, label="{}本に index:{} を適用。".format(len(curves), idx))

    cmds.button(label="インデックスで適用", height=30, command=_apply_index,
                backgroundColor=(0.22, 0.48, 0.85))
    cmds.separator(height=6, style="in")
    cmds.text(label="RGBカラー", align="left", font="smallBoldLabelFont")
    rgb_slider = cmds.colorSliderGrp(label="カラー", rgb=(1.0,0.0,0.0))
    status_rgb = cmds.text(label="", align="left", font="smallPlainLabelFont")

    def _apply_rgb(*_):
        curves = color_get_curves()
        if not curves:
            cmds.text(status_rgb, edit=True, label="カーブが選択されていません。"); return
        r, g, b = cmds.colorSliderGrp(rgb_slider, query=True, rgb=True)
        target  = COLOR_TARGET_VALUES[cmds.optionMenu(target_menu, query=True, select=True)-1]
        color_apply_rgb(curves, r, g, b, target)
        cmds.text(status_rgb, edit=True,
                  label="{}本に RGB({:.2f},{:.2f},{:.2f}) を適用。".format(len(curves),r,g,b))

    cmds.button(label="RGBで適用", height=30, command=_apply_rgb,
                backgroundColor=(0.22, 0.48, 0.85))
    cmds.separator(height=8, style="none")
    cmds.setParent("..")


def _build_tab_pair(parent):
    cmds.setParent(parent)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 10))
    cmds.separator(height=8, style="none")
    cmds.text(label="カーブとジョイントをペアリングしてコンストレイント適用",
              align="left", font="smallBoldLabelFont")
    cmds.separator(height=6, style="in")
    cmds.text(label="ペアリングモード", align="left", font="smallPlainLabelFont")
    mode_col = cmds.radioCollection()
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(110,110,110))
    rb_name   = cmds.radioButton(label="名前マッチング", collection=mode_col, select=True)
    rb_dist   = cmds.radioButton(label="距離マッチング", collection=mode_col)
    rb_manual = cmds.radioButton(label="手動リスト",    collection=mode_col)
    cmds.setParent("..")

    frame_auto = cmds.frameLayout(label="自動マッチング設定", collapsable=False,
                                   marginWidth=8, marginHeight=4)
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label="カーブと全ジョイントを選択して「ペア解析」", align="left",
              font="smallPlainLabelFont")
    cmds.setParent(".."); cmds.setParent("..")

    frame_manual = cmds.frameLayout(label="手動ペアリスト", collapsable=False,
                                     marginWidth=8, marginHeight=4)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)

    def _list_block(label, node_type):
        cmds.text(label=label, align="left", font="smallPlainLabelFont")
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
        list_ui = cmds.textScrollList(numberOfRows=4, allowMultiSelection=True)
        cmds.columnLayout(rowSpacing=3)
        cmds.button(label="追加",   width=50,
                    command=lambda *_, lu=list_ui, nt=node_type: _list_add(lu, nt))
        cmds.button(label="削除",   width=50,
                    command=lambda *_, lu=list_ui: _list_remove(lu))
        cmds.button(label="全削除", width=50,
                    command=lambda *_, lu=list_ui: cmds.textScrollList(lu, edit=True, removeAll=True))
        cmds.setParent(".."); cmds.setParent("..")
        return list_ui

    curve_list_ui = _list_block("カーブ登録（選択して追加）",     "curve")
    joint_list_ui = _list_block("ジョイント登録（選択して追加）", "joint")
    cmds.text(label="※ リストの上から順番にペアになります", align="left",
              font="smallPlainLabelFont")
    cmds.setParent(".."); cmds.setParent("..")

    def _update_mode_frames(*_):
        is_manual = cmds.radioButton(rb_manual, query=True, select=True)
        cmds.frameLayout(frame_auto,   edit=True, visible=not is_manual)
        cmds.frameLayout(frame_manual, edit=True, visible=is_manual)
    cmds.radioButton(rb_name,   edit=True, onCommand=_update_mode_frames)
    cmds.radioButton(rb_dist,   edit=True, onCommand=_update_mode_frames)
    cmds.radioButton(rb_manual, edit=True, onCommand=_update_mode_frames)
    _update_mode_frames()

    cmds.separator(height=6, style="in")
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
    pair_preview = cmds.textScrollList(numberOfRows=5, allowMultiSelection=False)
    cmds.button(label="ペア解析", width=70,
                command=lambda *_: _do_analyze(
                    rb_name, rb_dist, rb_manual,
                    curve_list_ui, joint_list_ui, pair_preview, pair_status))
    cmds.setParent("..")

    cmds.separator(height=6, style="in")
    cmds.text(label="コンストレイント設定", align="left", font="smallBoldLabelFont")
    const_menu, rb_c2j, opt_mo, w = _build_constraint_options_ui()
    cmds.separator(height=8, style="in")
    pair_status = cmds.text(label="", align="left", font="smallPlainLabelFont")
    cmds.separator(height=4, style="none")

    def on_run(*_):
        items = cmds.textScrollList(pair_preview, query=True, allItems=True) or []
        pairs = []
        for item in items:
            parts = item.split("  ->  ")
            if len(parts) == 2:
                c, j = parts[0].strip(), parts[1].strip()
                pairs.append((c if c != "---" else None, j if j != "---" else None))
        if not pairs:
            cmds.text(pair_status, edit=True, label="先に「ペア解析」を実行してください。"); return
        ct, direction, opts = _collect_constraint_options(const_menu, rb_c2j, opt_mo, w)
        ok, ng = pair_run_constraints(pairs, ct, direction, opts)
        cmds.text(pair_status, edit=True, label="完了: {}件成功 / {}件失敗".format(ok, ng))

    cmds.button(label="コンストレイント適用", height=34, command=on_run,
                backgroundColor=(0.22, 0.48, 0.85))
    cmds.separator(height=8, style="none")
    cmds.setParent("..")


def _build_tab_normal_orient(parent):
    cmds.setParent(parent)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 10))
    cmds.separator(height=8, style="none")

    cmds.text(label="選択モード", align="left", font="smallBoldLabelFont")
    selmode_col = cmds.radioCollection()
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(175, 175),
                   columnAlign2=("center", "center"))
    sel_vtx  = cmds.radioButton(label="頂点 + ジョイント",   collection=selmode_col, select=True)
    sel_mesh = cmds.radioButton(label="メッシュ + ジョイント", collection=selmode_col)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")

    cmds.text(label="主軸 (子ジョイント方向)", align="left", font="smallBoldLabelFont")
    pri_col = cmds.radioCollection()
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(110, 110, 110),
                   columnAlign3=("center", "center", "center"))
    pri_x = cmds.radioButton(label="X", collection=pri_col, select=True)
    pri_y = cmds.radioButton(label="Y", collection=pri_col)
    pri_z = cmds.radioButton(label="Z", collection=pri_col)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")

    cmds.text(label="法線を合わせる軸", align="left", font="smallBoldLabelFont")
    nor_col = cmds.radioCollection()
    cmds.rowLayout(numberOfColumns=6, columnWidth6=(55, 55, 55, 60, 60, 60),
                   columnAlign6=("center","center","center","center","center","center"))
    cmds.radioButton(label="X",  collection=nor_col)
    cmds.radioButton(label="Y",  collection=nor_col)
    cmds.radioButton(label="Z",  collection=nor_col, select=True)
    cmds.radioButton(label="-X", collection=nor_col)
    cmds.radioButton(label="-Y", collection=nor_col)
    cmds.radioButton(label="-Z", collection=nor_col)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")

    cb_children = cmds.checkBox(label="子ジョイントにも同様の処理を行う", value=False)

    cmds.separator(height=6, style="none")

    cmds.text(label="適用モード", align="left", font="smallBoldLabelFont")
    mode_col = cmds.radioCollection()
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(175, 175),
                   columnAlign2=("center", "center"))
    mode_orient = cmds.radioButton(label="Joint Orient（推奨）", collection=mode_col, select=True)
    cmds.radioButton(label="ローカル回転", collection=mode_col)
    cmds.setParent("..")

    cmds.separator(height=10, style="in")

    info_txt = cmds.text(label="頂点 + ジョイントを選択して実行", align="center", font="smallPlainLabelFont")
    cmds.separator(height=4, style="none")

    def _sel_label(col):
        return cmds.radioButton(cmds.radioCollection(col, q=True, select=True), q=True, label=True)

    def on_apply(*_):
        primary   = _sel_label(pri_col)
        normal_ax = _sel_label(nor_col)
        mode      = "orient" if cmds.radioButton(mode_orient, q=True, select=True) else "rotate"
        sel_mode  = "vertex" if cmds.radioButton(sel_vtx,    q=True, select=True) else "mesh"
        inc_ch    = cmds.checkBox(cb_children, q=True, value=True)

        if primary == normal_ax.lstrip('-'):
            cmds.confirmDialog(title="Error",
                               message="主軸と法線軸に同じ軸は設定できません",
                               button=["OK"])
            return

        cmds.text(info_txt, edit=True, label="処理中...")
        try:
            apply_normal_to_joint_orient(primary, normal_ax, mode, sel_mode, inc_ch)
            cmds.text(info_txt, edit=True, label="完了")
        except Exception as e:
            cmds.text(info_txt, edit=True, label="エラー: {}".format(e))
            cmds.warning(str(e))

    cmds.button(label="実行", height=34, command=on_apply,
                backgroundColor=(0.22, 0.55, 0.38))
    cmds.separator(height=8, style="none")
    cmds.setParent("..")


# ================================================================
# -- Move to Center  コア処理 ----------------------------------
# ================================================================

def move_to_center_get_selection_center():
    """
    現在の選択（オブジェクト・頂点・エッジ・フェース）のワールド空間での中心を返す。
    戻り値: (x, y, z) のタプル、または選択がなければ None
    """
    sel = cmds.ls(selection=True, flatten=True)
    if not sel:
        return None

    vtx_positions = []

    for item in sel:
        # ---- 頂点 --------------------------------------------------------
        if ".vtx[" in item:
            pos = cmds.xform(item, query=True, worldSpace=True, translation=True)
            vtx_positions.append(pos)

        # ---- エッジ -------------------------------------------------------
        elif ".e[" in item:
            verts = cmds.polyListComponentConversion(item, toVertex=True)
            verts = cmds.ls(verts, flatten=True)
            for v in verts:
                pos = cmds.xform(v, query=True, worldSpace=True, translation=True)
                vtx_positions.append(pos)

        # ---- フェース -----------------------------------------------------
        elif ".f[" in item:
            verts = cmds.polyListComponentConversion(item, toVertex=True)
            verts = cmds.ls(verts, flatten=True)
            for v in verts:
                pos = cmds.xform(v, query=True, worldSpace=True, translation=True)
                vtx_positions.append(pos)

        # ---- UV ----------------------------------------------------------
        elif ".map[" in item:
            verts = cmds.polyListComponentConversion(item, toVertex=True)
            verts = cmds.ls(verts, flatten=True)
            for v in verts:
                pos = cmds.xform(v, query=True, worldSpace=True, translation=True)
                vtx_positions.append(pos)

        # ---- オブジェクト ------------------------------------------------
        else:
            try:
                bb = cmds.xform(item, query=True, worldSpace=True, boundingBox=True)
                cx = (bb[0] + bb[3]) / 2.0
                cy = (bb[1] + bb[4]) / 2.0
                cz = (bb[2] + bb[5]) / 2.0
                vtx_positions.append([cx, cy, cz])
            except Exception:
                pos = cmds.xform(item, query=True, worldSpace=True, rotatePivot=True)
                vtx_positions.append(pos)

    if not vtx_positions:
        return None

    n = len(vtx_positions)
    cx = sum(p[0] for p in vtx_positions) / n
    cy = sum(p[1] for p in vtx_positions) / n
    cz = sum(p[2] for p in vtx_positions) / n
    return (cx, cy, cz)


# ================================================================
# -- Move to Center  タブUI ------------------------------------
# ================================================================

def _build_tab_move_to_center(parent):
    """Move to Center タブ"""
    cmds.setParent(parent)

    # タブ内で中心座標を保持する辞書（クロージャで共有）
    _state = {"center": None}

    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=("both", 10))
    cmds.separator(height=8, style="none")

    # ── STEP 1 ──────────────────────────────────────
    cmds.frameLayout(
        label="STEP 1 : 中心を取得",
        collapsable=False, marginWidth=8, marginHeight=8,
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)

    cmds.text(
        label="頂点・エッジ・フェース・オブジェクトを選択してから\n「取得」ボタンを押してください。",
        align="left", wordWrap=True,
    )
    cmds.separator(height=4, style="none")

    cmds.button(
        label="選択の中心を取得",
        height=30,
        backgroundColor=(0.25, 0.55, 0.85),
        command=lambda *_: _on_get_center(),
    )

    cmds.separator(height=4, style="none")

    # 座標表示フィールド（X / Y / Z）
    cmds.rowLayout(numberOfColumns=6, adjustableColumn=True)
    cmds.text(label=" X:", font="boldLabelFont")
    fld_x = cmds.floatField(value=0.0, precision=4, editable=False, width=82,
                             backgroundColor=(0.18, 0.18, 0.18))
    cmds.text(label="  Y:", font="boldLabelFont")
    fld_y = cmds.floatField(value=0.0, precision=4, editable=False, width=82,
                             backgroundColor=(0.18, 0.18, 0.18))
    cmds.text(label="  Z:", font="boldLabelFont")
    fld_z = cmds.floatField(value=0.0, precision=4, editable=False, width=82,
                             backgroundColor=(0.18, 0.18, 0.18))
    cmds.setParent("..")  # rowLayout

    cmds.setParent("..")  # columnLayout (frame)
    cmds.setParent("..")  # frameLayout

    cmds.separator(height=6, style="none")

    # ── STEP 2 ──────────────────────────────────────
    cmds.frameLayout(
        label="STEP 2 : オブジェクトを移動",
        collapsable=False, marginWidth=8, marginHeight=8,
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)

    cmds.text(
        label="移動したいオブジェクトを選択してから\n「移動」ボタンを押してください。",
        align="left", wordWrap=True,
    )
    cmds.separator(height=4, style="none")

    # 移動基準オプション
    opt_pivot = cmds.radioButtonGrp(
        label="移動基準:  ",
        labelArray2=["ピボット（原点）", "バウンディングボックス底面"],
        numberOfRadioButtons=2,
        select=1,
        columnWidth3=(70, 130, 150),
    )

    cmds.separator(height=4, style="none")

    cmds.button(
        label="オブジェクトを移動",
        height=30,
        backgroundColor=(0.25, 0.75, 0.45),
        command=lambda *_: _on_move_object(),
    )

    cmds.setParent("..")   # columnLayout (frame)
    cmds.setParent("..")   # frameLayout

    # ステータスバー
    cmds.separator(height=6, style="in")
    lbl_status = cmds.text(label="ステータス: 待機中", align="left",
                           font="smallBoldLabelFont")
    cmds.separator(height=8, style="none")
    cmds.setParent("..")   # top columnLayout

    # ── コールバック ───────────────────────────────

    def _set_status(msg, error=False):
        cmds.text(lbl_status, edit=True, label="ステータス: " + msg)

    def _on_get_center():
        result = move_to_center_get_selection_center()
        if result is None:
            _set_status("⚠  選択がありません。コンポーネントかオブジェクトを選択してください。", error=True)
            return

        _state["center"] = result
        cmds.floatField(fld_x, edit=True, value=result[0])
        cmds.floatField(fld_y, edit=True, value=result[1])
        cmds.floatField(fld_z, edit=True, value=result[2])

        sel = cmds.ls(selection=True, flatten=True)
        if sel:
            first = sel[0]
            if any(c in first for c in [".vtx[", ".e[", ".f[", ".map["]):
                kind = "コンポーネント ({} 個)".format(len(sel))
            else:
                kind = "オブジェクト ({} 個)".format(len(sel))
        else:
            kind = "不明"

        _set_status(
            "✔ 取得 [{kind}]  ({x:.4f}, {y:.4f}, {z:.4f})".format(
                kind=kind, x=result[0], y=result[1], z=result[2]
            )
        )

    def _on_move_object():
        if _state["center"] is None:
            _set_status("⚠  先に STEP 1 で中心を取得してください。", error=True)
            return

        # トランスフォームノードとして選択を取得
        sel = cmds.ls(selection=True, long=True, transforms=True)

        # コンポーネント選択状態の場合は親オブジェクトを取得
        if not sel:
            raw = cmds.ls(selection=True, flatten=True)
            parents = set()
            for r in raw:
                if "." in r:
                    node = r.split(".")[0]
                    t = cmds.listRelatives(node, parent=True, fullPath=True)
                    if t:
                        parents.add(t[0])
                    else:
                        parents.add(node)
                else:
                    parents.add(r)
            sel = list(parents)

        if not sel:
            _set_status("⚠  移動するオブジェクトが選択されていません。", error=True)
            return

        cx, cy, cz = _state["center"]
        use_bb_bottom = cmds.radioButtonGrp(opt_pivot, query=True, select=True) == 2

        moved = []
        for obj in sel:
            if use_bb_bottom:
                bb     = cmds.xform(obj, query=True, worldSpace=True, boundingBox=True)
                pivot  = cmds.xform(obj, query=True, worldSpace=True, rotatePivot=True)
                offset_y = pivot[1] - bb[1]
                cmds.xform(obj, worldSpace=True, translation=[cx, cy + offset_y, cz])
            else:
                cmds.xform(obj, worldSpace=True, translation=[cx, cy, cz])
            moved.append(obj.split("|")[-1])

        _set_status(
            "✔ 移動: [{objs}] → ({x:.4f}, {y:.4f}, {z:.4f})".format(
                objs=", ".join(moved), x=cx, y=cy, z=cz
            )
        )


# ================================================================
# -- IK/FK BlendColors Setup  コア処理 -------------------------
# ================================================================

def _ikfk_normalize(name):
    return name.split("|")[-1]


def _ikfk_strip_tag(name, tag):
    tag_lower = tag.lower()
    tokens    = name.split("_")
    filtered  = [t for t in tokens if t.lower() != tag_lower]
    return "_".join(filtered)


def _ikfk_has_tag(name, tag_lower):
    return tag_lower in [t.lower() for t in name.split("_")]


def ikfk_match_joints(joints, ik_tag, fk_tag):
    short_names  = [_ikfk_normalize(j) for j in joints]
    ik_tag_lower = ik_tag.lower()
    fk_tag_lower = fk_tag.lower()

    ik_joints     = {}
    fk_joints     = {}
    result_joints = {}
    unmatched     = []

    for jnt in short_names:
        has_ik = _ikfk_has_tag(jnt, ik_tag_lower)
        has_fk = _ikfk_has_tag(jnt, fk_tag_lower)
        if has_ik:
            base = _ikfk_strip_tag(jnt, ik_tag)
            ik_joints[base] = jnt
        elif has_fk:
            base = _ikfk_strip_tag(jnt, fk_tag)
            fk_joints[base] = jnt
        else:
            result_joints[jnt] = jnt

    trios        = []
    used_results = set()
    common_bases = set(ik_joints.keys()) & set(fk_joints.keys())

    for base in sorted(common_bases):
        if base in result_joints and base not in used_results:
            trios.append({
                "base":   base,
                "ik":     ik_joints[base],
                "fk":     fk_joints[base],
                "result": result_joints[base],
            })
            used_results.add(base)
        else:
            unmatched.append(ik_joints[base])
            unmatched.append(fk_joints[base])

    for base, jnt in ik_joints.items():
        if base not in common_bases:
            unmatched.append(jnt)
    for base, jnt in fk_joints.items():
        if base not in common_bases:
            unmatched.append(jnt)
    for base, jnt in result_joints.items():
        if base not in used_results:
            unmatched.append(jnt)

    return trios, unmatched


def _ikfk_get_existing_blend_node(result_jnt):
    sources = cmds.listConnections(
        result_jnt + ".rotate", source=True, destination=False, type="blendColors"
    ) or []
    return sources[0] if sources else None


def _ikfk_safe_connect(src, dst, force=False):
    if cmds.isConnected(src, dst):
        return
    existing_src = cmds.listConnections(dst, source=True, destination=False, plugs=True)
    if existing_src:
        if force:
            cmds.disconnectAttr(existing_src[0], dst)
        else:
            return
    try:
        cmds.connectAttr(src, dst, force=force)
    except Exception as e:
        cmds.warning("[IKFK] 接続失敗 {} -> {}: {}".format(src, dst, e))


def ikfk_setup_trio(trio, force=False):
    ik_jnt     = trio["ik"]
    fk_jnt     = trio["fk"]
    result_jnt = trio["result"]
    base       = trio["base"]

    for jnt in (ik_jnt, fk_jnt, result_jnt):
        if not cmds.objExists(jnt):
            return False, "ジョイントが見つかりません: {}".format(jnt)

    existing = _ikfk_get_existing_blend_node(result_jnt)
    if existing and not force:
        return None, "既存の BlendColors '{}' が {} に接続されています。".format(existing, result_jnt)

    blend_name = base + "_blendColors"
    if existing and force:
        blend_node = existing
    else:
        if cmds.objExists(blend_name):
            blend_node = cmds.createNode("blendColors")
            blend_node = cmds.rename(blend_node, blend_name + "_new")
        else:
            blend_node = cmds.createNode("blendColors", name=blend_name)

    _AXIS_TO_RGB = {"X": "R", "Y": "G", "Z": "B"}
    for axis in ("X", "Y", "Z"):
        ch = _AXIS_TO_RGB[axis]
        _ikfk_safe_connect("{}.rotate{}".format(ik_jnt,     axis),
                           "{}.color1{}".format(blend_node,  ch), force)
        _ikfk_safe_connect("{}.rotate{}".format(fk_jnt,     axis),
                           "{}.color2{}".format(blend_node,  ch), force)
        _ikfk_safe_connect("{}.output{}".format(blend_node,  ch),
                           "{}.rotate{}".format(result_jnt, axis), force)

    return True, "セットアップ完了: {} -> {}".format(base, blend_node)


# ================================================================
# -- IK/FK BlendColors Setup  タブUI ---------------------------
# ================================================================

def _build_tab_ikfk(parent):
    cmds.setParent(parent)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4, columnOffset=("both", 8))

    cmds.separator(height=8, style="none")
    cmds.frameLayout(label="タグ設定", collapsable=True, collapse=False,
                     marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.rowLayout(numberOfColumns=4,
                   columnWidth4=(80, 120, 80, 120),
                   columnAlign4=("right", "left", "right", "left"))
    cmds.text(label="IKタグ:", align="right")
    ik_field = cmds.textField(text="IK", width=110)
    cmds.text(label="FKタグ:", align="right")
    fk_field = cmds.textField(text="FK", width=110)
    cmds.setParent("..")
    cmds.text(label="※ タグはアンダースコア区切りで検索します（大文字小文字不問）",
              align="left", font="smallPlainLabelFont")
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.frameLayout(label="ジョイント選択 & マッチング", collapsable=True, collapse=False,
                     marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="ビューポートでジョイントを選択してから「マッチング実行」を押してください。",
              align="left", wordWrap=True, font="smallPlainLabelFont")
    match_btn = cmds.button(label="▶  選択ジョイントをマッチング", height=30,
                            backgroundColor=(0.25, 0.55, 0.45))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.frameLayout(label="マッチング結果", collapsable=True, collapse=False,
                     marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)

    cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 120, 120),
                   columnAlign3=("center", "center", "center"),
                   backgroundColor=(0.2, 0.2, 0.2))
    cmds.text(label="IKジョイント",  align="center", font="boldLabelFont")
    cmds.text(label="FKジョイント",  align="center", font="boldLabelFont")
    cmds.text(label="結果ジョイント", align="center", font="boldLabelFont")
    cmds.setParent("..")

    trio_scroll = cmds.scrollLayout(height=150, childResizable=True,
                                    horizontalScrollBarThickness=0)
    trio_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=1)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=4, style="in")
    cmds.text(label="未マッチ:", align="left", font="smallPlainLabelFont")
    unmatched_field = cmds.scrollField(height=40, editable=False, wordWrap=False,
                                       backgroundColor=(0.18, 0.18, 0.18))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.frameLayout(label="セットアップ実行", collapsable=False,
                     marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)

    overwrite_cb = cmds.checkBox(label="既存のBlendColors接続を上書きする", value=False)
    run_btn = cmds.button(label="✦  セットアップ実行", height=36,
                          backgroundColor=(0.2, 0.4, 0.65), enable=False)

    cmds.separator(height=4, style="in")
    cmds.text(label="ログ:", align="left", font="smallPlainLabelFont")
    log_field = cmds.scrollField(height=70, editable=False, wordWrap=True,
                                 backgroundColor=(0.15, 0.15, 0.15))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=8, style="none")

    _state = {"trios": [], "unmatched": []}

    def _log(text):
        cur = cmds.scrollField(log_field, query=True, text=True)
        new = (cur + "\n" + text).strip()
        cmds.scrollField(log_field, edit=True, text=new)
        cmds.scrollField(log_field, edit=True, insertionPosition=len(new))

    def _on_match(*_):
        selection = cmds.ls(selection=True, type="joint") or []
        if not selection:
            _log("⚠ ジョイントが選択されていません。"); return

        ik_tag = cmds.textField(ik_field, query=True, text=True).strip()
        fk_tag = cmds.textField(fk_field, query=True, text=True).strip()
        if not ik_tag or not fk_tag:
            _log("⚠ IKタグまたはFKタグが空です。"); return

        trios, unmatched = ikfk_match_joints(selection, ik_tag, fk_tag)
        _state["trios"]     = trios
        _state["unmatched"] = unmatched

        children = cmds.columnLayout(trio_col, query=True, childArray=True) or []
        for c in children:
            cmds.deleteUI(c)
        cmds.setParent(trio_col)
        if trios:
            for i, t in enumerate(trios):
                bg = (0.22, 0.22, 0.22) if i % 2 == 0 else (0.19, 0.19, 0.19)
                cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 120, 120),
                               columnAlign3=("center", "center", "center"),
                               backgroundColor=bg)
                cmds.text(label=t["ik"],     align="center", font="smallPlainLabelFont")
                cmds.text(label=t["fk"],     align="center", font="smallPlainLabelFont")
                cmds.text(label=t["result"], align="center", font="smallPlainLabelFont")
                cmds.setParent("..")
        else:
            cmds.text(label="（マッチング結果なし）", align="center",
                      font="smallPlainLabelFont")

        cmds.scrollField(unmatched_field, edit=True,
                         text="\n".join(unmatched) if unmatched else "（なし）")
        cmds.button(run_btn, edit=True, enable=bool(trios))

        parts = ["マッチング: {}トリオ".format(len(trios))]
        if unmatched:
            parts.append("未マッチ: {}件".format(len(unmatched)))
        _log(" / ".join(parts))

    cmds.button(match_btn, edit=True, command=_on_match)

    def _on_execute(*_):
        trios = _state["trios"]
        if not trios:
            _log("⚠ マッチング結果がありません。先にマッチングを実行してください。"); return

        force = cmds.checkBox(overwrite_cb, query=True, value=True)

        needs_confirm = []
        if not force:
            for trio in trios:
                existing = _ikfk_get_existing_blend_node(trio["result"])
                if existing:
                    needs_confirm.append((trio["result"], existing))

        if needs_confirm:
            msg = "以下のジョイントに既存のBlendColors接続があります:\n"
            for jnt, node in needs_confirm:
                msg += "  {}  ->  {}\n".format(jnt, node)
            msg += "\n上書きして続行しますか？"
            confirm = cmds.confirmDialog(
                title="既存接続の確認",
                message=msg,
                button=["上書きして実行", "スキップして実行", "キャンセル"],
                defaultButton="上書きして実行",
                cancelButton="キャンセル",
                dismissString="キャンセル",
            )
            if confirm == "キャンセル":
                _log("キャンセルされました。"); return
            elif confirm == "上書きして実行":
                force = True

        ok = skip = ng = 0
        for trio in trios:
            result, msg = ikfk_setup_trio(trio, force=force)
            if result is True:
                ok += 1
                _log("✓ " + msg)
            elif result is None:
                skip += 1
                _log("－ スキップ: {} （既存接続あり）".format(trio["base"]))
            else:
                ng += 1
                _log("✗ " + msg)

        _log("─" * 36)
        _log("完了: 成功 {} / スキップ {} / エラー {}".format(ok, skip, ng))

    cmds.button(run_btn, edit=True, command=_on_execute)
    cmds.setParent("..")


# ================================================================
# -- BlendColors Finder  コア処理 ------------------------------
# ================================================================

def _bcfind_trace_to_blendcolors(node, attr, direction, visited=None):
    if visited is None:
        visited = set()
    key = "{}.{}".format(node, attr)
    if key in visited:
        return set()
    visited.add(key)

    result = set()
    is_dst = (direction == "dst")

    conns = cmds.listConnections(
        key, source=not is_dst, destination=is_dst, plugs=True,
    ) or []

    for plug in conns:
        conn_node = plug.split(".")[0]
        conn_attr = plug.split(".", 1)[1] if "." in plug else ""
        node_type = cmds.nodeType(conn_node)

        if node_type == "blendColors":
            result.add(conn_node)
        elif node_type == "unitConversion":
            next_attr = "output" if is_dst else "input"
            result.update(_bcfind_trace_to_blendcolors(
                conn_node, next_attr, direction, visited))

    return result


def _bcfind_get_connected_blend_nodes(joint):
    found = set()
    short = joint.split("|")[-1]
    for attr in ("rotate", "rotateX", "rotateY", "rotateZ"):
        found.update(_bcfind_trace_to_blendcolors(short, attr, "dst"))
        found.update(_bcfind_trace_to_blendcolors(short, attr, "src"))
    return list(found)


def _bcfind_trace_joint(node, attr, direction, visited=None):
    if visited is None:
        visited = set()
    key = "{}.{}".format(node, attr)
    if key in visited:
        return ""
    visited.add(key)

    is_dst = (direction == "dst")
    conns = cmds.listConnections(
        key, source=not is_dst, destination=is_dst, plugs=True,
    ) or []

    for plug in conns:
        conn_node = plug.split(".")[0]
        conn_attr = plug.split(".", 1)[1] if "." in plug else ""
        node_type = cmds.nodeType(conn_node)

        if node_type == "joint":
            return conn_node.split("|")[-1]
        elif node_type in ("unitConversion",):
            next_attr = "output" if is_dst else "input"
            found = _bcfind_trace_joint(conn_node, next_attr, direction, visited)
            if found:
                return found

    return ""


def _bcfind_analyze_node(blend_node):
    def _src(attr):
        return _bcfind_trace_joint(blend_node, attr, "src")
    def _dst(attr):
        return _bcfind_trace_joint(blend_node, attr, "dst")

    color1_src = _src("color1R") or _src("color1G") or _src("color1B") or _src("color1")
    color2_src = _src("color2R") or _src("color2G") or _src("color2B") or _src("color2")
    output_dst = _dst("outputR") or _dst("outputG") or _dst("outputB") or _dst("output")
    expected   = (output_dst + "_blendColors") if output_dst else ""

    return {
        "node":          blend_node,
        "color1_src":    color1_src,
        "color2_src":    color2_src,
        "output_dst":    output_dst,
        "expected_name": expected,
    }


def bcfind_search(joints):
    found_nodes = set()
    for jnt in joints:
        for node in _bcfind_get_connected_blend_nodes(jnt):
            found_nodes.add(node)
    results = []
    for node in sorted(found_nodes):
        results.append(_bcfind_analyze_node(node))
    return results


def bcfind_rename_node(info):
    old_name = info["node"]
    new_name = info["expected_name"]
    if not new_name:
        return False, old_name, "output先ジョイントが不明のためリネーム不可"
    if old_name == new_name:
        return True, old_name, new_name
    if not cmds.objExists(old_name):
        return False, old_name, "ノードが存在しません: {}".format(old_name)
    target = new_name
    if cmds.objExists(new_name) and new_name != old_name:
        target = new_name + "_renamed"
    try:
        cmds.rename(old_name, target)
        return True, old_name, target
    except Exception as e:
        return False, old_name, str(e)


# ================================================================
# -- BlendColors Finder  タブUI --------------------------------
# ================================================================

def _build_tab_bcfind(parent):
    cmds.setParent(parent)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4, columnOffset=("both", 8))

    cmds.separator(height=8, style="none")
    cmds.frameLayout(label="BlendColors 検索", collapsable=False,
                     marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(
        label="ジョイントを選択して検索を実行します。\n"
              "IK / FK / 結果ジョイントのどれからでも検索できます。",
        align="left", font="smallPlainLabelFont"
    )
    search_btn = cmds.button(label="🔍  選択ジョイントから BlendColors を検索",
                             height=32, backgroundColor=(0.25, 0.50, 0.55))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.frameLayout(label="検索結果", collapsable=False,
                     marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)

    cmds.rowLayout(
        numberOfColumns=6,
        columnWidth6=(140, 100, 100, 100, 60, 60),
        columnAlign6=("center","center","center","center","center","center"),
        backgroundColor=(0.18, 0.18, 0.18),
    )
    cmds.text(label="BlendColorsノード", align="center", font="boldLabelFont")
    cmds.text(label="color1 (IK)",       align="center", font="boldLabelFont")
    cmds.text(label="color2 (FK)",       align="center", font="boldLabelFont")
    cmds.text(label="output先",          align="center", font="boldLabelFont")
    cmds.text(label="選択",              align="center", font="boldLabelFont")
    cmds.text(label="リネーム",          align="center", font="boldLabelFont")
    cmds.setParent("..")

    result_scroll = cmds.scrollLayout(height=200, childResizable=True,
                                      horizontalScrollBarThickness=0)
    result_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=1)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=4, style="in")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(190, 190),
                   columnAlign2=("center", "center"))
    sel_all_btn    = cmds.button(label="◈  全ノードを選択",
                                 height=28, width=185,
                                 backgroundColor=(0.30, 0.38, 0.55),
                                 enable=False)
    rename_all_btn = cmds.button(label="✎  全ノードをリネーム",
                                 height=28, width=185,
                                 backgroundColor=(0.50, 0.38, 0.22),
                                 enable=False)
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.frameLayout(label="ログ", collapsable=True, collapse=False,
                     marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True)
    log_field = cmds.scrollField(height=70, editable=False, wordWrap=True,
                                 backgroundColor=(0.15, 0.15, 0.15))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=8, style="none")
    cmds.setParent("..")

    _state = {"results": []}

    def _log(text):
        cur = cmds.scrollField(log_field, query=True, text=True)
        new = (cur + "\n" + text).strip()
        cmds.scrollField(log_field, edit=True, text=new)
        cmds.scrollField(log_field, edit=True, insertionPosition=len(new))

    def _rebuild_rows(results):
        kids = cmds.columnLayout(result_col, query=True, childArray=True) or []
        for k in kids:
            cmds.deleteUI(k)
        cmds.setParent(result_col)
        if not results:
            cmds.text(label="（結果なし）", align="center", font="smallPlainLabelFont")
            return
        for i, info in enumerate(results):
            bg = (0.22, 0.22, 0.22) if i % 2 == 0 else (0.19, 0.19, 0.19)
            name_match = (info["node"] == info["expected_name"] or not info["expected_name"])
            node_color = bg if name_match else (0.40, 0.25, 0.18)
            cmds.rowLayout(
                numberOfColumns=6,
                columnWidth6=(140, 100, 100, 100, 60, 60),
                columnAlign6=("left","center","center","center","center","center"),
                backgroundColor=node_color,
            )
            cmds.text(label=" " + info["node"], align="left", font="smallPlainLabelFont",
                      annotation=("期待名: " + info["expected_name"]) if info["expected_name"] else "")
            cmds.text(label=info["color1_src"] or "---", align="center", font="smallPlainLabelFont")
            cmds.text(label=info["color2_src"] or "---", align="center", font="smallPlainLabelFont")
            cmds.text(label=info["output_dst"] or "---", align="center", font="smallPlainLabelFont")
            _info_ref = dict(info)
            cmds.button(label="選択", width=55, height=22,
                        backgroundColor=(0.28, 0.36, 0.52),
                        command=lambda *_, n=_info_ref["node"]: _select_node(n))
            rename_enable = bool(info["expected_name"]) and (info["node"] != info["expected_name"])
            cmds.button(label="リネーム", width=55, height=22,
                        backgroundColor=(0.48, 0.36, 0.20),
                        enable=rename_enable,
                        command=lambda *_, inf=_info_ref: _rename_single(inf))
            cmds.setParent("..")

    def _select_node(node_name):
        if cmds.objExists(node_name):
            cmds.select(node_name, replace=True)
            _log("選択: {}".format(node_name))
        else:
            _log("⚠ ノードが見つかりません: {}".format(node_name))

    def _rename_single(info):
        ok, old, new = bcfind_rename_node(info)
        if ok:
            _log("✓ リネーム: {} → {}".format(old, new))
            for r in _state["results"]:
                if r["node"] == old:
                    r["node"] = new
                    break
            _rebuild_rows(_state["results"])
        else:
            _log("✗ リネーム失敗: {} （{}）".format(old, new))

    def _on_search(*_):
        selection = cmds.ls(selection=True, type="joint") or []
        if not selection:
            _log("⚠ ジョイントが選択されていません。"); return
        results = bcfind_search(selection)
        _state["results"] = results
        _rebuild_rows(results)
        cmds.button(sel_all_btn,    edit=True, enable=bool(results))
        cmds.button(rename_all_btn, edit=True, enable=bool(results))
        if results:
            _log("検索完了: {}件の BlendColors を発見。".format(len(results)))
            needs_rename = [r for r in results
                            if r["expected_name"] and r["node"] != r["expected_name"]]
            if needs_rename:
                _log("  うち {}件 は命名規則と不一致です（行が橙色で表示）。".format(len(needs_rename)))
        else:
            _log("⚠ 選択ジョイントに接続された BlendColors が見つかりませんでした。")

    cmds.button(search_btn, edit=True, command=_on_search)

    def _on_select_all(*_):
        nodes = [r["node"] for r in _state["results"] if cmds.objExists(r["node"])]
        if nodes:
            cmds.select(nodes, replace=True)
            _log("全選択: {} ノード".format(len(nodes)))
        else:
            _log("⚠ 有効なノードが見つかりません。")

    cmds.button(sel_all_btn, edit=True, command=_on_select_all)

    def _on_rename_all(*_):
        results = _state["results"]
        targets = [r for r in results
                   if r["expected_name"] and r["node"] != r["expected_name"]]
        if not targets:
            _log("リネームが必要なノードはありません。"); return
        confirm = cmds.confirmDialog(
            title="一括リネーム確認",
            message="{}件のノードをリネームします。よろしいですか？".format(len(targets)),
            button=["実行", "キャンセル"],
            defaultButton="実行", cancelButton="キャンセル", dismissString="キャンセル",
        )
        if confirm != "実行":
            _log("キャンセルされました。"); return
        ok_count = ng_count = 0
        for info in targets:
            ok, old, new = bcfind_rename_node(info)
            if ok:
                ok_count += 1
                _log("✓ {} → {}".format(old, new))
                for r in _state["results"]:
                    if r["node"] == old:
                        r["node"] = new
                        break
            else:
                ng_count += 1
                _log("✗ {} （{}）".format(old, new))
        _rebuild_rows(_state["results"])
        _log("─" * 36)
        _log("一括リネーム完了: 成功 {} / 失敗 {}".format(ok_count, ng_count))

    cmds.button(rename_all_btn, edit=True, command=_on_rename_all)


# ================================================================
# -- リスト操作ヘルパー -----------------------------------------
# ================================================================

def _list_add(list_ui, node_type):
    sel      = cmds.ls(selection=True, long=False)
    existing = cmds.textScrollList(list_ui, query=True, allItems=True) or []
    for node in sel:
        if node_type == "curve":
            shapes = cmds.listRelatives(node, shapes=True) or []
            if not any(cmds.nodeType(s) == "nurbsCurve" for s in shapes): continue
        elif node_type == "joint":
            if cmds.nodeType(node) != "joint": continue
        if node not in existing:
            cmds.textScrollList(list_ui, edit=True, append=node)


def _list_remove(list_ui):
    for item in (cmds.textScrollList(list_ui, query=True, selectItem=True) or []):
        cmds.textScrollList(list_ui, edit=True, removeItem=item)


def _get_sel_curves_joints():
    sel = cmds.ls(selection=True, long=False)
    curves, joints = [], []
    for node in sel:
        shapes = cmds.listRelatives(node, shapes=True) or []
        if any(cmds.nodeType(s) == "nurbsCurve" for s in shapes): curves.append(node)
        elif cmds.nodeType(node) == "joint": joints.append(node)
    return curves, joints


def _do_analyze(rb_name, rb_dist, rb_manual,
                curve_list_ui, joint_list_ui, pair_preview, status):
    cmds.textScrollList(pair_preview, edit=True, removeAll=True)
    if cmds.radioButton(rb_manual, query=True, select=True):
        curves = cmds.textScrollList(curve_list_ui, query=True, allItems=True) or []
        joints = cmds.textScrollList(joint_list_ui, query=True, allItems=True) or []
        n      = max(len(curves), len(joints)) if (curves or joints) else 0
        pairs  = [(curves[i] if i < len(curves) else None,
                   joints[i] if i < len(joints) else None) for i in range(n)]
    else:
        curves, joints = _get_sel_curves_joints()
        if not curves: cmds.text(status, edit=True, label="カーブが選択されていません。"); return
        if not joints: cmds.text(status, edit=True, label="ジョイントが選択されていません。"); return
        pairs = pair_by_name(curves, joints) if cmds.radioButton(rb_name, query=True, select=True)\
                else pair_by_distance(curves, joints)
    for c, j in pairs:
        cmds.textScrollList(pair_preview, edit=True,
                            append="{}  ->  {}".format(c or "---", j or "---"))
    cmds.text(status, edit=True, label="{}ペアを解析しました。".format(len(pairs)))


# ================================================================
# -- メインウィンドウ ------------------------------------------
# ================================================================

WINDOW_ID = "riggingToolkitWin"


def build_main_ui():
    if cmds.window(WINDOW_ID, exists=True):
        cmds.deleteUI(WINDOW_ID)

    cmds.window(WINDOW_ID, title="Rigging Toolkit", widthHeight=(430, 100), sizeable=True)
    cmds.columnLayout(adjustableColumn=True)

    # エディタ呼び出しボタン
    cmds.frameLayout(label="Maya エディタ", collapsable=True, marginWidth=8, marginHeight=6)
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(120,120,120))
    cmds.button(label="ノードエディタ",         height=28,
                command=lambda *_: mel.eval('NodeEditorWindow'))
    cmds.button(label="シェイプエディタ",       height=28,
                command=lambda *_: mel.eval('ShapeEditor'))
    cmds.button(label="セットドリブンエディタ", height=28,
                command=lambda *_: _open_sdk_editor())
    cmds.setParent(".."); cmds.setParent("..")

    tabs = cmds.tabLayout(innerMarginWidth=0, innerMarginHeight=0)

    snap_tab       = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")
    color_tab      = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")
    pair_tab       = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")
    normal_tab     = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")
    ctrldup_tab    = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")
    ikfk_tab       = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")
    bcfind_tab     = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")
    move2center_tab = cmds.columnLayout(adjustableColumn=True); cmds.setParent("..")  # ← 追加

    cmds.tabLayout(tabs, edit=True, tabLabel=[
        (snap_tab,        "カーブスナップ"),
        (color_tab,       "カラー上書き"),
        (pair_tab,        "コンストレイントペア"),
        (normal_tab,      "法線方向付け"),
        (ctrldup_tab,     "コントローラー複製"),
        (ikfk_tab,        "IK/FKブレンド"),
        (bcfind_tab,      "BC検索"),
        (move2center_tab, "中心に移動"),          # ← 追加
    ])

    _build_tab_snap(snap_tab)
    _build_tab_color(color_tab)
    _build_tab_pair(pair_tab)
    _build_tab_normal_orient(normal_tab)
    _build_tab_ctrldup(ctrldup_tab)
    _build_tab_ikfk(ikfk_tab)
    _build_tab_bcfind(bcfind_tab)
    _build_tab_move_to_center(move2center_tab)   # ← 追加

    cmds.setParent("..")
    cmds.setParent("..")

    cmds.showWindow(WINDOW_ID)


# ================================================================
# エントリーポイント
# ================================================================

build_main_ui()