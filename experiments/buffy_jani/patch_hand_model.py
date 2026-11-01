"""Make SMC-ready variants of the hand-written 16-stage FQ-CoDel PRISM model.

tests/models/fqcodel_5i_dtmc_unif.pm (despite its name) gives iq5 arrivals 0.6/0.1/0.1/0.1/0.1.
This writes:
  hand_p0.6.pm  that distribution;  hand_p0.2.pm  uniform 0.2 for iq5 as for iq1..iq4.
Both let `time`, `iq5_cenq` and `iq5_aipg` saturate (TIME_STEPS = 15) so simulation can run past
the horizon. Unchanged within the horizon.
hand.props checks the queries at time-step boundaries (stage=1) with time <= 14. The original
G<=224 bound is not 14 time steps: a time step takes 11..16 PRISM steps, depending on arrivals.
"""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
src = open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "../../tests/models/fqcodel_5i_dtmc_unif.pm")).read()
out = sys.argv[2] if len(sys.argv) > 2 else "."
s = re.sub(r"const int TIME_STEPS = \d+;", "const int TIME_STEPS = 15;", src)
s = s.replace("(time'=time+1)", "(time'=min(TIME_STEPS,time+1))")
s = s.replace("(iq5_aipg'=iq5_aipg+1)", "(iq5_aipg'=min(TIME_STEPS,iq5_aipg+1))")
s = re.sub(r"\(iq5_cenq'=iq5_cenq\+(\d)\)", r"(iq5_cenq'=min(TIME_STEPS*4,iq5_cenq+\1))", s)
open(os.path.join(out, "hand_p0.6.pm"), "w").write(s)
u = s.replace("0.6 : (stage'=REC_PKT_ARR_IQ5) & (iq5_arrivals'=0)", "0.2 : (stage'=REC_PKT_ARR_IQ5) & (iq5_arrivals'=0)")
u = re.sub(r"0\.1 : \(stage'=REC_PKT_ARR_IQ5\)", "0.2 : (stage'=REC_PKT_ARR_IQ5)", u)
open(os.path.join(out, "hand_p0.2.pm"), "w").write(u)
at = "stage=1 & time<=14"
open(os.path.join(out, "hand.props"), "w").write(
    f'"starve_violation": P=? [ F<=400 ({at} & !(iq5_deqs_bl<4)) ];\n'
    f'"cond_a_violation": P=? [ F<=400 ({at} & !((iq5_deqs_bl<4)&((time>5)|(iq5_cenq<2)))) ];\n'
    f'"early_violation": P=? [ F<=400 ({at} & !((time>5)|(iq5_cenq<2))) ];\n'
    f'"gap_violation": P=? [ F<=400 ({at} & !((time<7)|(iq5_aipg>1))) ];\n')
