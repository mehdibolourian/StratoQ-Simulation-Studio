"""Runtime smoke test for actual full-horizon Gurobi MILP; requires a Gurobi license.
Run: cd backend && python verify_offline_runtime.py
"""
import gurobipy as gp
from stratoq_demo.setup import default_scenario, build_links
from stratoq_demo.offline_allocator import solve_offline

scenario=default_scenario()
scenario.config.allocation_mode='optimal'
scenario.config.optimality_gap=0.0
records=build_links(scenario)
ids=[r['id'] for r in records]
rates=[{k:5000. for k in ids},{k:0. for k in ids}]
frames, info=solve_offline(scenario,[records,records],rates,{k:1e6 for k in ids},
                           {'d-1':[4000.,4000.]},300,gp)
served=sum(f['served']['d-1'] for f in frames)*300
print('Gurobi:',gp.gurobi.version(),'Status:',info['gurobi_status'],
      'MILP gap:',info['achieved_mip_gap'],'Variables:',info['gurobi_variable_count'],
      'Constraints:',info['gurobi_constraint_count'])
for i,frame in enumerate(frames):
    print('Slot',i+1,'Served bits:',frame['served']['d-1']*300,
          'Activated GS–HAP links:',sorted(frame['activated']),
          'QKP:',frame['buffers'])
print('Total served bits:',served)
assert info['gurobi_status']=='OPTIMAL'
assert abs(served-1500000)<5, 'Unexpected offline key-flow/QKP result'
print('PASS: solved a joint two-slot Gurobi MILP, consuming stored QKP in slot two')
