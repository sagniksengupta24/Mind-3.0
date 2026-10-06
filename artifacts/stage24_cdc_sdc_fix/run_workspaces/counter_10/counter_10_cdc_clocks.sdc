create_clock -name clk -period 10.000 [get_ports clk]
set_input_delay -clock clk 1.000 [get_ports rst_n]
set_input_delay -clock clk 1.000 [get_ports strobe]
