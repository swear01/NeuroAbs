clear -all
analyze -sva wrapper_abstract_2.v
elaborate -top wrapper
reset rst
#reset rst_i dwb_rst_i dwb_rst_i iwb_rst_i
# stopat {RTL.ex_alu_result}
clock clk
prove -bg -all
# prove {coverage_[2017]==0}
# set all_covers [get_property_list]

# foreach cov $all_covers {
#   visualize -cover -property $cov -new_window 
#   set filename [regsub -all {[\]\[} $cov _].vcd
#   visualize -save -vcd $filename -force -window $cov
# }