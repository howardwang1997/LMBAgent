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

    with tab_single:
        _render_single_upload(store)

    with tab_multi:
        _render_batch_upload(store)

    with tab_scan:
        _render_directory_scan(store)

    with tab_explore:
        _render_smart_explore(store)

    with tab_llm:
        _render_ai_load(store)


def _render_single_upload(store: DataStore):
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

                if not loaded:
                    try:
                        from lmbagent.data.llm_loader import llm_analyze_file, llm_smart_load
                        with st.spinner("AI 正在分析文件并加载..."):
                            analysis = llm_analyze_file(str(tmp_path))
                            ds = llm_smart_load(str(tmp_path), data_id=data_id or None, analysis=analysis)
                        if ds and ds.num_data_points > 0:
                            ds = add_cycle_summary(ds)
                            store.put(ds)
                            st.session_state.active_dataset_id = ds.data_id
                            st.success(f"AI 智能加载成功! ID: `{ds.data_id}`, {ds.num_data_points} points, {ds.num_cycles} cycles")
                        else:
                            st.error("AI 加载后数据仍为空，请检查文件格式。")
                    except Exception as e2:
                        st.error(f"AI 智能加载也失败: {e2}")


def _render_batch_upload(store: DataStore):
    st.subheader("批量上传")
    st.markdown("一次上传多个文件，自动检测格式并批量导入。标准加载失败时自动 AI 智能加载。")

    use_ai = st.checkbox("对失败文件启用 AI 智能加载", value=True, key="batch_use_ai")

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
            status_container = st.container()
            success_count = 0
            ai_count = 0
            fail_count = 0
            results = []

            for i, f in enumerate(files):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / f.name
                    tmp_path.write_bytes(f.getvalue())
                    status = "⏳"
                    loaded = False

                    try:
                        ds = load_auto(str(tmp_path))
                        if ds.num_data_points > 0:
                            ds = add_cycle_summary(ds)
                            store.put(ds)
                            success_count += 1
                            status = "✅"
                            loaded = True
                    except Exception:
                        pass

                    if not loaded and use_ai:
                        try:
                            from lmbagent.data.llm_loader import llm_analyze_file, llm_smart_load
                            with st.spinner(f"AI 加载: {f.name}..."):
                                analysis = llm_analyze_file(str(tmp_path))
                                ds = llm_smart_load(str(tmp_path), analysis=analysis)
                            if ds and ds.num_data_points > 0:
                                ds = add_cycle_summary(ds)
                                store.put(ds)
                                ai_count += 1
                                status = "🤖"
                                loaded = True
                        except Exception:
                            pass

                    if not loaded:
                        fail_count += 1
                        status = "❌"

                    results.append({"file": f.name, "status": status, "loaded": loaded})

                progress.progress((i + 1) / len(files))

            with status_container:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("总计", len(files))
                c2.metric("✅ 标准加载", success_count)
                c3.metric("🤖 AI 加载", ai_count)
                c4.metric("❌ 失败", fail_count)

                with st.expander("详细结果"):
                    for r in results:
                        st.markdown(f"{r['status']} `{r['file']}`")

            st.metric("数据库中实验总数", len(store.list_ids()))


