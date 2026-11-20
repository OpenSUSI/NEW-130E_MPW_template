// =============================================================================
// OpenSUSI x Google AI-Assisted Chip Design Platform — Reference PoC RTL
// Module : top (4-bit Registered ALU & Accumulator)
// Target : TR-1um PoC / NEW-130E 130nm Template
// =============================================================================

module top (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    input  wire [1:0] op,
    input  wire [3:0] in_data,
    output wire [3:0] out_data,
    output reg        carry
);

    reg [3:0] acc;
    reg [4:0] alu_res;

    assign out_data = acc;

    always @(*) begin
        case (op)
            2'b00:   alu_res = {1'b0, acc} + {1'b0, in_data};        // ADD
            2'b01:   alu_res = {1'b0, acc} - {1'b0, in_data};        // SUB (MSB = borrow)
            2'b10:   alu_res = {1'b0, acc ^ in_data};                // XOR
            default: alu_res = {acc[3], acc[2:0], in_data[0]};       // ROL + LSB inject
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc   <= 4'h0;
            carry <= 1'b0;
        end else if (en) begin
            acc   <= alu_res[3:0];
            carry <= alu_res[4];
        end
    end

endmodule
