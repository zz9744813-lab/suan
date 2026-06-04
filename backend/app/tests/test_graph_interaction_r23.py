"""R23: 锁定 GraphPage 交互式图谱的核心几何变换。

具体来说: 在 pan/zoom/fitAll/focusOnNode 几个变换中, 最关键的
不变量是 "用户光标下的 viewBox 点在缩放后仍在光标下" — 如果这个
错了, 滚轮缩放看起来"图在飞"而不是"图在那里放大"。

这个测试不启动浏览器 (前端 SVG 数学), 我们直接把 GraphPage
里的核心公式提到纯函数实现再测, 行为必须一致。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ----- 核心变换公式 (跟 GraphPage.tsx handleWheel 完全一致) -----

def zoom_at_point(t, svg_x, svg_y, factor, k_min=0.2, k_max=4.0):
    """以 svg_x, svg_y 为中心缩放 (k 乘 factor, 限制在 [k_min, k_max])。

    不变量: 缩放前后, viewBox 坐标 (svg_x, svg_y) 在屏幕上保持原位。
    屏幕坐标 = t.x + svg_x * t.k
    """
    new_k = max(k_min, min(k_max, t["k"] * factor))
    return {
        "x": t["x"] - svg_x * (new_k - t["k"]),
        "y": t["y"] - svg_y * (new_k - t["k"]),
        "k": new_k,
    }


def screen_pos(t, vb_x, vb_y):
    """viewBox 坐标 -> 屏幕坐标 (0..1 normalized if 跟 viewBox 一样大)。

    公式: screenX = t.x + vbX * t.k
    """
    return (t["x"] + vb_x * t["k"], t["y"] + vb_y * t["k"])


# ----- 测试: 缩放中心不变量 --------------------------------------

def test_zoom_keeps_cursor_point_stationary():
    """光标在 viewBox 坐标 (500, 300), 缩放 1.5x 后, 该点
    在屏幕坐标中应该跟缩放前完全一致。"""
    t0 = {"x": 0, "y": 0, "k": 1.0}
    cursor_vb = (500, 300)
    # 缩放前光标点的屏幕坐标
    sx0, sy0 = screen_pos(t0, *cursor_vb)
    # 缩放
    t1 = zoom_at_point(t0, *cursor_vb, factor=1.5)
    # 缩放后光标点的屏幕坐标 — 应该 == (sx0, sy0)
    sx1, sy1 = screen_pos(t1, *cursor_vb)
    assert abs(sx1 - sx0) < 1e-9, f"x shifted: {sx0} -> {sx1}"
    assert abs(sy1 - sy0) < 1e-9, f"y shifted: {sy0} -> {sy1}"


def test_zoom_zoom_out_keeps_point_stationary():
    """zoom out (factor=1/1.5) 也保持不变。"""
    t0 = {"x": 50, "y": -30, "k": 2.0}
    cursor_vb = (200, 400)
    sx0, sy0 = screen_pos(t0, *cursor_vb)
    t1 = zoom_at_point(t0, *cursor_vb, factor=1 / 1.5)
    sx1, sy1 = screen_pos(t1, *cursor_vb)
    assert abs(sx1 - sx0) < 1e-9, f"x shifted: {sx0} -> {sx1}"
    assert abs(sy1 - sy0) < 1e-9, f"y shifted: {sy0} -> {sy1}"


def test_zoom_clamped_at_k_min():
    """缩太多次, k 不会突破 k_min。"""
    t0 = {"x": 0, "y": 0, "k": 0.3}
    t1 = zoom_at_point(t0, 100, 100, factor=1 / 1.5, k_min=0.2, k_max=4.0)
    assert t1["k"] >= 0.2, f"k underflow: {t1['k']}"


def test_zoom_clamped_at_k_max():
    """缩太大, k 不会突破 k_max。"""
    t0 = {"x": 0, "y": 0, "k": 3.5}
    t1 = zoom_at_point(t0, 100, 100, factor=2.0, k_min=0.2, k_max=4.0)
    assert t1["k"] <= 4.0, f"k overflow: {t1['k']}"


# ----- 测试: fitAll 公式 -----------------------------------------

def fit_transform(nodes, container_w, container_h, viewbox_w, viewbox_h, padding=0.9):
    """把 nodes 列表铺满容器。

    公式 (跟 GraphPage.tsx::fitAll 一致):
      1. 算所有节点的 bbox (含半径)
      2. k = min(container_w / w, container_h / h) * padding
      3. 让 bbox 中心 → viewBox 中心:
         t.x = viewbox_w/2 - cx * k
    """
    if not nodes:
        return {"x": 0, "y": 0, "k": 1}
    min_x = min(n["x"] - n["r"] for n in nodes)
    min_y = min(n["y"] - n["r"] for n in nodes)
    max_x = max(n["x"] + n["r"] for n in nodes)
    max_y = max(n["y"] + n["r"] for n in nodes)
    w = max_x - min_x
    h = max_y - min_y
    k = min(container_w / w, container_h / h) * padding
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    return {
        "x": viewbox_w / 2 - cx * k,
        "y": viewbox_h / 2 - cy * k,
        "k": k,
    }


def test_fit_all_centers_graph():
    """fit 之后, bbox 中心应该映射到 viewBox 中心 (viewbox_w/2, viewbox_h/2)。"""
    nodes = [
        {"x": 100, "y": 200, "r": 10},
        {"x": 500, "y": 600, "r": 10},
        {"x": 300, "y": 400, "r": 10},
    ]
    t = fit_transform(nodes, container_w=800, container_h=600, viewbox_w=1200, viewbox_h=700)
    # bbox 中心 = (300, 400)
    sx, sy = screen_pos(t, 300, 400)
    assert abs(sx - 600) < 1e-6, f"bbox center not at viewBox center: sx={sx}"
    assert abs(sy - 350) < 1e-6, f"bbox center not at viewBox center: sy={sy}"


def test_fit_all_zooms_to_fit():
    """fit 之后, 最左/最右节点都在容器内。

    注意: fit 公式把 bbox 中心对齐到 viewBox 中心 (viewbox_w/2,
    viewbox_h/2)。container 是另一个独立维度 (SVG 缩放后渲染)。
    所以我们检查 viewBox 坐标 [0, viewbox_w] 内的范围, 跟
    container 的实际像素宽窄无关。
    """
    nodes = [
        {"x": 100, "y": 200, "r": 10},
        {"x": 500, "y": 600, "r": 10},
    ]
    t = fit_transform(nodes, container_w=800, container_h=600, viewbox_w=1200, viewbox_h=700)
    # bbox 范围: x=90..510, 屏幕 width = 420 * k
    k = t["k"]
    bbox_screen_w = 420 * k
    # bbox 中心 = 300, 映射到 viewbox_w/2 = 600
    cx_screen = screen_pos(t, 300, 400)[0]
    assert abs(cx_screen - 600) < 1e-6, f"center off: {cx_screen}"
    # 最左最右: 在 [cx_screen - bbox_screen_w/2, cx_screen + bbox_screen_w/2] 范围内
    left_screen = cx_screen - bbox_screen_w / 2
    right_screen = cx_screen + bbox_screen_w / 2
    assert 0 < left_screen, f"leftmost off-viewbox: {left_screen}"
    assert right_screen < 1200, f"rightmost off-viewbox: {right_screen}"


def test_fit_all_empty_returns_default():
    """空图谱 -> 默认 transform, 不崩。"""
    t = fit_transform([], 800, 600, 1200, 700)
    assert t == {"x": 0, "y": 0, "k": 1}


# ----- 测试: focusOnNode 公式 -----------------------------------

def focus_transform(node_x, node_y, target_k, viewbox_w, viewbox_h):
    """把节点 (node_x, node_y) 居中, 缩放到 target_k。"""
    return {
        "x": viewbox_w / 2 - node_x * target_k,
        "y": viewbox_h / 2 - node_y * target_k,
        "k": target_k,
    }


def test_focus_centers_target_node():
    """focus 之后, 目标节点在屏幕中心。"""
    t = focus_transform(450, 320, 1.5, 1200, 700)
    sx, sy = screen_pos(t, 450, 320)
    # 屏幕中心 = (viewbox_w/2, viewbox_h/2) = (600, 350)
    assert abs(sx - 600) < 1e-6
    assert abs(sy - 350) < 1e-6


# ----- 测试: kindFilter 只保留选中类型 ----------------------------

def filter_nodes_by_kind(nodes, kind_filter):
    """kind_filter 空集 -> 全保留; 否则只保留选中的 kind。"""
    if not kind_filter:
        return list(nodes)
    return [n for n in nodes if n["kind"] in kind_filter]


def test_kind_filter_empty_keeps_all():
    """空过滤集 -> 全保留。"""
    nodes = [
        {"id": 1, "kind": "study_character"},
        {"id": 2, "kind": "event"},
        {"id": 3, "kind": "behavior"},
    ]
    assert len(filter_nodes_by_kind(nodes, set())) == 3


def test_kind_filter_keeps_only_selected():
    """选中 character + event -> 只保留这两种。"""
    nodes = [
        {"id": 1, "kind": "study_character"},
        {"id": 2, "kind": "event"},
        {"id": 3, "kind": "behavior"},
        {"id": 4, "kind": "study_character"},
    ]
    out = filter_nodes_by_kind(nodes, {"study_character", "event"})
    assert len(out) == 3
    assert all(n["kind"] != "behavior" for n in out)


# ----- 测试: dimmedIds 选中态计算 --------------------------------

def compute_dimmed_nodes(selected_node_id, nodes, edges):
    """选中一个节点后, 跟它不直接相连的节点应该被 dim。

    跟 GraphPage.tsx::dimmedIds 逻辑一致。
    """
    if selected_node_id is None:
        return set()
    connected = {selected_node_id}
    for e in edges:
        if e["source_node_id"] == selected_node_id:
            connected.add(e["target_node_id"])
        if e["target_node_id"] == selected_node_id:
            connected.add(e["source_node_id"])
    return {n["id"] for n in nodes if n["id"] not in connected}


def test_dimmed_keeps_self_and_neighbors():
    """选中节点 N 后, N 自己 + 所有跟 N 有边相连的节点都不 dim。"""
    nodes = [{"id": i} for i in range(1, 6)]  # 1..5
    edges = [
        {"source_node_id": 1, "target_node_id": 2},
        {"source_node_id": 1, "target_node_id": 3},
        {"source_node_id": 4, "target_node_id": 5},
    ]
    dimmed = compute_dimmed_nodes(1, nodes, edges)
    # 1, 2, 3 不 dim, 4 和 5 dim
    assert 1 not in dimmed
    assert 2 not in dimmed
    assert 3 not in dimmed
    assert 4 in dimmed
    assert 5 in dimmed


def test_dimmed_no_selection_returns_empty():
    """没选中时, dimmed 集为空。"""
    nodes = [{"id": i} for i in range(1, 4)]
    edges = [{"source_node_id": 1, "target_node_id": 2}]
    assert compute_dimmed_nodes(None, nodes, edges) == set()


# ----- 测试: search 命中 ----------------------------------------

def search_hits(nodes, query):
    """按 name 大小写不敏感模糊匹配。"""
    q = query.strip().lower()
    if not q:
        return set()
    return {n["id"] for n in nodes if q in n["name"].lower()}


def test_search_case_insensitive():
    nodes = [
        {"id": 1, "name": "方源"},
        {"id": 2, "name": "方寒"},
        {"id": 3, "name": "古书"},
    ]
    # 小写 "fangyuan" 也能匹配 "方源" (只要 query 跟 name 都有 lower 后相等)
    # 实际上中文没有大小写, 所以应该返回包含 query 的所有 name
    hits = search_hits(nodes, "方")
    assert hits == {1, 2}


def test_search_empty_query_returns_empty():
    nodes = [{"id": 1, "name": "方源"}]
    assert search_hits(nodes, "") == set()
    assert search_hits(nodes, "   ") == set()


def test_search_whitespace_trimmed():
    nodes = [{"id": 1, "name": "方源"}]
    assert search_hits(nodes, "  方  ") == {1}


if __name__ == "__main__":
    tests = [
        test_zoom_keeps_cursor_point_stationary,
        test_zoom_zoom_out_keeps_point_stationary,
        test_zoom_clamped_at_k_min,
        test_zoom_clamped_at_k_max,
        test_fit_all_centers_graph,
        test_fit_all_zooms_to_fit,
        test_fit_all_empty_returns_default,
        test_focus_centers_target_node,
        test_kind_filter_empty_keeps_all,
        test_kind_filter_keeps_only_selected,
        test_dimmed_keeps_self_and_neighbors,
        test_dimmed_no_selection_returns_empty,
        test_search_case_insensitive,
        test_search_empty_query_returns_empty,
        test_search_whitespace_trimmed,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)