def _render_directory_scan(store: DataStore):
    st.subheader("目录扫描与 AI 智能探索")
    st.markdown("""
    扫描文件服务器上的目录，自动发现并批量导入实验数据。
    支持 AI 智能分析目录结构和命名模式。
    """)

    scan_dir = st.text_input(
        "输入目录路径",
        placeholder="/path/to/experiment/data",
        key="scan_dir",
    )

    use_ai = st.checkbox("对加载失败文件启用 AI 智能加载", value=True, key="scan_use_ai")

    if scan_dir and Path(scan_dir).is_dir():
        col_scan, col_ai = st.columns(2)
        with col_scan:
            scan_btn = st.button("扫描目录", key="scan_btn")
        with col_ai:
            ai_scan_btn = st.button("AI 智能探索目录", type="primary", key="ai_scan_btn")

        if scan_btn:
            with st.spinner("正在扫描..."):
                candidates = scan_directory(scan_dir)
            if not candidates:
                st.warning("未发现数据文件。")
            else:
                st.session_state.scan_candidates = candidates
                _display_scan_results(candidates)

        if ai_scan_btn:
            with st.spinner("AI 正在分析目录结构..."):
                try:
                    from lmbagent.data.catalog import smart_scan_directory
                    result = smart_scan_directory(scan_dir)
                except Exception as e:
                    st.error(f"AI 分析失败: {e}")
                    result = None

            if result:
                st.session_state.ai_scan_result = result

                if result.get("summary"):
                    st.info(f"AI 分析: {result['summary']}")

                if result.get("patterns"):
                    st.subheader("识别的模式")
                    for p in result["patterns"]:
                        st.markdown(f"- {p}")

                if result.get("groups"):
                    st.subheader("文件分组")
                    for group_name, files in result["groups"].items():
                        with st.expander(f"{group_name} ({len(files)} 文件)"):
                            for f in files:
                                st.markdown(f"  - `{f}`")

                if result.get("candidates"):
                    st.session_state.scan_candidates = result["candidates"]
                    _display_scan_results(result["candidates"])

        if "scan_candidates" in st.session_state and st.session_state.scan_candidates:
            candidates = st.session_state.scan_candidates
            if st.button(f"导入全部 {len(candidates)} 个文件", key="import_all_btn"):
                progress = st.progress(0)
                success_count = 0
                ai_count = 0
                fail_count = 0

                with st.spinner("批量导入中..."):
                    for i, c in enumerate(candidates):
                        loaded = False
                        try:
                            ds = load_auto(str(c.path))
                            if c.design and ds.experiment_design is None:
                                ds.experiment_design = c.design
                            if ds.num_data_points > 0:
                                ds = add_cycle_summary(ds)
                                store.put(ds)
                                c.imported = True
                                c.data_id = ds.data_id
                                success_count += 1
                                loaded = True
                        except Exception:
                            pass

                        if not loaded and use_ai:
                            try:
                                from lmbagent.data.llm_loader import llm_analyze_file, llm_smart_load
                                analysis = llm_analyze_file(str(c.path))
                                ds = llm_smart_load(str(c.path), analysis=analysis)
                                if ds and ds.num_data_points > 0:
                                    if c.design and ds.experiment_design is None:
                                        ds.experiment_design = c.design
                                    ds = add_cycle_summary(ds)
                                    store.put(ds)
                                    c.imported = True
                                    c.data_id = ds.data_id
                                    ai_count += 1
                                    loaded = True
                            except Exception:
                                pass

                        if not loaded:
                            fail_count += 1

                        progress.progress((i + 1) / len(candidates))

                c1, c2, c3 = st.columns(3)
                c1.metric("✅ 标准加载", success_count)
                c2.metric("🤖 AI 加载", ai_count)
                c3.metric("❌ 失败", fail_count)
                st.metric("数据库中实验总数", len(store.list_ids()))

    elif scan_dir:
        st.error(f"目录不存在: {scan_dir}")


def _display_scan_results(candidates):
    st.write(f"发现 {len(candidates)} 个数据文件:")
    formats = {}
    for c in candidates:
        design_info = " ✓ 有设计元数据" if c.design_path else ""
        st.markdown(f"  - `{c.path.name}` ({c.format}){design_info}")
        formats[c.format] = formats.get(c.format, 0) + 1

    if formats:
        st.markdown("**格式统计:** " + ", ".join(f"{k}: {v}" for k, v in formats.items()))


def _render_smart_explore(store: DataStore):
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

            col1, col2 = st.columns(2)
            with col1:
                if st.button("尝试加载", key="explore_load"):
                    try:
                        ds = load_auto(str(tmp_path), data_id=data_id or None)
                        ds = add_cycle_summary(ds)
                        store.put(ds)
                        st.success(f"加载成功! ID: `{ds.data_id}`, {ds.num_data_points} points, {ds.num_cycles} cycles")
                        st.session_state.active_dataset_id = ds.data_id
                    except Exception as e:
                        st.error(f"自动加载失败: {e}")
            with col2:
                if st.button("AI 智能加载", key="explore_ai_load"):
                    try:
                        from lmbagent.data.llm_loader import llm_analyze_file, llm_smart_load
                        with st.spinner("AI 正在分析..."):
                            analysis = llm_analyze_file(str(tmp_path))
                            ds = llm_smart_load(str(tmp_path), data_id=data_id or None, analysis=analysis)
                        if ds and ds.num_data_points > 0:
                            ds = add_cycle_summary(ds)
                            store.put(ds)
                            st.session_state.active_dataset_id = ds.data_id
                            st.success(f"AI 加载成功! ID: `{ds.data_id}`, {ds.num_data_points} points")
                            if analysis.get("reasoning"):
                                st.info(f"AI: {analysis['reasoning']}")
                        else:
                            st.error("AI 加载失败")
                    except Exception as e:
                        st.error(f"AI 加载失败: {e}")


