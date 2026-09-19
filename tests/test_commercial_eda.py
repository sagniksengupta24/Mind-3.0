"""Tests for Commercial EDA Toolchain Runner, TCL Templates, and Log Parsers."""

import tempfile
from pathlib import Path

import pytest

from mind3.eda import (
    CalibrePhysicalConfig,
    CommercialTCLGenerator,
    InnovusPnRConfig,
    MCMMScenarioConfig,
    PrimeTimeSTAConfig,
    SynthesisTCLConfig,
)
from mind3.sandbox.eda_commercial import (
    FlexLMMonitor,
    GridClusterDispatcher,
    GridJobSpec,
    parse_calibre_drc_summary,
    parse_calibre_lvs_summary,
    parse_innovus_log,
    parse_primetime_log,
)
from mind3.core.verifier import CommercialSignoffVerifier, TapeoutReadinessVerifier
from mind3.sandbox.bwrap import BubblewrapSandbox


def test_synopsys_dc_tcl_generation() -> None:
    """Validate Synopsys Design Compiler / Fusion Compiler TCL generation."""
    cfg = SynthesisTCLConfig(
        top_module="riscv_core",
        verilog_sources=["core.v", "alu.v"],
        target_libraries=["sc9_cln65lp_base_rvt.db"],
        link_libraries=["sc9_cln65lp_base_rvt.db"],
        sdc_path="constraints.sdc",
        compile_ultra=True,
        clock_gating=True,
        retiming=True,
    )
    tcl = CommercialTCLGenerator.generate_synopsys_dc(cfg)
    assert "elaborate riscv_core" in tcl
    assert "compile_ultra -gate_clock -retime" in tcl
    assert "set_clock_gating_style" in tcl
    assert "report_qor" in tcl
    assert "write -format verilog" in tcl


def test_cadence_genus_tcl_generation() -> None:
    """Validate Cadence Genus synthesis TCL generation."""
    cfg = SynthesisTCLConfig(
        top_module="crypto_engine",
        verilog_sources=["crypto.sv"],
        target_libraries=["tsmcN3_hvt.lib"],
        link_libraries=["tsmcN3_hvt.lib"],
        sdc_path="crypto.sdc",
    )
    tcl = CommercialTCLGenerator.generate_cadence_genus(cfg)
    assert "elaborate crypto_engine" in tcl
    assert "syn_generic" in tcl
    assert "syn_map" in tcl
    assert "syn_opt" in tcl
    assert "write_hdl" in tcl


def test_primetime_mcmm_tcl_generation() -> None:
    """Validate Synopsys PrimeTime MCMM STA signoff script generation."""
    scenarios = [
        MCMMScenarioConfig(
            name="func_ss_0p675v_m40c",
            mode="func",
            corner="ssgnp_0p675v_m40c",
            liberty_paths=["pdk/ss_0p675v_m40c.lib"],
            sdc_path="constraints/func.sdc",
            temperature_c=-40.0,
            voltage_v=0.675,
            is_setup=True,
            is_hold=False,
        ),
        MCMMScenarioConfig(
            name="func_ff_0p825v_125c",
            mode="func",
            corner="ffgnp_0p825v_125c",
            liberty_paths=["pdk/ff_0p825v_125c.lib"],
            sdc_path="constraints/func.sdc",
            temperature_c=125.0,
            voltage_v=0.825,
            is_setup=False,
            is_hold=True,
        ),
    ]
    cfg = PrimeTimeSTAConfig(
        top_module="chip_top",
        netlist_path="syn_netlist.v",
        scenarios=scenarios,
        enable_si=True,
        enable_pocv=True,
    )
    tcl = CommercialTCLGenerator.generate_primetime_mcmm(cfg)
    assert "create_scenario func_ss_0p675v_m40c" in tcl
    assert "create_scenario func_ff_0p825v_125c" in tcl
    assert "si_enable_analysis" in tcl
    assert "MIND3_PT_COMPLETE" in tcl


