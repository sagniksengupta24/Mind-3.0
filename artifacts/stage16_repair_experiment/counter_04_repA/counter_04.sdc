# Generated Timing Constraints
create_clock -name clk -period 10.000 [get_ports clk]
set_clock_uncertainty 0.150 [get_clocks clk]
set_input_delay -clock clk 1.000 [all_inputs]
set_output_delay -clock clk 1.000 [all_outputs]
# False paths: insert set_false_path constraints here for asynchronous crossings
# Multicycle paths: insert set_multicycle_path constraints here for multi-cycle logic