def _render_ai_load(store: DataStore):
    st.subheader("AI 智能加载与校对")
    st.markdown("""
    上传数据文件，AI 自动分析文件结构并加载。加载后可查看数据片段，
    如果有问题可直接用自然语言对话校正。

    **校正示例:** "第一列是循环号，第三列是电压" / "跳过前5行" / "容量需按电流正负拆分"
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

        llm_tmp_dir = Path(tempfile.gettempdir()) / "lmbagent_llm"
        llm_tmp_dir.mkdir(parents=True, exist_ok=True)
        llm_tmp_path = llm_tmp_dir / llm_file.name
        llm_tmp_path.write_bytes(llm_file.getvalue())

        if "llm_messages" not in st.session_state:
            st.session_state.llm_messages = []
        if "llm_analysis" not in st.session_state:
            st.session_state.llm_analysis = None
        if "llm_dataset" not in st.session_state:
            st.session_state.llm_dataset = None
        if "llm_file_key" not in st.session_state:
            st.session_state.llm_file_key = None

        if st.session_state.llm_file_key != llm_file.name:
            st.session_state.llm_messages = []
            st.session_state.llm_analysis = None
            st.session_state.llm_dataset = None
            st.session_state.llm_file_key = llm_file.name

        if st.button("AI 分析并加载", type="primary", key="llm_load_btn"):
            with st.spinner("AI 正在分析文件结构并加载..."):
                from lmbagent.data.llm_loader import llm_analyze_file, llm_smart_load

                analysis = llm_analyze_file(str(llm_tmp_path))

                analysis_lines = []
                analysis_lines.append(f"**识别格式:** `{analysis.get('format', 'unknown')}`")
                analysis_lines.append(f"**分隔符:** `{analysis.get('separator', ',')}`")
                analysis_lines.append(f"**跳过行数:** {analysis.get('skip_rows', 0)}")
                analysis_lines.append(f"**编码:** {analysis.get('encoding', 'utf-8')}")

                if analysis.get("column_map"):
                    analysis_lines.append("**列映射:**")
                    for std, actual in analysis["column_map"].items():
                        if actual:
                            analysis_lines.append(f"  `{std}` ← `{actual}`")

                if analysis.get("reasoning"):
                    analysis_lines.append(f"\n*AI说明: {analysis['reasoning']}*")

                st.session_state.llm_analysis = analysis

                try:
                    ds = llm_smart_load(
                        str(llm_tmp_path),
                        data_id=llm_data_id or None,
                        analysis=analysis,
                    )
                    if ds and ds.num_data_points > 0:
                        st.session_state.llm_dataset = ds
                        col_info = ", ".join(ds.raw_data.columns.tolist())
                        st.session_state.llm_messages.append({
                            "role": "assistant",
                            "content": (
                                f"AI 加载完成!\n\n"
                                + "\n".join(analysis_lines) + "\n\n"
                                f"**数据:** {ds.num_data_points} 行, {ds.num_cycles} 循环\n"
                                f"**列:** {col_info}\n\n"
                                f"请检查下方数据预览，如有问题请直接输入校正指令。"
                            ),
                        })
                    else:
                        st.session_state.llm_messages.append({
                            "role": "assistant",
                            "content": (
                                "AI 分析完成但加载结果为空。\n\n"
                                + "\n".join(analysis_lines) + "\n\n"
                                "请在下方描述文件格式，我会帮你校正加载。"
                            ),
                        })
                except Exception as e:
                    st.session_state.llm_messages.append({
                        "role": "assistant",
                        "content": (
                            f"AI 加载失败: {e}\n\n"
                            + "\n".join(analysis_lines) + "\n\n"
                            "请在下方描述文件格式，我会帮你校正加载。"
                        ),
                    })

        with st.expander("原始文件预览", expanded=False):
            _show_file_preview(llm_tmp_path)

        if st.session_state.llm_dataset is not None:
            ds_preview = st.session_state.llm_dataset
            with st.expander("数据预览", expanded=True):
                c1, c2, c3 = st.columns(3)
                c1.metric("数据行数", f"{ds_preview.num_data_points:,}")
                c2.metric("循环数", ds_preview.num_cycles)
                c3.metric("列数", len(ds_preview.raw_data.columns))
                st.markdown(f"**列名:** `{list(ds_preview.raw_data.columns)}`")
                st.dataframe(
                    ds_preview.raw_data.head(20),
                    hide_index=True,
                    use_container_width=True,
                )
                if ds_preview.num_cycles > 0 and "discharge_capacity" in ds_preview.raw_data.columns:
                    cyc = ds_preview.raw_data.groupby("cycle_index")["discharge_capacity"].max()
                    st.markdown(f"**放电容量范围:** {cyc.min():.4f} ~ {cyc.max():.4f} Ah")

        for msg in st.session_state.llm_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if user_input := st.chat_input("输入校正指令，如: 第一列是循环号，容量需按电流正负拆分..."):
            st.session_state.llm_messages.append({"role": "user", "content": user_input})

            with st.spinner("AI 正在根据你的反馈重新加载..."):
                from lmbagent.data.llm_loader import corrective_load

                ds, analysis = corrective_load(
                    str(llm_tmp_path),
                    user_feedback=user_input,
                    previous_analysis=st.session_state.llm_analysis,
                    data_id=llm_data_id or None,
                )

            st.session_state.llm_analysis = analysis

            if ds is not None and ds.num_data_points > 0:
                st.session_state.llm_dataset = ds
                col_info = ", ".join(ds.raw_data.columns.tolist())
                reply = (
                    f"校正加载成功!\n\n"
                    f"- 识别格式: `{analysis.get('format', 'unknown')}`\n"
                    f"- 数据: {ds.num_data_points} 行, {ds.num_cycles} 循环\n"
                    f"- 列: {col_info}\n"
                )
                if analysis.get("reasoning"):
                    reply += f"- AI说明: {analysis['reasoning']}\n"
                reply += "\n请检查数据预览，如需进一步调整请继续输入。"
                st.session_state.llm_messages.append({"role": "assistant", "content": reply})
            else:
                reason = analysis.get("reasoning", "未知原因")
                st.session_state.llm_messages.append({
                    "role": "assistant",
                    "content": (
                        f"校正后仍未成功加载: {reason}\n\n"
                        "请提供更多格式信息，例如:\n"
                        "- 列名含义\n- 分隔符类型\n- 需要跳过的行数"
                    ),
                })

            st.rerun()

        if st.session_state.llm_dataset is not None:
            st.divider()
            if st.button("确认入库", type="primary", key="llm_save_btn"):
                ds = st.session_state.llm_dataset
                ds = add_cycle_summary(ds)
                store.put(ds)
                st.session_state.active_dataset_id = ds.data_id
                st.success(
                    f"已入库! ID: `{ds.data_id}`, "
                    f"{ds.num_data_points} points, {ds.num_cycles} cycles"
                )
                st.session_state.llm_messages = []
                st.session_state.llm_analysis = None
                st.session_state.llm_dataset = None


def _show_file_preview(path: Path):
    suffix = path.suffix.lower()
    if suffix in (".csv", ".txt", ".tsv"):
        for enc in ["utf-8", "gbk", "latin-1"]:
            try:
                with open(path, "r", encoding=enc, errors="replace") as f:
                    lines = [f.readline().rstrip() for _ in range(10)]
                for i, line in enumerate(lines):
                    st.code(f"L{i+1}: {line[:200]}", language=None)
                break
            except Exception:
                continue
    elif suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), data_only=True)
            st.markdown(f"**Sheets:** {wb.sheetnames}")
            for sn in wb.sheetnames[:3]:
                ws = wb[sn]
                rows = list(ws.iter_rows(values_only=True, max_row=6))
                if rows:
                    st.markdown(f"**Sheet '{sn}'**:")
                    for i, row in enumerate(rows):
                        st.code(
                            f"L{i+1}: {[str(v) if v is not None else '' for v in row][:10]}",
                            language=None,
                        )
            wb.close()
        except Exception as e:
            st.error(f"Excel 读取失败: {e}")
    elif suffix == ".npy":
        st.info("二进制 numpy 文件，无法文本预览")


def _explore_file(path: Path):
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