def test_innovus_pnr_tcl_generation() -> None:
    """Validate Cadence Innovus PnR script generation."""
    cfg = InnovusPnRConfig(
        top_module="mac_unit",
        netlist_path="mac_netlist.v",
        lef_paths=["tsmcN3_tech.lef", "sc_macro.lef"],
        liberty_paths=["sc.lib"],
        sdc_path="mac.sdc",
        core_utilization=0.70,
    )
    tcl = CommercialTCLGenerator.generate_cadence_innovus_pnr(cfg)
    assert "floorPlan -r 1.0 0.7" in tcl
    assert "place_opt_design" in tcl
    assert "ccopt_design" in tcl
    assert "routeDesign" in tcl
    assert "verify_drc" in tcl


def test_calibre_runset_generation() -> None:
    """Validate Siemens Calibre nmDRC and nmLVS runset generation."""
    cfg = CalibrePhysicalConfig(
        top_module="top",
        gds_path="top.gds",
        drc_rule_deck="/pdk/calibre/drc.rules",
        lvs_rule_deck="/pdk/calibre/lvs.rules",
        schematic_netlist_path="top.sp",
        num_cpus=32,
    )
    runsets = CommercialTCLGenerator.generate_calibre_runset(cfg)
    assert cfg.drc_runset_path in runsets
    assert cfg.lvs_runset_path in runsets
    assert "*cmnNumCPUs: 32" in runsets[cfg.drc_runset_path]
    assert "*lvsLayoutPrimary: top" in runsets[cfg.lvs_runset_path]


def test_grid_cluster_dispatcher_commands() -> None:
    """Verify LSF, Slurm, and SGE submission command construction."""
    spec = GridJobSpec(
        job_name="sta_run_01",
        command=["pt_shell", "-f", "run.tcl"],
        workdir=Path("/scratch/job01"),
        queue_or_partition="priority",
        num_cpus=16,
        memory_gb=64,
    )

    lsf_disp = GridClusterDispatcher(scheduler="lsf")
    lsf_cmd = lsf_disp.build_submit_command(spec)
    assert lsf_cmd[0] == "bsub"
    assert "-q" in lsf_cmd and "priority" in lsf_cmd
    assert "-n" in lsf_cmd and "16" in lsf_cmd

    slurm_disp = GridClusterDispatcher(scheduler="slurm")
    slurm_cmd = slurm_disp.build_submit_command(spec)
    assert slurm_cmd[0] == "sbatch"
    assert "--partition" in slurm_cmd and "priority" in slurm_cmd
    assert "--cpus-per-task" in slurm_cmd and "16" in slurm_cmd
    assert "--mem" in slurm_cmd and "64G" in slurm_cmd


def test_flexlm_monitor() -> None:
    """FlexLMMonitor returns valid license telemetry even when lmutil is absent."""
    res = FlexLMMonitor.check_feature_availability("PrimeTime")
    assert "available" in res
    assert res["total_licenses"] != 0


def test_primetime_log_parser() -> None:
    """Validate PrimeTime MCMM log parser for clean vs violated reports."""
    clean_log = (
        "SCENARIO: func_ss | SETUP_WNS: 0.120 | HOLD_WNS: 0.050\n"
        "SCENARIO: func_ff | SETUP_WNS: 0.350 | HOLD_WNS: 0.015\n"
        "[MIND3_PT_COMPLETE]\n"
    )
    res_clean = parse_primetime_log(clean_log)
    assert res_clean["timing_passed"] is True
    assert res_clean["scenario_count"] == 2
    assert res_clean["worst_setup_wns"] == 0.120

    violated_log = (
        "SCENARIO: func_ss | SETUP_WNS: -0.240 | HOLD_WNS: 0.050\n"
        "[MIND3_PT_COMPLETE]\n"
    )
    res_viol = parse_primetime_log(violated_log)
    assert res_viol["timing_passed"] is False
    assert res_viol["worst_setup_wns"] == -0.240


