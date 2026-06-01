#!/usr/bin/env python3
"""Verification script for Phase 5 LangGraph Agents implementation."""
import sys
import os

# Add src to path
sys.path.insert(0, '/Users/leander/personal-projects/plutus-app/src')

results = {
    'file_checks': [],
    'import_checks': [],
    'graph_compilation': None,
    'function_imports': [],
    'errors': []
}

# 1. File existence check
print("=" * 60)
print("1. FILE EXISTENCE CHECK")
print("=" * 60)
files = [
    'openrouter_client.py',
    'prompts.py',
    'technical.py',
    'sentiment.py',
    'smart_money.py',
    'risk_manager.py',
    'synthesizer.py',
    'graph.py'
]

agents_dir = '/Users/leander/personal-projects/plutus-app/src/plutus/agents'
for f in files:
    path = os.path.join(agents_dir, f)
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    status = "✓" if exists else "✗"
    print(f"{status} {f} ({size} bytes)")
    results['file_checks'].append({'file': f, 'exists': exists, 'size': size})

# 2. Module import checks
print("\n" + "=" * 60)
print("2. MODULE IMPORT CHECKS")
print("=" * 60)

modules = [
    'plutus.agents.openrouter_client',
    'plutus.agents.prompts',
    'plutus.agents.technical',
    'plutus.agents.sentiment',
    'plutus.agents.smart_money',
    'plutus.agents.risk_manager',
    'plutus.agents.synthesizer',
    'plutus.agents.graph'
]

for mod in modules:
    try:
        __import__(mod)
        print(f"✓ {mod}")
        results['import_checks'].append({'module': mod, 'success': True, 'error': None})
    except Exception as e:
        print(f"✗ {mod}: {type(e).__name__}: {e}")
        results['import_checks'].append({'module': mod, 'success': False, 'error': str(e)})
        results['errors'].append(f"Import failed for {mod}: {e}")

# 3. Graph compilation test
print("\n" + "=" * 60)
print("3. GRAPH COMPILATION TEST")
print("=" * 60)

try:
    from plutus.agents.graph import build_graph
    graph = build_graph()
    print(f"✓ Graph compiled successfully")
    print(f"  Graph type: {type(graph)}")
    results['graph_compilation'] = {'success': True, 'error': None}
except Exception as e:
    print(f"✗ Graph compilation failed: {type(e).__name__}: {e}")
    results['graph_compilation'] = {'success': False, 'error': str(e)}
    results['errors'].append(f"Graph compilation failed: {e}")

# 4. Function import verification
print("\n" + "=" * 60)
print("4. FUNCTION IMPORT VERIFICATION")
print("=" * 60)

function_checks = [
    ('plutus.agents.graph', 'run_analysis'),
    ('plutus.agents.graph', 'build_graph'),
    ('plutus.agents.technical', 'run_technical_analysis'),
    ('plutus.agents.sentiment', 'run_sentiment_analysis'),
    ('plutus.agents.smart_money', 'run_smart_money_analysis'),
    ('plutus.agents.risk_manager', 'run_risk_manager'),
    ('plutus.agents.synthesizer', 'run_synthesizer'),
    ('plutus.agents.openrouter_client', 'call_llm'),
]

for module_name, func_name in function_checks:
    try:
        mod = __import__(module_name, fromlist=[func_name])
        func = getattr(mod, func_name)
        print(f"✓ {module_name}.{func_name}")
        results['function_imports'].append({'module': module_name, 'function': func_name, 'success': True, 'error': None})
    except Exception as e:
        print(f"✗ {module_name}.{func_name}: {type(e).__name__}: {e}")
        results['function_imports'].append({'module': module_name, 'function': func_name, 'success': False, 'error': str(e)})
        results['errors'].append(f"Function import failed for {module_name}.{func_name}: {e}")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
files_ok = all(r['exists'] for r in results['file_checks'])
imports_ok = all(r['success'] for r in results['import_checks'])
graph_ok = results['graph_compilation'] and results['graph_compilation']['success']
functions_ok = all(r['success'] for r in results['function_imports'])

print(f"Files: {'✓ PASS' if files_ok else '✗ FAIL'} ({sum(1 for r in results['file_checks'] if r['exists'])}/{len(results['file_checks'])})")
print(f"Imports: {'✓ PASS' if imports_ok else '✗ FAIL'} ({sum(1 for r in results['import_checks'] if r['success'])}/{len(results['import_checks'])})")
print(f"Graph compilation: {'✓ PASS' if graph_ok else '✗ FAIL'}")
print(f"Function imports: {'✓ PASS' if functions_ok else '✗ FAIL'} ({sum(1 for r in results['function_imports'] if r['success'])}/{len(results['function_imports'])})")

if results['errors']:
    print(f"\nErrors encountered: {len(results['errors'])}")
    for err in results['errors']:
        print(f"  - {err}")

overall = files_ok and imports_ok and graph_ok and functions_ok
print(f"\nOVERALL: {'✓ PASS' if overall else '✗ FAIL'}")
sys.exit(0 if overall else 1)
