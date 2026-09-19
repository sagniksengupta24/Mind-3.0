"""Tests for Multi-Objective Pareto PPA Optimization and Repair Strategy Engine."""

from mind3.core.driver import PPAOptimizer, PPAPoint


def test_ppa_optimizer_pareto_frontier() -> None:
    """Validate that PPAOptimizer identifies strictly non-dominated Pareto designs."""
    opt = PPAOptimizer()

    # Point 1: Fast, High Power, High Area (Pareto optimal for high performance)
    opt.record_point(turn=0, frequency_mhz=1000.0, setup_wns_ps=50.0, power_mw=50.0, area_um2=1000.0)

    # Point 2: Slower, Low Power, Low Area (Pareto optimal for low power)
    opt.record_point(turn=1, frequency_mhz=800.0, setup_wns_ps=100.0, power_mw=25.0, area_um2=600.0)

    # Point 3: Slower, Higher Power, Higher Area than Point 2 (Dominated!)
    opt.record_point(turn=2, frequency_mhz=750.0, setup_wns_ps=10.0, power_mw=40.0, area_um2=800.0)

    # Point 4: Failed timing (Should never be in Pareto frontier)
    opt.record_point(turn=3, frequency_mhz=1200.0, setup_wns_ps=-150.0, power_mw=70.0, area_um2=1100.0, passes_timing=False)

    frontier = opt.get_pareto_frontier()
    assert len(frontier) == 2
    freqs = {p.frequency_mhz for p in frontier}
    assert 1000.0 in freqs
    assert 800.0 in freqs
    assert 750.0 not in freqs
    assert 1200.0 not in freqs


def test_ppa_repair_strategy_selection() -> None:
    """Validate repair strategy recommendations based on timing slack and physical metrics."""
    # Critical setup slack violation (> 500ps deficit)
    strat_crit = PPAOptimizer.suggest_repair_strategy(
        error_category="TIMING_SLACK_VIOLATION",
        failure_reason="Setup violation",
        wns_ps=-650.0,
    )
    assert "pipeline register stages" in strat_crit.lower()

    # Moderate setup slack violation (< 500ps deficit)
    strat_mod = PPAOptimizer.suggest_repair_strategy(
        error_category="TIMING_SLACK_VIOLATION",
        failure_reason="Setup violation",
        wns_ps=-120.0,
    )
    assert "retiming" in strat_mod.lower()

    # Hold slack violation
    strat_hold = PPAOptimizer.suggest_repair_strategy(
        error_category="HOLD_SLACK_VIOLATION",
        failure_reason="Hold violation",
    )
    assert "buffer" in strat_hold.lower()

    # PnR placement overflow
    strat_pnr = PPAOptimizer.suggest_repair_strategy(
        error_category="PNR_PLACEMENT_FAILED",
        failure_reason="Placement congestion",
    )
    assert "utilization" in strat_pnr.lower()

    # CDC crossing
    strat_cdc = PPAOptimizer.suggest_repair_strategy(
        error_category="CDC_VIOLATION",
        failure_reason="Unregistered crossing",
    )
    assert "synchronizer" in strat_cdc.lower()
