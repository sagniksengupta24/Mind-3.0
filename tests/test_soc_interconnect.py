"""Tests for SoC Interconnect Crossbar Synthesis, SVA VIP, and Memory MBIST Collars."""

from mind3.soc import (
    AMBAInterconnectGenerator,
    CrossbarConfig,
    MasterPortSpec,
    MemoryCompilerWrapper,
    ProtocolVIPChecker,
    SlavePortSpec,
)


def test_axi4_lite_crossbar_synthesis() -> None:
    """Validate synthesizable AXI4-Lite crossbar generator."""
    cfg = CrossbarConfig(
        module_name="soc_crossbar",
        masters=[MasterPortSpec(name="m_cpu")],
        slaves=[
            SlavePortSpec(name="s_uart", base_addr=0x10000000, size_bytes=0x1000),
            SlavePortSpec(name="s_timer", base_addr=0x20000000, size_bytes=0x1000),
            SlavePortSpec(name="s_sram", base_addr=0x80000000, size_bytes=0x10000),
        ],
    )

    verilog = AMBAInterconnectGenerator.build_axi4_lite_crossbar(cfg)
    assert "module soc_crossbar" in verilog
    assert "32'h10000000" in verilog
    assert "32'h10000fff" in verilog
    assert "32'h20000000" in verilog
    assert "32'h80000000" in verilog
    assert "m0_bresp   = 2'b11; // DECERR" in verilog
    assert "m0_rdata   = 32'hDEADBEEF;" in verilog


def test_protocol_vip_sva_assertions() -> None:
    """Validate SVA Protocol Verification IP (VIP) generation."""
    vip = ProtocolVIPChecker.generate_axi_vip(prefix="m_dma")
    assert "property p_m_dma_awvalid_stable;" in vip
    assert "property p_m_dma_awaddr_stable;" in vip
    assert "property p_m_dma_wvalid_stable;" in vip
    assert "property p_m_dma_arvalid_stable;" in vip
    assert "property p_m_dma_bvalid_after_write;" in vip
    assert "[AXI_VIP_VIOLATION]" in vip


def test_sram_mbist_collar_generation() -> None:
    """Validate Foundry SRAM memory compiler MBIST collar generation."""
    sram_v = MemoryCompilerWrapper.generate_sram_collar(
        module_name="sram_1024x32",
        addr_width=10,
        data_width=32,
        num_words=1024,
    )
    assert "module sram_1024x32" in sram_v
    assert "mbist_en ? mbist_cs_n : cs_n" in sram_v
    assert "mbist_en ? mbist_we_n : we_n" in sram_v
    assert "mbist_en ? mbist_addr : addr" in sram_v
    assert "mbist_dout = sram_dout;" in sram_v
