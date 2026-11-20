`timescale 1ns/1ps

module tb_top;
    reg        clk;
    reg        rst_n;
    reg        en;
    reg  [1:0] op;
    reg  [3:0] in_data;
    wire [3:0] out_data;
    wire       carry;

    reg  [3:0] exp_acc;
    reg        exp_carry;
    integer    errors;
    integer    tests;

    top dut (
        .clk      (clk),
        .rst_n    (rst_n),
        .en       (en),
        .op       (op),
        .in_data  (in_data),
        .out_data (out_data),
        .carry    (carry)
    );

    initial clk = 1'b0;
    always #50 clk = ~clk;

    task check_outputs;
        input [255:0] label;
        begin
            tests = tests + 1;
            if (out_data !== exp_acc || carry !== exp_carry) begin
                $display("FAIL [%0s]: got out_data=%h carry=%b, expected out_data=%h carry=%b (t=%0t)",
                         label, out_data, carry, exp_acc, exp_carry, $time);
                errors = errors + 1;
            end
        end
    endtask

    task apply_cycle;
        input        t_en;
        input [1:0]  t_op;
        input [3:0]  t_in;
        input [255:0] label;
        reg   [4:0]  nxt;
        begin
            @(negedge clk);
            en      = t_en;
            op      = t_op;
            in_data = t_in;
            if (t_en) begin
                case (t_op)
                    2'b00:   nxt = {1'b0, exp_acc} + {1'b0, t_in};
                    2'b01:   nxt = {1'b0, exp_acc} - {1'b0, t_in};
                    2'b10:   nxt = {1'b0, exp_acc ^ t_in};
                    default: nxt = {exp_acc[3], exp_acc[2:0], t_in[0]};
                endcase
                exp_acc   = nxt[3:0];
                exp_carry = nxt[4];
            end
            @(posedge clk);
            #10;
            check_outputs(label);
        end
    endtask

    integer i;

    initial begin
        errors    = 0;
        tests     = 0;
        rst_n     = 1'b0;
        en        = 1'b0;
        op        = 2'b00;
        in_data   = 4'h0;
        exp_acc   = 4'h0;
        exp_carry = 1'b0;

        #120;
        check_outputs("async_reset");

        // Release reset
        @(negedge clk);
        rst_n = 1'b1;

        // Hold with en=0
        apply_cycle(1'b0, 2'b00, 4'hF, "hold_zero");

        // Directed ADD, carry, SUB, borrow, XOR, ROL tests
        apply_cycle(1'b1, 2'b00, 4'h5, "add_0_plus_5");
        apply_cycle(1'b1, 2'b00, 4'h7, "add_5_plus_7");
        apply_cycle(1'b1, 2'b00, 4'h8, "add_C_plus_8_carry");
        apply_cycle(1'b0, 2'b01, 4'hF, "hold_after_carry");
        apply_cycle(1'b1, 2'b01, 4'h3, "sub_4_minus_3");
        apply_cycle(1'b1, 2'b01, 4'h5, "sub_1_minus_5_borrow");
        apply_cycle(1'b1, 2'b10, 4'hA, "xor_C_with_A");
        apply_cycle(1'b1, 2'b11, 4'h1, "rol_inject_1");
        apply_cycle(1'b1, 2'b11, 4'h0, "rol_inject_0");
        apply_cycle(1'b1, 2'b11, 4'h1, "rol_carry_out");

        // Sweep across all 4 ops x 16 inputs = 64 cycles
        for (i = 0; i < 64; i = i + 1) begin
            apply_cycle(1'b1, i[5:4], i[3:0], "sweep");
        end

        // Mid-run async reset check
        @(negedge clk);
        rst_n     = 1'b0;
        exp_acc   = 4'h0;
        exp_carry = 1'b0;
        #20;
        check_outputs("mid_run_reset");

        if (errors == 0) begin
            $display("PASS: %0d/%0d checks passed.", tests, tests);
            $finish;
        end else begin
            $display("FAIL: %0d errors out of %0d checks.", errors, tests);
            $fatal(1);
        end
    end
endmodule
