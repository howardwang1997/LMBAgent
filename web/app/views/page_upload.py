"""Upload page: single/multi file upload, directory scan, smart exploration."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
import pandas as pd

from lmbagent.data.loader import load_auto, detect_format
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.data.store import DataStore
from lmbagent.data.catalog import scan_directory, batch_import


def render_upload_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    store = DataStore()

    tab_single, tab_multi, tab_scan, tab_explore, tab_llm = st.tabs([
        "上传文件", "批量上传", "目录扫描", "智能探索", "AI 智能加载",
    ])

    # --- Tab 1: Single file upload ---
    with tab_single:
        st.subheader("上传数据文件")
        st.markdown("支持 PEC CSV, Arbin CSV, Neware xlsx/npy, 通用 CSV")

        uploaded = st.file_uploader(
            "选择数据文件",
            type=["csv", "xlsx", "npy", "txt"],
            key="single_upload",
        )

        if uploaded:
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**文件名:** {uploaded.name}")
                st.write(f"**大小:** {uploaded.size / 1024:.1f} KB")
            with col2:
                data_id = st.text_input("数据集 ID (可选)", value="",
                                        placeholder=uploaded.name.split(".")[0])

            if st.button("加载并分析", type="primary"):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / uploaded.name
                    tmp_path.write_bytes(uploaded.getvalue())
                    loaded = False
                    
                    # Try standard loading first
                    try:
                        ds = load_auto(str(tmp_path), data_id=data_id or None)
                        if ds.num_data_points > 0:
                            ds = add_cycle_summary(ds)
                            store.put(ds)
                            st.session_state.active_dataset_id = ds.data_id
                            st.success(f"加载成功! ID: `{ds.data_id}`, {ds.num_data_points} points, {ds.num_cycles} cycles")
                            if ds.experiment_design:
                                st.info(f"已自动加载设计元数据: {ds.experiment_design.cell_id}")
                            loaded = True
                        else:
                            st.warning("标准加载成功但数据为空，尝试 AI 智能加载...")
                    except Exception as e:
                        st.warning(f"标准加载失败: {e}，尝试 AI 智能加载...")
                    
                    # Fallback to LLM smart loading
                    if not loaded:
                        try:
                            from lmbagent.data.llm_loader import llm_smart_load
                            with st.spinner("AI 正在分析文件并加载..."):
                                ds = llm_smart_load(str(tmp_path), data_id=data_id or None)
                            if ds.num_data_points > 0:
                                ds = add_cycle_summary(ds)
                                store.put(ds)
                                st.session_state.active_dataset_id = ds.data_id
                                st.success(f"AI 智能加载成功! ID: `{ds.data_id}`, {ds.num_data_points} points, {ds.num_cycles} cycles")
                            else:
                                st.error("AI 加载后数据仍为空，请检查文件格式。")
                        except Exception as e2:
                            st.error(f"AI 智能加载也失败: {e2}")

    # --- Tab 2: Multi-file upload ---
    with tab_multi:
        st.subheader("批量上传")
        st.markdown("一次上传多个文件，自动检测格式并批量导入")

        files = st.file_uploader(
            "选择多个数据文件",
            type=["csv", "xlsx", "npy", "txt"],
            accept_multiple_files=True,
            key="multi_upload",
        )

        if files:
            st.write(f"已选择 {len(files)} 个文件:")
            for f in files:
                fmt = "未知"
                try:
                    with tempfile.NamedTemporaryFile(suffix=f.name, delete=False) as tmp:
                        tmp.write(f.getvalue())
                        fmt = detect_format(tmp.name)
                except Exception:
                    pass
                st.markdown(f"  - `{f.name}` ({fmt}, {f.size / 1024:.1f} KB)")

            if st.button("批量导入", type="primary"):
                progress = st.progress(0)
                success_count = 0
                fail_count = 0
                for i, f in enumerate(files):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmp_path = Path(tmpdir) / f.name
                        tmp_path.write_bytes(f.getvalue())
                        try:
                            ds = load_auto(str(tmp_path))
                            ds = add_cycle_summary(ds)
                            store.put(ds)
                            success_count += 1
                        except Exception as e:
                            fail_count += 1
                            st.warning(f"失败: {f.name} — {e}")
                    progress.progress((i + 1) / len(files))

                st.success(f"导入完成: {success_count} 成功, {fail_count} 失败")
                st.metric("数据库中实验总数", len(store.list_ids()))

    # --- Tab 3: Directory scan ---
    with tab_scan:
        st.subheader("目录扫描导入")
        st.markdown("扫描文件服务器上的目录，自动发现并批量导入实验数据")

        scan_dir = st.text_input(
            "输入目录路径",
            placeholder="/path/to/experiment/data",
            key="scan_dir",
        )

        if scan_dir and Path(scan_dir).is_dir():
            if st.button("扫描目录"):
                with st.spinner("正在扫描..."):
                    candidates = scan_directory(scan_dir)
                if not candidates:
                    st.warning("未发现数据文件。")
                else:
                    st.write(f"发现 {len(candidates)} 个数据文件:")
                    for c in candidates:
                        design_info = " ✓ 有设计元数据" if c.design_path else ""
                        st.markdown(f"  - `{c.path.name}` ({c.format}){design_info}")

                    if st.button(f"导入全部 {len(candidates)} 个文件"):
                        progress = st.progress(0)
                        with st.spinner("批量导入中..."):
                            for i, c in enumerate(candidates):
                                try:
                                    ds = load_auto(str(c.path))
                                    if c.design and ds.experiment_design is None:
                                        ds.experiment_design = c.design
                                    ds = add_cycle_summary(ds)
                                    store.put(ds)
                                    c.imported = True
                                    c.data_id = ds.data_id
                                except Exception:
                                    pass
                                progress.progress((i + 1) / len(candidates))

                        imported = sum(1 for c in candidates if c.imported)
                        st.success(f"导入完成: {imported}/{len(candidates)} 成功")
                        st.metric("数据库中实验总数", len(store.list_ids()))
        elif scan_dir:
            st.error(f"目录不存在: {scan_dir}")

    # --- Tab 4: Smart exploration ---
    with tab_explore:
        st.subheader("智能探索加载")
        st.markdown("""
        上传格式未知或混乱的数据文件，系统会自动探索文件结构并尝试结构化。
        适用于非标准格式、混合编码、不规则表头等场景。
        """)

        explore_file = st.file_uploader(
            "上传数据文件",
            type=["csv", "txt", "tsv", "xlsx", "xls"],
            key="explore_upload",
        )

        if explore_file:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir) / explore_file.name
                tmp_path.write_bytes(explore_file.getvalue())

                st.write(f"**文件:** {explore_file.name}")

                with st.expander("文件探索结果", expanded=True):
                    _explore_file(tmp_path)

                data_id = st.text_input("数据集 ID", value="", key="explore_id",
                                        placeholder=explore_file.name.split(".")[0])

                if st.button("尝试加载", key="explore_load"):
                    try:
                        ds = load_auto(str(tmp_path), data_id=data_id or None)
                        ds = add_cycle_summary(ds)
                        store.put(ds)
                        st.success(f"加载成功! ID: `{ds.data_id}`, {ds.num_data_points} points, {ds.num_cycles} cycles")
                        st.session_state.active_dataset_id = ds.data_id
                    except Exception as e:
                        st.error(f"自动加载失败: {e}")
                        st.info("可以尝试指定格式:")
                        fmt = st.selectbox("选择格式", ["generic_csv", "pec", "arbin", "neware_xlsx"],
                                           key="explore_fmt")
                        if st.button("强制加载"):
                            try:
                                ds = load_auto(str(tmp_path), data_id=data_id or None, format=fmt)
                                ds = add_cycle_summary(ds)
                                store.put(ds)
                                st.success(f"加载成功! ID: `{ds.data_id}`")
                            except Exception as e2:
                                st.error(f"加载失败: {e2}")

    # --- Tab 5: LLM smart loading ---
    with tab_llm:
        st.subheader("AI 智能加载")
        st.markdown("""
        上传数据文件，AI 会自动分析文件结构，识别数据格式和列含义，智能选择最佳加载方式。
        适用于非标准格式、混合编码、不确定列映射等场景。
        """)

        llm_file = st.file_uploader(
            "上传数据文件",
            type=["csv", "txt", "tsv", "xlsx", "xls", "npy"],
            key="llm_upload",
        )

        if llm_file:
            st.write(f"**文件:** {llm_file.name} ({llm_file.size / 1024:.1f} KB)")
            llm_data_id = st.text_input("数据集 ID (可选)", value="",
                                        placeholder=llm_file.name.split(".")[0],
                                        key="llm_data_id")

            if st.button("AI 分析并加载", type="primary", key="llm_load_btn"):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / llm_file.name
                    tmp_path.write_bytes(llm_file.getvalue())

                    with st.spinner("AI 正在分析文件结构..."):
                        from lmbagent.data.llm_loader import llm_analyze_file, llm_smart_load
                        analysis = llm_analyze_file(str(tmp_path))

                    if analysis.get("llm_used"):
                        st.success("AI 分析完成")
                    else:
                        st.warning("AI 分析未成功，使用默认方式")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**识别格式:** `{analysis.get('format', 'unknown')}`")
                        st.markdown(f"**分隔符:** `{analysis.get('separator', ',')}`")
                        st.markdown(f"**跳过行数:** {analysis.get('skip_rows', 0)}")
                        st.markdown(f"**编码:** {analysis.get('encoding', 'utf-8')}")
                    with col2:
                        if analysis.get("column_map"):
                            st.markdown("**列映射:**")
                            for std, actual in analysis["column_map"].items():
                                if actual:
                                    st.markdown(f"  `{std}` ← `{actual}`")

                    if analysis.get("reasoning"):
                        with st.expander("AI 分析说明"):
                            st.markdown(analysis["reasoning"])

                    with st.spinner("正在加载数据..."):
                        try:
                            ds = llm_smart_load(str(tmp_path), data_id=llm_data_id or None)
                            ds = add_cycle_summary(ds)
                            store.put(ds)
                            st.session_state.active_dataset_id = ds.data_id
                            st.success(
                                f"加载成功! ID: `{ds.data_id}`, "
                                f"{ds.num_data_points} points, {ds.num_cycles} cycles"
                            )
                        except Exception as e:
                            st.error(f"加载失败: {e}")
                            st.info("可以尝试在\"上传文件\"标签页手动指定格式。")


def _explore_file(path: Path):
    """Explore a file's structure and display findings."""
    suffix = path.suffix.lower()
    st.markdown(f"**扩展名:** `{suffix}`")
    st.markdown(f"**大小:** {path.stat().st_size / 1024:.1f} KB")

    if suffix in (".csv", ".txt", ".tsv"):
        try:
            with open(path, "rb") as f:
                raw = f.read(4096)

            encodings = ["utf-8", "gbk", "gb2312", "latin-1", "utf-16"]
            detected_enc = None
            for enc in encodings:
                try:
                    raw.decode(enc)
                    detected_enc = enc
                    break
                except (UnicodeDecodeError, ValueError):
                    continue
            st.markdown(f"**编码:** {detected_enc or 'unknown'}")

            if detected_enc:
                with open(path, "r", encoding=detected_enc, errors="replace") as f:
                    lines = [f.readline().rstrip() for _ in range(10)]
                st.markdown("**前10行:**")
                for i, line in enumerate(lines):
                    st.code(f"L{i+1}: {line[:200]}", language=None)

            seps = [",", "\t", ";", "|"]
            best_sep = ","
            best_cols = 0
            for sep in seps:
                try:
                    df = pd.read_csv(path, sep=sep, nrows=5, encoding=detected_enc or "utf-8",
                                     on_bad_lines="skip")
                    if len(df.columns) > best_cols:
                        best_cols = len(df.columns)
                        best_sep = sep
                except Exception:
                    pass

            st.markdown(f"**分隔符:** `{repr(best_sep)}` ({best_cols} 列)")

            try:
                df = pd.read_csv(path, sep=best_sep, nrows=5, encoding=detected_enc or "utf-8",
                                 on_bad_lines="skip")
                st.markdown(f"**列名:** {list(df.columns)}")
                st.dataframe(df.head(), width="stretch", hide_index=True)

                battery_keywords = ["voltage", "current", "capacity", "cycle", "time",
                                    "voltage(v)", "current(a)", "capacity(ah)",
                                    "电压", "电流", "容量", "循环", "时间"]
                found = [c for c in df.columns if any(kw in str(c).lower() for kw in battery_keywords)]
                if found:
                    st.success(f"检测到电池数据列: {found}")
                else:
                    st.warning("未检测到标准电池数据列名")
            except Exception as e:
                st.warning(f"解析失败: {e}")

        except Exception as e:
            st.error(f"无法读取文件: {e}")

    elif suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), data_only=True)
            st.markdown(f"**Sheet列表:** {wb.sheetnames}")
            for sn in wb.sheetnames[:3]:
                ws = wb[sn]
                rows = list(ws.iter_rows(values_only=True, max_row=6))
                if rows:
                    st.markdown(f"**Sheet '{sn}' 前6行:**")
                    for i, row in enumerate(rows):
                        st.code(f"L{i+1}: {[str(v) if v is not None else '' for v in row][:10]}",
                                language=None)
            wb.close()
        except Exception as e:
            st.error(f"Excel读取失败: {e}")
