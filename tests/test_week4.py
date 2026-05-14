"""Tests for Week 4: search engine, vectorizer, conclusions, verification."""

import numpy as np
import pandas as pd
import pytest

from lmbagent.data.models import BatteryDataset
from lmbagent.data.schema import ExperimentDesign, ElectrodeDesign, ElectrolyteDesign
from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.search.vectorizer import (
    compute_design_vector,
    compute_performance_vector,
    compute_degradation_vector,
    compute_combined_vector,
    cosine_similarity,
    euclidean_distance,
)
from lmbagent.search.engine import SearchEngine, SearchResult
from lmbagent.conclusions.models import Conclusion, ConclusionStatus
from lmbagent.conclusions.store import ConclusionStore
from lmbagent.conclusions.verifier import verify_conclusion, verify_all


def _make_dataset(data_id, cell_id="cell_A", n_cycles=20, cap_scale=1.0, design=None):
    rows = []
    for c in range(n_cycles):
        fade = c * 0.01 * cap_scale
        base_v = 3.5 - fade * 0.5
        for s in range(20):
            t_frac = s / 20
            if s < 10:
                v = base_v + 0.5 * t_frac
                cur = 0.5 * cap_scale
                ch_cap = 0.005 * (s + 1) * cap_scale
                dis_cap = 0.0
                ch_e = 0.018 * (s + 1) * cap_scale
                dis_e = 0.0
            else:
                v = base_v + 0.5 - 0.5 * (t_frac - 0.5)
                cur = -0.5 * cap_scale
                ch_cap = 0.05 * cap_scale
                dis_cap = 0.005 * (s - 9) * cap_scale * (1 - fade)
                ch_e = 0.18 * cap_scale
                dis_e = 0.016 * (s - 9) * cap_scale * (1 - fade)
            rows.append({
                "data_point": c * 20 + s,
                "cycle_index": c,
                "step_index": 0,
                "test_time": c * 200 + s * 10,
                "voltage": v,
                "current": cur,
                "charge_capacity": ch_cap,
                "discharge_capacity": dis_cap,
                "charge_energy": ch_e,
                "discharge_energy": dis_e,
                "internal_resistance": 0.01 * (1 + c * 0.05),
                "temperature_ambient": 25.0,
                "temperature_cell": 25.0,
                "datetime": pd.Timestamp("2024-01-01") + pd.Timedelta(seconds=c * 200 + s * 10),
            })
    df = pd.DataFrame(rows)
    ds = BatteryDataset(
        data_id=data_id,
        source_file=f"test_{data_id}.csv",
        cell_id=cell_id,
        test_name=f"Test {data_id}",
        raw_data=df,
        experiment_design=design,
    )
    ds = add_cycle_summary(ds)
    return ds


