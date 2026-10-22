import sys,traceback
from pathlib import Path
root=Path(__file__).resolve().parent.parent
try:
    import core
    from ortools.sat.python import cp_model
    m=cp_model.CpModel();x=m.NewIntVar(0,2,'x');m.Add(x==1);s=cp_model.CpSolver()
    assert s.Solve(m)==cp_model.OPTIMAL and s.Value(x)==1
    # Έλεγχος μηχανισμού διάγνωσης (υποθέσεις) που χρησιμοποιεί η έκδοση 0.2
    m=cp_model.CpModel();a=m.NewBoolVar('a');b=m.NewBoolVar('b');y=m.NewIntVar(0,3,'y')
    m.Add(y>=2).OnlyEnforceIf(a);m.Add(y<=1).OnlyEnforceIf([b]);m.AddAssumptions([a,b]);s=cp_model.CpSolver();s.parameters.num_search_workers=1
    assert s.Solve(m)==cp_model.INFEASIBLE and set(s.SufficientAssumptionsForInfeasibility())<= {a.Index(),b.Index()}
    import rules
    (root/'data').mkdir(exist_ok=True)
    (root/'data'/'diagnostics.txt').write_text('OK\nPython: '+sys.version+'\nCP-SAT native solver: OK\n',encoding='utf-8')
    print('Runtime and solver: OK')
except Exception:
    text=traceback.format_exc();print(text)
    try:(root/'data'/'diagnostics.txt').write_text(text,encoding='utf-8')
    except OSError:pass
    sys.exit(1)
