# Project Notes

- Every LLM backend must prepend `src/initial_context.txt` to the per-statement
  message. The examples and abstraction rules in that file are part of the
  NeuroAbs experiment prompt, not optional setup text.
- Keep the paper's checker experiments separate: RQ2 uses rIC3 portfolio formal
  proof with a 3600-second cap, while RQ3 uses kissat BMC depth exploration only
  when formal proof does not conclude. The paper concluded the I2C and PicoRV32
  cases in RQ2 and therefore omitted them from RQ3.
- Pono returning `unknown` after the CEGAR bound-25 query only means that query
  found no usable counterexample; it is not a property proof. A modern rIC3
  `UNSAT` result is the proof, and rIC3 reports that result with exit status 20.