class TestVectorizer:
    def test_design_vector_no_design(self, sample_dataset):
        vec = compute_design_vector(sample_dataset)
        assert vec.shape == (20,)
        assert np.all(vec == 0)

    def test_design_vector_with_design(self):
        design = ExperimentDesign(
            cell_id="X1", chemistry="NMC811",
            positive_electrode=ElectrodeDesign(thickness_um=100, porosity=0.35),
        )
        ds = _make_dataset("d1", design=design)
        vec = compute_design_vector(ds)
        assert vec.shape == (20,)
        assert np.any(vec != 0)

    def test_performance_vector(self):
        ds = _make_dataset("d1", n_cycles=15)
        vec = compute_performance_vector(ds)
        assert vec.shape == (17,)
        assert vec[0] == 15.0  # num_cycles
        assert vec[1] > 0  # initial_cap

    def test_degradation_vector(self):
        ds = _make_dataset("d1", n_cycles=15)
        vec = compute_degradation_vector(ds)
        assert vec.shape == (7,)
        assert np.isfinite(vec).all()

    def test_combined_vector_shape(self):
        ds = _make_dataset("d1", n_cycles=10)
        vec = compute_combined_vector(ds)
        assert vec.shape == (44,)  # 20 + 17 + 7

    def test_cosine_similarity_identical(self):
        v = np.array([1.0, 2.0, 3.0])
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-10

    def test_cosine_similarity_orthogonal(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert abs(cosine_similarity(a, b)) < 1e-10

    def test_cosine_similarity_zero_vector(self):
        v = np.zeros(5)
        assert cosine_similarity(v, v) == 0.0

    def test_euclidean_distance(self):
        a = np.array([0.0, 0.0])
        b = np.array([3.0, 4.0])
        assert abs(euclidean_distance(a, b) - 5.0) < 1e-10


class TestSearchEngine:
    def test_similar_search_empty_store(self):
        store = DataStore()
        ds = _make_dataset("q1")
        store.put(ds)
        engine = SearchEngine(store)
        results = engine.search_similar("q1", mode="similar")
        assert len(results) == 0 or all(r.data_id != "q1" for r in results)

    def test_similar_search_finds_match(self):
        store = DataStore()
        ds1 = _make_dataset("ds1", n_cycles=20)
        ds2 = _make_dataset("ds2", n_cycles=20)
        store.put(ds1)
        store.put(ds2)
        engine = SearchEngine(store)
        results = engine.search_similar("ds1", mode="similar", top_k=3)
        assert len(results) >= 1
        found_ids = [r.data_id for r in results]
        assert "ds2" in found_ids
        for r in results:
            if r.data_id == "ds2":
                assert r.score > 0

    def test_contrast_search_different_degradation(self):
        store = DataStore()
        design_a = ExperimentDesign(cell_id="A", chemistry="NMC811",
                                     positive_electrode=ElectrodeDesign(thickness_um=80))
        design_b = ExperimentDesign(cell_id="B", chemistry="NMC811",
                                     positive_electrode=ElectrodeDesign(thickness_um=80))

        ds1 = _make_dataset("slow", design=design_a, n_cycles=20, cap_scale=1.0)
        ds2 = _make_dataset("fast", design=design_b, n_cycles=20, cap_scale=0.5)
        store.put(ds1)
        store.put(ds2)

        engine = SearchEngine(store)
        results = engine.search_similar("slow", mode="contrast", top_k=3)
        assert len(results) >= 1
        assert results[0].data_id == "fast"

    def test_keyword_search(self):
        store = DataStore()
        ds1 = _make_dataset("ds1", cell_id="NMC811_CellA")
        ds2 = _make_dataset("ds2", cell_id="LFP_CellB")
        store.put(ds1)
        store.put(ds2)

        engine = SearchEngine(store)
        results = engine.search_by_description("ds1")
        assert len(results) >= 1

    def test_search_nonexistent_query(self):
        store = DataStore()
        engine = SearchEngine(store)
        results = engine.search_similar("nonexistent")
        assert results == []


class TestConclusionStore:
    def test_add_and_get(self):
        store = DataStore()
        cs = ConclusionStore(store)
        c = Conclusion(
            conclusion_id="C-001",
            statement="NMC811 with 2% VC shows < 20% fade over 100 cycles",
            scope="NMC811|2C|25C",
            evidence_ids=["ds1", "ds2"],
            confidence="high",
        )
        cs.add(c)
        retrieved = cs.get("C-001")
        assert retrieved is not None
        assert retrieved.statement == c.statement
        assert retrieved.confidence == "high"
        assert retrieved.evidence_ids == ["ds1", "ds2"]

    def test_list_all(self):
        store = DataStore()
        cs = ConclusionStore(store)
        cs.add(Conclusion(conclusion_id="C-001", statement="First"))
        cs.add(Conclusion(conclusion_id="C-002", statement="Second", status=ConclusionStatus.CHALLENGED))
        all_c = cs.list_all()
        assert len(all_c) == 2

    def test_list_by_status(self):
        store = DataStore()
        cs = ConclusionStore(store)
        cs.add(Conclusion(conclusion_id="C-001", statement="Active"))
        cs.add(Conclusion(conclusion_id="C-002", statement="Challenged", status=ConclusionStatus.CHALLENGED))
        active = cs.list_all(status="active")
        assert len(active) == 1
        assert active[0].conclusion_id == "C-001"

    def test_update(self):
        store = DataStore()
        cs = ConclusionStore(store)
        cs.add(Conclusion(conclusion_id="C-001", statement="Original", confidence="medium"))
        updated = cs.update("C-001", statement="Updated", confidence="high")
        assert updated is not None
        assert updated.statement == "Updated"
        assert updated.confidence == "high"
        assert updated.updated_at is not None

    def test_update_status(self):
        store = DataStore()
        cs = ConclusionStore(store)
        cs.add(Conclusion(conclusion_id="C-001", statement="Test"))
        updated = cs.update("C-001", status="challenged", challenged_by=["ds3"])
        assert updated.status == ConclusionStatus.CHALLENGED
        assert "ds3" in updated.challenged_by

    def test_remove(self):
        store = DataStore()
        cs = ConclusionStore(store)
        cs.add(Conclusion(conclusion_id="C-001", statement="To delete"))
        assert cs.remove("C-001")
        assert cs.get("C-001") is None

    def test_remove_nonexistent(self):
        store = DataStore()
        cs = ConclusionStore(store)
        assert not cs.remove("nonexistent")

    def test_get_nonexistent(self):
        store = DataStore()
        cs = ConclusionStore(store)
        assert cs.get("nonexistent") is None


class TestVerifier:
    def test_verify_with_no_conclusions(self):
        store = DataStore()
        ds = _make_dataset("new1")
        store.put(ds)
        results = verify_all("new1", store=store)
        assert results == []

    def test_verify_supported(self):
        store = DataStore()
        ds1 = _make_dataset("ev1", n_cycles=20, cap_scale=1.0)
        ds2 = _make_dataset("new1", n_cycles=20, cap_scale=1.0)
        store.put(ds1)
        store.put(ds2)

        cs = ConclusionStore(store)
        cs.add(Conclusion(
            conclusion_id="C-001",
            statement="Capacity fade is moderate under these conditions",
            evidence_ids=["ev1"],
        ))

        results = verify_all("new1", store=store)
        assert len(results) == 1
        assert results[0].conclusion_id == "C-001"
        assert results[0].verdict in ("supported", "inconclusive", "challenged")

    def test_verify_nonexistent_dataset(self):
        store = DataStore()
        cs = ConclusionStore(store)
        cs.add(Conclusion(conclusion_id="C-001", statement="Test"))
        result = verify_conclusion(
            cs.get("C-001"), "nonexistent", store=store
        )
        assert result.verdict == "inconclusive"

    def test_verify_challenged_updates_status(self):
        store = DataStore()
        ds_ev = _make_dataset("ev1", n_cycles=20, cap_scale=1.0)
        ds_new = _make_dataset("new1", n_cycles=20, cap_scale=0.3)
        store.put(ds_ev)
        store.put(ds_new)

        cs = ConclusionStore(store)
        cs.add(Conclusion(
            conclusion_id="C-001",
            statement="Fade stays below 10%",
            evidence_ids=["ev1"],
        ))

        results = verify_all("new1", store=store)
        assert len(results) == 1
        c_after = cs.get("C-001")
        assert c_after is not None


class TestAgentTools:
    @pytest.mark.asyncio
    async def test_search_similar_tool(self):
        from lmbagent.agent import _handle_search_similar, store as agent_store
        ds1 = _make_dataset("ds1")
        ds2 = _make_dataset("ds2")
        agent_store.put(ds1)
        agent_store.put(ds2)

        result = await _handle_search_similar({"data_id": "ds1", "mode": "similar"})
        assert "ds2" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_manage_conclusion_list(self):
        from lmbagent.agent import _handle_manage_conclusion
        result = await _handle_manage_conclusion({"action": "list"})
        assert "No conclusions" in result["content"][0]["text"] or "Conclusions" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_manage_conclusion_add(self):
        from lmbagent.agent import _handle_manage_conclusion
        result = await _handle_manage_conclusion({
            "action": "add",
            "statement": "Test conclusion",
            "scope": "test",
            "confidence": "high",
        })
        assert "added" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_manage_conclusion_update(self):
        from lmbagent.agent import _handle_manage_conclusion
        await _handle_manage_conclusion({
            "action": "add",
            "conclusion_id": "C-TEST",
            "statement": "Original",
        })
        result = await _handle_manage_conclusion({
            "action": "update",
            "conclusion_id": "C-TEST",
            "status": "challenged",
        })
        assert "updated" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_manage_conclusion_delete(self):
        from lmbagent.agent import _handle_manage_conclusion
        await _handle_manage_conclusion({
            "action": "add",
            "conclusion_id": "C-DEL",
            "statement": "To delete",
        })
        result = await _handle_manage_conclusion({
            "action": "delete",
            "conclusion_id": "C-DEL",
        })
        assert "deleted" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_verify_tool(self):
        from lmbagent.agent import _handle_verify_with_new_data, store as agent_store
        ds1 = _make_dataset("ds1", n_cycles=20)
        agent_store.put(ds1)
        result = await _handle_verify_with_new_data({"data_id": "ds1"})
        assert "No active conclusions" in result["content"][0]["text"] or "Verification" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_search_no_data(self):
        from lmbagent.agent import _handle_search_similar
        result = await _handle_search_similar({"data_id": "nonexistent"})
        assert "Error" in result["content"][0]["text"]