def test_innovus_log_parser() -> None:
    """Validate Innovus PnR log parser."""
    clean_log = (
        "Total number of DRC violations : 0\n"
        "Total number of connectivity errors : 0\n"
        "Total routing overflow : 0.00%\n"
        "[MIND3_INNOVUS_COMPLETE]\n"
    )
    assert parse_innovus_log(clean_log)["passed"] is True

    bad_log = (
        "Total number of DRC violations : 14\n"
        "Total number of connectivity errors : 2\n"
        "Total routing overflow : 1.25%\n"
    )
    res_bad = parse_innovus_log(bad_log)
    assert res_bad["passed"] is False
    assert res_bad["drc_violations"] == 14
    assert res_bad["connectivity_errors"] == 2


def test_calibre_parsers() -> None:
    """Validate Calibre nmDRC and nmLVS summary parsers."""
    drc_clean = "TOTAL DRC Results Generated: 0 (0)"
    drc_fail = "TOTAL DRC Results Generated: 42 (120)"
    assert parse_calibre_drc_summary(drc_clean)["clean"] is True
    assert parse_calibre_drc_summary(drc_fail)["clean"] is False

    lvs_correct = "LVS COMPARISON RESULT: CORRECT"
    lvs_fail = "LVS COMPARISON RESULT: INCORRECT\nINCORRECT DEVICE"
    assert parse_calibre_lvs_summary(lvs_correct)["lvs_correct"] is True
    assert parse_calibre_lvs_summary(lvs_fail)["lvs_correct"] is False


def test_commercial_signoff_verifier_end_to_end() -> None:
    """Test CommercialSignoffVerifier across simulated clean receipts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "pt.log").write_text("SCENARIO: func | SETUP_WNS: 0.05 | HOLD_WNS: 0.02\n[MIND3_PT_COMPLETE]", encoding="utf-8")
        (ws / "pnr.log").write_text("Total number of DRC violations : 0\nTotal number of connectivity errors : 0\nTotal routing overflow : 0.00%\n[MIND3_INNOVUS_COMPLETE]", encoding="utf-8")
        (ws / "drc.sum").write_text("TOTAL DRC Results Generated: 0", encoding="utf-8")
        (ws / "lvs.sum").write_text("LVS COMPARISON RESULT: CORRECT", encoding="utf-8")
        (ws / "atpg.rpt").write_text("Test coverage: 99.85%\nTransition fault coverage: 96.20%", encoding="utf-8")

        verifier = CommercialSignoffVerifier(
            top_module="chip",
            sta_log_path="pt.log",
            pnr_log_path="pnr.log",
            drc_summary_path="drc.sum",
            lvs_summary_path="lvs.sum",
            atpg_report_path="atpg.rpt",
        )
        res = verifier.verify(ws, None)  # type: ignore
        assert res.passed is True
        assert res.tapeout_ready is True
        assert "sta" in res.commercial_signoff
        assert "pnr" in res.commercial_signoff
        assert "drc" in res.commercial_signoff
        assert "lvs" in res.commercial_signoff
        assert "atpg" in res.commercial_signoff


def test_tapeout_readiness_audit_content() -> None:
    """Test TapeoutReadinessVerifier with audit_content=True catching invalid content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "design.sta.rpt").write_text("slack (VIOLATED) -0.15", encoding="utf-8")

        # Default presence check passes because file exists
        v_presence = TapeoutReadinessVerifier(required_receipts=["sta"], audit_content=False)
        assert v_presence.verify(ws, None).passed is True  # type: ignore

        # Content audit must fail because of VIOLATED
        v_audit = TapeoutReadinessVerifier(required_receipts=["sta"], audit_content=True)
        res = v_audit.verify(ws, None)  # type: ignore
        assert res.passed is False
        assert res.error_category == "TAPEOUT_EVIDENCE_REJECTED"
        assert "VIOLATED" in str(res.failure_reason)
