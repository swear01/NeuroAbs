# NeuroAbs EDA handoff

## Executive takeaway

NeuroAbs is a 2026 ICCAD work that uses an LLM to propose property-guided RTL
rewrites, admits only sound over-approximations through SMT checks, and uses
R-CEGAR to restore logic when an abstraction causes a spurious counterexample.
It is relevant to EDA work because the LLM proposes where and how to simplify,
while formal methods remain responsible for accepting the rewrite and proving
the final property.

This fork has validated that public flow on one I2C scenario with Muse Spark
1.2 Contributor. The result is strong enough to demonstrate a working
LLM-plus-formal abstraction pipeline. It is not evidence that Muse reproduced
the authors' aggregate speedup.

Primary references:

- [NeuroAbs paper](https://arxiv.org/html/2608.17304)
- [Authors' detailed Figure 7 data](https://figshare.com/articles/dataset/LLMAbstractor_LLM-Assisted_RTL_Abstraction_for_Hardware_Property_Checking_Acceleration/30633074)
- [Local I2C evidence](../results/i2c_assert1/README.md)

## What the authors established

The paper evaluates two different questions that must not be collapsed:

- RQ1 reports whether generated statements are sound OAs and whether they are
  strict rather than equivalent no-ops. The full method reports a 95.27% OA
  rate and 236.17 strict OAs on average across its evaluation.
- RQ2 checks whether the final abstract models accelerate formal proof. In the
  authors' detailed data, the I2C prescaler low-byte case takes 0.90 seconds
  with concrete rIC3 and 0.08 seconds with rIC3 plus LLMAbstractor.

Those numbers use the authors' GPT-4o-mini-based LLMAbstractor, checker setup,
and Xeon machine. They are reference results, not directly matched measurements
for the Muse reproduction.

## What we validated

| Gate | Evidence | Interpretation |
| --- | --- | --- |
| LLM completion | 184/184 Muse responses completed | The backend and prompt path work end to end. |
| Local OA soundness | 184/184 forward counterexample queries were `UNSAT` | Every accepted rewrite includes all behavior of its original statement. |
| Strictness | 182/184 reverse queries were `SAT`; requests 21 and 52 were equivalent | 182 rewrites add behavior; two only change formatting. |
| Manual review | All 184 pairs inspected; 182 preserve the target/operator and replace the RHS with X, while two reproduce the original RHS | The observed syntax agrees with the formal classification. |
| Effective final rewrites | 121 distinct assignments use fresh inputs: 10 in `i2c_master_top`, 74 in `i2c_master_bit_ctrl`, and 37 in `i2c_master_byte_ctrl` | The 182 strict attempts are not 182 distinct final locations; repeated text can be rewritten again and supersede an earlier input. |
| Generated model | Yosys accepted the wrapper and produced BTOR2 | The effective local rewrites compose into a checkable model. |
| CEGAR | Pono returned `UNKNOWN` through bound 25 with zero refinements | This is neither failure nor a property proof; it only means no usable bounded counterexample was returned. |
| Final proof | rIC3 portfolio returned `UNSAT`, exit status 20 | The safety property is formally proved on the over-approximate model and therefore on the concrete model. |

One retained Muse proof-mode invocation took 0.20 seconds. Ten later Muse proof
runs had a 0.105-second median and 0.100-second mean; the concrete model had a
0.100-second median and 0.094-second mean. At this scale, startup and scheduling
noise dominate. The correct conclusion is successful abstraction and proof,
not a local checker speedup.

## Manual OA review

The 184 original/abstract pairs were read in request order. The audit found only
two output shapes:

1. 182 strict rewrites keep the same assignment target and assignment operator,
   replacing the complete right-hand expression with `'bx` or `1'bx`. NeuroAbs
   converts that X-value into a fresh free input. Replacing one deterministic
   next-state value with an arbitrary value weakens the transition relation, so
   it is a legal over-approximation.
2. Request 21 (`c_state <= idle`) and request 52 (`cnt <= cnt`) preserve the
   original expression and differ only in formatting. They are sound but
   equivalent no-ops, not effective abstractions.

This manual result agrees with the transition-aware SMT report: 184 sound, 182
strict, two equivalent, and zero invalid. It also shows that Muse's successful
outputs in this run are simple and highly aggressive local rewrites rather than
subtle algebraic simplifications.

The attempt-level report is not a final-location count. The generated metadata
contains 182 inputs, but only 121 appear on assignment right-hand sides in the
final wrapper. Repeated textual statements can be selected and rewritten again,
leaving an earlier input declared but superseded. Effectiveness reports must
therefore include both strict attempts and distinct effective final locations.

## Safe claim boundary

We can say:

- the paper's central LLM-proposal plus formal-acceptance architecture is
  reproducible on this public I2C scenario;
- Muse produced 182 formally strict statement-level OA attempts and two harmless
  no-ops, resulting in 121 distinct fresh-input assignments in the final wrapper;
- the composed abstract model passed Yosys and a complete rIC3 safety proof;
- the author's 0.08-second result and our 0.20-second initial result are the same
  order of magnitude on this very easy case.

We should not say:

- Muse reproduced the authors' GPT-4o-mini outputs;
- this single scenario reproduces the paper's aggregate acceleration;
- `184/184 UNSAT` alone proves abstraction effectiveness;
- Pono's bounded `UNKNOWN` is a proof;
- the 0.08- and 0.20-second values are an apples-to-apples performance result.

## Extending to more aggressive abstraction

The 182 Muse rewrites already replace the entire RHS at each selected assignment,
so there is little room to make an individual rewrite coarser. The next research
lever is to expand or coordinate the abstraction scope while retaining the same
soundness and CEGAR gates:

1. Fix rewrite identity and accounting so repeated statement text cannot hide or
   overwrite distinct source locations. Report requested, accepted, strict, and
   effective final locations separately.
2. Select property-guided cutpoints farther upstream and replace whole cones of
   irrelevant combinational logic with fresh inputs.
3. Generate coordinated multi-statement abstractions for state-machine branches
   or datapath regions instead of treating every assignment independently.
4. Add bit- or field-level abstraction so only property-irrelevant register bits
   become nondeterministic while relevant bits remain concrete.
5. Rank candidates by estimated model-checking cost and expected circuit-size
   reduction, then let CEGAR restore only the abstractions implicated by a
   spurious counterexample.
6. Evaluate on a case whose concrete proof takes seconds or minutes. Measure
   circuit size, checker-only time, end-to-end time, strict OA count, effective
   rewrite locations, and CEGAR refinements under matched conditions.

Every extension must preserve the evaluation gate in
[`evaluation.md`](evaluation.md): sound OA first, semantic strictness second,
then generated-model validation, CEGAR classification, and matched concrete vs.
abstract proof measurements.

## Shareable summary

> NeuroAbs shows a practical way to combine LLM semantic judgment with formal
> guarantees for RTL abstraction. We reproduced one public I2C scenario with
> Muse: 184/184 rewrite attempts were sound, 182 were strict abstractions, 121
> distinct fresh-input assignments remained in the final wrapper, the generated
> model passed synthesis, and rIC3 completed an `UNSAT` proof. The
> authors report 0.08 seconds for their abstract I2C model; our initial proof was
> 0.20 seconds, with a 0.105-second repeated median. This validates the flow, not
> the paper's aggregate speedup. The most useful next step is broader,
> property-guided multi-statement abstraction on a genuinely hard proof case,
> guarded by the same SMT and CEGAR checks.
