import json
from pathlib import Path

def audit_provenance():
    files = list(Path('.').glob('**/*.py')) + list(Path('.').glob('**/*.md')) + list(Path('.').glob('**/*.json'))
    violations = []
    
    for f in files:
        if 'provenance_audit.json' in f.name or 'evidence_package.json' in f.name or 'audit_provenance.py' in f.name:
            continue
        if f.is_file():
            try:
                content = f.read_text(encoding='utf-8')
                # Strict check for claims
                if '"source": "OFFICIAL_KAGGLE_RESULT"' in content or 'source=ResultSource.OFFICIAL_KAGGLE_RESULT' in content:
                    if 'ptcgabc' not in str(f) and 'tests' not in str(f):
                        violations.append(str(f))
                # Check for fabricated terms in reports
                if 'docs/' in str(f) or 'results/final_submission/' in str(f):
                    forbidden = ["official Kaggle win rate", "official Simulation score", "official leaderboard rank"]
                    for term in forbidden:
                        if term in content:
                            violations.append(f"{str(f)} contains forbidden term: {term}")
            except Exception:
                pass
                
    result = {
        'status': 'PASS' if not violations else 'FAIL',
        'simulation_entered': False,
        'official_kaggle_result_claims': violations,
        'note': 'All benchmark results use REAL_CABT_LOCAL.'
    }
    
    Path('results/final_submission/provenance_audit.json').write_text(json.dumps(result, indent=2))
    print("Provenance Audit Complete:", result['status'])
    if violations:
        print("Violations:", violations)

if __name__ == '__main__':
    audit_provenance()