"""Harness"""
import subprocess, sys, os
os.chdir(r'f:\kelaode\Data\Agents\zhongji8633\wudi8633\backend')
target = sys.argv[1] if len(sys.argv) > 1 else 'app/tests/'
r = subprocess.run(
    [r'F:\kelaode\Data\Agents\zqibcc8w9\tools\Python311\python.exe', '-m', 'pytest',
     target, '-q', '--tb=short', '-p', 'no:cacheprovider', '--no-header',
     '-W', 'ignore::DeprecationWarning', '-W', 'ignore::PendingDeprecationWarning'],
    capture_output=True, text=True, timeout=300,
)
print(f'exit: {r.returncode}')
print('=== STDOUT (last 4000) ===')
print(r.stdout[-4000:])
print('=== STDERR (last 1500) ===')
print(r.stderr[-1500:])
